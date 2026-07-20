"""Tidal provider implementation."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import logging
from time import monotonic, sleep
from typing import TypeVar

from tidal_playlist_builder.exceptions import (
    AuthenticationError,
    PlaylistCreationError,
    ValidationError,
)
from tidal_playlist_builder.model import (
    Album,
    Artist,
    PlaylistBuildPlan,
    PlaylistConflictAction,
    PlaylistSummary,
    Track,
)
from tidal_playlist_builder.repositories import (
    AlbumRepository,
    ArtistRepository,
    PlaylistRepository,
)
from tidal_playlist_builder.services.cache_service import CacheService
from tidal_playlist_builder.services.interfaces import IMusicProvider

from .api_client import TidalApiClient

ResponseT = TypeVar("ResponseT")
ProgressCallback = Callable[["PlaylistCreationProgress"], None]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlaylistCreationProgress:
    """Progress event for playlist creation."""

    phase: str
    completed: int
    total: int
    message: str


class PlaylistCreationCancelledError(PlaylistCreationError):
    """Raised when playlist creation is cancelled."""


class CancellationToken:
    """Simple cancellation token for cooperative cancellation."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass(slots=True)
class RequestRateLimiter:
    """Simple request rate limiter."""

    min_interval_seconds: float = 0.0
    now: Callable[[], float] = monotonic
    sleeper: Callable[[float], None] = sleep
    _last_request_at: float | None = None

    def wait_if_needed(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        current = self.now()
        if self._last_request_at is None:
            self._last_request_at = current
            return

        elapsed = current - self._last_request_at
        delay = self.min_interval_seconds - elapsed
        if delay > 0:
            self.sleeper(delay)
            current = self.now()
        self._last_request_at = current


class TidalProvider(IMusicProvider):
    """Tidal provider using repositories, cache, retries, and rate limiting."""

    def __init__(
        self,
        api_client: TidalApiClient,
        cache_service: CacheService | None = None,
        artist_repository: ArtistRepository | None = None,
        album_repository: AlbumRepository | None = None,
        playlist_repository: PlaylistRepository | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.1,
        retry_on: tuple[type[Exception], ...] = (TimeoutError, ConnectionError),
        rate_limiter: RequestRateLimiter | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if max_retries < 0:
            raise ValidationError("max_retries must be >= 0")
        if retry_backoff_seconds < 0:
            raise ValidationError("retry_backoff_seconds must be >= 0")
        self._api_client = api_client
        self._cache = cache_service or CacheService()
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._retry_on = retry_on
        self._rate_limiter = rate_limiter or RequestRateLimiter()
        self._sleeper = sleeper
        self._access_token: str | None = None
        self._authenticated_username: str | None = None

        self._artist_repository = artist_repository or ArtistRepository(
            cache=self._cache,
            search_operation=self._api_client.search_artists,
        )
        self._album_repository = album_repository or AlbumRepository(
            cache=self._cache,
            album_operation=self._api_client.get_artist_albums,
            track_operation=self._api_client.get_album_tracks,
        )
        self._playlist_repository = playlist_repository or PlaylistRepository(
            create_operation=self._api_client.create_playlist,
            add_tracks_operation=self._api_client.add_tracks_to_playlist,
            list_playlists_operation=self._api_client.list_playlists,
            playlist_track_ids_operation=self._api_client.get_playlist_track_ids,
            remove_tracks_operation=self._api_client.remove_tracks_from_playlist,
            delete_operation=self._api_client.delete_playlist,
        )

    @property
    def artist_repository(self) -> ArtistRepository:
        return self._artist_repository

    @property
    def album_repository(self) -> AlbumRepository:
        return self._album_repository

    @property
    def playlist_repository(self) -> PlaylistRepository:
        return self._playlist_repository

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    @property
    def authenticated_username(self) -> str | None:
        return self._authenticated_username

    def authenticate(self, credentials: dict[str, str]) -> None:
        if not credentials:
            raise ValidationError("credentials cannot be empty")
        token = self._execute_with_resilience(
            lambda: self._api_client.authenticate(credentials)
        )
        if not token.strip():
            raise AuthenticationError("authentication returned empty token")
        self._access_token = token
        username = credentials.get("username")
        self._authenticated_username = username.strip() if username else None
        self._cache.clear()
        logger.info("Provider authentication succeeded")

    def clear_authentication(self) -> None:
        self._access_token = None
        self._authenticated_username = None
        clear_operation = getattr(self._api_client, "clear_authentication", None)
        if callable(clear_operation):
            clear_operation()

    def search_artists(self, query: str, limit: int = 10) -> list[Artist]:
        self._ensure_authenticated()
        if not query.strip():
            raise ValidationError("query cannot be empty")
        if limit <= 0:
            raise ValidationError("limit must be positive")
        return self._execute_with_resilience(
            lambda: self._artist_repository.search(query, limit)
        )

    def get_artist_albums(self, artist_id: str) -> list[Album]:
        self._ensure_authenticated()
        if not artist_id.strip():
            raise ValidationError("artist_id cannot be empty")
        return self._execute_with_resilience(
            lambda: self._album_repository.get_artist_albums(artist_id)
        )

    def get_album_tracks(self, album_id: str) -> list[Track]:
        self._ensure_authenticated()
        if not album_id.strip():
            raise ValidationError("album_id cannot be empty")
        return self._execute_with_resilience(
            lambda: self._album_repository.get_album_tracks(album_id)
        )

    def create_playlist(
        self,
        plan: PlaylistBuildPlan,
        *,
        conflict_action: PlaylistConflictAction = PlaylistConflictAction.CREATE_ANOTHER,
        existing_playlist_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        batch_size: int = 100,
    ) -> str:
        """Create a Tidal playlist from a build plan."""
        self._ensure_authenticated()
        self._validate_playlist_plan(plan, batch_size)
        resolved_conflict_action = self._resolve_conflict_action(
            conflict_action=conflict_action,
            existing_playlist_id=existing_playlist_id,
        )

        token = cancellation_token or CancellationToken()
        track_ids = [track.id for track in plan.selected_tracks]
        target_track_ids = list(track_ids)

        playlist_name = (
            plan.playlist_name.strip()
            if plan.playlist_name and plan.playlist_name.strip()
            else f"{plan.artist.name} Playlist"
        )
        description = f"{plan.track_count} tracks from selected albums"

        self._check_cancelled(token, "before_create")
        if resolved_conflict_action is PlaylistConflictAction.CANCEL:
            raise PlaylistCreationCancelledError("Playlist creation cancelled by user")

        playlist_id: str
        created_new_playlist = False
        try:
            if resolved_conflict_action is PlaylistConflictAction.CREATE_ANOTHER:
                self._emit_progress(
                    progress_callback,
                    "creating_playlist",
                    0,
                    len(target_track_ids),
                    "Creating playlist shell",
                )
                playlist_id = self._execute_with_resilience(
                    lambda: self._playlist_repository.create_playlist(
                        playlist_name, description
                    )
                )
                self._emit_progress(
                    progress_callback,
                    "playlist_created",
                    0,
                    len(target_track_ids),
                    f"Playlist shell created: {playlist_id}",
                )
                created_new_playlist = True
            else:
                assert existing_playlist_id is not None
                playlist_id = existing_playlist_id
                existing_track_ids = self._load_playlist_track_ids(playlist_id)
                if resolved_conflict_action is PlaylistConflictAction.REPLACE_EXISTING:
                    self._emit_progress(
                        progress_callback,
                        "replacing_playlist",
                        0,
                        len(existing_track_ids),
                        f"Clearing existing playlist: {playlist_id}",
                    )
                    self._clear_playlist_tracks(
                        playlist_id, existing_track_ids, batch_size
                    )
                else:
                    existing_track_set = set(existing_track_ids)
                    target_track_ids = [
                        track_id
                        for track_id in target_track_ids
                        if track_id not in existing_track_set
                    ]
                    self._emit_progress(
                        progress_callback,
                        "appending_playlist",
                        0,
                        len(target_track_ids),
                        f"Appending {len(target_track_ids)} new tracks",
                    )

            self._upload_tracks(
                playlist_id=playlist_id,
                track_ids=target_track_ids,
                progress_callback=progress_callback,
                cancellation_token=token,
                batch_size=batch_size,
            )
            self._cache.invalidate("playlist:")
            self._cache.set(f"playlist:created:{playlist_id}", True, ttl_seconds=300)
            self._emit_progress(
                progress_callback,
                "completed",
                len(target_track_ids),
                len(target_track_ids),
                f"Playlist updated: {playlist_id}",
            )
            logger.info("Playlist creation completed (%s)", playlist_id)
            return playlist_id
        except PlaylistCreationCancelledError:
            logger.warning("Playlist creation cancelled")
            if created_new_playlist:
                self._recover_failed_playlist(playlist_id)
            raise
        except Exception:
            logger.exception("Playlist creation failed")
            if created_new_playlist:
                self._recover_failed_playlist(playlist_id)
            raise

    def find_playlist_by_name(self, playlist_name: str) -> PlaylistSummary | None:
        self._ensure_authenticated()
        normalized_name = playlist_name.strip().casefold()
        if not normalized_name:
            raise ValidationError("playlist_name cannot be empty")
        try:
            playlists = self._execute_with_resilience(
                self._playlist_repository.list_playlists
            )
        except Exception as error:
            raise PlaylistCreationError(
                "Failed to look up existing playlists"
            ) from error
        for playlist in playlists:
            if playlist.name.casefold() == normalized_name:
                return playlist
        return None

    def _resolve_conflict_action(
        self,
        *,
        conflict_action: PlaylistConflictAction,
        existing_playlist_id: str | None,
    ) -> PlaylistConflictAction:
        if (
            conflict_action
            in {
                PlaylistConflictAction.REPLACE_EXISTING,
                PlaylistConflictAction.APPEND_TRACKS,
            }
            and not existing_playlist_id
        ):
            raise ValidationError("existing_playlist_id is required for this action")
        return conflict_action

    def _load_playlist_track_ids(self, playlist_id: str) -> list[str]:
        try:
            return self._execute_with_resilience(
                lambda: self._playlist_repository.get_playlist_track_ids(playlist_id)
            )
        except Exception as error:
            raise PlaylistCreationError(
                "Failed to retrieve existing playlist tracks"
            ) from error

    def _clear_playlist_tracks(
        self, playlist_id: str, track_ids: list[str], batch_size: int
    ) -> None:
        if not track_ids:
            return
        for chunk in self._chunk_track_ids(track_ids, batch_size):
            try:
                self._execute_with_resilience(
                    lambda: self._playlist_repository.remove_tracks(playlist_id, chunk)
                )
            except Exception as error:
                raise PlaylistCreationError(
                    "Failed to clear existing playlist tracks"
                ) from error

    def _upload_tracks(
        self,
        *,
        playlist_id: str,
        track_ids: list[str],
        progress_callback: ProgressCallback | None,
        cancellation_token: CancellationToken,
        batch_size: int,
    ) -> None:
        total_tracks = len(track_ids)
        completed = 0
        for chunk in self._chunk_track_ids(track_ids, batch_size):
            self._check_cancelled(cancellation_token, "adding_tracks")
            try:
                self._execute_with_resilience(
                    lambda: self._playlist_repository.add_tracks(playlist_id, chunk)
                )
            except PlaylistCreationCancelledError:
                raise
            except Exception as error:
                raise PlaylistCreationError(
                    f"Playlist upload failed after {completed}/{total_tracks} tracks"
                ) from error
            completed += len(chunk)
            logger.debug(
                "Added %s tracks to playlist %s (completed=%s/%s)",
                len(chunk),
                playlist_id,
                completed,
                total_tracks,
            )
            self._emit_progress(
                progress_callback,
                "adding_tracks",
                completed,
                total_tracks,
                f"Added {completed}/{total_tracks} tracks",
            )

    def _recover_failed_playlist(self, playlist_id: str | None) -> None:
        if playlist_id is None:
            return
        try:
            self._execute_with_resilience(
                lambda: self._playlist_repository.delete_playlist(playlist_id)
            )
            logger.info(
                "Recovered by deleting partially created playlist %s", playlist_id
            )
        except Exception:
            logger.exception("Failed to recover playlist %s after error", playlist_id)

    def _validate_playlist_plan(self, plan: PlaylistBuildPlan, batch_size: int) -> None:
        if not isinstance(plan, PlaylistBuildPlan):
            raise ValidationError("plan must be a PlaylistBuildPlan")
        if batch_size <= 0:
            raise ValidationError("batch_size must be positive")
        if plan.track_count != len(plan.selected_tracks):
            raise ValidationError("plan.track_count must match selected_tracks length")
        for track in plan.selected_tracks:
            if not track.id.strip():
                raise ValidationError("all tracks in plan must have non-empty ids")

    def _check_cancelled(self, token: CancellationToken, phase: str) -> None:
        if token.is_cancelled:
            logger.warning("Playlist creation cancelled phase=%s", phase)
            raise PlaylistCreationCancelledError(
                f"Playlist creation cancelled during {phase}"
            )

    def _emit_progress(
        self,
        callback: ProgressCallback | None,
        phase: str,
        completed: int,
        total: int,
        message: str,
    ) -> None:
        if callback is None:
            return
        callback(
            PlaylistCreationProgress(
                phase=phase,
                completed=completed,
                total=total,
                message=message,
            )
        )

    def _chunk_track_ids(
        self, track_ids: list[str], batch_size: int
    ) -> Iterator[list[str]]:
        for i in range(0, len(track_ids), batch_size):
            yield track_ids[i : i + batch_size]

    def _ensure_authenticated(self) -> None:
        if self._access_token is None:
            raise AuthenticationError("Provider is not authenticated")

    def _execute_with_resilience(self, call: Callable[[], ResponseT]) -> ResponseT:
        attempt = 0
        while True:
            self._rate_limiter.wait_if_needed()
            try:
                return call()
            except self._retry_on:
                if attempt >= self._max_retries:
                    raise
                delay = self._retry_backoff_seconds * (2**attempt)
                if delay > 0:
                    self._sleeper(delay)
                attempt += 1

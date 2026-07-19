"""Tidal provider implementation."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import logging
from time import monotonic, sleep
from typing import Protocol, TypeVar

from tidal_playlist_builder.exceptions import (
    AuthenticationError,
    PlaylistCreationError,
    ValidationError,
)
from tidal_playlist_builder.model import Album, Artist, PlaylistBuildPlan, Track
from tidal_playlist_builder.repositories import (
    AlbumRepository,
    ArtistRepository,
    PlaylistRepository,
)
from tidal_playlist_builder.services.cache_service import CacheService
from tidal_playlist_builder.services.interfaces import IMusicProvider

ResponseT = TypeVar("ResponseT")
ProgressCallback = Callable[["PlaylistCreationProgress"], None]

logger = logging.getLogger(__name__)


class _TidalApiClient(Protocol):
    """Minimal API client contract used by TidalProvider."""

    def authenticate(self, credentials: dict[str, str]) -> str:
        """Authenticate and return token."""

    def search_artists(self, query: str, limit: int) -> list[dict[str, object]]:
        """Search artists."""

    def get_artist_albums(self, artist_id: str) -> list[dict[str, object]]:
        """Retrieve artist albums."""

    def get_album_tracks(self, album_id: str) -> list[dict[str, object]]:
        """Retrieve album tracks."""

    def create_playlist(self, name: str, description: str) -> str:
        """Create playlist and return id."""

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        """Append tracks to playlist."""

    def delete_playlist(self, playlist_id: str) -> None:
        """Delete playlist by id."""


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
        api_client: _TidalApiClient,
        cache_service: CacheService | None = None,
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

        self._artist_repository = ArtistRepository(
            cache=self._cache,
            search_operation=lambda query, limit: self._execute_with_resilience(
                lambda: self._api_client.search_artists(query, limit)
            ),
        )
        self._album_repository = AlbumRepository(
            cache=self._cache,
            album_operation=lambda artist_id: self._execute_with_resilience(
                lambda: self._api_client.get_artist_albums(artist_id)
            ),
            track_operation=lambda album_id: self._execute_with_resilience(
                lambda: self._api_client.get_album_tracks(album_id)
            ),
        )
        self._playlist_repository = PlaylistRepository(
            create_operation=lambda name, description: self._execute_with_resilience(
                lambda: self._api_client.create_playlist(name, description)
            ),
            add_tracks_operation=lambda playlist_id, track_ids: self._execute_with_resilience(
                lambda: self._api_client.add_tracks_to_playlist(playlist_id, track_ids)
            ),
            delete_operation=lambda playlist_id: self._execute_with_resilience(
                lambda: self._api_client.delete_playlist(playlist_id)
            ),
        )

    def authenticate(self, credentials: dict[str, str]) -> None:
        if not credentials:
            raise ValidationError("credentials cannot be empty")
        token = self._execute_with_resilience(
            lambda: self._api_client.authenticate(credentials)
        )
        if not token.strip():
            raise AuthenticationError("authentication returned empty token")
        self._access_token = token
        self._cache.clear()

    def search_artists(self, query: str, limit: int = 10) -> list[Artist]:
        self._ensure_authenticated()
        if not query.strip():
            raise ValidationError("query cannot be empty")
        if limit <= 0:
            raise ValidationError("limit must be positive")
        return self._artist_repository.search(query, limit)

    def get_artist_albums(self, artist_id: str) -> list[Album]:
        self._ensure_authenticated()
        if not artist_id.strip():
            raise ValidationError("artist_id cannot be empty")
        return self._album_repository.get_artist_albums(artist_id)

    def get_album_tracks(self, album_id: str) -> list[Track]:
        self._ensure_authenticated()
        if not album_id.strip():
            raise ValidationError("album_id cannot be empty")
        return self._album_repository.get_album_tracks(album_id)

    def create_playlist(
        self,
        plan: PlaylistBuildPlan,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        batch_size: int = 100,
    ) -> str:
        """Create a Tidal playlist from a build plan."""
        self._ensure_authenticated()
        self._validate_playlist_plan(plan, batch_size)

        token = cancellation_token or CancellationToken()
        track_ids = [track.id for track in plan.selected_tracks]
        total_tracks = len(track_ids)
        playlist_id: str | None = None

        self._check_cancelled(token, "before_create")
        self._emit_progress(
            progress_callback,
            "creating_playlist",
            0,
            total_tracks,
            "Creating playlist shell",
        )

        playlist_name = f"{plan.artist.name} Playlist"
        description = f"{plan.track_count} tracks from selected albums"

        try:
            playlist_id = self._playlist_repository.create_playlist(
                playlist_name, description
            )
            logger.info("Created playlist shell '%s' (%s)", playlist_name, playlist_id)
            self._emit_progress(
                progress_callback,
                "playlist_created",
                0,
                total_tracks,
                f"Playlist shell created: {playlist_id}",
            )

            completed = 0
            for chunk in self._chunk_track_ids(track_ids, batch_size):
                self._check_cancelled(token, "adding_tracks")
                self._playlist_repository.add_tracks(playlist_id, chunk)
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

            self._cache.invalidate("playlist:")
            self._cache.set(f"playlist:created:{playlist_id}", True, ttl_seconds=300)
            self._emit_progress(
                progress_callback,
                "completed",
                total_tracks,
                total_tracks,
                f"Playlist created: {playlist_id}",
            )
            logger.info("Playlist creation completed (%s)", playlist_id)
            return playlist_id
        except PlaylistCreationCancelledError:
            logger.warning("Playlist creation cancelled")
            self._recover_failed_playlist(playlist_id)
            raise
        except Exception:
            logger.exception("Playlist creation failed")
            self._recover_failed_playlist(playlist_id)
            raise

    def _recover_failed_playlist(self, playlist_id: str | None) -> None:
        if playlist_id is None:
            return
        try:
            self._playlist_repository.delete_playlist(playlist_id)
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

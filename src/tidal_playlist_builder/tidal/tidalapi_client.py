"""Open-source TIDAL transport based on the `tidalapi` package."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
import logging
from typing import Any
import webbrowser

from tidal_playlist_builder.exceptions import AuthenticationError, ProviderError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TidalApiSessionConfig:
    session_file: Path


class TidalApiSdkClient:
    """TidalApiClient implementation that uses OAuth device login via tidalapi."""

    def __init__(self, session_config: TidalApiSessionConfig) -> None:
        self._session_config = session_config
        self._tidalapi = self._load_tidalapi_module()
        self._session = self._tidalapi.Session()
        self._authenticated = False

    def authenticate(self, credentials: dict[str, str]) -> str:
        interactive = (
            str(credentials.get("interactive", "true")).strip().lower() != "false"
        )
        remember_session = (
            str(credentials.get("remember_session", "true")).strip().lower() != "false"
        )

        if self._try_restore_session():
            self._authenticated = True
            return "session-restored"
        if not interactive:
            raise AuthenticationError("No saved TIDAL session found")

        link_login, future = self._session.login_oauth()
        login_url = str(link_login.verification_uri_complete)
        opened = webbrowser.open(login_url)
        if not opened:
            logger.warning(
                "Failed to auto-open browser for OAuth login url=%s", login_url
            )
        logger.info("Waiting for OAuth device authorization")
        try:
            success = bool(future.result(timeout=float(link_login.expires_in) + 10))
        except TimeoutError as error:
            raise AuthenticationError(
                "Timed out waiting for TIDAL OAuth approval"
            ) from error
        except Exception as error:  # pragma: no cover - tidalapi backend exceptions
            raise AuthenticationError(
                "TIDAL OAuth login failed while waiting for approval"
            ) from error
        if not success or not self._session.check_login():
            raise AuthenticationError("TIDAL OAuth login did not complete successfully")
        if remember_session:
            self._session_config.session_file.parent.mkdir(parents=True, exist_ok=True)
            self._session.save_session_to_file(self._session_config.session_file)
        self._authenticated = True
        logger.info("TIDAL OAuth login succeeded")
        return "oauth"

    def clear_authentication(self) -> None:
        self._authenticated = False
        self._session = self._tidalapi.Session()

    def search_artists(self, query: str, limit: int) -> list[dict[str, object]]:
        self._ensure_authenticated()
        results = self._session.search(
            query, models=[self._tidalapi.artist.Artist], limit=limit
        )
        artists = results.get("artists", []) if isinstance(results, dict) else []
        payload: list[dict[str, object]] = []
        for artist in artists:
            payload.append(
                {
                    "id": str(getattr(artist, "id", "")).strip(),
                    "name": str(getattr(artist, "name", "")).strip(),
                }
            )
        return payload

    def get_artist_albums(self, artist_id: str) -> list[dict[str, object]]:
        self._ensure_authenticated()
        artist = self._session.artist(artist_id)
        albums = artist.get_albums(limit=300)
        payload: list[dict[str, object]] = []
        for album in albums:
            album_artist = getattr(album, "artist", None)
            payload.append(
                {
                    "id": str(getattr(album, "id", "")).strip(),
                    "title": str(getattr(album, "name", "")).strip(),
                    "release_year": int(getattr(album, "year", 0) or 0),
                    "album_type": str(getattr(album, "type", "album")).strip().lower(),
                    "edition": "original",
                    "quality": "lossless",
                    "is_explicit": bool(getattr(album, "explicit", False)),
                    "artist": {
                        "id": str(getattr(album_artist, "id", "")).strip(),
                        "name": str(getattr(album_artist, "name", "")).strip(),
                    },
                }
            )
        return payload

    def get_album_tracks(self, album_id: str) -> list[dict[str, object]]:
        self._ensure_authenticated()
        album = self._session.album(album_id)
        tracks = album.tracks(limit=500)
        payload: list[dict[str, object]] = []
        for track in tracks:
            payload.append(
                {
                    "id": str(getattr(track, "id", "")).strip(),
                    "title": str(getattr(track, "title", "")).strip(),
                    "duration_seconds": int(getattr(track, "duration", 0) or 0),
                }
            )
        return payload

    def create_playlist(self, name: str, description: str) -> str:
        self._ensure_authenticated()
        user = self._session.user
        if user is None:
            raise ProviderError("No authenticated TIDAL user available")
        playlist = user.create_playlist(name, description)
        return str(getattr(playlist, "id", "")).strip()

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        self._ensure_authenticated()
        playlist = self._session.playlist(playlist_id)
        add_operation = getattr(playlist, "add", None)
        if not callable(add_operation):
            raise ProviderError("TIDAL playlist object does not support adding tracks")
        add_operation([str(track_id) for track_id in track_ids], allow_duplicates=False)

    def delete_playlist(self, playlist_id: str) -> None:
        self._ensure_authenticated()
        playlist = self._session.playlist(playlist_id)
        delete_operation = getattr(playlist, "delete", None)
        if not callable(delete_operation):
            raise ProviderError("TIDAL playlist object does not support deletion")
        delete_operation()

    def _try_restore_session(self) -> bool:
        session_file = self._session_config.session_file
        if not session_file.exists():
            return False
        try:
            if (
                self._session.load_session_from_file(session_file)
                and self._session.check_login()
            ):
                return True
        except Exception:  # pragma: no cover - backend/session corruption handling
            logger.warning("Failed to restore persisted TIDAL session", exc_info=True)
        return False

    def _ensure_authenticated(self) -> None:
        if not self._authenticated and not self._session.check_login():
            raise AuthenticationError("Provider is not authenticated")
        self._authenticated = True

    def _load_tidalapi_module(self) -> Any:
        try:
            return import_module("tidalapi")
        except ModuleNotFoundError as error:
            raise ProviderError(
                "tidalapi dependency is required for TIDAL OAuth support"
            ) from error

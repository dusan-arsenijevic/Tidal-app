"""Playlist repository."""

from collections.abc import Callable
import logging

from tidal_playlist_builder.model import PlaylistSummary

logger = logging.getLogger(__name__)


class PlaylistRepository:
    """Delegates playlist persistence operations to provider client calls."""

    def __init__(
        self,
        create_operation: Callable[[str, str], str],
        add_tracks_operation: Callable[[str, list[str]], None],
        list_playlists_operation: Callable[[], list[dict[str, object]]],
        playlist_track_ids_operation: Callable[[str], list[str]],
        remove_tracks_operation: Callable[[str, list[str]], None],
        delete_operation: Callable[[str], None],
    ) -> None:
        self._create_operation = create_operation
        self._add_tracks_operation = add_tracks_operation
        self._list_playlists_operation = list_playlists_operation
        self._playlist_track_ids_operation = playlist_track_ids_operation
        self._remove_tracks_operation = remove_tracks_operation
        self._delete_operation = delete_operation

    def create_playlist(self, name: str, description: str) -> str:
        logger.debug("Playlist repository create playlist requested")
        return self._create_operation(name, description)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        logger.debug("Playlist repository add tracks count=%s", len(track_ids))
        self._add_tracks_operation(playlist_id, track_ids)

    def list_playlists(self) -> list[PlaylistSummary]:
        logger.debug("Playlist repository list playlists requested")
        payload = self._list_playlists_operation()
        summaries: list[PlaylistSummary] = []
        for item in payload:
            playlist_id = str(item.get("id", "")).strip()
            playlist_name = str(item.get("name", "")).strip()
            if not playlist_id or not playlist_name:
                continue
            summaries.append(PlaylistSummary(id=playlist_id, name=playlist_name))
        return summaries

    def get_playlist_track_ids(self, playlist_id: str) -> list[str]:
        logger.debug("Playlist repository track listing requested id=%s", playlist_id)
        return self._playlist_track_ids_operation(playlist_id)

    def remove_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        logger.debug("Playlist repository remove tracks count=%s", len(track_ids))
        self._remove_tracks_operation(playlist_id, track_ids)

    def delete_playlist(self, playlist_id: str) -> None:
        logger.debug("Playlist repository delete playlist requested")
        self._delete_operation(playlist_id)

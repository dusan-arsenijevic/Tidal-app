"""Playlist repository."""

from collections.abc import Callable


class PlaylistRepository:
    """Delegates playlist persistence operations to provider client calls."""

    def __init__(
        self,
        create_operation: Callable[[str, str], str],
        add_tracks_operation: Callable[[str, list[str]], None],
        delete_operation: Callable[[str], None],
    ) -> None:
        self._create_operation = create_operation
        self._add_tracks_operation = add_tracks_operation
        self._delete_operation = delete_operation

    def create_playlist(self, name: str, description: str) -> str:
        return self._create_operation(name, description)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self._add_tracks_operation(playlist_id, track_ids)

    def delete_playlist(self, playlist_id: str) -> None:
        self._delete_operation(playlist_id)

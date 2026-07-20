"""Public API client protocol for Tidal transport implementations."""

from typing import Protocol


class TidalApiClient(Protocol):
    """Transport contract consumed by TidalProvider."""

    def authenticate(self, credentials: dict[str, str]) -> str:
        """Authenticate and return token."""

    def clear_authentication(self) -> None:
        """Clear auth tokens from the transport."""

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

    def list_playlists(self) -> list[dict[str, object]]:
        """List authenticated user's playlists."""

    def get_playlist_track_ids(self, playlist_id: str) -> list[str]:
        """Return track ids currently present in a playlist."""

    def remove_tracks_from_playlist(
        self, playlist_id: str, track_ids: list[str]
    ) -> None:
        """Remove specific track ids from a playlist."""

    def delete_playlist(self, playlist_id: str) -> None:
        """Delete playlist by id."""

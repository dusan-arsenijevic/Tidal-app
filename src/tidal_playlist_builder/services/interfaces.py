"""Service interfaces."""

from typing import Protocol

from tidal_playlist_builder.model import (
    Album,
    Artist,
    PlaylistBuildPlan,
    PlaylistConflictAction,
    PlaylistSummary,
    Track,
)


class IMusicProvider(Protocol):
    """Music provider contract used by the application."""

    def authenticate(self, credentials: dict[str, str]) -> None:
        """Authenticate and prepare provider for subsequent calls."""

    def search_artists(self, query: str, limit: int = 10) -> list[Artist]:
        """Search artists."""

    def get_artist_albums(self, artist_id: str) -> list[Album]:
        """Retrieve albums for an artist."""

    def get_album_tracks(self, album_id: str) -> list[Track]:
        """Retrieve tracks for an album."""

    def find_playlist_by_name(self, playlist_name: str) -> PlaylistSummary | None:
        """Return an existing playlist by case-insensitive name match."""

    def create_playlist(
        self,
        plan: PlaylistBuildPlan,
        *,
        conflict_action: PlaylistConflictAction = PlaylistConflictAction.CREATE_ANOTHER,
        existing_playlist_id: str | None = None,
    ) -> str:
        """Create playlist from a build plan and return playlist id."""

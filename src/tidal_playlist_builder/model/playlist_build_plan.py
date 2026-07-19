"""Playlist build plan model."""

from dataclasses import dataclass

from tidal_playlist_builder.exceptions import ValidationError

from .album import Album
from .artist import Artist
from .track import Track


@dataclass(frozen=True, slots=True)
class PlaylistBuildPlan:
    """Plan created from selected albums before playlist creation."""

    artist: Artist
    selected_albums: tuple[Album, ...]
    selected_tracks: tuple[Track, ...]
    duplicates_skipped: int
    duration_seconds: int
    track_count: int

    def __post_init__(self) -> None:
        if not self.selected_albums:
            raise ValidationError("selected_albums cannot be empty")
        if self.duplicates_skipped < 0:
            raise ValidationError("duplicates_skipped cannot be negative")
        if self.duration_seconds < 0:
            raise ValidationError("duration_seconds cannot be negative")
        if self.track_count < 0:
            raise ValidationError("track_count cannot be negative")

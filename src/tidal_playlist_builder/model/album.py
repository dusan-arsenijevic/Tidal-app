"""Album model."""

from dataclasses import dataclass

from .artist import Artist
from .enums import AlbumEdition, AlbumType, AudioQuality
from .track import Track


@dataclass(frozen=True, slots=True)
class Album:
    """Album aggregate root used by filtering."""

    id: str
    title: str
    artist: Artist
    release_year: int
    album_type: AlbumType
    edition: AlbumEdition
    quality: AudioQuality
    is_explicit: bool
    tracks: tuple[Track, ...] = ()

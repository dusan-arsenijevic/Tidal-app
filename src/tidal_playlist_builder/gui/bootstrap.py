"""GUI bootstrap helpers."""

from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    Track,
)

from .models import AlbumTableModel


class MockAlbumFactory:
    """Factory for local/mock album data used at app bootstrap."""

    def create_albums(self) -> list[Album]:
        artist = Artist(id="artist:1", name="Mock Artist")
        return [
            Album(
                id="album:1",
                title="Mock Album A",
                artist=artist,
                release_year=1999,
                album_type=AlbumType.ALBUM,
                edition=AlbumEdition.ORIGINAL,
                quality=AudioQuality.LOSSLESS,
                is_explicit=False,
                tracks=(
                    Track(id="track:1", title="Song A", duration_seconds=210),
                    Track(id="track:2", title="Song B", duration_seconds=195),
                ),
            ),
            Album(
                id="album:2",
                title="Mock Album B",
                artist=artist,
                release_year=2005,
                album_type=AlbumType.EP,
                edition=AlbumEdition.DELUXE,
                quality=AudioQuality.HI_RES,
                is_explicit=True,
                tracks=(Track(id="track:3", title="Song C", duration_seconds=180),),
            ),
        ]


class AlbumModelFactory:
    """Factory for constructing album table models."""

    def __init__(self, album_factory: MockAlbumFactory | None = None) -> None:
        self._album_factory = album_factory or MockAlbumFactory()

    def create_album_table_model(self) -> AlbumTableModel:
        return AlbumTableModel(self._album_factory.create_albums())

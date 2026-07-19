"""Tests for GUI bootstrap factories."""

from tidal_playlist_builder.gui import AlbumModelFactory, MockAlbumFactory
from tidal_playlist_builder.gui.models import AlbumTableModel


def test_mock_album_factory_creates_albums() -> None:
    albums = MockAlbumFactory().create_albums()
    assert len(albums) == 2
    assert albums[0].title == "Mock Album A"


def test_album_model_factory_creates_table_model() -> None:
    model = AlbumModelFactory().create_album_table_model()
    assert isinstance(model, AlbumTableModel)
    assert model.rowCount() == 2

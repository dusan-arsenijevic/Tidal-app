"""Tests for AlbumTableModel."""

from PySide6.QtCore import Qt

from tidal_playlist_builder.gui.models import AlbumColumn, AlbumTableModel
from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    DuplicateGroup,
    Track,
)


def _artist() -> Artist:
    return Artist(id="artist-1", name="Radiohead")


def _album(
    album_id: str,
    title: str,
    year: int,
    edition: AlbumEdition,
    quality: AudioQuality,
    tracks: tuple[Track, ...],
) -> Album:
    return Album(
        id=album_id,
        title=title,
        artist=_artist(),
        release_year=year,
        album_type=AlbumType.ALBUM,
        edition=edition,
        quality=quality,
        is_explicit=False,
        tracks=tracks,
    )


def _albums() -> list[Album]:
    return [
        _album(
            "alb-2",
            "In Rainbows",
            2007,
            AlbumEdition.ORIGINAL,
            AudioQuality.LOSSLESS,
            (
                Track(id="t1", title="15 Step", duration_seconds=237),
                Track(id="t2", title="Bodysnatchers", duration_seconds=242),
            ),
        ),
        _album(
            "alb-1",
            "OK Computer",
            1997,
            AlbumEdition.REMASTER,
            AudioQuality.HI_RES,
            (
                Track(id="t3", title="Airbag", duration_seconds=284),
                Track(id="t4", title="Paranoid Android", duration_seconds=387),
                Track(
                    id="t5", title="Subterranean Homesick Alien", duration_seconds=267
                ),
            ),
        ),
        _album(
            "alb-3",
            "Kid A",
            2000,
            AlbumEdition.DELUXE,
            AudioQuality.LOSSY,
            (
                Track(
                    id="t6", title="Everything in Its Right Place", duration_seconds=251
                ),
            ),
        ),
    ]


def test_column_enum_is_stable() -> None:
    assert AlbumColumn.CHECKBOX == 0
    assert AlbumColumn.DUPLICATE_STATUS == 8


def test_row_and_column_count(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    assert model.rowCount() == 3
    assert model.columnCount() == 9


def test_header_labels(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    assert model.headerData(AlbumColumn.YEAR, Qt.Orientation.Horizontal) == "Year"
    assert model.headerData(AlbumColumn.TITLE, Qt.Orientation.Horizontal) == "Title"
    assert (
        model.headerData(AlbumColumn.DUPLICATE_STATUS, Qt.Orientation.Horizontal)
        == "Duplicate Status"
    )


def test_display_role_values(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    row = 0
    assert (
        model.data(model.index(row, AlbumColumn.YEAR), Qt.ItemDataRole.DisplayRole)
        == 2007
    )
    assert (
        model.data(model.index(row, AlbumColumn.TITLE), Qt.ItemDataRole.DisplayRole)
        == "In Rainbows"
    )
    assert (
        model.data(model.index(row, AlbumColumn.TYPE), Qt.ItemDataRole.DisplayRole)
        == "Album"
    )
    assert (
        model.data(model.index(row, AlbumColumn.EDITION), Qt.ItemDataRole.DisplayRole)
        == "Original"
    )
    assert (
        model.data(model.index(row, AlbumColumn.TRACKS), Qt.ItemDataRole.DisplayRole)
        == 2
    )
    assert (
        model.data(model.index(row, AlbumColumn.DURATION), Qt.ItemDataRole.DisplayRole)
        == "7:59"
    )
    assert (
        model.data(model.index(row, AlbumColumn.QUALITY), Qt.ItemDataRole.DisplayRole)
        == "Lossless"
    )
    assert (
        model.data(
            model.index(row, AlbumColumn.DUPLICATE_STATUS),
            Qt.ItemDataRole.DisplayRole,
        )
        == "Unique"
    )


def test_checkbox_flags_and_edit(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    index = model.index(1, AlbumColumn.CHECKBOX)
    flags = model.flags(index)

    assert flags & Qt.ItemFlag.ItemIsUserCheckable
    assert flags & Qt.ItemFlag.ItemIsEditable

    assert model.data(index, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert model.setData(index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert model.data(index, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert model.checked_album_ids() == ["alb-1"]


def test_set_row_checked_updates_state(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    assert model.set_row_checked(0, True)
    assert model.set_row_checked(2, True)
    assert model.checked_album_ids() == ["alb-2", "alb-3"]


def test_sort_by_year_ascending_and_descending(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    model.sort(AlbumColumn.YEAR, Qt.SortOrder.AscendingOrder)
    assert (
        model.data(model.index(0, AlbumColumn.TITLE), Qt.ItemDataRole.DisplayRole)
        == "OK Computer"
    )
    model.sort(AlbumColumn.YEAR, Qt.SortOrder.DescendingOrder)
    assert (
        model.data(model.index(0, AlbumColumn.TITLE), Qt.ItemDataRole.DisplayRole)
        == "In Rainbows"
    )


def test_sort_by_checkbox(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    model.set_row_checked(2, True)
    model.sort(AlbumColumn.CHECKBOX, Qt.SortOrder.DescendingOrder)
    assert (
        model.data(model.index(0, AlbumColumn.TITLE), Qt.ItemDataRole.DisplayRole)
        == "Kid A"
    )


def test_set_duplicate_groups_updates_column(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    groups = [
        DuplicateGroup(
            canonical_album_id="alb-1", variant_album_ids=frozenset({"alb-2"})
        )
    ]
    model.set_duplicate_groups(groups)

    titles_to_status = {
        model.data(
            model.index(row, AlbumColumn.TITLE), Qt.ItemDataRole.DisplayRole
        ): model.data(
            model.index(row, AlbumColumn.DUPLICATE_STATUS),
            Qt.ItemDataRole.DisplayRole,
        )
        for row in range(model.rowCount())
    }
    assert titles_to_status["OK Computer"] == "Canonical"
    assert titles_to_status["In Rainbows"] == "Variant"
    assert titles_to_status["Kid A"] == "Unique"


def test_update_album_updates_row_data(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    new_album = _album(
        "alb-1",
        "OKNOTOK",
        2017,
        AlbumEdition.REMASTER,
        AudioQuality.HI_RES,
        (Track(id="t7", title="Man of War", duration_seconds=257),),
    )

    assert model.update_album(1, new_album)
    assert (
        model.data(model.index(1, AlbumColumn.TITLE), Qt.ItemDataRole.DisplayRole)
        == "OKNOTOK"
    )
    assert (
        model.data(model.index(1, AlbumColumn.YEAR), Qt.ItemDataRole.DisplayRole)
        == 2017
    )
    assert (
        model.data(model.index(1, AlbumColumn.TRACKS), Qt.ItemDataRole.DisplayRole) == 1
    )


def test_user_role_returns_album_instance(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    album = model.data(model.index(0, AlbumColumn.TITLE), Qt.ItemDataRole.UserRole)
    assert isinstance(album, Album)
    assert album.id == "alb-2"


def test_invalid_indices_are_handled(qtbot: object) -> None:
    model = AlbumTableModel(_albums())
    invalid_index = model.index(-1, -1)
    assert model.data(invalid_index, Qt.ItemDataRole.DisplayRole) is None
    assert not model.setData(invalid_index, True, Qt.ItemDataRole.EditRole)
    assert not model.update_album(99, _albums()[0])

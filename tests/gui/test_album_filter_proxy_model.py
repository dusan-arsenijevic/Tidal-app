"""Tests for AlbumFilterProxyModel."""

import pytest
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

from tidal_playlist_builder.filtering import FilterEngine
from tidal_playlist_builder.gui.models import (
    AlbumColumn,
    AlbumFilterProxyModel,
    AlbumTableModel,
)
from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    DuplicateGroup,
    DuplicateStatus,
    FilterCriteria,
    Track,
)


def _artist(name: str = "Massive Attack", artist_id: str = "artist-1") -> Artist:
    return Artist(id=artist_id, name=name)


def _album(
    album_id: str,
    title: str,
    year: int,
    album_type: AlbumType,
    edition: AlbumEdition,
    quality: AudioQuality,
    explicit: bool,
    track_durations: tuple[int, ...],
    artist: Artist | None = None,
) -> Album:
    used_artist = artist or _artist()
    tracks = tuple(
        Track(
            id=f"{album_id}-t{index}",
            title=f"Track {index}",
            duration_seconds=seconds,
        )
        for index, seconds in enumerate(track_durations, start=1)
    )
    return Album(
        id=album_id,
        title=title,
        artist=used_artist,
        release_year=year,
        album_type=album_type,
        edition=edition,
        quality=quality,
        is_explicit=explicit,
        tracks=tracks,
    )


def _albums() -> list[Album]:
    artist = _artist()
    return [
        _album(
            "a1",
            "Blue Lines",
            1991,
            AlbumType.ALBUM,
            AlbumEdition.ORIGINAL,
            AudioQuality.LOSSLESS,
            False,
            (180, 220),
            artist,
        ),
        _album(
            "a2",
            "Blue Lines (Deluxe)",
            2012,
            AlbumType.ALBUM,
            AlbumEdition.DELUXE,
            AudioQuality.HI_RES,
            False,
            (240, 240, 240),
            artist,
        ),
        _album(
            "a3",
            "Mezzanine",
            1998,
            AlbumType.ALBUM,
            AlbumEdition.REMASTER,
            AudioQuality.LOSSY,
            True,
            (200,),
            artist,
        ),
        _album(
            "a4",
            "Protection EP",
            1995,
            AlbumType.EP,
            AlbumEdition.ORIGINAL,
            AudioQuality.LOSSLESS,
            False,
            (300,),
            artist,
        ),
    ]


def _proxy_with_source() -> tuple[AlbumTableModel, AlbumFilterProxyModel]:
    source = AlbumTableModel(_albums())
    proxy = AlbumFilterProxyModel()
    proxy.setSourceModel(source)
    return source, proxy


def _proxy_titles(proxy: AlbumFilterProxyModel) -> list[str]:
    return [
        str(
            proxy.data(proxy.index(row, AlbumColumn.TITLE), Qt.ItemDataRole.DisplayRole)
        )
        for row in range(proxy.rowCount())
    ]


def test_filters_release_year_album_type_edition_quality_explicit() -> None:
    _, proxy = _proxy_with_source()
    criteria = FilterCriteria(
        release_year_min=2000,
        release_year_max=2020,
        album_types=frozenset({AlbumType.ALBUM}),
        editions=frozenset({AlbumEdition.DELUXE}),
        qualities=frozenset({AudioQuality.HI_RES}),
        explicit=False,
    )
    proxy.set_filter_criteria(criteria)
    assert _proxy_titles(proxy) == ["Blue Lines (Deluxe)"]


def test_filters_by_duplicate_status_and_text_search() -> None:
    _, proxy = _proxy_with_source()
    proxy.set_duplicate_groups(
        [DuplicateGroup(canonical_album_id="a1", variant_album_ids=frozenset({"a2"}))]
    )
    proxy.set_filter_criteria(
        FilterCriteria(
            duplicate_status=DuplicateStatus.VARIANTS_ONLY,
            search_text="deluxe",
        )
    )
    assert _proxy_titles(proxy) == ["Blue Lines (Deluxe)"]


def test_sorting_by_every_visible_column_does_not_fail() -> None:
    _, proxy = _proxy_with_source()
    for column in AlbumColumn:
        proxy.sort(column, Qt.SortOrder.AscendingOrder)
        assert proxy.rowCount() == 4
        proxy.sort(column, Qt.SortOrder.DescendingOrder)
        assert proxy.rowCount() == 4


def test_sorting_examples_match_expected_rows() -> None:
    _, proxy = _proxy_with_source()
    proxy.sort(AlbumColumn.YEAR, Qt.SortOrder.AscendingOrder)
    assert _proxy_titles(proxy)[0] == "Blue Lines"
    proxy.sort(AlbumColumn.TITLE, Qt.SortOrder.AscendingOrder)
    assert _proxy_titles(proxy)[0] == "Blue Lines"
    proxy.sort(AlbumColumn.TRACKS, Qt.SortOrder.DescendingOrder)
    assert _proxy_titles(proxy)[0] == "Blue Lines (Deluxe)"


def test_changing_filters_updates_live() -> None:
    _, proxy = _proxy_with_source()
    proxy.set_filter_criteria(FilterCriteria(search_text="blue"))
    assert proxy.rowCount() == 2
    proxy.set_filter_criteria(FilterCriteria(search_text="mezz"))
    assert proxy.rowCount() == 1
    proxy.set_filter_criteria(FilterCriteria(search_text="protection"))
    assert proxy.rowCount() == 1


def test_clearing_filters_restores_all_rows() -> None:
    _, proxy = _proxy_with_source()
    proxy.set_filter_criteria(FilterCriteria(search_text="blue"))
    assert proxy.rowCount() == 2
    proxy.clear_filter_criteria()
    assert proxy.rowCount() == 4


def test_preserves_checked_albums_when_filter_changes() -> None:
    source, proxy = _proxy_with_source()
    source.set_row_checked(2, True)
    assert source.checked_album_ids() == ["a3"]

    proxy.set_filter_criteria(FilterCriteria(search_text="blue"))
    assert proxy.rowCount() == 2
    assert source.checked_album_ids() == ["a3"]

    proxy.clear_filter_criteria()
    assert proxy.rowCount() == 4
    assert source.checked_album_ids() == ["a3"]


def test_invalid_filter_criteria_type_raises() -> None:
    _, proxy = _proxy_with_source()
    with pytest.raises(TypeError, match="FilterCriteria"):
        proxy.set_filter_criteria("invalid")  # type: ignore[arg-type]


def test_invalid_source_model_is_handled() -> None:
    class DummyModel(QAbstractTableModel):
        def rowCount(  # noqa: N802
            self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
        ) -> int:
            return 1

        def columnCount(  # noqa: N802
            self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
        ) -> int:
            return 1

    dummy = DummyModel()
    proxy = AlbumFilterProxyModel()
    proxy.setSourceModel(dummy)
    proxy.set_filter_criteria(FilterCriteria(search_text="x"))
    assert proxy.rowCount() == 0


def test_handles_large_dataset() -> None:
    artist = _artist()
    albums = [
        _album(
            f"album-{index}",
            f"Album {index}",
            1980 + (index % 40),
            AlbumType.ALBUM if index % 2 == 0 else AlbumType.EP,
            AlbumEdition.ORIGINAL if index % 3 else AlbumEdition.DELUXE,
            AudioQuality.HI_RES if index % 5 == 0 else AudioQuality.LOSSLESS,
            explicit=index % 7 == 0,
            track_durations=(180, 200),
            artist=artist,
        )
        for index in range(1200)
    ]
    source = AlbumTableModel(albums)
    proxy = AlbumFilterProxyModel()
    proxy.setSourceModel(source)
    proxy.set_filter_criteria(
        FilterCriteria(
            release_year_min=2000,
            album_types=frozenset({AlbumType.ALBUM}),
            explicit=False,
        )
    )
    assert proxy.rowCount() > 0
    assert proxy.rowCount() < 1200


class _RecordingFilterEngine(FilterEngine):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def filter_albums(  # type: ignore[override]
        self,
        albums: list[Album],
        criteria: FilterCriteria,
        duplicate_groups: list[DuplicateGroup] | None = None,
    ) -> list[Album]:
        self.call_count += 1
        return super().filter_albums(albums, criteria, duplicate_groups)


def test_recomputes_on_source_model_signals() -> None:
    source = AlbumTableModel(_albums())
    engine = _RecordingFilterEngine()
    proxy = AlbumFilterProxyModel(filter_engine=engine)
    proxy.setSourceModel(source)
    baseline = engine.call_count

    source.modelReset.emit()
    source.rowsInserted.emit(QModelIndex(), 0, 0)
    source.rowsRemoved.emit(QModelIndex(), 0, 0)
    source.layoutChanged.emit()
    source.dataChanged.emit(
        source.index(0, AlbumColumn.TITLE),
        source.index(0, AlbumColumn.TITLE),
        [Qt.ItemDataRole.DisplayRole],
    )

    assert engine.call_count >= baseline + 5


def test_filter_updates_after_source_data_change() -> None:
    source, proxy = _proxy_with_source()
    proxy.set_filter_criteria(FilterCriteria(search_text="mezzanine"))
    assert _proxy_titles(proxy) == ["Mezzanine"]

    updated = _album(
        "a3",
        "Not Matching",
        1998,
        AlbumType.ALBUM,
        AlbumEdition.REMASTER,
        AudioQuality.LOSSY,
        True,
        (200,),
        _artist(),
    )
    assert source.update_album(2, updated)

    assert proxy.rowCount() == 0

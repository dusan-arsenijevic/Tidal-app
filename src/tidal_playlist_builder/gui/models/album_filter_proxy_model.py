"""Album filter proxy model for Qt Model/View."""

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)

from tidal_playlist_builder.filtering import FilterEngine
from tidal_playlist_builder.model import Album, DuplicateGroup, FilterCriteria

from .album_table_model import AlbumColumn, AlbumTableModel


class AlbumFilterProxyModel(QSortFilterProxyModel):
    """Proxy model delegating filtering decisions to FilterEngine."""

    def __init__(
        self,
        filter_engine: FilterEngine | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._filter_engine = filter_engine or FilterEngine()
        self._criteria = FilterCriteria()
        self._duplicate_groups: list[DuplicateGroup] = []
        self._accepted_album_ids: frozenset[str] = frozenset()
        self.setDynamicSortFilter(True)

    def setSourceModel(self, source_model: QAbstractItemModel) -> None:  # noqa: N802
        previous_source = self.sourceModel()
        if previous_source is not None:
            self._disconnect_source_model_signals(previous_source)

        super().setSourceModel(source_model)
        self._connect_source_model_signals(source_model)
        self._recompute_filter_cache()
        self._refresh_filter()

    def set_filter_criteria(self, criteria: FilterCriteria) -> None:
        """Set filter criteria and update rows immediately."""
        if not isinstance(criteria, FilterCriteria):
            raise TypeError("criteria must be a FilterCriteria")
        self._criteria = criteria
        self._recompute_filter_cache()
        self._refresh_filter()

    def clear_filter_criteria(self) -> None:
        """Clear criteria to defaults and show all rows."""
        self.set_filter_criteria(FilterCriteria())

    def filter_criteria(self) -> FilterCriteria:
        """Return active filter criteria."""
        return self._criteria

    def set_duplicate_groups(self, groups: Iterable[DuplicateGroup]) -> None:
        """Set duplicate groups used by duplicate status filtering."""
        self._duplicate_groups = list(groups)
        self._recompute_filter_cache()
        self._refresh_filter()

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:  # noqa: N802
        album = self._album_from_source_row(source_row, source_parent)
        if album is None:
            return False
        return album.id in self._accepted_album_ids

    def lessThan(
        self,
        left: QModelIndex | QPersistentModelIndex,
        right: QModelIndex | QPersistentModelIndex,
    ) -> bool:  # noqa: N802
        source = self.sourceModel()
        if source is None:
            return False

        left_sort = source.data(left, Qt.ItemDataRole.InitialSortOrderRole)
        right_sort = source.data(right, Qt.ItemDataRole.InitialSortOrderRole)

        if left_sort is None and right_sort is None:
            return False
        if left_sort is None:
            return True
        if right_sort is None:
            return False
        return left_sort < right_sort

    def _connect_source_model_signals(self, source_model: QAbstractItemModel) -> None:
        source_model.modelReset.connect(self._on_source_model_changed)
        source_model.rowsInserted.connect(self._on_source_model_changed)
        source_model.rowsRemoved.connect(self._on_source_model_changed)
        source_model.dataChanged.connect(self._on_source_model_changed)
        source_model.layoutChanged.connect(self._on_source_model_changed)

    def _disconnect_source_model_signals(
        self, source_model: QAbstractItemModel
    ) -> None:
        for signal in (
            source_model.modelReset,
            source_model.rowsInserted,
            source_model.rowsRemoved,
            source_model.dataChanged,
            source_model.layoutChanged,
        ):
            try:
                signal.disconnect(self._on_source_model_changed)
            except (TypeError, RuntimeError):
                pass

    def _on_source_model_changed(self, *_args: Any) -> None:
        self._recompute_filter_cache()
        self._refresh_filter()

    def _recompute_filter_cache(self) -> None:
        albums = self._source_albums()
        filtered = self._filter_engine.filter_albums(
            albums,
            self._criteria,
            self._duplicate_groups,
        )
        self._accepted_album_ids = frozenset(album.id for album in filtered)

    def _refresh_filter(self) -> None:
        self.beginFilterChange()
        self.endFilterChange()

    def _source_albums(self) -> list[Album]:
        source = self.sourceModel()
        if source is None:
            return []
        if not isinstance(source, AlbumTableModel):
            return []

        albums: list[Album] = []
        for row in range(source.rowCount()):
            index = source.index(row, AlbumColumn.TITLE)
            album_data = source.data(index, Qt.ItemDataRole.UserRole)
            if isinstance(album_data, Album):
                albums.append(album_data)
        return albums

    def _album_from_source_row(
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> Album | None:
        source = self.sourceModel()
        if source is None:
            return None
        if not isinstance(source, AlbumTableModel):
            return None

        index = source.index(source_row, AlbumColumn.TITLE, source_parent)
        album_data = source.data(index, Qt.ItemDataRole.UserRole)
        if isinstance(album_data, Album):
            return album_data
        return None

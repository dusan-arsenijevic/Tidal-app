"""Album table model for Qt Model/View."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from tidal_playlist_builder.model import Album, DuplicateGroup


class AlbumColumn(IntEnum):
    """Columns used by AlbumTableModel."""

    CHECKBOX = 0
    YEAR = 1
    TITLE = 2
    TYPE = 3
    EDITION = 4
    TRACKS = 5
    DURATION = 6
    QUALITY = 7
    DUPLICATE_STATUS = 8


@dataclass(slots=True)
class _AlbumRow:
    album: Album
    checked: bool
    duplicate_status: str


class AlbumTableModel(QAbstractTableModel):
    """Table model for album browsing/selection."""

    _HEADERS = {
        AlbumColumn.CHECKBOX: "",
        AlbumColumn.YEAR: "Year",
        AlbumColumn.TITLE: "Title",
        AlbumColumn.TYPE: "Type",
        AlbumColumn.EDITION: "Edition",
        AlbumColumn.TRACKS: "Tracks",
        AlbumColumn.DURATION: "Duration",
        AlbumColumn.QUALITY: "Quality",
        AlbumColumn.DUPLICATE_STATUS: "Duplicate Status",
    }

    def __init__(
        self, albums: list[Album] | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._rows: list[_AlbumRow] = []
        self._vertical_row_numbers: dict[int, str] = {}
        self.set_albums(albums or [])

    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        if parent.isValid():
            return 0
        return len(AlbumColumn)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            try:
                return self._HEADERS[AlbumColumn(section)]
            except (ValueError, KeyError):
                return None
        return self._vertical_row_numbers.get(section, str(section + 1))

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == AlbumColumn.CHECKBOX:
            return base | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable
        return base

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        if not index.isValid() or index.row() >= len(self._rows):
            return None

        row = self._rows[index.row()]
        column = AlbumColumn(index.column())

        if role == Qt.ItemDataRole.UserRole:
            return row.album

        if column == AlbumColumn.CHECKBOX and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if row.checked else Qt.CheckState.Unchecked

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in {
                AlbumColumn.CHECKBOX,
                AlbumColumn.YEAR,
                AlbumColumn.TRACKS,
                AlbumColumn.DURATION,
            }:
                return int(Qt.AlignmentFlag.AlignCenter)

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(row, column)

        if role == Qt.ItemDataRole.EditRole:
            if column == AlbumColumn.CHECKBOX:
                return row.checked
            return self._display_value(row, column)

        if role == Qt.ItemDataRole.InitialSortOrderRole:
            return self._sort_value(row, column)

        return None

    def setData(  # noqa: N802
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid() or index.row() >= len(self._rows):
            return False
        if index.column() != AlbumColumn.CHECKBOX:
            return False

        if role not in {Qt.ItemDataRole.EditRole, Qt.ItemDataRole.CheckStateRole}:
            return False

        checked = self._coerce_checked(value)
        if checked is None:
            return False

        row = self._rows[index.row()]
        if row.checked == checked:
            return True

        row.checked = checked
        self.dataChanged.emit(
            index,
            index,
            [Qt.ItemDataRole.CheckStateRole, Qt.ItemDataRole.EditRole],
        )
        return True

    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        """Sort rows by column."""
        try:
            album_column = AlbumColumn(column)
        except ValueError:
            return

        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self._rows.sort(
            key=lambda row: self._sort_value(row, album_column), reverse=reverse
        )
        self.layoutChanged.emit()

    def set_albums(self, albums: list[Album]) -> None:
        """Replace all rows with new album list."""
        self.beginResetModel()
        self._rows = [
            _AlbumRow(album=album, checked=False, duplicate_status="Unique")
            for album in albums
        ]
        self._vertical_row_numbers.clear()
        self.endResetModel()

    def set_vertical_row_numbers(self, labels_by_source_row: dict[int, str]) -> None:
        """Set vertical header labels keyed by source row index."""
        normalized = {
            row_index: str(label)
            for row_index, label in labels_by_source_row.items()
            if 0 <= row_index < len(self._rows)
        }
        if normalized == self._vertical_row_numbers:
            return
        self._vertical_row_numbers = normalized
        if not self._rows:
            return
        self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, len(self._rows) - 1)

    def set_duplicate_groups(self, groups: list[DuplicateGroup]) -> None:
        """Update duplicate status column from duplicate groups."""
        statuses = self._duplicate_status_by_album_id(groups)
        for row in self._rows:
            row.duplicate_status = statuses.get(row.album.id, "Unique")

        if not self._rows:
            return
        top_left = self.index(0, AlbumColumn.DUPLICATE_STATUS)
        bottom_right = self.index(len(self._rows) - 1, AlbumColumn.DUPLICATE_STATUS)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])

    def update_album(self, row_index: int, album: Album) -> bool:
        """Update a row's album data."""
        if row_index < 0 or row_index >= len(self._rows):
            return False

        row = self._rows[row_index]
        row.album = album
        top_left = self.index(row_index, 0)
        bottom_right = self.index(row_index, len(AlbumColumn) - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])
        return True

    def checked_album_ids(self) -> list[str]:
        """Return checked album ids in current row order."""
        return [row.album.id for row in self._rows if row.checked]

    def set_row_checked(self, row_index: int, checked: bool) -> bool:
        """Set checked state for a row."""
        if row_index < 0 or row_index >= len(self._rows):
            return False
        index = self.index(row_index, AlbumColumn.CHECKBOX)
        return self.setData(index, checked, Qt.ItemDataRole.EditRole)

    def set_all_checked(self, checked: bool) -> None:
        """Set checked state for all rows."""
        if not self._rows:
            return
        changed = False
        for row in self._rows:
            if row.checked != checked:
                row.checked = checked
                changed = True
        if not changed:
            return
        top_left = self.index(0, AlbumColumn.CHECKBOX)
        bottom_right = self.index(len(self._rows) - 1, AlbumColumn.CHECKBOX)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [Qt.ItemDataRole.CheckStateRole, Qt.ItemDataRole.EditRole],
        )

    def _display_value(self, row: _AlbumRow, column: AlbumColumn) -> object:
        album = row.album
        if column == AlbumColumn.CHECKBOX:
            return ""
        if column == AlbumColumn.YEAR:
            return album.release_year
        if column == AlbumColumn.TITLE:
            return album.title
        if column == AlbumColumn.TYPE:
            return self._format_enum(album.album_type.value)
        if column == AlbumColumn.EDITION:
            return self._format_enum(album.edition.value)
        if column == AlbumColumn.TRACKS:
            return len(album.tracks)
        if column == AlbumColumn.DURATION:
            return self._format_duration(self._duration_seconds(album))
        if column == AlbumColumn.QUALITY:
            return self._format_enum(album.quality.value)
        if column == AlbumColumn.DUPLICATE_STATUS:
            return row.duplicate_status
        return None

    def _sort_value(self, row: _AlbumRow, column: AlbumColumn) -> Any:
        album = row.album
        if column == AlbumColumn.CHECKBOX:
            return row.checked
        if column == AlbumColumn.YEAR:
            return album.release_year
        if column == AlbumColumn.TITLE:
            return album.title.lower()
        if column == AlbumColumn.TYPE:
            return album.album_type.value
        if column == AlbumColumn.EDITION:
            return album.edition.value
        if column == AlbumColumn.TRACKS:
            return len(album.tracks)
        if column == AlbumColumn.DURATION:
            return self._duration_seconds(album)
        if column == AlbumColumn.QUALITY:
            return album.quality.value
        if column == AlbumColumn.DUPLICATE_STATUS:
            return row.duplicate_status.lower()
        return ""

    def _duration_seconds(self, album: Album) -> int:
        return sum(track.duration_seconds for track in album.tracks)

    def _format_duration(self, seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining = seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{remaining:02d}"
        return f"{minutes}:{remaining:02d}"

    def _format_enum(self, value: str) -> str:
        return value.replace("_", " ").title()

    def _duplicate_status_by_album_id(
        self, groups: list[DuplicateGroup]
    ) -> dict[str, str]:
        status: dict[str, str] = {}
        for group in groups:
            status[group.canonical_album_id] = "Canonical"
            for album_id in group.variant_album_ids:
                status[album_id] = "Variant"
        return status

    def _coerce_checked(self, value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if value == Qt.CheckState.Checked:
            return True
        if value == Qt.CheckState.Unchecked:
            return False
        if isinstance(value, int):
            if value == Qt.CheckState.Checked.value:
                return True
            if value == Qt.CheckState.Unchecked.value:
                return False
        return None

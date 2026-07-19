"""Main application window."""

from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from tidal_playlist_builder.model import (
    AlbumEdition,
    AlbumType,
    DuplicateStatus,
    FilterCriteria,
)
from tidal_playlist_builder.__about__ import (
    APP_NAME,
    COPYRIGHT,
    LICENSE_NAME,
    PROJECT_URL,
    __version__,
)

from .models import AlbumFilterProxyModel, AlbumTableModel
from .resources import load_application_icon


class MainWindow(QMainWindow):
    """Top-level window that coordinates GUI widgets only."""

    searchRequested = Signal(str)
    refreshRequested = Signal()
    createPlaylistRequested = Signal()
    albumSelectionChanged = Signal(list)

    _SETTINGS_GEOMETRY = "main_window/geometry"
    _SETTINGS_SPLITTER = "main_window/splitter_state"
    _SETTINGS_COLUMN_WIDTHS = "main_window/column_widths"
    _SETTINGS_FILTER_DUPLICATE = "main_window/filter/duplicate_status"
    _SETTINGS_FILTER_RELEASE_TYPE = "main_window/filter/release_type"
    _SETTINGS_FILTER_ALBUM_TYPE = "main_window/filter/album_type"
    _SETTINGS_FILTER_YEAR_MIN = "main_window/filter/year_min"
    _SETTINGS_FILTER_YEAR_MAX = "main_window/filter/year_max"
    _SETTINGS_FILTER_EXPLICIT = "main_window/filter/explicit"
    _SETTINGS_FILTER_SEARCH_TEXT = "main_window/filter/search_text"

    def __init__(
        self,
        settings: QSettings | None = None,
        album_table_model: AlbumTableModel | None = None,
        album_proxy_model: AlbumFilterProxyModel | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings or QSettings(
            "tidal-playlist-builder", "tidal-playlist-builder"
        )
        self._album_table_model = album_table_model or AlbumTableModel([])
        self._album_proxy_model = album_proxy_model or AlbumFilterProxyModel()
        self._album_proxy_model.setSourceModel(self._album_table_model)

        self._search_enabled = False
        self._is_busy = False
        self._has_album_selection = False

        self._splitter: QSplitter
        self._album_table: QTableView
        self._search_input: QLineEdit
        self._search_button: QPushButton
        self._refresh_action: QAction
        self._create_playlist_action: QAction
        self._create_playlist_menu_action: QAction
        self._preview_table: QTableView
        self._preview_model: QStandardItemModel
        self._duplicate_status_combo: QComboBox
        self._release_type_combo: QComboBox
        self._album_type_combo: QComboBox
        self._explicit_combo: QComboBox
        self._year_min_spin: QSpinBox
        self._year_max_spin: QSpinBox
        self._filter_search_input: QLineEdit
        self._active_filter_criteria = FilterCriteria()

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(load_application_icon())
        self.resize(1200, 760)
        self._create_menu_bar()
        self._create_toolbar()
        self._create_central_layout()
        self._create_status_bar()
        self._restore_settings()
        self.set_search_enabled(False)

    def _create_menu_bar(self) -> None:
        file_menu: QMenu = self.menuBar().addMenu("&File")
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        actions_menu: QMenu = self.menuBar().addMenu("&Actions")
        self._create_playlist_menu_action = QAction("Create Playlist", self)
        self._create_playlist_menu_action.setEnabled(False)
        self._create_playlist_menu_action.triggered.connect(
            self._on_create_playlist_clicked
        )
        actions_menu.addAction(self._create_playlist_menu_action)

        help_menu: QMenu = self.menuBar().addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self._refresh_action = QAction("Refresh", self)
        self._refresh_action.setEnabled(False)
        self._refresh_action.triggered.connect(self._on_refresh_clicked)
        self._create_playlist_action = QAction("Create Playlist", self)
        self._create_playlist_action.setEnabled(False)
        self._create_playlist_action.triggered.connect(self._on_create_playlist_clicked)
        toolbar.addAction(self._refresh_action)
        toolbar.addAction(self._create_playlist_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

    def _create_central_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._create_search_row(root))

        self._splitter = QSplitter(Qt.Orientation.Horizontal, root)
        self._splitter.addWidget(self._create_filter_panel())
        self._splitter.addWidget(self._create_album_table())
        self._splitter.addWidget(self._create_preview_panel())
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setSizes([230, 700, 270])
        root_layout.addWidget(self._splitter)

        self.setCentralWidget(root)
        self._bind_model_signals()

    def _bind_model_signals(self) -> None:
        self._album_table_model.dataChanged.connect(self._on_model_selection_changed)
        self._album_table_model.modelReset.connect(self._on_model_selection_changed)
        self._album_table_model.rowsInserted.connect(self._on_model_selection_changed)
        self._album_table_model.rowsRemoved.connect(self._on_model_selection_changed)
        self._refresh_create_playlist_action_state()

    def _create_search_row(self, parent: QWidget) -> QWidget:
        search_group = QGroupBox("Artist Search", parent)
        row = QHBoxLayout(search_group)
        row.addWidget(QLabel("Artist Name", search_group))
        self._search_input = QLineEdit(search_group)
        self._search_input.setPlaceholderText("Search artist")
        self._search_button = QPushButton("Search", search_group)
        self._search_button.clicked.connect(self._on_search_clicked)
        row.addWidget(self._search_input, 1)
        row.addWidget(self._search_button)
        return search_group

    def _create_filter_panel(self) -> QWidget:
        panel = QGroupBox("Filters")
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        duplicate_row = QHBoxLayout()
        duplicate_row.addWidget(QLabel("Duplicate", panel))
        self._duplicate_status_combo = QComboBox(panel)
        self._duplicate_status_combo.setObjectName("duplicateStatusFilter")
        for status in DuplicateStatus:
            self._duplicate_status_combo.addItem(
                self._format_enum_label(status.value), status
            )
        duplicate_row.addWidget(self._duplicate_status_combo, 1)
        layout.addLayout(duplicate_row)

        release_type_row = QHBoxLayout()
        release_type_row.addWidget(QLabel("Release Type", panel))
        self._release_type_combo = QComboBox(panel)
        self._release_type_combo.setObjectName("releaseTypeFilter")
        self._release_type_combo.addItem("Any", None)
        for edition in AlbumEdition:
            self._release_type_combo.addItem(
                self._format_enum_label(edition.value), edition
            )
        release_type_row.addWidget(self._release_type_combo, 1)
        layout.addLayout(release_type_row)

        album_type_row = QHBoxLayout()
        album_type_row.addWidget(QLabel("Album Type", panel))
        self._album_type_combo = QComboBox(panel)
        self._album_type_combo.setObjectName("albumTypeFilter")
        self._album_type_combo.addItem("Any", None)
        for album_type in AlbumType:
            self._album_type_combo.addItem(
                self._format_enum_label(album_type.value), album_type
            )
        album_type_row.addWidget(self._album_type_combo, 1)
        layout.addLayout(album_type_row)

        year_row = QHBoxLayout()
        year_row.addWidget(QLabel("Year", panel))
        self._year_min_spin = QSpinBox(panel)
        self._year_min_spin.setObjectName("yearMinFilter")
        self._year_min_spin.setRange(0, 3000)
        self._year_min_spin.setSpecialValueText("Any")
        self._year_min_spin.setValue(0)
        self._year_max_spin = QSpinBox(panel)
        self._year_max_spin.setObjectName("yearMaxFilter")
        self._year_max_spin.setRange(0, 3000)
        self._year_max_spin.setSpecialValueText("Any")
        self._year_max_spin.setValue(0)
        year_row.addWidget(self._year_min_spin, 1)
        year_row.addWidget(QLabel("to", panel))
        year_row.addWidget(self._year_max_spin, 1)
        layout.addLayout(year_row)

        explicit_row = QHBoxLayout()
        explicit_row.addWidget(QLabel("Explicit", panel))
        self._explicit_combo = QComboBox(panel)
        self._explicit_combo.setObjectName("explicitFilter")
        self._explicit_combo.addItem("Any", None)
        self._explicit_combo.addItem("Clean only", False)
        self._explicit_combo.addItem("Explicit only", True)
        explicit_row.addWidget(self._explicit_combo, 1)
        layout.addLayout(explicit_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search", panel))
        self._filter_search_input = QLineEdit(panel)
        self._filter_search_input.setObjectName("filterSearchInput")
        self._filter_search_input.setPlaceholderText("Filter title/artist")
        search_row.addWidget(self._filter_search_input, 1)
        layout.addLayout(search_row)

        self._duplicate_status_combo.currentIndexChanged.connect(
            self._on_filter_controls_changed
        )
        self._release_type_combo.currentIndexChanged.connect(
            self._on_filter_controls_changed
        )
        self._album_type_combo.currentIndexChanged.connect(
            self._on_filter_controls_changed
        )
        self._explicit_combo.currentIndexChanged.connect(
            self._on_filter_controls_changed
        )
        self._year_min_spin.valueChanged.connect(self._on_filter_controls_changed)
        self._year_max_spin.valueChanged.connect(self._on_filter_controls_changed)
        self._filter_search_input.textChanged.connect(self._on_filter_controls_changed)
        layout.addStretch(1)
        return panel

    def _create_album_table(self) -> QWidget:
        panel = QGroupBox("Albums")
        layout = QVBoxLayout(panel)

        self._album_table = QTableView(panel)
        self._album_table.setModel(self._album_proxy_model)
        self._album_table.setSortingEnabled(True)
        self._album_table.setAlternatingRowColors(True)
        self._album_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._album_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._album_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._album_table)
        return panel

    def _create_preview_panel(self) -> QWidget:
        panel = QGroupBox("Playlist Preview")
        layout = QVBoxLayout(panel)
        self._preview_table = QTableView(panel)
        self._preview_table.setObjectName("playlistPreviewTable")
        self._preview_model = QStandardItemModel(0, 2, self)
        self._preview_model.setHorizontalHeaderLabels(["Field", "Value"])
        self._preview_table.setModel(self._preview_model)
        self._preview_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._preview_table.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self._preview_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._preview_table.verticalHeader().setVisible(False)
        self._preview_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._preview_table)
        self.set_playlist_preview(
            playlist_name="-",
            album_count=0,
            track_count=0,
            estimated_duration="-",
            duplicate_summary="-",
            validation_warnings=["No selection"],
        )
        return panel

    def _create_status_bar(self) -> None:
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

    def _restore_settings(self) -> None:
        geometry = self._settings.value(self._SETTINGS_GEOMETRY)
        if geometry is not None:
            self.restoreGeometry(geometry)

        splitter_state = self._settings.value(self._SETTINGS_SPLITTER)
        if splitter_state is not None:
            self._splitter.restoreState(splitter_state)

        widths = self._settings.value(self._SETTINGS_COLUMN_WIDTHS)
        if isinstance(widths, list):
            for column, width in enumerate(widths):
                if column >= self._album_table_model.columnCount():
                    continue
                parsed_width = self._coerce_column_width(width)
                if parsed_width is not None:
                    self._album_table.setColumnWidth(column, parsed_width)

        duplicate_status = self._settings.value(self._SETTINGS_FILTER_DUPLICATE)
        release_type = self._settings.value(self._SETTINGS_FILTER_RELEASE_TYPE)
        album_type = self._settings.value(self._SETTINGS_FILTER_ALBUM_TYPE)
        year_min = self._settings.value(self._SETTINGS_FILTER_YEAR_MIN)
        year_max = self._settings.value(self._SETTINGS_FILTER_YEAR_MAX)
        explicit = self._settings.value(self._SETTINGS_FILTER_EXPLICIT)
        search_text = self._settings.value(self._SETTINGS_FILTER_SEARCH_TEXT)

        self._set_combo_by_data(
            self._duplicate_status_combo,
            self._enum_from_value(
                DuplicateStatus, duplicate_status, DuplicateStatus.ALL
            ),
        )
        self._set_combo_by_data(
            self._release_type_combo,
            self._enum_from_value(AlbumEdition, release_type, None),
        )
        self._set_combo_by_data(
            self._album_type_combo,
            self._enum_from_value(AlbumType, album_type, None),
        )
        self._set_combo_by_data(
            self._explicit_combo,
            self._bool_from_value(explicit),
        )
        self._year_min_spin.setValue(self._int_or_default(year_min, 0))
        self._year_max_spin.setValue(self._int_or_default(year_max, 0))
        if isinstance(search_text, str):
            self._filter_search_input.setText(search_text)
        self._apply_filter_from_controls()

    def _save_settings(self) -> None:
        self._settings.setValue(self._SETTINGS_GEOMETRY, self.saveGeometry())
        self._settings.setValue(self._SETTINGS_SPLITTER, self._splitter.saveState())
        widths = [
            self._album_table.columnWidth(column)
            for column in range(self._album_table_model.columnCount())
        ]
        self._settings.setValue(self._SETTINGS_COLUMN_WIDTHS, widths)
        self._settings.setValue(
            self._SETTINGS_FILTER_DUPLICATE,
            self._combo_data_value(self._duplicate_status_combo),
        )
        self._settings.setValue(
            self._SETTINGS_FILTER_RELEASE_TYPE,
            self._combo_data_value(self._release_type_combo),
        )
        self._settings.setValue(
            self._SETTINGS_FILTER_ALBUM_TYPE,
            self._combo_data_value(self._album_type_combo),
        )
        self._settings.setValue(
            self._SETTINGS_FILTER_EXPLICIT,
            self._combo_data_value(self._explicit_combo),
        )
        self._settings.setValue(
            self._SETTINGS_FILTER_YEAR_MIN, self._year_min_spin.value()
        )
        self._settings.setValue(
            self._SETTINGS_FILTER_YEAR_MAX, self._year_max_spin.value()
        )
        self._settings.setValue(
            self._SETTINGS_FILTER_SEARCH_TEXT, self._filter_search_input.text()
        )
        self._settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_settings()
        super().closeEvent(event)

    @Slot()
    def _on_search_clicked(self) -> None:
        self.searchRequested.emit(self._search_input.text().strip())

    @Slot()
    def _on_refresh_clicked(self) -> None:
        self.refreshRequested.emit()

    @Slot()
    def _on_create_playlist_clicked(self) -> None:
        if not self._create_playlist_action.isEnabled():
            return
        self.createPlaylistRequested.emit()

    def set_busy(self, busy: bool) -> None:
        """Set busy UI state for future worker integration."""
        self._is_busy = busy
        self._refresh_action.setEnabled(not busy)
        self._search_button.setEnabled(self._search_enabled and not busy)
        self._refresh_create_playlist_action_state()

    def set_status(self, message: str) -> None:
        """Set current status bar message."""
        self.statusBar().showMessage(message)

    def set_search_enabled(self, enabled: bool) -> None:
        """Enable/disable search action without changing business behavior."""
        self._search_enabled = enabled
        self._search_button.setEnabled(enabled and not self._is_busy)

    def show_success_dialog(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def show_error_dialog(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            (
                f"{APP_NAME}\n"
                f"Version: {__version__}\n"
                f"{COPYRIGHT}\n"
                f"License: {LICENSE_NAME}\n"
                f"Project URL: {PROJECT_URL}"
            ),
        )

    def _coerce_column_width(self, value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @Slot()
    def _on_model_selection_changed(self, *_args: object) -> None:
        checked_ids = self._album_table_model.checked_album_ids()
        self._has_album_selection = bool(checked_ids)
        self._refresh_create_playlist_action_state()
        self.albumSelectionChanged.emit(checked_ids)

    def _refresh_create_playlist_action_state(self) -> None:
        enabled = self._has_album_selection and not self._is_busy
        self._create_playlist_action.setEnabled(enabled)
        self._create_playlist_menu_action.setEnabled(enabled)

    @Slot()
    def _on_filter_controls_changed(self, *_args: object) -> None:
        self._apply_filter_from_controls()

    def _apply_filter_from_controls(self) -> None:
        release_type = self._release_type_combo.currentData()
        album_type = self._album_type_combo.currentData()
        explicit = self._explicit_combo.currentData()

        criteria = FilterCriteria(
            release_year_min=self._none_if_zero(self._year_min_spin.value()),
            release_year_max=self._none_if_zero(self._year_max_spin.value()),
            album_types=(
                frozenset({album_type}) if isinstance(album_type, AlbumType) else None
            ),
            editions=(
                frozenset({release_type})
                if isinstance(release_type, AlbumEdition)
                else None
            ),
            explicit=explicit if isinstance(explicit, bool) else None,
            duplicate_status=(
                self._duplicate_status_combo.currentData()
                if isinstance(
                    self._duplicate_status_combo.currentData(), DuplicateStatus
                )
                else DuplicateStatus.ALL
            ),
            search_text=self._filter_search_input.text() or None,
        )
        if criteria == self._active_filter_criteria:
            return
        self._active_filter_criteria = criteria
        self._album_proxy_model.set_filter_criteria(criteria)

    def _set_combo_by_data(self, combo: QComboBox, value: object) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _combo_data_value(self, combo: QComboBox) -> object:
        value = combo.currentData()
        if hasattr(value, "value"):
            return getattr(value, "value")
        return value

    def _enum_from_value(
        self, enum_class: object, value: object, default: object
    ) -> object:
        if not isinstance(value, str):
            return default
        enum_type = enum_class
        try:
            return enum_type(value)  # type: ignore[operator]
        except (TypeError, ValueError):
            return default

    def _bool_from_value(self, value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
        return None

    def _int_or_default(self, value: object, default: int) -> int:
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return default

    def _none_if_zero(self, value: int) -> int | None:
        if value <= 0:
            return None
        return value

    def _format_enum_label(self, value: str) -> str:
        return value.replace("_", " ").title()

    def set_playlist_preview(
        self,
        *,
        playlist_name: str,
        album_count: int,
        track_count: int,
        estimated_duration: str,
        duplicate_summary: str,
        validation_warnings: list[str],
    ) -> None:
        rows = [
            ("Playlist Name", playlist_name),
            ("Album Count", str(album_count)),
            ("Track Count", str(track_count)),
            ("Estimated Duration", estimated_duration),
            ("Duplicate Summary", duplicate_summary),
            (
                "Validation Warnings",
                "None" if not validation_warnings else "\n".join(validation_warnings),
            ),
        ]
        self._preview_model.removeRows(0, self._preview_model.rowCount())
        for field, value in rows:
            field_item = QStandardItem(field)
            value_item = QStandardItem(value)
            field_item.setEditable(False)
            value_item.setEditable(False)
            self._preview_model.appendRow([field_item, value_item])

    @property
    def album_table_model(self) -> AlbumTableModel:
        return self._album_table_model

    @property
    def album_proxy_model(self) -> AlbumFilterProxyModel:
        return self._album_proxy_model

    @property
    def splitter(self) -> QSplitter:
        return self._splitter

    @property
    def album_table(self) -> QTableView:
        return self._album_table

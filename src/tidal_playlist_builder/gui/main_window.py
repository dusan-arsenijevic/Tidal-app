"""Main application window."""

from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .bootstrap import AlbumModelFactory
from .models import AlbumFilterProxyModel, AlbumTableModel


class MainWindow(QMainWindow):
    """Top-level window that coordinates GUI widgets only."""

    searchRequested = Signal(str)
    refreshRequested = Signal()

    _SETTINGS_GEOMETRY = "main_window/geometry"
    _SETTINGS_SPLITTER = "main_window/splitter_state"
    _SETTINGS_COLUMN_WIDTHS = "main_window/column_widths"

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
        model_factory = AlbumModelFactory()
        self._album_table_model = (
            album_table_model or model_factory.create_album_table_model()
        )
        self._album_proxy_model = album_proxy_model or AlbumFilterProxyModel()
        self._album_proxy_model.setSourceModel(self._album_table_model)

        self._search_enabled = False
        self._is_busy = False

        self._splitter: QSplitter
        self._album_table: QTableView
        self._search_input: QLineEdit
        self._search_button: QPushButton
        self._refresh_action: QAction

        self.setWindowTitle("Tidal Playlist Builder")
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

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self._refresh_action = QAction("Refresh", self)
        self._refresh_action.setEnabled(False)
        self._refresh_action.triggered.connect(self._on_refresh_clicked)
        toolbar.addAction(self._refresh_action)
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
        layout.addWidget(QLabel("Filter controls placeholder", panel))
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
        layout.addWidget(QLabel("Preview placeholder", panel))
        layout.addStretch(1)
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
                if isinstance(width, int):
                    self._album_table.setColumnWidth(column, width)
                    continue
                if isinstance(width, str) and width.isdigit():
                    self._album_table.setColumnWidth(column, int(width))

    def _save_settings(self) -> None:
        self._settings.setValue(self._SETTINGS_GEOMETRY, self.saveGeometry())
        self._settings.setValue(self._SETTINGS_SPLITTER, self._splitter.saveState())
        widths = [
            self._album_table.columnWidth(column)
            for column in range(self._album_table_model.columnCount())
        ]
        self._settings.setValue(self._SETTINGS_COLUMN_WIDTHS, widths)
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

    def set_busy(self, busy: bool) -> None:
        """Set busy UI state for future worker integration."""
        self._is_busy = busy
        self._refresh_action.setEnabled(not busy)
        self._search_button.setEnabled(self._search_enabled and not busy)

    def set_status(self, message: str) -> None:
        """Set current status bar message."""
        self.statusBar().showMessage(message)

    def set_search_enabled(self, enabled: bool) -> None:
        """Enable/disable search action without changing business behavior."""
        self._search_enabled = enabled
        self._search_button.setEnabled(enabled and not self._is_busy)

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

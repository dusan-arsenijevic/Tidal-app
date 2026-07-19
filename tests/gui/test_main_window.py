"""Tests for MainWindow."""

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QGroupBox, QLineEdit, QPushButton, QSplitter, QTableView

from tidal_playlist_builder.gui import MainWindow
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
    Track,
)


def _settings(tmp_path: Path) -> QSettings:
    settings_file = tmp_path / "main_window.ini"
    return QSettings(str(settings_file), QSettings.Format.IniFormat)


def test_window_constructs_with_mock_data(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "Tidal Playlist Builder"
    assert window.album_table_model.rowCount() > 0
    assert window.statusBar() is not None
    assert window.centralWidget() is not None


def test_splitter_and_panels_created(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()

    assert isinstance(window.splitter, QSplitter)
    assert window.splitter.orientation() == Qt.Orientation.Horizontal
    assert window.splitter.count() == 3

    panel_widgets = [window.splitter.widget(i) for i in range(window.splitter.count())]
    assert all(isinstance(widget, QGroupBox) for widget in panel_widgets)


def test_model_attachment(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()

    assert isinstance(window.album_table_model, AlbumTableModel)
    assert isinstance(window.album_proxy_model, AlbumFilterProxyModel)
    assert isinstance(window.album_table, QTableView)
    assert window.album_table.model() is window.album_proxy_model
    assert window.album_proxy_model.sourceModel() is window.album_table_model


def test_settings_persistence_on_close(qtbot, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.show()

    window.resize(980, 640)
    window.splitter.setSizes([180, 720, 260])
    window.album_table.setColumnWidth(AlbumColumn.TITLE, 444)
    window.album_table.setColumnWidth(AlbumColumn.YEAR, 111)
    window.close()

    saved_geometry = settings.value(MainWindow._SETTINGS_GEOMETRY)
    saved_splitter = settings.value(MainWindow._SETTINGS_SPLITTER)
    saved_widths = settings.value(MainWindow._SETTINGS_COLUMN_WIDTHS)

    assert saved_geometry is not None
    assert saved_splitter is not None
    assert isinstance(saved_widths, list)
    assert int(saved_widths[AlbumColumn.TITLE]) == 444
    assert int(saved_widths[AlbumColumn.YEAR]) == 111


def test_settings_restoration(qtbot, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = MainWindow(settings=settings)
    qtbot.addWidget(first)
    first.show()
    first.resize(1024, 700)
    first.splitter.setSizes([210, 680, 280])
    first.album_table.setColumnWidth(AlbumColumn.TITLE, 390)
    first.album_table.setColumnWidth(AlbumColumn.TRACKS, 123)
    first.close()

    restored = MainWindow(settings=settings)
    qtbot.addWidget(restored)
    restored.show()

    assert restored.width() == 1024
    assert restored.height() == 700
    sizes = restored.splitter.sizes()
    assert len(sizes) == 3
    assert sum(sizes) > 0
    assert restored.album_table.columnWidth(AlbumColumn.TITLE) == 390
    assert restored.album_table.columnWidth(AlbumColumn.TRACKS) == 123


def test_model_can_be_injected(qtbot, tmp_path: Path) -> None:
    artist = Artist(id="x", name="Injected")
    model = AlbumTableModel(
        [
            Album(
                id="a",
                title="Injected Album",
                artist=artist,
                release_year=2022,
                album_type=AlbumType.ALBUM,
                edition=AlbumEdition.ORIGINAL,
                quality=AudioQuality.LOSSLESS,
                is_explicit=False,
                tracks=(Track(id="t", title="Injected Track", duration_seconds=100),),
            )
        ]
    )
    window = MainWindow(settings=_settings(tmp_path), album_table_model=model)
    qtbot.addWidget(window)
    window.show()

    assert window.album_table_model is model
    assert window.album_proxy_model.sourceModel() is model
    assert window.album_table_model.rowCount() == 1


def test_search_signal_emits_user_intent(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()
    window.set_search_enabled(True)

    search_input = window.findChild(QLineEdit)
    search_button = next(
        (
            button
            for button in window.findChildren(QPushButton)
            if button.text() == "Search"
        ),
        None,
    )
    assert search_input is not None
    assert search_button is not None
    search_input.setText(" massive attack ")

    emitted: list[str] = []
    window.searchRequested.connect(emitted.append)
    qtbot.mouseClick(search_button, Qt.MouseButton.LeftButton)

    assert emitted == ["massive attack"]


def test_refresh_signal_emits_user_intent(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()

    emitted: list[bool] = []
    window.refreshRequested.connect(lambda: emitted.append(True))
    window.set_busy(False)
    for action in window.findChildren(QAction):
        if action.text() == "Refresh":
            action.trigger()
            break

    assert emitted == [True]


def test_busy_and_status_api_updates_ui_only(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()
    window.set_search_enabled(True)

    search_button = next(
        (
            button
            for button in window.findChildren(QPushButton)
            if button.text() == "Search"
        ),
        None,
    )
    assert search_button is not None
    assert search_button.isEnabled()

    window.set_busy(True)
    assert not search_button.isEnabled()

    window.set_status("Working")
    assert window.statusBar().currentMessage() == "Working"

    window.set_busy(False)
    assert search_button.isEnabled()

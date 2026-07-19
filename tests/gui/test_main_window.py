"""Tests for MainWindow."""

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
)

from tidal_playlist_builder.gui import MainWindow
from tidal_playlist_builder.__about__ import (
    APP_NAME,
    COPYRIGHT,
    LICENSE_NAME,
    PROJECT_URL,
    __version__,
)
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
    DuplicateStatus,
    FilterCriteria,
    Track,
)


def _settings(tmp_path: Path) -> QSettings:
    settings_file = tmp_path / "main_window.ini"
    return QSettings(str(settings_file), QSettings.Format.IniFormat)


def _model() -> AlbumTableModel:
    artist = Artist(id="artist:1", name="Massive Attack")
    return AlbumTableModel(
        [
            Album(
                id="album:1",
                title="Mezzanine",
                artist=artist,
                release_year=1998,
                album_type=AlbumType.ALBUM,
                edition=AlbumEdition.ORIGINAL,
                quality=AudioQuality.LOSSLESS,
                is_explicit=False,
                tracks=(Track(id="track:1", title="Angel", duration_seconds=390),),
            )
        ]
    )


def _model_with_two_albums() -> AlbumTableModel:
    artist = Artist(id="artist:1", name="Massive Attack")
    return AlbumTableModel(
        [
            Album(
                id="album:1",
                title="Mezzanine",
                artist=artist,
                release_year=1998,
                album_type=AlbumType.ALBUM,
                edition=AlbumEdition.ORIGINAL,
                quality=AudioQuality.LOSSLESS,
                is_explicit=False,
                tracks=(Track(id="track:1", title="Angel", duration_seconds=390),),
            ),
            Album(
                id="album:2",
                title="Blue Lines",
                artist=artist,
                release_year=1991,
                album_type=AlbumType.EP,
                edition=AlbumEdition.DELUXE,
                quality=AudioQuality.LOSSY,
                is_explicit=True,
                tracks=(
                    Track(id="track:2", title="Safe from Harm", duration_seconds=300),
                ),
            ),
        ]
    )


def test_window_constructs(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == APP_NAME
    assert not window.windowIcon().isNull()
    assert window.album_table_model.rowCount() == 1
    assert window.statusBar() is not None
    assert window.centralWidget() is not None


def test_splitter_and_panels_created(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    assert isinstance(window.splitter, QSplitter)
    assert window.splitter.orientation() == Qt.Orientation.Horizontal
    assert window.splitter.count() == 3

    panel_widgets = [window.splitter.widget(i) for i in range(window.splitter.count())]
    assert all(isinstance(widget, QGroupBox) for widget in panel_widgets)


def test_model_attachment(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    assert isinstance(window.album_table_model, AlbumTableModel)
    assert isinstance(window.album_proxy_model, AlbumFilterProxyModel)
    assert isinstance(window.album_table, QTableView)
    assert window.album_table.model() is window.album_proxy_model
    assert window.album_proxy_model.sourceModel() is window.album_table_model


def test_settings_persistence_on_close(qtbot, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    window = MainWindow(settings=settings, album_table_model=_model())
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
    first = MainWindow(settings=settings, album_table_model=_model())
    qtbot.addWidget(first)
    first.show()
    first.resize(1024, 700)
    first.splitter.setSizes([210, 680, 280])
    first.album_table.setColumnWidth(AlbumColumn.TITLE, 390)
    first.album_table.setColumnWidth(AlbumColumn.TRACKS, 123)
    first.close()

    restored = MainWindow(settings=settings, album_table_model=_model())
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
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
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
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
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
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
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


def test_create_playlist_action_state_depends_on_selection_and_busy(
    qtbot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()
    window.set_publish_ready(True)

    create_actions = [
        action
        for action in window.findChildren(QAction)
        if action.text() == "Create Playlist"
    ]
    assert len(create_actions) >= 1
    assert all(not action.isEnabled() for action in create_actions)

    window.album_table_model.set_row_checked(0, True)
    assert all(action.isEnabled() for action in create_actions)

    window.set_busy(True)
    assert all(not action.isEnabled() for action in create_actions)

    window.set_busy(False)
    assert all(action.isEnabled() for action in create_actions)


def test_create_playlist_action_emits_user_intent(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    window.set_publish_ready(True)
    window.album_table_model.set_row_checked(0, True)
    emitted: list[bool] = []
    window.createPlaylistRequested.connect(lambda: emitted.append(True))
    create_action = next(
        action
        for action in window.findChildren(QAction)
        if action.text() == "Create Playlist"
    )
    create_action.trigger()

    assert emitted == [True]


def test_publish_button_emits_user_intent(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()
    window.set_publish_ready(True)
    window.album_table_model.set_row_checked(0, True)

    emitted: list[bool] = []
    window.createPlaylistRequested.connect(lambda: emitted.append(True))
    publish_button = window.findChild(QPushButton, "publishPlaylistButton")
    assert publish_button is not None
    assert publish_button.isEnabled()

    qtbot.mouseClick(publish_button, Qt.MouseButton.LeftButton)
    assert emitted == [True]


def test_filter_controls_update_proxy_immediately(qtbot, tmp_path: Path) -> None:
    window = MainWindow(
        settings=_settings(tmp_path), album_table_model=_model_with_two_albums()
    )
    qtbot.addWidget(window)
    window.show()

    search_filter = window.findChild(QLineEdit, "filterSearchInput")
    album_type_filter = window.findChild(QComboBox, "albumTypeFilter")
    assert search_filter is not None
    assert album_type_filter is not None

    search_filter.setText("blue")
    assert window.album_proxy_model.rowCount() == 1

    # Reset search and filter by album type (EP)
    search_filter.setText("")
    album_type_filter.setCurrentIndex(2)  # EP
    criteria = window.album_proxy_model.filter_criteria()
    assert criteria.album_types == frozenset({AlbumType.EP})
    assert window.album_proxy_model.rowCount() == 1


def test_filter_settings_persist_and_restore(qtbot, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = MainWindow(settings=settings, album_table_model=_model_with_two_albums())
    qtbot.addWidget(first)
    first.show()

    duplicate_filter = first.findChild(QComboBox, "duplicateStatusFilter")
    year_min_filter = first.findChild(QSpinBox, "yearMinFilter")
    explicit_filter = first.findChild(QComboBox, "explicitFilter")
    search_filter = first.findChild(QLineEdit, "filterSearchInput")
    assert duplicate_filter is not None
    assert year_min_filter is not None
    assert explicit_filter is not None
    assert search_filter is not None

    duplicate_filter.setCurrentIndex(2)  # Variants only
    year_min_filter.setValue(1995)
    explicit_filter.setCurrentIndex(2)  # Explicit only
    search_filter.setText("blue")
    first.close()

    restored = MainWindow(settings=settings, album_table_model=_model_with_two_albums())
    qtbot.addWidget(restored)
    restored.show()

    restored_criteria = restored.album_proxy_model.filter_criteria()
    assert restored_criteria.duplicate_status == DuplicateStatus.VARIANTS_ONLY
    assert restored_criteria.release_year_min == 1995
    assert restored_criteria.explicit is True
    assert restored_criteria.search_text == "blue"


def test_filter_changes_preserve_checked_albums(qtbot, tmp_path: Path) -> None:
    window = MainWindow(
        settings=_settings(tmp_path), album_table_model=_model_with_two_albums()
    )
    qtbot.addWidget(window)
    window.show()

    window.album_table_model.set_row_checked(1, True)
    assert window.album_table_model.checked_album_ids() == ["album:2"]

    window.album_proxy_model.set_filter_criteria(FilterCriteria(search_text="mezz"))
    assert window.album_proxy_model.rowCount() == 1
    assert window.album_table_model.checked_album_ids() == ["album:2"]


def test_playlist_preview_updates_rows(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    window.set_playlist_preview(
        playlist_name="Massive Attack Playlist",
        album_count=2,
        track_count=30,
        estimated_duration="1:52:40",
        duplicate_summary="4 duplicate tracks skipped",
        validation_warnings=["Select at least one album"],
    )

    preview_table = window.findChild(QTableView, "playlistPreviewTable")
    assert preview_table is not None
    model = preview_table.model()
    assert model is not None
    assert model.rowCount() == 6
    assert model.index(0, 1).data() == "Massive Attack Playlist"
    assert model.index(1, 1).data() == "2"
    assert model.index(2, 1).data() == "30"
    assert model.index(3, 1).data() == "1:52:40"
    assert model.index(4, 1).data() == "4 duplicate tracks skipped"
    assert model.index(5, 1).data() == "Select at least one album"


def test_about_dialog_displays_release_metadata(
    monkeypatch, qtbot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    captured: list[tuple[object, str, str]] = []

    def _fake_about(parent: object, title: str, text: str) -> None:
        captured.append((parent, title, text))

    monkeypatch.setattr(
        "tidal_playlist_builder.gui.main_window.QMessageBox.about", _fake_about
    )
    window.show_about_dialog()

    assert len(captured) == 1
    _parent, title, text = captured[0]
    assert title == f"About {APP_NAME}"
    assert APP_NAME in text
    assert __version__ in text
    assert COPYRIGHT in text
    assert LICENSE_NAME in text
    assert PROJECT_URL in text


def test_sign_in_action_emits_credentials(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    emitted: list[tuple[dict[str, str], bool]] = []
    window.signInRequested.connect(
        lambda credentials, remember: emitted.append((credentials, remember))
    )
    sign_in_action = next(
        action
        for action in window.findChildren(QAction)
        if action.text() == "Sign In with Browser..."
    )
    sign_in_action.trigger()

    assert emitted == [({"interactive": "true"}, True)]


def test_authentication_state_updates_account_actions(qtbot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path), album_table_model=_model())
    qtbot.addWidget(window)
    window.show()

    sign_in_action = next(
        action
        for action in window.findChildren(QAction)
        if action.text() == "Sign In with Browser..."
    )
    sign_out_action = next(
        action for action in window.findChildren(QAction) if action.text() == "Sign Out"
    )

    assert sign_in_action.isEnabled()
    assert not sign_out_action.isEnabled()

    window.set_authentication_state(authenticated=True, username="demo-user")

    assert not sign_in_action.isEnabled()
    assert sign_out_action.isEnabled()
    labels = window.statusBar().findChildren(QLabel)
    assert any("demo-user" in label.text() for label in labels)

"""Integration tests for end-to-end workflow orchestration."""

from dataclasses import dataclass, field
from pathlib import Path
import time

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QPushButton, QTableView

from tidal_playlist_builder.application import AppConfig, build_production_composition


@dataclass
class _WorkflowApiClient:
    search_calls: int = 0
    album_calls: int = 0
    track_calls: int = 0
    create_calls: int = 0
    add_calls: int = 0
    delete_calls: int = 0
    auth_calls: int = 0
    fail_search: bool = False
    add_sleep_seconds: float = 0.0
    added_batches: list[list[str]] = field(default_factory=list)

    def authenticate(self, credentials: dict[str, str]) -> str:
        self.auth_calls += 1
        return "token"

    def clear_authentication(self) -> None:
        return None

    def search_artists(self, query: str, limit: int) -> list[dict[str, object]]:
        del query, limit
        self.search_calls += 1
        if self.fail_search:
            time.sleep(0.05)
            raise TimeoutError("search timeout")
        time.sleep(0.05)
        return [{"id": "artist:1", "name": "Massive Attack"}]

    def get_artist_albums(self, artist_id: str) -> list[dict[str, object]]:
        del artist_id
        self.album_calls += 1
        time.sleep(0.05)
        return [
            {
                "id": "album:1",
                "title": "Mezzanine",
                "release_year": 1998,
                "album_type": "album",
                "edition": "original",
                "quality": "lossless",
                "is_explicit": False,
                "artist": {"id": "artist:1", "name": "Massive Attack"},
            },
            {
                "id": "album:2",
                "title": "Mezzanine",
                "release_year": 2001,
                "album_type": "album",
                "edition": "deluxe",
                "quality": "lossless",
                "is_explicit": False,
                "artist": {"id": "artist:1", "name": "Massive Attack"},
            },
        ]

    def get_album_tracks(self, album_id: str) -> list[dict[str, object]]:
        self.track_calls += 1
        if album_id == "album:1":
            return [
                {"id": f"a1-{i}", "title": f"Track {i}", "duration_seconds": 180}
                for i in range(150)
            ]
        return [
            {"id": f"a2-{i}", "title": f"Track {i}", "duration_seconds": 200}
            for i in range(150)
        ]

    def create_playlist(self, name: str, description: str) -> str:
        del name, description
        self.create_calls += 1
        return "playlist:1"

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        del playlist_id
        self.add_calls += 1
        if self.add_sleep_seconds > 0:
            time.sleep(self.add_sleep_seconds)
        self.added_batches.append(list(track_ids))

    def delete_playlist(self, playlist_id: str) -> None:
        del playlist_id
        self.delete_calls += 1


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        base_url="https://api.example.test/v1",
        timeout_seconds=5.0,
        retry_count=0,
        retry_backoff_seconds=0.0,
        user_agent="workflow-test/1.0",
        cache_directory=tmp_path / "cache",
        max_memory_entries=64,
        default_ttl_seconds=300,
        max_worker_threads=2,
        provider_backend="http",
        auth_credentials={"token": "x"},
    )


def _config_without_auth(tmp_path: Path) -> AppConfig:
    return AppConfig(
        base_url="https://api.example.test/v1",
        timeout_seconds=5.0,
        retry_count=0,
        retry_backoff_seconds=0.0,
        user_agent="workflow-test/1.0",
        cache_directory=tmp_path / "cache",
        max_memory_entries=64,
        default_ttl_seconds=300,
        max_worker_threads=2,
        provider_backend="http",
        auth_credentials=None,
    )


def _search_button(composition) -> QPushButton:
    button = next(
        (
            candidate
            for candidate in composition.main_window.findChildren(QPushButton)
            if candidate.text() == "Search"
        ),
        None,
    )
    assert button is not None
    return button


def _create_playlist_action(composition) -> QAction:
    action = next(
        (
            candidate
            for candidate in composition.main_window.findChildren(QAction)
            if candidate.text() == "Create Playlist" and candidate.isEnabled()
        ),
        None,
    )
    assert action is not None
    return action


def _preview_value(composition, field_name: str) -> str:
    table = composition.main_window.findChild(QTableView, "playlistPreviewTable")
    assert table is not None
    model = table.model()
    assert model is not None
    for row in range(model.rowCount()):
        if model.index(row, 0).data() == field_name:
            value = model.index(row, 1).data()
            assert isinstance(value, str)
            return value
    raise AssertionError(f"Missing preview field: {field_name}")


def test_workflow_search_load_duplicates_and_cache(qtbot, tmp_path: Path) -> None:
    client = _WorkflowApiClient()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    composition = build_production_composition(
        _config(tmp_path), settings=settings, api_client=client
    )
    qtbot.addWidget(composition.main_window)
    composition.main_window.show()
    composition.main_window.show_error_dialog = lambda _t, _m: None  # type: ignore[assignment]
    composition.main_window.show_success_dialog = lambda _t, _m: None  # type: ignore[assignment]

    composition.workflow._on_search_requested("massive")
    qtbot.waitUntil(lambda: composition.album_table_model.rowCount() == 2, timeout=3000)
    qtbot.waitUntil(lambda: client.track_calls == 2, timeout=3000)
    assert (
        _preview_value(composition, "Validation Warnings")
        == "Select at least one album"
    )
    composition.album_table_model.set_row_checked(0, True)
    qtbot.waitUntil(
        lambda: _preview_value(composition, "Track Count") == "150", timeout=3000
    )
    assert _preview_value(composition, "Album Count") == "1"
    assert _preview_value(composition, "Playlist Name") == "Massive Attack Playlist"
    duplicate_groups = composition.workflow._detect_duplicates(  # noqa: SLF001
        composition.workflow._current_albums  # noqa: SLF001
    )
    assert len(duplicate_groups) == 1
    assert duplicate_groups[0].canonical_album_id == "album:1"

    assert client.auth_calls == 1
    assert client.search_calls == 1
    assert client.album_calls == 1
    assert client.track_calls == 2

    composition.workflow._on_refresh_requested()
    qtbot.wait(150)
    assert client.album_calls == 1
    assert client.track_calls == 2


def test_workflow_busy_state_and_error_propagation(qtbot, tmp_path: Path) -> None:
    client = _WorkflowApiClient(fail_search=True)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    composition = build_production_composition(
        _config(tmp_path), settings=settings, api_client=client
    )
    qtbot.addWidget(composition.main_window)
    composition.main_window.show()
    composition.main_window.show_error_dialog = lambda _t, _m: None  # type: ignore[assignment]
    composition.main_window.show_success_dialog = lambda _t, _m: None  # type: ignore[assignment]

    search_button = _search_button(composition)
    composition.workflow._on_search_requested("massive")
    qtbot.waitUntil(
        lambda: composition.main_window.statusBar()
        .currentMessage()
        .startswith("Error:"),
        timeout=3000,
    )
    qtbot.waitUntil(lambda: search_button.isEnabled(), timeout=3000)


def test_workflow_playlist_progress_and_cancellation(qtbot, tmp_path: Path) -> None:
    client = _WorkflowApiClient(add_sleep_seconds=0.05)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    composition = build_production_composition(
        _config(tmp_path), settings=settings, api_client=client
    )
    qtbot.addWidget(composition.main_window)
    composition.main_window.show()
    composition.main_window.show_error_dialog = lambda _t, _m: None  # type: ignore[assignment]
    composition.main_window.show_success_dialog = lambda _t, _m: None  # type: ignore[assignment]

    composition.workflow._on_search_requested("massive")
    qtbot.waitUntil(lambda: composition.album_table_model.rowCount() == 2, timeout=3000)
    composition.album_table_model.set_row_checked(0, True)
    composition.album_table_model.set_row_checked(1, True)

    progress_events: list[str] = []
    failures: list[str] = []
    composition.workflow.playlistProgress.connect(progress_events.append)
    composition.workflow.operationFailed.connect(failures.append)

    action = _create_playlist_action(composition)
    action.trigger()
    action.trigger()
    qtbot.waitUntil(lambda: len(progress_events) > 0, timeout=3000)
    composition.workflow.cancel_playlist_creation()
    qtbot.waitUntil(lambda: len(failures) > 0, timeout=5000)

    assert any("adding_tracks" in event for event in progress_events)
    assert "cancelled" in failures[-1].lower()
    assert client.create_calls == 1
    assert client.add_calls >= 1


def test_workflow_sign_in_enables_search_and_persists_credentials(
    monkeypatch, qtbot, tmp_path: Path
) -> None:
    class _FakeCredentialStore:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.saved: tuple[str, str] | None = None

        def load(self) -> dict[str, str] | None:
            return None

        def save(self, *, username: str, password: str) -> None:
            self.saved = (username, password)

        def clear(self) -> None:
            return None

    monkeypatch.setattr(
        "tidal_playlist_builder.application.KeyringCredentialStore",
        _FakeCredentialStore,
    )
    client = _WorkflowApiClient()
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    composition = build_production_composition(
        _config_without_auth(tmp_path), settings=settings, api_client=client
    )
    qtbot.addWidget(composition.main_window)
    composition.main_window.show()

    assert not _search_button(composition).isEnabled()
    composition.workflow._on_sign_in_requested(  # noqa: SLF001
        {"username": "demo-user", "password": "demo-pass"}, True
    )
    qtbot.waitUntil(lambda: _search_button(composition).isEnabled(), timeout=3000)

    store = composition.credential_store
    assert isinstance(store, _FakeCredentialStore)
    assert store.saved == ("demo-user", "demo-pass")
    assert client.auth_calls == 1

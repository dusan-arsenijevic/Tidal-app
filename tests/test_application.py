"""Tests for production composition root."""

from pathlib import Path

from PySide6.QtCore import QSettings

import tidal_playlist_builder.configuration as configuration_module
from tidal_playlist_builder.exceptions import CacheError
from tidal_playlist_builder.application import (
    AppConfig,
    build_production_composition,
    load_app_config_from_env,
)
from tidal_playlist_builder.gui import MainWindow
from tidal_playlist_builder.threading import WorkerThreadPool


class _FakeApiClient:
    def authenticate(self, credentials: dict[str, str]) -> str:
        return "token"

    def clear_authentication(self) -> None:
        return None

    def search_artists(self, query: str, limit: int) -> list[dict[str, object]]:
        return []

    def get_artist_albums(self, artist_id: str) -> list[dict[str, object]]:
        return []

    def get_album_tracks(self, album_id: str) -> list[dict[str, object]]:
        return []

    def create_playlist(self, name: str, description: str) -> str:
        return "playlist-1"

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        return None

    def delete_playlist(self, playlist_id: str) -> None:
        return None


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        base_url="https://api.example.test/v1",
        timeout_seconds=10.0,
        retry_count=2,
        retry_backoff_seconds=0.2,
        user_agent="tpb-test/1.0",
        cache_directory=tmp_path / "cache",
        max_memory_entries=32,
        default_ttl_seconds=300,
        max_worker_threads=2,
    )


def test_build_production_composition_wires_dependencies(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)
    composition = build_production_composition(
        _config(tmp_path),
        settings=settings,
        api_client=_FakeApiClient(),
    )
    qtbot.addWidget(composition.main_window)

    assert isinstance(composition.main_window, MainWindow)
    assert isinstance(composition.worker_pool, WorkerThreadPool)
    assert composition.main_window.album_table_model is composition.album_table_model
    assert composition.main_window.album_proxy_model is composition.album_proxy_model
    assert composition.album_proxy_model.sourceModel() is composition.album_table_model
    assert composition.cache_service is not None
    assert composition.provider is not None
    assert composition.workflow is not None


def test_load_app_config_from_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TPB_BASE_URL", "https://env.example/v2")
    monkeypatch.setenv("TPB_TIMEOUT_SECONDS", "8")
    monkeypatch.setenv("TPB_RETRY_COUNT", "3")
    monkeypatch.setenv("TPB_RETRY_BACKOFF_SECONDS", "0.5")
    monkeypatch.setenv("TPB_USER_AGENT", "env-agent/2.0")
    monkeypatch.setenv("TPB_CACHE_DIR", str(tmp_path / "env-cache"))
    monkeypatch.setenv("TPB_MAX_MEMORY_ENTRIES", "64")
    monkeypatch.setenv("TPB_DEFAULT_TTL_SECONDS", "120")
    monkeypatch.setenv("TPB_MAX_WORKER_THREADS", "6")

    config = load_app_config_from_env()

    assert config.base_url == "https://env.example/v2"
    assert config.timeout_seconds == 8.0
    assert config.retry_count == 3
    assert config.retry_backoff_seconds == 0.5
    assert config.user_agent == "env-agent/2.0"
    assert config.cache_directory == tmp_path / "env-cache"
    assert config.max_memory_entries == 64
    assert config.default_ttl_seconds == 120
    assert config.max_worker_threads == 6


def test_load_app_config_from_env_defaults_to_windows_local_appdata(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TPB_CACHE_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(configuration_module.platform, "system", lambda: "Windows")

    config = load_app_config_from_env()

    assert config.cache_directory == (
        tmp_path / "LocalAppData" / "tidal-playlist-builder" / "cache"
    )


def test_load_app_config_from_env_defaults_to_xdg_cache_home(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TPB_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setattr(configuration_module.platform, "system", lambda: "Linux")

    config = load_app_config_from_env()

    assert config.cache_directory == tmp_path / "xdg-cache" / "tidal-playlist-builder"


def test_load_app_config_from_env_defaults_to_macos_cache(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TPB_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(configuration_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(configuration_module.Path, "home", lambda: tmp_path / "home")

    config = load_app_config_from_env()

    assert config.cache_directory == (
        tmp_path / "home" / "Library" / "Caches" / "tidal-playlist-builder"
    )


def test_build_production_composition_falls_back_when_disk_cache_unavailable(
    monkeypatch, qtbot, tmp_path: Path
) -> None:
    def _raise_cache_error(*_args: object, **_kwargs: object) -> object:
        raise CacheError("permission denied")

    monkeypatch.setattr(
        "tidal_playlist_builder.application.JsonCacheBackend",
        _raise_cache_error,
    )
    settings = QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)

    composition = build_production_composition(
        _config(tmp_path),
        settings=settings,
        api_client=_FakeApiClient(),
    )
    qtbot.addWidget(composition.main_window)

    assert composition.cache_backend is None

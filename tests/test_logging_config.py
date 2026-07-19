"""Tests for centralized logging configuration."""

import logging
from pathlib import Path

import tidal_playlist_builder.logging_config as logging_config


def test_default_log_directory_windows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    path = logging_config._default_log_directory()  # noqa: SLF001

    assert path == tmp_path / "LocalAppData" / "tidal-playlist-builder" / "logs"


def test_default_log_directory_linux(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    path = logging_config._default_log_directory()  # noqa: SLF001

    assert path == tmp_path / "state" / "tidal-playlist-builder" / "logs"


def test_default_log_directory_macos(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(logging_config.Path, "home", lambda: tmp_path / "home")

    path = logging_config._default_log_directory()  # noqa: SLF001

    assert path == tmp_path / "home" / "Library" / "Logs" / "tidal-playlist-builder"


def test_configure_runtime_logging_creates_log_file(
    monkeypatch, tmp_path: Path
) -> None:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    try:
        state = logging_config.configure_runtime_logging(
            level="debug",
            log_directory=tmp_path / "logs",
        )
        logging.getLogger("test.logger").warning("hello")

        assert state.level == "DEBUG"
        assert state.file_logging_enabled is True
        assert state.log_file.exists()
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)
        root_logger.setLevel(original_level)


def test_resolve_level_defaults_for_unknown_value() -> None:
    assert logging_config._resolve_level("verbose") == "INFO"  # noqa: SLF001

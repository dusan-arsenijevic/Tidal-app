"""Centralized runtime logging configuration."""

from dataclasses import dataclass
import logging
import logging.config
from pathlib import Path
import platform
import os

_APP_NAME = "tidal-playlist-builder"
_LOG_FILE_NAME = "application.log"
_DEFAULT_LEVEL = "INFO"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


@dataclass(frozen=True, slots=True)
class LoggingConfiguration:
    level: str
    log_directory: Path
    log_file: Path
    file_logging_enabled: bool


def configure_runtime_logging(
    *,
    level: str | None = None,
    log_directory: Path | None = None,
) -> LoggingConfiguration:
    """Configure root logging with console and rotating file handlers."""
    resolved_level = _resolve_level(level or os.getenv("TPB_LOG_LEVEL"))
    resolved_directory = log_directory or _log_directory_from_env()
    log_file = resolved_directory / _LOG_FILE_NAME

    file_logging_enabled = True
    try:
        resolved_directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        file_logging_enabled = False

    handlers: dict[str, dict[str, object]] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": resolved_level,
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        }
    }
    root_handlers = ["console"]
    if file_logging_enabled:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": resolved_level,
            "formatter": "standard",
            "filename": str(log_file),
            "maxBytes": _MAX_BYTES,
            "backupCount": _BACKUP_COUNT,
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                }
            },
            "handlers": handlers,
            "root": {
                "level": resolved_level,
                "handlers": root_handlers,
            },
        }
    )

    if not file_logging_enabled:
        logging.getLogger(__name__).warning(
            "File logging disabled; using console only for this session"
        )

    return LoggingConfiguration(
        level=resolved_level,
        log_directory=resolved_directory,
        log_file=log_file,
        file_logging_enabled=file_logging_enabled,
    )


def _resolve_level(level: str | None) -> str:
    if level is None:
        return _DEFAULT_LEVEL
    normalized = level.strip().upper()
    if normalized in _VALID_LEVELS:
        return normalized
    return _DEFAULT_LEVEL


def _log_directory_from_env() -> Path:
    configured = os.getenv("TPB_LOG_DIR")
    if configured is not None and configured.strip():
        return Path(configured)
    return _default_log_directory()


def _default_log_directory() -> Path:
    system_name = platform.system().lower()
    if system_name == "windows":
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata and local_appdata.strip():
            return Path(local_appdata) / _APP_NAME / "logs"
        return Path.home() / "AppData" / "Local" / _APP_NAME / "logs"
    if system_name == "darwin":
        return Path.home() / "Library" / "Logs" / _APP_NAME

    xdg_state = os.getenv("XDG_STATE_HOME")
    if xdg_state and xdg_state.strip():
        return Path(xdg_state) / _APP_NAME / "logs"
    return Path.home() / ".local" / "state" / _APP_NAME / "logs"

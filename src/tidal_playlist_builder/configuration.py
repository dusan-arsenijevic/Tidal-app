"""Application configuration loading."""

from dataclasses import dataclass
import os
import platform
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Runtime configuration for application composition."""

    base_url: str
    timeout_seconds: float
    retry_count: int
    retry_backoff_seconds: float
    user_agent: str
    cache_directory: Path
    max_memory_entries: int
    default_ttl_seconds: int | None
    max_worker_threads: int
    provider_backend: str = "tidalapi"
    auth_credentials: dict[str, str] | None = None
    settings_org: str = "tidal-playlist-builder"
    settings_app: str = "tidal-playlist-builder"


def load_app_config_from_env() -> AppConfig:
    """Create AppConfig from environment variables."""
    cache_directory = _cache_directory_from_env()
    return AppConfig(
        base_url=os.getenv("TPB_BASE_URL", "https://api.tidal.com/v1"),
        timeout_seconds=float(os.getenv("TPB_TIMEOUT_SECONDS", "10")),
        retry_count=int(os.getenv("TPB_RETRY_COUNT", "2")),
        retry_backoff_seconds=float(os.getenv("TPB_RETRY_BACKOFF_SECONDS", "0.2")),
        user_agent=os.getenv("TPB_USER_AGENT", "tidal-playlist-builder/1.0"),
        cache_directory=cache_directory,
        max_memory_entries=int(os.getenv("TPB_MAX_MEMORY_ENTRIES", "512")),
        default_ttl_seconds=_optional_int_from_env("TPB_DEFAULT_TTL_SECONDS"),
        max_worker_threads=int(os.getenv("TPB_MAX_WORKER_THREADS", "4")),
        provider_backend=os.getenv("TPB_PROVIDER_BACKEND", "tidalapi"),
        auth_credentials=_auth_credentials_from_env(),
        settings_org=os.getenv("TPB_SETTINGS_ORG", "tidal-playlist-builder"),
        settings_app=os.getenv("TPB_SETTINGS_APP", "tidal-playlist-builder"),
    )


def _cache_directory_from_env() -> Path:
    configured = os.getenv("TPB_CACHE_DIR")
    if configured is not None and configured.strip():
        return Path(configured)

    app_name = "tidal-playlist-builder"
    system_name = platform.system().lower()
    if system_name == "windows":
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata and local_appdata.strip():
            return Path(local_appdata) / app_name / "cache"
        return Path.home() / "AppData" / "Local" / app_name / "cache"
    if system_name == "darwin":
        return Path.home() / "Library" / "Caches" / app_name

    xdg_cache = os.getenv("XDG_CACHE_HOME")
    if xdg_cache and xdg_cache.strip():
        return Path(xdg_cache) / app_name
    return Path.home() / ".cache" / app_name


def _optional_int_from_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return int(value)


def _auth_credentials_from_env() -> dict[str, str] | None:
    token = os.getenv("TPB_AUTH_TOKEN")
    if token is not None and token.strip():
        return {"token": token}

    username = os.getenv("TPB_USERNAME")
    password = os.getenv("TPB_PASSWORD")
    if username and password:
        return {"username": username, "password": password}
    return None

"""Package metadata constants."""

from __future__ import annotations

import json
from pathlib import Path
import sys

APP_NAME = "Tidal Playlist Builder"
PROJECT_URL = "https://github.com/dusan-arsenijevic/Tidal-app"
LICENSE_NAME = "MIT"
COPYRIGHT = "Copyright (c) 2026 Dusan Arsenijevic"
__version__ = "1.0.0rc1"


def build_number() -> str | None:
    build_info_path = _build_info_path()
    if build_info_path is None or not build_info_path.exists():
        return None
    try:
        payload = json.loads(build_info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = payload.get("build_number")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def display_version() -> str:
    current_build = build_number()
    if current_build is None:
        return __version__
    return f"{__version__} (build {current_build})"


def _build_info_path() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "build-info.json"
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "dist" / "desktop" / "windows" / "build-info.json"

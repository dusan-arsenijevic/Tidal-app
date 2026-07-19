"""UI font safety checks and fallback selection."""

from __future__ import annotations

from collections.abc import Iterable
import logging

from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

_GLYPH_PROBE = "Tidal Playlist Builder Search Filters Albums Preview 0123456789"
_FALLBACK_PREFERRED_FAMILIES = (
    "Segoe UI",
    "SF Pro Text",
    "Helvetica Neue",
    "Noto Sans",
    "DejaVu Sans",
    "Liberation Sans",
    "Arial",
    "Sans Serif",
)


def ensure_ui_font_has_basic_glyphs(app: QApplication) -> None:
    """Keep the system default font unless it cannot render basic UI glyphs."""
    current_font = app.font()
    platform_name = QGuiApplication.platformName().lower()

    if platform_name in {"offscreen", "minimal"}:
        replacement = _find_supported_font_family(
            preferred=_FALLBACK_PREFERRED_FAMILIES,
            available=QFontDatabase.families(),
        )
        if replacement is not None and replacement != current_font.family():
            app.setFont(QFont(replacement, current_font.pointSize()))
            logger.warning(
                "Applied UI font fallback for %s platform from '%s' to '%s'",
                platform_name,
                current_font.family(),
                replacement,
            )
        return

    if _font_supports_probe(current_font):
        return

    replacement = _find_supported_font_family(
        preferred=_FALLBACK_PREFERRED_FAMILIES,
        available=QFontDatabase.families(),
    )
    if replacement is None:
        logger.warning(
            "Default UI font '%s' lacks basic glyphs and no replacement was found",
            current_font.family(),
        )
        return

    fallback_font = QFont(replacement, current_font.pointSize())
    app.setFont(fallback_font)
    logger.warning(
        "Applied UI font fallback from '%s' to '%s'",
        current_font.family(),
        replacement,
    )


def _font_supports_probe(font: QFont) -> bool:
    metrics = QFontMetrics(font)
    return all(metrics.inFontUcs4(ord(ch)) for ch in _GLYPH_PROBE)


def _find_supported_font_family(
    *,
    preferred: tuple[str, ...],
    available: Iterable[str],
) -> str | None:
    available_set = {name for name in available}

    for family in preferred:
        if family in available_set and _font_supports_probe(QFont(family)):
            return family

    for family in sorted(available_set):
        if _font_supports_probe(QFont(family)):
            return family
    return None

"""Tests for UI font fallback selection."""

from PySide6.QtGui import QFont

from tidal_playlist_builder.gui import font_fallback


def test_find_supported_font_family_prefers_preferred_list(monkeypatch) -> None:
    monkeypatch.setattr(
        font_fallback,
        "_font_supports_probe",
        lambda font: font.family() == "Noto Sans",
    )

    family = font_fallback._find_supported_font_family(  # noqa: SLF001
        preferred=("Segoe UI", "Noto Sans"),
        available=("Noto Sans", "Other"),
    )
    assert family == "Noto Sans"


def test_find_supported_font_family_returns_none_when_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(font_fallback, "_font_supports_probe", lambda _font: False)

    family = font_fallback._find_supported_font_family(  # noqa: SLF001
        preferred=("Segoe UI",),
        available=("Other",),
    )
    assert family is None


def test_font_supports_probe_uses_qfont_metrics() -> None:
    # Smoke test that helper returns a bool with a real QFont instance.
    supported = font_fallback._font_supports_probe(QFont())  # noqa: SLF001
    assert isinstance(supported, bool)

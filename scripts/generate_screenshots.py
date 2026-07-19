"""Generate README screenshots using the real GUI with native font rendering."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tidal_playlist_builder.gui.font_fallback import ensure_ui_font_has_basic_glyphs
from tidal_playlist_builder.gui.main_window import MainWindow
from tidal_playlist_builder.gui.models import AlbumTableModel
from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    Track,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use offscreen backend (may render tofu if no fonts are installed).",
    )
    args = parser.parse_args()

    if args.headless:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    else:
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            os.environ.pop("QT_QPA_PLATFORM", None)

    out_dir = Path("docs") / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    ensure_ui_font_has_basic_glyphs(app)
    artist = Artist(id="artist:1", name="Massive Attack")
    model = AlbumTableModel(
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
                tracks=(Track(id="t1", title="Angel", duration_seconds=390),),
            ),
            Album(
                id="album:2",
                title="Blue Lines",
                artist=artist,
                release_year=1991,
                album_type=AlbumType.ALBUM,
                edition=AlbumEdition.DELUXE,
                quality=AudioQuality.LOSSLESS,
                is_explicit=True,
                tracks=(Track(id="t2", title="Safe from Harm", duration_seconds=320),),
            ),
        ]
    )

    window = MainWindow(album_table_model=model)
    window.set_search_enabled(True)
    window.resize(1260, 780)
    window.show()
    app.processEvents()
    window.grab().save(str(out_dir / "main-window.png"))

    model.set_row_checked(0, True)
    window.set_playlist_preview(
        playlist_name="Massive Attack Playlist",
        album_count=1,
        track_count=10,
        estimated_duration="0:42:10",
        duplicate_summary="2 duplicate tracks skipped",
        validation_warnings=[],
    )
    app.processEvents()
    window.grab().save(str(out_dir / "playlist-preview.png"))
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

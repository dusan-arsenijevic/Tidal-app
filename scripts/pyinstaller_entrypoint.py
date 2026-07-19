"""PyInstaller entrypoint that preserves package import semantics."""

from __future__ import annotations

from tidal_playlist_builder.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())

"""Package entrypoint."""

import argparse
from collections.abc import Sequence

from tidal_playlist_builder.__about__ import __version__
from tidal_playlist_builder.application import run


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for local execution."""
    parser = argparse.ArgumentParser(prog="tidal-playlist-builder")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

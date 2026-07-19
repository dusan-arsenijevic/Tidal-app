"""Build a Windows desktop executable with PyInstaller."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from PyInstaller.__main__ import run as pyinstaller_run

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
ENTRYPOINT = ROOT / "scripts" / "pyinstaller_entrypoint.py"
ICON_SVG = SRC_DIR / "tidal_playlist_builder" / "resources" / "icons" / "app-icon.svg"
APP_NAME = "TidalPlaylistBuilder"


@dataclass(frozen=True, slots=True)
class BuildPaths:
    dist: Path
    work: Path
    spec: Path


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("build_windows.py must be run on Windows")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from tidal_playlist_builder.__about__ import APP_NAME as PRODUCT_NAME
    from tidal_playlist_builder.__about__ import __version__

    paths = BuildPaths(
        dist=ROOT / "dist" / "desktop" / "windows",
        work=ROOT / "build" / "pyinstaller" / "windows",
        spec=ROOT / "build" / "pyinstaller" / "spec",
    )
    paths.dist.mkdir(parents=True, exist_ok=True)
    paths.work.mkdir(parents=True, exist_ok=True)
    paths.spec.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="tpb-pyinstaller-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        icon_path = temp_dir / "app-icon.ico"
        _render_icon_for_windows(icon_path)
        version_file = temp_dir / "version-info.txt"
        version_file.write_text(
            _windows_version_file(
                product_name=PRODUCT_NAME,
                product_version=__version__,
                file_name=f"{APP_NAME}.exe",
            ),
            encoding="utf-8",
        )

        args = [
            str(ENTRYPOINT),
            "--name",
            APP_NAME,
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onefile",
            "--paths",
            str(SRC_DIR),
            "--collect-data",
            "tidal_playlist_builder.resources",
            "--hidden-import",
            "requests",
            "--distpath",
            str(paths.dist),
            "--workpath",
            str(paths.work),
            "--specpath",
            str(paths.spec),
            "--version-file",
            str(version_file),
        ]
        if icon_path.exists():
            args.extend(["--icon", str(icon_path)])
        pyinstaller_run(args)

    return 0


def _render_icon_for_windows(output_path: Path) -> None:
    from PySide6.QtGui import QGuiApplication, QIcon

    app = QGuiApplication.instance()
    owns_app = app is None
    if app is None:
        app = QGuiApplication([])
    icon = QIcon(str(ICON_SVG))
    pixmap = icon.pixmap(256, 256)
    pixmap.save(str(output_path), "ICO")
    if owns_app:
        app.quit()


def _windows_version_numbers(version: str) -> tuple[int, int, int, int]:
    numbers = [int(part) for part in re.findall(r"\d+", version)]
    while len(numbers) < 4:
        numbers.append(0)
    return tuple(numbers[:4])


def _windows_version_file(
    *,
    product_name: str,
    product_version: str,
    file_name: str,
) -> str:
    a, b, c, d = _windows_version_numbers(product_version)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({a}, {b}, {c}, {d}),
    prodvers=({a}, {b}, {c}, {d}),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Dusan Arsenijevic'),
          StringStruct('FileDescription', '{product_name}'),
          StringStruct('FileVersion', '{product_version}'),
          StringStruct('InternalName', '{product_name}'),
          StringStruct('LegalCopyright', 'Copyright (c) 2026 Dusan Arsenijevic'),
          StringStruct('OriginalFilename', '{file_name}'),
          StringStruct('ProductName', '{product_name}'),
          StringStruct('ProductVersion', '{product_version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


if __name__ == "__main__":
    raise SystemExit(main())

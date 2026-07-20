"""Build a Windows installer package for Tidal Playlist Builder."""

from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_EXE = ROOT / "dist" / "desktop" / "windows" / "TidalPlaylistBuilder.exe"
INSTALLER_DIR = ROOT / "dist" / "desktop" / "windows-installer"


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("build_windows_installer.py must be run on Windows")

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_windows.py")],
        check=True,
    )

    iscc = _resolve_iscc()
    if iscc is None:
        raise SystemExit(
            "Inno Setup compiler (ISCC.exe) was not found. "
            "Install Inno Setup and ensure ISCC.exe is in PATH, or set INNO_SETUP_ISCC."
        )

    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="tpb-inno-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        script_path = temp_dir / "TidalPlaylistBuilder.iss"
        script_path.write_text(_installer_script(), encoding="utf-8")
        subprocess.run(
            [str(iscc), str(script_path)],
            check=True,
            cwd=str(ROOT),
        )
    return 0


def _resolve_iscc() -> Path | None:
    env_value = _non_empty(os.environ.get("INNO_SETUP_ISCC"))
    if env_value is not None:
        path = Path(env_value).expanduser()
        return path if path.exists() else None

    path_value = shutil.which("iscc")
    if path_value is not None:
        return Path(path_value)

    candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _installer_script() -> str:
    from tidal_playlist_builder.__about__ import APP_NAME
    from tidal_playlist_builder.__about__ import COPYRIGHT
    from tidal_playlist_builder.__about__ import PROJECT_URL
    from tidal_playlist_builder.__about__ import __version__

    exe_path = WINDOWS_EXE.resolve()
    build_info_path = (
        ROOT / "dist" / "desktop" / "windows" / "build-info.json"
    ).resolve()
    installer_dir = INSTALLER_DIR.resolve()
    license_file = (ROOT / "LICENSE").resolve()
    output_base = f"TidalPlaylistBuilder-setup-{__version__}{_build_suffix()}"
    app_id = "TidalPlaylistBuilder"
    return f"""[Setup]
AppId={app_id}
AppName={APP_NAME}
AppVersion={__version__}
AppPublisher=Dusan Arsenijevic
AppPublisherURL={PROJECT_URL}
AppSupportURL={PROJECT_URL}
AppUpdatesURL={PROJECT_URL}
AppCopyright={COPYRIGHT}
DefaultDirName={{autopf}}\\{APP_NAME}
DefaultGroupName={APP_NAME}
DisableProgramGroupPage=yes
LicenseFile={license_file}
OutputDir={installer_dir}
OutputBaseFilename={output_base}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={{app}}\\TidalPlaylistBuilder.exe
CloseApplications=yes
CloseApplicationsFilter=TidalPlaylistBuilder.exe
RestartApplications=no
ForceCloseApplications=yes
ForceCloseApplicationsDelay=2000

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

[Files]
Source: "{exe_path}"; DestDir: "{{app}}"; Flags: ignoreversion
Source: "{build_info_path}"; DestDir: "{{app}}"; Flags: ignoreversion

[Icons]
Name: "{{group}}\\{APP_NAME}"; Filename: "{{app}}\\TidalPlaylistBuilder.exe"
Name: "{{autodesktop}}\\{APP_NAME}"; Filename: "{{app}}\\TidalPlaylistBuilder.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\TidalPlaylistBuilder.exe"; Description: "{{cm:LaunchProgram,{APP_NAME}}}"; Flags: nowait postinstall skipifsilent
"""


def _non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _build_suffix() -> str:
    build_number = _non_empty(os.environ.get("TPB_BUILD_NUMBER"))
    if build_number is None:
        return ""
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", build_number)
    return f"-build.{normalized}"


if __name__ == "__main__":
    raise SystemExit(main())

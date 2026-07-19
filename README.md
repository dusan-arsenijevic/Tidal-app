# Tidal Playlist Builder

Desktop application for building TIDAL playlists from artist discographies with duplicate-edition awareness, filtering, and playlist planning.

## Project overview

This project provides a PySide6 GUI that lets you:

- Search artists
- Load discographies and album tracks
- Detect duplicate editions
- Filter albums interactively
- Build a playlist plan preview
- Create playlists through the TIDAL provider layer

Current implementation uses a production composition root, background workers, a concrete HTTP client, and two-level caching (memory + JSON disk cache).

## Screenshots

> Placeholder screenshots (to be added)

![Main window placeholder](docs/screenshots/main-window-placeholder.png)
![Playlist preview placeholder](docs/screenshots/playlist-preview-placeholder.png)

## Architecture overview

High-level flow:

`GUI -> Workers -> Repositories -> TidalProvider -> TidalApiClient (protocol) -> HttpTidalApiClient`

Key modules:

- `application.py`: composition root and startup entry point
- `workflow.py`: GUI workflow orchestration
- `tidal/`: provider and production HTTP client
- `repositories/`: domain mapping + cache-backed data access
- `services/`: cache and playlist plan builder
- `gui/`: Qt widgets and models

Detailed design notes are in `docs/architecture.md`.

## Installation

### Prerequisites

- Python 3.12 or 3.13
- pip

### Setup

```bash
python -m venv .venv
```

Activate the virtual environment, then install dependencies:

```bash
python -m pip install --upgrade pip
pip install PySide6 requests ruff black mypy pytest pytest-qt pytest-cov
```

## Running from source

From the repository root:

```bash
set PYTHONPATH=src
python -m tidal_playlist_builder
```

On PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m tidal_playlist_builder
```

## Project structure

```text
src/tidal_playlist_builder/
  application.py        # composition root + run()
  configuration.py      # runtime config loading
  workflow.py           # UI workflow controller
  gui/                  # main window and Qt models
  model/                # domain models
  filtering/            # filtering criteria/engine
  repositories/         # provider payload -> domain mapping
  services/             # cache service, disk cache backend, plan builder
  threading/            # workers and thread-pool wrapper
  tidal/                # provider abstractions and HTTP implementation
  exceptions/           # domain-specific exception hierarchy
tests/                  # unit and integration-style tests
docs/                   # architecture and implementation notes
```

## Testing

Run the full quality and test suite:

```bash
set PYTHONPATH=src
ruff check .
black --check .
mypy src tests
pytest
```

## Development workflow

1. Create a feature branch.
2. Implement focused changes.
3. Run `ruff`, `black --check`, `mypy`, and `pytest`.
4. Open a pull request.
5. CI runs the same gates on Python 3.12 and 3.13.

## Release process

1. Ensure `ruff`, `black --check`, `mypy`, and `pytest` pass locally.
2. Bump the single-source version in `src/tidal_playlist_builder/__about__.py`.
3. Create and push a release tag, then publish a GitHub release.
4. The Release workflow builds wheel + source distribution, verifies metadata, and uploads artifacts from `dist/`.

## Desktop packaging (PyInstaller)

### Local Windows build

```powershell
python -m pip install . pyinstaller
python scripts/build_windows.py
```

Output executable:

```text
dist/desktop/windows/TidalPlaylistBuilder.exe
```

### CI desktop artifacts

The `Release` workflow also builds desktop artifacts with PyInstaller for:

- Windows (primary)
- Linux (secondary)
- macOS (secondary)

Artifacts are uploaded from `dist/desktop/` in GitHub Actions.

## Cache behavior

- **L1:** in-memory cache (bounded entries, LRU-style eviction)
- **L2:** JSON disk cache (one file per key under a category directory)
- Memory is checked first, then disk.
- Disk hits are promoted into memory.
- TTL expiration is enforced.
- Corrupt cache files are removed and treated as cache misses.

## Supported platforms

- Windows
- Linux
- macOS (expected with PySide6 support)

CI currently runs on Linux with Python 3.12 and 3.13.

## Roadmap

- Improve duplicate detection heuristics
- Expand provider support (Spotify/Qobuz) via current provider abstraction
- Add richer UI diagnostics and polish
- Package/release workflow for end users

## Contributing

Contributions are welcome. Please open an issue for significant changes before implementation and keep pull requests focused and test-backed.

## License

MIT (see `LICENSE`).

# Tidal Playlist Builder - Architecture

## Overview

**Tidal Playlist Builder** is a production-quality desktop application built with Python 3.13+ and PySide6 for discovering music, curating albums, detecting editions, and creating Tidal playlists with an intuitive Qt-based GUI.

The architecture emphasizes:
- **Responsive UI**: Qt threading model keeps GUI responsive during long operations
- **Clean separation**: Domain models, services, and GUI are strictly separated
- **Extensibility**: Provider abstraction allows future support for Spotify and Qobuz without redesign
- **Comprehensive duplicate detection**: Distinguishes between original editions, remasters, deluxe editions, etc.
- **Session persistence**: Window state, sort order, and selection are restored on restart

---

## 1. Project Structure

```
src/tidal_playlist_builder/
├── __init__.py
├── main.py                           # Entry point
├── gui/
│   ├── __init__.py
│   ├── main_window.py                # Main QMainWindow
│   ├── models/
│   │   ├── __init__.py
│   │   ├── album_table_model.py      # QAbstractTableModel for albums
│   │   └── album_filter_proxy_model.py # QSortFilterProxyModel
│   ├── dialogs/
│   │   ├── __init__.py
│   │   ├── artist_search_dialog.py
│   │   └── playlist_preview_dialog.py
│   └── widgets/
│       ├── __init__.py
│       ├── filter_panel.py           # Filter controls
│       ├── album_table_view.py       # Custom QTableView
│       └── status_bar.py
├── model/
│   ├── __init__.py
│   ├── artist.py                     # Artist dataclass
│   ├── album.py                      # Album dataclass
│   ├── track.py                      # Track dataclass
│   ├── album_edition.py              # AlbumEdition enum/class
│   ├── duplicate_group.py            # DuplicateGroup class
│   ├── filter_criteria.py            # FilterCriteria dataclass
│   ├── playlist_build_plan.py        # PlaylistBuildPlan class
│   └── playlist_preview.py           # PlaylistPreview class
├── services/
│   ├── __init__.py
│   ├── interfaces.py                 # Protocol/ABC definitions
│   ├── tidal_provider.py             # IMusicProvider implementation
│   ├── artist_service.py             # IArtistService implementation
│   ├── album_service.py              # IAlbumService implementation
│   ├── playlist_service.py           # IPlaylistService implementation
│   ├── duplicate_detector.py         # IDuplicateDetector implementation
│   ├── edition_classifier.py         # EditionClassifier
│   └── cache_service.py              # ICache implementation
├── tidal/
│   ├── __init__.py
│   ├── api_client.py                 # Low-level Tidal API client
│   └── auth.py                       # Authentication handling
├── filtering/
│   ├── __init__.py
│   └── filter_engine.py              # Applies FilterCriteria to albums
├── util/
│   ├── __init__.py
│   ├── logger.py                     # Logging setup
│   ├── config.py                     # Configuration management
│   └── session_state.py              # Session persistence
└── threading/
    ├── __init__.py
    ├── workers.py                    # QRunnable implementations
    └── thread_pool.py                # Thread pool management
```

---

## 2. Application Workflow

The application follows a strict linear pipeline with well-defined inputs and outputs:

**Stage 1: SEARCH ARTIST** → Input: string | Output: List[Artist]
**Stage 2: RETRIEVE DISCOGRAPHY** → Input: Artist | Output: List[Album]
**Stage 3: NORMALIZE METADATA** → Input: List[Album] | Output: List[Album] (normalized)
**Stage 4: DETECT DUPLICATES** → Input: List[Album] | Output: List[DuplicateGroup]
**Stage 5: APPLY FILTERS** → Input: List[Album], FilterCriteria | Output: List[Album] (filtered)
**Stage 6: USER SELECTS** → Input: Filtered albums, user checkboxes | Output: List[Album] (selected)
**Stage 7: BUILD PLAN** → Input: Selected albums, Artist | Output: PlaylistBuildPlan
**Stage 8: PREVIEW** → Input: PlaylistBuildPlan | Output: User confirmation
**Stage 9: CREATE PLAYLIST** → Input: Approved PlaylistBuildPlan | Output: Playlist (created)

Each stage has clearly defined input/output contracts that enable testing and composition.

---

## 3. Qt Model/View Architecture

### AlbumTableModel

Extends `QAbstractTableModel`. Represents core album data.

**Columns**:
1. Checkbox (editable bool) - for album selection
2. Release Year (int) - sortable
3. Album Title (str) - sortable
4. Type (AlbumType) - sortable
5. Edition (str) - e.g., "Deluxe", "Remaster"
6. Track Count (int) - sortable
7. Duration (str) - formatted "H:MM:SS"
8. Quality (str) - "Lossless", "Hi-Res", "320 kbps"
9. Duplicate Status (str) - "Original", "Variant", "Hidden"

**Key Methods**:
```python
def rowCount(self, parent: QModelIndex = QModelIndex()) -> int
def columnCount(self, parent: QModelIndex = QModelIndex()) -> int
def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any
def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool
def flags(self, index: QModelIndex) -> Qt.ItemFlags
def headerData(self, section: int, orientation: Qt.Orientation, role: int) -> Any

def set_albums(self, albums: List[Album]) -> None
def selected_indices(self) -> List[int]
def get_album(self, index: int) -> Album
```

**Signals**:
- `selection_changed(list)` - emitted when checkboxes change
- `data_changed()` - emitted when data updated

### AlbumFilterProxyModel

Extends `QSortFilterProxyModel`. Provides filtering and sorting.

**Responsibilities**:
- Apply FilterCriteria to filter albums
- Support sorting by any column
- Maintain selection across filter changes

**Key Methods**:
```python
def set_filter_criteria(self, criteria: FilterCriteria) -> None
def set_sort_column(self, column: int, order: Qt.SortOrder) -> None
def filter_accepts_row(self, source_row: int, source_parent: QModelIndex) -> bool
def get_selected_albums(self) -> List[Album]
```

### SelectionModel

Uses Qt's built-in `QItemSelectionModel`.

**Responsibilities**:
- Track which albums are checked
- Emit selection change signals
- Provide API to programmatically select/deselect

---

## 4. Domain Model Classes

All classes in `src/tidal_playlist_builder/model/`.

### Artist

```python
@dataclass
class Artist:
    """Represents a music artist."""
    id: str
    name: str
    image_url: Optional[str]
    album_count: int
    popularity: float  # 0.0-1.0
```

### Album

```python
@dataclass
class Album:
    """Represents a music album."""
    id: str
    title: str
    title_normalized: str  # For comparison
    artist: Artist
    release_date: date
    image_url: Optional[str]
    num_tracks: int
    duration: int  # seconds
    album_type: AlbumType
    edition: AlbumEdition
    quality: AudioQuality
    is_explicit: bool
    
    def total_duration_formatted(self) -> str:
        """Return formatted duration: 'H:MM:SS'."""
```

### AlbumType & AlbumEdition

```python
class AlbumType(Enum):
    ALBUM = "Album"
    EP = "EP"
    SINGLE = "Single"
    COMPILATION = "Compilation"
    REMIX = "Remix EP"

class AlbumEdition(Enum):
    ORIGINAL = "Original"
    DELUXE = "Deluxe"
    EXPANDED = "Expanded"
    REMASTER = "Remaster"
    REMASTER_DELUXE = "Remaster Deluxe"
    ANNIVERSARY = "Anniversary"
    JAPANESE = "Japanese"
    HI_RES = "Hi-Res"
    EXPLICIT = "Explicit"
    CLEAN = "Clean"
    LIVE = "Live"

class AudioQuality(Enum):
    LOSSY = "320 kbps"
    LOSSLESS = "Lossless"
    HI_RES = "Hi-Res"
```

### Track

```python
@dataclass
class Track:
    """Represents a track in an album."""
    id: str
    title: str
    duration: int  # seconds
    track_number: int
    artist: Artist
    is_explicit: bool
```

### DuplicateGroup

```python
@dataclass
class DuplicateGroup:
    """Groups duplicate editions of the same album."""
    id: str
    canonical_album: Album
    variant_albums: List[Album]
    duplicate_reasons: Dict[str, DuplicateReason]
    
    def all_albums(self) -> List[Album]:
        return [self.canonical_album] + self.variant_albums
```

### DuplicateReason

```python
class DuplicateReason(Enum):
    """Why an album is considered a duplicate."""
    SAME_TITLE_ARTIST = "Same title and artist"
    DELUXE_EDITION = "Deluxe edition"
    EXPANDED_EDITION = "Expanded edition"
    REMASTER = "Remastered"
    REMASTER_DELUXE = "Remaster + Deluxe"
    ANNIVERSARY = "Anniversary edition"
    JAPANESE_IMPORT = "Japanese import"
    LIVE_VERSION = "Live version"
    HI_RES = "Hi-Res version"
    DIFFERENT_REGION = "Different region"
    UNKNOWN = "Unknown variant"
```

### FilterCriteria

```python
@dataclass
class FilterCriteria:
    """User-defined filter for albums."""
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    album_types: List[AlbumType] = field(default_factory=list)
    edition_types: List[AlbumEdition] = field(default_factory=list)
    min_quality: AudioQuality = AudioQuality.LOSSY
    hide_duplicates: bool = False
    hide_explicit: bool = False
    
    def matches(self, album: Album) -> bool:
        """Check if album matches all criteria."""
```

### PlaylistBuildPlan

First-class object representing intention to create a playlist.

```python
@dataclass
class PlaylistBuildPlan:
    """Plan to create a playlist - reviewed before execution."""
    artist: Artist
    selected_albums: List[Album]
    selected_tracks: List[Track]
    playlist_name: str
    playlist_description: str
    duplicates_excluded: List[Album]
    total_duration: int  # seconds
    total_tracks: int
    created_at: datetime
    
    def total_duration_formatted(self) -> str:
        """Return 'H:MM:SS'."""
    
    def summary(self) -> str:
        """Human-readable summary."""
```

### PlaylistPreview

```python
@dataclass
class PlaylistPreview:
    """Display-ready preview of a playlist."""
    name: str
    description: str
    track_count: int
    total_duration: int
    unique_artists: int
    album_count: int
    duplicates_skipped: int
```

---

## 5. Service Interfaces (Python Protocols)

All defined in `src/tidal_playlist_builder/services/interfaces.py`.

### IMusicProvider

```python
from typing import Protocol

class IMusicProvider(Protocol):
    """Base protocol for music streaming services."""
    
    def authenticate(self, credentials: dict) -> None: ...
    def is_authenticated(self) -> bool: ...
    def search_artists(self, query: str, limit: int = 10) -> List[Artist]: ...
    def get_artist_albums(self, artist_id: str) -> List[Album]: ...
    def get_album_details(self, album_id: str) -> Album: ...
    def get_album_tracks(self, album_id: str) -> List[Track]: ...
    def create_playlist(self, name: str, description: str = "") -> str: ...
    def add_tracks_to_playlist(self, playlist_id: str, track_ids: List[str]) -> None: ...
```

### IArtistService

```python
class IArtistService(Protocol):
    """Service for artist operations."""
    
    def search_artists(self, query: str, limit: int = 10) -> List[Artist]: ...
    def get_artist_details(self, artist_id: str) -> Artist: ...
```

### IAlbumService

```python
class IAlbumService(Protocol):
    """Service for album operations."""
    
    def get_artist_albums(self, artist_id: str) -> List[Album]: ...
    def get_album_details(self, album_id: str) -> Album: ...
    def get_album_tracks(self, album_id: str) -> List[Track]: ...
```

### IPlaylistService

```python
class IPlaylistService(Protocol):
    """Service for playlist operations."""
    
    def create_build_plan(
        self,
        artist: Artist,
        selected_albums: List[Album],
        criteria: FilterCriteria
    ) -> PlaylistBuildPlan: ...
    
    def create_playlist(self, plan: PlaylistBuildPlan) -> str: ...
```

### IDuplicateDetector

```python
class IDuplicateDetector(Protocol):
    """Service for detecting duplicate editions."""
    
    def detect_duplicates(self, albums: List[Album]) -> List[DuplicateGroup]: ...
```

### ICache

```python
class ICache(Protocol):
    """Service for caching."""
    
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None: ...
    def invalidate(self, pattern: str) -> None: ...
    def clear(self) -> None: ...
```

---

## 6. Threading Model (Qt-Only)

### Worker Pattern

Uses `QRunnable` + `QThreadPool`:

```python
class FetchArtistWorker(QRunnable):
    """Worker to fetch artist data on background thread."""
    
    finished = pyqtSignal(Artist)
    error = pyqtSignal(str)
    
    def __init__(self, service: IArtistService, query: str):
        super().__init__()
        self.service = service
        self.query = query
    
    def run(self):
        try:
            artist = self.service.search_artists(self.query)[0]
            self.finished.emit(artist)
        except Exception as e:
            self.error.emit(str(e))
```

### Usage in MainWindow

```python
class MainWindow(QMainWindow):
    def search_artist(self, query: str):
        worker = FetchArtistWorker(self.artist_service, query)
        worker.finished.connect(self.on_artist_loaded)
        worker.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)
    
    @pyqtSlot(Artist)
    def on_artist_loaded(self, artist: Artist):
        self.load_albums(artist)
```

### Thread Pool Configuration

```python
QThreadPool.globalInstance().setMaxThreadCount(4)
```

### Signals/Slots Pattern

- Workers emit signals with results
- Main thread connects signals to slots
- All UI updates happen in main thread (safe)
- Long operations (API calls, duplicate detection) run in workers

---

## 7. Duplicate Detection System

### EditionClassifier

Responsible for parsing album metadata and classifying editions.

```python
class EditionClassifier:
    """Classifies album editions from titles and metadata."""
    
    def classify_albums(self, albums: List[Album]) -> List[Album]:
        """Return albums with edition and type fields populated."""
    
    def _detect_edition(self, title: str, metadata: dict) -> AlbumEdition:
        """Detect edition from title patterns."""
        # Rules for detecting: Deluxe, Remaster, Anniversary, etc.
```

**Edition Detection Rules**:
- Title contains "Deluxe" → DELUXE
- Title contains "Remaster" + "Deluxe" → REMASTER_DELUXE
- Title contains "Remaster" → REMASTER
- Title contains "Anniversary" → ANNIVERSARY
- Title contains "Japanese" or region = "JP" → JAPANESE
- Quality = HI_RES and not other editions → HI_RES
- is_explicit = True → EXPLICIT
- is_explicit = False and album typically explicit → CLEAN
- Compilation flag → COMPILATION
- Otherwise → ORIGINAL or UNKNOWN

### DuplicateDetector

Detects groups of duplicate/variant editions.

```python
class DuplicateDetector:
    """Detects duplicate editions of albums."""
    
    def detect_duplicates(self, albums: List[Album]) -> List[DuplicateGroup]:
        """Return groups of duplicate albums."""
        # Algorithm:
        # 1. Group by normalized title + primary artist
        # 2. For each group, select canonical (original, best quality)
        # 3. Classify variants (deluxe, remaster, etc.)
        # 4. Return DuplicateGroup objects
```

**Canonical Album Selection** (`CanonicalAlbumSelector`):

Priority (highest first):
1. ORIGINAL edition (not deluxe, not remaster, not special)
2. Earliest release date (original release comes first)
3. Best quality (HI_RES > LOSSLESS > LOSSY)
4. Explicit version (if both exist)

```python
class CanonicalAlbumSelector:
    def select_canonical(self, albums: List[Album]) -> Album:
        """Select the canonical album from variants."""
```

---

## 8. Caching Strategy (Memory + JSON Disk)

### Memory Cache (in-process)

LRU cache using Python's `functools.lru_cache` or custom implementation.

**Cached Items**:
- Artist search results (TTL: 1 hour)
- Artist album lists (TTL: 1 hour)
- Album details (TTL: 1 hour)
- Duplicate detection results (TTL: 30 minutes)

**Cache Keys** (hierarchical):
```
artist:{artist_id}
artist:{artist_id}:albums
album:{album_id}
search:{query}
duplicates:{artist_id}
```

### JSON Disk Cache

Persisted to user's config directory (`~/.config/tidal-playlist-builder/cache/`).

**Files**:
- `artists.json` - cached artist searches
- `albums.json` - cached album lists
- `duplicates.json` - cached duplicate groups

**TTL**: 7 days (checked on app startup)

**Implementation**:
```python
class CacheService:
    def get(self, key: str) -> Optional[Any]:
        # 1. Check memory cache
        # 2. If miss, check disk cache
        # 3. Return None if both miss
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        # 1. Store in memory cache
        # 2. Persist to disk (async)
    
    def invalidate(self, pattern: str) -> None:
        # Clear memory + disk entries matching pattern
```

---

## 9. Session Persistence

### WindowState

Saved to `~/.config/tidal-playlist-builder/session.json`:

```json
{
  "window": {
    "geometry": {"x": 100, "y": 100, "width": 1200, "height": 800},
    "is_maximized": false
  },
  "album_table": {
    "column_widths": [40, 80, 300, 100, 150, 100, 100, 100, 100],
    "sort_column": 1,
    "sort_order": "ascending"
  },
  "filters": {
    "min_year": null,
    "max_year": null,
    "album_types": [],
    "hide_duplicates": false
  },
  "last_artist": {
    "id": "artist123",
    "name": "The Beatles"
  },
  "selected_albums": ["album1", "album2"]
}
```

### SessionState Class

```python
class SessionState:
    def save(self) -> None:
        """Save window geometry, table state, filters, selection."""
    
    def load(self) -> Optional[dict]:
        """Load saved state, return None if file doesn't exist."""
    
    def restore_window(self, window: QMainWindow) -> None:
        """Restore window geometry and maximized state."""
    
    def restore_table_state(self, table_view: QTableView) -> None:
        """Restore column widths, sort order."""
    
    def restore_filters(self) -> FilterCriteria:
        """Restore filter settings."""
```

### Integration Points

```python
def closeEvent(self, event: QCloseEvent):
    """Called when window closes."""
    self.session_state.save()
    event.accept()

def showEvent(self, event: QShowEvent):
    """Called when window shows."""
    self.session_state.restore_window(self)
    self.session_state.restore_table_state(self.album_table_view)
```

---

## 10. Error Handling

### Error Categories

| Category | Examples | Handling |
|----------|----------|----------|
| Network | API timeout, connection error | Retry 3x, show user-friendly message |
| Auth | Invalid credentials, expired token | Show login dialog |
| Validation | Invalid input | Highlight field, show error |
| Business Logic | No duplicates found, track not found | Show informational message |
| System | Disk full, corrupt cache | Log, suggest action |

### Implementation

```python
class TidalAPIError(Exception):
    """Base Tidal API error."""

class TidalNetworkError(TidalAPIError):
    """Network-related error."""

class TidalAuthError(TidalAPIError):
    """Authentication error."""

def with_retry(func, max_attempts=3, backoff_seconds=1):
    """Decorator for retry logic with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return func()
        except TidalNetworkError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(backoff_seconds * (2 ** attempt))
```

---

## 11. Extension Points

### Multi-Provider Support

All providers implement `IMusicProvider`:

```python
from typing import Protocol

class IMusicProvider(Protocol):
    """Any streaming service can implement this."""
    name: str
    
    def search_artists(self, query: str) -> List[Artist]: ...
    def get_artist_albums(self, artist_id: str) -> List[Album]: ...
    def create_playlist(self, name: str) -> str: ...
    def add_tracks_to_playlist(self, playlist_id: str, track_ids: List[str]) -> None: ...
```

### Factory Pattern

```python
class ProviderFactory:
    @staticmethod
    def create_provider(provider_name: str) -> IMusicProvider:
        if provider_name == "tidal":
            return TidalProvider()
        elif provider_name == "spotify":
            return SpotifyProvider()
        elif provider_name == "qobuz":
            return QobuzProvider()
        raise ValueError(f"Unknown provider: {provider_name}")
```

### Custom Duplicate Detection Strategy

```python
class IDuplicateDetectionStrategy(Protocol):
    def detect_duplicates(self, albums: List[Album]) -> List[DuplicateGroup]: ...

class AdvancedDuplicateDetector(IDuplicateDetectionStrategy):
    """Future: ML-based similarity detection."""
    def detect_duplicates(self, albums: List[Album]) -> List[DuplicateGroup]:
        # ML-based approach
        pass
```

### Custom Filters

```python
class IFilterStrategy(Protocol):
    def apply(self, albums: List[Album], criteria: dict) -> List[Album]: ...

class DecadeFilter(IFilterStrategy):
    def apply(self, albums: List[Album], decade: int) -> List[Album]:
        year_range = (decade, decade + 9)
        return [a for a in albums if year_range[0] <= a.release_date.year <= year_range[1]]
```

---

## 12. Testing Strategy

### Unit Tests

Focus on business logic with mocked dependencies:

```
tests/
├── unit/
│   ├── test_duplicate_detector.py
│   ├── test_filter_engine.py
│   ├── test_edition_classifier.py
│   ├── test_playlist_service.py
│   └── test_cache_service.py
```

**Example**:
```python
def test_duplicate_detection():
    albums = [
        Album(title="The White Album", artist=beatles, edition=ORIGINAL),
        Album(title="The White Album (Deluxe)", artist=beatles, edition=DELUXE),
        Album(title="The White Album (Remaster)", artist=beatles, edition=REMASTER),
    ]
    
    groups = detector.detect_duplicates(albums)
    
    assert len(groups) == 1
    assert groups[0].canonical_album.edition == ORIGINAL
    assert len(groups[0].variant_albums) == 2
```

### Integration Tests

Test service layer with real (or mocked) Tidal API:

```
tests/
├── integration/
│   ├── test_artist_search_workflow.py
│   ├── test_album_retrieval_workflow.py
│   └── test_playlist_creation_workflow.py
```

### GUI Tests (pytest-qt)

Test Qt components:

```python
def test_album_table_model_selection(qtbot):
    model = AlbumTableModel(albums)
    table = QTableView()
    table.setModel(model)
    
    # Simulate checkbox check
    index = model.index(0, 0)  # First album, checkbox column
    model.setData(index, True, Qt.EditRole)
    
    selected = model.selected_indices()
    assert 0 in selected
```

---

## 13. Performance Targets

| Operation | Target |
|-----------|--------|
| Artist search (API + cache) | < 500ms |
| Load 200 albums to table | < 1s |
| Duplicate detection (500 albums) | < 2s |
| Filter application | < 100ms |
| Playlist creation | < 500ms |
| Window launch | < 2s |
| Memory (idle) | < 150MB |
| Memory (200 albums loaded) | < 300MB |

---

## 14. Future Extensions

### Phase 1 (Current)
- Tidal support only
- Basic duplicate detection
- Manual filtering
- Local playlist management

### Phase 2
- Spotify provider integration
- OAuth authentication
- Cross-provider search

### Phase 3
- Qobuz provider integration
- Advanced duplicate detection (ML-based)
- Filter presets

### Phase 4
- Recommendations engine
- Library sync
- Collaboration features

---

## Summary

This architecture provides a production-ready foundation for the Tidal Playlist Builder. Key design principles:

1. **Clear Workflow**: 9-stage pipeline with defined inputs/outputs at each stage
2. **Qt Native**: Uses Qt threading, Model/View, signals/slots throughout
3. **Extensible**: Provider abstraction, Protocol-based interfaces
4. **Testable**: Separated concerns enable unit/integration testing
5. **Persistent**: Session state restored on restart
6. **Responsive**: All long operations run in background threads
7. **Future-Proof**: Duplicate detection, filtering, and providers are pluggable

Implementation can proceed directly from this architecture specification.

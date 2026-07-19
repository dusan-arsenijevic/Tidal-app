"""Workflow orchestration for GUI interactions."""

import logging

from PySide6.QtCore import QObject, Signal

from tidal_playlist_builder.exceptions import DuplicateDetectionError, ValidationError
from tidal_playlist_builder.gui import MainWindow
from tidal_playlist_builder.gui.models import AlbumFilterProxyModel, AlbumTableModel
from tidal_playlist_builder.model import (
    Album,
    Artist,
    DuplicateGroup,
    PlaylistBuildPlan,
)
from tidal_playlist_builder.services import PlaylistBuildPlanBuilder
from tidal_playlist_builder.threading import WorkerThreadPool
from tidal_playlist_builder.threading.workers import (
    AlbumLoadingWorker,
    ArtistSearchWorker,
    DuplicateDetectionWorker,
    PlaylistCreationWorker,
)
from tidal_playlist_builder.tidal import (
    CancellationToken,
    PlaylistCreationProgress,
    TidalProvider,
)

logger = logging.getLogger(__name__)


class WorkflowController(QObject):
    """Coordinates end-to-end user workflow using GUI + workers + provider."""

    operationFailed = Signal(str)
    playlistProgress = Signal(str)
    playlistCreated = Signal(str)
    playlistFailed = Signal(str)

    def __init__(
        self,
        main_window: MainWindow,
        worker_pool: WorkerThreadPool,
        provider: TidalProvider,
        playlist_builder: PlaylistBuildPlanBuilder,
        album_table_model: AlbumTableModel,
        album_proxy_model: AlbumFilterProxyModel,
    ) -> None:
        super().__init__(main_window)
        self._window = main_window
        self._worker_pool = worker_pool
        self._provider = provider
        self._playlist_builder = playlist_builder
        self._table_model = album_table_model
        self._proxy_model = album_proxy_model

        self._current_artist: Artist | None = None
        self._current_albums: list[Album] = []
        self._current_duplicate_groups: list[DuplicateGroup] = []
        self._active_operations = 0
        self._active_workers: set[object] = set()
        self._playlist_cancel_token: CancellationToken | None = None
        self._playlist_creation_running = False

        self._window.searchRequested.connect(self._on_search_requested)
        self._window.refreshRequested.connect(self._on_refresh_requested)
        self._window.createPlaylistRequested.connect(
            self.create_playlist_from_selection
        )
        self._window.albumSelectionChanged.connect(self._on_album_selection_changed)
        self._window.set_search_enabled(True)
        self._refresh_playlist_preview()

    def create_playlist_from_selection(self) -> None:
        """Build and create playlist for currently selected albums."""
        if self._playlist_creation_running:
            self._window.set_status("Playlist creation already running")
            return
        if self._current_artist is None:
            self._window.set_status("No artist loaded")
            return

        selected_ids = set(self._table_model.checked_album_ids())
        selected_albums = [a for a in self._current_albums if a.id in selected_ids]
        if not selected_albums:
            self._window.set_status("No albums selected")
            return

        try:
            plan = self._playlist_builder.build(self._current_artist, selected_albums)
        except ValidationError as error:
            self._handle_error(str(error))
            return

        self._playlist_cancel_token = CancellationToken()
        self._playlist_creation_running = True
        worker = self._worker_pool.start_playlist_creation(
            lambda playlist_plan: self._provider.create_playlist(
                playlist_plan,
                progress_callback=self._on_playlist_progress,
                cancellation_token=self._playlist_cancel_token,
            ),
            plan,
        )
        self._connect_playlist_creation_worker(worker, plan)

    def cancel_playlist_creation(self) -> None:
        """Cancel in-flight playlist creation operation."""
        token = self._playlist_cancel_token
        if token is not None:
            logger.info("Playlist cancellation requested")
            token.cancel()
            self._window.set_status("Cancelling playlist creation...")

    def _on_search_requested(self, query: str) -> None:
        worker = self._worker_pool.start_artist_search(
            self._provider.search_artists, query, 10
        )
        self._connect_artist_search_worker(worker)

    def _on_refresh_requested(self) -> None:
        artist = self._current_artist
        if artist is None:
            self._window.set_status("No artist selected")
            return
        worker = self._worker_pool.start_album_loading(
            self._load_artist_discography, artist.id
        )
        self._connect_album_loading_worker(worker, artist)

    def _connect_artist_search_worker(self, worker: ArtistSearchWorker) -> None:
        self._retain_worker(worker)
        worker.signals.started.connect(
            lambda: self._start_operation("Searching artist...")
        )
        worker.signals.error.connect(self._handle_error)
        worker.signals.result.connect(self._on_artist_search_result)
        worker.signals.finished.connect(self._finish_operation)

    def _connect_album_loading_worker(
        self, worker: AlbumLoadingWorker, artist: Artist
    ) -> None:
        self._retain_worker(worker)
        worker.signals.started.connect(
            lambda: self._start_operation("Loading discography...")
        )
        worker.signals.error.connect(self._handle_error)
        worker.signals.result.connect(
            lambda albums: self._on_albums_loaded(artist, albums)
        )
        worker.signals.finished.connect(self._finish_operation)

    def _connect_duplicate_detection_worker(
        self, worker: DuplicateDetectionWorker
    ) -> None:
        self._retain_worker(worker)
        worker.signals.started.connect(
            lambda: self._start_operation("Detecting duplicate editions...")
        )
        worker.signals.error.connect(self._handle_error)
        worker.signals.result.connect(self._on_duplicate_groups_detected)
        worker.signals.finished.connect(self._finish_operation)

    def _connect_playlist_creation_worker(
        self, worker: PlaylistCreationWorker, plan: PlaylistBuildPlan
    ) -> None:
        self._retain_worker(worker)
        worker.signals.started.connect(
            lambda: self._start_operation("Creating playlist...")
        )
        worker.signals.error.connect(self._handle_error)
        worker.signals.result.connect(
            lambda playlist_id: self._on_playlist_created(playlist_id, plan)
        )
        worker.signals.finished.connect(self._finish_operation)

    def _on_artist_search_result(self, artists: object) -> None:
        if not isinstance(artists, list) or not artists:
            self._current_artist = None
            self._current_albums = []
            self._current_duplicate_groups = []
            self._table_model.set_albums([])
            self._proxy_model.set_duplicate_groups([])
            self._refresh_playlist_preview()
            self._window.set_status("No artists found")
            return
        first_artist = artists[0]
        if not isinstance(first_artist, Artist):
            self._handle_error("Artist search returned invalid data")
            return
        self._current_artist = first_artist
        worker = self._worker_pool.start_album_loading(
            self._load_artist_discography,
            first_artist.id,
        )
        self._connect_album_loading_worker(worker, first_artist)

    def _on_albums_loaded(self, artist: Artist, albums: object) -> None:
        if not isinstance(albums, list) or any(
            not isinstance(a, Album) for a in albums
        ):
            self._handle_error("Album loading returned invalid data")
            return
        typed_albums = list(albums)
        self._current_artist = artist
        self._current_albums = typed_albums
        self._table_model.set_albums(typed_albums)
        self._refresh_playlist_preview()
        worker = self._worker_pool.start_duplicate_detection(
            self._detect_duplicates,
            typed_albums,
        )
        self._connect_duplicate_detection_worker(worker)

    def _on_duplicate_groups_detected(self, groups: object) -> None:
        if not isinstance(groups, list) or any(
            not isinstance(group, DuplicateGroup) for group in groups
        ):
            self._handle_error("Duplicate detection returned invalid data")
            return
        typed_groups = list(groups)
        self._current_duplicate_groups = typed_groups
        self._table_model.set_duplicate_groups(typed_groups)
        self._proxy_model.set_duplicate_groups(typed_groups)
        self._refresh_playlist_preview()
        if self._current_artist is not None:
            self._window.set_status(
                f"Loaded {len(self._current_albums)} albums for {self._current_artist.name}"
            )

    def _on_playlist_progress(self, progress: PlaylistCreationProgress) -> None:
        message = f"{progress.phase}: {progress.completed}/{progress.total}"
        self.playlistProgress.emit(message)
        self._window.set_status(message)

    def _on_playlist_created(self, playlist_id: str, plan: PlaylistBuildPlan) -> None:
        self._playlist_cancel_token = None
        self._playlist_creation_running = False
        self.playlistCreated.emit(playlist_id)
        self._window.set_status(
            f"Playlist created ({playlist_id}) with {plan.track_count} tracks"
        )

    def _start_operation(self, status: str) -> None:
        logger.debug("Workflow operation started status=%s", status)
        self._active_operations += 1
        self._window.set_busy(True)
        self._window.set_status(status)

    def _finish_operation(self) -> None:
        logger.debug("Workflow operation finished")
        self._active_operations = max(self._active_operations - 1, 0)
        self._window.set_busy(self._active_operations > 0)

    def _handle_error(self, message: str) -> None:
        logger.warning("Workflow error: %s", message)
        if self._playlist_creation_running:
            self._playlist_creation_running = False
            self._playlist_cancel_token = None
            self.playlistFailed.emit(message)
        self.operationFailed.emit(message)
        self._window.set_status(f"Error: {message}")

    def _detect_duplicates(self, albums: list[Album]) -> list[DuplicateGroup]:
        groups_by_key: dict[tuple[str, str], list[Album]] = {}
        for album in albums:
            key = (album.artist.id, album.title.strip().lower())
            groups_by_key.setdefault(key, []).append(album)

        duplicate_groups: list[DuplicateGroup] = []
        for candidates in groups_by_key.values():
            if len(candidates) < 2:
                continue
            ordered = sorted(candidates, key=lambda a: (a.release_year, a.id))
            canonical = ordered[0]
            variants = frozenset(album.id for album in ordered[1:])
            duplicate_groups.append(
                DuplicateGroup(
                    canonical_album_id=canonical.id,
                    variant_album_ids=variants,
                )
            )
        if not all(group.variant_album_ids for group in duplicate_groups):
            raise DuplicateDetectionError("Invalid duplicate groups produced")
        return duplicate_groups

    def _load_artist_discography(self, artist_id: str) -> list[Album]:
        albums = self._provider.get_artist_albums(artist_id)
        enriched: list[Album] = []
        for album in albums:
            tracks = self._provider.get_album_tracks(album.id)
            enriched.append(
                Album(
                    id=album.id,
                    title=album.title,
                    artist=album.artist,
                    release_year=album.release_year,
                    album_type=album.album_type,
                    edition=album.edition,
                    quality=album.quality,
                    is_explicit=album.is_explicit,
                    tracks=tuple(tracks),
                )
            )
        return enriched

    def _retain_worker(self, worker: object) -> None:
        self._active_workers.add(worker)
        signals = getattr(worker, "signals", None)
        if signals is None:
            return
        finished_signal = getattr(signals, "finished", None)
        if finished_signal is None:
            return
        finished_signal.connect(lambda: self._active_workers.discard(worker))

    def _on_album_selection_changed(self, _selected_ids: list[str]) -> None:
        self._refresh_playlist_preview()

    def _refresh_playlist_preview(self) -> None:
        artist = self._current_artist
        if artist is None:
            self._window.set_playlist_preview(
                playlist_name="-",
                album_count=0,
                track_count=0,
                estimated_duration="-",
                duplicate_summary="-",
                validation_warnings=["No artist loaded"],
            )
            return

        selected_ids = set(self._table_model.checked_album_ids())
        selected_albums = [a for a in self._current_albums if a.id in selected_ids]
        playlist_name = f"{artist.name} Playlist"
        if not selected_albums:
            self._window.set_playlist_preview(
                playlist_name=playlist_name,
                album_count=0,
                track_count=0,
                estimated_duration="0:00",
                duplicate_summary="0 duplicate tracks skipped",
                validation_warnings=["Select at least one album"],
            )
            return

        try:
            plan = self._playlist_builder.build(artist, selected_albums)
        except ValidationError as error:
            self._window.set_playlist_preview(
                playlist_name=playlist_name,
                album_count=len(selected_albums),
                track_count=0,
                estimated_duration="0:00",
                duplicate_summary="0 duplicate tracks skipped",
                validation_warnings=[str(error)],
            )
            return

        self._window.set_playlist_preview(
            playlist_name=playlist_name,
            album_count=len(plan.selected_albums),
            track_count=plan.track_count,
            estimated_duration=self._format_duration(plan.duration_seconds),
            duplicate_summary=f"{plan.duplicates_skipped} duplicate tracks skipped",
            validation_warnings=[],
        )

    def _format_duration(self, seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining = seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{remaining:02d}"
        return f"{minutes}:{remaining:02d}"

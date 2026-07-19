"""Thread pool coordinator for background workers."""

from collections.abc import Callable
from typing import TypeVar

from PySide6.QtCore import QThreadPool

from tidal_playlist_builder.exceptions import ValidationError
from tidal_playlist_builder.model import (
    Album,
    Artist,
    DuplicateGroup,
    PlaylistBuildPlan,
)

from .workers import (
    AlbumLoadingWorker,
    ArtistSearchWorker,
    BaseWorker,
    DuplicateDetectionWorker,
    PlaylistCreationWorker,
)

WorkerT = TypeVar("WorkerT", bound=BaseWorker[object])


class WorkerThreadPool:
    """Wrapper around QThreadPool to start app workers consistently."""

    def __init__(
        self, thread_pool: QThreadPool | None = None, max_threads: int = 4
    ) -> None:
        if max_threads <= 0:
            raise ValidationError("max_threads must be positive")
        self._pool = thread_pool or QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(max_threads)

    @property
    def thread_pool(self) -> QThreadPool:
        return self._pool

    def start_worker(self, worker: WorkerT) -> WorkerT:
        self._pool.start(worker)
        return worker

    def start_artist_search(
        self,
        search_operation: Callable[[str, int], list[Artist]],
        query: str,
        limit: int = 10,
    ) -> ArtistSearchWorker:
        worker = ArtistSearchWorker(search_operation, query, limit)
        return self.start_worker(worker)

    def start_album_loading(
        self,
        load_operation: Callable[[str], list[Album]],
        artist_id: str,
    ) -> AlbumLoadingWorker:
        worker = AlbumLoadingWorker(load_operation, artist_id)
        return self.start_worker(worker)

    def start_duplicate_detection(
        self,
        detect_operation: Callable[[list[Album]], list[DuplicateGroup]],
        albums: list[Album],
    ) -> DuplicateDetectionWorker:
        worker = DuplicateDetectionWorker(detect_operation, albums)
        return self.start_worker(worker)

    def start_playlist_creation(
        self,
        create_operation: Callable[[PlaylistBuildPlan], str],
        plan: PlaylistBuildPlan,
    ) -> PlaylistCreationWorker:
        worker = PlaylistCreationWorker(create_operation, plan)
        return self.start_worker(worker)

"""Background worker framework built on QRunnable and signals."""

from collections.abc import Callable
from typing import Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from tidal_playlist_builder.exceptions import ValidationError
from tidal_playlist_builder.model import (
    Album,
    Artist,
    DuplicateGroup,
    PlaylistBuildPlan,
)

ResultT = TypeVar("ResultT", covariant=True)


class WorkerSignals(QObject):
    """Standard signal set for background workers."""

    started = Signal()
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class BaseWorker(QRunnable, Generic[ResultT]):
    """Reusable QRunnable that delegates work to an injected callable."""

    def __init__(self, operation: Callable[[], ResultT]) -> None:
        super().__init__()
        if not callable(operation):
            raise TypeError("operation must be callable")
        self.signals = WorkerSignals()
        self._operation = operation
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        self.signals.started.emit()
        try:
            result = self._operation()
            self.signals.result.emit(result)
        except Exception as error:  # pragma: no cover - Qt entrypoint safety
            self.signals.error.emit(str(error))
        finally:
            self.signals.finished.emit()


class ArtistSearchWorker(BaseWorker[list[Artist]]):
    """Worker for artist search operations."""

    def __init__(
        self,
        search_operation: Callable[[str, int], list[Artist]],
        query: str,
        limit: int = 10,
    ) -> None:
        if not query.strip():
            raise ValidationError("query cannot be empty")
        if limit <= 0:
            raise ValidationError("limit must be positive")
        super().__init__(lambda: search_operation(query, limit))


class AlbumLoadingWorker(BaseWorker[list[Album]]):
    """Worker for loading an artist's albums."""

    def __init__(
        self,
        load_operation: Callable[[str], list[Album]],
        artist_id: str,
    ) -> None:
        if not artist_id.strip():
            raise ValidationError("artist_id cannot be empty")
        super().__init__(lambda: load_operation(artist_id))


class DuplicateDetectionWorker(BaseWorker[list[DuplicateGroup]]):
    """Worker for duplicate detection operations."""

    def __init__(
        self,
        detect_operation: Callable[[list[Album]], list[DuplicateGroup]],
        albums: list[Album],
    ) -> None:
        super().__init__(lambda: detect_operation(albums))


class PlaylistCreationWorker(BaseWorker[str]):
    """Worker for playlist creation operations."""

    def __init__(
        self,
        create_operation: Callable[[PlaylistBuildPlan], str],
        plan: PlaylistBuildPlan,
    ) -> None:
        super().__init__(lambda: create_operation(plan))

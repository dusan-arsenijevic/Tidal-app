"""Tests for background worker framework."""

import time

from PySide6.QtCore import QThreadPool

from tidal_playlist_builder.exceptions import ValidationError
from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    DuplicateGroup,
    PlaylistBuildPlan,
    Track,
)
from tidal_playlist_builder.threading import WorkerThreadPool
from tidal_playlist_builder.threading.workers import (
    AlbumLoadingWorker,
    ArtistSearchWorker,
    BaseWorker,
    DuplicateDetectionWorker,
    PlaylistCreationWorker,
)


def _artist() -> Artist:
    return Artist(id="artist-1", name="Massive Attack")


def _albums() -> list[Album]:
    artist = _artist()
    return [
        Album(
            id="alb-1",
            title="Blue Lines",
            artist=artist,
            release_year=1991,
            album_type=AlbumType.ALBUM,
            edition=AlbumEdition.ORIGINAL,
            quality=AudioQuality.LOSSLESS,
            is_explicit=False,
            tracks=(
                Track(id="t1", title="Safe from Harm", duration_seconds=200),
                Track(id="t2", title="Unfinished Sympathy", duration_seconds=300),
            ),
        )
    ]


def _plan() -> PlaylistBuildPlan:
    albums = _albums()
    tracks = albums[0].tracks
    return PlaylistBuildPlan(
        artist=_artist(),
        selected_albums=tuple(albums),
        selected_tracks=tracks,
        duplicates_skipped=0,
        duration_seconds=sum(track.duration_seconds for track in tracks),
        track_count=len(tracks),
    )


def test_base_worker_emits_result_and_finished(qtbot) -> None:
    worker = BaseWorker(lambda: 42)
    results: list[object] = []
    worker.signals.result.connect(results.append)
    with qtbot.waitSignal(worker.signals.finished, timeout=1000):
        worker.run()
    assert results == [42]


def test_base_worker_emits_error(qtbot) -> None:
    worker = BaseWorker(lambda: (_ for _ in ()).throw(ValueError("boom")))
    errors: list[str] = []
    worker.signals.error.connect(errors.append)
    with qtbot.waitSignal(worker.signals.finished, timeout=1000):
        worker.run()
    assert errors == ["boom"]


def test_artist_search_worker_validation() -> None:
    try:
        ArtistSearchWorker(lambda _q, _l: [], "   ")
        assert False, "Expected ValidationError"
    except ValidationError as error:
        assert "query cannot be empty" in str(error)

    try:
        ArtistSearchWorker(lambda _q, _l: [], "x", 0)
        assert False, "Expected ValidationError"
    except ValidationError as error:
        assert "limit must be positive" in str(error)


def test_album_loading_worker_validation() -> None:
    try:
        AlbumLoadingWorker(lambda _artist_id: [], " ")
        assert False, "Expected ValidationError"
    except ValidationError as error:
        assert "artist_id cannot be empty" in str(error)


def test_worker_thread_pool_validates_max_threads() -> None:
    try:
        WorkerThreadPool(max_threads=0)
        assert False, "Expected ValidationError"
    except ValidationError as error:
        assert "max_threads must be positive" in str(error)


def test_thread_pool_starts_artist_search_worker(qtbot) -> None:
    pool = QThreadPool()
    manager = WorkerThreadPool(thread_pool=pool, max_threads=1)
    results: list[object] = []

    def operation(query: str, limit: int) -> list[Artist]:
        assert query == "massive"
        assert limit == 5
        time.sleep(0.05)
        return [Artist(id="a", name="Massive Attack")]

    worker = manager.start_artist_search(operation, "massive", 5)
    worker.signals.result.connect(results.append)
    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        pass
    assert isinstance(worker, ArtistSearchWorker)
    assert len(results) == 1


def test_thread_pool_starts_album_loading_worker(qtbot) -> None:
    pool = QThreadPool()
    manager = WorkerThreadPool(thread_pool=pool, max_threads=1)
    results: list[object] = []

    def load(_artist_id: str) -> list[Album]:
        time.sleep(0.05)
        return _albums()

    worker = manager.start_album_loading(load, "artist-1")
    worker.signals.result.connect(results.append)
    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        pass
    assert isinstance(worker, AlbumLoadingWorker)
    assert len(results) == 1


def test_thread_pool_starts_duplicate_detection_worker(qtbot) -> None:
    pool = QThreadPool()
    manager = WorkerThreadPool(thread_pool=pool, max_threads=1)
    results: list[object] = []

    def detect(_albums_input: list[Album]) -> list[DuplicateGroup]:
        time.sleep(0.05)
        return [
            DuplicateGroup(canonical_album_id="alb-1", variant_album_ids=frozenset())
        ]

    worker = manager.start_duplicate_detection(detect, _albums())
    worker.signals.result.connect(results.append)
    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        pass
    assert isinstance(worker, DuplicateDetectionWorker)
    assert len(results) == 1


def test_thread_pool_starts_playlist_creation_worker(qtbot) -> None:
    pool = QThreadPool()
    manager = WorkerThreadPool(thread_pool=pool, max_threads=1)
    results: list[object] = []

    def create(_plan_input: PlaylistBuildPlan) -> str:
        time.sleep(0.05)
        return "playlist-1"

    worker = manager.start_playlist_creation(create, _plan())
    worker.signals.result.connect(results.append)
    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        pass
    assert isinstance(worker, PlaylistCreationWorker)
    assert results == ["playlist-1"]


def test_start_worker_uses_given_worker(qtbot) -> None:
    pool = QThreadPool()
    manager = WorkerThreadPool(thread_pool=pool, max_threads=1)
    worker = BaseWorker(lambda: "ok")
    results: list[object] = []
    worker.signals.result.connect(results.append)

    returned = manager.start_worker(worker)
    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        pass
    assert returned is worker
    assert results == ["ok"]

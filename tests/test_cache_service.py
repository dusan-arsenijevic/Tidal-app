"""Tests for two-level cache behavior."""

from pathlib import Path
import threading

from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
)
from tidal_playlist_builder.services.cache_service import CacheService


def _sample_album() -> Album:
    return Album(
        id="album:1",
        title="Mezzanine",
        artist=Artist(id="artist:1", name="Massive Attack"),
        release_year=1998,
        album_type=AlbumType.ALBUM,
        edition=AlbumEdition.ORIGINAL,
        quality=AudioQuality.LOSSLESS,
        is_explicit=False,
    )


def test_memory_hit(tmp_path: Path) -> None:
    cache = CacheService(cache_directory=tmp_path, max_memory_entries=10)
    cache.set("metadata:key", 123)

    assert cache.get("metadata:key") == 123


def test_disk_hit_promotes_to_memory(tmp_path: Path) -> None:
    cache_directory = tmp_path / "cache"
    writer = CacheService(cache_directory=cache_directory)
    writer.set("artist_search:massive:10", [_sample_album().artist])

    reader = CacheService(cache_directory=cache_directory)
    value = reader.get("artist_search:massive:10")
    assert value is not None

    for file_path in cache_directory.rglob("*.json"):
        file_path.unlink()
    promoted = reader.get("artist_search:massive:10")
    assert promoted is not None


def test_expired_item_is_ignored(tmp_path: Path) -> None:
    cache = CacheService(cache_directory=tmp_path)
    cache.set("metadata:expires", "value", ttl_seconds=0)

    assert cache.get("metadata:expires") is None


def test_corrupt_file_is_deleted_and_treated_as_miss(tmp_path: Path) -> None:
    writer = CacheService(cache_directory=tmp_path)
    writer.set("artist_search:corrupt:1", [_sample_album().artist])

    file_path = next(tmp_path.rglob("*.json"))
    file_path.write_text("{ bad json", encoding="utf-8")

    reader = CacheService(cache_directory=tmp_path)
    assert reader.get("artist_search:corrupt:1") is None
    assert not file_path.exists()


def test_missing_file_is_cache_miss(tmp_path: Path) -> None:
    cache = CacheService(cache_directory=tmp_path)

    assert cache.get("metadata:missing") is None


def test_concurrent_access_is_safe(tmp_path: Path) -> None:
    cache = CacheService(cache_directory=tmp_path, max_memory_entries=50)
    errors: list[Exception] = []

    def worker(thread_id: int) -> None:
        try:
            for index in range(100):
                key = f"artist_search:thread:{index % 5}"
                cache.set(key, f"value-{thread_id}-{index}")
                cache.get(key)
        except Exception as error:  # pragma: no cover - diagnostic branch
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert cache.get("artist_search:thread:1") is not None


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    cache = CacheService(cache_directory=tmp_path)
    cache.set("album_tracks:1", [_sample_album()])

    assert list(tmp_path.rglob("*.tmp")) == []
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_prefix_invalidation_removes_memory_and_disk_entries(tmp_path: Path) -> None:
    cache = CacheService(cache_directory=tmp_path)
    cache.set("artist_search:massive:10", [_sample_album().artist])
    cache.set("album_tracks:album-1", [])
    cache.set("playlist:created:123", True)

    cache.invalidate("artist_search:")

    assert cache.get("artist_search:massive:10") is None
    assert cache.get("album_tracks:album-1") == []
    assert cache.get("playlist:created:123") is True


def test_cache_layout_uses_category_directories(tmp_path: Path) -> None:
    cache = CacheService(cache_directory=tmp_path)
    cache.set("artist_search:massive:10", [_sample_album().artist])
    cache.set("album_tracks:album-1", [])
    cache.set("playlist:created:123", True)
    cache.set("other:key", 1)

    assert (tmp_path / "artist").exists()
    assert (tmp_path / "album").exists()
    assert (tmp_path / "playlist").exists()
    assert (tmp_path / "metadata").exists()

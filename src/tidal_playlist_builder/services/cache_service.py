"""Two-level cache service with in-memory and optional disk backend."""

from collections import OrderedDict
from dataclasses import dataclass
import logging
from pathlib import Path
import threading
from time import time

from .json_cache_backend import JsonCacheBackend

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _CacheItem:
    value: object
    expires_at: float | None


class CacheService:
    """Cache service with memory L1 and JSON disk L2."""

    def __init__(
        self,
        *,
        cache_directory: Path | str | None = "cache",
        max_memory_entries: int = 512,
        default_ttl_seconds: int | None = None,
        disk_backend: JsonCacheBackend | None = None,
    ) -> None:
        if max_memory_entries <= 0:
            raise ValueError("max_memory_entries must be positive")
        if default_ttl_seconds is not None and default_ttl_seconds < 0:
            raise ValueError("default_ttl_seconds must be >= 0")

        self._memory: OrderedDict[str, _CacheItem] = OrderedDict()
        self._max_memory_entries = max_memory_entries
        self._default_ttl_seconds = default_ttl_seconds
        self._lock = threading.RLock()
        self._disk = disk_backend
        if self._disk is None and cache_directory is not None:
            self._disk = JsonCacheBackend(cache_directory)

    def get(self, key: str) -> object | None:
        with self._lock:
            memory_item = self._memory.get(key)
            if memory_item is not None:
                if self._is_expired(memory_item.expires_at):
                    del self._memory[key]
                    logger.debug("Cache expired key=%s level=memory", key)
                else:
                    self._memory.move_to_end(key)
                    logger.debug("Cache hit key=%s level=memory", key)
                    return memory_item.value

            if self._disk is None:
                logger.debug("Cache miss key=%s", key)
                return None

            status, value, disk_expires_at = self._disk.get_with_status(key)
            if status == "hit":
                logger.debug("Cache hit key=%s level=disk", key)
                assert value is not None
                self._set_memory(key, value, expires_at=disk_expires_at)
                return value
            if status == "expired":
                logger.debug("Cache expired key=%s level=disk", key)
            elif status == "corrupt":
                logger.warning("Cache corrupt key=%s level=disk", key)
            else:
                logger.debug("Cache miss key=%s", key)
            return None

    def set(self, key: str, value: object, ttl_seconds: int | None = None) -> None:
        with self._lock:
            ttl_value = (
                self._default_ttl_seconds if ttl_seconds is None else ttl_seconds
            )
            expires_at = None if ttl_value is None else time() + ttl_value
            self._set_memory(key, value, expires_at=expires_at)
            if self._disk is not None:
                self._disk.set(key, value, expires_at)

    def invalidate(self, prefix: str) -> None:
        with self._lock:
            keys = [key for key in self._memory if key.startswith(prefix)]
            for key in keys:
                del self._memory[key]
            if self._disk is not None:
                self._disk.invalidate(prefix)

    def clear(self) -> None:
        with self._lock:
            self._memory.clear()
            if self._disk is not None:
                self._disk.clear()

    def _set_memory(self, key: str, value: object, *, expires_at: float | None) -> None:
        self._memory[key] = _CacheItem(value=value, expires_at=expires_at)
        self._memory.move_to_end(key)
        while len(self._memory) > self._max_memory_entries:
            evicted_key, _evicted_value = self._memory.popitem(last=False)
            logger.debug("Cache evicted key=%s level=memory", evicted_key)

    def _is_expired(self, expires_at: float | None) -> bool:
        return expires_at is not None and expires_at <= time()

"""Simple cache service."""

from dataclasses import dataclass
from time import monotonic
from typing import Any


@dataclass(slots=True)
class _CacheItem:
    value: Any
    expires_at: float | None


class CacheService:
    """In-memory cache with optional TTL support."""

    def __init__(self) -> None:
        self._data: dict[str, _CacheItem] = {}

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None

        if item.expires_at is not None and item.expires_at <= monotonic():
            del self._data[key]
            return None
        return item.value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires_at = None if ttl_seconds is None else monotonic() + ttl_seconds
        self._data[key] = _CacheItem(value=value, expires_at=expires_at)

    def invalidate(self, prefix: str) -> None:
        keys = [key for key in self._data if key.startswith(prefix)]
        for key in keys:
            del self._data[key]

    def clear(self) -> None:
        self._data.clear()

"""Artist repository."""

from collections.abc import Callable

from tidal_playlist_builder.model import Artist
from tidal_playlist_builder.services.cache_service import CacheService


class ArtistRepository:
    """Fetches artists from provider client with cache support."""

    def __init__(
        self,
        cache: CacheService,
        search_operation: Callable[[str, int], list[dict[str, object]]],
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._cache = cache
        self._search_operation = search_operation
        self._cache_ttl_seconds = cache_ttl_seconds

    def search(self, query: str, limit: int) -> list[Artist]:
        cache_key = f"artist_search:{query.strip().lower()}:{limit}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, list):
            return cached

        payload = self._search_operation(query, limit)
        artists = [self._to_artist(item) for item in payload]
        self._cache.set(cache_key, artists, ttl_seconds=self._cache_ttl_seconds)
        return artists

    def _to_artist(self, payload: dict[str, object]) -> Artist:
        artist_id = str(payload.get("id", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not artist_id:
            raise ValueError("Artist payload missing id")
        if not name:
            raise ValueError("Artist payload missing name")
        return Artist(id=artist_id, name=name)

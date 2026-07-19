"""Album repository."""

from collections.abc import Callable
from typing import TypeVar

from tidal_playlist_builder.exceptions import RepositoryError
from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    Track,
)
from tidal_playlist_builder.services.cache_service import CacheService

EnumT = TypeVar("EnumT")


class AlbumRepository:
    """Fetches albums/tracks from provider client with cache support."""

    _ALBUM_TYPE_MAP: dict[str, AlbumType] = {
        "album": AlbumType.ALBUM,
        "ep": AlbumType.EP,
        "single": AlbumType.SINGLE,
        "compilation": AlbumType.COMPILATION,
    }
    _EDITION_MAP: dict[str, AlbumEdition] = {item.value: item for item in AlbumEdition}
    _QUALITY_MAP: dict[str, AudioQuality] = {item.value: item for item in AudioQuality}

    def __init__(
        self,
        cache: CacheService,
        album_operation: Callable[[str], list[dict[str, object]]],
        track_operation: Callable[[str], list[dict[str, object]]],
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._cache = cache
        self._album_operation = album_operation
        self._track_operation = track_operation
        self._cache_ttl_seconds = cache_ttl_seconds

    def get_artist_albums(self, artist_id: str) -> list[Album]:
        cache_key = f"artist_albums:{artist_id}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, list):
            return cached

        payload = self._album_operation(artist_id)
        albums = [self._to_album(item) for item in payload]
        self._cache.set(cache_key, albums, ttl_seconds=self._cache_ttl_seconds)
        return albums

    def get_album_tracks(self, album_id: str) -> list[Track]:
        cache_key = f"album_tracks:{album_id}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, list):
            return cached

        payload = self._track_operation(album_id)
        tracks = [self._to_track(item) for item in payload]
        self._cache.set(cache_key, tracks, ttl_seconds=self._cache_ttl_seconds)
        return tracks

    def _to_album(self, payload: dict[str, object]) -> Album:
        artist_payload = payload.get("artist")
        if not isinstance(artist_payload, dict):
            raise RepositoryError("Album payload missing artist object")

        artist = Artist(
            id=str(artist_payload.get("id", "")).strip(),
            name=str(artist_payload.get("name", "")).strip(),
        )
        if not artist.id:
            raise RepositoryError("Album payload artist missing id")
        if not artist.name:
            raise RepositoryError("Album payload artist missing name")

        album_id = str(payload.get("id", "")).strip()
        title = str(payload.get("title", "")).strip()
        if not album_id:
            raise RepositoryError("Album payload missing id")
        if not title:
            raise RepositoryError("Album payload missing title")

        release_year = self._as_int(payload.get("release_year"), 0)
        album_type = self._parse_album_type(str(payload.get("album_type", "album")))
        edition = self._parse_edition(str(payload.get("edition", "original")))
        quality = self._parse_quality(str(payload.get("quality", "lossy")))
        is_explicit = bool(payload.get("is_explicit", False))

        return Album(
            id=album_id,
            title=title,
            artist=artist,
            release_year=release_year,
            album_type=album_type,
            edition=edition,
            quality=quality,
            is_explicit=is_explicit,
            tracks=(),
        )

    def _to_track(self, payload: dict[str, object]) -> Track:
        track_id = str(payload.get("id", "")).strip()
        title = str(payload.get("title", "")).strip()
        duration = self._as_int(payload.get("duration_seconds"), 0)
        return Track(id=track_id, title=title, duration_seconds=duration)

    def _parse_album_type(self, value: str) -> AlbumType:
        return self._parse_enum(value, self._ALBUM_TYPE_MAP, AlbumType.ALBUM)

    def _parse_edition(self, value: str) -> AlbumEdition:
        return self._parse_enum(value, self._EDITION_MAP, AlbumEdition.ORIGINAL)

    def _parse_quality(self, value: str) -> AudioQuality:
        return self._parse_enum(value, self._QUALITY_MAP, AudioQuality.LOSSY)

    def _parse_enum(
        self,
        value: str,
        mapping: dict[str, EnumT],
        default: EnumT,
    ) -> EnumT:
        normalized = value.strip().lower()
        return mapping.get(normalized, default)

    def _as_int(self, value: object, default: int) -> int:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        return default

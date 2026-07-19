"""Tests for TidalProvider using mocked responses."""

from dataclasses import dataclass, field
from tempfile import mkdtemp

import pytest

from tidal_playlist_builder.exceptions import (
    AuthenticationError,
    ValidationError,
)
from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    PlaylistBuildPlan,
    Track,
)
from tidal_playlist_builder.services.cache_service import CacheService
from tidal_playlist_builder.tidal import TidalProvider
from tidal_playlist_builder.tidal.provider import RequestRateLimiter


@dataclass
class _FakeClient:
    auth_calls: int = 0
    artist_calls: int = 0
    album_calls: int = 0
    track_calls: int = 0
    create_playlist_calls: int = 0
    add_tracks_calls: int = 0
    delete_playlist_calls: int = 0
    auth_token: str = "token-123"
    artist_response: list[dict[str, object]] = field(default_factory=list)
    album_response: list[dict[str, object]] = field(default_factory=list)
    track_response: list[dict[str, object]] = field(default_factory=list)
    artist_failures: list[Exception] = field(default_factory=list)

    def authenticate(self, credentials: dict[str, str]) -> str:
        self.auth_calls += 1
        return self.auth_token

    def search_artists(self, query: str, limit: int) -> list[dict[str, object]]:
        self.artist_calls += 1
        if self.artist_failures:
            error = self.artist_failures.pop(0)
            raise error
        return self.artist_response

    def get_artist_albums(self, artist_id: str) -> list[dict[str, object]]:
        self.album_calls += 1
        return self.album_response

    def get_album_tracks(self, album_id: str) -> list[dict[str, object]]:
        self.track_calls += 1
        return self.track_response

    def create_playlist(self, name: str, description: str) -> str:
        self.create_playlist_calls += 1
        return "playlist-1"

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        self.add_tracks_calls += 1

    def delete_playlist(self, playlist_id: str) -> None:
        self.delete_playlist_calls += 1


def _build_provider(
    client: _FakeClient,
    *,
    min_interval_seconds: float = 0.0,
    now_values: list[float] | None = None,
    recorded_sleeps: list[float] | None = None,
    max_retries: int = 2,
    retry_backoff_seconds: float = 0.0,
) -> TidalProvider:
    clock_values = now_values or [0.0, 0.0, 1.0, 1.0, 2.0]
    clock_iter = iter(clock_values)
    sleeps = recorded_sleeps if recorded_sleeps is not None else []
    limiter = RequestRateLimiter(
        min_interval_seconds=min_interval_seconds,
        now=lambda: next(clock_iter),
        sleeper=lambda seconds: sleeps.append(seconds),
    )
    return TidalProvider(
        api_client=client,
        cache_service=CacheService(cache_directory=mkdtemp()),
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        rate_limiter=limiter,
        sleeper=lambda seconds: sleeps.append(seconds),
    )


def _plan() -> PlaylistBuildPlan:
    artist = Artist(id="artist:1", name="Massive Attack")
    track_1 = Track(id="track:1", title="Teardrop", duration_seconds=330)
    track_2 = Track(id="track:2", title="Angel", duration_seconds=420)
    album = Album(
        id="album:1",
        title="Mezzanine",
        artist=artist,
        release_year=1998,
        album_type=AlbumType.ALBUM,
        edition=AlbumEdition.ORIGINAL,
        quality=AudioQuality.LOSSLESS,
        is_explicit=False,
        tracks=(track_1, track_2),
    )
    return PlaylistBuildPlan(
        artist=artist,
        selected_albums=(album,),
        selected_tracks=(track_1, track_2),
        duplicates_skipped=0,
        duration_seconds=750,
        track_count=2,
    )


def test_authentication_required() -> None:
    client = _FakeClient()
    provider = _build_provider(client)

    with pytest.raises(AuthenticationError, match="not authenticated"):
        provider.search_artists("massive")


def test_authenticate_success() -> None:
    client = _FakeClient()
    provider = _build_provider(client)

    provider.authenticate({"username": "user", "password": "pass"})

    assert client.auth_calls == 1


def test_authenticate_rejects_empty_credentials() -> None:
    client = _FakeClient()
    provider = _build_provider(client)

    with pytest.raises(ValidationError, match="credentials cannot be empty"):
        provider.authenticate({})


def test_artist_search_uses_cache() -> None:
    client = _FakeClient(artist_response=[{"id": "artist:1", "name": "Massive Attack"}])
    provider = _build_provider(client)
    provider.authenticate({"token": "x"})

    first = provider.search_artists("massive", 10)
    second = provider.search_artists("massive", 10)

    assert len(first) == 1
    assert len(second) == 1
    assert client.artist_calls == 1


def test_album_retrieval_uses_cache() -> None:
    client = _FakeClient(
        album_response=[
            {
                "id": "album:1",
                "title": "Mezzanine",
                "release_year": 1998,
                "album_type": "album",
                "edition": "original",
                "quality": "lossless",
                "is_explicit": False,
                "artist": {"id": "artist:1", "name": "Massive Attack"},
            }
        ]
    )
    provider = _build_provider(client)
    provider.authenticate({"token": "x"})

    first = provider.get_artist_albums("artist:1")
    second = provider.get_artist_albums("artist:1")

    assert len(first) == 1
    assert len(second) == 1
    assert client.album_calls == 1


def test_track_retrieval_uses_cache() -> None:
    client = _FakeClient(
        track_response=[{"id": "track:1", "title": "Teardrop", "duration_seconds": 330}]
    )
    provider = _build_provider(client)
    provider.authenticate({"token": "x"})

    first = provider.get_album_tracks("album:1")
    second = provider.get_album_tracks("album:1")

    assert len(first) == 1
    assert len(second) == 1
    assert client.track_calls == 1


def test_retries_on_transient_error_then_succeeds() -> None:
    client = _FakeClient(
        artist_response=[{"id": "artist:1", "name": "Massive Attack"}],
        artist_failures=[TimeoutError("t1"), TimeoutError("t2")],
    )
    sleeps: list[float] = []
    provider = _build_provider(
        client,
        recorded_sleeps=sleeps,
        max_retries=2,
        retry_backoff_seconds=0.5,
    )
    provider.authenticate({"token": "x"})

    artists = provider.search_artists("massive", 5)

    assert len(artists) == 1
    assert client.artist_calls == 3
    assert sleeps == [0.5, 1.0]


def test_retries_exhausted_raises() -> None:
    client = _FakeClient(
        artist_failures=[TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")]
    )
    provider = _build_provider(client, max_retries=2, retry_backoff_seconds=0.0)
    provider.authenticate({"token": "x"})

    with pytest.raises(TimeoutError, match="t3"):
        provider.search_artists("massive", 5)

    assert client.artist_calls == 3


def test_rate_limiter_waits_between_uncached_requests() -> None:
    client = _FakeClient(artist_response=[{"id": "artist:1", "name": "Massive Attack"}])
    sleeps: list[float] = []
    provider = _build_provider(
        client,
        min_interval_seconds=0.5,
        now_values=[0.0, 0.2, 0.2, 1.0],
        recorded_sleeps=sleeps,
    )
    provider.authenticate({"token": "x"})

    provider.search_artists("massive", 5)
    provider.search_artists("portishead", 5)

    assert any(delay > 0 for delay in sleeps)


def test_playlist_creation_success() -> None:
    client = _FakeClient()
    provider = _build_provider(client)
    provider.authenticate({"token": "x"})

    playlist_id = provider.create_playlist(_plan())

    assert playlist_id == "playlist-1"
    assert client.create_playlist_calls == 1
    assert client.add_tracks_calls == 1

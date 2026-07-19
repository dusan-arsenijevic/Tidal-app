"""Integration-style tests for playlist creation flow with mocked client."""

from dataclasses import dataclass, field
import logging

import pytest

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
from tidal_playlist_builder.tidal import (
    CancellationToken,
    PlaylistCreationCancelledError,
    PlaylistCreationProgress,
    RequestRateLimiter,
    TidalProvider,
)


@dataclass
class _PlaylistClient:
    add_failures: list[Exception] = field(default_factory=list)
    delete_failure: Exception | None = None
    created_playlist_ids: list[str] = field(default_factory=list)
    added_batches: list[list[str]] = field(default_factory=list)
    deleted_ids: list[str] = field(default_factory=list)

    def authenticate(self, credentials: dict[str, str]) -> str:
        return "token"

    def search_artists(self, query: str, limit: int) -> list[dict[str, object]]:
        return []

    def get_artist_albums(self, artist_id: str) -> list[dict[str, object]]:
        return []

    def get_album_tracks(self, album_id: str) -> list[dict[str, object]]:
        return []

    def create_playlist(self, name: str, description: str) -> str:
        playlist_id = f"pl-{len(self.created_playlist_ids) + 1}"
        self.created_playlist_ids.append(playlist_id)
        return playlist_id

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        if self.add_failures:
            error = self.add_failures.pop(0)
            raise error
        self.added_batches.append(list(track_ids))

    def delete_playlist(self, playlist_id: str) -> None:
        if self.delete_failure is not None:
            raise self.delete_failure
        self.deleted_ids.append(playlist_id)


def _provider(
    client: _PlaylistClient, retry_backoff_seconds: float = 0.0
) -> TidalProvider:
    limiter = RequestRateLimiter(
        min_interval_seconds=0.0,
        now=lambda: 0.0,
        sleeper=lambda _seconds: None,
    )
    provider = TidalProvider(
        api_client=client,
        cache_service=CacheService(),
        max_retries=2,
        retry_backoff_seconds=retry_backoff_seconds,
        rate_limiter=limiter,
        sleeper=lambda _seconds: None,
    )
    provider.authenticate({"token": "x"})
    return provider


def _plan(track_count: int = 5) -> PlaylistBuildPlan:
    artist = Artist(id="artist:1", name="Massive Attack")
    tracks = tuple(
        Track(id=f"track:{index}", title=f"Song {index}", duration_seconds=200)
        for index in range(track_count)
    )
    album = Album(
        id="album:1",
        title="Mezzanine",
        artist=artist,
        release_year=1998,
        album_type=AlbumType.ALBUM,
        edition=AlbumEdition.ORIGINAL,
        quality=AudioQuality.LOSSLESS,
        is_explicit=False,
        tracks=tracks,
    )
    return PlaylistBuildPlan(
        artist=artist,
        selected_albums=(album,),
        selected_tracks=tracks,
        duplicates_skipped=0,
        duration_seconds=track_count * 200,
        track_count=track_count,
    )


def test_progress_reporting_and_batching() -> None:
    client = _PlaylistClient()
    provider = _provider(client)
    progress_events: list[PlaylistCreationProgress] = []

    playlist_id = provider.create_playlist(
        _plan(track_count=5),
        progress_callback=progress_events.append,
        batch_size=2,
    )

    assert playlist_id == "pl-1"
    assert client.added_batches == [
        ["track:0", "track:1"],
        ["track:2", "track:3"],
        ["track:4"],
    ]
    assert [event.phase for event in progress_events] == [
        "creating_playlist",
        "playlist_created",
        "adding_tracks",
        "adding_tracks",
        "adding_tracks",
        "completed",
    ]
    assert progress_events[-1].completed == 5
    assert progress_events[-1].total == 5


def test_cancellation_before_create() -> None:
    client = _PlaylistClient()
    provider = _provider(client)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(PlaylistCreationCancelledError):
        provider.create_playlist(_plan(track_count=3), cancellation_token=token)

    assert client.created_playlist_ids == []
    assert client.deleted_ids == []


def test_cancellation_after_playlist_creation_recovers() -> None:
    client = _PlaylistClient(add_failures=[PlaylistCreationCancelledError("cancelled")])
    provider = _provider(client)

    with pytest.raises(PlaylistCreationCancelledError):
        provider.create_playlist(_plan(track_count=3), batch_size=1)

    assert client.created_playlist_ids == ["pl-1"]
    assert client.deleted_ids == ["pl-1"]


def test_retry_then_success_on_add_tracks() -> None:
    client = _PlaylistClient(add_failures=[TimeoutError("t1"), TimeoutError("t2")])
    provider = _provider(client, retry_backoff_seconds=0.0)

    playlist_id = provider.create_playlist(_plan(track_count=2), batch_size=2)

    assert playlist_id == "pl-1"
    assert client.deleted_ids == []
    assert client.added_batches == [["track:0", "track:1"]]


def test_error_recovery_deletes_partial_playlist() -> None:
    client = _PlaylistClient(
        add_failures=[TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")]
    )
    provider = _provider(client, retry_backoff_seconds=0.0)

    with pytest.raises(TimeoutError, match="t3"):
        provider.create_playlist(_plan(track_count=2), batch_size=2)

    assert client.created_playlist_ids == ["pl-1"]
    assert client.deleted_ids == ["pl-1"]


def test_error_recovery_logs_when_delete_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _PlaylistClient(
        add_failures=[TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")],
        delete_failure=RuntimeError("delete failed"),
    )
    provider = _provider(client, retry_backoff_seconds=0.0)

    caplog.set_level(logging.ERROR)
    with pytest.raises(TimeoutError):
        provider.create_playlist(_plan(track_count=1))

    assert "Failed to recover playlist" in caplog.text

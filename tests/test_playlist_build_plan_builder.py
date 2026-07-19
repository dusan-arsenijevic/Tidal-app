"""Tests for PlaylistBuildPlanBuilder."""

import pytest

from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    Track,
)
from tidal_playlist_builder.services import PlaylistBuildPlanBuilder


def _artist() -> Artist:
    return Artist(id="artist-1", name="Massive Attack")


def _track(track_id: str, title: str, seconds: int) -> Track:
    return Track(id=track_id, title=title, duration_seconds=seconds)


def _album(
    album_id: str,
    title: str,
    artist: Artist,
    tracks: tuple[Track, ...],
    release_year: int = 2000,
) -> Album:
    return Album(
        id=album_id,
        title=title,
        artist=artist,
        release_year=release_year,
        album_type=AlbumType.ALBUM,
        edition=AlbumEdition.ORIGINAL,
        quality=AudioQuality.LOSSLESS,
        is_explicit=False,
        tracks=tracks,
    )


def test_builds_plan_with_selected_tracks_duration_and_count() -> None:
    builder = PlaylistBuildPlanBuilder()
    artist = _artist()
    album1 = _album(
        "alb-1",
        "Mezzanine",
        artist,
        tracks=(
            _track("t1", "Angel", 380),
            _track("t2", "Risingson", 300),
        ),
    )
    album2 = _album(
        "alb-2",
        "Blue Lines",
        artist,
        tracks=(
            _track("t3", "Safe from Harm", 330),
            _track("t4", "Unfinished Sympathy", 320),
        ),
    )

    plan = builder.build(artist=artist, selected_albums=[album1, album2])

    assert plan.artist == artist
    assert [album.id for album in plan.selected_albums] == ["alb-1", "alb-2"]
    assert [track.id for track in plan.selected_tracks] == ["t1", "t2", "t3", "t4"]
    assert plan.duration_seconds == 1330
    assert plan.track_count == 4
    assert plan.duplicates_skipped == 0


def test_skips_duplicate_tracks_and_counts_skipped() -> None:
    builder = PlaylistBuildPlanBuilder()
    artist = _artist()
    shared = _track("t-shared", "Teardrop", 330)
    album1 = _album(
        "alb-1",
        "Album A",
        artist,
        tracks=(shared, _track("t2", "Inertia Creeps", 310)),
    )
    album2 = _album(
        "alb-2",
        "Album B",
        artist,
        tracks=(shared, _track("t3", "Black Milk", 390)),
    )

    plan = builder.build(artist=artist, selected_albums=[album1, album2])

    assert [track.id for track in plan.selected_tracks] == ["t-shared", "t2", "t3"]
    assert plan.track_count == 3
    assert plan.duration_seconds == 1030
    assert plan.duplicates_skipped == 1


def test_preserves_first_seen_track_order() -> None:
    builder = PlaylistBuildPlanBuilder()
    artist = _artist()
    album1 = _album(
        "alb-1",
        "Album A",
        artist,
        tracks=(_track("t1", "First", 100), _track("t2", "Second", 110)),
    )
    album2 = _album(
        "alb-2",
        "Album B",
        artist,
        tracks=(_track("t2", "Second", 110), _track("t3", "Third", 120)),
    )

    plan = builder.build(artist=artist, selected_albums=[album1, album2])

    assert [track.id for track in plan.selected_tracks] == ["t1", "t2", "t3"]


def test_supports_albums_with_no_tracks() -> None:
    builder = PlaylistBuildPlanBuilder()
    artist = _artist()
    album = _album("alb-1", "No Tracks", artist, tracks=())

    plan = builder.build(artist=artist, selected_albums=[album])

    assert plan.selected_tracks == ()
    assert plan.track_count == 0
    assert plan.duration_seconds == 0
    assert plan.duplicates_skipped == 0


def test_rejects_empty_selected_albums() -> None:
    builder = PlaylistBuildPlanBuilder()

    with pytest.raises(ValueError, match="selected_albums cannot be empty"):
        builder.build(artist=_artist(), selected_albums=[])


def test_rejects_album_from_different_artist() -> None:
    builder = PlaylistBuildPlanBuilder()
    artist = _artist()
    other_artist = Artist(id="artist-2", name="Portishead")
    album = _album("alb-1", "Dummy", other_artist, tracks=())

    with pytest.raises(ValueError, match="must belong to the input artist"):
        builder.build(artist=artist, selected_albums=[album])


def test_rejects_duplicate_album_ids() -> None:
    builder = PlaylistBuildPlanBuilder()
    artist = _artist()
    album1 = _album("alb-1", "One", artist, tracks=())
    album2 = _album("alb-1", "Two", artist, tracks=())

    with pytest.raises(ValueError, match="duplicate album ids"):
        builder.build(artist=artist, selected_albums=[album1, album2])


def test_rejects_non_artist_input() -> None:
    builder = PlaylistBuildPlanBuilder()
    artist = _artist()
    album = _album("alb-1", "One", artist, tracks=())

    with pytest.raises(TypeError, match="artist must be an Artist"):
        builder.build(artist="not-an-artist", selected_albums=[album])  # type: ignore[arg-type]


def test_rejects_non_album_in_selected_albums() -> None:
    builder = PlaylistBuildPlanBuilder()

    with pytest.raises(TypeError, match="must contain only Album objects"):
        builder.build(artist=_artist(), selected_albums=[object()])  # type: ignore[list-item]


def test_track_model_validation() -> None:
    with pytest.raises(ValueError, match="Track id cannot be empty"):
        Track(id="", title="X", duration_seconds=1)
    with pytest.raises(ValueError, match="Track title cannot be empty"):
        Track(id="t1", title="", duration_seconds=1)
    with pytest.raises(ValueError, match="cannot be negative"):
        Track(id="t1", title="X", duration_seconds=-1)

"""FilterEngine tests."""

import pytest
from tidal_playlist_builder.filtering.filter_engine import FilterEngine
from tidal_playlist_builder.model import (
    Album,
    AlbumEdition,
    AlbumType,
    Artist,
    AudioQuality,
    DuplicateGroup,
    DuplicateStatus,
    FilterCriteria,
)


def _albums() -> list[Album]:
    artist_a = Artist(id="a1", name="Pink Floyd")
    artist_b = Artist(id="a2", name="Daft Punk")
    return [
        Album(
            id="alb-1",
            title="The Dark Side of the Moon",
            artist=artist_a,
            release_year=1973,
            album_type=AlbumType.ALBUM,
            edition=AlbumEdition.ORIGINAL,
            quality=AudioQuality.LOSSLESS,
            is_explicit=False,
        ),
        Album(
            id="alb-2",
            title="The Dark Side of the Moon (Remaster)",
            artist=artist_a,
            release_year=2011,
            album_type=AlbumType.ALBUM,
            edition=AlbumEdition.REMASTER,
            quality=AudioQuality.HI_RES,
            is_explicit=False,
        ),
        Album(
            id="alb-3",
            title="The Wall",
            artist=artist_a,
            release_year=1979,
            album_type=AlbumType.ALBUM,
            edition=AlbumEdition.DELUXE,
            quality=AudioQuality.LOSSY,
            is_explicit=True,
        ),
        Album(
            id="alb-4",
            title="Random Access Memories",
            artist=artist_b,
            release_year=2013,
            album_type=AlbumType.ALBUM,
            edition=AlbumEdition.ORIGINAL,
            quality=AudioQuality.LOSSLESS,
            is_explicit=False,
        ),
        Album(
            id="alb-5",
            title="Alive 2007",
            artist=artist_b,
            release_year=2007,
            album_type=AlbumType.ALBUM,
            edition=AlbumEdition.LIVE,
            quality=AudioQuality.LOSSY,
            is_explicit=False,
        ),
    ]


def _duplicate_groups() -> list[DuplicateGroup]:
    return [
        DuplicateGroup(
            canonical_album_id="alb-1", variant_album_ids=frozenset({"alb-2"})
        )
    ]


def test_filters_by_release_year_range() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(release_year_min=1975, release_year_max=2012)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-2", "alb-3", "alb-5"]


def test_filters_by_album_type() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(album_types=frozenset({AlbumType.ALBUM}))

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert all(album.album_type is AlbumType.ALBUM for album in result)


def test_filters_by_edition() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(
        editions=frozenset({AlbumEdition.REMASTER, AlbumEdition.DELUXE})
    )

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-2", "alb-3"]


def test_filters_by_quality() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(qualities=frozenset({AudioQuality.HI_RES}))

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-2"]


def test_filters_by_explicit_true() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(explicit=True)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-3"]


def test_filters_by_explicit_false() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(explicit=False)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-1", "alb-2", "alb-4", "alb-5"]


def test_filters_by_duplicate_status_canonical_only() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(duplicate_status=DuplicateStatus.CANONICAL_ONLY)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-1"]


def test_filters_by_duplicate_status_variants_only() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(duplicate_status=DuplicateStatus.VARIANTS_ONLY)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-2"]


def test_filters_by_duplicate_status_duplicates_only() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(duplicate_status=DuplicateStatus.DUPLICATES_ONLY)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-1", "alb-2"]


def test_filters_by_duplicate_status_non_duplicates_only() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(duplicate_status=DuplicateStatus.NON_DUPLICATES_ONLY)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-3", "alb-4", "alb-5"]


def test_filters_by_text_search_case_insensitive() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(search_text="dark SIDE")

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-1", "alb-2"]


def test_text_search_matches_artist_name() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(search_text="daft")

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-4", "alb-5"]


def test_combines_all_filters_with_and_logic() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(
        release_year_min=2000,
        release_year_max=2020,
        album_types=frozenset({AlbumType.ALBUM}),
        editions=frozenset({AlbumEdition.REMASTER}),
        qualities=frozenset({AudioQuality.HI_RES}),
        explicit=False,
        duplicate_status=DuplicateStatus.VARIANTS_ONLY,
        search_text="moon",
    )

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-2"]


def test_empty_search_text_is_ignored() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(search_text="   ")

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert len(result) == len(_albums())


def test_release_year_min_only() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(release_year_min=2010)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-2", "alb-4"]


def test_release_year_max_only() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(release_year_max=1979)

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-1", "alb-3"]


def test_extension_filter_can_be_registered_and_used() -> None:
    engine = FilterEngine()

    def artist_prefix_filter(album: Album, value: object, _context: object) -> bool:
        assert isinstance(value, str)
        return album.artist.name.lower().startswith(value.lower())

    engine.register_extension_filter("artist_prefix", artist_prefix_filter)
    criteria = FilterCriteria(extension_filters={"artist_prefix": "Pink"})

    result = engine.filter_albums(_albums(), criteria, _duplicate_groups())

    assert [a.id for a in result] == ["alb-1", "alb-2", "alb-3"]


def test_unknown_extension_filter_raises() -> None:
    engine = FilterEngine()
    criteria = FilterCriteria(extension_filters={"unknown_filter": True})

    with pytest.raises(ValueError, match="Unknown extension filter"):
        engine.filter_albums(_albums(), criteria, _duplicate_groups())


def test_unregister_extension_filter_disables_handler() -> None:
    engine = FilterEngine()

    def allow_all(_album: Album, _value: object, _context: object) -> bool:
        return True

    engine.register_extension_filter("x", allow_all)
    engine.unregister_extension_filter("x")
    criteria = FilterCriteria(extension_filters={"x": 1})

    with pytest.raises(ValueError, match="Unknown extension filter"):
        engine.filter_albums(_albums(), criteria, _duplicate_groups())


def test_register_extension_filter_rejects_empty_name() -> None:
    engine = FilterEngine()

    def allow_all(_album: Album, _value: object, _context: object) -> bool:
        return True

    with pytest.raises(ValueError, match="cannot be empty"):
        engine.register_extension_filter("  ", allow_all)

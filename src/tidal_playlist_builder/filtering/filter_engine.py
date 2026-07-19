"""Filtering service for albums."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from tidal_playlist_builder.model.album import Album
from tidal_playlist_builder.model.duplicate_group import DuplicateGroup
from tidal_playlist_builder.model.enums import DuplicateStatus
from tidal_playlist_builder.model.filter_criteria import FilterCriteria


class _AlbumDuplicateState(Enum):
    UNIQUE = "unique"
    CANONICAL = "canonical"
    VARIANT = "variant"


@dataclass(frozen=True, slots=True)
class _FilterContext:
    duplicate_index: dict[str, _AlbumDuplicateState]


ExtensionFilter = Callable[[Album, object, _FilterContext], bool]


class FilterEngine:
    """Applies filtering criteria over album collections.

    The engine exposes extension points through `register_extension_filter`
    so additional criteria can be introduced without changing core methods.
    """

    def __init__(self) -> None:
        self._extension_filters: dict[str, ExtensionFilter] = {}

    def register_extension_filter(self, name: str, handler: ExtensionFilter) -> None:
        """Register an extension filter handler by name."""
        if not name.strip():
            raise ValueError("Extension filter name cannot be empty")
        self._extension_filters[name] = handler

    def unregister_extension_filter(self, name: str) -> None:
        """Remove an extension filter handler if present."""
        self._extension_filters.pop(name, None)

    def filter_albums(
        self,
        albums: list[Album],
        criteria: FilterCriteria,
        duplicate_groups: list[DuplicateGroup] | None = None,
    ) -> list[Album]:
        """Return albums matching all filter criteria."""
        context = _FilterContext(
            duplicate_index=self._build_duplicate_index(duplicate_groups or [])
        )
        search_text = criteria.normalized_search_text()
        selected: list[Album] = []

        for album in albums:
            if not self._matches_release_year(album, criteria):
                continue
            if not self._matches_album_type(album, criteria):
                continue
            if not self._matches_edition(album, criteria):
                continue
            if not self._matches_quality(album, criteria):
                continue
            if not self._matches_explicit(album, criteria):
                continue
            if not self._matches_duplicate_status(album, criteria, context):
                continue
            if not self._matches_text(album, search_text):
                continue
            if not self._matches_extensions(album, criteria, context):
                continue
            selected.append(album)

        return selected

    def _build_duplicate_index(
        self, groups: list[DuplicateGroup]
    ) -> dict[str, _AlbumDuplicateState]:
        index: dict[str, _AlbumDuplicateState] = {}
        for group in groups:
            index[group.canonical_album_id] = _AlbumDuplicateState.CANONICAL
            for album_id in group.variant_album_ids:
                index[album_id] = _AlbumDuplicateState.VARIANT
        return index

    def _matches_release_year(self, album: Album, criteria: FilterCriteria) -> bool:
        if (
            criteria.release_year_min is not None
            and album.release_year < criteria.release_year_min
        ):
            return False
        if (
            criteria.release_year_max is not None
            and album.release_year > criteria.release_year_max
        ):
            return False
        return True

    def _matches_album_type(self, album: Album, criteria: FilterCriteria) -> bool:
        if criteria.album_types is None:
            return True
        return album.album_type in criteria.album_types

    def _matches_edition(self, album: Album, criteria: FilterCriteria) -> bool:
        if criteria.editions is None:
            return True
        return album.edition in criteria.editions

    def _matches_quality(self, album: Album, criteria: FilterCriteria) -> bool:
        if criteria.qualities is None:
            return True
        return album.quality in criteria.qualities

    def _matches_explicit(self, album: Album, criteria: FilterCriteria) -> bool:
        if criteria.explicit is None:
            return True
        return album.is_explicit == criteria.explicit

    def _matches_duplicate_status(
        self, album: Album, criteria: FilterCriteria, context: _FilterContext
    ) -> bool:
        state = context.duplicate_index.get(album.id, _AlbumDuplicateState.UNIQUE)
        mode = criteria.duplicate_status

        if mode is DuplicateStatus.ALL:
            return True
        if mode is DuplicateStatus.CANONICAL_ONLY:
            return state is _AlbumDuplicateState.CANONICAL
        if mode is DuplicateStatus.VARIANTS_ONLY:
            return state is _AlbumDuplicateState.VARIANT
        if mode is DuplicateStatus.DUPLICATES_ONLY:
            return state in (
                _AlbumDuplicateState.CANONICAL,
                _AlbumDuplicateState.VARIANT,
            )
        if mode is DuplicateStatus.NON_DUPLICATES_ONLY:
            return state is _AlbumDuplicateState.UNIQUE
        return True

    def _matches_text(self, album: Album, search_text: str | None) -> bool:
        if search_text is None:
            return True
        haystack = f"{album.title} {album.artist.name}".lower()
        return all(token in haystack for token in search_text.split())

    def _matches_extensions(
        self, album: Album, criteria: FilterCriteria, context: _FilterContext
    ) -> bool:
        for name, value in criteria.extension_filters.items():
            handler = self._extension_filters.get(name)
            if handler is None:
                raise ValueError(f"Unknown extension filter: {name}")
            if not handler(album, value, context):
                return False
        return True

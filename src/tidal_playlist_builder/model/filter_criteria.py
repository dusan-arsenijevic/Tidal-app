"""Filtering criteria model."""

from dataclasses import dataclass, field
from typing import Mapping

from .enums import AlbumEdition, AlbumType, AudioQuality, DuplicateStatus


@dataclass(frozen=True, slots=True)
class FilterCriteria:
    """Describes filtering options for album lists."""

    release_year_min: int | None = None
    release_year_max: int | None = None
    album_types: frozenset[AlbumType] | None = None
    editions: frozenset[AlbumEdition] | None = None
    qualities: frozenset[AudioQuality] | None = None
    explicit: bool | None = None
    duplicate_status: DuplicateStatus = DuplicateStatus.ALL
    search_text: str | None = None
    extension_filters: Mapping[str, object] = field(default_factory=dict)

    def normalized_search_text(self) -> str | None:
        """Normalize search text for case-insensitive matching."""
        if self.search_text is None:
            return None
        value = self.search_text.strip().lower()
        return value if value else None

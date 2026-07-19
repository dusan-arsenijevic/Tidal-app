"""Duplicate grouping model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """A duplicate group represented by album ids."""

    canonical_album_id: str
    variant_album_ids: frozenset[str]

    def all_album_ids(self) -> frozenset[str]:
        """Return all album ids in the group."""
        return self.variant_album_ids | frozenset([self.canonical_album_id])

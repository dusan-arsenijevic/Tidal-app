"""Playlist conflict resolution models."""

from dataclasses import dataclass
from enum import Enum


class PlaylistConflictAction(str, Enum):
    """User-selected behavior when a playlist name already exists."""

    REPLACE_EXISTING = "replace_existing"
    APPEND_TRACKS = "append_tracks"
    CREATE_ANOTHER = "create_another"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class PlaylistSummary:
    """Minimal playlist data used for conflict detection and upload operations."""

    id: str
    name: str

"""Track model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Track:
    """Track entity used for playlist planning."""

    id: str
    title: str
    duration_seconds: int

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Track id cannot be empty")
        if not self.title.strip():
            raise ValueError("Track title cannot be empty")
        if self.duration_seconds < 0:
            raise ValueError("Track duration_seconds cannot be negative")

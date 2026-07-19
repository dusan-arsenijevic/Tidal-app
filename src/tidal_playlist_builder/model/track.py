"""Track model."""

from dataclasses import dataclass

from tidal_playlist_builder.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class Track:
    """Track entity used for playlist planning."""

    id: str
    title: str
    duration_seconds: int

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValidationError("Track id cannot be empty")
        if not self.title.strip():
            raise ValidationError("Track title cannot be empty")
        if self.duration_seconds < 0:
            raise ValidationError("Track duration_seconds cannot be negative")

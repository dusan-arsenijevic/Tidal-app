"""Artist model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Artist:
    """Music artist."""

    id: str
    name: str

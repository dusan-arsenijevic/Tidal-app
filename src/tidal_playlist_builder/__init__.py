"""Tidal playlist builder package."""

from .__about__ import __version__
from .exceptions import (
    AuthenticationError,
    CacheError,
    DuplicateDetectionError,
    NetworkError,
    PlaylistCreationError,
    ProviderError,
    RateLimitError,
    RepositoryError,
    TidalPlaylistBuilderError,
    ValidationError,
)

__all__ = [
    "__version__",
    "AuthenticationError",
    "CacheError",
    "DuplicateDetectionError",
    "NetworkError",
    "PlaylistCreationError",
    "ProviderError",
    "RateLimitError",
    "RepositoryError",
    "TidalPlaylistBuilderError",
    "ValidationError",
]

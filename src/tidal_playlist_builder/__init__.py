"""Tidal playlist builder package."""

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

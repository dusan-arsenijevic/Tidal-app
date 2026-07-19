"""Domain-specific exception hierarchy for the application."""


class TidalPlaylistBuilderError(Exception):
    """Base exception for all domain and application errors."""


class ValidationError(TidalPlaylistBuilderError):
    """Raised when domain or service input validation fails."""


class RepositoryError(TidalPlaylistBuilderError):
    """Raised when repository mapping or persistence operations fail."""


class ProviderError(TidalPlaylistBuilderError):
    """Raised for provider-layer operation failures."""


class AuthenticationError(ProviderError):
    """Raised when authentication is missing, invalid, or fails."""


class NetworkError(ProviderError):
    """Raised when provider operations fail due to network conditions."""


class RateLimitError(NetworkError):
    """Raised when provider rate limits are exceeded."""


class CacheError(TidalPlaylistBuilderError):
    """Raised for cache-layer failures."""


class CredentialStorageError(TidalPlaylistBuilderError):
    """Raised when secure credential storage operations fail."""


class PlaylistCreationError(ProviderError):
    """Raised for playlist creation workflow failures."""


class DuplicateDetectionError(TidalPlaylistBuilderError):
    """Raised for duplicate detection workflow failures."""

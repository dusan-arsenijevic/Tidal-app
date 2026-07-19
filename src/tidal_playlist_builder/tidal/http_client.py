"""Concrete HTTP client for the Tidal provider protocol."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
import logging
from time import monotonic, sleep
from typing import Protocol

from tidal_playlist_builder.exceptions import (
    AuthenticationError,
    NetworkError,
    ProviderError,
    RateLimitError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class _ResponseLike(Protocol):
    status_code: int
    text: str
    headers: dict[str, str]

    def json(self) -> object: ...


class _SessionLike(Protocol):
    headers: dict[str, str]

    def request(
        self,
        method: str,
        url: str,
        *,
        timeout: float,
        params: dict[str, object] | None = None,
        json: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> _ResponseLike: ...


@dataclass(frozen=True, slots=True)
class HttpClientConfig:
    """Configuration for HttpTidalApiClient."""

    base_url: str
    timeout_seconds: float
    max_retries: int
    backoff_base_seconds: float
    user_agent: str
    backoff_multiplier: float = 2.0
    token_refresh_leeway_seconds: float = 30.0
    min_request_interval_seconds: float = 0.0
    rate_limit_retry_after_default_seconds: float = 1.0


class HttpTidalApiClient:
    """Production HTTP client that satisfies the Tidal provider API protocol."""

    def __init__(
        self,
        config: HttpClientConfig,
        *,
        session: _SessionLike | None = None,
        now: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._validate_config(config)
        self._config = config
        self._now = now
        self._sleeper = sleeper
        self._cancellation_requested = cancellation_requested or (lambda: False)
        self._session = session or self._create_session()
        self._session.headers["User-Agent"] = config.user_agent
        self._last_request_at: float | None = None

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._access_token_expires_at: float | None = None
        self._transport_error_types = self._resolve_transport_error_types()

    def authenticate(self, credentials: dict[str, str]) -> str:
        if not credentials:
            raise ValidationError("credentials cannot be empty")
        payload = self._request_json(
            "POST", "/auth/login", json_body=credentials, require_auth=False
        )
        token = self._parse_auth_payload(payload)
        logger.info("Authentication succeeded")
        return token

    def search_artists(self, query: str, limit: int) -> list[dict[str, object]]:
        payload = self._request_json(
            "GET",
            "/artists/search",
            params={"q": query, "limit": limit},
            require_auth=True,
        )
        return self._extract_items(payload, "artists")

    def get_artist_albums(self, artist_id: str) -> list[dict[str, object]]:
        payload = self._request_json(
            "GET",
            f"/artists/{artist_id}/albums",
            require_auth=True,
        )
        return self._extract_items(payload, "albums")

    def get_album_tracks(self, album_id: str) -> list[dict[str, object]]:
        payload = self._request_json(
            "GET",
            f"/albums/{album_id}/tracks",
            require_auth=True,
        )
        return self._extract_items(payload, "tracks")

    def create_playlist(self, name: str, description: str) -> str:
        payload = self._request_json(
            "POST",
            "/playlists",
            json_body={"name": name, "description": description},
            require_auth=True,
        )
        return self._extract_id(payload, "playlist")

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        self._request_json(
            "POST",
            f"/playlists/{playlist_id}/tracks",
            json_body={"track_ids": track_ids},
            require_auth=True,
        )

    def delete_playlist(self, playlist_id: str) -> None:
        self._request_json(
            "DELETE",
            f"/playlists/{playlist_id}",
            require_auth=True,
        )

    def _validate_config(self, config: HttpClientConfig) -> None:
        if not config.base_url.strip():
            raise ValidationError("base_url cannot be empty")
        if config.timeout_seconds <= 0:
            raise ValidationError("timeout_seconds must be positive")
        if config.max_retries < 0:
            raise ValidationError("max_retries must be >= 0")
        if config.backoff_base_seconds < 0:
            raise ValidationError("backoff_base_seconds must be >= 0")
        if config.backoff_multiplier < 1:
            raise ValidationError("backoff_multiplier must be >= 1")
        if not config.user_agent.strip():
            raise ValidationError("user_agent cannot be empty")
        if config.token_refresh_leeway_seconds < 0:
            raise ValidationError("token_refresh_leeway_seconds must be >= 0")
        if config.min_request_interval_seconds < 0:
            raise ValidationError("min_request_interval_seconds must be >= 0")
        if config.rate_limit_retry_after_default_seconds < 0:
            raise ValidationError("rate_limit_retry_after_default_seconds must be >= 0")

    def _create_session(self) -> _SessionLike:
        try:
            requests = import_module("requests")
        except ModuleNotFoundError as error:
            raise ProviderError(
                "requests is required for HttpTidalApiClient production transport"
            ) from error
        return requests.Session()

    def _resolve_transport_error_types(self) -> tuple[type[BaseException], ...]:
        default_types: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError)
        try:
            requests = import_module("requests")
        except ModuleNotFoundError:
            return default_types
        exceptions_module = requests.exceptions
        return default_types + (
            exceptions_module.Timeout,
            exceptions_module.ConnectionError,
            exceptions_module.RequestException,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_body: Mapping[str, object] | list[object] | None = None,
        require_auth: bool,
    ) -> object:
        if require_auth:
            self._ensure_authenticated()
            if self._is_token_expired():
                self._refresh_access_token()

        retried_after_auth_refresh = False
        for attempt in range(self._config.max_retries + 1):
            self._check_cancelled()
            self._wait_rate_limit()
            url = self._build_url(path)
            headers = self._auth_headers(require_auth=require_auth)
            logger.debug(
                "HTTP request start method=%s path=%s attempt=%s",
                method,
                path,
                attempt + 1,
            )

            try:
                response = self._session.request(
                    method,
                    url,
                    timeout=self._config.timeout_seconds,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
            except self._transport_error_types as error:
                logger.warning(
                    "HTTP request transport failure method=%s path=%s attempt=%s",
                    method,
                    path,
                    attempt + 1,
                )
                if attempt >= self._config.max_retries:
                    raise NetworkError("HTTP transport failed after retries") from error
                self._sleep_for_retry(attempt, reason="transport")
                continue

            status = response.status_code
            logger.debug(
                "HTTP request completed method=%s path=%s status=%s attempt=%s",
                method,
                path,
                status,
                attempt + 1,
            )

            if status == 401:
                if (
                    require_auth
                    and not retried_after_auth_refresh
                    and self._refresh_token
                ):
                    self._refresh_access_token()
                    retried_after_auth_refresh = True
                    continue
                raise AuthenticationError("Unauthorized request")

            if status == 429:
                retry_after_header = response.headers.get("Retry-After")
                if attempt >= self._config.max_retries:
                    raise RateLimitError("Rate limited and retry budget exhausted")
                delay = self._rate_limit_delay(retry_after_header, attempt)
                logger.warning(
                    "Retrying after rate limit path=%s delay=%s", path, delay
                )
                self._sleeper(delay)
                continue

            if status >= 500:
                logger.warning("HTTP server error status=%s path=%s", status, path)
                if attempt >= self._config.max_retries:
                    raise ProviderError(f"Server error status={status}")
                self._sleep_for_retry(attempt, reason=f"status_{status}")
                continue

            if status >= 400:
                logger.warning("HTTP client error status=%s path=%s", status, path)
                raise ProviderError(f"HTTP error status={status}")

            try:
                return response.json()
            except ValueError as error:
                logger.warning("Invalid JSON response path=%s", path)
                raise ProviderError("Invalid JSON response payload") from error

        raise ProviderError("HTTP request failed unexpectedly")

    def _parse_auth_payload(self, payload: object) -> str:
        if not isinstance(payload, dict):
            raise AuthenticationError("Authentication response must be an object")
        access_token_value = payload.get("access_token")
        refresh_token_value = payload.get("refresh_token")
        expires_in_value = payload.get("expires_in")

        access_token = str(access_token_value or "").strip()
        refresh_token = str(refresh_token_value or "").strip()
        expires_in_seconds = self._as_non_negative_float(expires_in_value, "expires_in")

        if not access_token:
            raise AuthenticationError("Authentication response missing access_token")

        self._access_token = access_token
        self._refresh_token = refresh_token or None
        self._access_token_expires_at = self._now() + expires_in_seconds
        return access_token

    def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise AuthenticationError("Cannot refresh without refresh token")
        payload = self._request_json(
            "POST",
            "/auth/refresh",
            json_body={"refresh_token": self._refresh_token},
            require_auth=False,
        )
        self._parse_auth_payload(payload)
        logger.info("Access token refreshed")

    def _extract_items(self, payload: object, key: str) -> list[dict[str, object]]:
        if isinstance(payload, dict):
            items = payload.get(key)
            if isinstance(items, list) and all(
                isinstance(item, dict) for item in items
            ):
                return items
            raise ProviderError(f"Response missing '{key}' list")
        if isinstance(payload, list) and all(
            isinstance(item, dict) for item in payload
        ):
            return payload
        raise ProviderError(f"Invalid response payload for '{key}'")

    def _extract_id(self, payload: object, entity_name: str) -> str:
        if not isinstance(payload, dict):
            raise ProviderError(f"Invalid {entity_name} response payload")
        identifier = str(payload.get("id", "")).strip()
        if not identifier:
            raise ProviderError(f"{entity_name.capitalize()} response missing id")
        return identifier

    def _ensure_authenticated(self) -> None:
        if self._access_token is None:
            raise AuthenticationError("HTTP client is not authenticated")

    def _is_token_expired(self) -> bool:
        if self._access_token_expires_at is None:
            return False
        return (
            self._now() + self._config.token_refresh_leeway_seconds
            >= self._access_token_expires_at
        )

    def _auth_headers(self, *, require_auth: bool) -> dict[str, str] | None:
        if not require_auth:
            return None
        if self._access_token is None:
            return None
        return {"Authorization": f"Bearer {self._access_token}"}

    def _build_url(self, path: str) -> str:
        base = self._config.base_url.rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}"
        return f"{base}{suffix}"

    def _wait_rate_limit(self) -> None:
        interval = self._config.min_request_interval_seconds
        if interval <= 0:
            return
        current = self._now()
        if self._last_request_at is None:
            self._last_request_at = current
            return
        elapsed = current - self._last_request_at
        remaining = interval - elapsed
        if remaining > 0:
            self._sleeper(remaining)
            current = self._now()
        self._last_request_at = current

    def _rate_limit_delay(self, retry_after: str | None, attempt: int) -> float:
        if retry_after is not None:
            try:
                parsed = float(retry_after)
                if parsed >= 0:
                    return parsed
            except ValueError:
                pass
        return self._retry_delay(attempt)

    def _sleep_for_retry(self, attempt: int, *, reason: str) -> None:
        delay = self._retry_delay(attempt)
        if delay <= 0:
            return
        logger.debug("Retrying request reason=%s delay=%s", reason, delay)
        self._sleeper(delay)

    def _retry_delay(self, attempt: int) -> float:
        if self._config.backoff_base_seconds <= 0:
            return 0.0
        return self._config.backoff_base_seconds * (
            self._config.backoff_multiplier**attempt
        )

    def _as_non_negative_float(self, value: object, name: str) -> float:
        if isinstance(value, bool):
            raise AuthenticationError(f"{name} must be numeric")
        if isinstance(value, (int, float)):
            result = float(value)
            if result < 0:
                raise AuthenticationError(f"{name} must be non-negative")
            return result
        if isinstance(value, str):
            try:
                result = float(value)
            except ValueError as error:
                raise AuthenticationError(f"{name} must be numeric") from error
            if result < 0:
                raise AuthenticationError(f"{name} must be non-negative")
            return result
        raise AuthenticationError(f"{name} must be numeric")

    def _check_cancelled(self) -> None:
        if self._cancellation_requested():
            raise ProviderError("HTTP request cancelled")

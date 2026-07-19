"""Tests for HttpTidalApiClient with mocked HTTP transport."""

from dataclasses import dataclass, field

import pytest

from tidal_playlist_builder.exceptions import (
    AuthenticationError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from tidal_playlist_builder.tidal.http_client import (
    HttpClientConfig,
    HttpTidalApiClient,
)


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: object | None = None,
        *,
        headers: dict[str, str] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error
        self.headers = headers or {}
        self.text = "body"

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


@dataclass
class _FakeSession:
    actions: list[object]
    calls: list[tuple[str, str, float]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)

    def request(
        self,
        method: str,
        url: str,
        *,
        timeout: float,
        params: dict[str, object] | None = None,
        json: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        del params, json, headers
        self.calls.append((method, url, timeout))
        if not self.actions:
            raise AssertionError("No fake action configured")
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        if isinstance(action, _FakeResponse):
            return action
        raise AssertionError("Unsupported fake action")


def _config() -> HttpClientConfig:
    return HttpClientConfig(
        base_url="https://api.test.local",
        timeout_seconds=10.0,
        max_retries=2,
        backoff_base_seconds=0.1,
        backoff_multiplier=2.0,
        user_agent="tidal-tests/1.0",
        token_refresh_leeway_seconds=0.0,
        min_request_interval_seconds=0.0,
        rate_limit_retry_after_default_seconds=0.3,
    )


def test_authentication_success() -> None:
    session = _FakeSession(
        actions=[
            _FakeResponse(
                200,
                {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": 60,
                },
            )
        ]
    )
    client = HttpTidalApiClient(_config(), session=session)

    token = client.authenticate({"username": "u", "password": "p"})

    assert token == "access"
    assert session.headers["User-Agent"] == "tidal-tests/1.0"


def test_timeout_error_maps_to_network_error() -> None:
    session = _FakeSession(actions=[TimeoutError("timeout")] * 3)
    sleeps: list[float] = []
    client = HttpTidalApiClient(_config(), session=session, sleeper=sleeps.append)

    with pytest.raises(NetworkError, match="transport failed"):
        client.authenticate({"token": "x"})


def test_server_500_retries_then_fails() -> None:
    session = _FakeSession(
        actions=[_FakeResponse(500, {}), _FakeResponse(500, {}), _FakeResponse(500, {})]
    )
    sleeps: list[float] = []
    client = HttpTidalApiClient(_config(), session=session, sleeper=sleeps.append)

    with pytest.raises(ProviderError, match="Server error status=500"):
        client.authenticate({"token": "x"})

    assert sleeps == [0.1, 0.2]


def test_401_triggers_refresh_then_retries() -> None:
    now_values = iter([0.0, 0.0, 0.0, 120.0, 120.0])
    session = _FakeSession(
        actions=[
            _FakeResponse(
                200,
                {"access_token": "old", "refresh_token": "refresh", "expires_in": 60},
            ),
            _FakeResponse(401, {}),
            _FakeResponse(
                200,
                {"access_token": "new", "refresh_token": "refresh", "expires_in": 60},
            ),
            _FakeResponse(200, {"artists": [{"id": "a1", "name": "Artist"}]}),
        ]
    )
    client = HttpTidalApiClient(
        _config(), session=session, now=lambda: next(now_values)
    )
    client.authenticate({"token": "x"})

    artists = client.search_artists("query", 10)

    assert artists == [{"id": "a1", "name": "Artist"}]


def test_429_retries_then_rate_limit_error() -> None:
    session = _FakeSession(
        actions=[
            _FakeResponse(429, {}, headers={"Retry-After": "0.5"}),
            _FakeResponse(429, {}, headers={"Retry-After": "0.5"}),
            _FakeResponse(429, {}, headers={"Retry-After": "0.5"}),
        ]
    )
    sleeps: list[float] = []
    client = HttpTidalApiClient(_config(), session=session, sleeper=sleeps.append)

    with pytest.raises(RateLimitError, match="retry budget exhausted"):
        client.authenticate({"token": "x"})

    assert sleeps == [0.5, 0.5]


def test_invalid_json_maps_to_provider_error() -> None:
    session = _FakeSession(
        actions=[_FakeResponse(200, None, json_error=ValueError("bad json"))]
    )
    client = HttpTidalApiClient(_config(), session=session)

    with pytest.raises(ProviderError, match="Invalid JSON"):
        client.authenticate({"token": "x"})


def test_connection_error_maps_to_network_error() -> None:
    session = _FakeSession(actions=[ConnectionError("offline")] * 3)
    client = HttpTidalApiClient(_config(), session=session)

    with pytest.raises(NetworkError, match="transport failed"):
        client.authenticate({"token": "x"})


def test_retry_exhaustion_for_transport_errors() -> None:
    session = _FakeSession(
        actions=[TimeoutError("one"), TimeoutError("two"), TimeoutError("three")]
    )
    client = HttpTidalApiClient(_config(), session=session)

    with pytest.raises(NetworkError):
        client.authenticate({"token": "x"})


def test_authentication_missing_token_raises_authentication_error() -> None:
    session = _FakeSession(
        actions=[_FakeResponse(200, {"refresh_token": "r", "expires_in": 10})]
    )
    client = HttpTidalApiClient(_config(), session=session)

    with pytest.raises(AuthenticationError, match="missing access_token"):
        client.authenticate({"token": "x"})

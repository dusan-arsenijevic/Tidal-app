"""Tests for tidalapi OAuth transport adapter."""

from __future__ import annotations

import json
from pathlib import Path

from tidal_playlist_builder.tidal.tidalapi_client import (
    TidalApiSdkClient,
    TidalApiSessionConfig,
)


class _FakeFuture:
    def result(self, timeout: float) -> bool:
        del timeout
        return True


class _FakeLink:
    verification_uri_complete = "https://example.test/oauth"
    expires_in = 60


class _FakeSession:
    def __init__(self) -> None:
        self.token_type = "Bearer"
        self.session_id = "session-1"
        self.access_token = "access-1"
        self.refresh_token = "refresh-1"
        self.is_pkce = True
        self._logged_in = False

    def login_oauth(self) -> tuple[_FakeLink, _FakeFuture]:
        self._logged_in = True
        return (_FakeLink(), _FakeFuture())

    def check_login(self) -> bool:
        return self._logged_in

    def save_session_to_file(self, session_file: Path) -> None:
        del session_file
        return

    def load_session_from_file(self, session_file: Path) -> bool:
        if not session_file.exists():
            return False
        self._logged_in = True
        return True


class _FakeTidalModule:
    Session = _FakeSession


def test_authenticate_persists_fallback_session_file(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        TidalApiSdkClient,
        "_load_tidalapi_module",
        lambda self: _FakeTidalModule(),
    )
    monkeypatch.setattr(
        "tidal_playlist_builder.tidal.tidalapi_client.webbrowser.open",
        lambda _url: True,
    )
    session_file = tmp_path / "cache" / "tidalapi-session.json"
    client = TidalApiSdkClient(TidalApiSessionConfig(session_file=session_file))

    result = client.authenticate({"interactive": "true", "remember_session": "true"})

    assert result == "oauth"
    assert session_file.exists()
    payload = json.loads(session_file.read_text(encoding="utf-8"))
    assert payload["access_token"]["data"] == "access-1"


def test_authenticate_restores_saved_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        TidalApiSdkClient,
        "_load_tidalapi_module",
        lambda self: _FakeTidalModule(),
    )
    session_file = tmp_path / "cache" / "tidalapi-session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text("{}", encoding="utf-8")
    client = TidalApiSdkClient(TidalApiSessionConfig(session_file=session_file))

    result = client.authenticate({"interactive": "false"})

    assert result == "session-restored"


def test_authenticate_restores_legacy_session_and_migrates(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        TidalApiSdkClient,
        "_load_tidalapi_module",
        lambda self: _FakeTidalModule(),
    )
    session_file = tmp_path / "session" / "tidalapi-session.json"
    legacy_file = tmp_path / "cache" / "tidalapi-session.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text("{}", encoding="utf-8")
    client = TidalApiSdkClient(
        TidalApiSessionConfig(
            session_file=session_file,
            legacy_session_file=legacy_file,
        )
    )

    result = client.authenticate({"interactive": "false"})

    assert result == "session-restored"
    assert session_file.exists()

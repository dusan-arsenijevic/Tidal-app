"""Secure credential persistence backed by the OS keyring."""

from __future__ import annotations

from importlib import import_module
import json
import logging
from typing import Protocol, cast

from tidal_playlist_builder.exceptions import CredentialStorageError

logger = logging.getLogger(__name__)


class _KeyringModule(Protocol):
    errors: object

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class KeyringCredentialStore:
    """Persists TIDAL credentials in the platform keyring."""

    def __init__(
        self,
        *,
        service_name: str = "tidal-playlist-builder",
        account_name: str = "tidal-login",
    ) -> None:
        self._service_name = service_name
        self._account_name = account_name

    def load(self) -> dict[str, str] | None:
        keyring = self._load_keyring_module()
        payload = keyring.get_password(self._service_name, self._account_name)
        if payload is None or not payload.strip():
            return None
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "Stored credentials payload was invalid JSON; clearing entry"
            )
            self.clear()
            return None
        if not isinstance(parsed, dict):
            self.clear()
            return None
        username = str(parsed.get("username", "")).strip()
        password = str(parsed.get("password", "")).strip()
        if not username or not password:
            self.clear()
            return None
        return {"username": username, "password": password}

    def save(self, *, username: str, password: str) -> None:
        user = username.strip()
        secret = password.strip()
        if not user or not secret:
            raise CredentialStorageError("Username and password are required")
        keyring = self._load_keyring_module()
        payload = json.dumps({"username": user, "password": secret})
        try:
            keyring.set_password(self._service_name, self._account_name, payload)
        except Exception as error:  # pragma: no cover - backend-specific exceptions
            raise CredentialStorageError(
                "Failed to save credentials to secure storage"
            ) from error

    def clear(self) -> None:
        keyring = self._load_keyring_module()
        try:
            keyring.delete_password(self._service_name, self._account_name)
        except Exception as error:  # pragma: no cover - backend-specific exceptions
            errors_module = getattr(keyring, "errors", None)
            password_delete_error = getattr(errors_module, "PasswordDeleteError", None)
            if password_delete_error and isinstance(error, password_delete_error):
                return
            raise CredentialStorageError(
                "Failed to clear credentials from secure storage"
            ) from error

    def _load_keyring_module(self) -> _KeyringModule:
        try:
            return cast(_KeyringModule, import_module("keyring"))
        except ModuleNotFoundError as error:
            raise CredentialStorageError(
                "Secure credential storage backend is not available"
            ) from error

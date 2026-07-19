"""JSON disk cache backend used by CacheService."""

from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
import threading
from time import sleep, time
from typing import Literal
from uuid import uuid4

from tidal_playlist_builder.exceptions import CacheError, ValidationError

logger = logging.getLogger(__name__)

_DiskStatus = Literal["hit", "miss", "expired", "corrupt"]
_CATEGORY_NAMES = ("artist", "album", "playlist", "metadata")


class JsonCacheBackend:
    """Persistent JSON cache backend with TTL and corruption recovery."""

    def __init__(
        self,
        cache_directory: Path | str,
        *,
        now: Callable[[], float] = time,
    ) -> None:
        directory = Path(cache_directory)
        if not str(directory).strip():
            raise ValidationError("cache_directory cannot be empty")
        self._cache_directory = directory
        self._now = now
        self._lock = threading.RLock()
        self._ensure_directories()

    def get_with_status(
        self, key: str
    ) -> tuple[_DiskStatus, object | None, float | None]:
        with self._lock:
            file_path = self._file_path_for_key(key)
            if not file_path.exists():
                logger.debug("Disk cache miss key=%s", key)
                return ("miss", None, None)

            payload = self._load_file(file_path)
            if payload is None:
                return ("corrupt", None, None)

            expires_at = payload.get("expires_at")
            if isinstance(expires_at, (int, float)) and expires_at <= self._now():
                self._delete_file(file_path)
                logger.debug("Disk cache expired key=%s", key)
                return ("expired", None, None)

            serialized = payload.get("value")
            try:
                value = self._deserialize(serialized)
            except CacheError:
                self._delete_file(file_path)
                logger.warning("Disk cache corrupt key=%s", key)
                return ("corrupt", None, None)
            disk_expires_at = (
                expires_at if isinstance(expires_at, (int, float)) else None
            )
            logger.debug("Disk cache hit key=%s", key)
            return ("hit", value, disk_expires_at)

    def set(self, key: str, value: object, expires_at: float | None) -> None:
        with self._lock:
            file_path = self._file_path_for_key(key)
            try:
                serialized_value = self._serialize(value)
            except CacheError:
                logger.exception("Disk cache serialization failed for key=%s", key)
                raise

            payload = {
                "key": key,
                "expires_at": expires_at,
                "value": serialized_value,
            }
            self._atomic_write_json(file_path, payload)
            logger.debug("Disk cache write key=%s", key)

    def invalidate(self, prefix: str) -> None:
        with self._lock:
            for file_path in self._cache_directory.rglob("*.json"):
                payload = self._load_file(file_path)
                if payload is None:
                    continue
                key = payload.get("key")
                if isinstance(key, str) and key.startswith(prefix):
                    self._delete_file(file_path)
            logger.debug("Disk cache invalidated prefix=%s", prefix)

    def clear(self) -> None:
        with self._lock:
            for file_path in self._cache_directory.rglob("*.json"):
                self._delete_file(file_path)
            logger.debug("Disk cache cleared")

    def _ensure_directories(self) -> None:
        try:
            self._cache_directory.mkdir(parents=True, exist_ok=True)
            for category in _CATEGORY_NAMES:
                (self._cache_directory / category).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise CacheError(
                f"Failed to initialize cache directory: {self._cache_directory}"
            ) from error

    def _file_path_for_key(self, key: str) -> Path:
        category_dir = self._cache_directory / self._category_for_key(key)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return category_dir / f"{digest}.json"

    def _category_for_key(self, key: str) -> str:
        head = key.split(":", 1)[0].lower()
        if head.startswith("artist"):
            return "artist"
        if head.startswith("album"):
            return "album"
        if head.startswith("playlist"):
            return "playlist"
        return "metadata"

    def _load_file(self, file_path: Path) -> dict[str, object] | None:
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            logger.warning("Disk cache corrupt file=%s", file_path)
            self._delete_file(file_path)
            return None
        if not isinstance(payload, dict):
            logger.warning("Disk cache invalid payload file=%s", file_path)
            self._delete_file(file_path)
            return None
        return payload

    def _atomic_write_json(
        self, file_path: Path, payload: Mapping[str, object]
    ) -> None:
        temp_name = f"{file_path.name}.{uuid4().hex}.tmp"
        temp_path = file_path.with_name(temp_name)
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"))
            self._replace_with_retry(temp_path, file_path)
        except OSError as error:
            raise CacheError(f"Failed to write cache file: {file_path}") from error
        finally:
            if temp_path.exists():
                self._delete_file(temp_path)

    def _replace_with_retry(self, source: Path, target: Path) -> None:
        for attempt in range(3):
            try:
                source.replace(target)
                return
            except OSError:
                if attempt >= 2:
                    raise
                sleep(0.005)

    def _delete_file(self, file_path: Path) -> None:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed deleting cache file=%s", file_path)

    def _serialize(self, value: object) -> object:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, Enum):
            return {
                "__type__": "enum",
                "class": f"{value.__class__.__module__}.{value.__class__.__name__}",
                "value": self._serialize(value.value),
            }
        if is_dataclass(value):
            dataclass_fields: dict[str, object] = {}
            for field in fields(value):
                dataclass_fields[field.name] = self._serialize(
                    getattr(value, field.name)
                )
            return {
                "__type__": "dataclass",
                "class": f"{value.__class__.__module__}.{value.__class__.__name__}",
                "fields": dataclass_fields,
            }
        if isinstance(value, tuple):
            return {
                "__type__": "tuple",
                "items": [self._serialize(item) for item in value],
            }
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, dict):
            dict_payload: dict[str, object] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise CacheError(
                        "Cache serialization supports only string dict keys"
                    )
                dict_payload[key] = self._serialize(item)
            return dict_payload
        if isinstance(value, frozenset):
            return {
                "__type__": "frozenset",
                "items": [self._serialize(item) for item in value],
            }
        raise CacheError(
            f"Cache serialization unsupported type: {type(value).__name__}"
        )

    def _deserialize(self, payload: object) -> object:
        if payload is None or isinstance(payload, (bool, int, float, str)):
            return payload
        if isinstance(payload, list):
            return [self._deserialize(item) for item in payload]
        if not isinstance(payload, dict):
            raise CacheError("Invalid cache payload structure")

        payload_type = payload.get("__type__")
        if payload_type is None:
            return {key: self._deserialize(value) for key, value in payload.items()}
        if payload_type == "tuple":
            items = payload.get("items")
            if not isinstance(items, list):
                raise CacheError("Invalid tuple payload")
            return tuple(self._deserialize(item) for item in items)
        if payload_type == "frozenset":
            items = payload.get("items")
            if not isinstance(items, list):
                raise CacheError("Invalid frozenset payload")
            return frozenset(self._deserialize(item) for item in items)
        if payload_type == "enum":
            class_path = payload.get("class")
            value_payload = payload.get("value")
            if not isinstance(class_path, str):
                raise CacheError("Invalid enum payload")
            enum_class = self._resolve_class(class_path)
            if not issubclass(enum_class, Enum):
                raise CacheError("Enum payload class is not an enum")
            value = self._deserialize(value_payload)
            return enum_class(value)
        if payload_type == "dataclass":
            class_path = payload.get("class")
            fields_payload = payload.get("fields")
            if not isinstance(class_path, str) or not isinstance(fields_payload, dict):
                raise CacheError("Invalid dataclass payload")
            target_class = self._resolve_class(class_path)
            if not is_dataclass(target_class):
                raise CacheError("Dataclass payload target is not dataclass")
            kwargs = {
                key: self._deserialize(value) for key, value in fields_payload.items()
            }
            return target_class(**kwargs)
        raise CacheError("Unknown payload type marker")

    def _resolve_class(self, class_path: str) -> type[object]:
        try:
            module_name, class_name = class_path.rsplit(".", 1)
        except ValueError as error:
            raise CacheError("Invalid class path in cache payload") from error
        try:
            module = __import__(module_name, fromlist=[class_name])
            class_object = getattr(module, class_name)
        except (ImportError, AttributeError) as error:
            raise CacheError(f"Cannot resolve class: {class_path}") from error
        if not isinstance(class_object, type):
            raise CacheError(f"Resolved object is not a class: {class_path}")
        return class_object

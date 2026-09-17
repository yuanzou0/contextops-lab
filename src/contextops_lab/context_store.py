"""Durable, tenant-scoped storage for exact original context.

The adapter intentionally implements PariTok's small ``ShadowStorage`` protocol by duck typing,
while adding the controls ContextOps needs for a production safety boundary: authenticated
encryption, tenant/session isolation, explicit expiry state, and version metadata.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable


SCHEMA_VERSION = 1


class RetrievalStatus(str, Enum):
    FOUND = "found"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"
    CORRUPT = "corrupt"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    status: RetrievalStatus
    content: str | None = None
    content_version: str | None = None
    expires_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def content_hash(content: str) -> str:
    """Return the identifier format used by PariTok's shadow storage."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _digest(value: str) -> str:
    if not value:
        raise ValueError("tenant_id and session_id must be non-empty")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _decode_key(encoded: str) -> bytes:
    value = encoded.strip()
    if not value:
        raise ValueError("Context storage encryption key is empty")
    try:
        if len(value) == 64:
            key = bytes.fromhex(value)
        else:
            key = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as error:
        raise ValueError("Context storage key must be 32-byte hex or URL-safe base64") from error
    if len(key) != 32:
        raise ValueError("Context storage key must decode to exactly 32 bytes")
    return key


class _AesGcmCodec:
    def __init__(self, encoded_key: str) -> None:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as error:  # pragma: no cover - optional production dependency
            raise RuntimeError(
                "Durable context storage requires cryptography; install contextops-lab[durable]"
            ) from error
        key = _decode_key(encoded_key)
        self._cipher = AESGCM(key)
        self._version_key = hashlib.sha256(key + b"contextops-content-version").digest()

    def content_version(self, content: str) -> str:
        return hmac.new(
            self._version_key,
            content.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def encrypt(self, plaintext: str, *, associated_data: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            associated_data.encode("utf-8"),
        )
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, payload: str, *, associated_data: str) -> str:
        encoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        if len(encoded) < 13:
            raise ValueError("encrypted context payload is truncated")
        plaintext = self._cipher.decrypt(
            encoded[:12],
            encoded[12:],
            associated_data.encode("utf-8"),
        )
        return plaintext.decode("utf-8")


class DurableRedisShadowStorage:
    """Fail-closed Redis storage compatible with PariTok's ``ShadowStorage`` contract."""

    def __init__(
        self,
        client: Any,
        *,
        encryption_key: str,
        tenant_id: str,
        session_id: str,
        ttl_seconds: int = 86_400,
        tombstone_seconds: int = 86_400,
        key_prefix: str = "contextops",
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if tombstone_seconds <= 0:
            raise ValueError("tombstone_seconds must be positive")
        self._client = client
        self._codec = _AesGcmCodec(encryption_key)
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._tombstone_seconds = tombstone_seconds
        self._tenant_digest = _digest(tenant_id)
        self._session_digest = _digest(session_id)
        self._namespace = (
            f"{key_prefix}:v{SCHEMA_VERSION}:{self._tenant_digest}:{self._session_digest}"
        )

    @classmethod
    def from_url(
        cls,
        url: str,
        **kwargs: Any,
    ) -> "DurableRedisShadowStorage":
        if not url:
            raise ValueError("Redis URL is required for durable context storage")
        try:
            import redis
        except ImportError as error:  # pragma: no cover - optional production dependency
            raise RuntimeError(
                "Durable context storage requires redis; install contextops-lab[durable]"
            ) from error
        client = redis.Redis.from_url(url, decode_responses=True)
        try:
            client.ping()
        except Exception as error:
            raise ConnectionError(
                "Durable context storage cannot reach Redis; refusing to fall back to memory"
            ) from error
        return cls(client, **kwargs)

    @property
    def namespace(self) -> str:
        """Return the privacy-safe namespace (raw tenant/session values are never exposed)."""
        return self._namespace

    def _key(self, kind: str, identifier: str) -> str:
        return f"{self._namespace}:{kind}:{identifier}"

    def _associated_data(self, kind: str, identifier: str, version: str) -> str:
        return f"{self._namespace}:{kind}:{identifier}:{version}"

    def _store_encrypted(self, kind: str, identifier: str, content: str) -> str:
        now = self._clock()
        version = self._codec.content_version(content)
        expires_at = now + self._ttl_seconds
        associated_data = self._associated_data(kind, identifier, version)
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "content_version": version,
            "created_at": now,
            "expires_at": expires_at,
            "ciphertext": self._codec.encrypt(content, associated_data=associated_data),
        }
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "content_version": version,
            "expires_at": expires_at,
        }
        value = json.dumps(envelope, separators=(",", ":"), sort_keys=True)
        status_value = json.dumps(metadata, separators=(",", ":"), sort_keys=True)
        pipeline_factory = getattr(self._client, "pipeline", None)
        if pipeline_factory:
            pipeline = pipeline_factory(transaction=True)
            pipeline.set(
                self._key(kind, identifier),
                value,
                ex=self._ttl_seconds,
            )
            pipeline.set(
                self._key(f"{kind}_status", identifier),
                status_value,
                ex=self._ttl_seconds + self._tombstone_seconds,
            )
            pipeline.execute()
        else:  # Minimal injected clients used by deterministic unit tests.
            self._client.set(
                self._key(kind, identifier),
                value,
                ex=self._ttl_seconds,
            )
            self._client.set(
                self._key(f"{kind}_status", identifier),
                status_value,
                ex=self._ttl_seconds + self._tombstone_seconds,
            )
        return version

    def _retrieve_encrypted(self, kind: str, identifier: str) -> RetrievalResult:
        try:
            raw = self._client.get(self._key(kind, identifier))
            status_raw = self._client.get(self._key(f"{kind}_status", identifier))
        except Exception:
            return RetrievalResult(RetrievalStatus.UNHEALTHY)
        if raw is None:
            if status_raw is None:
                return RetrievalResult(RetrievalStatus.NOT_FOUND)
            try:
                metadata = json.loads(status_raw)
                expires_at = float(metadata["expires_at"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return RetrievalResult(RetrievalStatus.CORRUPT)
            status = RetrievalStatus.EXPIRED if expires_at <= self._clock() else RetrievalStatus.CORRUPT
            return RetrievalResult(
                status,
                content_version=str(metadata.get("content_version") or "") or None,
                expires_at=expires_at,
            )
        try:
            envelope = json.loads(raw)
            if int(envelope["schema_version"]) != SCHEMA_VERSION:
                return RetrievalResult(RetrievalStatus.CORRUPT)
            version = str(envelope["content_version"])
            expires_at = float(envelope["expires_at"])
            if expires_at <= self._clock():
                return RetrievalResult(
                    RetrievalStatus.EXPIRED,
                    content_version=version,
                    expires_at=expires_at,
                )
            content = self._codec.decrypt(
                str(envelope["ciphertext"]),
                associated_data=self._associated_data(kind, identifier, version),
            )
            if not hmac.compare_digest(self._codec.content_version(content), version):
                return RetrievalResult(RetrievalStatus.CORRUPT)
            return RetrievalResult(
                RetrievalStatus.FOUND,
                content=content,
                content_version=version,
                expires_at=expires_at,
            )
        except Exception:
            return RetrievalResult(RetrievalStatus.CORRUPT)

    def store(self, content: str) -> str:
        shadow_id = content_hash(content)
        self._store_encrypted("shadow", shadow_id, content)
        return shadow_id

    def retrieve_with_status(self, shadow_id: str) -> RetrievalResult:
        return self._retrieve_encrypted("shadow", shadow_id)

    def retrieve(self, shadow_id: str) -> str | None:
        return self.retrieve_with_status(shadow_id).content

    def has(self, shadow_id: str) -> bool:
        return self.retrieve_with_status(shadow_id).status is RetrievalStatus.FOUND

    def cache_compressed(self, shadow_id: str, compressed: str) -> None:
        self._store_encrypted("cache", shadow_id, compressed)

    def get_cached_compressed(self, shadow_id: str) -> str | None:
        return self._retrieve_encrypted("cache", shadow_id).content

    def invalidate_compressed(self, shadow_id: str) -> None:
        self._client.delete(
            self._key("cache", shadow_id),
            self._key("cache_status", shadow_id),
        )

    def set_shadow_for_path(self, path: str, shadow_id: str) -> None:
        if not path:
            return
        result = self.retrieve_with_status(shadow_id)
        if result.status is not RetrievalStatus.FOUND:
            raise ValueError("Cannot map a path to an unavailable shadow reference")
        path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
        mapping_key = self._key("path", path_id)
        try:
            previous = self._client.get(mapping_key)
            history = list(json.loads(previous).get("shadow_ids", [])) if previous else []
        except Exception:
            history = []
        if shadow_id in history:
            history.remove(shadow_id)
        history.append(shadow_id)
        history = history[-8:]
        mapping = json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "shadow_id": shadow_id,
                "shadow_ids": history,
                "content_version": result.content_version,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        self._client.set(mapping_key, mapping, ex=self._ttl_seconds)
        self._store_encrypted("shadow_path", shadow_id, path)

    def get_shadow_for_path(self, path: str) -> str | None:
        if not path:
            return None
        path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
        try:
            raw = self._client.get(self._key("path", path_id))
            if raw is None:
                return None
            shadow_id = str(json.loads(raw)["shadow_id"])
        except Exception:
            return None
        return shadow_id if self.has(shadow_id) else None

    def get_shadows_for_path(self, path: str) -> list[str]:
        if not path:
            return []
        path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
        try:
            raw = self._client.get(self._key("path", path_id))
            history = list(json.loads(raw).get("shadow_ids", [])) if raw else []
        except Exception:
            return []
        return [shadow_id for shadow_id in reversed(history) if self.has(shadow_id)]

    def get_path_for_shadow(self, shadow_id: str) -> str | None:
        if not shadow_id:
            return None
        return self._retrieve_encrypted("shadow_path", shadow_id).content

    def pin_source(self, path: str) -> None:
        if path:
            path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
            self._client.set(self._key("pinned_path", path_id), "1", ex=self._ttl_seconds)

    def is_source_pinned(self, path: str) -> bool:
        if not path:
            return False
        path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
        try:
            return bool(self._client.exists(self._key("pinned_path", path_id)))
        except Exception:
            return False

    def pin_shadow(self, shadow_id: str) -> None:
        if shadow_id:
            self._client.set(
                self._key("pinned_shadow", shadow_id),
                "1",
                ex=self._ttl_seconds,
            )

    def is_shadow_pinned(self, shadow_id: str) -> bool:
        if not shadow_id:
            return False
        try:
            return bool(self._client.exists(self._key("pinned_shadow", shadow_id)))
        except Exception:
            return False

    def health(self) -> dict[str, Any]:
        try:
            healthy = bool(self._client.ping())
        except Exception:
            healthy = False
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if healthy else "unhealthy",
            "backend": "redis",
            "namespace": self._namespace,
            "encryption": "aes-256-gcm",
            "ttl_seconds": self._ttl_seconds,
            "explicit_expiry_status": True,
            "raw_tenant_or_session_recorded": False,
        }

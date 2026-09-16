import base64
import hashlib
import os
import unittest
from io import StringIO
from unittest.mock import patch

from contextops_lab.cache_safety import build_paritok_storage
from contextops_lab.cli import build_parser, run_safe_proxy_command
from contextops_lab.context_store import DurableRedisShadowStorage, RetrievalStatus


class FakeClock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeRedis:
    def __init__(self, clock):
        self.clock = clock
        self.values = {}
        self.expiries = {}
        self.available = True

    def ping(self):
        if not self.available:
            raise ConnectionError("redis unavailable")
        return True

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.expiries[key] = self.clock() + ex if ex is not None else None
        return True

    def get(self, key):
        if not self.available:
            raise ConnectionError("redis unavailable")
        expires_at = self.expiries.get(key)
        if expires_at is not None and expires_at <= self.clock():
            self.values.pop(key, None)
            self.expiries.pop(key, None)
            return None
        return self.values.get(key)

    def exists(self, key):
        return int(self.get(key) is not None)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.expiries.pop(key, None)


class DurableContextStoreTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.redis = FakeRedis(self.clock)
        self.key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")

    def build(self, *, tenant="tenant-a", session="session-1", ttl=60):
        return DurableRedisShadowStorage(
            self.redis,
            encryption_key=self.key,
            tenant_id=tenant,
            session_id=session,
            ttl_seconds=ttl,
            tombstone_seconds=120,
            clock=self.clock,
        )

    def test_exact_original_survives_process_reconstruction(self):
        original = "secret source\nCRITICAL_SIGNAL: exact-bytes\n"
        first_process = self.build()
        shadow_id = first_process.store(original)

        restarted_process = self.build()
        result = restarted_process.retrieve_with_status(shadow_id)

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertEqual(result.content, original)
        self.assertEqual(len(result.content_version), 64)
        self.assertNotEqual(result.content_version, hashlib.sha256(original.encode()).hexdigest())
        self.assertTrue(restarted_process.has(shadow_id))

    def test_tenant_and_session_namespaces_are_isolated(self):
        original = "same content produces the same public reference"
        owner = self.build(tenant="tenant-a", session="session-1")
        shadow_id = owner.store(original)

        other_tenant = self.build(tenant="tenant-b", session="session-1")
        other_session = self.build(tenant="tenant-a", session="session-2")

        self.assertEqual(
            other_tenant.retrieve_with_status(shadow_id).status,
            RetrievalStatus.NOT_FOUND,
        )
        self.assertEqual(
            other_session.retrieve_with_status(shadow_id).status,
            RetrievalStatus.NOT_FOUND,
        )
        self.assertEqual(owner.retrieve(shadow_id), original)

    def test_expired_reference_has_explicit_status_without_plaintext_retention(self):
        store = self.build(ttl=10)
        shadow_id = store.store("short-lived original")
        self.clock.advance(11)

        result = store.retrieve_with_status(shadow_id)

        self.assertEqual(result.status, RetrievalStatus.EXPIRED)
        self.assertIsNone(result.content)
        self.assertIsNotNone(result.content_version)
        self.assertFalse(store.has(shadow_id))

    def test_redis_values_and_keys_do_not_contain_raw_context_or_scope(self):
        store = self.build(tenant="private-tenant", session="private-session")
        original = "api_key=do-not-store-this-in-plaintext"
        store.store(original)

        persisted = "\n".join(f"{key}\n{value}" for key, value in self.redis.values.items())
        self.assertNotIn(original, persisted)
        self.assertNotIn("private-tenant", persisted)
        self.assertNotIn("private-session", persisted)
        self.assertEqual(store.health()["encryption"], "aes-256-gcm")

    def test_path_version_and_query_aware_cache_use_durable_backend(self):
        durable = self.build()
        storage = build_paritok_storage(
            "query_aware",
            backend="redis",
            base_storage=durable,
        )
        shadow_id = storage.store("versioned original")
        storage.set_shadow_for_path("src/service.py", shadow_id)
        storage.set_active_query("first intent")
        storage.cache_compressed(shadow_id, "first summary")

        self.assertEqual(storage.get_shadow_for_path("src/service.py"), shadow_id)
        self.assertEqual(storage.get_cached_compressed(shadow_id), "first summary")
        storage.set_active_query("changed intent")
        self.assertIsNone(storage.get_cached_compressed(shadow_id))
        self.assertEqual(storage.retrieve(shadow_id), "versioned original")

        newer_shadow_id = storage.store("versioned original v2")
        storage.set_shadow_for_path("src/service.py", newer_shadow_id)
        self.assertEqual(storage.get_shadow_for_path("src/service.py"), newer_shadow_id)
        self.assertEqual(
            storage.get_shadows_for_path("src/service.py"),
            [newer_shadow_id, shadow_id],
        )
        self.assertEqual(storage.get_path_for_shadow(shadow_id), "src/service.py")
        storage.pin_source("src/service.py")
        storage.pin_shadow(shadow_id)
        self.assertTrue(storage.is_source_pinned("src/service.py"))
        self.assertTrue(storage.is_shadow_pinned(shadow_id))

    def test_pins_and_reverse_path_mapping_survive_process_reconstruction(self):
        first_process = self.build()
        shadow_id = first_process.store("expanded original")
        first_process.set_shadow_for_path("src/expanded.py", shadow_id)
        first_process.pin_source("src/expanded.py")
        first_process.pin_shadow(shadow_id)

        restarted_process = self.build()
        self.assertTrue(restarted_process.is_source_pinned("src/expanded.py"))
        self.assertTrue(restarted_process.is_shadow_pinned(shadow_id))
        self.assertEqual(
            restarted_process.get_path_for_shadow(shadow_id),
            "src/expanded.py",
        )
        other_tenant = self.build(tenant="tenant-b")
        self.assertFalse(other_tenant.is_source_pinned("src/expanded.py"))
        self.assertFalse(other_tenant.is_shadow_pinned(shadow_id))

    def test_corrupt_and_unhealthy_storage_fail_closed(self):
        store = self.build()
        shadow_id = store.store("protected original")
        shadow_key = next(key for key in self.redis.values if ":shadow:" in key)
        self.redis.values[shadow_key] = "not-json"
        self.assertEqual(
            store.retrieve_with_status(shadow_id).status,
            RetrievalStatus.CORRUPT,
        )
        self.redis.available = False
        self.assertEqual(
            store.retrieve_with_status(shadow_id).status,
            RetrievalStatus.UNHEALTHY,
        )
        self.assertEqual(store.health()["status"], "unhealthy")

    def test_wrong_encryption_key_cannot_recover_original(self):
        store = self.build()
        shadow_id = store.store("key-scoped original")
        wrong_key = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode("ascii")
        restarted_with_wrong_key = DurableRedisShadowStorage(
            self.redis,
            encryption_key=wrong_key,
            tenant_id="tenant-a",
            session_id="session-1",
            clock=self.clock,
        )
        result = restarted_with_wrong_key.retrieve_with_status(shadow_id)
        self.assertEqual(result.status, RetrievalStatus.CORRUPT)
        self.assertIsNone(result.content)

    def test_safe_proxy_defaults_to_fail_closed_redis_configuration(self):
        args = build_parser().parse_args(["safe-proxy"])
        self.assertEqual(args.storage_backend, "redis")
        with patch.dict(os.environ, {}, clear=True), patch("sys.stderr", new=StringIO()):
            self.assertEqual(run_safe_proxy_command(args), 2)

    def test_memory_storage_requires_explicit_cli_override(self):
        args = build_parser().parse_args(["safe-proxy", "--storage-backend", "memory"])
        self.assertEqual(args.storage_backend, "memory")


if __name__ == "__main__":
    unittest.main()

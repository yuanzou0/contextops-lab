# Durable original-context storage

ContextOps keeps exact original context recoverable without treating PariTok's process memory as a
production durability boundary. The adapter in `contextops_lab.context_store` implements PariTok's
`store`, `retrieve`, compressed-cache, and path-mapping methods while adding isolation, encryption,
version metadata, and explicit retrieval states.

## Production contract

The `safe-proxy` command selects Redis by default. Startup requires:

- `CONTEXTOPS_REDIS_URL`: a Redis connection URL supplied through the environment;
- `CONTEXTOPS_STORAGE_KEY`: a 32-byte key encoded as URL-safe base64 or 64 hexadecimal characters;
- `--tenant-id`: the tenant isolation scope; and
- `--session-id`: the session isolation scope.

```bash
export CONTEXTOPS_REDIS_URL='redis://127.0.0.1:6379/0'
export CONTEXTOPS_STORAGE_KEY='<secret-manager value>'

contextops-lab safe-proxy \
  --tenant-id evaluation \
  --session-id recovery-001 \
  --storage-ttl-seconds 86400 \
  --cache-contract query_aware
```

If Redis, its client package, or the encryption key is unavailable, startup fails. ContextOps does
not inherit PariTok's permissive Redis-to-memory fallback. `--storage-backend memory` is available
only as an explicit development/test choice.

## Data model and privacy boundary

Every key is scoped as:

```text
contextops:v1:<tenant-sha256-prefix>:<session-sha256-prefix>:<kind>:<identifier>
```

Raw tenant and session identifiers are not placed in Redis keys. Original and compressed values
are encrypted independently with AES-256-GCM. The namespace, kind, identifier, and content version
are authenticated as associated data, preventing ciphertext from being moved silently across
sessions or record types.

The encrypted envelope records:

- schema version;
- keyed HMAC-SHA-256 content version;
- creation time;
- expiry time; and
- ciphertext.

File paths are represented by hashes in Redis keys. Forward mappings retain the eight most recent
shadow references and their versions. Reverse path values are encrypted, so edit recovery and
PariTok 1.3.11's expand-to-pin behavior survive restarts without exposing raw paths. Source and
shadow pin markers share the same tenant/session TTL boundary.

## Retrieval states

`retrieve_with_status` returns one of:

| Status | Meaning | Safe behavior |
|---|---|---|
| `found` | Authenticated content is present and unexpired | Return exact original bytes |
| `expired` | Content TTL elapsed; metadata tombstone remains | Do not return content; report expiry |
| `not_found` | No record exists in this tenant/session scope | Do not search another scope |
| `corrupt` | Envelope, ciphertext, version, or Redis state is inconsistent | Fail closed and alert |
| `unhealthy` | Redis cannot be read | Fail closed and alert |

The tombstone retains only version and expiry metadata for one additional TTL window. It exists so
an expired reference is distinguishable from a never-valid or cross-tenant reference without
retaining plaintext.

## Verification boundary

The deterministic suite covers reconstruction of a new storage object over the same persistent
client, expiry, tenant and session isolation, absence of plaintext at rest, path/version mapping,
query-aware cache behavior, corruption, and backend failure.

These tests establish the adapter contract. They do not claim that a particular Redis deployment,
backup policy, key-management system, failover topology, or production restart drill has been
validated. Those remain release-infrastructure checks in `release-checklist.md`.

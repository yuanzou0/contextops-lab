# Changelog

This project follows semantic versioning for its Python package and keeps evidence claims
versioned separately from code releases.

## [0.9.0] - Unreleased

- add a PariTok-compatible, tenant/session-scoped Redis context store;
- encrypt exact originals and compressed-cache values with AES-256-GCM;
- record content versions and preserve explicit expired-reference tombstones;
- persist PariTok 1.3.11 path history, reverse lookup, and expand-to-pin state across restarts;
- make Redis the safe-proxy production default and fail closed when its URL or encryption key is
  missing;
- retain in-memory storage only as an explicit development/test override; and
- cover restart reconstruction, TTL expiry, namespace isolation, ciphertext-at-rest, corruption,
  and backend-unavailable behavior with deterministic tests; and
- move GitHub CI actions to their Node.js 24-backed releases.

Release boundary:

- no live Redis deployment or process-restart drill has been recorded on release infrastructure;
- durable storage does not change the failed Wave A outcome or unlock production rollout; and
- provider-backed terminal-task recovery remains unproven.

## [0.8.0] - 2026-09-05

Release-candidate scope:

- add a fail-closed cache contract for multi-turn workloads;
- add query-aware and cache-disabled isolation modes around PariTok;
- validate compressed segments and forward the exact original on rejection;
- expose privacy-safe ContextOps safety telemetry beside the upstream proxy;
- add provider-free cache and transformed-context regression protocols;
- add evidence gates that prevent proxy metrics from being presented as independently reviewed
  semantic quality;
- upgrade the default live dependency from PariTok 1.3.3 to 1.3.11;
- test both the historical 1.3.3 dependency and the current 1.3.11 default in CI; and
- add a machine-readable PariTok compatibility contract and CLI audit.

Known release boundary:

- the historical Wave A result remains a STOP/OFF result from PariTok 1.3.3;
- current provider-backed recovery and production non-inferiority are not yet established; and
- a real local PariTok 4B/Ollama run is required on release infrastructure before the candidate
  can be tagged.

## [0.7.0] - 2026-08-14

- publish the initial live Luna smoke evidence and keep rollout disabled;
- add staged long-context workloads and multi-turn live experiment gates; and
- retain explicit provenance for cost, latency, and task-proxy evidence.

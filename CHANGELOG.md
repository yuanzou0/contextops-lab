# Changelog

This project follows semantic versioning for its Python package and keeps evidence claims
versioned separately from code releases.

## [0.8.0] - Unreleased

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

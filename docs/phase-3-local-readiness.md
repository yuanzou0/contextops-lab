# Phase 3 local-runtime readiness

Observed on 2026-08-12 with no paid provider calls.

## Result

- PariTok package 1.3.3: gateway health and zero-traffic telemetry passed.
- Ollama 0.32.9: `paritok-4b-v1:latest` was present locally (4B Qwen3, Q4_K_M, 8,192 runtime context).
- Direct compression test: 15,314 input tokens became 506 tokens, saving 14,808 (96.7%).
- The required deployment identifier was preserved exactly and a shadow reference was created.
- The provider key was absent, so no OpenAI completion was attempted.

The gateway `/health` payload reports `version=1.0.0`, while the installed Python distribution is
1.3.3. The readiness record keeps both fields instead of treating the health value as the package
version.

## Scope

This proves local model availability and one compression-path invariant. It does not prove task
non-inferiority, provider cost savings, latency performance, or rollout suitability. Those claims
remain gated on the paid Luna smoke experiment and the subsequent Terra formal matrix.

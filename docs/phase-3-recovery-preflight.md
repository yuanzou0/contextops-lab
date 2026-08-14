# Phase 3 workload audit

- Suite: `contextops-phase3-matrix-v1`
- Stage: `wave_a`
- Model: `gpt-5.6-luna`
- Pricing: `openai-2026-08-12`
- Scenarios: 4
- Paired requests: 40
- Estimated paired input tokens before compression: 968,346
- Estimated input-only upper bound: $0.9683

> This is a preflight estimate, not measured evidence. It excludes output tokens and PariTok compute. Treatment input should be lower when compression is active.

| Scenario | Type | History payload | Turns | Tools | Risk | Input tokens/arm | Baseline input cost |
|---|---|---:|---:|---:|---|---:|---:|
| `read-heavy-32k-5t` | read_heavy | 32,000 | 5 | 24 | medium | 111,098 | $0.1111 |
| `debugging-32k-5t` | debugging | 32,000 | 5 | 36 | medium | 118,451 | $0.1185 |
| `mcp-heavy-32k-5t` | mcp_heavy | 32,000 | 5 | 72 | medium | 140,787 | $0.1408 |
| `edit-critical-32k-5t` | edit_critical | 32,000 | 5 | 28 | high | 113,837 | $0.1138 |

## Interpretation guardrails

- Smoke results validate integration only and cannot authorize rollout.
- Edit-critical scenarios require exact preservation of all critical signals.
- The 8K/32K/128K band is message-history payload; tool schemas are measured overhead.
- Report context cohorts separately; do not hide segment failures in a global mean.
- Promote from smoke to core and extended only after the preceding stage passes.

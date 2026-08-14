# Phase 3 workload audit

- Suite: `contextops-phase3-matrix-v1`
- Stage: `evidence`
- Model: `gpt-5.6-luna`
- Pricing: `openai-2026-08-12`
- Scenarios: 20
- Paired requests: 248
- Estimated paired input tokens before compression: 12,425,174
- Estimated input-only upper bound: $12.4252

> This is a preflight estimate, not measured evidence. It excludes output tokens and PariTok compute. Treatment input should be lower when compression is active.

| Scenario | Type | History payload | Turns | Tools | Risk | Input tokens/arm | Baseline input cost |
|---|---|---:|---:|---:|---|---:|---:|
| `read-heavy-32k-1t` | read_heavy | 32,000 | 1 | 24 | medium | 34,993 | $0.0350 |
| `read-heavy-32k-5t` | read_heavy | 32,000 | 5 | 24 | medium | 111,098 | $0.1111 |
| `read-heavy-32k-10t` | read_heavy | 32,000 | 10 | 24 | medium | 206,507 | $0.2065 |
| `read-heavy-128k-5t` | read_heavy | 128,000 | 5 | 24 | medium | 400,955 | $0.4010 |
| `read-heavy-128k-10t` | read_heavy | 128,000 | 10 | 24 | medium | 737,941 | $0.7379 |
| `debugging-32k-1t` | debugging | 32,000 | 1 | 36 | medium | 36,464 | $0.0365 |
| `debugging-32k-5t` | debugging | 32,000 | 5 | 36 | medium | 118,451 | $0.1185 |
| `debugging-32k-10t` | debugging | 32,000 | 10 | 36 | medium | 221,198 | $0.2212 |
| `debugging-128k-5t` | debugging | 128,000 | 5 | 36 | medium | 408,274 | $0.4083 |
| `debugging-128k-10t` | debugging | 128,000 | 10 | 36 | medium | 752,553 | $0.7526 |
| `mcp-heavy-32k-1t` | mcp_heavy | 32,000 | 1 | 72 | medium | 40,933 | $0.0409 |
| `mcp-heavy-32k-5t` | mcp_heavy | 32,000 | 5 | 72 | medium | 140,787 | $0.1408 |
| `mcp-heavy-32k-10t` | mcp_heavy | 32,000 | 10 | 72 | medium | 265,868 | $0.2659 |
| `mcp-heavy-128k-5t` | mcp_heavy | 128,000 | 5 | 72 | medium | 430,655 | $0.4307 |
| `mcp-heavy-128k-10t` | mcp_heavy | 128,000 | 10 | 72 | medium | 797,313 | $0.7973 |
| `edit-critical-32k-1t` | edit_critical | 32,000 | 1 | 28 | high | 35,535 | $0.0355 |
| `edit-critical-32k-5t` | edit_critical | 32,000 | 5 | 28 | high | 113,837 | $0.1138 |
| `edit-critical-32k-10t` | edit_critical | 32,000 | 10 | 28 | high | 212,072 | $0.2121 |
| `edit-critical-128k-5t` | edit_critical | 128,000 | 5 | 28 | high | 403,685 | $0.4037 |
| `edit-critical-128k-10t` | edit_critical | 128,000 | 10 | 28 | high | 743,468 | $0.7435 |

## Interpretation guardrails

- Smoke results validate integration only and cannot authorize rollout.
- Edit-critical scenarios require exact preservation of all critical signals.
- The 8K/32K/128K band is message-history payload; tool schemas are measured overhead.
- Report context cohorts separately; do not hide segment failures in a global mean.
- Promote from smoke to core and extended only after the preceding stage passes.

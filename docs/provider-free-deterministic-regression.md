# Provider-free transformed-context regression

- Engine: `deterministic`
- Evidence: `provider_free_deterministic_transformed_context_regression`
- PariTok: `1.3.3`
- Provider requests / cost: 0 / $0.00
- Scenarios: 4
- Conditions: content_only, disabled, query_aware
- Raw content recorded: no

## Prespecified outcomes

- Cache behavior: PASS
- Guarded signal safety: PASS (36/36)
- Raw compression signal quality: FAIL (24/36)
- Recovery-condition raw quality: PASS
- Wave B eligible: no

| Workload | Condition | Cross-query hits | Replay hits | Raw recall | Guarded recall | Fallbacks |
|---|---|---:|---:|---:|---:|---:|
| read_heavy | content_only | 3 | 3 | 0/3 | 3/3 | 3 |
| debugging | content_only | 3 | 3 | 0/3 | 3/3 | 3 |
| mcp_heavy | content_only | 3 | 3 | 0/3 | 3/3 | 3 |
| edit_critical | content_only | 3 | 3 | 0/3 | 3/3 | 3 |
| read_heavy | disabled | 0 | 0 | 3/3 | 3/3 | 0 |
| debugging | disabled | 0 | 0 | 3/3 | 3/3 | 0 |
| mcp_heavy | disabled | 0 | 0 | 3/3 | 3/3 | 0 |
| edit_critical | disabled | 0 | 0 | 3/3 | 3/3 | 0 |
| read_heavy | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |
| debugging | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |
| mcp_heavy | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |
| edit_critical | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |

## Interpretation boundary

Measures transformed-context signal retention and cache/fallback mechanics without an upstream agent provider. It does not measure end-task semantic quality, provider behavior, or synchronous latency eligibility.

Passing guarded safety means unsafe transformed segments were replaced by exact original content in this directly observable pipeline. Passing raw compression quality is a separate and stricter requirement for a recovery pilot.

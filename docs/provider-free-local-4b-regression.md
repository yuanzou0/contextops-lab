# Provider-free transformed-context regression

- Engine: `local_paritok_4b`
- Evidence: `provider_free_local_paritok_4b_transformed_context_regression`
- PariTok: `1.3.3`
- Provider requests / cost: 0 / $0.00
- Scenarios: 4
- Conditions: query_aware
- Raw content recorded: no

## Prespecified outcomes

- Cache behavior: PASS
- Guarded signal safety: PASS (12/12)
- Raw compression signal quality: PASS (12/12)
- Recovery-condition raw quality: PASS
- Wave B eligible: no

| Workload | Condition | Cross-query hits | Replay hits | Raw recall | Guarded recall | Fallbacks |
|---|---|---:|---:|---:|---:|---:|
| read_heavy | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |
| debugging | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |
| mcp_heavy | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |
| edit_critical | query_aware | 0 | 3 | 3/3 | 3/3 | 0 |

## Interpretation boundary

Measures transformed-context signal retention and cache/fallback mechanics without an upstream agent provider. It does not measure end-task semantic quality, provider behavior, or synchronous latency eligibility.

Passing guarded safety means unsafe transformed segments were replaced by exact original content in this directly observable pipeline. Passing raw compression quality is a separate and stricter requirement for a recovery pilot.

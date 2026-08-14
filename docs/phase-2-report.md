# ContextOps Lab — Phase 2 Product-Loop Report

**Generated:** 2026-08-14
**Evidence level:** offline_deterministic

## Decision

Production rollout remains **locked** unless the policy evidence label is `production`. Offline recommendations validate segmentation and decision logic only.

## Workload policy recommendations

| Workload | Paired tasks | Task-proxy Δ (95% CI) | Cost improvement | Fallback | Mode | Reasons |
|---|---:|---:|---:|---:|---|---|
| debugging | 8 | 0.0% [-32.4%, 32.4%] | 54.8% | 0.0% | off | success_non_inferiority_failed |
| edit_critical | 6 | 0.0% [-39.0%, 39.0%] | 56.4% | 0.0% | off | success_non_inferiority_failed |
| intent_pivot | 4 | 0.0% [-49.0%, 49.0%] | 54.8% | 0.0% | off | insufficient_sample, success_non_inferiority_failed |
| log_analysis | 4 | 0.0% [-49.0%, 49.0%] | 56.5% | 0.0% | off | insufficient_sample, success_non_inferiority_failed |
| mcp_heavy | 4 | 0.0% [-49.0%, 49.0%] | 56.8% | 0.0% | off | insufficient_sample, success_non_inferiority_failed |
| read_heavy | 6 | 0.0% [-39.0%, 39.0%] | 46.1% | 16.7% | off | success_non_inferiority_failed |
| short_simple | 4 | 0.0% [-49.0%, 49.0%] | 41.0% | 25.0% | off | insufficient_sample, success_non_inferiority_failed |

## Failure analysis

| Category | Reason | Count | Event rate |
|---|---|---:|---:|
| validation_fallback | empty_output | 2 | 2.8% |

## Product controls delivered

- self-contained analytics dashboard with workload filtering;
- versioned evidence-gated rollout policy;
- runtime `off`, `conservative`, and `balanced` strategies;
- failure taxonomy with structured reason aggregation;
- `doctor` checks for task pairing, privacy schema, policy integrity, and live adapters;
- reproducible data lineage manifest for generated artifacts.
- timestamped, versioned experiment and pricing metadata with duplicate-event checks.

## Next evidence gate

Run representative live tasks through the configured compressor and agent endpoint. Do not change `production_ready` manually; regenerate policy from production-labeled evidence.

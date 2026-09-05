# ContextOps Lab — Phase 1 Analysis Report

**Generated:** 2026-08-14
**Evidence level:** offline deterministic pipeline validation

## Executive conclusion

This report validates the paired-experiment, safety fallback, event, and analytics pipeline. It is not evidence that PariTok or another production compressor reduces real-world cost. A production recommendation requires live model runs.

## Overall results

| Arm | Runs | Task-proxy success | Cost / proxy success | Fallback | P95 latency | Token ratio |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 36 | 100.0% | 0.000300 | 0.0% | 14.0 ms | 100.0% |
| compressed | 36 | 100.0% | 0.000142 | 5.6% | 12.6 ms | 29.2% |

## Workload segmentation

| Workload | Compressed runs | Task-proxy success | Fallback | Token ratio |
|---|---:|---:|---:|---:|
| debugging | 8 | 100.0% | 0.0% | 25.7% |
| edit_critical | 6 | 100.0% | 0.0% | 24.8% |
| intent_pivot | 4 | 100.0% | 0.0% | 25.7% |
| log_analysis | 4 | 100.0% | 0.0% | 24.4% |
| mcp_heavy | 4 | 100.0% | 0.0% | 24.1% |
| read_heavy | 6 | 100.0% | 16.7% | 37.5% |
| short_simple | 4 | 100.0% | 25.0% | 43.8% |

## Release decision

**Decision: do not enable production rollout yet.** The offline fixture demonstrates that rejected compression returns exact original context and remains observable. The next evidence gate is a live paired run using the same agent model, task snapshot, temperature, tools, and retry policy in both arms.

## Known limitations

- Task outcomes use a deterministic marker oracle, not human or model-based grading.
- Costs and latency are fixture measurements used to validate calculation paths.
- The 36 cases are executable pipeline fixtures, not a representative production sample.
- No upstream PariTok benchmark or savings claim is reproduced here.

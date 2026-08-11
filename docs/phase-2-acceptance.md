# ContextOps Lab — Phase 2 Acceptance Criteria

## 9. Analytics dashboard

- Generates as a self-contained HTML artifact with no external service dependency.
- Shows success delta, cost per successful task improvement, fallback rate, and rollout state.
- Supports workload views by task type, language, repository size, session length, tool density, and model.
- Displays an explicit evidence label and never presents offline fixture results as production impact.

## 10. Workload segmentation

- Uses only fully paired baseline/compressed tasks.
- Reports sample size, success-rate difference with 95% bounds, cost improvement, latency delta, and fallback rate.
- Keeps failed tasks in the denominator.

## 11. Failure analysis

- Separates validation fallback, task failure, test failure, manual intervention, upstream error, and silent failure.
- Preserves structured fallback reasons without storing prompts or raw source content.

## 12. Rollout policy

- Stores thresholds, per-segment metrics, reasons, and recommended modes in versioned JSON.
- Defaults unknown workloads to `off`.
- Blocks production authorization for any evidence label other than `production`.
- Treats confidence-bound non-inferiority, silent failure, cost, latency, fallback, and sample size as gates.

## 13. Runtime strategies

- `off`: forwards original context and does not invoke compression.
- `conservative`: preserves edit-critical context and uses a stricter compression bound.
- `balanced`: enables validated compression with exact-original fallback.

## 14. Doctor command

- Checks Python, executable cases, paired events, privacy schema, policy integrity, compressor availability, endpoint validity, and API-key presence.
- Returns a failing process status for blocking problems and warnings for optional live integrations.

## Additional product controls

- Every generated artifact is tied to its input dataset through a SHA-256 lineage manifest.
- Events include timestamp, experiment-configuration version, and pricing version for reproducible economics.
- Duplicate event identities and incomplete experiment pairs are blocking data-quality failures.
- Dashboard recommendations and runtime authorization remain separate concepts.
- Live production evidence is still required before rollout is unlocked.

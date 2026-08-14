# Phase 3 acceptance — production-shaped evidence

## Purpose

Phase 3 replaces the fixture compressor path with a real paired-endpoint contract:

- baseline arm: call the model provider directly;
- treatment arm: call the same model through the PariTok proxy;
- hold task, model, temperature, seed, grader, and price version constant;
- attribute treatment token changes from isolated `/stats` snapshots;
- store hashes and metadata, never prompts, source code, credentials, or raw files.

## Engineering acceptance

- [x] Versioned, secret-free live experiment configuration.
- [x] Identical-model direct/proxy paired executor.
- [x] PariTok `/health` and `/stats` client.
- [x] Fail-closed telemetry attribution when concurrent proxy traffic is detected.
- [x] Provider usage, proxy token delta, endpoint role, config hash, and pricing version in schema v4.
- [x] Bounded HTTP retry behavior and explicit paid-call confirmation.
- [x] Reproducible run manifest with config, task, and event hashes.
- [x] `doctor --live-config ... --probe-live` readiness checks.
- [x] Mocked HTTP contract tests with no paid calls.
- [x] Staged 36-scenario workload matrix across 8K/32K/128K history and 1/5/10 turns.
- [x] Versioned Luna/Terra pricing registry and paid-run cost preflight.
- [x] Four-scenario Luna smoke stage capped before any provider request.
- [x] Multi-turn agent/tool-call history with exactly one terminal task grade per arm.
- [x] Compression-backend model check before any external provider request.
- [x] Atomic partial-event output for interrupted live runs.

## Evidence acceptance

- [x] PariTok gateway, telemetry, local model listing, and direct compression verified locally.
- [ ] Provider key and a non-zero, date-versioned price entry configured.
- [x] A small paid Luna smoke run completes with exact critical-signal recall.
- [x] A bounded 32K/5-turn Wave A pilot completes and correctly keeps rollout off after 4/4
  treatment terminal task-proxy failures.
- [x] Provider-free controlled audit reproduces cross-query reuse under the installed content-only
  cache behavior and verifies disabled/query-aware isolation interventions.
- [x] Prespecified provider-free regression verifies the actual local PariTok 4B query-aware path
  across four 32K/5-turn workloads: 0/12 cross-query hits, 12/12 replay hits, and 12/12 raw and
  guarded signal recall. This is transformed-context evidence, not terminal task success.
- [x] Multi-turn execution fails closed for an unverified cache contract; any research override is
  explicitly non-rollout evidence.
- [ ] At least five paired tasks per workload at 32K/128K complete.
- [ ] Independent human or calibrated LLM reviews cover terminal responses.
- [ ] Cold/warm latency is decomposed with instrumented local and provider timing.
- [ ] All 36 paired cases execute on an isolated proxy instance.
- [ ] Results are reviewed for task equivalence, silent failures, cost per success, and P95 latency.
- [ ] Production rollout policy remains locked until confidence and reliability gates pass.

Engineering readiness is not production evidence. The unchecked items require the operator's
provider credentials and authorization to incur cost. Marker recall is a safety check, not a
semantic-quality verdict; see `quality-review-protocol.md`. Local readiness evidence is recorded in
`artifacts/phase-3-local-readiness.json`; it is not provider-performance evidence.

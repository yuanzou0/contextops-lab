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
- [x] Provider usage, proxy token delta, endpoint role, config hash, and pricing version in schema v3.
- [x] Bounded HTTP retry behavior and explicit paid-call confirmation.
- [x] Reproducible run manifest with config, task, and event hashes.
- [x] `doctor --live-config ... --probe-live` readiness checks.
- [x] Mocked HTTP contract tests with no paid calls.

## Evidence acceptance

- [ ] PariTok gateway health and telemetry verified in the target environment.
- [ ] Provider key and a non-zero, date-versioned price entry configured.
- [ ] A small paid smoke run passes before the full benchmark.
- [ ] All 36 paired cases execute on an isolated proxy instance.
- [ ] Results are reviewed for task equivalence, silent failures, cost per success, and P95 latency.
- [ ] Production rollout policy remains locked until confidence and reliability gates pass.

Engineering readiness is not production evidence. The unchecked items require the operator's
provider credentials, model choice, running PariTok deployment, and authorization to incur cost.

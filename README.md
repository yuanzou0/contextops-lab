# ContextOps Lab

**AI Agent Reliability & Cost Evaluation**

An independent paired-experiment and safety framework for deciding when context compression should be enabled in AI-agent workloads.

## Core question

> When does context compression reduce the cost of AI agents without degrading task success, reliability, or latency?

PariTok-4B-v1 is the first planned compression treatment, not the name of this project. ContextOps Lab does **not** claim authorship of the upstream gateway, model, benchmarks, or reported savings.

## Decision pipeline

```text
Paired Experiments
        ↓
Context Compression
        ↓
Validation + Safe Fallback
        ↓
Task Success × Cost × Latency
        ↓
Workload Segmentation
        ↓
Rollout Policy
```

The primary metric is **cost per successful task**, not compression ratio.

## Phase 1 MVP

The first implementation provides:

- a typed request-event schema with privacy-safe analytics fields;
- layered validation for empty output, malformed references, output expansion, and loss of task-critical signals;
- automatic fallback to exact original context with structured reason codes;
- concrete baseline/compressed execution arms with external compressor and OpenAI-compatible agent adapters;
- JSONL event storage and aggregate quality/cost/latency metrics;
- a 36-case executable workload benchmark spanning read-heavy, debugging, edit-critical, log, MCP-heavy, short, and intent-pivot cases;
- a reproducible offline pipeline-validation report that is explicitly separated from production evidence;
- unit tests for validator, fallback, events, and paired experiments.

## Quick start

```bash
python -m pip install -e '.[dev]'
pytest

# Reproduce the Phase 1 offline validation evidence
contextops-lab offline-benchmark
```

The zero-install verification path uses only the Python standard library:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m contextops_lab.cli offline-benchmark
```

The framework is provider-neutral. Use `SubprocessCompressor` for a local or hosted compressor command and `OpenAICompatibleAgent` for a live agent endpoint. Both arms share the same agent and benchmark case; only the supplied context changes.

## Repository map

```text
src/contextops_lab/    evaluation and reliability package
evals/tasks/           workload manifests
tests/                 deterministic unit tests
artifacts/             privacy-safe Phase 1 events
docs/                  experiment and rollout design
skills/                reusable supporting methodology
```

The [`ai-agent-project-strategist`](skills/ai-agent-project-strategist/) Codex Skill is a supporting methodology asset, not the product headline.

## Phase 1 evidence boundary

The included report validates pipeline mechanics with deterministic offline fixtures. It does not establish real-world savings or task-quality equivalence for PariTok. Live paired runs are the next release gate.

## Phase 2 product loop

Phase 2 turns experiment events into governed product decisions:

```text
Event quality checks
        ↓
Workload segmentation + confidence bounds
        ↓
Failure root-cause analysis
        ↓
Evidence-gated rollout policy
        ↓
off / conservative / balanced runtime strategy
        ↓
doctor preflight + analytics dashboard
```

Generate all Phase 2 artifacts and run diagnostics:

```bash
contextops-lab phase-2
contextops-lab doctor
```

Outputs include a self-contained dashboard, versioned rollout policy, Markdown decision report, and SHA-256 lineage manifest. Non-production evidence always keeps operational rollout locked even when offline metrics look favorable.

Phase 2 deliverables:

- [`artifacts/phase-2-dashboard.html`](artifacts/phase-2-dashboard.html): interactive analytics dashboard;
- [`policies/rollout-policy.json`](policies/rollout-policy.json): versioned decision rules and thresholds;
- [`docs/phase-2-report.md`](docs/phase-2-report.md): workload and failure analysis;
- [`artifacts/phase-2-lineage.json`](artifacts/phase-2-lineage.json): input/output hashes and evidence provenance;
- [`docs/phase-2-acceptance.md`](docs/phase-2-acceptance.md): product-loop acceptance contract.

## Success criteria

A workload segment is eligible for rollout only when:

1. silent data loss is zero;
2. task success remains inside the declared non-inferiority margin;
3. cost per successful task improves;
4. P95 latency remains within budget;
5. recall and fallback paths meet their reliability targets.

## Attribution

ContextOps Lab is an independent evaluation project. PariTok and its upstream code, weights, benchmarks, and trademarks belong to their respective authors. Review the upstream Apache-2.0 license and the Qwen base-model license before redistributing derived code or weights.

# ContextOps Lab

**AI Agent Optimization Experimentation & Product Economics Lab**

An independent paired-experiment and safety framework for deciding when context compression should be enabled in AI-agent workloads.

## Core question

> When does context compression reduce the cost of AI agents without degrading task success, reliability, or latency?

PariTok-4B-v1 is the first planned compression treatment, not the name of this project. ContextOps Lab does **not** claim authorship of the upstream gateway, model, benchmarks, or reported savings.

## Results at a glance

| Evidence | N | Cost | Quality measure | Median latency | Decision |
|---|---:|---:|---|---:|---|
| Offline pipeline | 36 pairs | fixture only | deterministic task proxy | fixture | no rollout |
| Live smoke | 4 pairs | 80.8% lower observed estimated provider cost | required signals preserved in 4/4 pairs | 17.0x worse | **OFF** |
| Live Wave A | 4 pairs / 40 requests | 89.9% lower observed estimated provider cost | treatment proxy failed 4/4 terminal tasks | 15.9x worse | **STOP / OFF** |
| Production | — | not validated | not validated | not validated | locked |

Across four controlled 8K/1-turn live pairs, the compression treatment showed 80.8% lower
observed estimated provider cost while increasing median end-to-end latency 17.0x; the
evidence-gated policy therefore kept rollout off. This smoke validates integration and exact
signal preservation only—not semantic equivalence or production non-inferiority.

The subsequent 32K/5-turn Wave A pilot reduced observed estimated provider cost by 89.9%, but the
treatment failed the required-signal task proxy in all four workloads and increased median request
latency 15.9x. Expansion is stopped pending signal-retention and fallback fixes; see
[`docs/phase-3-wave-a-results.md`](docs/phase-3-wave-a-results.md).

## Decision pipeline

```text
Paired Experiments
        ↓
Context Compression
        ↓
Validation + Safe Fallback
        ↓
Task-proxy Quality × Cost × Latency
        ↓
Workload Segmentation
        ↓
Rollout Policy
```

The primary decision metric is **cost per independently reviewed successful task**, not
compression ratio. Until independent reviews exist, the repository reports task-proxy success.

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

`pytest` is the canonical development and CI runner. The `unittest` command is retained only as a
dependency-free compatibility check; both discover the same `unittest.TestCase`-based suite.

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

## Phase 3 real-integration gate

Phase 3 adds a production-shaped, multi-turn A/B path: the baseline calls a provider endpoint
directly, while the treatment calls the identical model through a PariTok proxy. Historical tool
results carry the long context that PariTok is designed to compress. The runner snapshots proxy
stats around each treatment request and fails closed if the local compression model is unavailable
or concurrent traffic makes attribution ambiguous.

```bash
# Validate configuration and probe only health/telemetry (no completion cost)
cp configs/phase-3.example.json configs/phase-3.local.json
# Edit the ignored local copy; never place an API key in JSON.
contextops-lab doctor --live-config configs/phase-3.local.json --probe-live

# Explicit confirmation and a hard cost ceiling are mandatory for paid model calls
contextops-lab live-session-run \
  --config configs/phase-3-luna-smoke.json \
  --stage smoke \
  --max-estimated-input-cost-usd 0.25 \
  --confirm-live-costs
```

See [`docs/phase-3-runbook.md`](docs/phase-3-runbook.md) and
[`docs/phase-3-acceptance.md`](docs/phase-3-acceptance.md). The repository contains the tested
integration and evidence contract, plus a local-runtime readiness record. It intentionally contains
no fabricated provider results. The first paid integration smoke is documented in
[`docs/phase-3-results.md`](docs/phase-3-results.md); it observed cost reduction and exact marker
recall in four cases while keeping rollout off because of sample size, semantic-review, and latency
gaps.

Before any paid call, audit the staged 36-scenario workload matrix and its input-cost ceiling:

```bash
contextops-lab workload-audit --stage smoke --model gpt-5.6-luna
```

The matrix covers read-heavy, debugging, MCP-heavy, and edit-critical work at 8K/32K/128K
message-history payloads and 1/5/10 turns. Tool schemas are measured as additional input overhead.

## Evidence and multi-compressor controls

The four-case Luna run is an integration smoke, not a non-inferiority result. The repository now
enforces the missing evidence explicitly:

```bash
# Fails the quality-claim gate until every segment has >=5 pairs,
# both 32K and 128K are observed, and terminal arms have human/LLM reviews.
contextops-lab evidence-audit

# Estimate paired provider vs local/proxy overhead (clearly labeled as an estimate).
contextops-lab latency-audit

# After restarting Ollama, separate cold, warm-uncached, and cache-reuse latency (no provider call).
contextops-lab local-latency-probe --confirm-backend-restarted

# Build cumulative cost/latency curves. Break-even remains disabled unless latency is valued.
contextops-lab multi-turn-economics
contextops-lab multi-turn-economics --latency-value-usd-per-second 0.10

# Reproduce a provider-free comparison of two compressor adapters.
contextops-lab compressor-compare

# Audit the proposed 20-scenario evidence stage: 5 pairs per workload, 32K/128K.
contextops-lab workload-audit --stage evidence --model gpt-5.6-luna
```

The second adapter, `ExtractiveRiskCompressor`, is a deterministic, answer-independent baseline.
It proves that the evaluation layer can compare treatments; it is not presented as a replacement
for PariTok or as live provider evidence.

## Success criteria

A workload segment is eligible for rollout only when:

1. silent data loss is zero;
2. independently reviewed task quality remains inside the declared non-inferiority margin;
3. cost per successful task improves;
4. P95 latency remains within budget;
5. recall and fallback paths meet their reliability targets.

## Attribution

ContextOps Lab is licensed under [Apache-2.0](LICENSE). It is an independent evaluation project.
PariTok and its upstream code, weights, benchmarks, and trademarks belong to their respective
authors. Review the upstream Apache-2.0 license and the Qwen base-model license before
redistributing derived code or weights.

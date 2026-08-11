# PariTok Agent Reliability & Cost Evaluation Lab

A paired experimentation and reliability framework for deciding when context compression should be enabled in AI-agent workloads.

## Core question

> When does context compression reduce the cost of AI agents without degrading task success, reliability, or latency?

This independent project evaluates [PariTok-4B-v1](https://github.com/Paritok-official/paritok-4b-v1). It does **not** claim authorship of the upstream gateway, model, benchmarks, or reported savings.

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
- a paired baseline/treatment experiment runner;
- JSONL event storage and aggregate quality/cost/latency metrics;
- a 36-task workload manifest spanning read-heavy, debugging, edit-critical, log, MCP-heavy, short, and intent-pivot cases;
- unit tests for validator, fallback, events, and paired experiments.

## Quick start

```bash
python -m pip install -e '.[dev]'
pytest
```

The framework is provider-neutral. Supply baseline and compressed executors through the `PairedExperimentRunner`; the lab records comparable outcomes without storing raw prompts or source code.

## Repository map

```text
src/paritok_lab/       evaluation and reliability package
evals/tasks/           workload manifests
tests/                 deterministic unit tests
docs/                  experiment and rollout design
skills/                reusable supporting methodology
```

The [`ai-agent-project-strategist`](skills/ai-agent-project-strategist/) Codex Skill is a supporting methodology asset, not the product headline.

## Success criteria

A workload segment is eligible for rollout only when:

1. silent data loss is zero;
2. task success remains inside the declared non-inferiority margin;
3. cost per successful task improves;
4. P95 latency remains within budget;
5. recall and fallback paths meet their reliability targets.

## Attribution

PariTok and its upstream code, weights, benchmarks, and trademarks belong to their respective authors. Review the upstream Apache-2.0 license and the Qwen base-model license before redistributing derived code or weights.

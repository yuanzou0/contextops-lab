# Phase 3 live experiment runbook

## 1. Install and start the local compression backend

The tested local stack uses PariTok 1.3.3 and Ollama 0.32.9. Install the live extra in an isolated
environment, then pull and alias the model as required by PariTok:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,live]"
ollama pull paritok/paritok-4b-v1
ollama cp paritok/paritok-4b-v1 paritok-4b-v1
ollama serve
```

In a separate terminal, start the gateway with the provider key exported only in the environment:

```bash
export OPENAI_API_KEY="..."
.venv/bin/paritok proxy --port 8080
```

PariTok may pass content through when its compression backend is unavailable. ContextOps Lab checks
the Ollama model listing before a paid run and fails closed instead of accepting that silent no-op.

## 2. Configure the gateway and provider

Start PariTok separately and verify that its proxy, `/health`, and `/stats` endpoints are reachable.
Use a dedicated proxy instance during measurement: cumulative stats cannot safely attribute a
treatment request if unrelated traffic occurs between snapshots.

Use the checked-in Luna smoke config first. Copy `configs/phase-3.example.json` only for a custom
provider, then set:

- the identical model used by both endpoints;
- current input/output price per million tokens and a dated pricing version;
- the baseline provider and PariTok proxy Chat Completions URLs;
- a non-production evidence label until human review is complete.

Do not put a secret in the JSON file. Export it through the configured environment variable.

## 3. Diagnose without spending provider tokens

```bash
contextops-lab doctor --live-config configs/phase-3.local.json
contextops-lab doctor --live-config configs/phase-3.local.json --probe-live
```

The probe calls health, stats, and the local Ollama model-list endpoint. It does not send a provider
completion. Confirm that it reports both `paritok_gateway=PASS` and the configured compression model.

## 4. Paid Luna smoke test

```bash
contextops-lab workload-audit --stage smoke --model gpt-5.6-luna

contextops-lab live-session-run \
  --config configs/phase-3-luna-smoke.json \
  --stage smoke \
  --max-estimated-input-cost-usd 0.25 \
  --confirm-live-costs
```

The preflight estimate is an upper bound for paired input before compression; output tokens and
local compute are separate. Inspect the atomically written events and run manifest. Continue only
if all four sessions have valid direct/proxy pairs, one terminal grade per arm, exact critical-signal
recall, and exactly one proxy request per treatment turn.

## 5. Terra formal experiment and decision artifacts

```bash
contextops-lab live-session-run \
  --config configs/phase-3-terra-formal.json \
  --stage extended \
  --max-estimated-input-cost-usd 25 \
  --confirm-live-costs

contextops-lab phase-2 \
  --events artifacts/phase-3-live-events.jsonl \
  --policy policies/phase-3-rollout-policy.json \
  --dashboard artifacts/phase-3-dashboard.html \
  --report docs/phase-3-results.md \
  --lineage artifacts/phase-3-analysis-lineage.json \
  --evidence-label live_unreviewed
```

Human review may promote the evidence label only after checking failure traces and experimental
assumptions. A strong compression ratio alone is not a rollout decision.

## 6. Stop local services

Stop the dedicated gateway and Ollama processes after the run. Do not reuse a gateway handling
unrelated traffic because cumulative stats would make per-request attribution ambiguous.

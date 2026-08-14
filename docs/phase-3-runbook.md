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

For multi-turn recovery experiments, use the ContextOps-owned safety wrapper instead of the raw
PariTok command:

```bash
contextops-lab safe-proxy --cache-contract query_aware --port 8080
```

This remains a real OpenAI-compatible external HTTP proxy. Before forwarding upstream, it scopes
compressed-cache reuse to the active query, validates every transformed segment, and substitutes
exact original content on rejection. `/contextops/stats` exposes cumulative, raw-content-free
safety counters for paired attribution.

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

Keep provider retries disabled for measured runs. A slow first local compression can otherwise make
the client retry a request that the gateway is still processing, duplicating provider cost and
invalidating per-request telemetry. Pre-warm local dependencies and use a longer end-to-end timeout
instead.

Before expanding the matrix, restart Ollama and immediately run `contextops-lab
local-latency-probe --confirm-backend-restarted`. It makes no provider request and records a cold candidate, a distinct-input
warm uncached call, and exact-input cache reuse. The cold label is valid only when the backend was
actually restarted. Combine that artifact with
`contextops-lab latency-audit`, whose direct arm is the provider control. The paired subtraction is
explicitly labeled an estimate because PariTok 1.3.3 does not expose split timing headers.

### Query-sensitive cache safety gate

Run the provider-free contract audit before any further multi-turn experiment:

```bash
contextops-lab cache-contract-audit
```

Multi-turn execution defaults to the `unverified` cache contract and therefore fails closed before
checking an API key or calling a provider. A future integration config must declare
`compression_cache_contract` as `disabled` or `query_aware`. The
`--allow-unsafe-query-sensitive-cache-experiment` flag exists only to reproduce a controlled unsafe
condition and is recorded as non-rollout research evidence.

A config that declares `disabled` or `query_aware` must also provide
`contextops_safety_stats_url`. The live runner probes that endpoint and rejects the run if the
observed cache or validator contract differs from the config.

### Four-scenario recovery pilot

Read `phase-3-recovery-protocol.md` before authorizing costs. The fixed Wave A matrix contains four
32K/5-turn paired sessions and 40 requests. Generate the preflight without provider calls:

```bash
contextops-lab workload-audit \
  --stage wave_a \
  --model gpt-5.6-luna \
  --output artifacts/phase-3-recovery-preflight.json \
  --report docs/phase-3-recovery-preflight.md
```

Only after a fresh dollar ceiling is explicitly approved:

```bash
contextops-lab live-session-run \
  --config configs/phase-3-luna-recovery.json \
  --stage wave_a \
  --events artifacts/phase-3-recovery-events.jsonl \
  --run-manifest artifacts/phase-3-recovery-manifest.json \
  --max-estimated-input-cost-usd <AUTHORIZED_CEILING> \
  --confirm-live-costs
```

## 5. Terra formal experiment and decision artifacts

Before the full evidence stage, use the bounded Wave A pilot to test all four workloads at
32K/5-turn. It is still directional evidence, not non-inferiority:

```bash
contextops-lab live-session-run \
  --config configs/phase-3-luna-wave-a.json \
  --stage wave_a \
  --events artifacts/phase-3-wave-a-events.jsonl \
  --run-manifest artifacts/phase-3-wave-a-manifest.json \
  --max-estimated-input-cost-usd 1.25 \
  --confirm-live-costs
```

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

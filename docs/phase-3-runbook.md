# Phase 3 live experiment runbook

## 1. Configure the gateway and provider

Start PariTok separately and verify that its proxy, `/health`, and `/stats` endpoints are reachable.
Use a dedicated proxy instance during measurement: cumulative stats cannot safely attribute a
treatment request if unrelated traffic occurs between snapshots.

Copy `configs/phase-3.example.json` to a local config, then set:

- the identical model used by both endpoints;
- current input/output price per million tokens and a dated pricing version;
- the baseline provider and PariTok proxy Chat Completions URLs;
- a non-production evidence label until human review is complete.

Do not put a secret in the JSON file. Export it through the configured environment variable.

## 2. Diagnose without spending model tokens

```bash
contextops-lab doctor --live-config configs/phase-3.local.json
contextops-lab doctor --live-config configs/phase-3.local.json --probe-live
```

The probe calls only health and stats endpoints. It does not send a model completion.

## 3. Paid smoke test

```bash
contextops-lab live-run \
  --config configs/phase-3.local.json \
  --limit 2 \
  --confirm-live-costs
```

Inspect the resulting events and run manifest. Then run the full 36-case benchmark only after the
smoke test has valid direct/proxy pairs and exactly one proxy request per treatment snapshot.

## 4. Full experiment and decision artifacts

```bash
contextops-lab live-run \
  --config configs/phase-3.local.json \
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

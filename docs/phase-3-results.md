# ContextOps Lab — Phase 3 Luna smoke results

**Run date:** 2026-08-12  
**Evidence:** `live_smoke_unreviewed`  
**Decision:** integration validated; rollout remains **off**

## Executive result

All four 8K-context paired scenarios passed the deterministic marker oracle in both arms and
preserved every required signal. This establishes exact recall for these cases, not semantic
quality equivalence; no human or LLM judge was used.
PariTok reduced provider input by 82.6% and successful-run cost by 80.8%, but increased median
end-to-end latency by 40.75 seconds (17.0x). This is a promising economics result and an
unacceptable interactive-latency result. Do not expand to the Terra matrix until the latency path
has a product policy and a measured mitigation.

| Metric | Direct baseline | PariTok | Change |
|---|---:|---:|---:|
| Required-signal task proxy | 4/4 | 4/4 | no observed proxy degradation |
| Provider input tokens | 36,663 | 6,392 | -82.6% |
| Provider output tokens | 137 | 137 | unchanged |
| Estimated successful-run cost | $0.037485 | $0.007214 | -80.8% |
| Median latency | 2.54 s | 43.29 s | +40.75 s / 17.0x |
| P95 latency | 2.55 s | 45.16 s | +42.61 s / 17.7x |
| Silent failures | 0 | 0 | pass |
| Fallbacks | 0 | 0 | pass |

PariTok telemetry recorded four isolated treatment requests, 45,285 touched input tokens reduced
to 7,178, and 38,107 tokens saved. No expansion or edit-recovery call was required.

## Segment results

| Workload | Baseline cost | PariTok cost | Cost reduction | Baseline latency | PariTok latency |
|---|---:|---:|---:|---:|---:|
| Read-heavy | $0.008309 | $0.001739 | 79.1% | 1.98 s | 45.16 s |
| Debugging | $0.008702 | $0.001721 | 80.2% | 2.55 s | 35.49 s |
| MCP-heavy | $0.011932 | $0.001871 | 84.3% | 2.78 s | 46.32 s |
| Edit-critical | $0.008542 | $0.001883 | 78.0% | 2.54 s | 41.42 s |

Each segment contains one pair, so the confidence interval is too wide for a non-inferiority claim.
The segment table is directional evidence, not a ranking.

## Failed-closed attempt

The first attempt correctly stopped after its initial pair reported two proxy requests. Root cause:
the 120-second client timeout expired while first-run local dependencies were loading, and the
client retried a request that the gateway was still processing. A local fake-upstream contract test
confirmed that PariTok increments telemetry once per HTTP request. Measured-run retries are now
disabled, the timeout is 300 seconds, and the failed partial event is retained as diagnostic evidence.

The completed run recorded $0.044699 in event-attributed provider cost. Including the incomplete
attempt is estimated at approximately $0.0565 total, below the user-authorized $0.25 ceiling; the
failed treatment usage is an estimate because the executor stopped before writing those events.

## Local latency follow-up

A provider-free three-state probe was run immediately after restarting Ollama. The
`read-heavy-32k-5t` cold candidate took 38.82 seconds. A distinct `debugging-32k-5t` input then took
29.18 seconds with the model loaded and no application cache hit. Repeating that exact second input
hit the cache and took 4.69 milliseconds. Outputs shrank from 5,123 to 15 estimated tokens and from
4,873 to 52 tokens, but neither has received semantic quality review.

The scenarios are close in size but not identical, so the 9.64-second difference cannot be
attributed entirely to model loading. The important product result is that warm, uncached
compression remained around 29 seconds: cold loading is not the only blocker, while millisecond
latency is available only for exact-input cache reuse. On this hardware and configuration, the
result supports an eligibility policy that favors reusable/asynchronous context and rejects
uncached synchronous work.

Artifact: `artifacts/phase-3-local-latency.json`.

## Product decision

- Keep the default rollout mode `off`.
- Treat cost reduction as validated only for this four-case integration smoke.
- Before Terra, add a latency-aware eligibility rule: compression is unsuitable for synchronous
  short sessions unless local work can be cached, precomputed, or amortized across later turns.
- Add instrumented backend timing for warm, uncached inference; the current paired subtraction is
  only a local-plus-proxy estimate because PariTok 1.3.3 exposes no split timing headers.
- Require at least five paired tasks per segment before applying the existing non-inferiority gate.

Artifacts: `phase-3-session-events.jsonl`, `phase-3-session-manifest.json`,
`phase-3-dashboard.html`, `phase-3-analysis-lineage.json`, and the attempt-1 diagnostic files.

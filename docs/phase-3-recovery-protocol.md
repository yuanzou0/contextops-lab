# ContextOps Phase 3 provider-backed recovery pilot protocol

## Status

Prespecified before any provider-backed recovery result is observed. This four-scenario pilot is a
targeted repair check after Wave A; it is not the 20-pair evidence stage and cannot establish
non-inferiority.

## Question

Does the ContextOps-owned external proxy boundary—query-aware compression cache plus validation
and exact-original fallback—recover terminal critical-signal task-proxy success on the four
original 32K/5-turn Wave A workloads?

## Fixed design

- Same four workload types, scenario definitions, tool schemas, model, pricing version, and seed as
  Wave A.
- Paired direct-provider baseline and ContextOps-safe PariTok proxy treatment.
- Five cumulative requests per arm and workload: 40 provider requests if the run completes.
- Cache contract must be reported as `query_aware` by the running proxy.
- Every rejected transformed segment must be forwarded as exact original content.
- Raw prompts, transformed context, and completions are not stored; events retain metrics only.

## Primary recovery gates

1. Treatment terminal required-signal task proxy: 4/4.
2. Treatment intermediate acknowledgement protocol: 16/16.
3. Baseline terminal task proxy: 4/4, as a run-validity control.
4. Proxy request attribution: exactly one proxy request per treatment turn.
5. Safety telemetry: fallback count equals exact-original fallback count; no silent rejection.
6. Declared and observed cache contract: `query_aware`.

Any failed gate keeps expansion stopped. Missing or contradictory telemetry aborts the run rather
than being treated as a failed model task.

## Secondary outcomes

- Observed provider cost and cost per successful task.
- Provider input/output tokens.
- Median and P95 request latency.
- Compression latency, validation passes, fallback rate/reasons, and cache hits.

Latency does not become acceptable merely because task-proxy recovery passes. The existing rollout
budget remains a maximum P95 increase of 500 ms; the pilot reports the observed gap but is not
powered to validate latency eligibility.

## Stop and claim rules

- Enforce a newly authorized dollar ceiling before the first request.
- Stop on an unavailable local compression model, safety-contract mismatch, non-isolated proxy
  telemetry, upstream error, or interrupted evidence write.
- Do not change signals, thresholds, exclusions, or the primary outcome after viewing results.
- Report all four workloads regardless of whether the repair succeeds.
- A 4/4 recovery supports only: “the repaired path recovered the deterministic task proxy in this
  bounded pilot.” It does not support semantic equivalence, production reliability, or rollout.

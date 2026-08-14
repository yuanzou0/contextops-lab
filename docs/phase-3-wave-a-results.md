# ContextOps Lab — Phase 3 Wave A results

**Run date:** 2026-08-14

**Evidence:** `live_wave_a_unreviewed`

**Scope:** four 32K/5-turn paired workloads; 40 provider requests

**Decision:** **stop expansion; rollout remains OFF**

## Executive result

The direct baseline preserved all three required signals in 4/4 terminal responses. The PariTok
treatment preserved the intermediate acknowledgement protocol in 16/16 requests but failed the
terminal required-signal task proxy in 4/4 workloads. Provider input and estimated provider cost
fell by about 90%, but cost per successful treatment task is undefined because no treatment task
passed. Median request latency increased from 2.05 seconds to 32.62 seconds.

This result rejects expansion to the 20-pair evidence stage under the current configuration. It
does not prove that every context-compression approach fails; it shows that this PariTok proxy path,
model, hardware, task protocol, and configuration are not eligible for synchronous rollout.

| Metric | Direct baseline | PariTok treatment | Change |
|---|---:|---:|---:|
| Terminal required-signal task proxy | 4/4 | 0/4 | -100 percentage points |
| Provider input tokens | 367,737 | 36,152 | -90.2% |
| Provider output tokens | 265 | 187 | -29.4% |
| Observed estimated provider cost | $0.369327 | $0.037274 | -89.9% |
| Cost / successful proxy task | $0.092332 | undefined | no treatment successes |
| Median request latency | 2.05 s | 32.62 s | 15.9x |
| P95 request latency | 3.57 s | 72.69 s | 20.4x |
| Cumulative latency across requests | 46.28 s | 771.96 s | 16.7x |

## Workload results

| Workload | Baseline cost | Treatment cost | Baseline cumulative latency | Treatment cumulative latency | Terminal proxy |
|---|---:|---:|---:|---:|---|
| Read-heavy | $0.087258 | $0.008815 | 13.33 s | 223.23 s | fail |
| Debugging | $0.086925 | $0.008699 | 8.33 s | 138.43 s | fail |
| MCP-heavy | $0.107034 | $0.010910 | 11.15 s | 254.01 s | fail |
| Edit-critical | $0.088110 | $0.008850 | 13.47 s | 156.29 s | fail |

## Failure interpretation

Three treatment terminal responses used only 11 output tokens, while returning all three required
signals needs at least 19–21 estimated tokens. Those three responses could not have satisfied the
declared task. The debugging response used 26 output tokens but still failed exact signal recall.

Raw completions are intentionally absent from the privacy-safe event schema, so this run cannot
distinguish among compressed-history signal loss, reference/recovery behavior, and other response
content errors. The event schema has therefore been advanced for future runs to record the number
of required signals recalled and a structured `missing_required_signals` failure reason without
storing raw content.

The leading mechanism is a code-supported inference: PariTok 1.3.3 derives its compression cache
key from the content hash alone. It does not include the active query. In these cumulative sessions,
early tool outputs are first compressed while the user asks for the intermediate
`CONTEXT_RECORDED` acknowledgement. When the fifth-turn query changes to the final signal-recall
task, those identical tool outputs can reuse summaries created for the earlier intent instead of
being recompressed for the final task. This mechanism fits the observed pattern, but the absent raw
responses mean it cannot be called the sole cause.

A subsequent provider-free controlled audit held the content, pipeline, deterministic compression
model, and configuration constant. Under the installed content-only behavior, changing the query
produced a cache hit and reused the first output after only one model call. Cache-disabled and
query-aware reference interventions each produced query-specific outputs, while repeating the
second query under the query-aware condition still hit cache. This confirms that the mechanism is
present in PariTok 1.3.3 and strengthens the attribution, without claiming that it explains every
Wave A terminal failure. See `query-sensitive-cache-decision.md` and
`artifacts/query-sensitive-cache-audit.json`.

The live proxy path reports compression telemetry but does not expose the transformed context to
ContextOps before the upstream call. Consequently, ContextOps cannot apply its content validator
or automatic original-context fallback inside this external proxy path. That is now a production
safety blocker, not merely a reporting limitation.

## Cost control

The input-only preflight upper bound was $0.9683 and the user-authorized ceiling was $1.25. The
event-attributed provider cost was $0.406601, including both arms and output. Local compute is not
included. No additional paid expansion was run after the terminal failures were observed.

## Product decision

- Keep every workload mode `off`.
- Do not run the 20-pair/32K+128K evidence stage yet.
- Diagnose signal retention provider-free at the transformed-context boundary.
- Require query-aware cache invalidation, or disable cached compression when task intent changes.
- Add a validated fallback boundary before treating the external proxy as production-safe.
- Re-run a small recovery pilot only after the task proxy and latency blockers have mitigations.

Artifacts: `phase-3-wave-a-events.jsonl`, `phase-3-wave-a-manifest.json`,
`phase-3-wave-a-dashboard.html`, `phase-3-wave-a-economics.json`,
`phase-3-wave-a-evidence-audit.json`, `phase-3-wave-a-latency.json`, and
`phase-3-wave-a-lineage.json`.

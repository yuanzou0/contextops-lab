# Phase 3 provider-backed recovery pilot result

## Decision

**FAIL — EXPANSION REMAINS STOPPED.** The fixed Wave A recovery pilot stopped on a 300-second
treatment request timeout after 25 successful events. Retries were disabled and the runner did not
continue after the prescribed stop condition.

The completed-event estimate is **$0.41763** for 415,650 provider input tokens and 330 output
tokens. The timed-out request may have incurred additional usage that was not available to the
atomic event writer, so provider billing records—not this estimate—are authoritative for the exact
total.

## Primary gates

| Gate | Observation | Result |
|---|---:|---:|
| Treatment terminal required-signal task proxy | 2/4 | FAIL — incomplete |
| Treatment intermediate acknowledgement protocol | 8/16 | FAIL — incomplete |
| Baseline terminal task proxy | 3/4 | FAIL — incomplete |
| Proxy request attribution | 10/10 completed treatment events; timeout unattributable | FAIL |
| Fallback equals exact-original fallback | 5/5 | PASS |
| Declared and observed cache contract | `query_aware` | PASS |

The completed read-heavy and debugging pairs passed their terminal task proxies in both arms. The
mcp-heavy baseline completed, then the first treatment request timed out. The fourth workload was
not started. These partial successes do not satisfy the prespecified recovery gates and do not
support a recovery claim.

## Latency

Completed baseline requests had median latency 1,335.01 ms and maximum latency 3,071.39 ms.
Completed treatment requests had median latency 61,086.82 ms and maximum latency 220,420.37 ms.
The separate rollout budget is 500 ms, so latency eligibility is independently failed by a wide
margin.

## Safety and privacy

The proxy reported five validator fallbacks and five exact-original fallbacks, zero cache hits,
`query_aware` cache behavior, a healthy encrypted Redis store, and no recorded raw content. No real
user data, prompt text, completion text, or secret is present in the evidence.

The privacy-safe partial JSONL is retained at
`artifacts/phase-3-recovery-events.jsonl.partial` with SHA-256
`208de1cb32c2b843d03e07b7c7955e5103c675c17fc2d1c5d24a7ea4b045f4d0`.

No automatic rerun is permitted: the run failed a prespecified stop rule and already consumed part
of the authorized budget.

## Credential lifecycle

The one-day API key created solely for this run (`key_1SlPMz9wftmenjMi`) was verified as
`Revoked` in the selected OpenAI Platform project on 2026-09-22. The local Keychain item created
for the run was deleted, browser automation memory was reset, and no secret value was written to
the repository or retained in this evidence.

## Change-control decision

This result is immutable negative evidence. The partial events, fixed gates, timeout, failed status,
and cost caveat must not be edited to manufacture a pass. In particular, increasing the timeout,
dropping the `mcp-heavy` workload, excluding the timed-out request, or weakening the latency gate
would create a new protocol and cannot alter this result.

Engineering changes are allowed and encouraged in a separately versioned successor intervention.
The evidence points to the synchronous local compression path—not provider authentication or Redis
durability—as the immediate blocker: 45 compression operations accumulated 1,711,440.985 ms across
10 completed treatment requests, with zero cache hits. Candidate interventions are:

1. reduce repeated compression work by compressing stable history once and reusing only
   query-compatible results;
2. add an explicit local-compression deadline that forwards exact original content and records a
   distinct timeout fallback without retrying the provider request;
3. restrict compression eligibility to paths with a measured latency advantage, leaving cold or
   oversized histories uncompressed;
4. benchmark a faster local backend or execution profile provider-free before another paid run;
5. separate compression, proxy, and upstream timing so a successor timeout remains attributable.

Items 2 and 3 improve safety but may intentionally disable compression and therefore cannot by
themselves establish compression benefit. Before any paid successor run, the chosen intervention
must pass provider-free safety, attribution, and latency tests under a new config/evidence label;
the user must then authorize a new request and dollar ceiling.

On 2026-09-26, the split timing attribution, cold-compression eligibility gate, and backend-level
deadline fallback were implemented and passed provider-free contract tests. A subsequent real
local Ollama/Redis drill passed 12/12 control gates with zero provider calls. This does not alter
the failed pilot or authorize a successor paid run; see `phase-3.1-latency-controls.md`.

# Query-sensitive cache: isolation decision and product story

## Decision

ContextOps Lab isolates query-sensitive cache risk before attempting an upstream repair. Multi-turn
execution now fails closed when the compression-cache contract is `unverified`. A live config must
declare `disabled` or `query_aware` before the run can be rollout-eligible. An explicit research-only
override remains available, but its decision object always sets `rollout_eligible` to false.
That field represents the cache-safety gate only; passing it does not bypass the separate quality,
latency, sample-size, or independent-review rollout gates.

This is a ContextOps safety boundary, not a claim that the upstream PariTok project has been fixed.

## What was observed

The 32K/5-turn Wave A pilot produced a useful negative result:

- direct baseline terminal task proxy: 4/4 passed;
- PariTok treatment terminal task proxy: 0/4 passed;
- intermediate acknowledgement protocol: 16/16 passed;
- observed estimated provider cost: 89.9% lower in treatment;
- median request latency: 15.9 times baseline;
- total provider-attributed cost: $0.406601 against a $1.25 ceiling.

ContextOps stopped expansion rather than optimizing the headline savings. The unused $0.843399 of
the authorized ceiling was not spent.

## Controlled provider-free diagnostic

The command below runs without an upstream provider, Ollama, API key, or network tokenizer asset:

```bash
contextops-lab cache-contract-audit
```

It holds content, pipeline, deterministic compression model, and configuration constant. The active
query and cache contract are the manipulated variables.

| Condition | Model calls | Second query cache hit | Output changed with query |
|---|---:|---:|---:|
| Installed content-only behavior | 1 | yes | no |
| Cache disabled intervention | 2 | no | yes |
| Query-aware reference intervention | 2 | no | yes |

Repeating the second query under the query-aware reference condition does produce a cache hit,
showing that safe reuse remains possible within a stable intent.

The audit confirms that PariTok 1.3.3's installed compression pipeline can reuse a transformation
created for one query after the query changes. This strengthens the proposed mechanism behind Wave
A, but does not prove it was the sole cause of every terminal failure because the privacy-safe live
events did not retain raw completions or transformed contexts.

Artifact: `artifacts/query-sensitive-cache-audit.json`.

## Provider-free recovery regression

After prespecifying the protocol and gates, ContextOps exercised the actual local PariTok 4B
pipeline under the `query_aware` contract on the four original 32K/5-turn workloads. Across three
signal-bearing segments per workload it observed:

- 0/12 cross-query cache hits after intent changed;
- 12/12 same-query replay cache hits;
- 12/12 task-critical signals retained by raw compressed output;
- 12/12 signals retained after validation/fallback, with zero fallbacks;
- zero upstream provider requests and $0 provider cost.

The deterministic negative control also behaved as designed: content-only caching produced 12/12
cross-query hits and 0/12 raw signal recall, while the validator recovered guarded recall to 12/12
through exact-original fallback. Disabled and query-aware recovery conditions retained 24/24 raw
signals in total.

This closes the provider-free transformed-context recovery gate. It does **not** establish end-task
semantic equivalence, provider compatibility, or acceptable synchronous latency, so Wave B remains
ineligible. Protocol and reports: `provider-free-regression-protocol.md`,
`provider-free-deterministic-regression.md`, and `provider-free-local-4b-regression.md`.

## Runtime isolation contract

The live configuration supports three states:

- `unverified`: default; multi-turn intent changes are blocked;
- `disabled`: execution may proceed without reusable compression cache;
- `query_aware`: execution may proceed when the integration has verified query-scoped reuse.

Historical Wave A configs intentionally remain unchanged and therefore resolve to `unverified`.
Reproducing an unsafe research condition requires both live-cost confirmation and:

```bash
contextops-lab live-session-run \
  --stage wave_a \
  --allow-unsafe-query-sensitive-cache-experiment \
  --confirm-live-costs
```

That override permits measurement only; it cannot make the cohort rollout-eligible.

## Evidence ladder

1. **Observed live evidence:** Wave A treatment failed 4/4 terminal task proxies.
2. **Code-supported mechanism:** the installed pipeline derives its compressed-cache lookup from
   content identity while compression accepts the active query as an input.
3. **Controlled mechanism test:** changing only the query reused the first transformation under the
   installed behavior; disabling or query-scoping cache removed that reuse.
4. **Still unknown:** the fraction of Wave A failure attributable to cache reuse versus other
   signal-retention or recovery failures.

This separation prevents a controlled mechanism demonstration from being overstated as complete
live causal attribution.

## Interview narrative

**Situation:** A context-compression treatment cut observed provider cost by nearly 90%, but failed
all four terminal multi-turn task proxies and increased median latency about 16 times.

**Task:** Decide whether to expand the experiment, repair the dependency immediately, or protect the
product while isolating the cause.

**Action:** I stopped the paid expansion, traced a query-sensitive cache hypothesis, built a
provider-free controlled diagnostic, compared content-only, disabled, and query-aware cache
conditions, and added a fail-closed runtime contract with an explicitly non-rollout research escape
hatch.

**Result:** ContextOps prevented a misleading cost-only launch decision, preserved $0.843399 of the
authorized budget, converted an ambiguous failure into reproducible evidence, and established clear
criteria for a small recovery pilot. The upstream implementation remains external; ContextOps owns
the evaluation and safety decision.

## Recovery gate

Do not start Wave B until all of the following are true:

1. the integration declares and verifies `disabled` or `query_aware` cache behavior;
2. the original four Wave A scenarios recover 4/4 terminal task-proxy success in a provider-backed
   recovery pilot (provider-free transformed-context recovery is complete);
3. intermediate protocol success remains 16/16;
4. transformed-context validation or exact-original fallback is available before the upstream call
   (now implemented and contract-tested in the ContextOps-safe external HTTP proxy; provider-backed
   recovery remains unobserved);
5. latency passes a separately declared synchronous or asynchronous workload threshold.

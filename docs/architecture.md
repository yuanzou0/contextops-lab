# ContextOps Lab architecture

ContextOps Lab is the decision and safety layer around a context-compression treatment. PariTok is
the first treatment implementation; it is deliberately kept outside the evidence, policy, and
fallback ownership boundary.

```text
Workload + identical model configuration
                  |
          paired experiment runner
             /             \
      direct baseline     ContextOps safe proxy
                              |
                  query-scoped cache isolation
                              |
                  PariTok compression pipeline
                              |
                 validation of transformed context
                      /                 \
                   pass              reject/error
                     |                    |
             compressed context     exact original
                      \                 /
                         upstream model
                              |
             events + safety telemetry + reviews
                              |
                  evidence gates and rollout policy
```

## Owned boundaries

| Boundary | ContextOps responsibility | Fail-closed behavior |
|---|---|---|
| Experiment | Paired ordering, identical task/model inputs, versioned configuration | Reject incomplete or unattributable runs |
| Cache | Declare and observe `disabled` or `query_aware` semantics | Block multi-turn runs with an unverified contract |
| Transformation | Check structure, references, expansion, and required signals | Forward the byte-exact original |
| Telemetry | Record counters, timings, reasons, and lineage without raw context | Reject verified-cache claims without the safety endpoint |
| Evidence | Separate deterministic, task-proxy, reviewed semantic, and production claims | Keep rollout off when a gate is missing |
| Policy | Convert quality, cost, latency, sample, and review gates into a decision | Production remains locked for non-production evidence |

## External boundary

PariTok owns its model, compression strategy, native proxy, and upstream release lifecycle.
ContextOps pins a supported version, verifies it against
[`configs/paritok-compatibility.json`](../configs/paritok-compatibility.json), and never silently
transfers evidence across versions. The wrapper is intentionally thin: it supplies cache isolation,
post-transformation validation, exact-original fallback, and observable safety counters without
forking the compressor.

## Runtime invariants

1. Baseline and treatment use the same task, model, sampling configuration, and pricing registry.
2. Multi-turn execution cannot declare an unverified cache contract unless an explicit
   research-only override is used; overridden runs are never rollout-eligible.
3. A rejected transformation or backend failure cannot replace the input with a partial summary;
   the exact original is forwarded.
4. A supported dependency version must pass its versioned provider-free compatibility contract.
5. Provider-free success proves only the local transformation boundary. Provider task quality,
   interactive latency, and production safety require their own evidence.
6. No production rollout policy is generated from fixture, deterministic, or task-proxy evidence.

## Evidence levels

```text
L0  Unit and deterministic fixtures
L1  Provider-free real-pipeline boundary tests
L2  Bounded provider-backed paired task-proxy pilot
L3  Independently reviewed semantic non-inferiority study
L4  Production canary with rollback and observability
```

Progress at a lower level cannot satisfy a higher-level gate. This is the main architectural
distinction between ContextOps Lab and a generic compression benchmark.

# Phase 3 provider-backed recovery pilot readiness

## Outcome

**BLOCKED BEFORE PROVIDER.** The provider-backed run did not start because
`CONTEXTOPS_PROVIDER_API_KEY` and `OPENAI_API_KEY` were absent from the task environment. No
provider request was made, provider cost is **$0.00**, no real user data was used, and no secret or
raw prompt was recorded.

This is a missing execution precondition, not a failed primary recovery gate. The primary gates in
`phase-3-recovery-protocol.md` remain unobserved. The authorized ceiling remains **$1.25** for the
fixed 40-request Wave A pilot.

## Zero-cost readiness checks

| Check | Result |
|---|---:|
| Fixed recovery config | PASS |
| Workload preflight | PASS |
| Query-aware cache contract audit | PASS |
| Ollama model listing (`paritok-4b-v1`) | PASS |
| PariTok gateway health | PASS |
| ContextOps safety boundary | PASS |
| Real Redis durable context store | PASS |
| Proxy requests before paid run | 0 |

The local runtime used Ollama 0.34.2, PariTok 1.3.11, Redis 7.4.5, and the model content ID
`86fa6d2593e2`. The safety boundary reported `query_aware`, exact-original fallback on validator
rejection, and Redis storage.

## Local latency warning

The provider-free local probe observed 46,415.45 ms for the cold candidate, 130,295.94 ms for a
warm uncached transformation, and 2.36 ms for exact-input cache reuse. The uncached local path is
therefore already ineligible under the 500 ms rollout latency budget. A successful task-proxy
recovery pilot would not override this separate latency gate.

## Reproduction

```bash
contextops-lab workload-audit \
  --stage wave_a \
  --model gpt-5.6-luna \
  --output artifacts/phase-3-recovery-preflight.json \
  --report docs/phase-3-recovery-preflight.md

contextops-lab cache-contract-audit \
  --output artifacts/phase-3-recovery-cache-audit.json

contextops-lab doctor \
  --live-config configs/phase-3-luna-recovery.json \
  --probe-live

contextops-lab local-latency-probe \
  --confirm-backend-restarted \
  --model paritok-4b-v1 \
  --output artifacts/phase-3-recovery-local-latency.json
```

The doctor probe calls only local health, statistics, and model-list endpoints. It does not send a
provider completion. The paid command must not be run until both required environment variables
are present and the local services have been restarted and re-probed.

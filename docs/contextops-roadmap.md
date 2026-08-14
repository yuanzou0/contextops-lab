# ContextOps Lab Roadmap

## Product judgment

PariTok is the first planned treatment evaluated by ContextOps Lab. The product opportunity is not “compress harder”; it is to make every saving observable, quality-aware, and safely reversible. For a portfolio targeting data analysis, AI product management, and Applied AI, the strongest project is an independent evaluation and control layer that can compare multiple compressors.

## P0 — Make failure safe

Status labels below are authoritative: **complete** means implemented and tested in this
repository; **partial/external** means only part of the behavior exists or belongs to PariTok;
**proposed** means roadmap only and must not be described as shipped in a résumé or interview.

### 1. Compression validation and automatic fallback

**Status: complete (ContextOps Lab).**

- **Problem:** Empty, malformed, or identifier-damaging summaries can silently corrupt an agent task.
- **Build:** Validate non-empty output, reference integrity, required identifiers, file paths, error strings, and size bounds. On failure, forward the original and emit a structured fallback event.
- **Acceptance:** Zero silent empty outputs; 100% of rejected compressions use original content; every fallback has a reason code.
- **Portfolio value:** Demonstrates product guardrails, Python validation, observability, and reliability ownership.

### 2. Adaptive tool discovery

**Status: isolation complete; upstream repair external.** PariTok 1.3.3 supplies tool filtering and
ContextOps measures its telemetry, but ContextOps Lab has not implemented its own recovery engine.
Wave A exposed a query-sensitive cache risk: content cached under an intermediate intent may be
reused after the user task changes. A provider-free controlled audit reproduced that behavior in
the installed pipeline. Runtime execution now fails closed unless the cache contract is declared
`disabled` or `query_aware`; a research override is explicitly never rollout-eligible.

- **Problem:** Freezing tool selection helps prompt caching but can fail when the user changes goals mid-session.
- **Build:** Keep a permanent core-tool allowlist, detect intent drift, refresh only the optional tool segment, and provide deterministic full-schema recovery.
- **Acceptance:** Core tools are never dropped; tool false-negative rate is measured; task pivots recover without restarting the session.

### 3. Durable, versioned original-context storage

**Status: proposed.** No Redis deployment, tenant isolation, encryption, or restart-recovery suite
is implemented in this repository.

- **Problem:** In-memory references disappear on restart or expiration.
- **Build:** Make Redis the production default, namespace references by tenant/session, store content version and expiry metadata, encrypt sensitive originals, and expose retrieval health.
- **Acceptance:** Restart recovery tests pass; expired references return an explicit status; tenant isolation tests pass.

### 4. Protocol compatibility regression suite

**Status: proposed.** Current mocked tests cover the OpenAI-compatible path used by Phase 3; they
are not a multi-provider golden conformance suite.

- **Problem:** Anthropic, OpenAI Chat Completions, Responses, Gemini-compatible tools, and streaming have different edge cases.
- **Build:** Golden request/response fixtures covering tool calls, streaming, errors, images, custom tools, and recovery loops.
- **Acceptance:** Every supported provider has conformance tests; releases are blocked on regression.

## P1 — Prove product value

### 5. Evaluation lab and analytics dashboard

**Status: partial.** The lab, dashboard, cost and latency metrics are implemented. The Luna smoke
has one pair per segment, so non-inferiority remains unproven pending the 20-scenario evidence stage
and independent quality reviews.

- **Build:** Run paired compressed/uncompressed tasks and display cost per successful task, quality-adjusted savings, P50/P95 latency, recall rate, tool false negatives, and fallback rate.
- **Segment:** Session length, tool count, task type, repository size, language, upstream model, and deployment mode.
- **Decision:** Enable compression only for cohorts where the confidence interval supports positive net value.

### 6. Risk-aware compression policy

**Status: partial.** A deterministic latency-aware eligibility rule now keeps short synchronous
requests off and allows long amortizable contexts, but it has not been calibrated on 32K/128K live
evidence.

- **Build:** Select compression level using content type, age, task intent, edit risk, identifier density, and available context budget.
- **Policy examples:** Preserve exact current-file edit context; compress stale logs aggressively; summarize old reasoning only near the context threshold.
- **Acceptance:** Lower quality-adjusted cost than a single fixed policy without violating success-rate guardrails.

### 7. Preflight and explainability

**Status: complete for the OpenAI/PariTok path; broader provider support proposed.**

- **Build:** Add a `doctor` command and per-request explanation: backend health, selected tools, compressed blocks, fallback reason, privacy mode, and expected/realized savings.
- **Acceptance:** Setup failures are actionable; silent no-op compression is distinguishable from “nothing eligible to compress.”

## P2 — Productize and differentiate

### 8. Workload recommender

Use historical session features to recommend `off`, `balanced`, or `aggressive` mode and estimate break-even volume. Keep the first version rule-based and auditable before adding ML.

### 9. Privacy and governance controls

Add local-only enforcement, redaction rules, data-retention policy, audit logs, tenant quotas, and hosted-mode consent. Never include raw code or secrets in analytics.

### 10. Multi-language evaluation and training data

Expand verified coverage to TypeScript, Go, Rust, and Java. Use language-specific identifier and AST-aware preservation tests before claiming general support.

## Recommended portfolio scope

Build items 1, 5, and 7 first. Together they form a coherent product:

1. a safe compression gateway wrapper;
2. a paired evaluation harness;
3. an analytics dashboard;
4. a preflight and diagnostics experience;
5. an evidence-backed rollout recommendation.

This scope is more relevant to the target roles than retraining a 4B model and is feasible to explain end to end in interviews.

## Delivery status

- **Phase 1 — reliable MVP:** complete with 36 deterministic paired cases, validation, and fallback.
- **Phase 2 — product decision loop:** complete with segmentation, failure analysis, dashboard,
  evidence-gated policy, runtime modes, and diagnostics.
- **Phase 3 — production-shaped evidence:** integration contract completed in v0.3.0; v0.4.0 added
  the staged workload and cost preflight; v0.5.0 adds real multi-turn execution, fail-closed local
  model checks, atomic evidence output, and verified local PariTok/Ollama readiness. The Luna smoke
  is complete but insufficient for a quality non-inferiority claim. The proposed evidence stage has
  five 32K/128K pairs per workload and requires independent human/LLM review. A 32K/5-turn Wave A
  pilot subsequently failed the terminal task proxy in 4/4 treatment workloads, so expansion is
  stopped. Query-sensitive cache reuse is now isolated and reproduced provider-free, while an
  upstream cache repair and the external-proxy fallback boundary remain prerequisites for a
  recovery pilot. See `phase-3-acceptance.md` and `query-sensitive-cache-decision.md`.

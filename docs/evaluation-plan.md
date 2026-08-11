# Evaluation Plan

## Decision question

For which AI-agent workloads does a configured compression treatment reduce cost per successful task without unacceptable quality or latency degradation?

## Experimental design

- Use paired A/B runs on identical task and repository snapshots.
- Control upstream model, temperature, tools, system prompt, token budget, and retry policy.
- Randomize arm order to reduce temporal and cache effects.
- Start with 30–50 tasks for pipeline debugging; expand before making production claims.
- Include long/read-heavy, debugging, edit-heavy, short/simple, MCP-heavy, and task-pivot scenarios.

## Event schema

Record per request:

| Field group | Examples |
|---|---|
| Identity | experiment, arm, task, session, turn |
| Workload | language, task type, repository size, tool count |
| Tokens | original, compressed, recalled, upstream input/output |
| Performance | compression, first-token, and end-to-end latency |
| Reliability | validator result, fallback reason, recall success, upstream status |
| Outcome | tests passed, task success, human intervention, retries |
| Economics | compressor compute cost, upstream cost, total task cost |

Do not log raw prompts, source code, credentials, or file contents.

## KPI tree

Primary:

`Cost per successful task = total experiment cost / successful tasks`

Supporting metrics:

- quality-adjusted token savings;
- task completion rate and test pass rate;
- P50/P95 latency;
- exact-original retrieval success;
- tool-selection false-negative rate;
- silent failure, fallback, retry, and manual-intervention rates.

## Analysis

- Report paired differences and confidence intervals.
- Segment results by workload rather than presenting only a global average.
- Separate measured results from projections.
- Treat failed tasks as costs, not as excluded observations.
- Price local GPU inference and hosted compression explicitly.

## Release gate

Ship a cohort only when:

1. silent data loss is zero;
2. task success stays within the declared non-inferiority margin;
3. cost per successful task improves;
4. P95 latency remains within the target budget;
5. recall and fallback paths pass reliability tests.

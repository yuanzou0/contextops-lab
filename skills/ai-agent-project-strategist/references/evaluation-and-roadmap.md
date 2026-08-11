# Evaluation and Roadmap Reference

## Minimum credible evaluation

Use paired runs over the same tasks, repository snapshot, upstream model, prompts, tools, and temperature. Include at least these workload strata:

- short vs. long sessions;
- few vs. many tools;
- read-heavy, debugging, and edit-heavy tasks;
- Python and at least one non-Python language;
- clean success, recoverable failure, and hard failure cases.

Capture one event per request with session/task identifiers, experimental arm, model, original/compressed tokens, tool counts, compression latency, total latency, recall events, fallback reason, task result, test result, and estimated cost. Remove secrets and repository content from analytics events.

## Decision metrics

Primary metric:

`quality_adjusted_cost = total_cost / successful_tasks`

Guardrails:

- task success must not fall below the predeclared margin;
- silent data loss must be zero;
- P95 latency must remain within the target budget;
- exact-original retrieval must meet the reliability target;
- tool false negatives must trigger a recoverable fallback.

Report confidence intervals and paired differences. Do not infer production impact from a handful of hand-picked sessions.

## Roadmap scoring

Score each proposal from 1–5 on user impact, evidence strength, role relevance, implementation effort, and differentiation. Suggested priority score:

`(impact × evidence × role_relevance × differentiation) / effort`

Correctness work can override the numeric score. Any failure that silently changes or deletes context is P0.

For every roadmap item provide:

1. user problem;
2. current failure mode;
3. proposed behavior;
4. implementation surface;
5. acceptance criteria;
6. measurement plan;
7. risks and rollback;
8. résumé evidence created.

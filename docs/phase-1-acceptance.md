# Phase 1 Acceptance Criteria

## Positioning

- The repository headline presents an AI infrastructure evaluation lab.
- Career-positioning material and the reusable Skill are supporting assets only.
- Upstream PariTok authorship and benchmark claims are clearly attributed.

## Reliability

- Empty compressor output always falls back to original content.
- Malformed or unavailable references are rejected.
- Missing task-critical identifiers, paths, and error types produce structured reasons.
- Validator rejection never forwards the rejected compressed content.

## Experiment integrity

- Every task runs in both baseline and PariTok arms.
- Arm order is randomized with a reproducible seed.
- Failed tasks remain in the event dataset and cost denominator.
- Events do not contain prompts, source code, credentials, or raw file content.

## Metrics

- Cost per successful task is reported by arm.
- Task success, fallback rate, effective token ratio, median latency, and P95 latency are available.
- The initial 36-task manifest is explicitly an MVP inventory, not production evidence.

## Release gate

Do not recommend rollout until the framework is connected to real executors and task outcomes. Phase 1 proves the measurement and safety mechanics; it does not prove PariTok's business impact.

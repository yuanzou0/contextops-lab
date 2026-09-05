# Quality review protocol

Deterministic marker recall remains a safety invariant, not a complete quality score. A claim that
compression is quality-equivalent requires independent review of every terminal arm in the evidence
stage.

## Rubric

Score each blinded response from 0 to 1 on:

1. task completion and factual correctness;
2. exact identifier, path, and error preservation;
3. unsupported claims or invented evidence;
4. instruction adherence and actionability.

Use either two human reviewers for a stratified sample with adjudication, or a versioned LLM judge
plus at least 20% human calibration. Reviewer identity, method, score, and a bounded rationale code
must be stored; raw private context must not be placed in analytics events.

## JSONL review contract

```json
{"task_id":"read-heavy-32k-5t","arm":"compressed","method":"human","reviewer_id":"r1","score":0.9,"rationale_code":"correct_complete"}
```

Run `contextops-lab evidence-audit --reviews path/to/reviews.jsonl`. The quality claim remains
blocked until every terminal arm is reviewed, every workload has at least five paired tasks, and
both 32K and 128K contexts are present. Each arm must score at least 0.8, and the conservative 95%
lower bound of the paired treatment-minus-baseline score must stay above the -0.05
non-inferiority margin in every workload. No review rows are fabricated in this repository.

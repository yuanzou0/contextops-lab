"""Evidence sufficiency and quality-review contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import statistics
from typing import Iterable

from .models import ExperimentArm, RequestEvent


@dataclass(frozen=True, slots=True)
class QualityReview:
    task_id: str
    arm: ExperimentArm
    method: str
    reviewer_id: str
    score: float
    rationale_code: str

    def __post_init__(self) -> None:
        if self.method not in {"human", "llm_judge"}:
            raise ValueError("quality review method must be human or llm_judge")
        if not 0 <= self.score <= 1:
            raise ValueError("quality review score must be in [0, 1]")

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["arm"] = self.arm.value
        return payload


def load_reviews(path: str | Path | None) -> list[QualityReview]:
    if path is None:
        return []
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
    return [
        QualityReview(
            task_id=row["task_id"],
            arm=ExperimentArm(row["arm"]),
            method=row["method"],
            reviewer_id=row["reviewer_id"],
            score=float(row["score"]),
            rationale_code=row["rationale_code"],
        )
        for row in rows
    ]


def audit_evidence(
    events: Iterable[RequestEvent],
    reviews: Iterable[QualityReview] = (),
    *,
    minimum_pairs_per_segment: int = 5,
    required_contexts: tuple[int, ...] = (32_000, 128_000),
    required_task_types: tuple[str, ...] = (
        "read_heavy",
        "debugging",
        "mcp_heavy",
        "edit_critical",
    ),
    minimum_review_score: float = 0.8,
    quality_noninferiority_margin: float = 0.05,
) -> dict:
    terminal = [event for event in events if event.is_terminal_turn]
    review_rows = list(reviews)
    task_types = sorted(set(required_task_types) | {event.task_type for event in terminal})
    segment_rows = []
    for task_type in task_types:
        rows = [event for event in terminal if event.task_type == task_type]
        arms_by_task: dict[str, set[ExperimentArm]] = {}
        for event in rows:
            arms_by_task.setdefault(event.task_id, set()).add(event.arm)
        paired_ids = {
            task_id
            for task_id, arms in arms_by_task.items()
            if {ExperimentArm.BASELINE, ExperimentArm.COMPRESSED} <= arms
        }
        contexts = sorted({event.context_tokens for event in rows if event.task_id in paired_ids})
        segment_rows.append(
            {
                "task_type": task_type,
                "paired_tasks": len(paired_ids),
                "contexts": contexts,
                "sample_gate_passed": len(paired_ids) >= minimum_pairs_per_segment,
            }
        )
    observed_contexts = {event.context_tokens for event in terminal}
    reviews_by_key = {(row.task_id, row.arm): row for row in review_rows}
    reviewed = set(reviews_by_key)
    terminal_keys = {(event.task_id, event.arm) for event in terminal}
    quality_segments = []
    for task_type in task_types:
        task_ids = sorted({event.task_id for event in terminal if event.task_type == task_type})
        paired_deltas = []
        scores = []
        for task_id in task_ids:
            baseline = reviews_by_key.get((task_id, ExperimentArm.BASELINE))
            treatment = reviews_by_key.get((task_id, ExperimentArm.COMPRESSED))
            if baseline is None or treatment is None:
                continue
            scores.extend((baseline.score, treatment.score))
            paired_deltas.append(treatment.score - baseline.score)
        mean_delta = statistics.fmean(paired_deltas) if paired_deltas else None
        if len(paired_deltas) >= 2:
            standard_error = statistics.stdev(paired_deltas) / math.sqrt(len(paired_deltas))
            ci_low = mean_delta - 2.776 * standard_error
        else:
            ci_low = mean_delta
        gate_passed = (
            len(paired_deltas) >= minimum_pairs_per_segment
            and bool(scores)
            and min(scores) >= minimum_review_score
            and ci_low is not None
            and ci_low >= -quality_noninferiority_margin
        )
        quality_segments.append(
            {
                "task_type": task_type,
                "paired_reviews": len(paired_deltas),
                "minimum_score": min(scores) if scores else None,
                "mean_treatment_minus_baseline": mean_delta,
                "conservative_95pct_ci_low": ci_low,
                "gate_passed": gate_passed,
            }
        )
    coverage_passed = bool(terminal_keys) and terminal_keys <= reviewed
    score_gate_passed = bool(quality_segments) and all(
        row["gate_passed"] for row in quality_segments
    )
    review_gate_passed = coverage_passed and score_gate_passed
    sample_gate_passed = bool(segment_rows) and all(
        row["sample_gate_passed"] for row in segment_rows
    )
    context_gate_passed = set(required_contexts) <= observed_contexts
    return {
        "schema_version": 1,
        "minimum_pairs_per_segment": minimum_pairs_per_segment,
        "required_contexts": list(required_contexts),
        "required_task_types": list(required_task_types),
        "minimum_review_score": minimum_review_score,
        "quality_noninferiority_margin": quality_noninferiority_margin,
        "segments": segment_rows,
        "sample_gate_passed": sample_gate_passed,
        "context_gate_passed": context_gate_passed,
        "quality_review": {
            "reviewed_terminal_arms": len(reviewed & terminal_keys),
            "terminal_arms": len(terminal_keys),
            "methods": sorted({row.method for row in review_rows}),
            "coverage_passed": coverage_passed,
            "segments": quality_segments,
            "gate_passed": review_gate_passed,
        },
        "quality_claim_allowed": sample_gate_passed
        and context_gate_passed
        and review_gate_passed,
    }

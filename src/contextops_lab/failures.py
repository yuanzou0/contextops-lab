"""Failure taxonomy and root-cause aggregation."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable

from .models import RequestEvent


class FailureCategory(str, Enum):
    VALIDATION_FALLBACK = "validation_fallback"
    TASK_FAILURE = "task_failure"
    TEST_FAILURE = "test_failure"
    MANUAL_INTERVENTION = "manual_intervention"
    UPSTREAM_ERROR = "upstream_error"
    SILENT_FAILURE = "silent_failure"


@dataclass(frozen=True, slots=True)
class FailureSummary:
    category: str
    reason: str
    count: int
    rate: float

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_failures(events: Iterable[RequestEvent]) -> list[FailureSummary]:
    rows = list(events)
    counts: Counter[tuple[str, str]] = Counter()
    for event in rows:
        if event.fallback_reason:
            counts[(FailureCategory.VALIDATION_FALLBACK.value, event.fallback_reason)] += 1
        if not event.task_success:
            counts[(FailureCategory.TASK_FAILURE.value, event.failure_reason or "unspecified")] += 1
        if event.tests_passed is False:
            counts[(FailureCategory.TEST_FAILURE.value, event.failure_reason or "tests_failed")] += 1
        if event.manual_intervention:
            counts[(FailureCategory.MANUAL_INTERVENTION.value, "manual_intervention")] += 1
        if event.upstream_error:
            counts[(FailureCategory.UPSTREAM_ERROR.value, event.upstream_error)] += 1
        if event.silent_failure:
            counts[(FailureCategory.SILENT_FAILURE.value, "silent_failure")] += 1
    denominator = max(1, len(rows))
    return [
        FailureSummary(category, reason, count, count / denominator)
        for (category, reason), count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]

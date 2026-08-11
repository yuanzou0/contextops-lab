"""Provider-neutral paired experiment orchestration."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Callable, Iterable

from .models import ExperimentArm, RequestEvent


@dataclass(frozen=True, slots=True)
class ExperimentTask:
    task_id: str
    task_type: str
    language: str
    repo_size: int
    tool_count: int
    session_length: int


@dataclass(frozen=True, slots=True)
class RunOutcome:
    event: RequestEvent


Executor = Callable[[ExperimentTask, ExperimentArm], RunOutcome]
EventWriter = Callable[[RequestEvent], None]


class PairedExperimentRunner:
    def __init__(self, executor: Executor, event_writer: EventWriter, seed: int = 17):
        self.executor = executor
        self.event_writer = event_writer
        self.random = random.Random(seed)

    def run(self, tasks: Iterable[ExperimentTask]) -> list[RunOutcome]:
        outcomes: list[RunOutcome] = []
        for task in tasks:
            arms = [ExperimentArm.BASELINE, ExperimentArm.COMPRESSED]
            self.random.shuffle(arms)
            for arm in arms:
                outcome = self.executor(task, arm)
                if outcome.event.task_id != task.task_id or outcome.event.arm != arm:
                    raise ValueError("Executor returned an event for the wrong task or arm")
                normalized = replace(outcome, event=outcome.event)
                self.event_writer(normalized.event)
                outcomes.append(normalized)
        return outcomes

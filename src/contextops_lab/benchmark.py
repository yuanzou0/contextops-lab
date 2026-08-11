"""Executable benchmark cases derived from the Phase 1 workload manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .experiments import ExperimentTask


_EXTENSIONS = {
    "python": "py",
    "typescript": "ts",
    "go": "go",
    "java": "java",
    "rust": "rs",
}


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    task: ExperimentTask
    instruction: str
    original_context: str
    required_signals: tuple[str, ...]
    expected_markers: tuple[str, ...]

    @property
    def task_id(self) -> str:
        return self.task.task_id

    def is_success(self, response: str) -> bool:
        return all(marker in response for marker in self.expected_markers)


def _build_case(row: dict) -> BenchmarkCase:
    task = ExperimentTask(
        task_id=row["task_id"],
        task_type=row["task_type"],
        language=row["language"],
        repo_size=int(row["repo_size"]),
        tool_count=int(row["tool_count"]),
        session_length=int(row["session_length"]),
    )
    extension = _EXTENSIONS[task.language]
    identifier = f"anchor_{task.task_id}"
    error_name = f"{task.task_id.title().replace('_', '')}Error"
    file_path = f"src/{task.language}/{task.task_id}.{extension}"
    mode = "empty" if sum(ord(char) for char in task.task_id) % 11 == 0 else "normal"
    original_context = "\n".join(
        (
            f"CASE: {task.task_id}",
            f"WORKLOAD: {task.task_type}",
            f"COMPRESSION_TEST: {mode}",
            "The surrounding discussion contains historical implementation details, repeated "
            "observations, and low-priority notes used to exercise context reduction.",
            f"KEEP: identifier={identifier}",
            f"KEEP: file={file_path}",
            f"KEEP: error={error_name}",
            "The final answer must preserve every KEEP value exactly so that the deterministic "
            "oracle can evaluate task completion without storing private source code.",
        )
    )
    required = (identifier, file_path, error_name)
    return BenchmarkCase(
        task=task,
        instruction="Return the identifier, file path, and error name required by this case.",
        original_context=original_context,
        required_signals=required,
        expected_markers=required,
    )


def load_benchmark_cases(path: str | Path) -> list[BenchmarkCase]:
    """Load and validate the 30–50 task MVP manifest as executable cases."""
    manifest = Path(path)
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    if not 30 <= len(rows) <= 50:
        raise ValueError(f"Phase 1 requires 30–50 tasks; found {len(rows)}")
    identifiers = [row["task_id"] for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Benchmark task_id values must be unique")
    missing_languages = sorted(set(row["language"] for row in rows) - set(_EXTENSIONS))
    if missing_languages:
        raise ValueError(f"Unsupported benchmark languages: {', '.join(missing_languages)}")
    return [_build_case(row) for row in rows]

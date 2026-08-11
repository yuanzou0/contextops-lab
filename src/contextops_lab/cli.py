"""Command-line entry point for the Phase 1 offline benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from .benchmark import load_benchmark_cases
from .events import JsonlEventStore
from .execution import DualArmExecutor
from .experiments import PairedExperimentRunner
from .fixtures import FixtureAgent, FixtureCompressor
from .models import ExperimentArm, RequestEvent
from .reporting import build_markdown_report


def _event_from_dict(row: dict) -> RequestEvent:
    row = dict(row)
    row["arm"] = ExperimentArm(row["arm"])
    return RequestEvent(**row)


def run_offline(args: argparse.Namespace) -> int:
    cases = load_benchmark_cases(args.manifest)
    events_path = Path(args.events)
    if events_path.exists():
        events_path.unlink()
    store = JsonlEventStore(events_path)
    executor = DualArmExecutor(FixtureAgent(), FixtureCompressor())
    runner = PairedExperimentRunner(executor, store.append, seed=args.seed)
    runner.run(cases)
    events = [_event_from_dict(row) for row in store.read_all()]
    report = build_markdown_report(events, evidence_label="offline deterministic pipeline validation")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"Executed {len(cases)} paired cases ({len(events)} arm runs)")
    print(f"Events: {events_path}")
    print(f"Report: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contextops-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)
    offline = subparsers.add_parser("offline-benchmark")
    offline.add_argument("--manifest", default="evals/tasks/mvp_tasks.jsonl")
    offline.add_argument("--events", default="artifacts/phase-1-events.jsonl")
    offline.add_argument("--report", default="docs/phase-1-analysis.md")
    offline.add_argument("--seed", type=int, default=17)
    offline.set_defaults(func=run_offline)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

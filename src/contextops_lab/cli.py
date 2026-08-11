"""Command-line entry point for benchmarks, analytics, policy, and diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from .benchmark import load_benchmark_cases
from .dashboard import build_dashboard, write_dashboard
from .doctor import CheckStatus, run_doctor
from .events import JsonlEventStore, load_events
from .execution import DualArmExecutor
from .experiments import PairedExperimentRunner
from .fixtures import FixtureAgent, FixtureCompressor
from .policy import generate_rollout_policy, write_policy
from .reporting import build_markdown_report, build_phase2_report


def run_offline(args: argparse.Namespace) -> int:
    cases = load_benchmark_cases(args.manifest)
    events_path = Path(args.events)
    if events_path.exists():
        events_path.unlink()
    store = JsonlEventStore(events_path)
    executor = DualArmExecutor(
        FixtureAgent(),
        FixtureCompressor(),
        recorded_at="2000-01-01T00:00:00Z",
        experiment_config_version="offline-fixture-v1",
        pricing_version="fixture-pricing-v1",
    )
    runner = PairedExperimentRunner(executor, store.append, seed=args.seed)
    runner.run(cases)
    events = load_events(events_path)
    report = build_markdown_report(events, evidence_label="offline deterministic pipeline validation")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"Executed {len(cases)} paired cases ({len(events)} arm runs)")
    print(f"Events: {events_path}")
    print(f"Report: {report_path}")
    return 0


def _load_policy(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_policy(args: argparse.Namespace) -> int:
    policy = generate_rollout_policy(
        load_events(args.events), evidence_label=args.evidence_label
    )
    write_policy(policy, args.output)
    print(f"Policy: {args.output}")
    return 0


def run_dashboard(args: argparse.Namespace) -> int:
    policy = _load_policy(args.policy)
    content = build_dashboard(
        load_events(args.events), policy, evidence_label=args.evidence_label
    )
    write_dashboard(content, args.output)
    print(f"Dashboard: {args.output}")
    return 0


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_phase2(args: argparse.Namespace) -> int:
    events = load_events(args.events)
    policy = generate_rollout_policy(events, evidence_label=args.evidence_label)
    write_policy(policy, args.policy)
    write_dashboard(
        build_dashboard(events, policy, evidence_label=args.evidence_label),
        args.dashboard,
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_phase2_report(events, policy, evidence_label=args.evidence_label),
        encoding="utf-8",
    )
    lineage = {
        "schema_version": 1,
        "generated": date.today().isoformat(),
        "evidence_label": args.evidence_label,
        "input": {"path": args.events, "sha256": _sha256(args.events), "events": len(events)},
        "outputs": {
            "policy": {"path": args.policy, "sha256": _sha256(args.policy)},
            "dashboard": {"path": args.dashboard, "sha256": _sha256(args.dashboard)},
            "report": {"path": args.report, "sha256": _sha256(args.report)},
        },
    }
    lineage_path = Path(args.lineage)
    lineage_path.parent.mkdir(parents=True, exist_ok=True)
    lineage_path.write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Policy: {args.policy}")
    print(f"Dashboard: {args.dashboard}")
    print(f"Report: {args.report}")
    print(f"Lineage: {args.lineage}")
    return 0


def run_doctor_command(args: argparse.Namespace) -> int:
    checks = run_doctor(
        manifest=args.manifest,
        events=args.events,
        policy=args.policy,
        compressor_command=args.compressor_command,
        agent_endpoint=args.agent_endpoint,
        api_key_environment=args.api_key_environment,
    )
    for check in checks:
        print(f"[{check.status.value.upper():4}] {check.name}: {check.message}")
    return int(any(check.status is CheckStatus.FAIL for check in checks))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contextops-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)
    offline = subparsers.add_parser("offline-benchmark")
    offline.add_argument("--manifest", default="evals/tasks/mvp_tasks.jsonl")
    offline.add_argument("--events", default="artifacts/phase-1-events.jsonl")
    offline.add_argument("--report", default="docs/phase-1-analysis.md")
    offline.add_argument("--seed", type=int, default=17)
    offline.set_defaults(func=run_offline)

    policy = subparsers.add_parser("policy", help="generate an evidence-gated rollout policy")
    policy.add_argument("--events", default="artifacts/phase-1-events.jsonl")
    policy.add_argument("--output", default="policies/rollout-policy.json")
    policy.add_argument("--evidence-label", default="offline_deterministic")
    policy.set_defaults(func=run_policy)

    dashboard = subparsers.add_parser("dashboard", help="generate a self-contained dashboard")
    dashboard.add_argument("--events", default="artifacts/phase-1-events.jsonl")
    dashboard.add_argument("--policy", default="policies/rollout-policy.json")
    dashboard.add_argument("--output", default="artifacts/phase-2-dashboard.html")
    dashboard.add_argument("--evidence-label", default="offline_deterministic")
    dashboard.set_defaults(func=run_dashboard)

    phase2 = subparsers.add_parser("phase-2", help="build all Phase 2 decision artifacts")
    phase2.add_argument("--events", default="artifacts/phase-1-events.jsonl")
    phase2.add_argument("--policy", default="policies/rollout-policy.json")
    phase2.add_argument("--dashboard", default="artifacts/phase-2-dashboard.html")
    phase2.add_argument("--report", default="docs/phase-2-report.md")
    phase2.add_argument("--lineage", default="artifacts/phase-2-lineage.json")
    phase2.add_argument("--evidence-label", default="offline_deterministic")
    phase2.set_defaults(func=run_phase2)

    doctor = subparsers.add_parser("doctor", help="diagnose data and integration readiness")
    doctor.add_argument("--manifest", default="evals/tasks/mvp_tasks.jsonl")
    doctor.add_argument("--events", default="artifacts/phase-1-events.jsonl")
    doctor.add_argument("--policy", default="policies/rollout-policy.json")
    doctor.add_argument("--compressor-command")
    doctor.add_argument("--agent-endpoint")
    doctor.add_argument("--api-key-environment")
    doctor.set_defaults(func=run_doctor_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

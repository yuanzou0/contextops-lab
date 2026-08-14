"""Command-line entry point for benchmarks, analytics, policy, and diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import date
from pathlib import Path

from .benchmark import load_benchmark_cases
from .cache_safety import audit_installed_paritok_cache, decide_cache_safety
from .compressors import ExtractiveRiskCompressor
from .dashboard import build_dashboard, write_dashboard
from .doctor import CheckStatus, run_doctor
from .economics import build_multi_turn_economics
from .events import JsonlEventStore, load_events
from .evidence import audit_evidence, load_reviews
from .execution import DualArmExecutor
from .execution import OpenAICompatibleAgent
from .experiments import PairedExperimentRunner
from .fixtures import FixtureAgent, FixtureCompressor
from .live import ProxyPairedExecutor
from .live_config import load_live_config
from .latency import decompose_paired_latency, measure_local_latency_states
from .metrics import summarize
from .paritok import PariTokGateway
from .policy import generate_rollout_policy, write_policy
from .provider_free_regression import (
    RegressionSpec,
    run_provider_free_regression,
    write_regression_artifacts,
)
from .reporting import build_markdown_report, build_phase2_report
from .session_live import MultiTurnProxyExecutor, run_paired_sessions
from .workloads import (
    audit_stage,
    build_audit_markdown,
    build_session_messages,
    load_pricing,
    load_workload_matrix,
    select_stage,
)


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


def run_compressor_compare(args: argparse.Namespace) -> int:
    cases = load_benchmark_cases(args.manifest)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    comparisons = {}
    for compressor in (FixtureCompressor(), ExtractiveRiskCompressor()):
        events = []
        executor = DualArmExecutor(
            FixtureAgent(),
            compressor,
            experiment_id=f"offline-{compressor.name}",
            recorded_at="2000-01-01T00:00:00Z",
            experiment_config_version="offline-compressor-comparison-v1",
            pricing_version="fixture-pricing-v1",
        )
        PairedExperimentRunner(executor, events.append, seed=args.seed).run(cases)
        comparisons[compressor.name] = summarize(events)
    payload = {
        "schema_version": 1,
        "evidence_label": "offline_adapter_comparison",
        "limitations": "Validates adapter comparability; does not reproduce PariTok live results.",
        "compressors": comparisons,
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Compared {len(comparisons)} compressor adapters across {len(cases)} cases")
    print(f"Comparison: {destination}")
    return 0


def run_evidence_audit(args: argparse.Namespace) -> int:
    payload = audit_evidence(load_events(args.events), load_reviews(args.reviews))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Evidence audit: {destination}")
    print(f"Quality claim allowed: {str(payload['quality_claim_allowed']).lower()}")
    return 0 if payload["quality_claim_allowed"] else 3


def run_cache_contract_audit(args: argparse.Namespace) -> int:
    try:
        payload = audit_installed_paritok_cache()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Cache contract audit: {destination}")
    print(
        "Content-only query reuse observed: "
        f"{str(payload['content_only_query_reuse_observed']).lower()}"
    )
    print(
        "Isolation interventions passed: "
        f"{str(payload['isolation_interventions_passed']).lower()}"
    )
    return 0 if payload["isolation_interventions_passed"] else 3


def run_provider_free_regression_command(args: argparse.Namespace) -> int:
    protocol = json.loads(Path(args.config).read_text(encoding="utf-8"))
    matrix, scenarios = load_workload_matrix(args.matrix)
    del matrix
    rule = protocol["scenario_filter"]
    selected = [
        scenario
        for scenario in scenarios
        if scenario.context_tokens == int(rule["context_tokens"])
        and scenario.session_turns == int(rule["session_turns"])
        and scenario.task_type in set(rule["task_types"])
    ]
    condition_key = (
        "deterministic_conditions" if args.engine == "deterministic" else "local_conditions"
    )
    spec = RegressionSpec(
        engine=args.engine,
        conditions=tuple(protocol[condition_key]),
        stage=protocol["stage"],
        config_version=protocol["config_version"],
    )
    try:
        payload = run_provider_free_regression(selected, spec)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    write_regression_artifacts(payload, args.output, args.report)
    print(f"Provider-free regression: {args.output}")
    print(f"Report: {args.report}")
    print(f"Provider requests / cost: {payload['provider_requests']} / $0.00")
    passed = (
        payload["cache_behavior_all_passed"]
        and payload["guarded_safety_all_passed"]
        and payload["recovery_conditions_raw_quality_passed"]
    )
    return 0 if passed else 3


def run_latency_audit(args: argparse.Namespace) -> int:
    rows = [row.to_dict() for row in decompose_paired_latency(load_events(args.events))]
    payload = {
        "schema_version": 1,
        "measurement": "paired_estimate",
        "limitation": (
            "PariTok 1.3.3 exposes no split timing header; incremental latency combines local "
            "compression and proxy overhead."
        ),
        "pairs": rows,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Latency audit: {destination}")
    return 0


def run_local_latency_probe(args: argparse.Namespace) -> int:
    try:
        from paritok.config import ParitokConfig
        from paritok.pipelines.compress import CompressionPipeline
    except ImportError:
        print("Install the live extra: python -m pip install -e '.[live]'", file=sys.stderr)
        return 2
    matrix, scenarios = load_workload_matrix(args.matrix)
    del matrix
    by_id = {item.scenario_id: item for item in scenarios}
    try:
        cold_scenario = by_id[args.scenario]
        warm_scenario = by_id[args.warm_scenario]
    except KeyError as error:
        print(f"Unknown scenario: {error.args[0]}", file=sys.stderr)
        return 2
    if cold_scenario.context_tokens != warm_scenario.context_tokens:
        print("Cold and warm scenarios must use the same context band", file=sys.stderr)
        return 2

    def tool_content(scenario):
        return next(
            message["content"]
            for message in build_session_messages(scenario)[-1]
            if message["role"] == "tool"
        )

    pipeline = CompressionPipeline(ParitokConfig())
    payload = measure_local_latency_states(
        lambda content: pipeline.compress(
            content,
            query="Preserve critical software evidence",
            upstream_model=args.model,
        ),
        tool_content(cold_scenario),
        tool_content(warm_scenario),
    )
    payload["cold_scenario_id"] = cold_scenario.scenario_id
    payload["warm_uncached_scenario_id"] = warm_scenario.scenario_id
    payload["backend_restarted_before_probe"] = args.confirm_backend_restarted
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Local latency probe: {destination}")
    return 0


def run_multi_turn_economics(args: argparse.Namespace) -> int:
    payload = build_multi_turn_economics(
        load_events(args.events),
        latency_value_usd_per_second=args.latency_value_usd_per_second,
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Multi-turn economics: {destination}")
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
        live_config=args.live_config,
        probe_live=args.probe_live,
    )
    for check in checks:
        print(f"[{check.status.value.upper():4}] {check.name}: {check.message}")
    return int(any(check.status is CheckStatus.FAIL for check in checks))


def run_live(args: argparse.Namespace) -> int:
    if not args.confirm_live_costs:
        print("Refusing live model calls without --confirm-live-costs", file=sys.stderr)
        return 2
    config, config_sha256 = load_live_config(args.config)
    if not config.api_key:
        print(
            f"Missing API key environment variable: {config.api_key_environment}",
            file=sys.stderr,
        )
        return 2
    gateway = PariTokGateway(
        config.paritok_health_url,
        config.paritok_stats_url,
        timeout_seconds=min(config.timeout_seconds, 10.0),
    )
    health = gateway.health()
    gateway.stats()
    gateway.require_compression_model(
        config.compression_backend_models_url,
        config.compression_model,
    )
    common = {
        "model": config.model,
        "api_key": config.api_key,
        "input_cost_per_million": config.input_cost_per_million,
        "output_cost_per_million": config.output_cost_per_million,
        "timeout_seconds": config.timeout_seconds,
        "temperature": config.temperature,
        "max_retries": config.max_retries,
        "max_completion_tokens": config.max_completion_tokens,
        "reasoning_effort": config.reasoning_effort,
    }
    executor = ProxyPairedExecutor(
        OpenAICompatibleAgent(config.baseline_endpoint, **common),
        OpenAICompatibleAgent(config.paritok_endpoint, **common),
        gateway,
        experiment_id=config.experiment_id,
        config_version=config.config_version,
        config_sha256=config_sha256,
        pricing_version=config.pricing_version,
        require_proxy_telemetry=config.require_proxy_telemetry,
    )
    cases = load_benchmark_cases(args.manifest)
    if args.limit is not None and args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    if args.limit:
        cases = cases[: args.limit]
    events_path = Path(args.events)
    partial_path = events_path.with_suffix(events_path.suffix + ".partial")
    if partial_path.exists():
        partial_path.unlink()
    store = JsonlEventStore(partial_path)
    outcomes = PairedExperimentRunner(executor, store.append, seed=args.seed).run(cases)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.replace(events_path)
    manifest = {
        "schema_version": 1,
        "experiment_id": config.experiment_id,
        "evidence_label": config.evidence_label,
        "completed_at": date.today().isoformat(),
        "config": {
            "path": args.config,
            "sha256": config_sha256,
            "version": config.config_version,
        },
        "tasks": {
            "path": args.manifest,
            "sha256": _sha256(args.manifest),
            "count": len(cases),
        },
        "events": {
            "path": args.events,
            "sha256": _sha256(args.events),
            "count": len(outcomes),
        },
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "paritok_health": {
            "status": health.get("status"),
            "version": health.get("version", "unknown"),
        },
        "secrets_recorded": False,
    }
    manifest_path = Path(args.run_manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Executed {len(cases)} live paired cases ({len(outcomes)} arm runs)")
    print(f"Events: {args.events}")
    print(f"Run manifest: {args.run_manifest}")
    return 0


def run_workload_audit(args: argparse.Namespace) -> int:
    matrix, scenarios = load_workload_matrix(args.matrix)
    selected = select_stage(matrix, scenarios, args.stage)
    pricing = load_pricing(args.pricing, args.model)
    audit = audit_stage(selected, pricing)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_audit_markdown(audit, stage=args.stage, suite_id=matrix["suite_id"]),
        encoding="utf-8",
    )
    print(f"Audited {len(selected)} scenarios for {args.stage}")
    print(f"Estimated paired requests: {audit['paired_request_count']}")
    print(
        "Estimated input-only upper bound: "
        f"${audit['estimated_paired_input_cost_upper_bound_usd']:.4f}"
    )
    print(f"Audit: {args.output}")
    print(f"Report: {args.report}")
    return 0


def run_live_sessions(args: argparse.Namespace) -> int:
    config, config_sha256 = load_live_config(args.config)
    matrix, all_scenarios = load_workload_matrix(args.matrix)
    scenarios = select_stage(matrix, all_scenarios, args.stage)
    cache_safety = decide_cache_safety(
        scenarios,
        contract=config.compression_cache_contract,
        allow_unsafe_experiment=args.allow_unsafe_query_sensitive_cache_experiment,
    )
    if not cache_safety.allowed:
        print(
            "Refusing multi-turn execution: compression cache contract is unverified across "
            "task-intent changes. Declare disabled/query_aware in the live config, or use the "
            "explicit research-only override.",
            file=sys.stderr,
        )
        return 2
    pricing = load_pricing(args.pricing, config.model)
    if (
        pricing.version != config.pricing_version
        or pricing.input_per_million != config.input_cost_per_million
        or pricing.output_per_million != config.output_cost_per_million
    ):
        print("Live config pricing does not match the selected pricing registry", file=sys.stderr)
        return 2
    audit = audit_stage(scenarios, pricing)
    estimate = audit["estimated_paired_input_cost_upper_bound_usd"]
    if estimate > args.max_estimated_input_cost_usd:
        print(
            f"Estimated input cost ${estimate:.4f} exceeds the configured ceiling "
            f"${args.max_estimated_input_cost_usd:.4f}",
            file=sys.stderr,
        )
        return 2
    if not args.confirm_live_costs:
        print("Refusing live model calls without --confirm-live-costs", file=sys.stderr)
        return 2
    if not config.api_key:
        print(
            f"Missing API key environment variable: {config.api_key_environment}",
            file=sys.stderr,
        )
        return 2

    gateway = PariTokGateway(
        config.paritok_health_url,
        config.paritok_stats_url,
        timeout_seconds=min(config.timeout_seconds, 10.0),
    )
    health = gateway.health()
    gateway.stats()
    gateway.require_compression_model(
        config.compression_backend_models_url,
        config.compression_model,
    )
    common = {
        "model": config.model,
        "api_key": config.api_key,
        "input_cost_per_million": config.input_cost_per_million,
        "output_cost_per_million": config.output_cost_per_million,
        "timeout_seconds": config.timeout_seconds,
        "temperature": config.temperature,
        "max_retries": config.max_retries,
        "max_completion_tokens": config.max_completion_tokens,
        "reasoning_effort": config.reasoning_effort,
    }
    executor = MultiTurnProxyExecutor(
        OpenAICompatibleAgent(config.baseline_endpoint, **common),
        OpenAICompatibleAgent(config.paritok_endpoint, **common),
        gateway,
        experiment_id=config.experiment_id,
        config_version=config.config_version,
        config_sha256=config_sha256,
        pricing_version=config.pricing_version,
        require_proxy_telemetry=config.require_proxy_telemetry,
    )
    events_path = Path(args.events)
    partial_path = events_path.with_suffix(events_path.suffix + ".partial")
    if partial_path.exists():
        partial_path.unlink()
    outcomes = run_paired_sessions(
        scenarios,
        executor,
        JsonlEventStore(partial_path).append,
        seed=args.seed,
    )
    events_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.replace(events_path)
    events = load_events(events_path)
    manifest = {
        "schema_version": 1,
        "experiment_id": config.experiment_id,
        "evidence_label": config.evidence_label,
        "completed_at": date.today().isoformat(),
        "stage": args.stage,
        "suite_id": matrix["suite_id"],
        "scenario_count": len(scenarios),
        "paired_session_count": len(outcomes),
        "request_count": len(events),
        "cost_preflight": {
            "pricing_version": pricing.version,
            "estimated_input_cost_upper_bound_usd": estimate,
            "authorized_ceiling_usd": args.max_estimated_input_cost_usd,
            "output_and_paritok_compute_excluded": True,
        },
        "config": {"path": args.config, "sha256": config_sha256},
        "matrix": {"path": args.matrix, "sha256": _sha256(args.matrix)},
        "events": {"path": args.events, "sha256": _sha256(args.events)},
        "paritok_health": {
            "status": health.get("status"),
            "version": health.get("version", "unknown"),
        },
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "secrets_recorded": False,
        "cache_safety": cache_safety.to_dict(),
    }
    manifest_path = Path(args.run_manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Executed {len(scenarios)} scenarios / {len(events)} requests")
    print(f"Events: {args.events}")
    print(f"Run manifest: {args.run_manifest}")
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

    compare = subparsers.add_parser(
        "compressor-compare", help="compare deterministic compressor adapters offline"
    )
    compare.add_argument("--manifest", default="evals/tasks/mvp_tasks.jsonl")
    compare.add_argument("--output", default="artifacts/compressor-comparison.json")
    compare.add_argument("--seed", type=int, default=17)
    compare.set_defaults(func=run_compressor_compare)

    evidence = subparsers.add_parser(
        "evidence-audit", help="check sample, context, and independent quality-review gates"
    )
    evidence.add_argument("--events", default="artifacts/phase-3-session-events.jsonl")
    evidence.add_argument("--reviews")
    evidence.add_argument("--output", default="artifacts/phase-3-evidence-audit.json")
    evidence.set_defaults(func=run_evidence_audit)

    cache_audit = subparsers.add_parser(
        "cache-contract-audit",
        help="test query-sensitive PariTok cache behavior without provider or Ollama calls",
    )
    cache_audit.add_argument("--output", default="artifacts/query-sensitive-cache-audit.json")
    cache_audit.set_defaults(func=run_cache_contract_audit)

    regression = subparsers.add_parser(
        "provider-free-regression",
        help="run transformed-context cache, signal, and fallback regression without a provider",
    )
    regression.add_argument(
        "--engine", choices=("deterministic", "local_paritok_4b"), default="deterministic"
    )
    regression.add_argument("--config", default="configs/provider-free-regression-v1.json")
    regression.add_argument("--matrix", default="configs/phase-3-workloads.json")
    regression.add_argument("--output", default="artifacts/provider-free-regression.json")
    regression.add_argument("--report", default="docs/provider-free-regression.md")
    regression.set_defaults(func=run_provider_free_regression_command)

    latency = subparsers.add_parser(
        "latency-audit", help="estimate paired provider versus local/proxy latency"
    )
    latency.add_argument("--events", default="artifacts/phase-3-session-events.jsonl")
    latency.add_argument("--output", default="artifacts/phase-3-latency-audit.json")
    latency.set_defaults(func=run_latency_audit)

    local_latency = subparsers.add_parser(
        "local-latency-probe", help="measure cold/warm local PariTok compression without a provider"
    )
    local_latency.add_argument("--matrix", default="configs/phase-3-workloads.json")
    local_latency.add_argument("--scenario", default="read-heavy-32k-5t")
    local_latency.add_argument("--warm-scenario", default="debugging-32k-5t")
    local_latency.add_argument("--model", default="gpt-5.6-luna")
    local_latency.add_argument("--confirm-backend-restarted", action="store_true")
    local_latency.add_argument("--output", default="artifacts/phase-3-local-latency.json")
    local_latency.set_defaults(func=run_local_latency_probe)

    economics = subparsers.add_parser(
        "multi-turn-economics",
        help="build cumulative cost, latency, and explicit-value break-even curves",
    )
    economics.add_argument("--events", default="artifacts/phase-3-session-events.jsonl")
    economics.add_argument("--latency-value-usd-per-second", type=float)
    economics.add_argument("--output", default="artifacts/phase-3-multi-turn-economics.json")
    economics.set_defaults(func=run_multi_turn_economics)

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
    doctor.add_argument("--live-config")
    doctor.add_argument("--probe-live", action="store_true")
    doctor.set_defaults(func=run_doctor_command)

    live = subparsers.add_parser("live-run", help="run paid paired calls via direct and PariTok endpoints")
    live.add_argument("--config", default="configs/phase-3.example.json")
    live.add_argument("--manifest", default="evals/tasks/mvp_tasks.jsonl")
    live.add_argument("--events", default="artifacts/phase-3-live-events.jsonl")
    live.add_argument("--run-manifest", default="artifacts/phase-3-run-manifest.json")
    live.add_argument("--seed", type=int, default=17)
    live.add_argument("--limit", type=int)
    live.add_argument("--confirm-live-costs", action="store_true")
    live.set_defaults(func=run_live)

    workloads = subparsers.add_parser(
        "workload-audit", help="expand and cost a staged long-context workload matrix"
    )
    workloads.add_argument("--matrix", default="configs/phase-3-workloads.json")
    workloads.add_argument("--pricing", default="configs/openai-pricing-2026-08-12.json")
    workloads.add_argument("--model", default="gpt-5.6-luna")
    workloads.add_argument(
        "--stage", choices=("smoke", "core", "wave_a", "evidence", "extended"), default="smoke"
    )
    workloads.add_argument("--output", default="artifacts/phase-3-smoke-audit.json")
    workloads.add_argument("--report", default="docs/phase-3-workload-audit.md")
    workloads.set_defaults(func=run_workload_audit)

    sessions = subparsers.add_parser(
        "live-session-run", help="run staged multi-turn direct/PariTok paired sessions"
    )
    sessions.add_argument("--config", default="configs/phase-3-luna-smoke.json")
    sessions.add_argument("--matrix", default="configs/phase-3-workloads.json")
    sessions.add_argument("--pricing", default="configs/openai-pricing-2026-08-12.json")
    sessions.add_argument(
        "--stage", choices=("smoke", "core", "wave_a", "evidence", "extended"), default="smoke"
    )
    sessions.add_argument("--events", default="artifacts/phase-3-session-events.jsonl")
    sessions.add_argument("--run-manifest", default="artifacts/phase-3-session-manifest.json")
    sessions.add_argument("--seed", type=int, default=17)
    sessions.add_argument("--max-estimated-input-cost-usd", type=float, default=0.25)
    sessions.add_argument("--confirm-live-costs", action="store_true")
    sessions.add_argument(
        "--allow-unsafe-query-sensitive-cache-experiment",
        action="store_true",
        help="research only: bypass the unverified-cache block; never marks rollout eligible",
    )
    sessions.set_defaults(func=run_live_sessions)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

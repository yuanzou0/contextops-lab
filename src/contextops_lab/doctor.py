"""Preflight diagnostics for data, policy, and live integration readiness."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from .benchmark import load_benchmark_cases
from .events import load_events
from .models import ExperimentArm
from .live_config import load_live_config
from .paritok import PariTokGateway
from .strategy import CompressionMode


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: CheckStatus
    message: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def run_doctor(
    *,
    manifest: str | Path,
    events: str | Path,
    policy: str | Path,
    compressor_command: str | None = None,
    agent_endpoint: str | None = None,
    api_key_environment: str | None = None,
    live_config: str | Path | None = None,
    probe_live: bool = False,
) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    python_ok = sys.version_info >= (3, 10)
    checks.append(
        DoctorCheck(
            "python",
            CheckStatus.PASS if python_ok else CheckStatus.FAIL,
            f"Python {sys.version_info.major}.{sys.version_info.minor}",
        )
    )

    try:
        cases = load_benchmark_cases(manifest)
        checks.append(DoctorCheck("manifest", CheckStatus.PASS, f"{len(cases)} executable cases"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        checks.append(DoctorCheck("manifest", CheckStatus.FAIL, str(error)))

    try:
        rows = load_events(events)
        arms_by_task: dict[str, set[ExperimentArm]] = {}
        for event in rows:
            arms_by_task.setdefault(event.task_id, set()).add(event.arm)
        paired = sum(
            {ExperimentArm.BASELINE, ExperimentArm.COMPRESSED} <= arms
            for arms in arms_by_task.values()
        )
        status = CheckStatus.PASS if rows and paired == len(arms_by_task) else CheckStatus.FAIL
        checks.append(DoctorCheck("events", status, f"{len(rows)} events; {paired} paired tasks"))
        identities = [
            (event.experiment_id, event.task_id, event.session_id, event.turn_id, event.arm)
            for event in rows
        ]
        duplicates = len(identities) - len(set(identities))
        checks.append(
            DoctorCheck(
                "event_uniqueness",
                CheckStatus.FAIL if duplicates else CheckStatus.PASS,
                f"{duplicates} duplicate event identities" if duplicates else "event identities unique",
            )
        )
        missing_timestamps = sum(not event.recorded_at for event in rows)
        checks.append(
            DoctorCheck(
                "event_time",
                CheckStatus.WARN if missing_timestamps else CheckStatus.PASS,
                f"{missing_timestamps} events missing recorded_at" if missing_timestamps else "timestamps present",
            )
        )
        forbidden = {"prompt", "source_code", "credential", "raw_file"}
        serialized_keys = set().union(*(event.to_dict().keys() for event in rows)) if rows else set()
        exposed = sorted(forbidden & serialized_keys)
        checks.append(
            DoctorCheck(
                "privacy_schema",
                CheckStatus.FAIL if exposed else CheckStatus.PASS,
                "forbidden raw fields absent" if not exposed else f"forbidden fields: {exposed}",
            )
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        checks.append(DoctorCheck("events", CheckStatus.FAIL, str(error)))

    try:
        policy_payload = json.loads(Path(policy).read_text(encoding="utf-8"))
        invalid_modes = sorted(
            {
                rule.get("mode")
                for rule in policy_payload.get("rules", [])
                if rule.get("mode") not in {mode.value for mode in CompressionMode}
            }
        )
        production_mismatch = (
            policy_payload.get("production_ready")
            and policy_payload.get("evidence_label") != "production"
        )
        status = CheckStatus.FAIL if invalid_modes or production_mismatch else CheckStatus.PASS
        message = "policy schema and evidence gate valid"
        if invalid_modes:
            message = f"invalid modes: {invalid_modes}"
        elif production_mismatch:
            message = "non-production evidence cannot authorize rollout"
        checks.append(DoctorCheck("rollout_policy", status, message))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        checks.append(DoctorCheck("rollout_policy", CheckStatus.FAIL, str(error)))

    if compressor_command:
        resolved = shutil.which(compressor_command)
        checks.append(
            DoctorCheck(
                "compressor_command",
                CheckStatus.PASS if resolved else CheckStatus.FAIL,
                resolved or f"command not found: {compressor_command}",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "compressor_command",
                CheckStatus.WARN,
                "not configured; offline analysis remains available",
            )
        )

    if agent_endpoint:
        parsed = urlparse(agent_endpoint)
        valid = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        checks.append(
            DoctorCheck(
                "agent_endpoint",
                CheckStatus.PASS if valid else CheckStatus.FAIL,
                agent_endpoint if valid else "endpoint must be an HTTP(S) URL",
            )
        )
    else:
        checks.append(DoctorCheck("agent_endpoint", CheckStatus.WARN, "not configured"))

    if api_key_environment:
        present = bool(os.environ.get(api_key_environment))
        checks.append(
            DoctorCheck(
                "api_key",
                CheckStatus.PASS if present else CheckStatus.WARN,
                f"{api_key_environment} is set" if present else f"{api_key_environment} is not set",
            )
        )
    if live_config:
        try:
            config, config_sha256 = load_live_config(live_config)
            checks.append(
                DoctorCheck(
                    "live_config",
                    CheckStatus.PASS,
                    f"{config.config_version}; sha256={config_sha256[:12]}",
                )
            )
            key_present = bool(config.api_key)
            checks.append(
                DoctorCheck(
                    "live_api_key",
                    CheckStatus.PASS if key_present else CheckStatus.WARN,
                    f"{config.api_key_environment} is set"
                    if key_present
                    else f"{config.api_key_environment} is not set",
                )
            )
            pricing_set = bool(
                config.pricing_version != "replace-with-provider-price-date"
                and (config.input_cost_per_million or config.output_cost_per_million)
            )
            checks.append(
                DoctorCheck(
                    "live_pricing",
                    CheckStatus.PASS if pricing_set else CheckStatus.WARN,
                    config.pricing_version
                    if pricing_set
                    else "replace example pricing before interpreting cost results",
                )
            )
            if probe_live:
                gateway = PariTokGateway(
                    config.paritok_health_url,
                    config.paritok_stats_url,
                    timeout_seconds=min(config.timeout_seconds, 10.0),
                )
                health = gateway.health()
                stats = gateway.stats()
                gateway.require_compression_model(
                    config.compression_backend_models_url,
                    config.compression_model,
                )
                checks.append(
                    DoctorCheck(
                        "paritok_gateway",
                        CheckStatus.PASS,
                        f"status={health.get('status')}; compression_model="
                        f"{config.compression_model}; total_requests={stats.total_requests}",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        "paritok_gateway",
                        CheckStatus.WARN,
                        "not probed; pass --probe-live to verify health and telemetry",
                    )
                )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            checks.append(DoctorCheck("live_config", CheckStatus.FAIL, str(error)))
        except RuntimeError as error:
            checks.append(DoctorCheck("paritok_gateway", CheckStatus.FAIL, str(error)))
    return checks

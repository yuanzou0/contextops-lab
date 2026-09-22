"""Provider-free P0.3-D drill against an isolated real Redis process."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cache_safety import build_paritok_storage
from .context_store import DurableRedisShadowStorage, RetrievalStatus

LABEL = "local_real_redis_restart_drill"
PREFIX = "contextops-drill"
TENANT, SESSION = "synthetic-tenant-alpha", "synthetic-session-alpha"
OTHER_TENANT, OTHER_SESSION = "synthetic-tenant-beta", "synthetic-session-beta"
SYNTHETIC_PATH = "synthetic/project/service.py"
ORIGINALS = {
    "one": "SYNTHETIC_CONTEXT::restart::alpha\nCRITICAL_SIGNAL: alpha\n",
    "two": "SYNTHETIC_CONTEXT::restart::beta\nCRITICAL_SIGNAL: beta\n",
    "wrong": "SYNTHETIC_CONTEXT::wrong-key\n",
    "tamper": "SYNTHETIC_CONTEXT::tamper\n",
    "swap_a": "SYNTHETIC_CONTEXT::swap-a\n",
    "swap_b": "SYNTHETIC_CONTEXT::swap-b\n",
    "ttl": "SYNTHETIC_CONTEXT::ttl\n",
}
PROVIDER_ENV = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "AZURE_OPENAI_API_KEY",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def store(
    tenant: str = TENANT,
    session: str = SESSION,
    ttl: int = 120,
    tombstone: int = 30,
    key: str | None = None,
) -> DurableRedisShadowStorage:
    return DurableRedisShadowStorage.from_url(
        os.environ["CONTEXTOPS_DRILL_REDIS_URL"],
        encryption_key=key or os.environ["CONTEXTOPS_DRILL_STORAGE_KEY"],
        tenant_id=tenant,
        session_id=session,
        ttl_seconds=ttl,
        tombstone_seconds=tombstone,
        key_prefix=PREFIX,
    )


def worker_write(_: argparse.Namespace) -> dict[str, Any]:
    base = store()
    wrapped = build_paritok_storage("query_aware", backend="redis", base_storage=base)
    one = wrapped.store(ORIGINALS["one"])
    wrapped.set_shadow_for_path(SYNTHETIC_PATH, one)
    two = wrapped.store(ORIGINALS["two"])
    wrapped.set_shadow_for_path(SYNTHETIC_PATH, two)
    wrapped.pin_source(SYNTHETIC_PATH)
    wrapped.pin_shadow(one)
    for query, summary in (("intent-one", "summary-one"), ("intent-two", "summary-two")):
        wrapped.set_active_query(query)
        wrapped.cache_compressed(one, summary)
    refs = {name: base.store(ORIGINALS[name]) for name in ("wrong", "tamper", "swap_a", "swap_b")}
    result = base.retrieve_with_status(one)
    return {"one": one, "two": two, "refs": refs, "version": result.content_version,
            "namespace_hash": digest(base.namespace)}


def load_state(args: argparse.Namespace) -> dict[str, Any]:
    return json.loads(Path(args.state).read_text())


def worker_verify(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args)
    base = store()
    wrapped = build_paritok_storage("query_aware", backend="redis", base_storage=base)
    one, two = base.retrieve_with_status(state["one"]), base.retrieve_with_status(state["two"])
    caches = []
    for query in ("intent-one", "intent-two", "unseen-intent"):
        wrapped.set_active_query(query)
        caches.append(wrapped.get_cached_compressed(state["one"]))
    checks = {
        "first_exact": one.status is RetrievalStatus.FOUND and one.content == ORIGINALS["one"],
        "second_exact": two.status is RetrievalStatus.FOUND and two.content == ORIGINALS["two"],
        "version_stable": one.content_version == state["version"],
        "path_history": wrapped.get_shadows_for_path(SYNTHETIC_PATH) == [state["two"], state["one"]],
        "reverse_path": wrapped.get_path_for_shadow(state["one"]) == SYNTHETIC_PATH,
        "source_pin": wrapped.is_source_pinned(SYNTHETIC_PATH),
        "shadow_pin": wrapped.is_shadow_pinned(state["one"]),
        "query_cache": caches == ["summary-one", "summary-two", None],
    }
    return {"passed": all(checks.values()), "checks": checks}


def worker_isolation(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args)
    statuses = [
        store(tenant=OTHER_TENANT).retrieve_with_status(state["one"]).status.value,
        store(session=OTHER_SESSION).retrieve_with_status(state["one"]).status.value,
    ]
    return {"passed": statuses == ["not_found", "not_found"], "statuses": statuses}


def worker_ttl_write(args: argparse.Namespace) -> dict[str, Any]:
    base = store(session="synthetic-expiry-session", ttl=args.expiry_ttl, tombstone=args.tombstone)
    ref = base.store(ORIGINALS["ttl"])
    result = base.retrieve_with_status(ref)
    return {"reference": ref, "version": result.content_version, "expires_at": result.expires_at}


def worker_ttl_status(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args)
    base = store(session="synthetic-expiry-session", ttl=args.expiry_ttl, tombstone=args.tombstone)
    result = base.retrieve_with_status(state["reference"])
    return {
        "status": result.status.value,
        "content_is_null": result.content is None,
        "version_preserved": result.content_version == state["version"],
        "expiry_preserved": result.expires_at == state["expires_at"],
        "body_exists": bool(base._client.exists(base._key("shadow", state["reference"]))),
        "tombstone_exists": bool(base._client.exists(base._key("shadow_status", state["reference"]))),
        "has": base.has(state["reference"]),
    }


def worker_negative(args: argparse.Namespace) -> dict[str, Any]:
    state, base = load_state(args), store()
    refs = state["refs"]
    wrong_key = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode()
    wrong = store(key=wrong_key).retrieve_with_status(refs["wrong"]).status.value
    tamper_key = base._key("shadow", refs["tamper"])
    envelope = json.loads(base._client.get(tamper_key))
    value = envelope["ciphertext"]
    envelope["ciphertext"] = value[:-1] + ("A" if value[-1] != "A" else "B")
    base._client.set(tamper_key, json.dumps(envelope), ex=120)
    tampered = base.retrieve_with_status(refs["tamper"]).status.value
    keys = [base._key("shadow", refs[name]) for name in ("swap_a", "swap_b")]
    envelopes = [json.loads(base._client.get(key)) for key in keys]
    envelopes[0]["ciphertext"], envelopes[1]["ciphertext"] = (
        envelopes[1]["ciphertext"], envelopes[0]["ciphertext"])
    for key, item in zip(keys, envelopes, strict=True):
        base._client.set(key, json.dumps(item), ex=120)
    swapped = [base.retrieve_with_status(refs[name]).status.value for name in ("swap_a", "swap_b")]
    passed = wrong == tampered == "corrupt" and swapped == ["corrupt", "corrupt"]
    return {"passed": passed, "wrong_key": wrong, "tamper": tampered, "swap": swapped}


def worker_privacy(_: argparse.Namespace) -> dict[str, Any]:
    base = store()
    keys = sorted(str(key) for key in base._client.scan_iter(match=f"{PREFIX}:*"))
    persisted = "\n".join(keys + [str(base._client.get(key) or "") for key in keys])
    forbidden = [TENANT, SESSION, OTHER_TENANT, OTHER_SESSION, SYNTHETIC_PATH,
                 os.environ["CONTEXTOPS_DRILL_STORAGE_KEY"], *ORIGINALS.values()]
    findings = sum(value in persisted for value in forbidden)
    return {"passed": findings == 0, "key_count": len(keys), "finding_count": findings,
            "encryption": base.health()["encryption"]}


def worker_outage(args: argparse.Namespace) -> dict[str, Any]:
    state, base = load_state(args), store()
    Path(args.ready).write_text("ready\n")
    deadline = time.monotonic() + 20
    while not Path(args.proceed).exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    result = base.retrieve_with_status(state["one"])
    health = base.health()["status"]
    return {"passed": result.status.value == health == "unhealthy", "status": result.status.value,
            "health": health}


def worker_startup(_: argparse.Namespace) -> dict[str, Any]:
    try:
        from .safe_proxy import create_safe_proxy_app
        create_safe_proxy_app(
            openai_base_url="http://127.0.0.1:9", anthropic_base_url="http://127.0.0.1:9",
            cache_contract="query_aware", storage_backend="redis",
            redis_url=os.environ["CONTEXTOPS_DRILL_REDIS_URL"],
            storage_encryption_key=os.environ["CONTEXTOPS_DRILL_STORAGE_KEY"],
            tenant_id=TENANT, session_id=SESSION)
    except Exception as error:
        chain, current = [], error
        while current:
            chain.append(type(current).__name__)
            current = current.__cause__
        return {"passed": "ConnectionError" in chain, "startup": "rejected",
                "memory_fallback": False, "exception_chain": chain}
    return {"passed": False, "startup": "unexpected_success", "memory_fallback": None}


WORKERS = {"write": worker_write, "verify": worker_verify, "isolation": worker_isolation,
           "ttl-write": worker_ttl_write, "ttl-status": worker_ttl_status,
           "negative": worker_negative, "privacy": worker_privacy,
           "outage": worker_outage, "startup": worker_startup}


def worker_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=WORKERS)
    parser.add_argument("--state")
    parser.add_argument("--ready")
    parser.add_argument("--proceed")
    parser.add_argument("--expiry-ttl", type=int, default=2)
    parser.add_argument("--tombstone", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        payload = WORKERS[args.action](args)
    except Exception as error:
        payload = {"passed": False, "worker_error": type(error).__name__}
        print(json.dumps(payload, sort_keys=True))
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


class Coordinator:
    def __init__(self, redis_server: str, output_dir: Path, report_path: Path, port: int,
                 expiry_ttl: int, tombstone: int) -> None:
        self.redis_server = str(Path(redis_server).resolve())
        self.output_dir, self.report_path = output_dir.resolve(), report_path.resolve()
        self.runtime = Path(tempfile.mkdtemp(prefix="contextops-redis-drill-"))
        self.data = self.runtime / "redis-data"
        self.data.mkdir()
        self.state, self.ttl_state = self.runtime / "state.json", self.runtime / "ttl.json"
        self.port = port or self.free_port()
        self.url = f"redis://127.0.0.1:{self.port}/15"
        self.key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        self.expiry_ttl, self.tombstone = expiry_ttl, tombstone
        self.process: subprocess.Popen[str] | None = None
        self.events: list[dict[str, Any]] = []
        self.gates: dict[str, bool] = {}
        self.started = now()
        self.commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, text=True,
                                     capture_output=True).stdout.strip()
        self.redis_version = subprocess.run([self.redis_server, "--version"], check=True, text=True,
                                            capture_output=True).stdout.strip()
        self.config = self.runtime / "redis.conf"

    @staticmethod
    def free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        for name in PROVIDER_ENV:
            env.pop(name, None)
        env.update(CONTEXTOPS_DRILL_REDIS_URL=self.url, CONTEXTOPS_DRILL_STORAGE_KEY=self.key)
        root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        return env

    def client(self) -> Any:
        import redis
        return redis.Redis.from_url(self.url, decode_responses=True)

    def write_config(self) -> None:
        text = (f"bind 127.0.0.1\nprotected-mode yes\nport {self.port}\ndir {self.data}\n"
                "appendonly yes\nappendfsync always\nsave \"\"\ndatabases 16\n"
                "daemonize no\nloglevel notice\n")
        self.config.write_text(text)
        safe = text.replace(str(self.port), "<dedicated-port>").replace(str(self.data),
                                                                         "<ephemeral-volume>")
        (self.output_dir / "redis-config.txt").write_text(safe)

    def start(self) -> None:
        self.process = subprocess.Popen([self.redis_server, str(self.config)], stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, text=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("redis-server exited during startup")
            try:
                if self.client().ping():
                    return
            except Exception:
                time.sleep(0.1)
        raise TimeoutError("redis startup timeout")

    def stop(self) -> None:
        if not self.process:
            return
        try:
            self.client().shutdown(nosave=False)
        except Exception:
            pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.process = None

    def worker(self, action: str, *extra: str) -> dict[str, Any]:
        result = subprocess.run([sys.executable, "-m", "contextops_lab.redis_drill", "_worker",
                                 action, *extra], env=self.env(), text=True, capture_output=True)
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            payload = {"passed": False, "worker_error": "invalid_output"}
        payload["worker_exit_code"] = result.returncode
        return payload

    def event(self, phase: str, gate: str, passed: bool, details: dict[str, Any]) -> None:
        self.gates[gate] = bool(passed)
        self.events.append({"schema_version": 1, "recorded_at": now(), "phase": phase,
                            "gate": gate, "status": "PASS" if passed else "FAIL", "details": details,
                            "provider_calls": 0, "provider_cost_usd": 0.0,
                            "contains_raw_context": False})

    def poll_ttl(self, expected: str, timeout: float) -> dict[str, Any]:
        extra = ("--state", str(self.ttl_state), "--expiry-ttl", str(self.expiry_ttl),
                 "--tombstone", str(self.tombstone))
        deadline, last = time.monotonic() + timeout, {}
        while time.monotonic() < deadline:
            last = self.worker("ttl-status", *extra)
            if last.get("status") == expected:
                return last
            time.sleep(0.2)
        return last

    def run(self) -> int:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.write_config()
        self.start()
        try:
            client = self.client()
            config = {**client.config_get("appendonly"), **client.config_get("appendfsync")}
            details = {"namespace_clean": client.dbsize() == 0,
                       "appendonly": config.get("appendonly") == "yes",
                       "appendfsync": config.get("appendfsync") == "always",
                       "key_bytes": len(base64.urlsafe_b64decode(self.key)) == 32,
                       "provider_credentials_forwarded": False,
                       "dedicated_loopback_instance": True}
            preflight = all(value for key, value in details.items()
                            if key != "provider_credentials_forwarded")
            self.event("preflight", "preflight", preflight, details)
            if not preflight:
                return self.write_evidence()

            state = self.worker("write")
            self.state.write_text(json.dumps(state))
            self.event("write", "synthetic_write", state.get("worker_exit_code") == 0,
                       {"reference_count": 6, "namespace_sha256": state.get("namespace_hash")})
            app = self.worker("verify", "--state", str(self.state))
            self.event("application_restart", "application_restart_exact_recovery",
                       bool(app.get("passed")), app)
            self.stop()
            self.start()
            aof = self.worker("verify", "--state", str(self.state))
            aof["persistence_mode"] = "AOF appendfsync always"
            self.event("redis_restart", "redis_aof_restart_exact_recovery", bool(aof.get("passed")), aof)
            isolation = self.worker("isolation", "--state", str(self.state))
            self.event("isolation", "tenant_session_isolation", bool(isolation.get("passed")), isolation)

            ttl = self.worker("ttl-write", "--expiry-ttl", str(self.expiry_ttl),
                              "--tombstone", str(self.tombstone))
            self.ttl_state.write_text(json.dumps(ttl))
            found = self.poll_ttl("found", 1)
            expired = self.poll_ttl("expired", self.expiry_ttl + 4)
            missing = self.poll_ttl("not_found", self.tombstone + 4)
            ttl_ok = (found.get("status") == "found" and expired.get("status") == "expired"
                      and expired.get("content_is_null") and expired.get("version_preserved")
                      and expired.get("expiry_preserved") and not expired.get("body_exists")
                      and expired.get("tombstone_exists") and not expired.get("has")
                      and missing.get("status") == "not_found" and not missing.get("body_exists")
                      and not missing.get("tombstone_exists"))
            self.event("real_ttl", "found_expired_not_found", ttl_ok,
                       {"clock": "wall", "sequence": [found, expired, missing]})
            negative = self.worker("negative", "--state", str(self.state))
            self.event("negative_controls", "wrong_key_tamper_swap_corrupt",
                       bool(negative.get("passed")), negative)
            privacy = self.worker("privacy")
            self.event("privacy_scan", "ciphertext_at_rest_and_privacy",
                       bool(privacy.get("passed")), privacy)

            ready, proceed = self.runtime / "ready", self.runtime / "proceed"
            proc = subprocess.Popen([sys.executable, "-m", "contextops_lab.redis_drill", "_worker",
                                     "outage", "--state", str(self.state), "--ready", str(ready),
                                     "--proceed", str(proceed)], env=self.env(), text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            ready_ok = ready.exists()
            self.stop()
            proceed.write_text("continue\n")
            stdout, _ = proc.communicate(timeout=15)
            try:
                outage = json.loads(stdout.strip().splitlines()[-1])
            except (IndexError, json.JSONDecodeError):
                outage = {"passed": False, "worker_error": "invalid_output"}
            outage["worker_exit_code"] = proc.returncode
            self.event("backend_outage", "read_outage_unhealthy",
                       ready_ok and bool(outage.get("passed")), outage)
            startup = self.worker("startup")
            self.event("backend_outage", "safe_proxy_startup_fail_closed",
                       bool(startup.get("passed")), startup)
            self.start()
            recovery = self.worker("verify", "--state", str(self.state))
            self.event("backend_recovery", "fresh_process_recovers_after_outage",
                       bool(recovery.get("passed")), recovery)

            self.stop()
            shutil.rmtree(self.data)
            self.data.mkdir()
            self.start()
            clean = self.client().dbsize() == 0
            repeat_state = self.worker("write")
            self.state.write_text(json.dumps(repeat_state))
            repeat_app = self.worker("verify", "--state", str(self.state))
            self.stop()
            self.start()
            repeat_aof, repeat_privacy = (self.worker("verify", "--state", str(self.state)),
                                          self.worker("privacy"))
            repeat_ok = (clean and repeat_state.get("worker_exit_code") == 0
                         and repeat_app.get("passed") and repeat_aof.get("passed")
                         and repeat_privacy.get("passed"))
            self.event("repeatability", "clean_volume_repeat_run", bool(repeat_ok),
                       {"volume_cleared": True, "namespace_clean": clean,
                        "application_restart": bool(repeat_app.get("passed")),
                        "aof_restart": bool(repeat_aof.get("passed")),
                        "privacy_scan": bool(repeat_privacy.get("passed"))})
            self.event("cost_boundary", "zero_provider_calls_and_cost", True,
                       {"provider_calls": 0, "provider_cost_usd": 0.0, "data": "synthetic_only"})
        finally:
            self.stop()
        return self.write_evidence()

    def label(self, path: Path) -> str:
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return path.name

    def write_evidence(self) -> int:
        passed = bool(self.gates) and all(self.gates.values())
        environment = {"schema_version": 1, "evidence_label": LABEL, "git_commit": self.commit,
                       "python": platform.python_version(), "platform": platform.platform(),
                       "redis_server": self.redis_version, "redis_client": version("redis"),
                       "cryptography": version("cryptography"), "paritok": version("paritok"),
                       "provider_credentials_forwarded": False}
        results = {"schema_version": 1, "evidence_label": LABEL,
                   "status": "PASS" if passed else "FAIL", "started_at": self.started,
                   "completed_at": now(),
                   "gates": [{"name": name, "status": "PASS" if value else "FAIL"}
                             for name, value in self.gates.items()],
                   "provider_calls": 0, "provider_cost_usd": 0.0,
                   "real_user_data": False, "production_claim": False}
        manifest = {"schema_version": 1, "evidence_label": LABEL, "status": results["status"],
                    "git_commit": self.commit,
                    "artifacts": ["environment.json", "events.jsonl", "manifest.json",
                                  "redis-config.txt", "results.json", "sha256sums.txt"],
                    "report": self.label(self.report_path),
                    "reproduction": {"command": "contextops-lab durable-store-drill --redis-server <path>",
                                     "requires": ["redis-server", "contextops-lab[live]"]}}
        for name, payload in (("environment.json", environment), ("results.json", results),
                              ("manifest.json", manifest)):
            (self.output_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        (self.output_dir / "events.jsonl").write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in self.events))
        rows = "\n".join(f"| `{name}` | **{'PASS' if value else 'FAIL'}** |"
                         for name, value in self.gates.items())
        self.report_path.write_text(
            f"# P0.3-D real Redis drill results\n\n**Evidence label:** `{LABEL}`  \n"
            f"**Overall status:** **{results['status']}**  \n**Git commit:** `{self.commit}`\n\n"
            "This provider-free local drill used a dedicated loopback Redis process, synthetic data, "
            "AES-256-GCM, and AOF with `appendfsync always`. It does not establish production-cluster, "
            "failover, backup, cross-region, key-rotation, or zero-data-loss claims.\n\n"
            f"## Gates\n\n| Gate | Status |\n|---|---|\n{rows}\n\n"
            "## Cost and privacy boundary\n\n- Provider calls: **0**\n- Provider cost: **$0.00**\n"
            "- Real user data: **none**\n- Raw context, scope, path, or encryption key in evidence: **none**\n\n"
            f"## Runtime\n\n- Redis: `{environment['redis_server']}`\n- Python: `{environment['python']}`\n"
            f"- redis-py: `{environment['redis_client']}`\n- cryptography: `{environment['cryptography']}`\n"
            f"- PariTok: `{environment['paritok']}`\n")
        paths = [self.output_dir / name for name in ("environment.json", "events.jsonl",
                 "manifest.json", "redis-config.txt", "results.json")] + [self.report_path]
        (self.output_dir / "sha256sums.txt").write_text(
            "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {self.label(path)}\n"
                    for path in paths))
        return 0 if passed else 1

    def cleanup(self) -> None:
        self.stop()
        shutil.rmtree(self.runtime, ignore_errors=True)


def run_drill(*, redis_server: str, output_dir: Path, report_path: Path, port: int = 0,
              expiry_ttl: int = 2, tombstone: int = 4) -> int:
    coordinator: Coordinator | None = None
    try:
        coordinator = Coordinator(redis_server, output_dir, report_path, port, expiry_ttl, tombstone)
        return coordinator.run()
    except Exception as error:
        print(f"Redis drill failed closed: {type(error).__name__}: {error}", file=sys.stderr)
        if coordinator:
            coordinator.output_dir.mkdir(parents=True, exist_ok=True)
            coordinator.report_path.parent.mkdir(parents=True, exist_ok=True)
            if not (coordinator.output_dir / "redis-config.txt").exists():
                (coordinator.output_dir / "redis-config.txt").write_text("preflight failed closed\n")
            coordinator.event("orchestration", "unhandled_failure", False,
                              {"error_type": type(error).__name__})
            coordinator.write_evidence()
        return 1
    finally:
        if coordinator:
            coordinator.cleanup()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        raise SystemExit(worker_main(sys.argv[2:]))
    raise SystemExit("Use `contextops-lab durable-store-drill`.")

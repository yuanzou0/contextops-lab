"""Versioned compatibility contract for the external PariTok dependency."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .cache_safety import audit_installed_paritok_cache


EXPECTED_CACHE_CHECKS = frozenset(
    {"content_only_query_reuse_observed", "isolation_interventions_passed"}
)


def load_compatibility_matrix(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported PariTok compatibility-matrix schema")
    versions = payload.get("tested_versions")
    if not isinstance(versions, list) or not versions:
        raise ValueError("Compatibility matrix must declare tested_versions")
    if any(not isinstance(row, dict) for row in versions):
        raise ValueError("Compatibility-matrix entries must be objects")
    declared = [str(row.get("version", "")) for row in versions]
    if any(not item for item in declared) or len(declared) != len(set(declared)):
        raise ValueError("Compatibility-matrix versions must be non-empty and unique")
    if payload.get("default_version") not in declared:
        raise ValueError("default_version must be present in tested_versions")
    if not isinstance(payload.get("latest_checked_at"), str) or not payload["latest_checked_at"]:
        raise ValueError("Compatibility matrix must declare latest_checked_at")
    if not isinstance(payload.get("source"), str) or not payload["source"]:
        raise ValueError("Compatibility matrix must declare source")
    for row in versions:
        if not isinstance(row.get("role"), str) or not row["role"]:
            raise ValueError(f"Compatibility entry {row['version']} must declare role")
        expected = row.get("expected_cache_audit")
        if not isinstance(expected, dict) or set(expected) != EXPECTED_CACHE_CHECKS:
            raise ValueError(
                f"Compatibility entry {row['version']} must declare all expected cache checks"
            )
        if any(not isinstance(value, bool) for value in expected.values()):
            raise ValueError(f"Compatibility entry {row['version']} cache checks must be boolean")
    return payload


def audit_installed_paritok_compatibility(path: str | Path) -> dict[str, Any]:
    """Run the cache contract against the installed, explicitly supported version."""
    matrix_path = Path(path)
    matrix = load_compatibility_matrix(matrix_path)
    try:
        installed_version = version("paritok")
    except PackageNotFoundError as error:
        raise RuntimeError("Install the live extra before running compatibility-audit") from error

    entry = next(
        (
            row
            for row in matrix["tested_versions"]
            if str(row["version"]) == installed_version
        ),
        None,
    )
    base = {
        "schema_version": 1,
        "matrix_schema_version": matrix["schema_version"],
        "matrix_latest_checked_at": matrix["latest_checked_at"],
        "matrix_source": matrix["source"],
        "matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        "installed_version": installed_version,
        "default_version": matrix["default_version"],
        "supported": entry is not None,
        "role": entry.get("role") if entry else None,
    }
    if entry is None:
        return {**base, "checks": {}, "cache_audit": None, "passed": False}

    cache_audit = audit_installed_paritok_cache()
    expected = entry["expected_cache_audit"]
    checks = {
        key: cache_audit.get(key) == value
        for key, value in sorted(expected.items())
    }
    return {
        **base,
        "checks": checks,
        "cache_audit": cache_audit,
        "passed": bool(checks) and all(checks.values()),
    }


def write_compatibility_audit(payload: dict[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

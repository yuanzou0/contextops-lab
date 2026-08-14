"""Auditable latency-aware compression eligibility rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    eligible: bool
    mode: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def decide_eligibility(
    *,
    context_tokens: int,
    session_turns: int,
    risk_level: str,
    synchronous: bool = True,
    reusable_cache: bool = False,
    query_stable: bool = True,
) -> EligibilityDecision:
    """Choose a conservative mode before paying local-compression latency.

    The first live smoke showed that an 8K one-turn synchronous request saved cost but added
    roughly 40 seconds. Until longer cohorts are measured, those requests remain ineligible.
    """
    reasons: list[str] = []
    if context_tokens < 32_000:
        reasons.append("context_below_32k")
    if session_turns < 2 and not reusable_cache:
        reasons.append("latency_not_amortized")
    if synchronous and context_tokens < 128_000 and not reusable_cache:
        reasons.append("synchronous_latency_risk")
    if reusable_cache and not query_stable:
        reasons.append("query_sensitive_cache_risk")
    if reasons:
        return EligibilityDecision(False, "off", tuple(reasons))
    if risk_level == "high":
        return EligibilityDecision(True, "conservative", ("risk_sensitive_context",))
    return EligibilityDecision(True, "balanced", ("long_context_amortizable",))

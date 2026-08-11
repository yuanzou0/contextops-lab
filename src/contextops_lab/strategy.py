"""Runtime compression strategies exposed as product modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CompressionMode(str, Enum):
    OFF = "off"
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"


@dataclass(frozen=True, slots=True)
class StrategySettings:
    mode: CompressionMode
    enabled: bool
    maximum_token_ratio: float
    preserve_edit_context: bool


def settings_for(mode: CompressionMode, task_type: str) -> StrategySettings:
    if mode is CompressionMode.OFF:
        return StrategySettings(mode, False, 1.0, True)
    if mode is CompressionMode.CONSERVATIVE:
        return StrategySettings(
            mode,
            enabled=task_type != "edit_critical",
            maximum_token_ratio=0.85,
            preserve_edit_context=True,
        )
    return StrategySettings(mode, True, 1.05, task_type == "edit_critical")

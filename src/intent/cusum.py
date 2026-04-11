"""L2.5 — CUSUM anomaly detection for intent-commit patterns.

Detects agents whose behavior drifts from their declared intents over time.
Uses Cumulative Sum (CUSUM) control charts to flag anomalous patterns:
- Scope creep (consistently exceeding declared scope)
- Timing anomalies (actions far outside declared timeouts)
- Value drift (financial actions trending above declared limits)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CUSUMState:
    """Running CUSUM state for one agent's intent-commit behavior."""

    agent_id: str
    # Upper and lower cumulative sums
    s_high: float = 0.0
    s_low: float = 0.0
    # Number of observations
    n: int = 0
    # Running mean of deviation scores
    mean_deviation: float = 0.0
    # Alarm history
    alarms: list[dict] = field(default_factory=list)
    last_updated: Optional[datetime] = None

    # Tuning parameters (defaults from Montgomery 2012, adapted for agent context)
    k: float = 0.5  # Allowance (slack) — half the shift we want to detect
    h: float = 5.0  # Decision interval — triggers alarm when S exceeds this


def compute_deviation(commitment: dict, outcome: dict) -> float:
    """Compute a normalized deviation score between declared intent and actual outcome.

    Returns a value where 0 = perfect compliance, positive = exceeded scope.

    Factors:
    - scope_tools_used vs scope_tools_declared
    - actual_actions vs max_actions
    - actual_duration vs timeout_seconds
    - actual_value vs max_value_usd
    """
    score = 0.0
    weight_sum = 0.0

    # Tool scope deviation
    declared_tools = set(commitment.get("scope", {}).get("tools", []))
    used_tools = set(outcome.get("tools_used", []))
    if declared_tools:
        extra = used_tools - declared_tools
        tool_dev = len(extra) / max(len(declared_tools), 1)
        score += tool_dev * 2.0  # weight=2
        weight_sum += 2.0

    # Action count deviation
    max_actions = commitment.get("scope", {}).get("max_actions")
    actual_actions = outcome.get("action_count")
    if max_actions and actual_actions is not None:
        action_dev = max(0, (actual_actions - max_actions) / max_actions)
        score += action_dev * 1.5
        weight_sum += 1.5

    # Duration deviation
    timeout = commitment.get("scope", {}).get("timeout_seconds")
    actual_duration = outcome.get("duration_seconds")
    if timeout and actual_duration is not None:
        dur_dev = max(0, (actual_duration - timeout) / timeout)
        score += dur_dev * 1.0
        weight_sum += 1.0

    # Value deviation (highest weight — financial)
    max_val = commitment.get("scope", {}).get("max_value_usd")
    actual_val = outcome.get("value_usd")
    if max_val and actual_val is not None:
        val_dev = max(0, (actual_val - max_val) / max_val)
        score += val_dev * 3.0
        weight_sum += 3.0

    if weight_sum == 0:
        return 0.0
    return score / weight_sum


def update_cusum(state: CUSUMState, deviation: float) -> list[str]:
    """Update CUSUM state with a new deviation observation.

    Returns list of alarm messages (empty if no alarms).
    """
    state.n += 1
    state.last_updated = datetime.now(timezone.utc)

    # Update running mean
    state.mean_deviation += (deviation - state.mean_deviation) / state.n

    # CUSUM update (two-sided)
    state.s_high = max(0, state.s_high + deviation - state.k)
    state.s_low = max(0, state.s_low - deviation - state.k)  # Detects negative shift (under-commitment)

    alarms = []

    if state.s_high > state.h:
        alarm = {
            "type": "scope_creep",
            "s_high": state.s_high,
            "threshold": state.h,
            "n": state.n,
            "timestamp": state.last_updated.isoformat(),
            "message": f"Agent {state.agent_id}: CUSUM upper alarm (S+={state.s_high:.2f} > h={state.h}). "
                       f"Persistent scope exceedance detected over {state.n} observations.",
        }
        state.alarms.append(alarm)
        alarms.append(alarm["message"])
        # Reset after alarm (Western Electric rules variant)
        state.s_high = 0.0

    return alarms


@dataclass
class L25Assessment:
    """Result of an L2.5 anomaly assessment."""

    agent_id: str
    level: str = "L2.5"
    deviation_score: float = 0.0
    cusum_s_high: float = 0.0
    cusum_s_low: float = 0.0
    n_observations: int = 0
    alarms: list[str] = field(default_factory=list)
    passed: bool = True  # False if any alarms triggered
    mean_deviation: float = 0.0


def assess_l25(
    state: CUSUMState,
    commitment: dict,
    outcome: dict,
) -> L25Assessment:
    """Run L2.5 anomaly detection on a single commit-reveal cycle.

    Updates CUSUMState in place and returns assessment.
    """
    deviation = compute_deviation(commitment, outcome)
    alarms = update_cusum(state, deviation)

    return L25Assessment(
        agent_id=state.agent_id,
        deviation_score=deviation,
        cusum_s_high=state.s_high,
        cusum_s_low=state.s_low,
        n_observations=state.n,
        alarms=alarms,
        passed=len(alarms) == 0,
        mean_deviation=state.mean_deviation,
    )

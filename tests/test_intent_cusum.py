"""Tests for L2.5 CUSUM anomaly detection."""

import pytest
from src.intent.cusum import (
    CUSUMState,
    compute_deviation,
    update_cusum,
    assess_l25,
    L25Assessment,
)


class TestComputeDeviation:
    def test_perfect_compliance(self):
        commitment = {"scope": {"tools": ["git"], "max_actions": 10, "timeout_seconds": 3600}}
        outcome = {"tools_used": ["git"], "action_count": 5, "duration_seconds": 1800}
        assert compute_deviation(commitment, outcome) == 0.0

    def test_tool_scope_violation(self):
        commitment = {"scope": {"tools": ["git"]}}
        outcome = {"tools_used": ["git", "shell", "network"]}
        dev = compute_deviation(commitment, outcome)
        assert dev > 0  # 2 extra tools out of 1 declared

    def test_action_count_exceeded(self):
        commitment = {"scope": {"max_actions": 10}}
        outcome = {"action_count": 15}
        dev = compute_deviation(commitment, outcome)
        assert dev == pytest.approx(0.5)  # (15-10)/10 = 0.5

    def test_value_exceeded(self):
        commitment = {"scope": {"max_value_usd": 100}}
        outcome = {"value_usd": 200}
        dev = compute_deviation(commitment, outcome)
        assert dev > 0

    def test_under_limits_no_deviation(self):
        commitment = {"scope": {"max_actions": 10, "timeout_seconds": 3600, "max_value_usd": 1000}}
        outcome = {"action_count": 3, "duration_seconds": 100, "value_usd": 50}
        assert compute_deviation(commitment, outcome) == 0.0

    def test_empty_scope(self):
        assert compute_deviation({}, {}) == 0.0


class TestUpdateCUSUM:
    def test_no_alarm_on_zero_deviation(self):
        state = CUSUMState(agent_id="test")
        alarms = update_cusum(state, 0.0)
        assert alarms == []
        assert state.s_high == 0.0

    def test_alarm_on_persistent_high_deviation(self):
        state = CUSUMState(agent_id="test", k=0.5, h=5.0)
        all_alarms = []
        # Feed persistent deviation of 2.0 — should trigger alarm
        for _ in range(10):
            alarms = update_cusum(state, 2.0)
            all_alarms.extend(alarms)
        assert len(all_alarms) > 0
        assert "scope_creep" in all_alarms[0].lower() or "CUSUM" in all_alarms[0]

    def test_no_alarm_on_small_deviations(self):
        state = CUSUMState(agent_id="test", k=0.5, h=5.0)
        all_alarms = []
        for _ in range(20):
            alarms = update_cusum(state, 0.3)  # Below k=0.5, so S stays at 0
            all_alarms.extend(alarms)
        assert len(all_alarms) == 0

    def test_state_tracks_observations(self):
        state = CUSUMState(agent_id="test")
        update_cusum(state, 1.0)
        update_cusum(state, 2.0)
        assert state.n == 2
        assert state.last_updated is not None


class TestAssessL25:
    def test_passing_assessment(self):
        state = CUSUMState(agent_id="agent-a")
        commitment = {"scope": {"tools": ["git"], "max_actions": 10}}
        outcome = {"tools_used": ["git"], "action_count": 5}
        result = assess_l25(state, commitment, outcome)
        assert result.passed is True
        assert result.deviation_score == 0.0
        assert result.agent_id == "agent-a"
        assert result.level == "L2.5"

    def test_failing_assessment_after_repeated_violations(self):
        state = CUSUMState(agent_id="bad-agent", k=0.5, h=3.0)
        commitment = {"scope": {"tools": ["git"], "max_actions": 5}}
        outcome = {"tools_used": ["git", "shell", "net"], "action_count": 15}

        results = []
        for _ in range(10):
            r = assess_l25(state, commitment, outcome)
            results.append(r)

        # At least one should have triggered alarm
        any_alarm = any(not r.passed for r in results)
        assert any_alarm

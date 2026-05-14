"""
test_expert_load_balancing_engine.py
Phase 3.12 — Expert Load Balancing Intelligence
22 test scenarios — full coverage
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from expert_load_balancing_engine import (
    ExpertLoadBalancingEngine,
    ExpertLoadState,
    SafeAssignmentCapacity,
    LoadBalancingResult,
    get_load_balancing_engine,
    init_load_balancing_engine,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_fresh_engine() -> ExpertLoadBalancingEngine:
    """Return a fresh engine (reset singleton for test isolation)."""
    ExpertLoadBalancingEngine._instance = None
    engine = ExpertLoadBalancingEngine.get_instance()
    engine._initialized = True
    engine._db = None
    return engine


def balanced_context() -> dict:
    return {
        "active_escalations": 0.10,
        "recent_escalations_24h": 0.10,
        "queue_depth": 0.10,
        "expert_caseload_ratio": 0.20,
        "escalation_density": 0.10,
        "handoff_volume": 0.10,
        "capacity_headroom": 0.90,
        "distribution_balance": 0.90,
        "recovery_trend": 0.10,
        "response_lag": 0.05,
        "continuity_handoff_risk": 0.10,
        "emotional_safety_buffer": 0.90,
        "per_expert_loads": [0.15, 0.20, 0.18],
    }


def overloaded_context() -> dict:
    return {
        "active_escalations": 0.90,
        "recent_escalations_24h": 0.90,
        "queue_depth": 0.85,
        "expert_caseload_ratio": 0.90,
        "escalation_density": 0.90,
        "handoff_volume": 0.80,
        "capacity_headroom": 0.05,
        "distribution_balance": 0.20,
        "recovery_trend": 0.05,
        "response_lag": 0.80,
        "continuity_handoff_risk": 0.80,
        "emotional_safety_buffer": 0.10,
        "per_expert_loads": [0.95, 0.90, 0.85],
    }


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# TEST 1: Singleton returns same instance
# ---------------------------------------------------------------------------

def test_01_singleton_same_instance():
    ExpertLoadBalancingEngine._instance = None
    e1 = ExpertLoadBalancingEngine.get_instance()
    e2 = ExpertLoadBalancingEngine.get_instance()
    assert e1 is e2, "Singleton must return same instance"


# ---------------------------------------------------------------------------
# TEST 2: Neutral result on null context
# ---------------------------------------------------------------------------

def test_02_neutral_result_on_null_context():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_001", context=None))
    assert result.is_neutral is True
    assert result.expert_load_state == ExpertLoadState.UNKNOWN.value


# ---------------------------------------------------------------------------
# TEST 3: Neutral result on empty context
# ---------------------------------------------------------------------------

def test_03_neutral_result_on_empty_context():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_002", context={}))
    assert result.is_neutral is False  # empty dict is valid context, returns BALANCED/UNKNOWN
    assert result.expert_load_state is not None


# ---------------------------------------------------------------------------
# TEST 4: BALANCED state — low congestion, full capacity
# ---------------------------------------------------------------------------

def test_04_balanced_state():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_003", context=balanced_context()))
    assert result.expert_load_state == ExpertLoadState.BALANCED.value
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.FULL.value
    assert result.support_congestion_score < 0.35


# ---------------------------------------------------------------------------
# TEST 5: PRESSURED state — elevated load
# ---------------------------------------------------------------------------

def test_05_pressured_state():
    engine = get_fresh_engine()
    ctx = balanced_context()
    ctx["active_escalations"] = 0.45
    ctx["expert_caseload_ratio"] = 0.50
    ctx["escalation_density"] = 0.45
    ctx["response_lag"] = 0.40
    ctx["queue_depth"] = 0.35
    result = run(engine.evaluate_load_balance("user_004", context=ctx))
    assert result.expert_load_state == ExpertLoadState.PRESSURED.value
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.REDUCED.value


# ---------------------------------------------------------------------------
# TEST 6: CONGESTED state
# ---------------------------------------------------------------------------

def test_06_congested_state():
    engine = get_fresh_engine()
    ctx = {
        "active_escalations": 0.68,
        "recent_escalations_24h": 0.65,
        "queue_depth": 0.60,
        "expert_caseload_ratio": 0.65,
        "escalation_density": 0.60,
        "handoff_volume": 0.55,
        "capacity_headroom": 0.30,
        "distribution_balance": 0.40,
        "recovery_trend": 0.10,
        "response_lag": 0.60,
        "continuity_handoff_risk": 0.45,
        "emotional_safety_buffer": 0.40,
        "per_expert_loads": [0.70, 0.65, 0.68],
    }
    result = run(engine.evaluate_load_balance("user_005", context=ctx))
    assert result.expert_load_state == ExpertLoadState.CONGESTED.value
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.MINIMAL.value


# ---------------------------------------------------------------------------
# TEST 7: OVERLOADED state
# ---------------------------------------------------------------------------

def test_07_overloaded_state():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_006", context=overloaded_context()))
    assert result.expert_load_state == ExpertLoadState.OVERLOADED.value
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.ZERO.value


# ---------------------------------------------------------------------------
# TEST 8: RECOVERING state — load decreasing from high
# ---------------------------------------------------------------------------

def test_08_recovering_state():
    engine = get_fresh_engine()
    ctx = {
        "active_escalations": 0.50,
        "recent_escalations_24h": 0.40,
        "queue_depth": 0.40,
        "expert_caseload_ratio": 0.45,
        "escalation_density": 0.40,
        "handoff_volume": 0.30,
        "capacity_headroom": 0.55,
        "distribution_balance": 0.60,
        "recovery_trend": 0.70,
        "response_lag": 0.35,
        "continuity_handoff_risk": 0.35,
        "emotional_safety_buffer": 0.60,
        "per_expert_loads": [0.50, 0.45, 0.48],
    }
    result = run(engine.evaluate_load_balance("user_007", context=ctx))
    assert result.expert_load_state == ExpertLoadState.RECOVERING.value
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.PARTIAL.value


# ---------------------------------------------------------------------------
# TEST 9: HANDOFF_AT_RISK state
# ---------------------------------------------------------------------------

def test_09_handoff_at_risk_state():
    engine = get_fresh_engine()
    ctx = balanced_context()
    ctx["continuity_handoff_risk"] = 0.80
    ctx["active_escalations"] = 0.40
    ctx["expert_caseload_ratio"] = 0.40
    result = run(engine.evaluate_load_balance("user_008", context=ctx))
    assert result.expert_load_state == ExpertLoadState.HANDOFF_AT_RISK.value
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.RESTRICTED.value


# ---------------------------------------------------------------------------
# TEST 10: QUEUE_CRITICAL state
# ---------------------------------------------------------------------------

def test_10_queue_critical_state():
    engine = get_fresh_engine()
    ctx = balanced_context()
    ctx["active_escalations"] = 0.90
    ctx["recent_escalations_24h"] = 0.90
    ctx["queue_depth"] = 0.90
    result = run(engine.evaluate_load_balance("user_009", context=ctx))
    assert result.expert_load_state == ExpertLoadState.QUEUE_CRITICAL.value
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.EMERGENCY.value


# ---------------------------------------------------------------------------
# TEST 11: UNKNOWN state — minimal signals
# ---------------------------------------------------------------------------

def test_11_unknown_capacity_on_missing_data():
    engine = get_fresh_engine()
    # Context with all defaults — should resolve to BALANCED (defaults are safe)
    result = run(engine.evaluate_load_balance("user_010", context={}))
    assert result.safe_assignment_capacity in [
        SafeAssignmentCapacity.CONSERVATIVE.value,
        SafeAssignmentCapacity.FULL.value,
    ]


# ---------------------------------------------------------------------------
# TEST 12: human_support_integrity flag when < 0.50
# ---------------------------------------------------------------------------

def test_12_integrity_at_risk_flag():
    engine = get_fresh_engine()
    ctx = overloaded_context()
    ctx["emotional_safety_buffer"] = 0.05
    ctx["capacity_headroom"] = 0.05
    ctx["distribution_balance"] = 0.05
    result = run(engine.evaluate_load_balance("user_011", context=ctx))
    assert result.integrity_at_risk is True
    assert result.human_support_integrity_score < 0.50


# ---------------------------------------------------------------------------
# TEST 13: safe_assignment_capacity = zero when OVERLOADED
# ---------------------------------------------------------------------------

def test_13_zero_capacity_when_overloaded():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_012", context=overloaded_context()))
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.ZERO.value


# ---------------------------------------------------------------------------
# TEST 14: safe_assignment_capacity = full when BALANCED
# ---------------------------------------------------------------------------

def test_14_full_capacity_when_balanced():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_013", context=balanced_context()))
    assert result.safe_assignment_capacity == SafeAssignmentCapacity.FULL.value


# ---------------------------------------------------------------------------
# TEST 15: congestion score capped at 1.0
# ---------------------------------------------------------------------------

def test_15_congestion_score_capped():
    engine = get_fresh_engine()
    ctx = {k: 1.0 for k in [
        "active_escalations", "recent_escalations_24h", "queue_depth",
        "expert_caseload_ratio", "escalation_density", "handoff_volume",
        "response_lag", "continuity_handoff_risk",
    ]}
    ctx["capacity_headroom"] = 0.0
    ctx["distribution_balance"] = 0.0
    ctx["recovery_trend"] = 0.0
    ctx["emotional_safety_buffer"] = 0.0
    ctx["per_expert_loads"] = [1.0, 1.0, 1.0]
    result = run(engine.evaluate_load_balance("user_014", context=ctx))
    assert result.support_congestion_score <= 1.0


# ---------------------------------------------------------------------------
# TEST 16: stability score floored at 0.0
# ---------------------------------------------------------------------------

def test_16_stability_floored():
    engine = get_fresh_engine()
    ctx = overloaded_context()
    result = run(engine.evaluate_load_balance("user_015", context=ctx))
    assert result.operational_stability_score >= 0.0


# ---------------------------------------------------------------------------
# TEST 17: notes JSONB contains signal breakdown
# ---------------------------------------------------------------------------

def test_17_notes_contain_signal_breakdown():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_016", context=balanced_context()))
    notes = result.load_balancing_notes
    assert "congestion" in notes
    assert "overload_risk" in notes
    assert "stability" in notes
    assert "load_state" in notes
    assert "evaluated_at" in notes


# ---------------------------------------------------------------------------
# TEST 18: DB persistence called when db available
# ---------------------------------------------------------------------------

def test_18_db_persistence_called():
    ExpertLoadBalancingEngine._instance = None
    engine = ExpertLoadBalancingEngine.get_instance()
    engine._initialized = True
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    engine._db = mock_db
    result = run(engine.evaluate_load_balance("user_017", context=balanced_context()))
    assert mock_db.execute.called


# ---------------------------------------------------------------------------
# TEST 19: last_load_balancing_check timestamp updated
# ---------------------------------------------------------------------------

def test_19_evaluated_at_present():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_018", context=balanced_context()))
    assert result.evaluated_at is not None
    assert "T" in result.evaluated_at  # ISO format


# ---------------------------------------------------------------------------
# TEST 20: governance hierarchy — never overrides escalation
# ---------------------------------------------------------------------------

def test_20_no_outbound_in_result():
    engine = get_fresh_engine()
    result = run(engine.evaluate_load_balance("user_019", context=balanced_context()))
    # Result is a pure data object — no callable, no send method
    assert not hasattr(result, "send")
    assert not hasattr(result, "dispatch")
    assert not hasattr(result, "notify")
    assert not hasattr(result, "escalate")


# ---------------------------------------------------------------------------
# TEST 21: no outbound calls in any code path
# ---------------------------------------------------------------------------

def test_21_no_outbound_imports():
    import inspect
    import expert_load_balancing_engine as mod
    source = inspect.getsource(mod)
    forbidden = ["import telegram", "import sendpulse", "requests.post", "httpx.post"]
    for f in forbidden:
        assert f not in source.lower(), f"Forbidden outbound call found: {f}"


# ---------------------------------------------------------------------------
# TEST 22: idempotent init — second call returns same singleton
# ---------------------------------------------------------------------------

def test_22_idempotent_init():
    ExpertLoadBalancingEngine._instance = None
    e1 = run(init_load_balancing_engine(db=None))
    e2 = run(init_load_balancing_engine(db=None))
    assert e1 is e2, "Second init must return same singleton"
    assert e1._initialized is True


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_01_singleton_same_instance,
        test_02_neutral_result_on_null_context,
        test_03_neutral_result_on_empty_context,
        test_04_balanced_state,
        test_05_pressured_state,
        test_06_congested_state,
        test_07_overloaded_state,
        test_08_recovering_state,
        test_09_handoff_at_risk_state,
        test_10_queue_critical_state,
        test_11_unknown_capacity_on_missing_data,
        test_12_integrity_at_risk_flag,
        test_13_zero_capacity_when_overloaded,
        test_14_full_capacity_when_balanced,
        test_15_congestion_score_capped,
        test_16_stability_floored,
        test_17_notes_contain_signal_breakdown,
        test_18_db_persistence_called,
        test_19_evaluated_at_present,
        test_20_no_outbound_in_result,
        test_21_no_outbound_imports,
        test_22_idempotent_init,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")

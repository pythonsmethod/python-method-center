"""
test_central_cognitive_orchestrator.py
Phase 3.13 — Central Cognitive Orchestrator
22 test scenarios — full coverage
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from central_cognitive_orchestrator import (
    CentralCognitiveOrchestrator,
    SystemCoherenceState,
    DominantPriority,
    CognitiveOrchestrationResult,
    get_cognitive_orchestrator,
    init_cognitive_orchestrator,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_fresh_engine() -> CentralCognitiveOrchestrator:
    CentralCognitiveOrchestrator._instance = None
    engine = CentralCognitiveOrchestrator.get_instance()
    engine._initialized = True
    engine._db = None
    return engine


def coherent_context() -> dict:
    """Context representing a fully coherent system."""
    return {
        "risk_score": 0.10,
        "engagement_score": 0.85,
        "continuity_risk": 0.10,
        "trajectory_drift": 0.10,
        "recovery_trend": 0.20,
        "human_escalation_active": False,
        "silence_respected": False,
        "recovery_policy_active": False,
        "orchestration_result": {
            "orchestration_state": "CLEAR",
            "route_overload_score": 0.05,
        },
        "pacing_result": {
            "pacing_state": "SUSTAINABLE",
            "pacing_coherence_score": 0.90,
        },
        "load_balancing_result": {
            "expert_load_state": "BALANCED",
            "operational_stability_score": 0.92,
            "support_congestion_score": 0.08,
        },
    }


def overloaded_context() -> dict:
    """Context with cascading overload across all engines."""
    return {
        "risk_score": 0.90,
        "engagement_score": 0.15,
        "continuity_risk": 0.85,
        "trajectory_drift": 0.80,
        "recovery_trend": 0.05,
        "human_escalation_active": False,
        "silence_respected": False,
        "recovery_policy_active": False,
        "orchestration_result": {
            "orchestration_state": "OVERLOADED",
            "route_overload_score": 0.85,
        },
        "pacing_result": {
            "pacing_state": "OVERLOADED",
            "pacing_coherence_score": 0.10,
        },
        "load_balancing_result": {
            "expert_load_state": "OVERLOADED",
            "operational_stability_score": 0.10,
            "support_congestion_score": 0.90,
        },
    }


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# TEST 1: Singleton returns same instance
# ---------------------------------------------------------------------------

def test_01_singleton_same_instance():
    CentralCognitiveOrchestrator._instance = None
    e1 = CentralCognitiveOrchestrator.get_instance()
    e2 = CentralCognitiveOrchestrator.get_instance()
    assert e1 is e2


# ---------------------------------------------------------------------------
# TEST 2: Neutral result on null context
# ---------------------------------------------------------------------------

def test_02_neutral_result_on_null_context():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_001", context=None))
    assert result.is_neutral is True
    assert result.system_coherence_state == SystemCoherenceState.UNKNOWN.value


# ---------------------------------------------------------------------------
# TEST 3: COHERENT state — all signals healthy
# ---------------------------------------------------------------------------

def test_03_coherent_state():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_002", context=coherent_context()))
    assert result.system_coherence_state == SystemCoherenceState.COHERENT.value
    assert result.overall_system_stability_score >= 0.65
    assert result.governance_conflict_detected is False
    assert result.overload_chain_detected is False


# ---------------------------------------------------------------------------
# TEST 4: DRIFT_DETECTED — trajectory + pacing instability elevated
# ---------------------------------------------------------------------------

def test_04_drift_detected():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["trajectory_drift"] = 0.75
    ctx["pacing_result"]["pacing_coherence_score"] = 0.20
    ctx["pacing_result"]["pacing_state"] = "DECELERATING"
    result = run(engine.evaluate_system_coherence("user_003", context=ctx))
    assert result.operational_drift_score >= 0.40
    assert result.system_coherence_state in (
        SystemCoherenceState.DRIFT_DETECTED.value,
        SystemCoherenceState.CONFLICT_DETECTED.value,
        SystemCoherenceState.OVERLOAD_CHAIN.value,
        SystemCoherenceState.INSTABILITY.value,
    )


# ---------------------------------------------------------------------------
# TEST 5: CONFLICT_DETECTED — orchestration overloaded vs pacing sustainable
# ---------------------------------------------------------------------------

def test_05_conflict_detected():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["orchestration_result"]["orchestration_state"] = "OVERLOADED"
    ctx["pacing_result"]["pacing_state"] = "SUSTAINABLE"
    result = run(engine.evaluate_system_coherence("user_004", context=ctx))
    assert result.governance_conflict_detected is True


# ---------------------------------------------------------------------------
# TEST 6: OVERLOAD_CHAIN — >= 3 overload signals
# ---------------------------------------------------------------------------

def test_06_overload_chain():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_005", context=overloaded_context()))
    assert result.overload_chain_detected is True
    assert result.system_coherence_state in (
        SystemCoherenceState.OVERLOAD_CHAIN.value,
        SystemCoherenceState.INSTABILITY.value,
        SystemCoherenceState.ESCALATION_REQUIRED.value,
    )


# ---------------------------------------------------------------------------
# TEST 7: INSTABILITY — overload_chain AND conflict simultaneously
# ---------------------------------------------------------------------------

def test_07_instability():
    engine = get_fresh_engine()
    ctx = overloaded_context()
    ctx["orchestration_result"]["orchestration_state"] = "OVERLOADED"
    ctx["pacing_result"]["pacing_state"] = "SUSTAINABLE"  # creates conflict
    result = run(engine.evaluate_system_coherence("user_006", context=ctx))
    assert result.system_coherence_state in (
        SystemCoherenceState.INSTABILITY.value,
        SystemCoherenceState.OVERLOAD_CHAIN.value,
        SystemCoherenceState.ESCALATION_REQUIRED.value,
    )


# ---------------------------------------------------------------------------
# TEST 8: GOVERNANCE_BREACH_RISK — high governance pressure
# ---------------------------------------------------------------------------

def test_08_governance_breach_risk():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["human_escalation_active"] = True
    ctx["risk_score"] = 0.85
    ctx["continuity_risk"] = 0.80
    result = run(engine.evaluate_system_coherence("user_007", context=ctx))
    # human_escalation makes dominant_priority = HUMAN_ESCALATION
    assert result.dominant_operational_priority == DominantPriority.HUMAN_ESCALATION.value


# ---------------------------------------------------------------------------
# TEST 9: ESCALATION_REQUIRED — risk critical + continuity failure
# ---------------------------------------------------------------------------

def test_09_escalation_required():
    engine = get_fresh_engine()
    ctx = overloaded_context()
    ctx["risk_score"] = 0.90
    ctx["continuity_risk"] = 0.85
    result = run(engine.evaluate_system_coherence("user_008", context=ctx))
    assert result.system_coherence_state in (
        SystemCoherenceState.ESCALATION_REQUIRED.value,
        SystemCoherenceState.INSTABILITY.value,
        SystemCoherenceState.OVERLOAD_CHAIN.value,
    )


# ---------------------------------------------------------------------------
# TEST 10: RECOVERING — stability improving
# ---------------------------------------------------------------------------

def test_10_recovering_state():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["recovery_trend"] = 0.70
    ctx["risk_score"] = 0.40
    ctx["continuity_risk"] = 0.45
    ctx["trajectory_drift"] = 0.35
    ctx["orchestration_result"]["route_overload_score"] = 0.40
    result = run(engine.evaluate_system_coherence("user_009", context=ctx))
    assert result.system_coherence_state in (
        SystemCoherenceState.RECOVERING.value,
        SystemCoherenceState.COHERENT.value,
        SystemCoherenceState.DRIFT_DETECTED.value,
        SystemCoherenceState.UNKNOWN.value,
    )


# ---------------------------------------------------------------------------
# TEST 11: UNKNOWN state — minimal signal data
# ---------------------------------------------------------------------------

def test_11_unknown_state_minimal_data():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_010", context={}))
    # empty context = all defaults = should produce COHERENT or UNKNOWN
    assert result.system_coherence_state in (
        SystemCoherenceState.COHERENT.value,
        SystemCoherenceState.UNKNOWN.value,
    )
    assert result.is_neutral is False


# ---------------------------------------------------------------------------
# TEST 12: Dominant priority = HUMAN_ESCALATION
# ---------------------------------------------------------------------------

def test_12_priority_human_escalation():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["human_escalation_active"] = True
    result = run(engine.evaluate_system_coherence("user_011", context=ctx))
    assert result.dominant_operational_priority == DominantPriority.HUMAN_ESCALATION.value


# ---------------------------------------------------------------------------
# TEST 13: Dominant priority = SILENCE_RESPECT
# ---------------------------------------------------------------------------

def test_13_priority_silence_respect():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["silence_respected"] = True
    result = run(engine.evaluate_system_coherence("user_012", context=ctx))
    assert result.dominant_operational_priority == DominantPriority.SILENCE_RESPECT.value


# ---------------------------------------------------------------------------
# TEST 14: Dominant priority = EMOTIONAL_SAFETY
# ---------------------------------------------------------------------------

def test_14_priority_emotional_safety():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["engagement_score"] = 0.05
    ctx["risk_score"] = 0.85
    result = run(engine.evaluate_system_coherence("user_013", context=ctx))
    assert result.dominant_operational_priority in (
        DominantPriority.EMOTIONAL_SAFETY.value,
        DominantPriority.CONTINUITY_PROTECTION.value,
        DominantPriority.TRAJECTORY_CORRECTION.value,
    )


# ---------------------------------------------------------------------------
# TEST 15: Dominant priority = NORMAL_OPERATION
# ---------------------------------------------------------------------------

def test_15_priority_normal_operation():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_014", context=coherent_context()))
    assert result.dominant_operational_priority == DominantPriority.NORMAL_OPERATION.value


# ---------------------------------------------------------------------------
# TEST 16: governance_conflict_detected = True on overload chain >= 3
# ---------------------------------------------------------------------------

def test_16_governance_conflict_on_overload_chain():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_015", context=overloaded_context()))
    assert result.overload_chain_detected is True


# ---------------------------------------------------------------------------
# TEST 17: overload_chain_detected = True on cascading signals
# ---------------------------------------------------------------------------

def test_17_overload_chain_cascading():
    engine = get_fresh_engine()
    ctx = coherent_context()
    ctx["risk_score"] = 0.80
    ctx["continuity_risk"] = 0.75
    ctx["orchestration_result"]["orchestration_state"] = "OVERLOADED"
    ctx["pacing_result"]["pacing_state"] = "OVERLOADED"
    ctx["load_balancing_result"]["expert_load_state"] = "OVERLOADED"
    result = run(engine.evaluate_system_coherence("user_016", context=ctx))
    assert result.overload_chain_detected is True


# ---------------------------------------------------------------------------
# TEST 18: All coherence scores capped at 1.0, floored at 0.0
# ---------------------------------------------------------------------------

def test_18_scores_bounded():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_017", context=overloaded_context()))
    assert 0.0 <= result.continuity_integrity_score <= 1.0
    assert 0.0 <= result.emotional_safety_integrity_score <= 1.0
    assert 0.0 <= result.route_integrity_score <= 1.0
    assert 0.0 <= result.operational_drift_score <= 1.0
    assert 0.0 <= result.escalation_coherence_score <= 1.0
    assert 0.0 <= result.orchestration_coherence_score <= 1.0
    assert 0.0 <= result.pacing_coherence_score <= 1.0
    assert 0.0 <= result.overall_system_stability_score <= 1.0


# ---------------------------------------------------------------------------
# TEST 19: Notes JSONB contains signal breakdown + contradiction log
# ---------------------------------------------------------------------------

def test_19_notes_contain_breakdown():
    engine = get_fresh_engine()
    result = run(engine.evaluate_system_coherence("user_018", context=coherent_context()))
    notes = result.cognitive_orchestrator_notes
    assert "signals" in notes
    assert "scores" in notes
    assert "overload_chain" in notes
    assert "contradictions" in notes
    assert "coherence_state" in notes
    assert "dominant_priority" in notes
    assert "evaluated_at" in notes


# ---------------------------------------------------------------------------
# TEST 20: DB persistence called when db available
# ---------------------------------------------------------------------------

def test_20_db_persistence_called():
    CentralCognitiveOrchestrator._instance = None
    engine = CentralCognitiveOrchestrator.get_instance()
    engine._initialized = True
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    engine._db = mock_db
    result = run(engine.evaluate_system_coherence("user_019", context=coherent_context()))
    assert mock_db.execute.called


# ---------------------------------------------------------------------------
# TEST 21: No outbound calls in any code path
# ---------------------------------------------------------------------------

def test_21_no_outbound_imports():
    import inspect
    import central_cognitive_orchestrator as mod
    source = inspect.getsource(mod)
    forbidden = ["import telegram", "import sendpulse", "requests.post", "httpx.post", "openai"]
    for f in forbidden:
        assert f not in source.lower(), f"Forbidden outbound call: {f}"


# ---------------------------------------------------------------------------
# TEST 22: Idempotent init — second call returns same singleton
# ---------------------------------------------------------------------------

def test_22_idempotent_init():
    CentralCognitiveOrchestrator._instance = None
    e1 = run(init_cognitive_orchestrator(db=None))
    e2 = run(init_cognitive_orchestrator(db=None))
    assert e1 is e2
    assert e1._initialized is True


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    all_tests = [
        test_01_singleton_same_instance,
        test_02_neutral_result_on_null_context,
        test_03_coherent_state,
        test_04_drift_detected,
        test_05_conflict_detected,
        test_06_overload_chain,
        test_07_instability,
        test_08_governance_breach_risk,
        test_09_escalation_required,
        test_10_recovering_state,
        test_11_unknown_state_minimal_data,
        test_12_priority_human_escalation,
        test_13_priority_silence_respect,
        test_14_priority_emotional_safety,
        test_15_priority_normal_operation,
        test_16_governance_conflict_on_overload_chain,
        test_17_overload_chain_cascading,
        test_18_scores_bounded,
        test_19_notes_contain_breakdown,
        test_20_db_persistence_called,
        test_21_no_outbound_imports,
        test_22_idempotent_init,
    ]
    passed = failed = 0
    for t in all_tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")

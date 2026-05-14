"""
test_dynamic_pacing_intelligence.py
Phase 3.11 — Dynamic Pacing Intelligence Tests
Python Method Digital Rehabilitation Center

22 test scenarios covering:
- Singleton idempotency
- Pacing state classification
- Pressure risk detection
- Overload detection
- Adaptive pause logic
- Safe delay lookup
- Governance guards
- Exception safety
- Formula verification
- Dashboard stats
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine():
    """Create a fresh engine instance without DB pool."""
    from dynamic_pacing_intelligence import DynamicPacingEngine
    engine = DynamicPacingEngine.__new__(DynamicPacingEngine)
    engine._pool = None
    return engine


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test 1 — Singleton idempotency
# ---------------------------------------------------------------------------

def test_01_singleton_idempotent():
    import dynamic_pacing_intelligence as mod
    mod._engine_instance = None
    mod._engine_lock = None
    DynamicPacingEngine = mod.DynamicPacingEngine
    DynamicPacingEngine._instance = None
    DynamicPacingEngine._initialized = False

    async def _run():
        with patch.object(DynamicPacingEngine, '_init', new_callable=AsyncMock):
            e1 = await mod.init_pacing_engine()
            e2 = await mod.init_pacing_engine()
            assert e1 is e2

    run(_run())


# ---------------------------------------------------------------------------
# Test 2 — Empty inputs → UNKNOWN, neutral result, no raise
# ---------------------------------------------------------------------------

def test_02_empty_inputs_unknown():
    engine = make_engine()
    result = run(engine.evaluate_pacing(user_id="u1"))
    from dynamic_pacing_intelligence import PacingState
    assert result.pacing_state == PacingState.UNKNOWN
    assert result.error_message is None
    assert result.pacing_score >= 0.0


# ---------------------------------------------------------------------------
# Test 3 — High behaviour + recent message → SUSTAINABLE
# ---------------------------------------------------------------------------

def test_03_sustainable_state():
    engine = make_engine()
    result = run(engine.evaluate_pacing(
        user_id="u2",
        behaviour_result={"behaviour_score": 0.9},
        trajectory_result={"trajectory_score": 0.85},
        continuity_result={"continuity_score": 0.8},
        state_machine_result={
            "stage_completion_score": 0.7,
            "stage_stall_detected": False,
            "rehabilitation_state": "TREATMENT_ACTIVE",
            "escalation_gate": "clear",
        },
        profile_data={"days_since_last_message": 1.0},
        orchestration_result={"route_overload_score": 0.1, "active_stage_count": 1},
    ))
    from dynamic_pacing_intelligence import PacingState
    assert result.pacing_state == PacingState.SUSTAINABLE
    assert result.pacing_score >= 0.75
    assert result.error_message is None


# ---------------------------------------------------------------------------
# Test 4 — pacing_pressure_risk >= 0.60 → adaptive_pause_needed = True
# ---------------------------------------------------------------------------

def test_04_high_pressure_pause_needed():
    engine = make_engine()
    # Force high pressure: high overload + many stages + stall + escalation
    result = run(engine.evaluate_pacing(
        user_id="u3",
        orchestration_result={"route_overload_score": 0.9, "active_stage_count": 4},
        state_machine_result={
            "stage_stall_detected": True,
            "escalation_gate": "active",
            "rehabilitation_state": "NEEDS_ASSESSMENT",
            "stage_completion_score": 0.2,
        },
        profile_data={"days_since_last_message": 2.0},
    ))
    assert result.adaptive_pause_needed is True
    assert result.pacing_pressure_risk >= 0.60


# ---------------------------------------------------------------------------
# Test 5 — pacing_overload_risk >= 0.65 → adaptive_pause_needed = True
# ---------------------------------------------------------------------------

def test_05_high_overload_pause_needed():
    engine = make_engine()
    overload_risk = engine._compute_pacing_overload_risk(
        route_overload_score=0.9,
        active_stage_count=4,
        escalation_gate="active",
    )
    assert overload_risk >= 0.65
    # Full eval
    result = run(engine.evaluate_pacing(
        user_id="u4",
        orchestration_result={"route_overload_score": 0.9, "active_stage_count": 4},
        state_machine_result={"escalation_gate": "active", "stage_stall_detected": False, "rehabilitation_state": "INITIAL_CONTACT"},
        profile_data={"days_since_last_message": 1.0},
    ))
    assert result.adaptive_pause_needed is True


# ---------------------------------------------------------------------------
# Test 6 — stage_stall + stability < 0.40 → pause needed
# ---------------------------------------------------------------------------

def test_06_stall_low_stability_pause():
    engine = make_engine()
    result = run(engine.evaluate_pacing(
        user_id="u5",
        state_machine_result={
            "stage_stall_detected": True,
            "escalation_gate": "clear",
            "rehabilitation_state": "MONITORING",
            "stage_completion_score": 0.1,
        },
        behaviour_result={"behaviour_score": 0.1},
        trajectory_result={"trajectory_score": 0.1},
        profile_data={"days_since_last_message": 25.0},
        orchestration_result={"route_overload_score": 0.0, "active_stage_count": 1},
    ))
    assert result.pacing_stability_score < 0.40
    assert result.adaptive_pause_needed is True


# ---------------------------------------------------------------------------
# Test 7 — silence_respected = True → neutral result
# ---------------------------------------------------------------------------

def test_07_silence_respected_guard():
    engine = make_engine()
    result = run(engine.evaluate_pacing(user_id="u6", silence_respected=True))
    from dynamic_pacing_intelligence import PacingState
    assert result.pacing_state == PacingState.UNKNOWN
    assert "silence_respected" in (result.pacing_notes.get("neutral_reason") or "")


# ---------------------------------------------------------------------------
# Test 8 — human_escalation = True → neutral result
# ---------------------------------------------------------------------------

def test_08_human_escalation_guard():
    engine = make_engine()
    result = run(engine.evaluate_pacing(user_id="u7", human_escalation=True))
    from dynamic_pacing_intelligence import PacingState
    assert result.pacing_state == PacingState.UNKNOWN
    assert "human_escalation" in (result.pacing_notes.get("neutral_reason") or "")


# ---------------------------------------------------------------------------
# Test 9 — recovery_policy_active = True → neutral result
# ---------------------------------------------------------------------------

def test_09_recovery_policy_guard():
    engine = make_engine()
    result = run(engine.evaluate_pacing(user_id="u8", recovery_policy_active=True))
    from dynamic_pacing_intelligence import PacingState
    assert result.pacing_state == PacingState.UNKNOWN
    assert "recovery_policy" in (result.pacing_notes.get("neutral_reason") or "")


# ---------------------------------------------------------------------------
# Test 10 — OVERLOADED state → safe_next_step_delay = 96h
# ---------------------------------------------------------------------------

def test_10_overloaded_delay_96h():
    engine = make_engine()
    from dynamic_pacing_intelligence import PacingState
    delay = engine._compute_safe_delay(PacingState.OVERLOADED, 0.1)
    assert delay == 96
    delay_high = engine._compute_safe_delay(PacingState.OVERLOADED, 0.7)
    assert delay_high == 96


# ---------------------------------------------------------------------------
# Test 11 — PAUSED state → safe_next_step_delay = 72h
# ---------------------------------------------------------------------------

def test_11_paused_delay_72h():
    engine = make_engine()
    from dynamic_pacing_intelligence import PacingState
    delay = engine._compute_safe_delay(PacingState.PAUSED, 0.1)
    assert delay == 72


# ---------------------------------------------------------------------------
# Test 12 — SUSTAINABLE + pressure < 0.30 → safe_next_step_delay = 0
# ---------------------------------------------------------------------------

def test_12_sustainable_low_pressure_no_delay():
    engine = make_engine()
    from dynamic_pacing_intelligence import PacingState
    delay = engine._compute_safe_delay(PacingState.SUSTAINABLE, 0.1)
    assert delay == 0


# ---------------------------------------------------------------------------
# Test 13 — recommended_route_speed = "hold" when OVERLOADED
# ---------------------------------------------------------------------------

def test_13_hold_when_overloaded():
    engine = make_engine()
    from dynamic_pacing_intelligence import PacingState, RouteSpeed
    speed = engine._determine_route_speed(PacingState.OVERLOADED, 0.2)
    assert speed == RouteSpeed.HOLD


# ---------------------------------------------------------------------------
# Test 14 — recommended_route_speed = "slow" when DECELERATING + pressure >= 0.30
# ---------------------------------------------------------------------------

def test_14_slow_when_decelerating_mid_pressure():
    engine = make_engine()
    from dynamic_pacing_intelligence import PacingState, RouteSpeed
    speed = engine._determine_route_speed(PacingState.DECELERATING, 0.35)
    assert speed == RouteSpeed.SLOW


# ---------------------------------------------------------------------------
# Test 15 — pacing_coherence low when signals contradict each other
# ---------------------------------------------------------------------------

def test_15_coherence_low_when_contradictory():
    engine = make_engine()
    # Very different values = high stdev = low coherence
    coherence = engine._compute_pacing_coherence(
        pacing_stability_score=0.9,      # high
        pacing_pressure_risk=0.9,        # high → 1-0.9=0.1
        pacing_overload_risk=0.9,        # high → 1-0.9=0.1
        progression_sustainability_score=0.9,  # high
    )
    # signals = [0.9, 0.1, 0.1, 0.9] → stdev is high → coherence low
    assert coherence < 0.6


# ---------------------------------------------------------------------------
# Test 16 — pacing_score formula verification
# ---------------------------------------------------------------------------

def test_16_pacing_score_formula():
    engine = make_engine()
    score = engine._compute_pacing_score(
        engagement_recovery_capacity=0.8,
        pacing_stability_score=0.7,
        progression_sustainability_score=0.6,
        pacing_overload_risk=0.2,
        pacing_pressure_risk=0.1,
    )
    expected = (0.8 * 0.25) + (0.7 * 0.25) + (0.6 * 0.20) + (0.8 * 0.20) + (0.9 * 0.10)
    assert abs(score - expected) < 0.001


# ---------------------------------------------------------------------------
# Test 17 — pacing_stability_score formula verification
# ---------------------------------------------------------------------------

def test_17_stability_formula():
    engine = make_engine()
    # 5 days, behaviour=0.8, no stall, trajectory=0.7
    score = engine._compute_pacing_stability(
        days_since_last_message=5.0,
        behaviour_score=0.8,
        stage_stall_detected=False,
        trajectory_score=0.7,
    )
    recency = max(0, 1.0 - (5/30)) * 0.30    # = (25/30)*0.30 ≈ 0.25
    freq    = max(0, 1.0 - (5/14)) * 0.25    # = (9/14)*0.25 ≈ 0.16
    beh     = 0.8 * 0.20                     # = 0.16
    stall   = 0.15                           # no stall
    traj    = 0.7 * 0.10                     # = 0.07
    expected = recency + freq + beh + stall + traj
    assert abs(score - round(min(expected, 1.0), 4)) < 0.001


# ---------------------------------------------------------------------------
# Test 18 — engagement_recovery_capacity formula
# ---------------------------------------------------------------------------

def test_18_engagement_recovery_formula():
    engine = make_engine()
    score = engine._compute_engagement_recovery(
        trajectory_score=0.8,
        behaviour_score=0.7,
        continuity_score=0.6,
        stage_completion_score=0.5,
    )
    expected = (0.8 * 0.35) + (0.7 * 0.30) + (0.6 * 0.20) + (0.5 * 0.15)
    assert abs(score - round(min(expected, 1.0), 4)) < 0.001


# ---------------------------------------------------------------------------
# Test 19 — exception in evaluate_pacing → neutral result, no raise
# ---------------------------------------------------------------------------

def test_19_exception_returns_neutral():
    engine = make_engine()
    original = engine._compute_pacing_stability
    def broken(*args, **kwargs):
        raise RuntimeError("forced failure")
    engine._compute_pacing_stability = broken

    result = run(engine.evaluate_pacing(
        user_id="u9",
        profile_data={"days_since_last_message": 2.0},
        behaviour_result={"behaviour_score": 0.5},
    ))
    from dynamic_pacing_intelligence import PacingState
    assert result.pacing_state == PacingState.UNKNOWN
    assert result.error_message is not None
    assert "forced failure" in result.error_message


# ---------------------------------------------------------------------------
# Test 20 — get_dashboard_stats returns no_db when pool is None
# ---------------------------------------------------------------------------

def test_20_dashboard_no_db():
    engine = make_engine()
    stats = run(engine.get_dashboard_stats())
    assert stats.get("status") == "no_db"


# ---------------------------------------------------------------------------
# Test 21 — pacing_notes contains full reasoning chain
# ---------------------------------------------------------------------------

def test_21_notes_contain_reasoning():
    engine = make_engine()
    result = run(engine.evaluate_pacing(
        user_id="u10",
        behaviour_result={"behaviour_score": 0.7},
        trajectory_result={"trajectory_score": 0.6},
        continuity_result={"continuity_score": 0.5},
        state_machine_result={
            "stage_stall_detected": False,
            "rehabilitation_state": "MONITORING",
            "stage_completion_score": 0.5,
            "escalation_gate": "clear",
        },
        profile_data={"days_since_last_message": 3.0},
        orchestration_result={"route_overload_score": 0.1, "active_stage_count": 1},
    ))
    notes = result.pacing_notes
    assert "evaluated_at" in notes
    assert "pacing_state" in notes
    assert "pacing_score" in notes
    assert "pacing_stability_score" in notes
    assert "pacing_pressure_risk" in notes
    assert "adaptive_pause_needed" in notes
    assert "safe_next_step_delay" in notes
    assert "pacing_coherence" in notes
    assert "behaviour_score" in notes
    assert "trajectory_score" in notes


# ---------------------------------------------------------------------------
# Test 22 — silence_respected = True → adaptive_pause_needed = True
# ---------------------------------------------------------------------------

def test_22_silence_respected_triggers_pause():
    engine = make_engine()
    pause_needed = engine._check_adaptive_pause_needed(
        pacing_pressure_risk=0.1,
        pacing_overload_risk=0.1,
        pacing_state="SUSTAINABLE",
        stage_stall_detected=False,
        pacing_stability_score=0.9,
        silence_respected=True,  # <-- governance
        days_since_last_message=1.0,
        rehab_state="MONITORING",
    )
    assert pause_needed is True


# ---------------------------------------------------------------------------
# Run guard
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    tests = [
        test_01_singleton_idempotent,
        test_02_empty_inputs_unknown,
        test_03_sustainable_state,
        test_04_high_pressure_pause_needed,
        test_05_high_overload_pause_needed,
        test_06_stall_low_stability_pause,
        test_07_silence_respected_guard,
        test_08_human_escalation_guard,
        test_09_recovery_policy_guard,
        test_10_overloaded_delay_96h,
        test_11_paused_delay_72h,
        test_12_sustainable_low_pressure_no_delay,
        test_13_hold_when_overloaded,
        test_14_slow_when_decelerating_mid_pressure,
        test_15_coherence_low_when_contradictory,
        test_16_pacing_score_formula,
        test_17_stability_formula,
        test_18_engagement_recovery_formula,
        test_19_exception_returns_neutral,
        test_20_dashboard_no_db,
        test_21_notes_contain_reasoning,
        test_22_silence_respected_triggers_pause,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS: {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {t.__name__} — {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

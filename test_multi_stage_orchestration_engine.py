"""
test_multi_stage_orchestration_engine.py
Phase 3.10 — Multi-Stage Orchestration Engine Tests
Python Method Digital Rehabilitation Center

22 test scenarios covering:
- Singleton idempotency
- Stage classification
- Conflict detection
- Overload scoring
- Handoff readiness
- Governance guards
- Exception safety
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
    from multi_stage_orchestration_engine import MultiStageOrchestrationEngine
    engine = MultiStageOrchestrationEngine.__new__(MultiStageOrchestrationEngine)
    engine._pool = None
    return engine


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test 1 — Singleton idempotency
# ---------------------------------------------------------------------------

def test_01_singleton_idempotent():
    """init_orchestration_engine() called twice returns same instance."""
    import multi_stage_orchestration_engine as mod
    # Reset for test
    mod._engine_instance = None
    mod._engine_lock = None
    MultiStageOrchestrationEngine = mod.MultiStageOrchestrationEngine
    MultiStageOrchestrationEngine._instance = None
    MultiStageOrchestrationEngine._initialized = False

    async def _run():
        with patch.object(MultiStageOrchestrationEngine, '_init', new_callable=AsyncMock):
            e1 = await mod.init_orchestration_engine()
            e2 = await mod.init_orchestration_engine()
            assert e1 is e2

    run(_run())


# ---------------------------------------------------------------------------
# Test 2 — Empty stages → CLEAR, no_action_needed
# ---------------------------------------------------------------------------

def test_02_empty_stages_clear():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u1",
        state_machine_result={},
        trajectory_result={},
        continuity_result={},
        behaviour_result={},
        profile_data={},
    ))
    from multi_stage_orchestration_engine import OrchestrationState, OrchestrationAction
    assert result.orchestration_state == OrchestrationState.CLEAR
    assert result.active_stage_count == 0
    assert result.stage_conflict_detected is False
    assert result.error_message is None


# ---------------------------------------------------------------------------
# Test 3 — Single active intake stage → CLEAR, primary = intake
# ---------------------------------------------------------------------------

def test_03_single_intake_stage():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u2",
        state_machine_result={
            "rehabilitation_state": "INITIAL_CONTACT",
            "escalation_gate": "clear",
            "progression_gate": "open",
            "stage_completion_score": 0.3,
            "stage_stall_detected": False,
        },
    ))
    from multi_stage_orchestration_engine import OrchestrationState, OrchestrationAction
    assert result.orchestration_state == OrchestrationState.CLEAR
    assert result.current_primary_stage == "intake"
    assert result.active_stage_count == 1
    assert result.next_orchestration_action == OrchestrationAction.PROCEED_PRIMARY
    assert result.error_message is None


# ---------------------------------------------------------------------------
# Test 4 — intake + diagnostic both active → MULTI_ACTIVE, primary = intake
# ---------------------------------------------------------------------------

def test_04_multi_active_intake_diagnostic():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u3",
        state_machine_result={
            "rehabilitation_state": "INITIAL_CONTACT",
            "escalation_gate": "clear",
            "progression_gate": "open",
            "stage_completion_score": 0.4,
            "stage_stall_detected": False,
        },
        continuity_result={"active_stage": "diagnostic"},
    ))
    from multi_stage_orchestration_engine import OrchestrationState, OrchestrationAction
    assert result.orchestration_state == OrchestrationState.MULTI_ACTIVE
    assert result.current_primary_stage == "intake"  # weight 1.0 > 0.9
    assert "diagnostic" in result.waiting_stages
    assert result.active_stage_count == 2
    assert result.next_orchestration_action == OrchestrationAction.WAIT_SECONDARY


# ---------------------------------------------------------------------------
# Test 5 — intervention + continuity both active → MULTI_ACTIVE, primary = intervention
# ---------------------------------------------------------------------------

def test_05_multi_active_intervention_continuity():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u4",
        state_machine_result={
            "rehabilitation_state": "TREATMENT_ACTIVE",
            "escalation_gate": "clear",
            "progression_gate": "open",
            "stage_completion_score": 0.6,
            "stage_stall_detected": False,
        },
        continuity_result={"active_stage": "continuity"},
    ))
    from multi_stage_orchestration_engine import OrchestrationState
    assert result.orchestration_state == OrchestrationState.MULTI_ACTIVE
    assert result.current_primary_stage == "intervention"  # weight 0.8 > 0.6


# ---------------------------------------------------------------------------
# Test 6 — escalation gate active + active stage → CONFLICT
# ---------------------------------------------------------------------------

def test_06_escalation_gate_active_conflict():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u5",
        state_machine_result={
            "rehabilitation_state": "NEEDS_ASSESSMENT",
            "escalation_gate": "active",
            "progression_gate": "open",
            "stage_completion_score": 0.2,
            "stage_stall_detected": False,
        },
    ))
    from multi_stage_orchestration_engine import OrchestrationState
    assert result.orchestration_state == OrchestrationState.CONFLICT
    assert result.stage_conflict_detected is True


# ---------------------------------------------------------------------------
# Test 7 — TREATMENT_ACTIVE + pre-treatment stage active → clinical skip conflict
# ---------------------------------------------------------------------------

def test_07_clinical_skip_conflict():
    engine = make_engine()
    # TREATMENT_ACTIVE with a diagnostic stage also active from continuity
    result = run(engine.evaluate_orchestration(
        user_id="u6",
        state_machine_result={
            "rehabilitation_state": "TREATMENT_ACTIVE",
            "escalation_gate": "clear",
            "progression_gate": "open",
            "stage_completion_score": 0.5,
            "stage_stall_detected": False,
        },
        continuity_result={"active_stage": "intake"},
    ))
    from multi_stage_orchestration_engine import OrchestrationState
    assert result.stage_conflict_detected is True
    assert result.orchestration_state == OrchestrationState.CONFLICT


# ---------------------------------------------------------------------------
# Test 8 — stage_stall + escalation_gate active → conflict
# ---------------------------------------------------------------------------

def test_08_stall_plus_escalation_conflict():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u7",
        state_machine_result={
            "rehabilitation_state": "CONSULTATION_ACTIVE",
            "escalation_gate": "active",
            "progression_gate": "open",
            "stage_completion_score": 0.3,
            "stage_stall_detected": True,
        },
    ))
    assert result.stage_conflict_detected is True


# ---------------------------------------------------------------------------
# Test 9 — active_stage_count=4 → overload_score ≥ 0.70 → OVERLOADED
# ---------------------------------------------------------------------------

def test_09_overloaded_state():
    engine = make_engine()
    # Force overload by mocking the overload compute
    score = engine._compute_overload_score(
        active_stage_count=4,
        stage_conflict_detected=True,
        escalation_gate="active",
        stage_stall=True,
    )
    # 4/4*0.40 + 1*0.25 + 1*0.20 + 1*0.15 = 0.40+0.25+0.20+0.15 = 1.00
    assert score >= 0.70
    assert score <= 1.0


# ---------------------------------------------------------------------------
# Test 10 — handoff_ready conditions all met → HANDOFF_READY
# ---------------------------------------------------------------------------

def test_10_handoff_ready():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u8",
        state_machine_result={
            "rehabilitation_state": "INITIAL_CONTACT",
            "escalation_gate": "clear",
            "progression_gate": "open",
            "stage_completion_score": 0.92,  # >= 0.85
            "stage_stall_detected": False,
        },
    ))
    from multi_stage_orchestration_engine import OrchestrationState, OrchestrationAction
    assert result.handoff_ready is True
    assert result.orchestration_state == OrchestrationState.HANDOFF_READY
    assert result.next_orchestration_action == OrchestrationAction.TRIGGER_HANDOFF


# ---------------------------------------------------------------------------
# Test 11 — all stages blocked → BLOCKED
# ---------------------------------------------------------------------------

def test_11_all_blocked():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u9",
        state_machine_result={
            "rehabilitation_state": "NEEDS_ASSESSMENT",
            "escalation_gate": "clear",
            "progression_gate": "closed",  # blocks current stage
            "stage_completion_score": 0.4,
            "stage_stall_detected": False,
        },
    ))
    from multi_stage_orchestration_engine import OrchestrationState, OrchestrationAction
    assert result.orchestration_state == OrchestrationState.BLOCKED
    assert result.next_orchestration_action == OrchestrationAction.AWAIT_HUMAN


# ---------------------------------------------------------------------------
# Test 12 — human_escalation = True → neutral result
# ---------------------------------------------------------------------------

def test_12_human_escalation_guard():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u10",
        human_escalation=True,
    ))
    from multi_stage_orchestration_engine import OrchestrationState
    assert result.orchestration_state == OrchestrationState.UNKNOWN
    assert "human_escalation" in (result.orchestration_notes.get("neutral_reason") or "")


# ---------------------------------------------------------------------------
# Test 13 — silence_respected = True → neutral result
# ---------------------------------------------------------------------------

def test_13_silence_respected_guard():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u11",
        silence_respected=True,
    ))
    from multi_stage_orchestration_engine import OrchestrationState
    assert result.orchestration_state == OrchestrationState.UNKNOWN
    assert "silence_respected" in (result.orchestration_notes.get("neutral_reason") or "")


# ---------------------------------------------------------------------------
# Test 14 — recovery_policy_active = True → neutral result
# ---------------------------------------------------------------------------

def test_14_recovery_policy_guard():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u12",
        recovery_policy_active=True,
    ))
    from multi_stage_orchestration_engine import OrchestrationState
    assert result.orchestration_state == OrchestrationState.UNKNOWN
    assert "recovery_policy" in (result.orchestration_notes.get("neutral_reason") or "")


# ---------------------------------------------------------------------------
# Test 15 — exception inside evaluate → neutral result, no raise
# ---------------------------------------------------------------------------

def test_15_exception_returns_neutral():
    engine = make_engine()

    original = engine._extract_stages_from_context
    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure")
    engine._extract_stages_from_context = broken

    result = run(engine.evaluate_orchestration(user_id="u13"))
    from multi_stage_orchestration_engine import OrchestrationState
    assert result.orchestration_state == OrchestrationState.UNKNOWN
    assert result.error_message is not None
    assert "simulated failure" in result.error_message


# ---------------------------------------------------------------------------
# Test 16 — overload score formula verification
# ---------------------------------------------------------------------------

def test_16_overload_score_formula():
    engine = make_engine()
    # 2 active stages, no conflict, clear escalation, no stall
    score = engine._compute_overload_score(
        active_stage_count=2,
        stage_conflict_detected=False,
        escalation_gate="clear",
        stage_stall=False,
    )
    expected = min(2/4.0, 1.0) * 0.40  # = 0.20
    assert abs(score - expected) < 0.001

    # 4 stages, conflict, escalation, stall
    score_max = engine._compute_overload_score(4, True, "active", True)
    assert abs(score_max - 1.0) < 0.001


# ---------------------------------------------------------------------------
# Test 17 — primary stage determination
# ---------------------------------------------------------------------------

def test_17_primary_stage_weights():
    engine = make_engine()
    primary = engine._determine_primary_stage(["continuity", "intake", "diagnostic"])
    assert primary == "intake"  # highest weight 1.0

    primary2 = engine._determine_primary_stage(["continuity", "diagnostic"])
    assert primary2 == "diagnostic"  # weight 0.9 > 0.6


# ---------------------------------------------------------------------------
# Test 18 — waiting stages exclude primary
# ---------------------------------------------------------------------------

def test_18_waiting_stages():
    engine = make_engine()
    waiting = engine._determine_waiting_stages(["intake", "diagnostic", "continuity"], "intake")
    assert "intake" not in waiting
    assert "diagnostic" in waiting
    assert "continuity" in waiting


# ---------------------------------------------------------------------------
# Test 19 — stall_detected contributes to overload score
# ---------------------------------------------------------------------------

def test_19_stall_contributes_overload():
    engine = make_engine()
    score_no_stall = engine._compute_overload_score(1, False, "clear", False)
    score_with_stall = engine._compute_overload_score(1, False, "clear", True)
    assert score_with_stall > score_no_stall
    assert abs(score_with_stall - score_no_stall - 0.15) < 0.001


# ---------------------------------------------------------------------------
# Test 20 — progression_gate=closed → stage added to blocked_stages
# ---------------------------------------------------------------------------

def test_20_progression_gate_closed_blocked():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u14",
        state_machine_result={
            "rehabilitation_state": "ANALYSIS_REVIEW",
            "escalation_gate": "clear",
            "progression_gate": "closed",
            "stage_completion_score": 0.3,
            "stage_stall_detected": False,
        },
    ))
    assert "diagnostic" in result.blocked_stages
    assert result.active_stage_count == 0


# ---------------------------------------------------------------------------
# Test 21 — ESCALATION_NEEDED when overload=1.0 + conflict
# ---------------------------------------------------------------------------

def test_21_escalation_needed():
    engine = make_engine()
    from multi_stage_orchestration_engine import OrchestrationState, OrchestrationAction
    state = engine._determine_orchestration_state(
        active_stages=["intake"],
        blocked_stages=[],
        stage_conflict_detected=True,
        route_overload_score=1.0,
        handoff_ready=False,
        escalation_gate="active",
    )
    assert state == OrchestrationState.ESCALATION_NEEDED

    action = engine._determine_action(
        OrchestrationState.ESCALATION_NEEDED,
        route_overload_score=1.0,
        handoff_ready=False,
        waiting_stages=[],
    )
    assert action == OrchestrationAction.AWAIT_HUMAN


# ---------------------------------------------------------------------------
# Test 22 — orchestration_notes contains full reasoning chain
# ---------------------------------------------------------------------------

def test_22_notes_contain_reasoning():
    engine = make_engine()
    result = run(engine.evaluate_orchestration(
        user_id="u15",
        state_machine_result={
            "rehabilitation_state": "NEEDS_ASSESSMENT",
            "escalation_gate": "clear",
            "progression_gate": "open",
            "stage_completion_score": 0.4,
            "stage_stall_detected": False,
        },
        behaviour_result={"behaviour_score": 0.7},
        trajectory_result={"trajectory_score": 0.6},
        continuity_result={"continuity_score": 0.5},
    ))
    notes = result.orchestration_notes
    assert "evaluated_at" in notes
    assert "rehab_state" in notes
    assert "orchestration_state" in notes
    assert "overload_score" in notes
    assert "conflict_detected" in notes
    assert "next_action" in notes
    assert "behaviour_score" in notes
    assert "trajectory_score" in notes
    assert "continuity_score" in notes


# ---------------------------------------------------------------------------
# Run guard
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    tests = [
        test_01_singleton_idempotent,
        test_02_empty_stages_clear,
        test_03_single_intake_stage,
        test_04_multi_active_intake_diagnostic,
        test_05_multi_active_intervention_continuity,
        test_06_escalation_gate_active_conflict,
        test_07_clinical_skip_conflict,
        test_08_stall_plus_escalation_conflict,
        test_09_overloaded_state,
        test_10_handoff_ready,
        test_11_all_blocked,
        test_12_human_escalation_guard,
        test_13_silence_respected_guard,
        test_14_recovery_policy_guard,
        test_15_exception_returns_neutral,
        test_16_overload_score_formula,
        test_17_primary_stage_weights,
        test_18_waiting_stages,
        test_19_stall_contributes_overload,
        test_20_progression_gate_closed_blocked,
        test_21_escalation_needed,
        test_22_notes_contain_reasoning,
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

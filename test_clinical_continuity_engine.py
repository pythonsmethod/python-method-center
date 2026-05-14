# -*- coding: utf-8 -*-
"""
test_clinical_continuity_engine.py
Phase 3.7 — Clinical Continuity Intelligence

15 test scenarios covering all spec requirements.
Run with: pytest test_clinical_continuity_engine.py -v
"""

import asyncio
import pytest
from clinical_continuity_engine import (
    ClinicalContinuityEngine,
    ContinuityResult,
    ContinuityState,
    ContinuityAction,
    init_continuity_engine,
    get_continuity_engine,
    _neutral_result,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Synchronous runner for async tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


def make_engine() -> ClinicalContinuityEngine:
    return ClinicalContinuityEngine()


def base_ctx(**overrides) -> dict:
    """Minimal safe context package."""
    ctx = {
        "silence_respect": False,
        "human_escalation_required": False,
        "recovery_policy_blocked": False,
        "emotional_overload": False,
        "behaviour_low_intensity": False,
        "current_stage": "support_cycle",
        "previous_stage": "support_cycle",
        "last_completed_action": "session_completed",
        "next_expected_action": "follow_up_call",
        "days_since_last_progress": 3,
        "days_since_last_contact": 3,
        "user_is_waiting": False,
        "system_is_waiting": False,
        "expert_expected": False,
        "karen_expected": False,
        "analyses_incomplete": False,
        "data_collection_incomplete": False,
        "returned_after_pause": False,
        "repeated_unresolved_count": 0,
        "prior_escalation_pending": False,
        "cooldown_active": False,
        "payment_pending": False,
        "support_cycle_active": False,
    }
    ctx.update(overrides)
    return ctx


# ---------------------------------------------------------------------------
# Scenario 1: Stable active support cycle
# ---------------------------------------------------------------------------

def test_01_stable_support_cycle():
    """Stable active support cycle — continuity score high, no gaps."""
    engine = make_engine()
    ctx = base_ctx(support_cycle_active=True, days_since_last_progress=2)
    result = run(engine.evaluate_continuity(user_id=1001, context_package=ctx))
    assert isinstance(result, ContinuityResult)
    assert result.safe_to_continue is True
    assert result.continuity_score >= 0.80, f"Expected high score, got {result.continuity_score}"
    assert result.continuity_gap_detected is False
    assert result.recommended_action == ContinuityAction.NO_ACTION


# ---------------------------------------------------------------------------
# Scenario 2: User waiting for Karen — stable waiting
# ---------------------------------------------------------------------------

def test_02_waiting_for_karen_stable():
    """User waiting for Karen within 14 days — waiting_stable, no gap."""
    engine = make_engine()
    ctx = base_ctx(
        user_is_waiting=True,
        karen_expected=True,
        days_since_last_progress=7,
    )
    result = run(engine.evaluate_continuity(user_id=1002, context_package=ctx))
    assert result.safe_to_continue is True
    assert result.continuity_state == ContinuityState.EXPERT_REVIEW_PENDING
    assert result.continuity_gap_detected is False
    assert result.recommended_action == ContinuityAction.PREPARE_KAREN_REVIEW
    assert result.waiting_stability == "waiting_for_expert"


# ---------------------------------------------------------------------------
# Scenario 3: User waiting too long without clear next step
# ---------------------------------------------------------------------------

def test_03_waiting_too_long_unclear():
    """User waiting 22+ days without expert expected — waiting_unclear."""
    engine = make_engine()
    ctx = base_ctx(
        user_is_waiting=True,
        days_since_last_progress=22,
        expert_expected=False,
        karen_expected=False,
    )
    result = run(engine.evaluate_continuity(user_id=1003, context_package=ctx))
    assert result.safe_to_continue is True
    assert result.continuity_state == ContinuityState.WAITING_UNCLEAR
    assert result.continuity_score < 0.80
    assert result.recommended_action == ContinuityAction.PRESERVE_WAITING_STATE
    assert result.waiting_stability == "borderline"


# ---------------------------------------------------------------------------
# Scenario 4: Data collection incomplete
# ---------------------------------------------------------------------------

def test_04_data_collection_incomplete():
    """Data collection not complete — DATA_COLLECTION_INCOMPLETE state."""
    engine = make_engine()
    ctx = base_ctx(data_collection_incomplete=True, days_since_last_progress=5)
    result = run(engine.evaluate_continuity(user_id=1004, context_package=ctx))
    assert result.continuity_state == ContinuityState.DATA_COLLECTION_INCOMPLETE
    assert result.recommended_action == ContinuityAction.REQUEST_MISSING_DATA_VIA_DISPATCHER
    assert result.continuity_gap_detected is False


# ---------------------------------------------------------------------------
# Scenario 5: Analyses received but not escalated
# ---------------------------------------------------------------------------

def test_05_analyses_incomplete():
    """Analyses present but incomplete — ANALYSIS_PENDING state."""
    engine = make_engine()
    ctx = base_ctx(analyses_incomplete=True, days_since_last_progress=8)
    result = run(engine.evaluate_continuity(user_id=1005, context_package=ctx))
    assert result.continuity_state == ContinuityState.ANALYSIS_PENDING
    assert result.recommended_action == ContinuityAction.PRESERVE_WAITING_STATE
    assert result.continuity_gap_detected is False


# ---------------------------------------------------------------------------
# Scenario 6: Stage transition pending after payment
# ---------------------------------------------------------------------------

def test_06_stage_transition_fragile_after_payment():
    """Stage changed + payment pending = TRANSITION_FRAGILE."""
    engine = make_engine()
    ctx = base_ctx(
        previous_stage="consultation",
        current_stage="treatment_cycle",
        payment_pending=True,
    )
    result = run(engine.evaluate_continuity(user_id=1006, context_package=ctx))
    assert result.continuity_state == ContinuityState.TRANSITION_FRAGILE
    assert result.stage_transition_risk is True
    assert result.recommended_action == ContinuityAction.MARK_TRANSITION_PENDING
    assert result.escalation_hint is not None


# ---------------------------------------------------------------------------
# Scenario 7: User returned after one month
# ---------------------------------------------------------------------------

def test_07_returned_after_pause():
    """User returned after long pause — score partially recovered."""
    engine = make_engine()
    ctx = base_ctx(
        returned_after_pause=True,
        days_since_last_progress=35,
        days_since_last_contact=35,
    )
    result = run(engine.evaluate_continuity(user_id=1007, context_package=ctx))
    # Should detect gap but score slightly elevated due to re-engagement
    assert result.continuity_gap_detected is True
    assert result.continuity_score > 0.0  # partial recovery bonus applied


# ---------------------------------------------------------------------------
# Scenario 8: Repeated unresolved loop
# ---------------------------------------------------------------------------

def test_08_unresolved_loop():
    """3+ repeated unresolved questions — UNRESOLVED_LOOP state."""
    engine = make_engine()
    ctx = base_ctx(repeated_unresolved_count=3)
    result = run(engine.evaluate_continuity(user_id=1008, context_package=ctx))
    assert result.continuity_state == ContinuityState.UNRESOLVED_LOOP
    assert result.unresolved_loop is True
    assert result.recommended_action == ContinuityAction.PREPARE_HUMAN_REVIEW
    assert result.escalation_hint is not None


# ---------------------------------------------------------------------------
# Scenario 9: Silence respect active — must NOT recommend outreach
# ---------------------------------------------------------------------------

def test_09_silence_respect_blocks_continuity():
    """Silence respect overrides continuity logic — no outreach recommended."""
    engine = make_engine()
    ctx = base_ctx(silence_respect=True, days_since_last_progress=35)
    result = run(engine.evaluate_continuity(user_id=1009, context_package=ctx))
    assert result.safe_to_continue is False
    assert result.recommended_action == ContinuityAction.HOLD_DUE_TO_SILENCE_RESPECT
    # Must NOT recommend any form of outreach
    assert result.recommended_action != ContinuityAction.REQUEST_MISSING_DATA_VIA_DISPATCHER
    assert result.recommended_action != ContinuityAction.CLARIFY_NEXT_STEP


# ---------------------------------------------------------------------------
# Scenario 10: Human escalation active — must NOT override
# ---------------------------------------------------------------------------

def test_10_human_escalation_blocks_continuity():
    """Human escalation active — continuity engine defers entirely."""
    engine = make_engine()
    ctx = base_ctx(human_escalation_required=True)
    result = run(engine.evaluate_continuity(user_id=1010, context_package=ctx))
    assert result.safe_to_continue is False
    assert result.continuity_state == ContinuityState.NEEDS_HUMAN_REVIEW
    assert result.recommended_action == ContinuityAction.HOLD_DUE_TO_ESCALATION
    assert result.escalation_hint is not None
    # Must NOT suggest automated outreach
    assert result.recommended_action != ContinuityAction.REQUEST_MISSING_DATA_VIA_DISPATCHER


# ---------------------------------------------------------------------------
# Scenario 11: Recovery policy blocks contact
# ---------------------------------------------------------------------------

def test_11_recovery_policy_blocked():
    """Recovery policy blocks all contact — recommended_action is no_action."""
    engine = make_engine()
    ctx = base_ctx(recovery_policy_blocked=True, days_since_last_progress=25)
    result = run(engine.evaluate_continuity(user_id=1011, context_package=ctx))
    assert result.recommended_action == ContinuityAction.NO_ACTION


# ---------------------------------------------------------------------------
# Scenario 12: Adaptive behaviour says low intensity
# ---------------------------------------------------------------------------

def test_12_low_intensity_mode():
    """Low intensity mode — reduce message intensity recommended."""
    engine = make_engine()
    ctx = base_ctx(
        behaviour_low_intensity=True,
        days_since_last_contact=35,
        days_since_last_progress=35,
    )
    result = run(engine.evaluate_continuity(user_id=1012, context_package=ctx))
    assert result.recommended_action == ContinuityAction.REDUCE_MESSAGE_INTENSITY


# ---------------------------------------------------------------------------
# Scenario 13: Continuity gap detected
# ---------------------------------------------------------------------------

def test_13_continuity_gap_detected():
    """30+ days without progress and not waiting — CONTINUITY_GAP."""
    engine = make_engine()
    ctx = base_ctx(
        days_since_last_progress=31,
        days_since_last_contact=31,
        user_is_waiting=False,
        system_is_waiting=False,
    )
    result = run(engine.evaluate_continuity(user_id=1013, context_package=ctx))
    assert result.continuity_state == ContinuityState.CONTINUITY_GAP
    assert result.continuity_gap_detected is True
    assert result.continuity_score < 0.60


# ---------------------------------------------------------------------------
# Scenario 14: Continuity stable — no action
# ---------------------------------------------------------------------------

def test_14_stable_no_action():
    """All signals green — stable progression, no action needed."""
    engine = make_engine()
    ctx = base_ctx(
        support_cycle_active=False,
        days_since_last_progress=1,
        days_since_last_contact=1,
        current_stage="support_cycle",
        previous_stage="support_cycle",
        next_expected_action="next_session",
    )
    result = run(engine.evaluate_continuity(user_id=1014, context_package=ctx))
    assert result.continuity_state == ContinuityState.STABLE_PROGRESSION
    assert result.continuity_score >= 0.80
    assert result.continuity_gap_detected is False
    assert result.stage_transition_risk is False
    assert result.unresolved_loop is False
    assert result.recommended_action == ContinuityAction.NO_ACTION


# ---------------------------------------------------------------------------
# Scenario 15: Engine error — fallback returns neutral safe result
# ---------------------------------------------------------------------------

def test_15_engine_error_fallback():
    """Any engine exception returns neutral safe ContinuityResult."""
    engine = make_engine()
    # Pass a context that will cause a type error inside _evaluate_safe
    # by providing a non-numeric days_since_last_progress
    ctx = base_ctx(days_since_last_progress="not_a_number")
    result = run(engine.evaluate_continuity(user_id=1015, context_package=ctx))
    # Must always return a ContinuityResult — never crash
    assert isinstance(result, ContinuityResult)
    assert result.is_fallback is True
    assert result.safe_to_continue is True
    assert result.continuity_state == ContinuityState.STABLE_PROGRESSION
    assert result.recommended_action == ContinuityAction.NO_ACTION
    assert result.error_message is not None


# ---------------------------------------------------------------------------
# Additional: neutral_result helper
# ---------------------------------------------------------------------------

def test_neutral_result_is_safe():
    """_neutral_result() always returns a safe, non-pressuring result."""
    result = _neutral_result("test error")
    assert result.safe_to_continue is True
    assert result.is_fallback is True
    assert result.continuity_score == 0.75
    assert result.recommended_action == ContinuityAction.NO_ACTION
    assert result.continuity_gap_detected is False
    assert result.stage_transition_risk is False
    assert result.unresolved_loop is False


# ---------------------------------------------------------------------------
# Additional: singleton management
# ---------------------------------------------------------------------------

def test_singleton_init():
    """init_continuity_engine() is idempotent."""
    e1 = init_continuity_engine()
    e2 = init_continuity_engine()
    assert e1 is e2
    assert get_continuity_engine() is e1


# ---------------------------------------------------------------------------
# Additional: to_dict serialisation
# ---------------------------------------------------------------------------

def test_result_to_dict():
    """ContinuityResult.to_dict() returns complete serialisable structure."""
    result = _neutral_result()
    d = result.to_dict()
    required_keys = [
        "safe_to_continue", "continuity_state", "continuity_score",
        "continuity_gap_detected", "stage_transition_risk", "unresolved_loop",
        "waiting_stability", "recommended_action", "escalation_hint",
        "reason_codes", "metadata", "evaluated_at", "is_fallback", "error_message",
    ]
    for key in required_keys:
        assert key in d, f"Missing key in to_dict(): {key}"

# -*- coding: utf-8 -*-
# =============================================================================
# TESTS — Phase 3.9: Rehabilitation State Machine
# test_rehabilitation_state_machine.py
#
# 17 scenarios covering all states, transitions, gates, stall detection,
# governance overrides, fail-safe, and safety constraints.
# =============================================================================

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sm():
    """Return a fresh initialized RehabilitationStateMachine (no DB)."""
    from rehabilitation_state_machine import RehabilitationStateMachine
    sm = RehabilitationStateMachine.__new__(RehabilitationStateMachine)
    sm._initialized = True
    return sm


def profile_in_state(state: str, days_in_state: int = 1, **kwargs) -> dict:
    entered = (datetime.now(timezone.utc) - timedelta(days=days_in_state)).isoformat()
    return {"rehabilitation_state": state, "state_entered_at": entered, **kwargs}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Scenario 1 — New user: no state → defaults to INITIAL_CONTACT
# ---------------------------------------------------------------------------
def test_01_new_user_defaults_to_initial_contact():
    sm = make_sm()
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(user_id=1, profile={}))
    assert result.rehabilitation_state == "initial_contact"
    assert result.rehabilitation_stage == "intake"
    assert result.is_neutral_fallback is False
    assert result.error_message is None


# ---------------------------------------------------------------------------
# Scenario 2 — Forward transition NEEDS_ASSESSMENT → AWAITING_CONSULTATION
# ---------------------------------------------------------------------------
def test_02_forward_transition_allowed():
    sm = make_sm()
    profile = profile_in_state("needs_assessment", days_in_state=2)
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(
            user_id=1, profile=profile,
            requested_transition="awaiting_consultation",
        ))
    assert result.transition_blocked is False
    assert result.blocked_transition_reason == ""
    assert "awaiting_consultation" in result.next_allowed_states


# ---------------------------------------------------------------------------
# Scenario 3 — Blocked transition: INITIAL_CONTACT → TREATMENT_ACTIVE (skip)
# ---------------------------------------------------------------------------
def test_03_blocked_skip_transition():
    sm = make_sm()
    profile = profile_in_state("initial_contact")
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(
            user_id=1, profile=profile,
            requested_transition="treatment_active",
        ))
    assert result.transition_blocked is True
    assert result.blocked_transition_reason != ""
    assert "hard_blocked" in result.blocked_transition_reason or "transition_not_defined" in result.blocked_transition_reason


# ---------------------------------------------------------------------------
# Scenario 4 — Blocked transition: COMPLETED → any (journey over)
# ---------------------------------------------------------------------------
def test_04_completed_blocks_all_forward():
    sm = make_sm()
    profile = profile_in_state("completed")
    for target in ("needs_assessment", "treatment_active", "monitoring", "follow_up"):
        with patch.object(sm, '_persist_result', new_callable=AsyncMock):
            result = run(sm.evaluate_state(
                user_id=1, profile=profile,
                requested_transition=target,
            ))
        assert result.transition_blocked is True, f"Expected blocked for COMPLETED → {target}"


# ---------------------------------------------------------------------------
# Scenario 5 — Allowed regression: TREATMENT_ACTIVE → TREATMENT_PLANNING
# ---------------------------------------------------------------------------
def test_05_allowed_regression_low_completion():
    sm = make_sm()
    profile = profile_in_state("treatment_active")
    # Force low completion score by using minimal profile + empty signals
    with patch.object(sm, '_compute_completion_score', return_value=0.25):
        with patch.object(sm, '_persist_result', new_callable=AsyncMock):
            result = run(sm.evaluate_state(
                user_id=1, profile=profile,
                requested_transition="treatment_planning",
            ))
    assert result.transition_blocked is False


# ---------------------------------------------------------------------------
# Scenario 6 — Blocked regression: completion score too high
# ---------------------------------------------------------------------------
def test_06_regression_blocked_high_completion():
    sm = make_sm()
    profile = profile_in_state("treatment_active")
    with patch.object(sm, '_compute_completion_score', return_value=0.72):
        with patch.object(sm, '_persist_result', new_callable=AsyncMock):
            result = run(sm.evaluate_state(
                user_id=1, profile=profile,
                requested_transition="treatment_planning",
            ))
    assert result.transition_blocked is True
    assert "regression_blocked" in result.blocked_transition_reason


# ---------------------------------------------------------------------------
# Scenario 7 — Stall detected: AWAITING_CONSULTATION > 21 days
# ---------------------------------------------------------------------------
def test_07_stall_detected_awaiting_consultation():
    sm = make_sm()
    profile = profile_in_state("awaiting_consultation", days_in_state=25)
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(user_id=1, profile=profile))
    assert result.stage_stall_detected is True
    assert result.stall_days >= 25


# ---------------------------------------------------------------------------
# Scenario 8 — No stall: AWAITING_CONSULTATION within threshold
# ---------------------------------------------------------------------------
def test_08_no_stall_within_threshold():
    sm = make_sm()
    profile = profile_in_state("awaiting_consultation", days_in_state=5)
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(user_id=1, profile=profile))
    assert result.stage_stall_detected is False


# ---------------------------------------------------------------------------
# Scenario 9 — Progression gate closed: insufficient completion score
# ---------------------------------------------------------------------------
def test_09_progression_gate_closed():
    sm = make_sm()
    profile = profile_in_state("treatment_active")
    with patch.object(sm, '_compute_completion_score', return_value=0.20):
        with patch.object(sm, '_persist_result', new_callable=AsyncMock):
            result = run(sm.evaluate_state(user_id=1, profile=profile))
    assert result.progression_gate_status == "closed"


# ---------------------------------------------------------------------------
# Scenario 10 — Escalation gate flagged: stall detected
# ---------------------------------------------------------------------------
def test_10_escalation_gate_flagged_on_stall():
    sm = make_sm()
    profile = profile_in_state("awaiting_consultation", days_in_state=30)
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(user_id=1, profile=profile))
    assert result.escalation_gate_status in ("flagged", "active")


# ---------------------------------------------------------------------------
# Scenario 11 — LOST_TO_FOLLOW_UP: forward transitions blocked
# ---------------------------------------------------------------------------
def test_11_lost_to_follow_up_blocks_forward():
    sm = make_sm()
    profile = profile_in_state("lost_to_follow_up")
    for target in ("awaiting_consultation", "treatment_active", "monitoring", "completed"):
        with patch.object(sm, '_persist_result', new_callable=AsyncMock):
            result = run(sm.evaluate_state(
                user_id=1, profile=profile,
                requested_transition=target,
            ))
        assert result.transition_blocked is True, f"Expected blocked LOST_TO_FOLLOW_UP → {target}"
    # Escalation gate active
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(user_id=1, profile=profile))
    assert result.escalation_gate_status == "active"


# ---------------------------------------------------------------------------
# Scenario 12 — PAUSED: next_allowed_states contains resume-like states
# ---------------------------------------------------------------------------
def test_12_paused_state_has_universal_transitions():
    sm = make_sm()
    profile = profile_in_state("paused", previous_rehabilitation_state="treatment_active")
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(user_id=1, profile=profile))
    # Universal transitions should include completed and stalled
    assert "completed" in result.next_allowed_states or "stalled" in result.next_allowed_states


# ---------------------------------------------------------------------------
# Scenario 13 — Silence respect active: governance override
# ---------------------------------------------------------------------------
def test_13_silence_respect_override():
    sm = make_sm()
    result = run(sm.evaluate_state(
        user_id=1, profile={"rehabilitation_state": "treatment_active"},
        silence_respected=True,
    ))
    assert result.rehabilitation_state == "unknown"
    assert "silence_respect_active" in str(result.state_machine_notes)
    assert result.is_neutral_fallback is False


# ---------------------------------------------------------------------------
# Scenario 14 — Human escalation active: governance override
# ---------------------------------------------------------------------------
def test_14_human_escalation_override():
    sm = make_sm()
    result = run(sm.evaluate_state(
        user_id=1, profile={"rehabilitation_state": "treatment_active"},
        human_escalation=True,
    ))
    assert result.rehabilitation_state == "unknown"
    assert "human_escalation_active" in str(result.state_machine_notes)


# ---------------------------------------------------------------------------
# Scenario 15 — Recovery policy active: governance override
# ---------------------------------------------------------------------------
def test_15_recovery_policy_override():
    sm = make_sm()
    result = run(sm.evaluate_state(
        user_id=1, profile={"rehabilitation_state": "monitoring"},
        recovery_policy_active=True,
    ))
    assert result.rehabilitation_state == "unknown"
    assert "recovery_policy_active" in str(result.state_machine_notes)


# ---------------------------------------------------------------------------
# Scenario 16 — Engine exception: neutral fallback result
# ---------------------------------------------------------------------------
def test_16_engine_exception_returns_neutral_fallback():
    sm = make_sm()
    with patch.object(sm, '_resolve_current_state', side_effect=RuntimeError("forced error")):
        result = run(sm.evaluate_state(user_id=1, profile={}))
    assert result.is_neutral_fallback is True
    assert result.rehabilitation_state == "unknown"
    assert "forced error" in result.error_message


# ---------------------------------------------------------------------------
# Scenario 17 — Singleton idempotent init
# ---------------------------------------------------------------------------
def test_17_singleton_idempotent():
    import rehabilitation_state_machine as mod
    original = mod._state_machine
    mod._state_machine = None
    sm1 = run(mod.init_state_machine())
    sm2 = run(mod.init_state_machine())
    assert sm1 is sm2
    mod._state_machine = original  # cleanup


# ---------------------------------------------------------------------------
# Scenario 18 — Result never has outbound fields
# ---------------------------------------------------------------------------
def test_18_result_has_no_outbound_fields():
    from rehabilitation_state_machine import StateMachineResult
    result = StateMachineResult(user_id=1)
    for field in ('send_message', 'telegram_message', 'outbound_text',
                  'sendpulse_payload', 'dispatch_message'):
        assert not hasattr(result, field), f"Outbound field found: {field}"


# ---------------------------------------------------------------------------
# Scenario 19 — Transition map completeness: TREATMENT_PLANNING → TREATMENT_ACTIVE
# ---------------------------------------------------------------------------
def test_19_treatment_planning_to_treatment_active():
    sm = make_sm()
    profile = profile_in_state("treatment_planning")
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(
            user_id=1, profile=profile,
            requested_transition="treatment_active",
        ))
    assert result.transition_blocked is False
    assert result.rehabilitation_state == "treatment_planning"


# ---------------------------------------------------------------------------
# Scenario 20 — Stage mapping: TREATMENT_ACTIVE maps to 'intervention' stage
# ---------------------------------------------------------------------------
def test_20_stage_mapping_treatment_active():
    sm = make_sm()
    profile = profile_in_state("treatment_active")
    with patch.object(sm, '_persist_result', new_callable=AsyncMock):
        result = run(sm.evaluate_state(user_id=1, profile=profile))
    assert result.rehabilitation_stage == "intervention"

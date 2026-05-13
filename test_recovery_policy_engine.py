# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.3 — Proactive Engagement Governance
# Module: test_recovery_policy_engine.py
# Tests for RecoveryPolicyEngine
#
# Scenarios:
#   1. Explicit refusal — suppressed 72h
#   2. Cooldown active — DELAY returned
#   3. Payment hesitation — no pressure, context_reminder tone
#   4. Post-payment silence — post_payment_support tone
#   5. Emotional overload — suppressed 24h
#   6. Repeated failed recovery — SILENCE_RESPECT
#   7. Human escalation override — ESCALATE_HUMAN
#   8. Fallback safety if engine errors
#   9. Stop keyword detected — suppressed
#  10. All gates pass — ALLOW returned
# =============================================================================

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys, os

# Allow import from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recovery_policy_engine import (
    RecoveryPolicyEngine,
    UserContext,
    RiskProfile,
    RouteState,
    MemoryState,
    PolicyAction,
    ToneMode,
    RecoveryChannel,
    NextAction,
    STAGE_COOLDOWN_MINUTES,
)


def _now():
    return datetime.now(timezone.utc)


def _engine(pool=None):
    return RecoveryPolicyEngine(db_pool=pool)


def _default_ctx(**kw):
    return UserContext(user_id=12345, **kw)


def _default_risk(**kw):
    return RiskProfile(**kw)


def _default_route(**kw):
    return RouteState(**kw)


def _default_mem(**kw):
    return MemoryState(**kw)


# ---------------------------------------------------------------------------
# Scenario 1 — Explicit refusal
# ---------------------------------------------------------------------------
def test_explicit_refusal_suppresses():
    engine = _engine()
    ctx  = _default_ctx(explicit_refusal=True)
    risk = _default_risk()
    rt   = _default_route()
    mem  = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.SUPPRESS, f"Expected SUPPRESS, got {decision.action}"
    assert decision.cooldown_until is not None
    minutes = (decision.cooldown_until - _now()).total_seconds() / 60
    assert minutes > 4000, f"Expected 72h+ cooldown, got {minutes:.0f}min"
    assert decision.suppression_reason == "explicit_refusal"
    print("PASS: test_explicit_refusal_suppresses")


# ---------------------------------------------------------------------------
# Scenario 2 — Cooldown active
# ---------------------------------------------------------------------------
def test_cooldown_active_returns_delay():
    engine = _engine()
    # last_recovery_at = 10 minutes ago, cooldown for 'default' stage = 120 min
    ctx  = _default_ctx(last_recovery_at=_now() - timedelta(minutes=10))
    risk = _default_risk(risk_type="none", risk_level="low")
    rt   = _default_route()
    mem  = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.DELAY, f"Expected DELAY, got {decision.action}"
    assert decision.next_action == NextAction.WAIT
    print("PASS: test_cooldown_active_returns_delay")


# ---------------------------------------------------------------------------
# Scenario 3 — Payment hesitation — no pressure, correct tone
# ---------------------------------------------------------------------------
def test_payment_hesitation_no_pressure():
    engine = _engine()
    ctx  = _default_ctx(
        payment_status="pending",
        recovery_attempt_count=0,  # first attempt allowed
    )
    risk = _default_risk(
        risk_type="payment_hesitation_risk",
        risk_level="medium",
        current_risk_score=0.55,
    )
    rt  = _default_route()
    mem = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    # First attempt: ALLOW with context_reminder (not sales tone)
    assert decision.action == PolicyAction.ALLOW, f"Expected ALLOW, got {decision.action}"
    assert decision.tone_mode == ToneMode.CONTEXT_REMINDER, (
        f"Expected context_reminder, got {decision.tone_mode}"
    )
    assert decision.recovery_channel == RecoveryChannel.AI_MESSAGE
    print("PASS: test_payment_hesitation_no_pressure")


# ---------------------------------------------------------------------------
# Scenario 3b — Payment hesitation second attempt — pressure guard fires
# ---------------------------------------------------------------------------
def test_payment_hesitation_pressure_guard_on_second_attempt():
    engine = _engine()
    ctx  = _default_ctx(
        payment_status="pending",
        recovery_attempt_count=1,  # second attempt → pressure guard
    )
    risk = _default_risk(
        risk_type="payment_hesitation_risk",
        risk_level="medium",
    )
    rt  = _default_route()
    mem = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.SUPPRESS, f"Expected SUPPRESS, got {decision.action}"
    assert decision.suppression_reason == "payment_pressure_guard"
    print("PASS: test_payment_hesitation_pressure_guard_on_second_attempt")


# ---------------------------------------------------------------------------
# Scenario 4 — Post-payment silence
# ---------------------------------------------------------------------------
def test_post_payment_silence_correct_tone():
    engine = _engine()
    ctx  = _default_ctx(
        payment_status="paid",
        recovery_attempt_count=0,
    )
    risk = _default_risk(
        risk_type="post_payment_silence_risk",
        risk_level="medium",
    )
    rt  = _default_route()
    mem = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.ALLOW
    assert decision.tone_mode == ToneMode.POST_PAYMENT_SUPPORT
    print("PASS: test_post_payment_silence_correct_tone")


# ---------------------------------------------------------------------------
# Scenario 5 — Emotional overload — suppressed 24h
# ---------------------------------------------------------------------------
def test_emotional_overload_suppresses_24h():
    engine = _engine()
    ctx  = _default_ctx()
    risk = _default_risk(
        risk_type="emotional_overload_risk",
        risk_level="high",
    )
    rt  = _default_route()
    mem = _default_mem(emotional_spike_count=5)

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.SUPPRESS, f"Expected SUPPRESS, got {decision.action}"
    assert decision.suppression_reason == "emotional_overload"
    assert decision.cooldown_until is not None
    hours = (decision.cooldown_until - _now()).total_seconds() / 3600
    assert hours > 23, f"Expected 24h cooldown, got {hours:.1f}h"
    print("PASS: test_emotional_overload_suppresses_24h")


# ---------------------------------------------------------------------------
# Scenario 6 — Repeated failed recovery — SILENCE_RESPECT
# ---------------------------------------------------------------------------
def test_repeated_failed_recovery_silence_respect():
    engine = _engine()
    ctx  = _default_ctx(recovery_attempt_count=5)  # exceeds all max attempts
    risk = _default_risk(risk_type="recovery_failure_risk", risk_level="high")
    rt   = _default_route()
    mem  = _default_mem(recovery_ignored_count=4, irritation_signals=3)

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action in (PolicyAction.SILENCE_RESPECT, PolicyAction.SUPPRESS), (
        f"Expected SILENCE_RESPECT or SUPPRESS, got {decision.action}"
    )
    assert decision.silence_respect or decision.suppression_reason != ""
    print("PASS: test_repeated_failed_recovery_silence_respect")


# ---------------------------------------------------------------------------
# Scenario 7 — Human escalation override
# ---------------------------------------------------------------------------
def test_human_escalation_active_blocks_ai():
    engine = _engine()
    ctx  = _default_ctx(is_human_escalated=True)
    risk = _default_risk()
    rt   = _default_route(escalation_active=True)
    mem  = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.ESCALATE_HUMAN
    assert decision.human_escalation_required == True
    assert decision.recovery_channel == RecoveryChannel.HUMAN_AGENT
    assert decision.tone_mode == ToneMode.HUMAN_HANDOFF
    print("PASS: test_human_escalation_active_blocks_ai")


# ---------------------------------------------------------------------------
# Scenario 8 — Fallback safety: engine error → SUPPRESS
# ---------------------------------------------------------------------------
def test_engine_error_defaults_to_suppress():
    engine = _engine()
    # Pass a context object that will cause an AttributeError inside evaluate
    class BrokenContext:
        user_id = 99999
        # missing all other attributes — will raise AttributeError

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(
            BrokenContext(),  # type: ignore
            _default_risk(),
            _default_route(),
            _default_mem(),
        )
    )

    assert decision.action == PolicyAction.SUPPRESS, (
        f"Expected SUPPRESS on error, got {decision.action}"
    )
    assert "fail-safe" in decision.reason.lower() or "engine_error" in decision.suppression_reason
    print("PASS: test_engine_error_defaults_to_suppress")


# ---------------------------------------------------------------------------
# Scenario 9 — Stop keyword in recent messages
# ---------------------------------------------------------------------------
def test_stop_keyword_suppresses():
    engine = _engine()
    ctx  = _default_ctx(recent_messages=["not now", "leave me alone"])
    risk = _default_risk()
    rt   = _default_route()
    mem  = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.SUPPRESS, f"Expected SUPPRESS, got {decision.action}"
    assert decision.suppression_reason == "explicit_refusal"
    print("PASS: test_stop_keyword_suppresses")


# ---------------------------------------------------------------------------
# Scenario 10 — All gates clear — ALLOW
# ---------------------------------------------------------------------------
def test_all_gates_pass_allow():
    engine = _engine()
    ctx  = _default_ctx(
        payment_status="none",
        recovery_attempt_count=0,
        last_recovery_at=None,
        last_ai_message_at=None,
        is_human_escalated=False,
        route_lock_active=False,
        silence_respect=False,
        explicit_refusal=False,
        recent_messages=[],
    )
    risk = _default_risk(risk_type="abandonment_risk", risk_level="medium")
    rt   = _default_route(route_locked=False, escalation_active=False)
    mem  = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.ALLOW, f"Expected ALLOW, got {decision.action}"
    assert decision.recovery_channel == RecoveryChannel.AI_MESSAGE
    print("PASS: test_all_gates_pass_allow")


# ---------------------------------------------------------------------------
# Safety constants test
# ---------------------------------------------------------------------------
def test_safety_never_trigger_constants():
    from recovery_policy_engine import SAFETY_NEVER_TRIGGER
    required = {
        "medical_diagnosis", "payment_pressure", "emergency_override",
        "spam_recovery", "route_lock_bypass",
    }
    missing = required - SAFETY_NEVER_TRIGGER
    assert not missing, f"Missing safety constants: {missing}"
    print("PASS: test_safety_never_trigger_constants")


# ---------------------------------------------------------------------------
# PolicyAction constants test
# ---------------------------------------------------------------------------
def test_policy_action_constants():
    assert PolicyAction.ALLOW == "ALLOW"
    assert PolicyAction.DELAY == "DELAY"
    assert PolicyAction.SUPPRESS == "SUPPRESS"
    assert PolicyAction.ESCALATE_HUMAN == "ESCALATE_HUMAN"
    assert PolicyAction.SILENCE_RESPECT == "SILENCE_RESPECT"
    print("PASS: test_policy_action_constants")


# ---------------------------------------------------------------------------
# ToneMode never sales/pressure test
# ---------------------------------------------------------------------------
def test_tone_mode_never_sales():
    engine = _engine()
    banned_tones = {"sales", "urgency", "pressure", "aggressive"}
    all_tones = {
        ToneMode.SOFT_CHECKIN, ToneMode.CONTEXT_REMINDER,
        ToneMode.STATUS_CONFIRMATION, ToneMode.TRUST_REPAIR,
        ToneMode.POST_PAYMENT_SUPPORT, ToneMode.HUMAN_HANDOFF,
        ToneMode.SILENCE_RESPECT,
    }
    for tone in all_tones:
        for banned in banned_tones:
            assert banned not in tone, f"Banned tone word '{banned}' found in '{tone}'"
    print("PASS: test_tone_mode_never_sales")


# ---------------------------------------------------------------------------
# should_escalate_to_human test
# ---------------------------------------------------------------------------
def test_should_escalate_to_human():
    engine = _engine()

    # Should escalate: escalation_needed_risk flagged
    ctx  = _default_ctx()
    risk = _default_risk(risk_type="escalation_needed_risk", risk_level="high")
    mem  = _default_mem()

    result, reason = asyncio.get_event_loop().run_until_complete(
        engine.should_escalate_to_human(ctx, risk, mem)
    )
    assert result == True, f"Expected escalation, got False"
    assert "escalation_needed_risk" in reason
    print("PASS: test_should_escalate_to_human")


# ---------------------------------------------------------------------------
# Silence respect already set test
# ---------------------------------------------------------------------------
def test_silence_respect_flag_respected():
    engine = _engine()
    ctx  = _default_ctx(silence_respect=True)
    risk = _default_risk()
    rt   = _default_route()
    mem  = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.SILENCE_RESPECT
    assert decision.next_action == NextAction.MARK_SILENCE_RESPECT
    assert decision.silence_respect == True
    print("PASS: test_silence_respect_flag_respected")


# ---------------------------------------------------------------------------
# Route lock test
# ---------------------------------------------------------------------------
def test_route_lock_suppresses():
    engine = _engine()
    ctx  = _default_ctx(route_lock_active=True)
    risk = _default_risk()
    rt   = _default_route(route_locked=True)
    mem  = _default_mem()

    decision = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_recovery_policy(ctx, risk, rt, mem)
    )

    assert decision.action == PolicyAction.SUPPRESS
    assert decision.suppression_reason == "route_lock_active"
    print("PASS: test_route_lock_suppresses")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_explicit_refusal_suppresses,
        test_cooldown_active_returns_delay,
        test_payment_hesitation_no_pressure,
        test_payment_hesitation_pressure_guard_on_second_attempt,
        test_post_payment_silence_correct_tone,
        test_emotional_overload_suppresses_24h,
        test_repeated_failed_recovery_silence_respect,
        test_human_escalation_active_blocks_ai,
        test_engine_error_defaults_to_suppress,
        test_stop_keyword_suppresses,
        test_all_gates_pass_allow,
        test_safety_never_trigger_constants,
        test_policy_action_constants,
        test_tone_mode_never_sales,
        test_should_escalate_to_human,
        test_silence_respect_flag_respected,
        test_route_lock_suppresses,
    ]

    passed = 0
    failed = 0
    errors = []
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append(f"FAIL: {t.__name__}: {e}")
            print(f"FAIL: {t.__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    if errors:
        print("\nFailed tests:")
        for e in errors:
            print(f"  {e}")
    if failed == 0:
        print("ALL TESTS PASSED")

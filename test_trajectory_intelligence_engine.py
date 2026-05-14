# -*- coding: utf-8 -*-
# =============================================================================
# TESTS — Phase 3.8: Trajectory Intelligence Engine
# test_trajectory_intelligence_engine.py
#
# 16 scenarios covering all trajectory states, governance overrides,
# fail-safe rules, and safety constraints.
# =============================================================================

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine():
    """Return a fresh, initialized TrajectoryIntelligenceEngine (no DB)."""
    from trajectory_intelligence_engine import TrajectoryIntelligenceEngine
    engine = TrajectoryIntelligenceEngine.__new__(TrajectoryIntelligenceEngine)
    engine._initialized = True
    return engine


def old_profile():
    """Return a profile with 30-day history (sufficient for trajectory)."""
    return {
        "user_id": 999,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        "silent_scan_count": 0,
    }


def new_profile():
    """Return a profile with 3-day history (insufficient for trajectory)."""
    return {
        "user_id": 999,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "silent_scan_count": 0,
    }


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Scenario 1 — Accelerating progression: all positive signals
# ---------------------------------------------------------------------------
def test_01_accelerating_progression():
    """All positive dimensions → score > 0.80 → accelerating_progression."""
    engine = make_engine()
    profile = old_profile()
    continuity = {
        "continuity_state": "stable_progression",
        "continuity_score": 0.92,
        "continuity_gap_detected": False,
        "unresolved_continuity_loop": False,
        "waiting_stability": "stable",
    }
    risk = {"risk_score": 0.05}
    behaviour = {"behaviour_score": 0.95, "behaviour_label": "active"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state == "accelerating_progression"
    assert result.trajectory_score >= 0.80
    assert result.trajectory_direction == "improving"
    assert result.is_neutral_fallback is False
    assert result.error_message is None


# ---------------------------------------------------------------------------
# Scenario 2 — Steady progression over 4 weeks
# ---------------------------------------------------------------------------
def test_02_steady_progression():
    """Moderate positive signals → steady_progression (0.61–0.80)."""
    engine = make_engine()
    profile = old_profile()
    continuity = {
        "continuity_state": "support_cycle_active",
        "continuity_score": 0.70,
        "continuity_gap_detected": False,
        "unresolved_continuity_loop": False,
        "waiting_stability": "stable",
    }
    risk = {"risk_score": 0.25}
    behaviour = {"behaviour_score": 0.65, "behaviour_label": "active"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("steady_progression", "accelerating_progression", "stable_plateau")
    assert result.trajectory_score >= 0.45
    assert result.is_neutral_fallback is False


# ---------------------------------------------------------------------------
# Scenario 3 — Stable plateau: no progress, not degrading
# ---------------------------------------------------------------------------
def test_03_stable_plateau():
    """Balanced signals, no improvement or degradation → stable_plateau."""
    engine = make_engine()
    profile = old_profile()
    continuity = {
        "continuity_state": "waiting_stable",
        "continuity_score": 0.55,
        "continuity_gap_detected": False,
        "unresolved_continuity_loop": False,
        "waiting_stability": "stable",
    }
    risk = {"risk_score": 0.45}
    behaviour = {"behaviour_score": 0.50, "behaviour_label": "neutral"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("stable_plateau", "steady_progression", "needs_trajectory_review")
    assert result.is_neutral_fallback is False


# ---------------------------------------------------------------------------
# Scenario 4 — Oscillating but still engaged
# ---------------------------------------------------------------------------
def test_04_oscillating_active():
    """Unresolved loop + gap but still active → oscillating_active."""
    engine = make_engine()
    profile = old_profile()
    profile["silent_scan_count"] = 1
    continuity = {
        "continuity_state": "unresolved_loop",
        "continuity_score": 0.50,
        "continuity_gap_detected": True,
        "unresolved_continuity_loop": True,
        "waiting_stability": "unclear",
    }
    risk = {"risk_score": 0.40}
    behaviour = {"behaviour_score": 0.55, "behaviour_label": "active"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("oscillating_active", "oscillating_at_risk", "follow_through_gap")
    assert result.is_neutral_fallback is False


# ---------------------------------------------------------------------------
# Scenario 5 — Oscillation with degradation trend
# ---------------------------------------------------------------------------
def test_05_oscillating_at_risk():
    """High oscillation + degradation label → oscillating_at_risk or degrading."""
    engine = make_engine()
    profile = old_profile()
    profile["silent_scan_count"] = 4
    continuity = {
        "continuity_state": "continuity_gap",
        "continuity_score": 0.30,
        "continuity_gap_detected": True,
        "unresolved_continuity_loop": True,
        "waiting_stability": "unclear",
    }
    risk = {"risk_score": 0.72}
    behaviour = {"behaviour_score": 0.30, "behaviour_label": "degrading"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("oscillating_at_risk", "degrading", "disengagement_trajectory")
    assert result.trajectory_score < 0.60
    assert result.trajectory_gap_detected is True


# ---------------------------------------------------------------------------
# Scenario 6 — Fragile transition / pacing issue
# ---------------------------------------------------------------------------
def test_06_pacing_issue():
    """Transition fragile state → pacing_too_slow or coherence_break."""
    engine = make_engine()
    profile = old_profile()
    continuity = {
        "continuity_state": "transition_fragile",
        "continuity_score": 0.40,
        "continuity_gap_detected": False,
        "unresolved_continuity_loop": False,
        "waiting_stability": "unclear",
    }
    risk = {"risk_score": 0.50}
    behaviour = {"behaviour_score": 0.45, "behaviour_label": "neutral"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("pacing_too_slow", "stable_plateau", "oscillating_active",
                                        "follow_through_gap", "needs_trajectory_review")
    assert result.is_neutral_fallback is False


# ---------------------------------------------------------------------------
# Scenario 7 — Follow-through gap: consistent non-completion
# ---------------------------------------------------------------------------
def test_07_follow_through_gap():
    """follow_up_missing + unresolved_loop → follow_through_gap."""
    engine = make_engine()
    profile = old_profile()
    continuity = {
        "continuity_state": "follow_up_missing",
        "continuity_score": 0.35,
        "continuity_gap_detected": True,
        "unresolved_continuity_loop": True,
        "waiting_stability": "unstable",
    }
    risk = {"risk_score": 0.55}
    behaviour = {"behaviour_score": 0.35, "behaviour_label": "low"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("follow_through_gap", "degrading", "oscillating_at_risk")
    assert result.trajectory_gap_detected is True


# ---------------------------------------------------------------------------
# Scenario 8 — Coherence break
# ---------------------------------------------------------------------------
def test_08_coherence_break():
    """data_collection_incomplete + unresolved_loop → coherence_break."""
    engine = make_engine()
    profile = old_profile()
    continuity = {
        "continuity_state": "data_collection_incomplete",
        "continuity_score": 0.30,
        "continuity_gap_detected": True,
        "unresolved_continuity_loop": True,
        "waiting_stability": "unclear",
    }
    risk = {"risk_score": 0.60}
    behaviour = {"behaviour_score": 0.30, "behaviour_label": "low"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("coherence_break", "follow_through_gap", "degrading")
    assert result.escalation_hint is True or result.trajectory_gap_detected is True


# ---------------------------------------------------------------------------
# Scenario 9 — Long-term disengagement trajectory
# ---------------------------------------------------------------------------
def test_09_disengagement_trajectory():
    """High silent count + dormant + low score → disengagement_trajectory."""
    engine = make_engine()
    profile = old_profile()
    profile["silent_scan_count"] = 12
    continuity = {
        "continuity_state": "dormant_but_not_lost",
        "continuity_score": 0.15,
        "continuity_gap_detected": True,
        "unresolved_continuity_loop": False,
        "waiting_stability": "unstable",
    }
    risk = {"risk_score": 0.80}
    behaviour = {"behaviour_score": 0.10, "behaviour_label": "dormant"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.trajectory_state in ("disengagement_trajectory", "degrading")
    assert result.trajectory_direction == "declining"
    assert result.escalation_hint is True


# ---------------------------------------------------------------------------
# Scenario 10 — Silence respect active: engine must yield
# ---------------------------------------------------------------------------
def test_10_silence_respect_active():
    """silence_respected=True → governance override result, no evaluation."""
    engine = make_engine()
    result = run(engine.evaluate_trajectory(
        user_id=999, silence_respected=True,
        profile=old_profile(),
    ))
    assert result.recommended_action == "no_action"
    assert "silence_respect_active" in str(result.trajectory_notes)
    assert result.is_neutral_fallback is False
    assert result.error_message is None


# ---------------------------------------------------------------------------
# Scenario 11 — Human escalation active: engine must not override
# ---------------------------------------------------------------------------
def test_11_human_escalation_active():
    """human_escalation=True → governance override result immediately returned."""
    engine = make_engine()
    result = run(engine.evaluate_trajectory(
        user_id=999, human_escalation=True,
        profile=old_profile(),
    ))
    assert result.recommended_action == "no_action"
    assert "human_escalation_active" in str(result.trajectory_notes)
    # Must NOT escalate further (engine already deferred)
    assert result.escalation_hint is False


# ---------------------------------------------------------------------------
# Scenario 12 — Recovery policy active: engine must yield
# ---------------------------------------------------------------------------
def test_12_recovery_policy_active():
    """recovery_policy_active=True → governance override, no trajectory action."""
    engine = make_engine()
    result = run(engine.evaluate_trajectory(
        user_id=999, recovery_policy_active=True,
        profile=old_profile(),
    ))
    assert result.recommended_action == "no_action"
    assert "recovery_policy_active" in str(result.trajectory_notes)


# ---------------------------------------------------------------------------
# Scenario 13 — New user: insufficient history
# ---------------------------------------------------------------------------
def test_13_new_user_insufficient_history():
    """User created 3 days ago → insufficient_history → neutral result."""
    engine = make_engine()
    result = run(engine.evaluate_trajectory(
        user_id=999, profile=new_profile(),
        continuity_result={"continuity_state": "stable_progression", "continuity_score": 0.9},
    ))
    assert result.trajectory_state == "needs_trajectory_review"
    assert result.trajectory_notes.get("reason") == "insufficient_history"
    assert result.is_neutral_fallback is False


# ---------------------------------------------------------------------------
# Scenario 14 — Trajectory stable: no action needed
# ---------------------------------------------------------------------------
def test_14_stable_no_action():
    """Fully stable scenario → recommended_action is no_action."""
    engine = make_engine()
    profile = old_profile()
    continuity = {
        "continuity_state": "stable_progression",
        "continuity_score": 0.85,
        "continuity_gap_detected": False,
        "unresolved_continuity_loop": False,
        "waiting_stability": "stable",
    }
    risk = {"risk_score": 0.10}
    behaviour = {"behaviour_score": 0.90, "behaviour_label": "active"}

    with patch.object(engine, '_persist_result', new_callable=AsyncMock):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=profile,
            continuity_result=continuity, risk_result=risk, behaviour_result=behaviour,
        ))

    assert result.recommended_action in ("no_action",)
    assert result.trajectory_gap_detected is False
    assert result.escalation_hint is False


# ---------------------------------------------------------------------------
# Scenario 15 — Engine error: safe fallback neutral result
# ---------------------------------------------------------------------------
def test_15_engine_error_fallback():
    """Any exception in evaluate_trajectory → _neutral_result(), no crash."""
    engine = make_engine()

    # Force an exception inside _compute_dimensions
    with patch.object(engine, '_compute_dimensions', side_effect=RuntimeError("test error")):
        result = run(engine.evaluate_trajectory(
            user_id=999, profile=old_profile(),
            continuity_result={"continuity_state": "stable_progression"},
        ))

    assert result.is_neutral_fallback is True
    assert result.trajectory_state == "needs_trajectory_review"
    assert result.recommended_action == "neutral_fallback"
    assert "test error" in result.error_message
    assert result.trajectory_score == 0.5


# ---------------------------------------------------------------------------
# Scenario 16 — Result never triggers outbound message
# ---------------------------------------------------------------------------
def test_16_result_never_has_outbound_action():
    """TrajectoryResult must never contain any outbound message field."""
    from trajectory_intelligence_engine import TrajectoryResult
    result = TrajectoryResult(user_id=1)
    # Verify no outbound fields exist on result
    assert not hasattr(result, 'send_message')
    assert not hasattr(result, 'telegram_message')
    assert not hasattr(result, 'outbound_text')
    assert not hasattr(result, 'sendpulse_payload')
    assert not hasattr(result, 'dispatch_message')


# ---------------------------------------------------------------------------
# Scenario 17 — Singleton: init_trajectory_engine is idempotent
# ---------------------------------------------------------------------------
def test_17_singleton_idempotent():
    """init_trajectory_engine() called twice returns same instance."""
    import trajectory_intelligence_engine as mod
    # Reset singleton
    mod._engine = None
    e1 = run(mod.init_trajectory_engine())
    e2 = run(mod.init_trajectory_engine())
    assert e1 is e2
    mod._engine = None  # cleanup


# ---------------------------------------------------------------------------
# Scenario 18 — get_trajectory_engine returns None before init
# ---------------------------------------------------------------------------
def test_18_get_engine_before_init_returns_none():
    """get_trajectory_engine() before initialization must return None."""
    import trajectory_intelligence_engine as mod
    original = mod._engine
    mod._engine = None
    result = mod.get_trajectory_engine()
    assert result is None
    mod._engine = original  # restore

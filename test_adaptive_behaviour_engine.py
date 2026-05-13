"""
test_adaptive_behaviour_engine.py
Phase 3.6 -- Adaptive Behavioural Intelligence
Test suite: 10+ scenarios covering all critical paths.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from adaptive_behaviour_engine import (
    AdaptiveBehaviourEngine,
    BehaviourProfile,
    BehaviourClassification,
    AdaptationCategory,
    BehaviourDimensions,
    init_behaviour_engine,
    get_behaviour_engine,
    _neutral_profile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine() -> AdaptiveBehaviourEngine:
    return AdaptiveBehaviourEngine()


def make_user_context(**kwargs):
    base = {
        "user_id": "test_user_001",
        "current_stage": "onboarding_incomplete",
        "silence_respect": False,
        "explicit_refusal": False,
        "human_escalation_required": False,
        "route_lock": False,
        "trust_lock": False,
        "cooldown_active": False,
        "last_user_message_at": None,
        "ai_message_count": 3,
        "user_message_count": 5,
    }
    base.update(kwargs)
    return base


def make_memory_state(**kwargs):
    base = {
        "emotional_tone_history": ["neutral", "anxious", "neutral"],
        "escalation_history": [],
        "stage_transitions": ["intake", "onboarding_incomplete"],
        "trust_score": 0.5,
        "session_count": 3,
        "re_engagement_count": 1,
        "silence_period_count": 2,
        "behaviour_dimensions": {},
    }
    base.update(kwargs)
    return base


def make_risk_profile(**kwargs):
    base = {
        "risk_level": "low",
        "risk_score": 0.2,
        "risk_flags": [],
        "emotional_overload_detected": False,
    }
    base.update(kwargs)
    return base


def make_history(n=5, latency=3600):
    """Create interaction history with n user messages."""
    import time
    now = time.time()
    history = []
    for i in range(n):
        history.append({
            "timestamp": now - (n - i) * latency,
            "message_type": "user",
            "latency_seconds": latency,
            "emotional_tone": "neutral",
            "route": "ai",
            "stage": "onboarding_incomplete",
        })
    return history


# ---------------------------------------------------------------------------
# Test 1: cautious users get slower pacing recommendation
# ---------------------------------------------------------------------------
def test_cautious_user_gets_slower_pacing():
    engine = make_engine()
    user_ctx = make_user_context()
    # Simulate slow latency, low trust
    memory = make_memory_state(trust_score=0.1, session_count=10)
    risk = make_risk_profile()
    # Long latency history
    history = make_history(n=6, latency=72000)  # 20h avg latency

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert isinstance(profile, BehaviourProfile)
    assert profile.is_fallback is False
    # Should produce pacing decrease or overwhelm classification
    pacing_recs = [r for r in profile.adaptation_recommendations
                   if r.category == AdaptationCategory.PACING and r.direction == "decrease"]
    cautious_or_overwhelmed = profile.classification in (
        BehaviourClassification.CAUTIOUS_SLOW,
        BehaviourClassification.OVERWHELMED_FRAGMENTED,
        BehaviourClassification.RECOVERY_RESISTANT,
        BehaviourClassification.SILENT_OBSERVER,
    )
    assert cautious_or_overwhelmed or len(pacing_recs) > 0, (
        f"Expected cautious/overwhelmed classification or pacing-decrease recommendation. "
        f"Got: {profile.classification}, recs: {[r.category.value + ':' + r.direction for r in profile.adaptation_recommendations]}"
    )


# ---------------------------------------------------------------------------
# Test 2: overwhelmed users get reduced message density
# ---------------------------------------------------------------------------
def test_overwhelmed_user_gets_shorter_messages():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state(
        emotional_tone_history=["confused", "frustrated", "confused", "overwhelmed", "frustrated"],
        escalation_history=["e1", "e2", "e3"],
        session_count=5,
    )
    risk = make_risk_profile(risk_score=0.7, emotional_overload_detected=True)
    history = make_history(n=5)

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert not profile.is_fallback
    assert profile.dimensions.overwhelm_sensitivity is not None
    assert profile.dimensions.overwhelm_sensitivity > 0.5

    msg_length_recs = [r for r in profile.adaptation_recommendations
                       if r.category == AdaptationCategory.MESSAGE_LENGTH and r.direction == "decrease"]
    assert len(msg_length_recs) > 0, (
        f"Expected message_length decrease. Got recs: {[r.category.value+':'+r.direction for r in profile.adaptation_recommendations]}"
    )


# ---------------------------------------------------------------------------
# Test 3: analytical users get deeper explanations
# ---------------------------------------------------------------------------
def test_analytical_user_gets_deeper_explanation():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state(
        emotional_tone_history=["neutral"] * 10,
        trust_score=0.8,
        session_count=8,
        stage_transitions=["intake", "onboarding_incomplete"],  # few transitions = deliberate
    )
    risk = make_risk_profile(risk_score=0.1)
    history = make_history(n=8, latency=7200)

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert not profile.is_fallback
    depth_recs = [r for r in profile.adaptation_recommendations
                  if r.category == AdaptationCategory.EXPLANATION_DEPTH and r.direction == "increase"]
    analytical = profile.classification == BehaviourClassification.ANALYTICAL_REPETITIVE
    assert analytical or len(depth_recs) > 0, (
        f"Expected analytical classification or explanation depth increase. "
        f"Got: {profile.classification}"
    )


# ---------------------------------------------------------------------------
# Test 4: recovery-resistant users reduce reminder frequency
# ---------------------------------------------------------------------------
def test_recovery_resistant_reduces_reminder_frequency():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state(
        re_engagement_count=0,
        silence_period_count=5,
        trust_score=0.2,
        session_count=5,
    )
    risk = make_risk_profile(risk_score=0.5)
    # Very long latency history
    history = make_history(n=5, latency=86400)  # 24h avg latency

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert not profile.is_fallback
    reminder_recs = [r for r in profile.adaptation_recommendations
                     if r.category == AdaptationCategory.REMINDER_SPACING and r.direction == "increase"]
    assert len(reminder_recs) > 0, (
        f"Expected reminder_spacing increase for recovery-resistant user. "
        f"Got recs: {[r.category.value+':'+r.direction for r in profile.adaptation_recommendations]}"
    )


# ---------------------------------------------------------------------------
# Test 5: escalation-dependent users escalate earlier
# ---------------------------------------------------------------------------
def test_escalation_dependent_escalates_earlier():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state(
        escalation_history=["e1", "e2", "e3", "e4", "e5"],
        session_count=5,
        trust_score=0.3,
    )
    risk = make_risk_profile()
    history = make_history(n=5)

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert not profile.is_fallback
    escalation_recs = [r for r in profile.adaptation_recommendations
                       if r.category == AdaptationCategory.ESCALATION_TIMING and r.direction == "decrease"]
    dependent = profile.classification == BehaviourClassification.DEPENDENT_ON_HUMAN
    assert dependent or len(escalation_recs) > 0, (
        f"Expected dependent_on_human classification or earlier escalation recommendation. "
        f"Got: {profile.classification}"
    )


# ---------------------------------------------------------------------------
# Test 6: behavioural shift detection works
# ---------------------------------------------------------------------------
def test_behavioural_shift_detection():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state(
        # Previous dimensions show high recovery responsiveness (0.8)
        behaviour_dimensions={
            "recovery_responsiveness": 0.8,
            "trust_building_speed": 0.7,
            "engagement_rhythm": 0.6,
        },
        re_engagement_count=0,   # Now zero re-engagements
        silence_period_count=5,
    )
    risk = make_risk_profile()
    history = make_history(n=5, latency=86400)

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert not profile.is_fallback
    # Should detect a shift in recovery_responsiveness (was 0.8, now close to 0.0)
    assert profile.shift_detected is True, "Expected shift_detected=True"
    shift_dims = [s.dimension for s in profile.detected_shifts]
    assert "recovery_responsiveness" in shift_dims, (
        f"Expected recovery_responsiveness shift. Shifts found: {shift_dims}"
    )


# ---------------------------------------------------------------------------
# Test 7: volatility score updates based on emotional variability
# ---------------------------------------------------------------------------
def test_volatility_score_reflects_emotional_variability():
    engine = make_engine()
    user_ctx = make_user_context()

    # High variability scenario
    memory_volatile = make_memory_state(
        emotional_tone_history=["happy", "angry", "confused", "anxious", "calm", "frustrated"],
        trust_score=0.3,
    )
    risk_volatile = make_risk_profile(risk_score=0.8, emotional_overload_detected=True)
    history = make_history(n=5)

    profile_volatile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory_volatile, risk_volatile, history)
    )

    # Low variability scenario
    memory_stable = make_memory_state(
        emotional_tone_history=["neutral"] * 6,
        trust_score=0.8,
    )
    risk_stable = make_risk_profile(risk_score=0.1)

    profile_stable = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory_stable, risk_stable, history)
    )

    assert not profile_volatile.is_fallback
    assert not profile_stable.is_fallback
    assert profile_volatile.volatility_score > profile_stable.volatility_score, (
        f"Volatile profile ({profile_volatile.volatility_score}) should have higher "
        f"volatility than stable ({profile_stable.volatility_score})"
    )


# ---------------------------------------------------------------------------
# Test 8: adaptation NEVER increases pressure, urgency, or persuasion
# ---------------------------------------------------------------------------
def test_adaptation_never_increases_pressure():
    engine = make_engine()
    FORBIDDEN_CATEGORIES_INCREASE = {
        # These would increase pressure — must NEVER appear with direction="increase"
        # Pacing increase is allowed only for HIGH_TRUST_FAST (minor magnitude)
        # Reminder spacing should never decrease (would increase contact frequency)
    }
    FORBIDDEN_DIRECTION = "decrease"
    FORBIDDEN_REMINDER_SPACING_DIRECTION = "decrease"

    # Test across multiple behaviour profiles
    scenarios = [
        {"memory": make_memory_state(emotional_tone_history=["anxious"] * 5, trust_score=0.1),
         "risk": make_risk_profile(risk_score=0.9, emotional_overload_detected=True),
         "desc": "high risk emotional overload"},
        {"memory": make_memory_state(trust_score=0.5, session_count=3),
         "risk": make_risk_profile(risk_score=0.5),
         "desc": "medium risk"},
        {"memory": make_memory_state(re_engagement_count=0, silence_period_count=8),
         "risk": make_risk_profile(risk_score=0.6),
         "desc": "recovery resistant"},
    ]

    user_ctx = make_user_context()
    history = make_history(n=5)

    for scenario in scenarios:
        profile = asyncio.get_event_loop().run_until_complete(
            engine.evaluate_behaviour_profile(user_ctx, scenario["memory"], scenario["risk"], history)
        )
        assert not profile.is_fallback

        for rec in profile.adaptation_recommendations:
            # Reminder spacing must NEVER decrease (would = more frequent contact)
            assert not (rec.category == AdaptationCategory.REMINDER_SPACING and rec.direction == "decrease"), (
                f"Scenario '{scenario['desc']}': reminder spacing must never decrease "
                f"(would increase contact pressure). Got: {rec.direction}"
            )
            # Escalation timing should never increase beyond what's needed (no delay escalation)
            # Pacing increase must not have significant magnitude for non-high-trust users
            if rec.category == AdaptationCategory.PACING and rec.direction == "increase":
                assert rec.magnitude in ("minor",), (
                    f"Scenario '{scenario['desc']}': pacing increase magnitude must be 'minor'. "
                    f"Got: {rec.magnitude} for classification {profile.classification.value}"
                )


# ---------------------------------------------------------------------------
# Test 9: fail-safe returns neutral profile on error
# ---------------------------------------------------------------------------
def test_fail_safe_returns_neutral_profile():
    engine = make_engine()

    # Pass completely broken input
    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(
            user_context=None,  # Will cause AttributeError internally
            memory_state={},
            risk_profile={},
            interaction_history=[],
        )
    )

    assert isinstance(profile, BehaviourProfile)
    assert profile.is_fallback is True
    assert profile.classification == BehaviourClassification.NEUTRAL
    assert profile.confidence == 0.0
    assert profile.error_message is not None


# ---------------------------------------------------------------------------
# Test 10: orchestrator override preserved — engine only recommends
# ---------------------------------------------------------------------------
def test_engine_only_recommends_does_not_route():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state()
    risk = make_risk_profile()
    history = make_history(n=5)

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert not profile.is_fallback
    # BehaviourProfile has NO routing fields — it cannot change routes directly
    assert not hasattr(profile, "route"), "BehaviourProfile must not have a route field"
    assert not hasattr(profile, "next_stage"), "BehaviourProfile must not have a next_stage field"
    assert not hasattr(profile, "send_message"), "BehaviourProfile must not have a send_message field"
    # Adaptations are recommendations only
    for rec in profile.adaptation_recommendations:
        assert hasattr(rec, "rationale"), "Each recommendation must include a rationale"


# ---------------------------------------------------------------------------
# Test 11: neutral profile for insufficient interaction history
# ---------------------------------------------------------------------------
def test_neutral_classification_with_no_history():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state()
    risk = make_risk_profile()

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, interaction_history=[])
    )

    assert not profile.is_fallback
    assert profile.classification == BehaviourClassification.NEUTRAL
    assert profile.confidence <= 0.25


# ---------------------------------------------------------------------------
# Test 12: singleton initialisation
# ---------------------------------------------------------------------------
def test_singleton_init():
    engine1 = init_behaviour_engine()
    engine2 = init_behaviour_engine()
    assert engine1 is engine2, "init_behaviour_engine must return same singleton"

    gotten = get_behaviour_engine()
    assert gotten is engine1


# ---------------------------------------------------------------------------
# Test 13: high-trust fast user gets minimal pacing change
# ---------------------------------------------------------------------------
def test_high_trust_fast_user():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state(
        trust_score=0.95,
        session_count=2,
        emotional_tone_history=["positive"] * 8,
        re_engagement_count=3,
        silence_period_count=3,
        stage_transitions=["intake", "onboarding_incomplete", "data_collection_incomplete"],
    )
    risk = make_risk_profile(risk_score=0.05)
    history = make_history(n=8, latency=300)  # 5min avg latency

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    assert not profile.is_fallback
    # Should NOT produce aggressive reminders or heavy pacing decreases
    heavy_decreases = [r for r in profile.adaptation_recommendations
                       if r.direction == "decrease" and r.magnitude == "significant"]
    assert len(heavy_decreases) == 0, (
        f"High-trust fast user should not get significant decrease adaptations. "
        f"Got: {[(r.category.value, r.direction, r.magnitude) for r in heavy_decreases]}"
    )


# ---------------------------------------------------------------------------
# Test 14: BehaviourProfile.to_dict() serialises correctly
# ---------------------------------------------------------------------------
def test_profile_serialisation():
    engine = make_engine()
    user_ctx = make_user_context()
    memory = make_memory_state()
    risk = make_risk_profile()
    history = make_history(n=4)

    profile = asyncio.get_event_loop().run_until_complete(
        engine.evaluate_behaviour_profile(user_ctx, memory, risk, history)
    )

    d = profile.to_dict()
    assert "user_id" in d
    assert "classification" in d
    assert "dimensions" in d
    assert "confidence" in d
    assert "volatility_score" in d
    assert "adaptation_recommendations" in d
    assert "detected_shifts" in d
    assert "shift_detected" in d
    assert "last_updated_at" in d
    assert "is_fallback" in d
    assert isinstance(d["adaptation_recommendations"], list)
    assert isinstance(d["dimensions"], dict)


# ---------------------------------------------------------------------------
# Test 15: persist_profile skips fallback profiles
# ---------------------------------------------------------------------------
def test_persist_skips_fallback():
    engine = make_engine()
    fallback_profile = _neutral_profile(user_id="test", error="test error")
    assert fallback_profile.is_fallback is True

    mock_pool = MagicMock()
    result = asyncio.get_event_loop().run_until_complete(
        engine.persist_profile(mock_pool, fallback_profile)
    )
    assert result is False
    mock_pool.acquire.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

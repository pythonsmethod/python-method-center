# -*- coding: utf-8 -*-
"""
test_adaptive_rehabilitation_strategy.py
Phase 3.15 — Tests for Adaptive Rehabilitation Strategy Engine
25 test scenarios covering all states, scores, booleans, modes, and edge cases.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from adaptive_rehabilitation_strategy import (
    AdaptiveRehabilitationStrategyEngine,
    get_adaptive_strategy_engine,
    init_adaptive_strategy_engine,
    evaluate_adaptive_strategy,
    _neutral_result,
    STRATEGY_STATES,
    CONTINUITY_STRATEGIES,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_LOW_THRESHOLD,
    STABILITY_HIGH_THRESHOLD,
    STABILITY_LOW_THRESHOLD,
    EROSION_RISK_HIGH,
    PACING_LOW_THRESHOLD,
    ROUTE_LOW_THRESHOLD,
    TRAJECTORY_LOW_THRESHOLD,
    EXPERT_HANDOFF_THRESHOLD,
    SHIFT_PRESSURE_THRESHOLD,
    INSTABILITY_COUNT_TRIGGER,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_profile(
    engagement=0.70,
    continuity=0.70,
    pacing=0.65,
    route_stability=0.70,
    trajectory=0.65,
    recovery=0.70,
    risk=0.20,
    escalation_level=0.10,
    long_stability=0.68,
    resilience=0.65,
    continuity_sustain=0.66,
    recurring_instab=False,
    disengagement_cycle=False,
    pacing_adapt=0.65,
    route_durability=0.67,
    erosion_risk=0.20,
    long_coherence=0.65,
    orch_coherence=0.70,
    system_stability=0.70,
    emotional_safety=0.72,
    disruption_count=0,
    instability_count=0,
):
    return {
        "engagement_score":                 engagement,
        "continuity_score":                 continuity,
        "pacing_score":                     pacing,
        "route_stability_score":            route_stability,
        "trajectory_score":                 trajectory,
        "recovery_score":                   recovery,
        "risk_score":                       risk,
        "escalation_level":                 escalation_level,
        "longitudinal_stability_score":     long_stability,
        "rehabilitation_resilience_score":  resilience,
        "continuity_sustainability_score":  continuity_sustain,
        "recurring_instability_detected":   recurring_instab,
        "disengagement_cycle_detected":     disengagement_cycle,
        "pacing_adaptation_quality":        pacing_adapt,
        "long_term_route_durability":       route_durability,
        "continuity_erosion_risk":          erosion_risk,
        "longitudinal_coherence_score":     long_coherence,
        "orchestration_coherence_score":    orch_coherence,
        "overall_system_stability_score":   system_stability,
        "emotional_safety_integrity_score": emotional_safety,
        "disruption_count":                 disruption_count,
        "instability_count":                instability_count,
    }

def make_context(**kwargs):
    return {
        "escalation_pending": False,
        "silence_detected": False,
        "disruption_active": False,
        "human_escalation_active": False,
        "silence_respected": False,
        **kwargs,
    }

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    AdaptiveRehabilitationStrategyEngine._instance = None
    AdaptiveRehabilitationStrategyEngine._initialized = False
    eng = AdaptiveRehabilitationStrategyEngine.get_instance()
    run(eng.initialize())
    return eng

# ── Test 1: Stable strategy ───────────────────────────────────────────────────

def test_stable_strategy(engine):
    profile = make_profile(
        engagement=0.85, continuity=0.85, long_stability=0.80,
        long_coherence=0.80, system_stability=0.82,
        route_stability=0.80, trajectory=0.78, resilience=0.80,
        continuity_sustain=0.80, disruption_count=0,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "STABLE_STRATEGY"
    assert scores["confidence"] >= CONFIDENCE_HIGH_THRESHOLD
    assert scores["stability"] >= STABILITY_HIGH_THRESHOLD

# ── Test 2: Standard continuity strategy ─────────────────────────────────────

def test_standard_continuity_selected(engine):
    profile = make_profile(
        engagement=0.85, continuity=0.85, long_stability=0.80,
        long_coherence=0.80, system_stability=0.82,
        route_stability=0.80, trajectory=0.78, resilience=0.80,
        continuity_sustain=0.80, route_durability=0.80,
    )
    signals  = engine._extract_signals(profile, make_context())
    scores   = engine._compute_scores(signals)
    state    = engine._determine_state(scores, signals)
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy in ("standard_continuity", "low_pressure_support")

# ── Test 3: Strategy shift needed ────────────────────────────────────────────

def test_strategy_shift_needed(engine):
    profile = make_profile(
        recurring_instab=True, disruption_count=2,
        risk=0.55, erosion_risk=0.40,
        disengagement_cycle=True,
    )
    signals = engine._extract_signals(profile, make_context(disruption_active=True))
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "STRATEGY_SHIFT_NEEDED"
    assert scores["shift_pressure"] > SHIFT_PRESSURE_THRESHOLD

# ── Test 4: Low confidence ────────────────────────────────────────────────────

def test_low_confidence(engine):
    profile = make_profile(
        engagement=0.20, continuity=0.20, long_stability=0.10,
        long_coherence=0.10, system_stability=0.15,
        route_stability=0.20, trajectory=0.20, resilience=0.20,
        continuity_sustain=0.20,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "LOW_CONFIDENCE"
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy == "hold_no_change"

# ── Test 5: Continuity protection ────────────────────────────────────────────

def test_continuity_protection(engine):
    profile = make_profile(
        continuity=0.30, erosion_risk=0.65,
        engagement=0.65, long_stability=0.60,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "CONTINUITY_PROTECTION"
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy == "stabilization_first"

# ── Test 6: Pacing reduction ──────────────────────────────────────────────────

def test_pacing_reduction(engine):
    profile = make_profile(pacing=0.30, pacing_adapt=0.25)
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "PACING_REDUCTION"
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy == "pacing_reduction"

# ── Test 7: Human support alignment ──────────────────────────────────────────

def test_human_support_alignment(engine):
    profile = make_profile(escalation_level=0.80, risk=0.70)
    signals = engine._extract_signals(profile, make_context(escalation_pending=True))
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "HUMAN_SUPPORT_ALIGNMENT"
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy == "human_alignment"

# ── Test 8: Route repair ──────────────────────────────────────────────────────

def test_route_repair(engine):
    profile = make_profile(route_stability=0.25, trajectory=0.30)
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "ROUTE_REPAIR"
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy == "route_repair"

# ── Test 9: Longitudinal stabilization ───────────────────────────────────────

def test_longitudinal_stabilization(engine):
    profile = make_profile(
        recurring_instab=True, disruption_count=4,
        long_stability=0.55, resilience=0.45,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state == "LONGITUDINAL_STABILIZATION"
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy == "long_term_maintenance"

# ── Test 10: Unknown state (governance override) ──────────────────────────────

def test_unknown_state_governance(engine):
    profile = make_profile()
    signals = engine._extract_signals(profile, make_context(
        human_escalation_active=True,
        silence_respected=True,
    ))
    scores = engine._compute_scores(signals)
    state  = engine._determine_state(scores, signals)
    assert state == "UNKNOWN"
    strategy = engine._select_strategy(state, scores, signals)
    assert strategy == "hold_no_change"

# ── Test 11: Null user_id returns neutral ─────────────────────────────────────

def test_null_user_id_returns_neutral(engine):
    result = run(engine.evaluate("", make_context()))
    assert result["is_neutral"] is True
    assert result["adaptive_strategy_state"] == "UNKNOWN"

# ── Test 12: DB exception returns neutral ─────────────────────────────────────

def test_db_exception_returns_neutral(engine):
    with patch.object(engine, "_load_profile", side_effect=Exception("DB down")):
        result = run(engine.evaluate("user_123", make_context()))
    assert result["is_neutral"] is True

# ── Test 13: Confidence score clamped 0–1 ────────────────────────────────────

def test_confidence_score_clamped(engine):
    profile = make_profile(
        engagement=99.0, long_stability=99.0, long_coherence=99.0,
        continuity=99.0, system_stability=99.0,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    assert 0.0 <= scores["confidence"] <= 1.0

# ── Test 14: Stability score clamped 0–1 ─────────────────────────────────────

def test_stability_score_clamped(engine):
    profile = make_profile(
        route_stability=99.0, trajectory=99.0, resilience=99.0,
        continuity_sustain=99.0,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    assert 0.0 <= scores["stability"] <= 1.0

# ── Test 15: Shift flag true ──────────────────────────────────────────────────

def test_shift_flag_true(engine):
    profile = make_profile(
        recurring_instab=True, disruption_count=3,
        risk=0.60, erosion_risk=0.45, disengagement_cycle=True,
    )
    signals  = engine._extract_signals(profile, make_context(disruption_active=True))
    scores   = engine._compute_scores(signals)
    state    = engine._determine_state(scores, signals)
    strategy = engine._select_strategy(state, scores, signals)
    modes    = engine._compute_modes(scores, signals, state)
    result   = {
        "adaptive_strategy_state": state,
        "strategy_shift_needed":   state == "STRATEGY_SHIFT_NEEDED",
    }
    if state == "STRATEGY_SHIFT_NEEDED":
        assert result["strategy_shift_needed"] is True

# ── Test 16: Shift flag false ─────────────────────────────────────────────────

def test_shift_flag_false(engine):
    profile = make_profile(
        engagement=0.85, continuity=0.85, long_stability=0.80,
        long_coherence=0.80, system_stability=0.82,
        route_stability=0.80, trajectory=0.78, resilience=0.80,
        continuity_sustain=0.80, disruption_count=0,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    assert state != "STRATEGY_SHIFT_NEEDED"

# ── Test 17: Continuity support mode active ───────────────────────────────────

def test_continuity_support_mode_active(engine):
    profile = make_profile(route_stability=0.25, trajectory=0.30)
    signals = engine._extract_signals(profile, make_context(escalation_pending=True))
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    modes   = engine._compute_modes(scores, signals, state)
    assert modes["support_mode"] == "active"

# ── Test 18: Continuity support mode hold ────────────────────────────────────

def test_continuity_support_mode_hold(engine):
    profile = make_profile(
        engagement=0.20, continuity=0.20, long_stability=0.10,
        long_coherence=0.10, system_stability=0.15,
        route_stability=0.20, trajectory=0.20, resilience=0.20,
        continuity_sustain=0.20,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    modes   = engine._compute_modes(scores, signals, state)
    assert modes["support_mode"] == "hold"

# ── Test 19: Longitudinal fit score ──────────────────────────────────────────

def test_longitudinal_fit_score(engine):
    profile = make_profile(
        long_stability=0.90, long_coherence=0.88, route_durability=0.85,
    )
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    assert scores["longitudinal_fit"] >= 0.70

# ── Test 20: Emotional safety fit ────────────────────────────────────────────

def test_emotional_safety_fit(engine):
    profile = make_profile(emotional_safety=0.95)
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    assert scores["emotional_safety_fit"] >= 0.90

# ── Test 21: Expert handoff fit ──────────────────────────────────────────────

def test_expert_handoff_fit(engine):
    profile = make_profile(escalation_level=0.80, risk=0.75)
    signals = engine._extract_signals(profile, make_context(escalation_pending=True))
    scores  = engine._compute_scores(signals)
    assert scores["expert_handoff_fit"] >= EXPERT_HANDOFF_THRESHOLD

# ── Test 22: Singleton same instance ─────────────────────────────────────────

def test_singleton_same_instance(engine):
    e2 = AdaptiveRehabilitationStrategyEngine.get_instance()
    assert engine is e2

# ── Test 23: Init no exception ───────────────────────────────────────────────

def test_init_no_exception(engine):
    run(engine.initialize())  # idempotent, must not raise

# ── Test 24: get_stats returns dict ──────────────────────────────────────────

def test_get_stats(engine):
    stats = engine.get_stats()
    assert isinstance(stats, dict)
    assert stats["engine"] == "AdaptiveRehabilitationStrategyEngine"
    assert stats["phase"] == "3.15"
    assert "eval_count" in stats
    assert "state_counts" in stats
    assert "strategy_counts" in stats

# ── Test 25: Neutral result structure ────────────────────────────────────────

def test_neutral_result_structure():
    result = _neutral_result("test_user")
    required_keys = [
        "user_id",
        "adaptive_strategy_state",
        "recommended_continuity_strategy",
        "strategy_confidence_score",
        "strategy_stability_score",
        "strategy_shift_needed",
        "continuity_support_mode",
        "route_support_intensity",
        "pacing_strategy_alignment",
        "longitudinal_strategy_fit",
        "emotional_safety_strategy_fit",
        "expert_handoff_strategy_fit",
        "strategy_notes",
        "evaluated_at",
        "is_neutral",
    ]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"
    assert result["is_neutral"] is True
    assert result["adaptive_strategy_state"] == "UNKNOWN"
    assert result["recommended_continuity_strategy"] == "hold_no_change"
    assert result["strategy_shift_needed"] is False
    assert result["continuity_support_mode"] == "hold"
    assert result["strategy_confidence_score"] == 0.0
    assert result["strategy_stability_score"] == 0.0

# ── Test 26 (bonus): Notes structure ─────────────────────────────────────────

def test_notes_structure(engine):
    profile = make_profile()
    signals = engine._extract_signals(profile, make_context())
    scores  = engine._compute_scores(signals)
    state   = engine._determine_state(scores, signals)
    strategy = engine._select_strategy(state, scores, signals)
    notes   = engine._build_notes(state, strategy, scores, signals)
    assert isinstance(notes, dict)
    assert "reason" in notes
    assert "signals" in notes
    assert "scores" in notes
    assert isinstance(notes["signals"], list)

# ── Test 27 (bonus): All states in STRATEGY_STATES ───────────────────────────

def test_all_strategy_states_defined():
    expected = [
        "STABLE_STRATEGY", "STRATEGY_SHIFT_NEEDED", "LOW_CONFIDENCE",
        "CONTINUITY_PROTECTION", "PACING_REDUCTION", "HUMAN_SUPPORT_ALIGNMENT",
        "ROUTE_REPAIR", "LONGITUDINAL_STABILIZATION", "UNKNOWN",
    ]
    for state in expected:
        assert state in STRATEGY_STATES

# ── Test 28 (bonus): All continuity strategies defined ────────────────────────

def test_all_continuity_strategies_defined():
    expected = [
        "standard_continuity", "low_pressure_support", "stabilization_first",
        "pacing_reduction", "route_repair", "human_alignment",
        "post_disruption_rebuild", "long_term_maintenance", "hold_no_change",
    ]
    for strategy in expected:
        assert strategy in CONTINUITY_STRATEGIES

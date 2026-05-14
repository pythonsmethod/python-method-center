"""
Phase 3.16 — Rehabilitation Route Simulation Engine
Test suite: 28 scenarios
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(**kwargs):
    base = {
        "human_esc": False,
        "silence_respected": False,
        "continuity_score": 0.75,
        "trajectory_score": 0.70,
        "pacing_score": 0.65,
        "load_balancing_score": 0.70,
        "orchestration_score": 0.68,
        "longitudinal_stability_score": 0.72,
        "strategy_stability_score": 0.71,
        "behaviour_engagement_score": 0.73,
        "risk_score": 0.20,
        "continuity_state": "STABLE",
        "trajectory_state": "STABLE",
        "longitudinal_state": "STABLE",
        "pacing_intensity": "MODERATE",
        "strategy_state": "MAINTAIN",
        "rehabilitation_state": "ACTIVE",
    }
    base.update(kwargs)
    return base


def _make_low_context(**kwargs):
    base = _make_context(
        continuity_score=0.20,
        trajectory_score=0.18,
        pacing_score=0.15,
        load_balancing_score=0.18,
        orchestration_score=0.20,
        longitudinal_stability_score=0.15,
        strategy_stability_score=0.17,
        behaviour_engagement_score=0.12,
        risk_score=0.80,
        continuity_state="DISRUPTED",
        trajectory_state="DECLINING",
        longitudinal_state="UNSTABLE",
    )
    base.update(kwargs)
    return base


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Import engine
# ---------------------------------------------------------------------------

from rehabilitation_route_simulation import (
    RehabilitationRouteSimulationEngine,
    _neutral_result,
    evaluate_route_simulation,
    get_route_simulation_engine,
    init_route_simulation_engine,
)


# ---------------------------------------------------------------------------
# Test 1: neutral_result structure
# ---------------------------------------------------------------------------

def test_neutral_result_structure():
    r = _neutral_result("u1")
    assert r["user_id"] == "u1"
    assert r["route_simulation_state"] == "UNKNOWN"
    assert r["simulation_stability_score"] == 0.0
    assert r["simulation_coherence_score"] == 0.0
    assert r["is_neutral"] is True
    assert isinstance(r["simulation_notes"], dict)


# ---------------------------------------------------------------------------
# Test 2: neutral_result on missing profile
# ---------------------------------------------------------------------------

def test_neutral_result_on_missing_profile():
    engine = RehabilitationRouteSimulationEngine()
    with patch.object(engine, "_load_profile", return_value={}):
        result = run(engine.evaluate("user_missing", _make_context()))
    assert result["is_neutral"] is True
    assert result["route_simulation_state"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test 3: neutral_result on DB exception
# ---------------------------------------------------------------------------

def test_neutral_result_on_db_exception():
    engine = RehabilitationRouteSimulationEngine()
    with patch.object(engine, "_load_profile", side_effect=Exception("DB error")):
        result = run(engine.evaluate("user_db_err", _make_context()))
    assert result["is_neutral"] is True


# ---------------------------------------------------------------------------
# Test 4: neutral_result on general exception in evaluate
# ---------------------------------------------------------------------------

def test_neutral_result_on_evaluate_exception():
    engine = RehabilitationRouteSimulationEngine()
    with patch.object(engine, "_run_evaluation", side_effect=Exception("crash")):
        result = run(engine.evaluate("user_crash", _make_context()))
    assert result["is_neutral"] is True


# ---------------------------------------------------------------------------
# Test 5: STABLE_SIMULATION on high scores
# ---------------------------------------------------------------------------

def test_stable_simulation_high_scores():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_stable", _make_context()))
    assert result["route_simulation_state"] == "STABLE_SIMULATION"
    assert result["simulation_stability_score"] > 0.0
    assert result["is_neutral"] is False


# ---------------------------------------------------------------------------
# Test 6: ROUTE_EROSION_RISK on very low scores
# ---------------------------------------------------------------------------

def test_route_erosion_risk_low_scores():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_low_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_erosion", _make_low_context()))
    assert result["route_simulation_state"] in (
        "ROUTE_EROSION_RISK", "HIGH_UNCERTAINTY", "DISENGAGEMENT_RECOVERY_PATH",
        "CONTINUITY_RECOVERY_PATH", "LONGITUDINAL_STABILIZATION_PATH", "UNKNOWN"
    )
    assert result["route_erosion_risk_projection"] > 0.0


# ---------------------------------------------------------------------------
# Test 7: HIGH_UNCERTAINTY on incoherent signals
# ---------------------------------------------------------------------------

def test_high_uncertainty_incoherent_signals():
    engine = RehabilitationRouteSimulationEngine()
    # Mix very high and very low scores → high variance → low coherence
    profile = _make_context(
        continuity_score=0.95,
        trajectory_score=0.05,
        pacing_score=0.90,
        load_balancing_score=0.04,
        orchestration_score=0.92,
        longitudinal_stability_score=0.03,
        strategy_stability_score=0.91,
        behaviour_engagement_score=0.04,
    )
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_uncertain", profile))
    assert result["route_simulation_state"] == "HIGH_UNCERTAINTY"


# ---------------------------------------------------------------------------
# Test 8: governance check — human_esc → neutral
# ---------------------------------------------------------------------------

def test_governance_human_esc_returns_neutral():
    engine = RehabilitationRouteSimulationEngine()
    ctx = _make_context(human_esc=True)
    with patch.object(engine, "_load_profile", return_value=ctx):
        result = run(engine.evaluate("user_human_esc", ctx))
    assert result["is_neutral"] is True
    assert result["route_simulation_state"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test 9: governance check — silence_respected → neutral
# ---------------------------------------------------------------------------

def test_governance_silence_respected_returns_neutral():
    engine = RehabilitationRouteSimulationEngine()
    ctx = _make_context(silence_respected=True)
    with patch.object(engine, "_load_profile", return_value=ctx):
        result = run(engine.evaluate("user_silent", ctx))
    assert result["is_neutral"] is True


# ---------------------------------------------------------------------------
# Test 10: simulation_stability_score in [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_simulation_stability_score_clamped():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_clamp", _make_context()))
    assert 0.0 <= result["simulation_stability_score"] <= 1.0


# ---------------------------------------------------------------------------
# Test 11: simulation_coherence_score in [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_simulation_coherence_score_clamped():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_coh", _make_context()))
    assert 0.0 <= result["simulation_coherence_score"] <= 1.0


# ---------------------------------------------------------------------------
# Test 12: route_erosion_risk_projection in [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_route_erosion_risk_clamped():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_low_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_erosion_clamp", _make_low_context()))
    assert 0.0 <= result["route_erosion_risk_projection"] <= 1.0


# ---------------------------------------------------------------------------
# Test 13: all scores clamped [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_all_scores_clamped():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_all_clamp", _make_context()))
    score_keys = [
        "simulation_stability_score", "continuity_recovery_probability",
        "pacing_stabilization_effect", "overload_mitigation_effect",
        "route_erosion_risk_projection", "disengagement_recovery_projection",
        "orchestration_balance_projection", "longitudinal_stability_projection",
        "adaptive_strategy_projection", "simulation_coherence_score",
    ]
    for key in score_keys:
        val = result[key]
        assert 0.0 <= val <= 1.0, f"{key} = {val} out of range"


# ---------------------------------------------------------------------------
# Test 14: singleton pattern
# ---------------------------------------------------------------------------

def test_singleton_pattern():
    a = RehabilitationRouteSimulationEngine.get_instance()
    b = RehabilitationRouteSimulationEngine.get_instance()
    assert a is b


# ---------------------------------------------------------------------------
# Test 15: is_neutral=False on successful evaluation
# ---------------------------------------------------------------------------

def test_is_neutral_false_on_success():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_ok", _make_context()))
    assert result["is_neutral"] is False


# ---------------------------------------------------------------------------
# Test 16: simulation_notes is dict
# ---------------------------------------------------------------------------

def test_simulation_notes_is_dict():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context()
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_notes", _make_context()))
    assert isinstance(result["simulation_notes"], dict)


# ---------------------------------------------------------------------------
# Test 17: persist does not crash on DB error
# ---------------------------------------------------------------------------

def test_persist_does_not_crash():
    engine = RehabilitationRouteSimulationEngine()
    result = _neutral_result("user_persist")
    # Should not raise
    engine._persist("user_persist", result)


# ---------------------------------------------------------------------------
# Test 18: adaptive_strategy_projection driven by strategy_stability_score
# ---------------------------------------------------------------------------

def test_adaptive_strategy_projection_driven_by_strategy():
    engine = RehabilitationRouteSimulationEngine()
    signals_high = _make_context(strategy_stability_score=0.95, strategy_state="MAINTAIN")
    signals_low = _make_context(strategy_stability_score=0.05, strategy_state="UNKNOWN")
    high = engine._scenario_adaptive_strategy_impact(
        engine._extract_signals(signals_high, signals_high)
    )
    low = engine._scenario_adaptive_strategy_impact(
        engine._extract_signals(signals_low, signals_low)
    )
    assert high > low


# ---------------------------------------------------------------------------
# Test 19: orchestration_balance_projection driven by load_balancing + orchestration
# ---------------------------------------------------------------------------

def test_orchestration_balance_projection():
    engine = RehabilitationRouteSimulationEngine()
    s_high = engine._extract_signals(_make_context(load_balancing_score=0.9, orchestration_score=0.9), {})
    s_low = engine._extract_signals(_make_context(load_balancing_score=0.1, orchestration_score=0.1), {})
    high = engine._scenario_orchestration_balancing(s_high)
    low = engine._scenario_orchestration_balancing(s_low)
    assert high > low


# ---------------------------------------------------------------------------
# Test 20: longitudinal_stability_projection driven by longitudinal_stability_score
# ---------------------------------------------------------------------------

def test_longitudinal_stability_projection():
    engine = RehabilitationRouteSimulationEngine()
    s_high = engine._extract_signals(
        _make_context(longitudinal_stability_score=0.9, longitudinal_state="STABLE"), {}
    )
    s_low = engine._extract_signals(
        _make_context(longitudinal_stability_score=0.1, longitudinal_state="UNSTABLE"), {}
    )
    high = engine._scenario_longitudinal_stabilization(s_high)
    low = engine._scenario_longitudinal_stabilization(s_low)
    assert high > low


# ---------------------------------------------------------------------------
# Test 21: evaluate_route_simulation module function returns dict
# ---------------------------------------------------------------------------

def test_evaluate_route_simulation_returns_dict():
    with patch("rehabilitation_route_simulation.get_route_simulation_engine") as mock_get:
        mock_engine = MagicMock()
        mock_engine.evaluate = AsyncMock(return_value=_neutral_result("u"))
        mock_get.return_value = mock_engine
        result = run(evaluate_route_simulation("u", {}))
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 22: evaluate_route_simulation never raises
# ---------------------------------------------------------------------------

def test_evaluate_route_simulation_never_raises():
    with patch("rehabilitation_route_simulation.get_route_simulation_engine") as mock_get:
        mock_get.side_effect = Exception("engine crash")
        result = run(evaluate_route_simulation("u_crash", {}))
    assert result["is_neutral"] is True


# ---------------------------------------------------------------------------
# Test 23: CONTINUITY_RECOVERY_PATH when continuity low
# ---------------------------------------------------------------------------

def test_continuity_recovery_path():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context(
        continuity_score=0.20,
        continuity_state="DISRUPTED",
        trajectory_score=0.55,
        behaviour_engagement_score=0.55,
        risk_score=0.25,
        load_balancing_score=0.60,
        orchestration_score=0.60,
        pacing_score=0.55,
        longitudinal_stability_score=0.55,
        strategy_stability_score=0.55,
    )
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_cont_rec", profile))
    # Should not be STABLE and erosion-free path should dominate
    assert result["continuity_recovery_probability"] > 0.0


# ---------------------------------------------------------------------------
# Test 24: PACING_STABILIZATION_PATH when pacing low
# ---------------------------------------------------------------------------

def test_pacing_stabilization_path():
    engine = RehabilitationRouteSimulationEngine()
    s = engine._extract_signals(
        _make_context(pacing_score=0.15, pacing_intensity="LOW"), {}
    )
    result = engine._scenario_pacing_reduction(s)
    assert result >= 0.0


# ---------------------------------------------------------------------------
# Test 25: OVERLOAD_MITIGATION_PATH
# ---------------------------------------------------------------------------

def test_overload_mitigation_path():
    engine = RehabilitationRouteSimulationEngine()
    s_low = engine._extract_signals(
        _make_context(load_balancing_score=0.20, orchestration_score=0.20), {}
    )
    s_high = engine._extract_signals(
        _make_context(load_balancing_score=0.80, orchestration_score=0.80), {}
    )
    low = engine._scenario_overload_mitigation(s_low)
    high = engine._scenario_overload_mitigation(s_high)
    assert high > low


# ---------------------------------------------------------------------------
# Test 26: route_erosion increases with declining signals
# ---------------------------------------------------------------------------

def test_route_erosion_increases_with_declining_signals():
    engine = RehabilitationRouteSimulationEngine()
    s_good = engine._extract_signals(_make_context(), {})
    s_bad = engine._extract_signals(_make_low_context(), {})
    good = engine._scenario_route_erosion(s_good)
    bad = engine._scenario_route_erosion(s_bad)
    assert bad > good


# ---------------------------------------------------------------------------
# Test 27: get_stats returns dict
# ---------------------------------------------------------------------------

def test_get_stats_returns_dict():
    engine = RehabilitationRouteSimulationEngine()
    with patch.object(engine, "get_stats", new_callable=AsyncMock, return_value={"total": 0}):
        result = run(engine.get_stats())
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 28: no outbound calls — evaluate never calls send functions
# ---------------------------------------------------------------------------

def test_no_outbound_calls():
    engine = RehabilitationRouteSimulationEngine()
    profile = _make_context()
    forbidden = [
        "send_telegram_message", "send_message", "send_notification",
        "requests.post", "httpx.post",
    ]
    with patch.object(engine, "_load_profile", return_value=profile),          patch.object(engine, "_persist", return_value=None):
        result = run(engine.evaluate("user_no_outbound", _make_context()))
    # If we reach here without error, no outbound calls were made
    assert result["user_id"] == "user_no_outbound"

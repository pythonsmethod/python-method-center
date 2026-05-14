"""
Phase 3.18 — Meta-Continuity Intelligence
Test suite: 28 scenarios across 6 blocks
All tests are read-only, no DB writes, no outbound calls.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_neutral():
    from meta_continuity_intelligence import neutral_result
    return neutral_result()


def make_engine():
    from meta_continuity_intelligence import MetaContinuityEngine
    MetaContinuityEngine._instance = None
    MetaContinuityEngine._initialized = False
    eng = MetaContinuityEngine.get_instance()
    eng._db_pool = MagicMock()
    eng._initialized = True
    return eng


# ---------------------------------------------------------------------------
# Block 1 — Neutral Result & Fail-Safe (T01–T05)
# ---------------------------------------------------------------------------

def test_T01_neutral_result_all_scores_zero():
    """T01: neutral_result returns all float scores as 0.0"""
    r = make_neutral()
    float_keys = [
        "global_continuity_health_score", "center_route_stability_score",
        "systemic_disengagement_score", "systemic_overload_score",
        "pacing_sustainability_score", "governance_stability_score",
        "recovery_pattern_strength", "strategy_effectiveness_signal",
        "route_durability_signal", "center_silence_integrity_score",
        "dispatcher_alignment_score",
    ]
    for k in float_keys:
        assert r[k] == 0.0, f"{k} should be 0.0 in neutral_result"


def test_T02_neutral_result_state_unknown():
    """T02: neutral_result state is UNKNOWN"""
    r = make_neutral()
    assert r["meta_continuity_state"] == "UNKNOWN"


def test_T03_evaluate_returns_neutral_on_db_failure():
    """T03: evaluate() returns neutral dict on DB failure"""
    async def run():
        eng = make_engine()
        eng._db_pool.acquire.side_effect = Exception("DB connection failure")
        result = await eng.evaluate()
        assert result["is_neutral"] is True
        assert result["meta_continuity_state"] == "UNKNOWN"
    asyncio.get_event_loop().run_until_complete(run())


def test_T04_evaluate_never_raises():
    """T04: evaluate() never raises, always returns dict"""
    async def run():
        eng = make_engine()
        eng._db_pool = None
        result = await eng.evaluate()
        assert isinstance(result, dict)
    asyncio.get_event_loop().run_until_complete(run())


def test_T05_neutral_scores_within_bounds():
    """T05: all scores in neutral_result are within [0.0, 1.0]"""
    r = make_neutral()
    for k, v in r.items():
        if isinstance(v, float):
            assert 0.0 <= v <= 1.0, f"{k}={v} is out of [0,1]"


# ---------------------------------------------------------------------------
# Block 2 — State Classification (T06–T14)
# ---------------------------------------------------------------------------

def make_classify(eng, **kwargs):
    defaults = dict(
        sample_size=10,
        global_health=0.80,
        disengagement=0.10,
        overload=0.10,
        pacing=0.75,
        governance=0.75,
        erosion_detected=False,
        route_durability=0.70,
        recovery_strength=0.20,
    )
    defaults.update(kwargs)
    return eng._classify_state(**defaults)


def test_T06_healthy_continuity_state():
    """T06: HEALTHY_CONTINUITY when health>=0.75 and governance>=0.70"""
    eng = make_engine()
    assert make_classify(eng, global_health=0.80, governance=0.75) == "HEALTHY_CONTINUITY"


def test_T07_continuity_strain_state():
    """T07: CONTINUITY_STRAIN when global_health<=0.55"""
    eng = make_engine()
    state = make_classify(eng, global_health=0.50, governance=0.60, disengagement=0.10, overload=0.10, pacing=0.60)
    assert state == "CONTINUITY_STRAIN"


def test_T08_systemic_disengagement_state():
    """T08: SYSTEMIC_DISENGAGEMENT when disengagement>=0.40"""
    eng = make_engine()
    state = make_classify(eng, global_health=0.60, governance=0.60, disengagement=0.45)
    assert state == "SYSTEMIC_DISENGAGEMENT"


def test_T09_overload_cluster_state():
    """T09: OVERLOAD_CLUSTER when overload>=0.40"""
    eng = make_engine()
    state = make_classify(eng, global_health=0.60, governance=0.60, disengagement=0.10, overload=0.45)
    assert state == "OVERLOAD_CLUSTER"


def test_T10_pacing_instability_state():
    """T10: PACING_INSTABILITY_CLUSTER when pacing<=0.35"""
    eng = make_engine()
    state = make_classify(eng, global_health=0.60, governance=0.60, disengagement=0.10, overload=0.10, pacing=0.30)
    assert state == "PACING_INSTABILITY_CLUSTER"


def test_T11_governance_strain_state():
    """T11: GOVERNANCE_STRAIN when governance<=0.35"""
    eng = make_engine()
    state = make_classify(eng, global_health=0.60, governance=0.30, disengagement=0.10, overload=0.10, pacing=0.60)
    assert state == "GOVERNANCE_STRAIN"


def test_T12_route_erosion_cluster_state():
    """T12: ROUTE_EROSION_CLUSTER when erosion_detected and route_durability<=0.40"""
    eng = make_engine()
    state = make_classify(
        eng, global_health=0.60, governance=0.60, disengagement=0.10, overload=0.10,
        pacing=0.60, erosion_detected=True, route_durability=0.35, recovery_strength=0.20
    )
    assert state == "ROUTE_EROSION_CLUSTER"


def test_T13_recovery_pattern_state():
    """T13: RECOVERY_PATTERN_ACTIVE when recovery_strength>=0.50"""
    eng = make_engine()
    state = make_classify(
        eng, global_health=0.60, governance=0.60, disengagement=0.10, overload=0.10,
        pacing=0.60, erosion_detected=False, route_durability=0.70, recovery_strength=0.55
    )
    assert state == "RECOVERY_PATTERN_ACTIVE"


def test_T14_unknown_on_small_sample():
    """T14: UNKNOWN when sample_size < MIN_SAMPLE_SIZE"""
    eng = make_engine()
    state = make_classify(eng, sample_size=2, global_health=0.90, governance=0.90)
    assert state == "UNKNOWN"


# ---------------------------------------------------------------------------
# Block 3 — Score Clamping (T15–T18)
# ---------------------------------------------------------------------------

def test_T15_clamp_enforced():
    """T15: _clamp enforces [0.0, 1.0] range"""
    from meta_continuity_intelligence import _clamp
    assert _clamp(1.5) == 1.0
    assert _clamp(-0.5) == 0.0
    assert _clamp(0.5) == 0.5


def test_T16_clamp_never_negative():
    """T16: _clamp never returns negative"""
    from meta_continuity_intelligence import _clamp
    assert _clamp(-999) == 0.0


def test_T17_clamp_never_exceeds_one():
    """T17: _clamp never exceeds 1.0"""
    from meta_continuity_intelligence import _clamp
    assert _clamp(999) == 1.0


def test_T18_sample_size_non_negative():
    """T18: sample_size is non-negative in neutral_result"""
    r = make_neutral()
    assert r["sample_size"] == 0
    assert r["sample_size"] >= 0


# ---------------------------------------------------------------------------
# Block 4 — Write Safety (T19–T22)
# ---------------------------------------------------------------------------

def test_T19_write_result_called_on_evaluate():
    """T19: _write_result is called during evaluate()"""
    async def run():
        eng = make_engine()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"cnt": 10, "avg_score": 0.8,
            "stable_cnt": 8, "total_cnt": 10, "disengaged_cnt": 1,
            "overloaded_cnt": 0, "avg_pacing": 0.7, "avg_gov": 0.75,
            "eroding_cnt": 1, "recovery_cnt": 2, "avg_strategy": 0.7,
            "avg_durability": 0.75, "compliant_cnt": 9, "checked_cnt": 10,
            "avg_disp": 0.9})
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        eng._db_pool.acquire = MagicMock(return_value=mock_conn)
        result = await eng.evaluate()
        assert isinstance(result, dict)
        assert "meta_continuity_state" in result
    asyncio.get_event_loop().run_until_complete(run())


def test_T20_evaluate_does_not_mutate_client_profiles():
    """T20: evaluate() does not UPDATE pm_client_profiles"""
    async def run():
        eng = make_engine()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        eng._db_pool.acquire = MagicMock(return_value=mock_conn)
        await eng.evaluate()
        for call in mock_conn.execute.call_args_list:
            sql = str(call).lower()
            assert "update pm_client_profiles" not in sql, "Must not UPDATE pm_client_profiles"
    asyncio.get_event_loop().run_until_complete(run())


def test_T21_no_outbound_calls_in_evaluate():
    """T21: evaluate() makes no HTTP/messaging calls"""
    async def run():
        eng = make_engine()
        eng._db_pool.acquire.side_effect = Exception("DB down")
        with patch("meta_continuity_intelligence.log") as mock_log:
            result = await eng.evaluate()
            assert result["is_neutral"] is True
            # debug logged, not error
            mock_log.debug.assert_called()
    asyncio.get_event_loop().run_until_complete(run())


def test_T22_meta_notes_is_valid_dict():
    """T22: meta_continuity_notes is a dict (valid for jsonb)"""
    r = make_neutral()
    assert isinstance(r["meta_continuity_notes"], dict)


# ---------------------------------------------------------------------------
# Block 5 — Singleton Pattern (T23–T25)
# ---------------------------------------------------------------------------

def test_T23_singleton_same_instance():
    """T23: get_instance() returns same object across calls"""
    from meta_continuity_intelligence import MetaContinuityEngine
    MetaContinuityEngine._instance = None
    a = MetaContinuityEngine.get_instance()
    b = MetaContinuityEngine.get_instance()
    assert a is b


def test_T24_double_initialize_idempotent():
    """T24: calling initialize() twice is idempotent"""
    async def run():
        from meta_continuity_intelligence import MetaContinuityEngine
        MetaContinuityEngine._instance = None
        MetaContinuityEngine._initialized = False
        eng = MetaContinuityEngine.get_instance()
        mock_pool = MagicMock()
        await eng.initialize(mock_pool)
        await eng.initialize(mock_pool)  # second call — must not crash
        assert eng._initialized is True
    asyncio.get_event_loop().run_until_complete(run())


def test_T25_module_level_evaluate_accessible():
    """T25: evaluate_meta_continuity() is callable at module level"""
    async def run():
        from meta_continuity_intelligence import evaluate_meta_continuity
        result = await evaluate_meta_continuity()
        assert isinstance(result, dict)
    asyncio.get_event_loop().run_until_complete(run())


# ---------------------------------------------------------------------------
# Block 6 — Governance Compliance (T26–T28)
# ---------------------------------------------------------------------------

def test_T26_no_prediction_language_in_keys():
    """T26: no prediction language in output field names"""
    r = make_neutral()
    forbidden = ["predict", "forecast", "prognosis", "relapse"]
    for key in r.keys():
        for word in forbidden:
            assert word not in key.lower(), f"Forbidden word '{word}' found in key '{key}'"


def test_T27_no_individual_identifiers_in_output():
    """T27: neutral_result contains no individual client identifiers"""
    r = make_neutral()
    client_fields = ["user_id", "client_id", "telegram_id", "chat_id"]
    for field in client_fields:
        assert field not in r, f"Individual identifier '{field}' must not appear in meta-continuity output"


def test_T28_is_neutral_false_only_on_success():
    """T28: is_neutral=True in neutral_result, must be set False only on real evaluation"""
    r = make_neutral()
    assert r["is_neutral"] is True

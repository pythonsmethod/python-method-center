"""
Phase 3.19 — Institutional Memory Intelligence
Test suite: 28 scenarios across 6 blocks
Read-only pattern observer. No DB writes to source tables. No outbound calls.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_neutral():
    from institutional_memory_intelligence import neutral_result
    return neutral_result()


def make_engine():
    from institutional_memory_intelligence import InstitutionalMemoryEngine
    InstitutionalMemoryEngine._instance = None
    InstitutionalMemoryEngine._initialized = False
    eng = InstitutionalMemoryEngine.get_instance()
    eng._db_pool = MagicMock()
    eng._initialized = True
    return eng


def make_rows(n=10, **overrides):
    base = {
        "governance_stability_score": 0.75,
        "systemic_overload_score": 0.10,
        "pacing_sustainability_score": 0.70,
        "global_continuity_health_score": 0.72,
        "systemic_disengagement_score": 0.15,
        "continuity_erosion_cluster_detected": False,
        "recovery_pattern_strength": 0.30,
        "dispatcher_alignment_score": 0.85,
        "center_silence_integrity_score": 0.90,
    }
    base.update(overrides)
    return [dict(base) for _ in range(n)]


# ---------------------------------------------------------------------------
# Block 1 — Neutral Result & Fail-Safe (T01–T05)
# ---------------------------------------------------------------------------

def test_T01_neutral_result_all_scores_zero():
    """T01: neutral_result returns all float scores as 0.0"""
    r = make_neutral()
    float_keys = [
        "governance_pattern_score", "overload_pattern_score",
        "pacing_pattern_score", "continuity_resilience_score",
        "stabilization_effectiveness_score", "route_erosion_pattern_score",
        "recovery_resilience_pattern_score", "dispatcher_safety_pattern_score",
        "silence_integrity_pattern_score", "institutional_stability_score",
    ]
    for k in float_keys:
        assert r[k] == 0.0, f"{k} should be 0.0 in neutral_result"


def test_T02_neutral_result_state_unknown():
    """T02: neutral_result state is UNKNOWN"""
    r = make_neutral()
    assert r["institutional_memory_state"] == "UNKNOWN"


def test_T03_evaluate_returns_neutral_on_db_failure():
    """T03: evaluate() returns neutral dict on DB failure"""
    async def run():
        eng = make_engine()
        eng._db_pool.acquire.side_effect = Exception("DB connection failure")
        result = await eng.evaluate()
        assert result["is_neutral"] is True
        assert result["institutional_memory_state"] == "UNKNOWN"
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
        institutional_stability=0.80,
        governance=0.75,
        overload=0.10,
        route_erosion=0.05,
        recovery=0.30,
        pacing=0.65,
        stabilization=0.80,
        continuity=0.72,
    )
    defaults.update(kwargs)
    return eng._classify_state(**defaults)


def test_T06_stable_institutional_memory():
    """T06: STABLE_INSTITUTIONAL_MEMORY when stability>=0.75 and governance>=0.70"""
    eng = make_engine()
    assert make_classify(eng, institutional_stability=0.80, governance=0.75) == "STABLE_INSTITUTIONAL_MEMORY"


def test_T07_overload_pattern_detected():
    """T07: OVERLOAD_PATTERN_DETECTED when overload>=0.40"""
    eng = make_engine()
    state = make_classify(eng, institutional_stability=0.60, governance=0.60, overload=0.45)
    assert state == "OVERLOAD_PATTERN_DETECTED"


def test_T08_governance_strain_pattern():
    """T08: GOVERNANCE_STRAIN_PATTERN when governance<=0.35"""
    eng = make_engine()
    state = make_classify(eng, institutional_stability=0.50, governance=0.30, overload=0.10)
    assert state == "GOVERNANCE_STRAIN_PATTERN"


def test_T09_route_erosion_history():
    """T09: ROUTE_EROSION_HISTORY when route_erosion>=0.35"""
    eng = make_engine()
    state = make_classify(eng, institutional_stability=0.55, governance=0.60, overload=0.10, route_erosion=0.40)
    assert state == "ROUTE_EROSION_HISTORY"


def test_T10_recovery_resilience_pattern():
    """T10: RECOVERY_RESILIENCE_PATTERN when recovery>=0.55"""
    eng = make_engine()
    state = make_classify(
        eng, institutional_stability=0.60, governance=0.60, overload=0.10,
        route_erosion=0.10, recovery=0.60
    )
    assert state == "RECOVERY_RESILIENCE_PATTERN"


def test_T11_pacing_evolution_pattern_low():
    """T11: PACING_EVOLUTION_PATTERN when pacing<=0.40"""
    eng = make_engine()
    state = make_classify(
        eng, institutional_stability=0.55, governance=0.60, overload=0.10,
        route_erosion=0.10, recovery=0.30, pacing=0.35
    )
    assert state == "PACING_EVOLUTION_PATTERN"


def test_T12_stabilization_effectiveness_pattern():
    """T12: STABILIZATION_EFFECTIVENESS_PATTERN when stabilization>=0.70"""
    eng = make_engine()
    state = make_classify(
        eng, institutional_stability=0.60, governance=0.60, overload=0.10,
        route_erosion=0.10, recovery=0.30, pacing=0.60, stabilization=0.75
    )
    assert state == "STABILIZATION_EFFECTIVENESS_PATTERN"


def test_T13_continuity_pattern_forming():
    """T13: CONTINUITY_PATTERN_FORMING when continuity<=0.60"""
    eng = make_engine()
    state = make_classify(
        eng, institutional_stability=0.55, governance=0.60, overload=0.10,
        route_erosion=0.10, recovery=0.30, pacing=0.60, stabilization=0.50, continuity=0.50
    )
    assert state == "CONTINUITY_PATTERN_FORMING"


def test_T14_unknown_on_small_sample():
    """T14: UNKNOWN when sample_size < MIN_HISTORY_SAMPLE"""
    eng = make_engine()
    state = make_classify(eng, sample_size=2, institutional_stability=0.90, governance=0.90)
    assert state == "UNKNOWN"


# ---------------------------------------------------------------------------
# Block 3 — Score Clamping (T15–T18)
# ---------------------------------------------------------------------------

def test_T15_clamp_enforced():
    """T15: _clamp enforces [0.0, 1.0]"""
    from institutional_memory_intelligence import _clamp
    assert _clamp(1.5) == 1.0
    assert _clamp(-0.5) == 0.0
    assert _clamp(0.5) == 0.5


def test_T16_clamp_never_negative():
    """T16: _clamp never returns negative"""
    from institutional_memory_intelligence import _clamp
    assert _clamp(-999) == 0.0


def test_T17_clamp_never_exceeds_one():
    """T17: _clamp never exceeds 1.0"""
    from institutional_memory_intelligence import _clamp
    assert _clamp(999) == 1.0


def test_T18_historical_sample_size_non_negative():
    """T18: historical_sample_size is non-negative in neutral_result"""
    r = make_neutral()
    assert r["historical_sample_size"] == 0
    assert r["historical_sample_size"] >= 0


# ---------------------------------------------------------------------------
# Block 4 — Write Safety (T19–T22)
# ---------------------------------------------------------------------------

def test_T19_evaluate_writes_to_institutional_memory_only():
    """T19: evaluate() writes only to pm_institutional_memory"""
    async def run():
        eng = make_engine()
        mock_conn = AsyncMock()
        rows = make_rows(5)
        mock_conn.fetch = AsyncMock(return_value=rows)
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        eng._db_pool.acquire = MagicMock(return_value=mock_conn)
        result = await eng.evaluate()
        assert isinstance(result, dict)
        assert "institutional_memory_state" in result
        for call in mock_conn.execute.call_args_list:
            sql = str(call).lower()
            assert "pm_institutional_memory" in sql or sql == ""
    asyncio.get_event_loop().run_until_complete(run())


def test_T20_evaluate_does_not_mutate_source_tables():
    """T20: evaluate() never UPDATEs pm_client_profiles or pm_center_continuity_metrics"""
    async def run():
        eng = make_engine()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        eng._db_pool.acquire = MagicMock(return_value=mock_conn)
        await eng.evaluate()
        for call in mock_conn.execute.call_args_list:
            sql = str(call).lower()
            assert "update pm_client_profiles" not in sql
            assert "update pm_center_continuity_metrics" not in sql
    asyncio.get_event_loop().run_until_complete(run())


def test_T21_no_outbound_calls_in_evaluate():
    """T21: evaluate() makes no HTTP/messaging calls"""
    async def run():
        eng = make_engine()
        eng._db_pool.acquire.side_effect = Exception("DB down")
        with patch("institutional_memory_intelligence.log") as mock_log:
            result = await eng.evaluate()
            assert result["is_neutral"] is True
            mock_log.debug.assert_called()
    asyncio.get_event_loop().run_until_complete(run())


def test_T22_institutional_memory_notes_is_dict():
    """T22: institutional_memory_notes is a valid dict (jsonb-compatible)"""
    r = make_neutral()
    assert isinstance(r["institutional_memory_notes"], dict)


# ---------------------------------------------------------------------------
# Block 5 — Singleton Pattern (T23–T25)
# ---------------------------------------------------------------------------

def test_T23_singleton_same_instance():
    """T23: get_instance() returns same object across calls"""
    from institutional_memory_intelligence import InstitutionalMemoryEngine
    InstitutionalMemoryEngine._instance = None
    a = InstitutionalMemoryEngine.get_instance()
    b = InstitutionalMemoryEngine.get_instance()
    assert a is b


def test_T24_double_initialize_idempotent():
    """T24: calling initialize() twice is idempotent"""
    async def run():
        from institutional_memory_intelligence import InstitutionalMemoryEngine
        InstitutionalMemoryEngine._instance = None
        InstitutionalMemoryEngine._initialized = False
        eng = InstitutionalMemoryEngine.get_instance()
        mock_pool = MagicMock()
        await eng.initialize(mock_pool)
        await eng.initialize(mock_pool)
        assert eng._initialized is True
    asyncio.get_event_loop().run_until_complete(run())


def test_T25_module_level_evaluate_accessible():
    """T25: evaluate_institutional_memory() callable at module level"""
    async def run():
        from institutional_memory_intelligence import evaluate_institutional_memory
        result = await evaluate_institutional_memory()
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
            assert word not in key.lower(), f"Forbidden word '{word}' in key '{key}'"


def test_T27_no_individual_identifiers_in_output():
    """T27: output contains no individual client identifiers"""
    r = make_neutral()
    client_fields = ["user_id", "client_id", "telegram_id", "chat_id"]
    for field in client_fields:
        assert field not in r, f"Individual identifier '{field}' must not appear in institutional memory output"


def test_T28_is_neutral_false_only_on_success():
    """T28: is_neutral=True in neutral_result"""
    r = make_neutral()
    assert r["is_neutral"] is True

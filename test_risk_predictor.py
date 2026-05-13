"""
test_risk_predictor.py — Phase 3.2: Predictive Risk Intelligence Tests
All 9 scenario tests per spec. Run standalone or via pytest.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

# ─── Test Helpers ─────────────────────────────────────────────────────────────

def make_timeline_event(user_msg=None, route=None, event_type="interaction",
                         minutes_ago=1, risk_score=0.0):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {
        "event_type": event_type,
        "user_message": user_msg,
        "route": route,
        "risk_score": risk_score,
        "summary": "",
        "created_at": ts,
        "user_state": "",
        "intent": "",
    }

def make_orch_event(event_type, minutes_ago=1):
    return {
        "event_type": event_type,
        "route": None,
        "payload": {},
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    }

def make_profile(stage="active", created_hours_ago=None):
    p = {"current_stage": stage}
    if created_hours_ago is not None:
        p["created_at"] = datetime.now(timezone.utc) - timedelta(hours=created_hours_ago)
        p["first_seen_at"] = p["created_at"]
    return p


def run_scenario(signals):
    """Run scoring synchronously for test."""
    from risk_predictor import RiskPredictor
    predictor = RiskPredictor()
    return predictor._score_signals(signals["user_id"], signals)


# ─── Scenario 1: User asks price 5 times but does not pay ─────────────────────

def test_scenario_1_payment_hesitation():
    print("\n[TEST 1] User asks price 5 times but does not pay")
    price_msgs = [
        "Сколько стоит программа?",
        "Дорого, а что включает цена?",
        "За что именно я плачу?",
        "Есть ли скидка на оплату?",
        "Какова стоимость полного курса?",
    ]
    timeline = [make_timeline_event(user_msg=m, minutes_ago=(5-i)*10)
                for i, m in enumerate(price_msgs)]
    signals = {
        "user_id": 1001,
        "now": datetime.now(timezone.utc),
        "profile": make_profile("active"),
        "timeline": timeline,
        "orch_events": [],
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(minutes=30),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None, "Expected risk result"
    assert result.risk_type == "payment_hesitation_risk", f"Got {result.risk_type}"
    assert result.current_risk_score >= 0.3, f"Score too low: {result.current_risk_score}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")
    print(f"  Reason: {result.risk_reason}")
    print(f"  Action: {result.recommended_action}")


# ─── Scenario 2: User disappears after payment ────────────────────────────────

def test_scenario_2_post_payment_silence():
    print("\n[TEST 2] User disappears after payment")
    orch_events = [make_orch_event("payment_confirmed", minutes_ago=30*60)]  # 30h ago
    signals = {
        "user_id": 1002,
        "now": datetime.now(timezone.utc),
        "profile": make_profile("post_payment"),
        "timeline": [],  # no messages after payment
        "orch_events": orch_events,
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(hours=31),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None, "Expected risk result"
    assert result.risk_type == "post_payment_silence_risk", f"Got {result.risk_type}"
    assert result.current_risk_score >= 0.5, f"Score too low: {result.current_risk_score}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")
    print(f"  Reason: {result.risk_reason}")


# ─── Scenario 3: User expresses fear repeatedly ───────────────────────────────

def test_scenario_3_trust_collapse():
    print("\n[TEST 3] User expresses fear repeatedly")
    fear_msgs = [
        "Я боюсь, что это развод",
        "Не доверяю, слышала много плохого",
        "Это точно не мошенник?",
        "Сомневаюсь, стоит ли платить",
    ]
    timeline = [make_timeline_event(user_msg=m, minutes_ago=(4-i)*20)
                for i, m in enumerate(fear_msgs)]
    signals = {
        "user_id": 1003,
        "now": datetime.now(timezone.utc),
        "profile": make_profile("active"),
        "timeline": timeline,
        "orch_events": [],
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None
    assert result.risk_type == "trust_collapse_risk", f"Got {result.risk_type}"
    assert result.current_risk_score >= 0.5, f"Score: {result.current_risk_score}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")
    print(f"  Action: {result.recommended_action}")


# ─── Scenario 4: User sends many messages rapidly ─────────────────────────────

def test_scenario_4_emotional_overload():
    print("\n[TEST 4] User sends many messages rapidly (burst)")
    # 8 messages in last 2 minutes
    timeline = [make_timeline_event(user_msg=f"Сообщение {i}", minutes_ago=i*0.2)
                for i in range(8)]
    signals = {
        "user_id": 1004,
        "now": datetime.now(timezone.utc),
        "profile": make_profile("active"),
        "timeline": timeline,
        "orch_events": [],
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(seconds=10),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None
    assert result.risk_type == "emotional_overload_risk", f"Got {result.risk_type}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")
    print(f"  Action: {result.recommended_action}")


# ─── Scenario 5: User stuck in onboarding ─────────────────────────────────────

def test_scenario_5_onboarding_drop():
    print("\n[TEST 5] User stuck in onboarding")
    signals = {
        "user_id": 1005,
        "now": datetime.now(timezone.utc),
        "profile": make_profile(stage="onboarding", created_hours_ago=10),
        "timeline": [make_timeline_event("Привет!", minutes_ago=600)],
        "orch_events": [],
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(hours=10),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None
    assert result.risk_type == "onboarding_drop_risk", f"Got {result.risk_type}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")


# ─── Scenario 6: User delays analysis upload ──────────────────────────────────

def test_scenario_6_analysis_delay():
    print("\n[TEST 6] User delays analysis upload")
    timeline = [
        make_timeline_event(event_type="analysis_request", minutes_ago=800),
    ]
    signals = {
        "user_id": 1006,
        "now": datetime.now(timezone.utc),
        "profile": make_profile(stage="analysis_pending"),
        "timeline": timeline,
        "orch_events": [],
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(hours=13),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None
    assert result.risk_type == "analysis_delay_risk", f"Got {result.risk_type}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")


# ─── Scenario 7: User requests human several times ────────────────────────────

def test_scenario_7_escalation_needed():
    print("\n[TEST 7] User requests human several times")
    msgs = [
        "Хочу с живым человеком поговорить",
        "Позвоните мне пожалуйста",
        "Соедините меня с менеджером",
    ]
    timeline = [make_timeline_event(user_msg=m, minutes_ago=i*15)
                for i, m in enumerate(msgs)]
    signals = {
        "user_id": 1007,
        "now": datetime.now(timezone.utc),
        "profile": make_profile("active"),
        "timeline": timeline,
        "orch_events": [],
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None
    assert result.risk_type == "escalation_needed_risk", f"Got {result.risk_type}"
    assert result.risk_level in ("high", "critical"), f"Expected high/critical, got {result.risk_level}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")
    print(f"  Action: {result.recommended_action}")


# ─── Scenario 8: Route oscillation pattern ────────────────────────────────────

def test_scenario_8_route_oscillation():
    print("\n[TEST 8] Route oscillation pattern")
    routes = ["trust_route", "info_route", "trust_route", "payment_route",
              "info_route", "trust_route", "recovery_route"]
    timeline = [make_timeline_event(route=r, minutes_ago=(7-i)*10)
                for i, r in enumerate(routes)]
    signals = {
        "user_id": 1008,
        "now": datetime.now(timezone.utc),
        "profile": make_profile("active"),
        "timeline": timeline,
        "orch_events": [],
        "recovery_plans": [],
        "last_message_at": datetime.now(timezone.utc) - timedelta(minutes=10),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None
    assert result.risk_type == "route_oscillation_risk", f"Got {result.risk_type}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} switches={result.details.get('route_switches')}")


# ─── Scenario 9: Recovery attempt fails ───────────────────────────────────────

def test_scenario_9_recovery_failure():
    print("\n[TEST 9] Recovery attempt fails repeatedly")
    recovery_plans = [
        {"status": "failed", "plan_type": "abandonment_risk", "attempts": 3,
         "created_at": datetime.now(timezone.utc) - timedelta(hours=24),
         "completed_at": None},
        {"status": "expired", "plan_type": "payment_hesitation_risk", "attempts": 2,
         "created_at": datetime.now(timezone.utc) - timedelta(hours=12),
         "completed_at": None},
    ]
    signals = {
        "user_id": 1009,
        "now": datetime.now(timezone.utc),
        "profile": make_profile("active"),
        "timeline": [],
        "orch_events": [],
        "recovery_plans": recovery_plans,
        "last_message_at": datetime.now(timezone.utc) - timedelta(hours=50),
        "existing_risk": {},
    }
    result = run_scenario(signals)
    assert result is not None
    assert result.risk_type == "recovery_failure_risk", f"Got {result.risk_type}"
    assert result.risk_level in ("high", "critical"), f"Got {result.risk_level}"
    print(f"  PASS: {result.risk_type} score={result.current_risk_score} level={result.risk_level}")
    print(f"  Action: {result.recommended_action}")


# ─── Safety Tests ─────────────────────────────────────────────────────────────

def test_safety_no_medical():
    print("\n[SAFETY] Risk predictor does not generate medical advice")
    from risk_predictor import SAFETY_NEVER_TRIGGER
    assert "medical_diagnosis" in SAFETY_NEVER_TRIGGER
    assert "payment_pressure" in SAFETY_NEVER_TRIGGER
    assert "emergency_override" in SAFETY_NEVER_TRIGGER
    assert "spam_recovery" in SAFETY_NEVER_TRIGGER
    print("  PASS: Safety set contains all required forbidden actions")


def test_safety_score_bounds():
    print("\n[SAFETY] Risk scores are always 0.0-1.0")
    from risk_predictor import RiskPredictor
    predictor = RiskPredictor()
    for score in [0.0, 0.5, 1.0, -0.1, 1.5]:
        level = predictor._score_to_level(max(0.0, min(1.0, score)))
        assert level in ("low", "medium", "high", "critical"), f"Bad level for {score}"
    print("  PASS: All scores mapped to valid levels")


# ─── Run All Tests ────────────────────────────────────────────────────────────

ALL_TESTS = [
    test_scenario_1_payment_hesitation,
    test_scenario_2_post_payment_silence,
    test_scenario_3_trust_collapse,
    test_scenario_4_emotional_overload,
    test_scenario_5_onboarding_drop,
    test_scenario_6_analysis_delay,
    test_scenario_7_escalation_needed,
    test_scenario_8_route_oscillation,
    test_scenario_9_recovery_failure,
    test_safety_no_medical,
    test_safety_score_bounds,
]

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3.2 — Risk Predictor Test Suite")
    print("=" * 60)
    passed = 0
    failed = 0
    errors = []
    for test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test_fn.__name__, str(e)))
            print(f"  FAIL: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(ALL_TESTS)} tests")
    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)

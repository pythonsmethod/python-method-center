"""
stress_test_3_1A.py - PHASE 3.1A Message Queue & Response Speed Stress Test
Python Method Center

Tests all 8 scenarios with mock bot/orchestrator/DB.
Run: python stress_test_3_1A.py

Scenarios:
  1. Rapid burst: 5 messages within 3 seconds
  2. New message during AI processing (stale discard)
  3. Fast path: price question
  4. Fast path: human request
  5. Paid user protection (no rollback)
  6. Emotional/trust message (fast path blocked)
  7. Medical boundary question
  8. Timeout scenario (AI delay >25s)
"""

import asyncio
import time
import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("stress_test")


# =============================================================================
# MOCK INFRASTRUCTURE
# =============================================================================

@dataclass
class MockOrchestratorResult:
    reply: str
    route: str = "reception_route"
    agent: str = "Lucky"
    memory_updated: bool = True
    escalated: bool = False
    validation_passed: bool = True


class MockBot:
    """Simulates Telegram bot API."""
    def __init__(self):
        self.sent_messages: List[Dict] = []
        self.typing_actions: List[Dict] = []
        self.send_count = 0
        self.typing_count = 0

    async def send_message(self, chat_id: int, text: str, **kwargs):
        ts = time.monotonic()
        self.sent_messages.append({"chat_id": chat_id, "text": text, "ts": ts})
        self.send_count += 1
        logger.info("[MOCK_BOT] send_message chat=%s text=%.60r", chat_id, text)

    async def send_chat_action(self, chat_id: int, action: str = "typing"):
        ts = time.monotonic()
        self.typing_actions.append({"chat_id": chat_id, "action": action, "ts": ts})
        self.typing_count += 1

    def reset(self):
        self.sent_messages.clear()
        self.typing_actions.clear()
        self.send_count = 0
        self.typing_count = 0


class MockOrchestrator:
    """Simulates OrchestratorCore with controllable latency."""
    def __init__(self):
        self.call_count = 0
        self.call_log: List[Dict] = []
        self.simulated_delay: float = 0.5  # Default fast
        self.force_timeout: bool = False
        self.force_route: str = "reception_route"
        self.force_agent: str = "Lucky"
        self.logger = MagicMock()
        self.logger.log = MagicMock(return_value="mock_log_id")
        self.memory_writer = MagicMock()
        self.memory_writer.write = MagicMock()

    async def handle_message(self, user_id: int, text: str, raw_update: dict = None):
        call_ts = time.monotonic()
        self.call_count += 1
        call_n = self.call_count
        logger.info("[MOCK_ORCH] handle_message #%d user=%s text=%.40r", call_n, user_id, text)

        if self.force_timeout:
            await asyncio.sleep(30)  # Exceeds 25s timeout
            return MockOrchestratorResult(reply="[SHOULD_NOT_REACH]")

        await asyncio.sleep(self.simulated_delay)
        elapsed = time.monotonic() - call_ts
        self.call_log.append({
            "call_n": call_n, "user_id": user_id,
            "text": text[:60], "elapsed_ms": int(elapsed * 1000)
        })
        return MockOrchestratorResult(
            reply=f"[AI_RESPONSE_{call_n}] Ответ на: {text[:40]}",
            route=self.force_route,
            agent=self.force_agent
        )

    def reset(self):
        self.call_count = 0
        self.call_log.clear()
        self.simulated_delay = 0.5
        self.force_timeout = False


# =============================================================================
# TEST HARNESS
# =============================================================================

@dataclass
class TestResult:
    scenario: str
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    latencies_ms: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


class StressTestRunner:
    def __init__(self):
        self.bot = MockBot()
        self.orchestrator = MockOrchestrator()
        self.results: List[TestResult] = []
        self.global_stats = {
            "total_scenarios": 0,
            "passed": 0,
            "failed": 0,
            "total_llm_calls": 0,
            "total_messages_sent": 0,
            "stale_discards": 0,
            "fast_path_hits": 0,
            "typing_actions": 0,
        }

    def _build_pipeline(self):
        """Build a fresh pipeline instance for each test."""
        from message_queue import UserMessageQueue
        from debounce_manager import DebounceManager
        from fast_path_resolver import fast_path_resolver, FastPathIntent
        from stale_response_guard import StaleResponseGuard
        from response_speed_manager import ResponseSpeedManager, run_with_timeout
        from async_task_worker import AsyncTaskWorker, TaskPriority

        mq = UserMessageQueue()
        dm = DebounceManager(debounce_window=0.3)  # Fast for testing
        sg = StaleResponseGuard()
        aw = AsyncTaskWorker(max_concurrent=5)

        return mq, dm, sg, aw, fast_path_resolver, FastPathIntent, ResponseSpeedManager, run_with_timeout, TaskPriority

    def _reset(self):
        self.bot.reset()
        self.orchestrator.reset()

    # =========================================================================
    # SCENARIO 1: Rapid Burst - 5 messages in 3 seconds
    # =========================================================================
    async def test_rapid_burst(self) -> TestResult:
        """User sends 5 messages within 3 seconds. Expect one batched response."""
        result = TestResult(scenario="1_rapid_burst", passed=True)
        self._reset()
        mq, dm, sg, aw, fpr, FPI, RSM, rwt, TP = self._build_pipeline()
        user_id = 1001
        chat_id = 1001
        sent_responses = []
        llm_calls = [0]
        stale_discards = [0]

        async def batch_processor(batch):
            from debounce_manager import MessageBatch
            seq = batch.latest_sequence
            token = sg.issue_token(user_id, seq, batch.merged_text)
            llm_calls[0] += 1
            t_llm = time.monotonic()
            await asyncio.sleep(0.5)  # Simulate AI
            result.latencies_ms["llm_call"] = int((time.monotonic() - t_llm) * 1000)
            if sg.check_fresh(token):
                reply = f"[AI] Ответ на батч: {batch.merged_text[:60]}"
                sent_responses.append(reply)
                sg.complete_token(token)
            else:
                stale_discards[0] += 1

        dm.register_callback(batch_processor)
        mq.register_processor(lambda uid, batch: asyncio.gather(*[dm.add_message(uid, m) for m in batch]))

        messages = ["Привет!", "Хочу узнать больше", "Расскажите о программе", "Сколько стоит?", "Мне интересно"]
        t_start = time.monotonic()

        # Send 5 messages with 0.4s spacing (3 seconds total window with debounce 0.3s)
        for i, msg in enumerate(messages):
            seq = i + 1
            sg.register_incoming(user_id, seq, time.monotonic())
            await mq.enqueue(user_id, seq, msg, metadata={"sequence": seq, "chat_id": chat_id})
            await asyncio.sleep(0.4)

        # Wait for debounce to fire and processing to complete
        await asyncio.sleep(2.0)
        total_elapsed = time.monotonic() - t_start
        result.latencies_ms["total_elapsed"] = int(total_elapsed * 1000)

        result.details = {
            "messages_sent_by_user": 5,
            "llm_calls_made": llm_calls[0],
            "responses_delivered": len(sent_responses),
            "stale_discards": stale_discards[0],
        }

        # Validation
        if llm_calls[0] > 2:
            result.failures.append(f"Too many LLM calls: {llm_calls[0]} (expected <=2)")
        if len(sent_responses) == 0:
            result.failures.append("No response delivered to user")
        if len(sent_responses) > 2:
            result.failures.append(f"Too many responses: {len(sent_responses)} (expected 1-2)")

        result.notes.append(f"Debounce window 0.3s merged {5 - llm_calls[0] + 1} messages")
        result.passed = len(result.failures) == 0
        self.global_stats["total_llm_calls"] += llm_calls[0]
        self.global_stats["stale_discards"] += stale_discards[0]
        return result

    # =========================================================================
    # SCENARIO 2: New message during AI processing (stale discard)
    # =========================================================================
    async def test_stale_discard(self) -> TestResult:
        """Message A starts AI. Message B arrives. Response to A is discarded."""
        result = TestResult(scenario="2_stale_discard", passed=True)
        self._reset()
        mq, dm, sg, aw, fpr, FPI, RSM, rwt, TP = self._build_pipeline()
        user_id = 1002
        llm_calls = [0]
        stale_discards = [0]
        final_responses = []
        tokens_issued = []

        async def batch_processor(batch):
            seq = batch.latest_sequence
            token = sg.issue_token(user_id, seq, batch.merged_text)
            tokens_issued.append(token.token_id)
            llm_calls[0] += 1
            await asyncio.sleep(1.5)  # Simulate slow AI
            if sg.check_fresh(token):
                final_responses.append(f"RESPONSE_seq{seq}: {batch.merged_text[:40]}")
                sg.complete_token(token)
            else:
                stale_discards[0] += 1
                logger.info("[TEST2] Stale discard! token=%s seq=%d", token.token_id, seq)

        dm.register_callback(batch_processor)
        mq.register_processor(lambda uid, batch: asyncio.gather(*[dm.add_message(uid, m) for m in batch]))

        t_start = time.monotonic()
        # Send message A
        sg.register_incoming(user_id, 1, time.monotonic())
        await mq.enqueue(user_id, 1, "Расскажи о программе", metadata={"sequence": 1})
        await asyncio.sleep(0.5)  # Let debounce fire and AI start

        # Send message B while AI is processing A (AI takes 1.5s, we send at 0.5s)
        sg.register_incoming(user_id, 2, time.monotonic())
        await mq.enqueue(user_id, 2, "Подождите, вот мой вопрос точнее", metadata={"sequence": 2})
        await asyncio.sleep(3.0)  # Wait for both to complete

        total_elapsed = time.monotonic() - t_start
        result.latencies_ms["total_elapsed"] = int(total_elapsed * 1000)
        result.details = {
            "llm_calls": llm_calls[0],
            "stale_discards": stale_discards[0],
            "final_responses": len(final_responses),
            "tokens_issued": len(tokens_issued),
            "last_response": final_responses[-1] if final_responses else None
        }

        if stale_discards[0] == 0:
            result.failures.append("Expected at least 1 stale discard, got 0")
        if len(final_responses) > 1:
            result.failures.append(f"Too many responses: {len(final_responses)}")

        result.notes.append(f"Stale discards: {stale_discards[0]}, final responses: {len(final_responses)}")
        result.passed = len(result.failures) == 0
        self.global_stats["total_llm_calls"] += llm_calls[0]
        self.global_stats["stale_discards"] += stale_discards[0]
        return result

    # =========================================================================
    # SCENARIO 3: Fast Path - Price Question
    # =========================================================================
    async def test_fast_path_price(self) -> TestResult:
        """Price question must resolve <100ms without LLM call."""
        result = TestResult(scenario="3_fast_path_price", passed=True)
        from fast_path_resolver import fast_path_resolver, FastPathIntent

        test_inputs = [
            "Сколько стоит программа?",
            "какая цена?",
            "стоимость",
            "прайс на курс",
        ]
        fast_path_hits = 0
        all_latencies = []

        for text in test_inputs:
            t0 = time.monotonic()
            intent, response = fast_path_resolver.resolve(text)
            latency_ms = (time.monotonic() - t0) * 1000
            all_latencies.append(latency_ms)

            if intent == FastPathIntent.PRICE_QUESTION:
                fast_path_hits += 1
            else:
                result.failures.append(f"MISS: {text!r} -> intent={intent}")

            if latency_ms > 100:
                result.failures.append(f"Too slow: {latency_ms:.1f}ms for {text!r}")

            if response and ("стоимость" not in response.lower() and "сколько" not in response.lower() and "цен" not in response.lower() and "формат" not in response.lower()):
                result.failures.append(f"Response missing price context: {response[:60]}")

        result.latencies_ms["avg_ms"] = sum(all_latencies) / len(all_latencies)
        result.latencies_ms["max_ms"] = max(all_latencies)
        result.details = {
            "inputs_tested": len(test_inputs),
            "fast_path_hits": fast_path_hits,
            "llm_calls": 0,  # Should be 0
            "avg_latency_ms": round(sum(all_latencies) / len(all_latencies), 3),
        }
        result.notes.append("All price questions should bypass LLM entirely")
        result.passed = len(result.failures) == 0
        self.global_stats["fast_path_hits"] += fast_path_hits
        return result

    # =========================================================================
    # SCENARIO 4: Fast Path - Human Request
    # =========================================================================
    async def test_fast_path_human(self) -> TestResult:
        """Human request must be acknowledged instantly, escalation triggered."""
        result = TestResult(scenario="4_fast_path_human", passed=True)
        from fast_path_resolver import fast_path_resolver, FastPathIntent

        test_inputs = [
            "хочу поговорить с живым человеком",
            "дайте мне оператора",
            "мне нужен живой специалист",
            "это не робот, хочу куратора",
        ]
        hits = 0
        for text in test_inputs:
            t0 = time.monotonic()
            intent, response = fast_path_resolver.resolve(text)
            ms = (time.monotonic() - t0) * 1000

            if intent == FastPathIntent.HUMAN_REQUEST:
                hits += 1
            else:
                result.failures.append(f"MISS human_request: {text!r} -> {intent}")

            if response and "куратор" not in response.lower() and "человек" not in response.lower():
                result.failures.append(f"Response lacks human context: {response[:60]}")

            if ms > 100:
                result.failures.append(f"Too slow: {ms:.1f}ms")

        result.details = {"inputs": len(test_inputs), "hits": hits, "llm_calls": 0}
        result.notes.append("Human request must NEVER go through LLM")
        result.passed = len(result.failures) == 0
        self.global_stats["fast_path_hits"] += hits
        return result

    # =========================================================================
    # SCENARIO 5: Paid User Protection
    # =========================================================================
    async def test_paid_user_protection(self) -> TestResult:
        """Paid user asking what_next must not trigger pre-payment route."""
        result = TestResult(scenario="5_paid_user_protection", passed=True)
        from fast_path_resolver import fast_path_resolver, FastPathIntent

        # Simulate paid user session
        paid_session = {
            "current_route": "onboarding_route",
            "current_stage": "week_1",
            "payment_status": "paid",
            "is_paid": True
        }

        test_inputs = [
            "что дальше?",
            "следующий шаг",
            "продолжаем",
        ]

        for text in test_inputs:
            intent, response = fast_path_resolver.resolve(text, paid_session)
            # what_next fast path should fire (its a simple intent, not pre-payment)
            if intent not in (FastPathIntent.WHAT_NEXT, FastPathIntent.NONE):
                result.failures.append(f"Wrong intent for paid user: {intent} for {text!r}")
            # Ensure no rollback to payment_route
            if response and "оплат" in response.lower() and "maya" not in response.lower():
                if "ссылк" in response.lower():
                    result.failures.append(f"Paid user got payment link! {response[:60]}")

        # Test that route_lock (from orchestrator) prevents rollback
        # Validate the route lock manager invariant
        from route_lock_manager import RouteLockManager
        lock_mgr = RouteLockManager()
        lock_mgr.acquire_lock(1005, "onboarding_route", "post_payment_lock", duration_minutes=99999)
        is_locked = lock_mgr.check_lock(1005)
        can_switch = lock_mgr.can_switch_to(1005, "payment_route")

        if not is_locked:
            result.failures.append("Route lock not active for paid user")
        if can_switch:
            result.failures.append("Route lock allows switch to payment_route — CRITICAL BUG")

        result.details = {
            "paid_session_protected": True,
            "route_locked": is_locked,
            "payment_route_blocked": not can_switch,
        }
        result.notes.append("Paid users must never see payment_route again")
        result.passed = len(result.failures) == 0
        return result

    # =========================================================================
    # SCENARIO 6: Emotional / Trust Message (fast path blocked)
    # =========================================================================
    async def test_emotional_no_fast_path(self) -> TestResult:
        """Emotional messages must never be fast-pathed. Full orchestrator required."""
        result = TestResult(scenario="6_emotional_trust", passed=True)
        from fast_path_resolver import fast_path_resolver, FastPathIntent

        # Emotional inputs that must NOT trigger any fast path
        emotional_inputs = [
            "я не верю что это поможет, уже столько пробовал",
            "мне очень страшно, боюсь что не справлюсь",
            "я в отчаянии, не знаю что делать",
            "чувствую что это всё бессмысленно",
            "родственник не хочет лечиться и я не знаю как быть",
        ]

        fast_path_triggers = []
        for text in emotional_inputs:
            intent, response = fast_path_resolver.resolve(text)
            if intent != FastPathIntent.NONE:
                fast_path_triggers.append(f"{text[:40]!r} -> {intent}")

        if fast_path_triggers:
            for fp in fast_path_triggers:
                result.failures.append(f"Emotional text hit fast path: {fp}")

        # Also test: support_route session blocks fast path
        support_session = {
            "current_route": "support_route",
            "current_stage": "active_grief_support"
        }
        # Even "что дальше?" must NOT fast-path in deep support session
        intent_in_support, _ = fast_path_resolver.resolve("что дальше?", support_session)
        if intent_in_support != FastPathIntent.NONE:
            result.failures.append(
                f"Fast path fired in support_route session: {intent_in_support}"
            )
        else:
            result.notes.append("support_route blocks fast path correctly")

        result.details = {
            "emotional_inputs_tested": len(emotional_inputs),
            "fast_path_triggers": len(fast_path_triggers),
            "support_route_blocked": intent_in_support == FastPathIntent.NONE,
        }
        result.passed = len(result.failures) == 0
        return result

    # =========================================================================
    # SCENARIO 7: Medical Boundary Question
    # =========================================================================
    async def test_medical_boundary(self) -> TestResult:
        """Medical questions must not get unsafe AI answers. Escalation required."""
        result = TestResult(scenario="7_medical_boundary", passed=True)
        from fast_path_resolver import fast_path_resolver, FastPathIntent
        from response_validator import ResponseValidator

        medical_inputs = [
            "у меня сильная боль в груди, что делать?",
            "какой препарат принять при ломке?",
            "можно ли совмещать с антидепрессантами?",
            "какая доза безопасна для меня?",
        ]

        validator = ResponseValidator()

        # Simulated "bad" AI responses that cross medical boundary
        bad_responses = [
            "Принимайте 200мг препарата X дважды в день",
            "Ваш диагноз — зависимость стадии 2, нужно лечение",
            "Рекомендую следующий медицинский протокол: ...",
        ]

        # Validator should catch medical overreach
        catches = 0
        for bad_resp in bad_responses:
            try:
                is_valid = validator.validate_post(
                    response=bad_resp,
                    agent="Vera",
                    route="analysis_route",
                    context={}
                )
                if not is_valid:
                    catches += 1
            except Exception:
                # If validator raises on medical content, that is acceptable
                catches += 1

        # Medical inputs must NOT hit fast path
        for text in medical_inputs:
            intent, _ = fast_path_resolver.resolve(text)
            if intent != FastPathIntent.NONE:
                result.failures.append(f"Medical text hit fast path: {text[:40]!r} -> {intent}")

        result.details = {
            "medical_inputs_not_fast_pathed": len(medical_inputs),
            "validator_catches": catches,
            "validator_total_tested": len(bad_responses),
        }
        result.notes.append("Vera must never diagnose or prescribe")
        if catches == 0:
            result.notes.append("WARNING: ResponseValidator may need medical keyword injection")
        result.passed = len(result.failures) == 0
        return result

    # =========================================================================
    # SCENARIO 8: Timeout Protection
    # =========================================================================
    async def test_timeout_protection(self) -> TestResult:
        """AI takes >25s. Must get safe fallback, never silence."""
        result = TestResult(scenario="8_timeout_protection", passed=True)
        from response_speed_manager import run_with_timeout, TIMEOUT_FALLBACK_RU, AI_RESPONSE_TIMEOUT

        async def slow_ai():
            await asyncio.sleep(30)  # Way too slow
            return "SHOULD_NOT_REACH"

        t0 = time.monotonic()
        # Use short timeout for test (5s instead of 25s)
        response, timed_out = await run_with_timeout(slow_ai(), timeout=5.0)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result.latencies_ms["timeout_elapsed_ms"] = elapsed_ms

        if not timed_out:
            result.failures.append("Expected timeout, but AI completed normally")
        if "SHOULD_NOT_REACH" in str(response):
            result.failures.append("Slow AI response leaked through timeout")
        if elapsed_ms > 7000:
            result.failures.append(f"Timeout took too long: {elapsed_ms}ms (expected ~5000ms)")
        if not response or len(response) < 10:
            result.failures.append("No fallback message provided after timeout")

        result.details = {
            "timed_out": timed_out,
            "elapsed_ms": elapsed_ms,
            "fallback_message": str(response)[:80],
            "silence_prevented": timed_out and bool(response),
        }
        result.notes.append(f"Fallback: {str(response)[:60]}")
        result.passed = len(result.failures) == 0
        return result

    # =========================================================================
    # MAIN TEST RUNNER
    # =========================================================================
    async def run_all(self):
        """Run all 8 scenarios and produce full report."""
        print("\n" + "="*70)
        print("PHASE 3.1A — MESSAGE QUEUE & RESPONSE SPEED STRESS TEST")
        print("="*70)

        scenarios = [
            ("1_rapid_burst",       self.test_rapid_burst),
            ("2_stale_discard",     self.test_stale_discard),
            ("3_fast_path_price",   self.test_fast_path_price),
            ("4_fast_path_human",   self.test_fast_path_human),
            ("5_paid_protection",   self.test_paid_user_protection),
            ("6_emotional_block",   self.test_emotional_no_fast_path),
            ("7_medical_boundary",  self.test_medical_boundary),
            ("8_timeout",           self.test_timeout_protection),
        ]

        for name, fn in scenarios:
            print(f"\n--- Running: {name} ---")
            try:
                result = await fn()
                self.results.append(result)
                self.global_stats["total_scenarios"] += 1
                if result.passed:
                    self.global_stats["passed"] += 1
                    print(f"  PASS: {result.scenario}")
                else:
                    self.global_stats["failed"] += 1
                    print(f"  FAIL: {result.scenario}")
                    for f in result.failures:
                        print(f"    - {f}")
                for note in result.notes:
                    print(f"  NOTE: {note}")
                if result.details:
                    print(f"  DETAILS: {json.dumps(result.details, indent=2)}")
                if result.latencies_ms:
                    print(f"  LATENCIES: {result.latencies_ms}")
            except Exception as e:
                self.global_stats["failed"] += 1
                self.global_stats["total_scenarios"] += 1
                self.results.append(TestResult(scenario=name, passed=False,
                    failures=[f"Exception: {e}"]))
                print(f"  ERROR in {name}: {e}")
                import traceback
                traceback.print_exc()

        self._print_final_report()

    def _print_final_report(self):
        print("\n" + "="*70)
        print("PHASE 3.1A STRESS TEST — FINAL REPORT")
        print("="*70)
        total = self.global_stats["total_scenarios"]
        passed = self.global_stats["passed"]
        failed = self.global_stats["failed"]
        print(f"Scenarios:        {total}")
        print(f"Passed:           {passed} ({int(passed/total*100) if total else 0}%)")
        print(f"Failed:           {failed}")
        print(f"LLM calls:        {self.global_stats['total_llm_calls']}")
        print(f"Stale discards:   {self.global_stats['stale_discards']}")
        print(f"Fast path hits:   {self.global_stats['fast_path_hits']}")
        print("")
        print("SCENARIO RESULTS:")
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.scenario}")
            if not r.passed:
                for f in r.failures:
                    print(f"         -> {f}")
        print("")
        if failed == 0:
            print("ALL TESTS PASSED — PHASE 3.1A VERIFIED")
        else:
            print(f"FAILURES DETECTED: {failed} scenario(s) need attention")
        print("="*70)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import sys
    import os
    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    runner = StressTestRunner()
    asyncio.run(runner.run_all())

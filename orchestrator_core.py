# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: orchestrator_core.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Master orchestration controller for every user message.
#          Coordinates all 12 subsystems in strict execution order.
#          Single entry point: OrchestratorCore.handle_message()
#
# Execution pipeline (per message):
#   Step 0  build_context_package()     — assemble full context snapshot
#   Step 1  state_engine.analyze()      — detect intent + state + risk
#   Step 2  route_resolver.resolve()    — recommend optimal route (observe only)
#   Step 3  route_lock_manager.check()  — enforce active locks
#   Step 4  interrupt_detector.scan()   — detect critical interrupts
#   Step 5  priority_engine.rank()      — resolve interrupt/route priority
#   Step 6  auto_router.apply()         — apply safe automatic route switches
#   Step 7  agent_selector.select()     — select single active agent
#   Step 8  emotional_overlay.detect()  — inject emotional intelligence layer
#   Step 9  escalation_manager.check()  — decide AI vs human escalation
#   Step 10 response_validator.pre()    — validate prompt before generation
#   Step 11 ask_claude() / escalate     — generate AI response or escalate
#   Step 12 response_validator.post()   — validate generated response
#   Step 13 memory_writer.write()       — update long-term memory
#   Step 14 orchestration_logger.log()  — persist orchestration event
#   Step 15 save_session()              — persist session state
#
# Critical invariants (enforced by this module):
#   - NEVER more than one active agent at the same time
#   - NEVER route oscillation (enforced by route_lock_manager)
#   - NEVER loss of context (enforced by context_package_builder)
#   - NEVER medical overreach (enforced by interrupt_detector + response_validator)
#   - NEVER payment dead zones (enforced by priority_engine)
#   - NEVER post-payment silence (enforced by agent_selector)
#   - NEVER return paid user to pre-payment flow (enforced by route_lock_manager)
#   - NEVER escalate without full context_package (enforced by escalation_manager)
# =============================================================================

from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("orchestrator_core")

# ---------------------------------------------------------------------------
# Import all subsystems
# ---------------------------------------------------------------------------
try:
    from context_package_builder import ContextPackageBuilder
    from state_engine import analyze as state_analyze
    from route_resolver import resolve_route
    from route_lock_manager import RouteLockManager
    from interrupt_detector import InterruptDetector
    from priority_engine import PriorityEngine
    from auto_router import apply_auto_route
    from agent_selector import AgentSelector
    from emotional_overlay import (
        detect_emotional_overlay,
        build_overlay_injection,
        update_overlay_session,
    )
    from escalation_manager import EscalationManager
    from response_validator import ResponseValidator
    from memory_writer import MemoryWriter
    from orchestration_logger import OrchestrationLogger
except ImportError as _ie:
    log.error("[ORCH] Import error: %s", _ie)


# ---------------------------------------------------------------------------
# Orchestration result dataclass (plain dict for compatibility)
# ---------------------------------------------------------------------------
class OrchestrationResult:
    """
    Immutable result object returned by OrchestratorCore.handle_message().
    Contains everything needed to send reply, update session, expose to Dashboard.
    """

    def __init__(
        self,
        reply: str,
        session: Dict[str, Any],
        context_package: Dict[str, Any],
        intent: str,
        user_state: str,
        risk_score: float,
        route: str,
        active_agent: str,
        overlay_type: str,
        overlay_confidence: float,
        interrupt_type: Optional[str],
        interrupt_priority: int,
        escalated: bool,
        escalation_reason: Optional[str],
        route_switched: bool,
        route_switch_reason: Optional[str],
        route_locked: bool,
        memory_updated: bool,
        validation_passed: bool,
        validation_issues: list,
        orchestration_log_id: Optional[str],
        processing_ms: int,
    ):
        self.reply = reply
        self.session = session
        self.context_package = context_package
        self.intent = intent
        self.user_state = user_state
        self.risk_score = risk_score
        self.route = route
        self.active_agent = active_agent
        self.overlay_type = overlay_type
        self.overlay_confidence = overlay_confidence
        self.interrupt_type = interrupt_type
        self.interrupt_priority = interrupt_priority
        self.escalated = escalated
        self.escalation_reason = escalation_reason
        self.route_switched = route_switched
        self.route_switch_reason = route_switch_reason
        self.route_locked = route_locked
        self.memory_updated = memory_updated
        self.validation_passed = validation_passed
        self.validation_issues = validation_issues
        self.orchestration_log_id = orchestration_log_id
        self.processing_ms = processing_ms

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# OrchestratorCore — main class
# ---------------------------------------------------------------------------
class OrchestratorCore:
    """
    Central orchestration controller for Python Method Digital Rehabilitation Center.

    Usage (in agents.py or main.py):
        orch = OrchestratorCore()
        result = await orch.handle_message(user_id, message_text, session)
        reply = result.reply
        session = result.session

    Thread safety: Each handle_message() call is independent.
    State is NOT stored on the instance — it is passed in via session dict.
    """

    def __init__(self):
        self.ctx_builder = ContextPackageBuilder()
        self.lock_mgr = RouteLockManager()
        self.interrupt_det = InterruptDetector()
        self.priority_eng = PriorityEngine()
        self.agent_sel = AgentSelector()
        self.esc_mgr = EscalationManager()
        self.validator = ResponseValidator()
        self.mem_writer = MemoryWriter()
        self.logger = OrchestrationLogger()
        log.info("[ORCH] OrchestratorCore initialised")

    # -----------------------------------------------------------------------
    # Main entry point
    # -----------------------------------------------------------------------
    async def handle_message(
        self,
        user_id: int,
        message_text: str,
        session: Dict[str, Any],
        *,
        ask_claude_fn=None,
        save_session_fn=None,
    ) -> OrchestrationResult:
        """
        Full orchestration pipeline for a single user message.

        Args:
            user_id:        Telegram user_id (int)
            message_text:   Raw user message string
            session:        Current session dict (loaded from DB before calling)
            ask_claude_fn:  Callable async fn(system_prompt, history) -> str
            save_session_fn: Callable async fn(session) -> None

        Returns:
            OrchestrationResult with reply + full orchestration metadata
        """
        _t0 = time.monotonic()
        _orch_event: Dict[str, Any] = {
            "user_id": user_id,
            "message": message_text[:200],
            "steps": [],
        }

        reply = ""
        escalated = False
        escalation_reason = None
        route_switched = False
        route_switch_reason = None
        route_locked = False
        interrupt_type = None
        interrupt_priority = 0
        overlay_type = "none"
        overlay_confidence = 0.0
        memory_updated = False
        validation_passed = True
        validation_issues = []
        log_id = None

        try:
            # ---------------------------------------------------------------
            # STEP 0: Build context package
            # ---------------------------------------------------------------
            context_package = self.ctx_builder.build(session, message_text)
            _orch_event["steps"].append("S0:context_package")
            log.debug("[ORCH S0] context_package built for user %s", user_id)

            # ---------------------------------------------------------------
            # STEP 1: State analysis (intent + state + risk)
            # ---------------------------------------------------------------
            state_result = state_analyze(message_text, session)
            intent = state_result.get("intent", "question")
            user_state = state_result.get("state", "neutral")
            risk_score = float(state_result.get("risk_score", 0.0))
            session["last_intent"] = intent
            session["last_state"] = user_state
            session["last_risk_score"] = risk_score
            _orch_event["steps"].append("S1:state_analyze")
            log.debug("[ORCH S1] intent=%s state=%s risk=%.2f", intent, user_state, risk_score)

            # ---------------------------------------------------------------
            # STEP 2: Route resolver (observation — does NOT switch route)
            # ---------------------------------------------------------------
            route_result = resolve_route(intent, user_state, risk_score, session)
            proposed_route = route_result.get("proposed_route", session.get("route", "reception"))
            proposed_agent = route_result.get("proposed_agent", "Lucky")
            route_confidence = float(route_result.get("route_confidence", 0.0))
            session["proposed_route"] = proposed_route
            session["proposed_agent"] = proposed_agent
            session["route_confidence"] = route_confidence
            _orch_event["steps"].append("S2:route_resolver")

            # ---------------------------------------------------------------
            # STEP 3: Route lock enforcement
            # ---------------------------------------------------------------
            lock_result = self.lock_mgr.check(session)
            route_locked = lock_result.get("locked", False)
            lock_reason = lock_result.get("reason", "")
            if route_locked:
                log.info("[ORCH S3] route LOCKED: %s", lock_reason)
            _orch_event["steps"].append("S3:route_lock=%s" % route_locked)

            # ---------------------------------------------------------------
            # STEP 4: Interrupt detection
            # ---------------------------------------------------------------
            interrupt_result = self.interrupt_det.scan(
                message_text, context_package, session
            )
            interrupt_type = interrupt_result.get("interrupt_type")
            interrupt_priority = interrupt_result.get("priority", 0)
            if interrupt_type:
                log.info("[ORCH S4] INTERRUPT detected: %s P%d", interrupt_type, interrupt_priority)
            _orch_event["steps"].append("S4:interrupt=%s" % interrupt_type)

            # ---------------------------------------------------------------
            # STEP 5: Priority engine
            # ---------------------------------------------------------------
            priority_result = self.priority_eng.rank(
                interrupt_result, route_result, context_package, session
            )
            final_route = priority_result.get("route", session.get("route", "reception"))
            final_agent = priority_result.get("agent", "Lucky")
            _orch_event["steps"].append("S5:priority_route=%s" % final_route)

            # ---------------------------------------------------------------
            # STEP 6: Auto-router (guarded route switching)
            # ---------------------------------------------------------------
            prev_route = session.get("route", "reception")
            apply_auto_route(session, intent, user_state, risk_score)
            current_route = session.get("route", "reception")
            if current_route != prev_route:
                route_switched = True
                route_switch_reason = session.get("last_route_switch_reason", "auto_router")
                log.info("[ORCH S6] route switched: %s -> %s (%s)", prev_route, current_route, route_switch_reason)
            _orch_event["steps"].append("S6:auto_route=%s" % current_route)

            # ---------------------------------------------------------------
            # STEP 7: Agent selector (single active agent, no conflicts)
            # ---------------------------------------------------------------
            agent_result = self.agent_sel.select(session, context_package, priority_result)
            active_agent = agent_result.get("agent", "Lucky")
            agent_system_prompt = agent_result.get("system_prompt", "")
            session["active_agent"] = active_agent
            _orch_event["steps"].append("S7:agent=%s" % active_agent)
            log.debug("[ORCH S7] active_agent=%s", active_agent)

            # ---------------------------------------------------------------
            # STEP 8: Emotional overlay (Layer 5)
            # ---------------------------------------------------------------
            try:
                _overlay = detect_emotional_overlay(intent, user_state, risk_score, current_route, session)
                overlay_type = _overlay.get("overlay_type", "none")
                overlay_confidence = float(_overlay.get("overlay_confidence", 0.0))
                overlay_prefix = build_overlay_injection(_overlay)
                if overlay_prefix:
                    agent_system_prompt = overlay_prefix + "\n\n" + agent_system_prompt
                log.info("[OVERLAY] type=%s conf=%.2f route=%s agent=%s blocked=%s reason=%s",
                    overlay_type, overlay_confidence, current_route, active_agent,
                    _overlay.get("blocked", False), _overlay.get("block_reason", ""))
            except Exception as _oe:
                log.error("[ORCH S8] overlay error: %s", _oe)
                overlay_type = "none"
                overlay_prefix = ""
            _orch_event["steps"].append("S8:overlay=%s" % overlay_type)

            # ---------------------------------------------------------------
            # STEP 9: Escalation check
            # ---------------------------------------------------------------
            esc_result = self.esc_mgr.check(
                interrupt_result, context_package, session, risk_score
            )
            escalated = esc_result.get("escalate", False)
            escalation_reason = esc_result.get("reason")
            _orch_event["steps"].append("S9:escalate=%s" % escalated)

            # ---------------------------------------------------------------
            # STEP 10 & 11: Generate response (AI or escalation)
            # ---------------------------------------------------------------
            if escalated:
                reply = await self.esc_mgr.handle_escalation(
                    esc_result, context_package, session
                )
                log.info("[ORCH S11] escalated: %s — reply: %s...", escalation_reason, reply[:60])
            else:
                # Pre-validation of prompt
                pre_valid = self.validator.validate_prompt(agent_system_prompt, session)
                validation_issues.extend(pre_valid.get("issues", []))
                if not pre_valid.get("safe", True):
                    log.warning("[ORCH S10] prompt pre-validation failed: %s", pre_valid.get("issues"))

                # Generate AI response
                if ask_claude_fn:
                    try:
                        reply = await ask_claude_fn(
                            system_prompt=agent_system_prompt,
                            history=session.get("history", []),
                        )
                    except Exception as _ce:
                        log.error("[ORCH S11] ask_claude error: %s", _ce)
                        reply = "Извините, произошла временная ошибка. Попробуйте ещё раз."
                else:
                    reply = "[ORCHESTRATOR] No AI runtime provided. Configure ask_claude_fn."

            # ---------------------------------------------------------------
            # STEP 12: Post-generation response validation
            # ---------------------------------------------------------------
            post_valid = self.validator.validate_response(reply, session, context_package)
            validation_passed = post_valid.get("safe", True)
            validation_issues.extend(post_valid.get("issues", []))
            if not validation_passed:
                log.warning("[ORCH S12] response validation failed: %s", post_valid.get("issues"))
                reply = post_valid.get("safe_reply", reply)

            # ---------------------------------------------------------------
            # STEP 13: Memory update
            # ---------------------------------------------------------------
            try:
                memory_updated = self.mem_writer.write(
                    session, message_text, reply, context_package
                )
            except Exception as _me:
                log.error("[ORCH S13] memory write error: %s", _me)

            # ---------------------------------------------------------------
            # STEP 14: Overlay session tracking
            # ---------------------------------------------------------------
            try:
                update_overlay_session(session, _overlay if overlay_type != "none" else {"overlay_type": "none"})
            except Exception as _ue:
                log.error("[ORCH S14] overlay session update error: %s", _ue)

            # ---------------------------------------------------------------
            # STEP 15: Orchestration logging
            # ---------------------------------------------------------------
            _proc_ms = int((time.monotonic() - _t0) * 1000)
            _orch_event.update({
                "route": current_route,
                "agent": active_agent,
                "intent": intent,
                "state": user_state,
                "risk_score": risk_score,
                "overlay": overlay_type,
                "escalated": escalated,
                "route_switched": route_switched,
                "route_locked": route_locked,
                "interrupt": interrupt_type,
                "validation_passed": validation_passed,
                "processing_ms": _proc_ms,
            })
            try:
                log_id = self.logger.log(_orch_event, session)
            except Exception as _le:
                log.error("[ORCH S15] logging error: %s", _le)

            # ---------------------------------------------------------------
            # STEP 16: Persist session
            # ---------------------------------------------------------------
            if save_session_fn:
                try:
                    await save_session_fn(session)
                except Exception as _se:
                    log.error("[ORCH S16] save_session error: %s", _se)

        except Exception as _ex:
            log.error("[ORCH FATAL] Unhandled error in handle_message: %s", traceback.format_exc())
            reply = reply or "Извините, произошла ошибка. Специалист уже получил уведомление."
            validation_passed = False
            validation_issues.append("fatal_error: " + str(_ex))

        _proc_ms = int((time.monotonic() - _t0) * 1000)
        log.info("[ORCH DONE] user=%s agent=%s route=%s overlay=%s escalated=%s ms=%d",
                 user_id, active_agent if 'active_agent' in dir() else '?',
                 current_route if 'current_route' in dir() else '?',
                 overlay_type, escalated, _proc_ms)

        return OrchestrationResult(
            reply=reply,
            session=session,
            context_package=context_package if 'context_package' in dir() else {},
            intent=intent if 'intent' in dir() else "unknown",
            user_state=user_state if 'user_state' in dir() else "unknown",
            risk_score=risk_score if 'risk_score' in dir() else 0.0,
            route=current_route if 'current_route' in dir() else session.get("route", "reception"),
            active_agent=active_agent if 'active_agent' in dir() else "Lucky",
            overlay_type=overlay_type,
            overlay_confidence=overlay_confidence,
            interrupt_type=interrupt_type,
            interrupt_priority=interrupt_priority,
            escalated=escalated,
            escalation_reason=escalation_reason,
            route_switched=route_switched,
            route_switch_reason=route_switch_reason,
            route_locked=route_locked,
            memory_updated=memory_updated,
            validation_passed=validation_passed,
            validation_issues=validation_issues,
            orchestration_log_id=log_id,
            processing_ms=_proc_ms,
        )


# ---------------------------------------------------------------------------
# Singleton accessor (optional — for direct import in agents.py)
# ---------------------------------------------------------------------------
_ORCHESTRATOR: Optional[OrchestratorCore] = None


def get_orchestrator() -> OrchestratorCore:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = OrchestratorCore()
    return _ORCHESTRATOR


# =============================================================================
# PHASE 3.1A — Message Queue Pipeline Integration
# Wraps OrchestratorCore with:
#   message_queue -> debounce -> batch -> orchestrator
#   -> stale_guard -> send -> async background tasks
# =============================================================================

from message_queue import UserMessageQueue, QueuedMessage
from debounce_manager import DebounceManager, MessageBatch, DEBOUNCE_WINDOW
from fast_path_resolver import fast_path_resolver, FastPathIntent
from stale_response_guard import StaleResponseGuard, ResponseToken
from response_speed_manager import ResponseSpeedManager, run_with_timeout, compress_context_for_llm, get_model_tier
from async_task_worker import AsyncTaskWorker, TaskPriority, submit_memory_write, submit_orch_log


class MessagePipelineManager:
    """
    Full message processing pipeline with speed & queue management.
    
    This is the outermost layer that every incoming Telegram message
    must pass through before reaching OrchestratorCore.
    
    Pipeline:
    incoming_message
      -> stale_guard.register_incoming()     [instant, O(1)]
      -> message_queue.enqueue()             [instant, never blocks]
      -> debounce_manager.add_message()      [accumulate rapid messages]
      -> (wait debounce window 1.8s)
      -> batch ready callback fires
      -> fast_path_resolver.resolve()        [<100ms, bypass LLM if match]
      -> stale_guard.issue_token()           [freshness token]
      -> speed_manager start typing()        [immediate Telegram feedback]
      -> orchestrator_core.handle_message()  [full pipeline, 3-8s]
      -> stale_guard.check_fresh(token)      [is response still valid?]
      -> if fresh: send response to Telegram
      -> if stale: discard, re-enqueue with latest context
      -> async_worker: memory_write + orch_log + analytics [background]
    """

    def __init__(self, bot=None):
        self.bot = bot
        self.orchestrator = get_orchestrator()
        self.message_queue = UserMessageQueue()
        self.debounce = DebounceManager()
        self.stale_guard = StaleResponseGuard()
        self.async_worker = AsyncTaskWorker(max_concurrent=10)
        self._sequence: Dict[int, int] = {}
        # Wire debounce -> batch processor
        self.debounce.register_callback(self._process_batch)
        # Wire message_queue -> debounce
        self.message_queue.register_processor(self._queue_to_debounce)
        log.info("[PIPELINE] MessagePipelineManager initialized")

    async def start(self):
        """Start background workers."""
        await self.async_worker.start()
        log.info("[PIPELINE] Background workers started")

    def set_bot(self, bot):
        """Set Telegram bot reference (injected at startup)."""
        self.bot = bot

    async def incoming(self, user_id: int, message_id: int, text: str,
                       chat_id: int, raw_update: Optional[Dict] = None) -> None:
        """
        Entry point for every incoming Telegram message.
        Returns immediately — processing happens in background.
        """
        # Track sequence
        self._sequence[user_id] = self._sequence.get(user_id, 0) + 1
        seq = self._sequence[user_id]
        now = time.monotonic()

        log.info("[PIPELINE] Incoming user=%s seq=%d text=%.40r", user_id, seq, text)

        # Register with stale guard immediately
        self.stale_guard.register_incoming(user_id, seq, now)

        # Enqueue (spawns worker, never blocks)
        await self.message_queue.enqueue(
            user_id=user_id,
            message_id=message_id,
            text=text,
            raw_update=raw_update or {},
            metadata={"sequence": seq, "chat_id": chat_id}
        )

    async def _queue_to_debounce(self, user_id: int, batch: list):
        """Message queue processor: pass each message through debounce."""
        for msg in batch:
            await self.debounce.add_message(user_id, msg)

    async def _process_batch(self, batch: MessageBatch):
        """
        Called by debounce when batch is ready.
        This is where actual processing happens.
        """
        user_id = batch.user_id
        text = batch.merged_text
        seq = batch.latest_sequence
        chat_id = None
        raw_update = None

        # Extract chat_id and raw_update from last message metadata
        if batch.messages:
            last_msg = batch.messages[-1]
            chat_id = last_msg.metadata.get("chat_id", user_id)
            raw_update = last_msg.raw_update

        log.info("[PIPELINE] Batch ready user=%s seq=%d count=%d text=%.50r",
                 user_id, seq, batch.message_count, text)

        try:
            await self._run_full_pipeline(
                user_id=user_id,
                chat_id=chat_id or user_id,
                text=text,
                seq=seq,
                raw_update=raw_update,
                batch=batch
            )
        except Exception as e:
            log.error("[PIPELINE] Pipeline error user=%s: %s", user_id, e)

    async def _run_full_pipeline(self, user_id: int, chat_id: int,
                                  text: str, seq: int,
                                  raw_update: Optional[Dict],
                                  batch: MessageBatch):
        """
        Full orchestration pipeline for a debounced message batch.
        """
        # ------------------------------------------------------------------
        # FAST PATH: Check if this is a simple intent (bypass LLM)
        # ------------------------------------------------------------------
        session_hint = None  # Would load from DB in production
        fast_intent, fast_response = fast_path_resolver.resolve(text, session_hint)

        if fast_intent != FastPathIntent.NONE and fast_response:
            # Check freshness before sending fast response
            token = self.stale_guard.issue_token(user_id, seq, text)
            if self.stale_guard.check_fresh(token):
                log.info("[PIPELINE] FAST PATH user=%s intent=%s", user_id, fast_intent)
                await self._send_response(chat_id, fast_response)
                self.stale_guard.complete_token(token)
            else:
                log.warning("[PIPELINE] Fast path response was stale, skipping user=%s", user_id)
            return

        # ------------------------------------------------------------------
        # FULL PIPELINE: Start speed manager (typing indicator + holding msg)
        # ------------------------------------------------------------------
        token = self.stale_guard.issue_token(user_id, seq, text)

        async with ResponseSpeedManager(self.bot, chat_id, user_id) as speed:
            # Run orchestrator with timeout protection
            async def run_orch():
                return await self.orchestrator.handle_message(
                    user_id=user_id,
                    text=text,
                    raw_update=raw_update or {}
                )

            result, timed_out = await run_with_timeout(run_orch())

        # ------------------------------------------------------------------
        # STALE GUARD: Check if response is still current
        # ------------------------------------------------------------------
        if not self.stale_guard.check_fresh(token):
            log.warning("[PIPELINE] STALE response discarded user=%s seq=%d", user_id, seq)
            self.stale_guard.complete_token(token)
            return

        # ------------------------------------------------------------------
        # SEND RESPONSE
        # ------------------------------------------------------------------
        if isinstance(result, str):
            reply_text = result
        elif hasattr(result, "reply"):
            reply_text = result.reply
        else:
            reply_text = str(result)

        await self._send_response(chat_id, reply_text)
        self.stale_guard.complete_token(token)
        log.info("[PIPELINE] Response sent user=%s seq=%d len=%d timed_out=%s",
                 user_id, seq, len(reply_text), timed_out)

        # ------------------------------------------------------------------
        # BACKGROUND TASKS (fire-and-forget after response is sent)
        # ------------------------------------------------------------------
        try:
            orch_result = result if hasattr(result, "memory_updated") else None
            await self._schedule_background_tasks(user_id, text, reply_text, orch_result)
        except Exception as e:
            log.error("[PIPELINE] Background task scheduling error user=%s: %s", user_id, e)

    async def _send_response(self, chat_id: int, text: str):
        """Send response to Telegram. Safe fallback if bot not set."""
        if not self.bot:
            log.warning("[PIPELINE] Bot not set, cannot send response to chat %s", chat_id)
            return
        try:
            await self.bot.send_message(chat_id, text)
        except Exception as e:
            log.error("[PIPELINE] Send response error chat=%s: %s", chat_id, e)

    async def _schedule_background_tasks(self, user_id: int,
                                           input_text: str,
                                           reply_text: str,
                                           orch_result: Optional[Any]):
        """
        Schedule all post-response background tasks.
        These run AFTER response is sent. Never block user.
        """
        # Task 1: Orchestration log (normal priority)
        async def log_task():
            try:
                self.orchestrator.logger.log({
                    "user_id": user_id,
                    "input": input_text[:200],
                    "reply": reply_text[:200],
                    "pipeline": "message_pipeline_v1"
                }, {})
            except Exception as e:
                log.debug("[PIPELINE_BG] Log error: %s", e)

        await self.async_worker.fire_and_forget(
            task_type="orch_log",
            user_id=user_id,
            coro_factory=log_task,
            priority=TaskPriority.NORMAL
        )

        # Task 2: Memory write (high priority)
        if orch_result and hasattr(orch_result, "memory_updated") and orch_result.memory_updated:
            async def memory_task():
                try:
                    self.orchestrator.memory_writer.write(
                        user_id=user_id,
                        session={},
                        orch_result=orch_result.__dict__ if hasattr(orch_result, "__dict__") else {}
                    )
                except Exception as e:
                    log.debug("[PIPELINE_BG] Memory error: %s", e)

            await self.async_worker.fire_and_forget(
                task_type="memory_write",
                user_id=user_id,
                coro_factory=memory_task,
                priority=TaskPriority.HIGH
            )

        # Task 3: Risk prediction (async, non-blocking, does not affect response)
        async def risk_task():
            try:
                from risk_predictor import get_risk_predictor
                predictor = get_risk_predictor()
                if predictor:
                    await predictor.predict_for_user(user_id)
                    log.debug("[PIPELINE_BG] Risk prediction done user=%s", user_id)
            except Exception as e:
                log.debug("[PIPELINE_BG] Risk prediction error: %s", e)

        await self.async_worker.fire_and_forget(
            task_type="risk_prediction",
            user_id=user_id,
            coro_factory=risk_task,
            priority=TaskPriority.LOW
        )

        # Task 4: Recovery policy governance check (background only, does NOT send messages)
        async def policy_task():
            try:
                from recovery_policy_engine import get_recovery_policy_engine
                from recovery_policy_engine import (
                    UserContext, RiskProfile, RouteState, MemoryState
                )
                engine = get_recovery_policy_engine()
                if not engine:
                    return
                # Build minimal context from available data for governance check
                orch_ctx = orch_result.__dict__ if orch_result and hasattr(orch_result, '__dict__') else {}
                user_ctx = UserContext(user_id=user_id)
                risk_prof = RiskProfile()
                route_st  = RouteState()
                mem_st    = MemoryState()
                decision  = await engine.evaluate_recovery_policy(
                    user_ctx, risk_prof, route_st, mem_st
                )
                log.debug(
                    "[PIPELINE_BG] Policy decision user=%s action=%s stage=%s fatigue=%.2f",
                    user_id, decision.action,
                    decision.dashboard_flags.get("stage", "?"),
                    decision.fatigue_score,
                )
                await engine.persist_full_decision(decision)
            except Exception as e:
                log.debug("[PIPELINE_BG] Policy task error (non-fatal): %s", e)

        await self.async_worker.fire_and_forget(
            task_type="policy_governance",
            user_id=user_id,
            coro_factory=policy_task,
            priority=TaskPriority.LOW
        )

        # Task 5: Proactive dispatcher — send approved recovery messages (background only)
        async def dispatcher_task():
            try:
                from proactive_message_dispatcher import get_dispatcher
                dispatcher = get_dispatcher()
                if dispatcher:
                    sent = await dispatcher.dispatch_allowed_recovery_messages()
                    if sent > 0:
                        log.info("[PIPELINE_BG] Dispatcher sent %d message(s) user=%s",
                                 sent, user_id)
            except Exception as e:
                log.debug("[PIPELINE_BG] Dispatcher task error (non-fatal): %s", e)

        await self.async_worker.fire_and_forget(
            task_type="proactive_dispatch",
            user_id=user_id,
            coro_factory=dispatcher_task,
            priority=TaskPriority.LOW
        )

        # Task 5.5 — Adaptive Behaviour Engine (LOWEST priority — runs after policy, before dispatch)
        # Evaluates user behavioural profile and generates adaptation recommendations.
        # NEVER sends messages. Central Orchestrator remains final authority.
        async def behaviour_task():
            try:
                from adaptive_behaviour_engine import get_behaviour_engine
                engine = get_behaviour_engine()
                if not engine:
                    return
                # Build minimal context from available data
                user_ctx = {
                    "user_id": user_id,
                    "current_stage": orch_ctx.get("current_stage", "unknown"),
                    "silence_respect": orch_ctx.get("silence_respect", False),
                    "explicit_refusal": orch_ctx.get("explicit_refusal", False),
                    "human_escalation_required": orch_ctx.get("human_escalation_required", False),
                    "route_lock": orch_ctx.get("route_lock", False),
                    "trust_lock": orch_ctx.get("trust_lock", False),
                    "cooldown_active": orch_ctx.get("cooldown_active", False),
                    "ai_message_count": orch_ctx.get("ai_message_count", 0),
                    "user_message_count": orch_ctx.get("user_message_count", 0),
                }
                memory_st = orch_ctx.get("memory_state", {})
                risk_prof  = orch_ctx.get("risk_profile", {})
                history    = orch_ctx.get("interaction_history", [])
                profile = await engine.evaluate_behaviour_profile(
                    user_ctx, memory_st, risk_prof, history
                )
                log.debug(
                    "[PIPELINE_BG] Behaviour profile: user=%s classification=%s volatility=%.2f",
                    user_id,
                    profile.classification.value,
                    profile.volatility_score,
                )
            except Exception as e:
                log.debug("[PIPELINE_BG] Behaviour task error (non-fatal): %s", e)

        await self.async_worker.fire_and_forget(
            task_type="behaviour_eval",
            user_id=user_id,
            coro_factory=behaviour_task,
            priority=TaskPriority.LOW
        )

        # Task 5.6 — Clinical Continuity Intelligence (analytical layer, no outbound sends)
        # Runs after behaviour_eval and before scanner/dispatcher final packaging.
        # This task NEVER sends messages directly.
        # Central Orchestrator remains final authority.
        async def continuity_task():
            try:
                from clinical_continuity_engine import get_continuity_engine
                engine = get_continuity_engine()
                if not engine:
                    log.debug("[CONTINUITY] Engine not initialised — skipping continuity_task")
                    return
                result = await engine.evaluate_continuity(
                    user_id=user_id,
                    context_package=user_context,
                )
                # Attach result to context for dispatcher/governance enrichment
                user_context["continuity_result"] = result.to_dict()
                log.debug(
                    "[CONTINUITY] continuity_task complete for user %s: state=%s score=%.2f",
                    user_id, result.continuity_state, result.continuity_score,
                )
            except Exception as exc:
                log.warning("[CONTINUITY] continuity_task error for user %s: %s", user_id, exc)

        fire_and_forget(
            task_type="continuity_eval",
            user_id=user_id,
            coro_factory=continuity_task,
        )


                # Task 5.7 — Trajectory Intelligence (LOW priority, enriches dispatcher context)
        # Runs AFTER continuity_task, BEFORE dispatcher_task
        # IMMUTABLE: must never bypass dispatcher, silence, escalation, or recovery governance
        async def trajectory_task():
            try:
                from trajectory_intelligence_engine import get_trajectory_engine
                engine = get_trajectory_engine()
                if engine:
                    silence_resp  = getattr(self, '_silence_respected', False)
                    human_esc     = getattr(self, '_human_escalation_active', False)
                    rec_policy    = getattr(self, '_recovery_policy_active', False)
                    profile_data  = context.get('profile', {}) if context else {}
                    continuity_r  = context.get('continuity_result', {}) if context else {}
                    risk_r        = context.get('risk_result', {}) if context else {}
                    behaviour_r   = context.get('behaviour_result', {}) if context else {}
                    t_result = await engine.evaluate_trajectory(
                        user_id=user_id,
                        profile=profile_data,
                        continuity_result=continuity_r,
                        risk_result=risk_r,
                        behaviour_result=behaviour_r,
                        silence_respected=silence_resp,
                        human_escalation=human_esc,
                        recovery_policy_active=rec_policy,
                    )
                    if context is not None:
                        context['trajectory_result'] = {
                            'trajectory_state':   t_result.trajectory_state,
                            'trajectory_score':   t_result.trajectory_score,
                            'trajectory_direction': t_result.trajectory_direction,
                            'trajectory_gap':     t_result.trajectory_gap_detected,
                            'escalation_hint':    t_result.escalation_hint,
                            'action':             t_result.recommended_action,
                        }
            except Exception as exc:
                log.debug("[PIPELINE_BG] Trajectory task error (non-fatal): %s", exc)

        await self.async_worker.fire_and_forget(
            task_type="trajectory_eval",
            user_id=user_id,
            coro_factory=trajectory_task,
        )


        # Task 5.8 — Rehabilitation State Machine (LOW priority, enriches dispatcher context)
        # Runs AFTER trajectory_task, BEFORE dispatcher_task
        # IMMUTABLE: must never bypass dispatcher, silence, escalation, or recovery governance
        async def state_machine_task():
            try:
                from rehabilitation_state_machine import get_state_machine
                sm = get_state_machine()
                if sm:
                    silence_resp  = getattr(self, '_silence_respected', False)
                    human_esc     = getattr(self, '_human_escalation_active', False)
                    rec_policy    = getattr(self, '_recovery_policy_active', False)
                    profile_data  = context.get('profile', {}) if context else {}
                    continuity_r  = context.get('continuity_result', {}) if context else {}
                    trajectory_r  = context.get('trajectory_result', {}) if context else {}
                    behaviour_r   = context.get('behaviour_result', {}) if context else {}
                    risk_r        = context.get('risk_result', {}) if context else {}
                    sm_result = await sm.evaluate_state(
                        user_id=user_id,
                        profile=profile_data,
                        continuity_result=continuity_r,
                        trajectory_result=trajectory_r,
                        behaviour_result=behaviour_r,
                        risk_result=risk_r,
                        silence_respected=silence_resp,
                        human_escalation=human_esc,
                        recovery_policy_active=rec_policy,
                    )
                    if context is not None:
                        context['state_machine_result'] = {
                            'rehabilitation_state':   sm_result.rehabilitation_state,
                            'rehabilitation_stage':   sm_result.rehabilitation_stage,
                            'stage_completion_score': sm_result.stage_completion_score,
                            'stage_stall_detected':   sm_result.stage_stall_detected,
                            'progression_gate':       sm_result.progression_gate_status,
                            'escalation_gate':        sm_result.escalation_gate_status,
                            'next_allowed_states':    sm_result.next_allowed_states,
                        }
            except Exception as exc:
                log.debug("[PIPELINE_BG] State machine task error (non-fatal): %s", exc)

        await self.async_worker.fire_and_forget(
            task_type="state_machine_eval",
            user_id=user_id,
            coro_factory=state_machine_task,
        )


# Task 6 — Silent User Scanner (LOW priority, runs scan cycle)
        async def scanner_task():
            try:
                from silent_user_scanner import get_scanner
                scanner = get_scanner()
                if scanner:
                    await scanner.run_scan()
            except Exception as e:
                log.debug("[PIPELINE_BG] Scanner task error (non-fatal): %s", e)

        await self.async_worker.fire_and_forget(
            task_type="silent_scan",
            user_id=user_id,
            coro_factory=scanner_task,
            priority=TaskPriority.LOW
        )

    def get_stats(self) -> Dict[str, Any]:
        """Return pipeline health stats."""
        return {
            "queue": self.message_queue.get_stats(),
            "debounce": self.debounce.get_stats(),
            "stale_guard": self.stale_guard.get_stats(),
            "async_worker": self.async_worker.get_stats(),
        }


# ---------------------------------------------------------------------------
# Global pipeline singleton
# ---------------------------------------------------------------------------
_PIPELINE: Optional[MessagePipelineManager] = None


def get_pipeline(bot=None) -> MessagePipelineManager:
    """Get or create the global pipeline manager."""
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = MessagePipelineManager(bot=bot)
    if bot and not _PIPELINE.bot:
        _PIPELINE.set_bot(bot)
    return _PIPELINE

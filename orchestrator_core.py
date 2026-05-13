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

# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: escalation_manager.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Decide whether AI can handle the message or human escalation is needed.
#          If escalated: generate holding response + notify human team.
#          CRITICAL: NEVER escalate without full context_package.
#
# Escalation triggers:
#   MANDATORY (always escalate to human):
#     - medical_emergency interrupt
#     - suicide_risk interrupt
#     - 3rd escalation request within same session
#     - explicit "live operator" request
#
#   CONDITIONAL (escalate if AI confidence too low):
#     - severe_panic + risk >= 0.85
#     - high_risk_oncology + AI failed twice
#     - analysis_overdue + no doctor available message
#
#   NEVER escalate:
#     - normal questions
#     - payment doubt (Maya handles)
#     - normal emotional overlays (Nadia handles)
# =============================================================================

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("escalation_manager")

NOTIFY_BOT_TOKEN = os.environ.get("NOTIFY_BOT_TOKEN", "")
KAREN_CHAT_ID = os.environ.get("KAREN_CHAT_ID", "6181048365")
ANNA_CHAT_ID = os.environ.get("ANNA_CHAT_ID", "402361257")

# ---------------------------------------------------------------------------
# Escalation thresholds
# ---------------------------------------------------------------------------
_MANDATORY_INTERRUPTS = {"medical_emergency", "suicide_risk"}
_CONDITIONAL_INTERRUPTS = {"severe_panic", "analysis_overdue"}
_HUMAN_REQUEST_PHRASES = [
    "живой оператор", "живого оператора", "позвоните мне", "хочу с человеком",
    "переключите на человека", "мне нужен специалист", "live agent", "real person",
    "хочу поговорить с врачом", "speak to a human",
]


# ---------------------------------------------------------------------------
# EscalationManager class
# ---------------------------------------------------------------------------
class EscalationManager:
    """
    Decides AI vs human escalation per message.

    INVARIANT: Never escalates without context_package.
    INVARIANT: Always sends holding response before notifying human.
    INVARIANT: Escalation count tracked per session.
    """

    def check(
        self,
        interrupt_result: Dict[str, Any],
        context_package: Dict[str, Any],
        session: Dict[str, Any],
        risk_score: float,
    ) -> Dict[str, Any]:
        try:
            return self._check(interrupt_result, context_package, session, risk_score)
        except Exception as e:
            log.error("[ESC] check error: %s", e)
            return {"escalate": False, "reason": f"error: {e}", "type": "none"}

    def _check(
        self,
        interrupt_result: Dict[str, Any],
        context_package: Dict[str, Any],
        session: Dict[str, Any],
        risk_score: float,
    ) -> Dict[str, Any]:
        interrupt_type = interrupt_result.get("interrupt_type")
        requires_human = interrupt_result.get("requires_human", False)
        requires_immediate = interrupt_result.get("requires_immediate_escalation", False)
        message_text = context_package.get("message_text", "").lower()
        escalation_count = int(session.get("escalation_count", 0))

        # -------------------------------------------------------------------
        # Rule 1: Immediate escalation — P1 critical interrupts
        # -------------------------------------------------------------------
        if requires_immediate or interrupt_type in _MANDATORY_INTERRUPTS:
            return {
                "escalate": True,
                "type": "immediate",
                "reason": f"critical_interrupt: {interrupt_type}",
                "notify_karen": True,
                "notify_anna": True,
                "priority": 1,
            }

        # -------------------------------------------------------------------
        # Rule 2: Explicit human request from user
        # -------------------------------------------------------------------
        if any(phrase in message_text for phrase in _HUMAN_REQUEST_PHRASES):
            return {
                "escalate": True,
                "type": "user_requested",
                "reason": "user_requested_human",
                "notify_karen": True,
                "notify_anna": False,
                "priority": 2,
            }

        # -------------------------------------------------------------------
        # Rule 3: 3rd escalation in same session (AI is failing)
        # -------------------------------------------------------------------
        if escalation_count >= 2:
            return {
                "escalate": True,
                "type": "repeated_escalation",
                "reason": f"session escalation_count={escalation_count} >= 2",
                "notify_karen": True,
                "notify_anna": False,
                "priority": 3,
            }

        # -------------------------------------------------------------------
        # Rule 4: Conditional — severe panic at very high risk
        # -------------------------------------------------------------------
        if interrupt_type == "severe_panic" and risk_score >= 0.85:
            return {
                "escalate": True,
                "type": "conditional",
                "reason": f"severe_panic risk={risk_score:.2f}",
                "notify_karen": True,
                "notify_anna": False,
                "priority": 2,
            }

        # -------------------------------------------------------------------
        # Rule 5: Requires human (set by interrupt_detector) but not immediate
        # -------------------------------------------------------------------
        if requires_human:
            return {
                "escalate": True,
                "type": "required",
                "reason": f"interrupt requires_human: {interrupt_type}",
                "notify_karen": True,
                "notify_anna": False,
                "priority": 2,
            }

        # Default: AI handles
        return {"escalate": False, "type": "none", "reason": "ai_handles", "priority": 0}

    async def handle_escalation(
        self,
        esc_result: Dict[str, Any],
        context_package: Dict[str, Any],
        session: Dict[str, Any],
    ) -> str:
        """
        Generate holding response + notify human team.
        Returns the holding message to send to user.
        """
        try:
            # Increment escalation counter
            session["escalation_count"] = int(session.get("escalation_count", 0)) + 1
            session["route"] = "escalation_route"
            session["active_agent"] = "Karen"

            esc_type = esc_result.get("type", "required")
            holding_reply = self._build_holding_reply(esc_type, context_package)

            # Notify team
            if esc_result.get("notify_karen") or esc_result.get("notify_anna"):
                await self._notify_team(esc_result, context_package, session)

            return holding_reply

        except Exception as e:
            log.error("[ESC] handle_escalation error: %s", e)
            return (
                "Я передаю вас живому специалисту. "
                "Он свяжется с вами в ближайшее время. Мы рядом."
            )

    def _build_holding_reply(
        self,
        esc_type: str,
        context_package: Dict[str, Any],
    ) -> str:
        client_name = context_package.get("client_name", "")
        name_part = f", {client_name}" if client_name else ""

        if esc_type == "immediate":
            return (
                f"Я слышу вас{name_part}. Это важно. "
                "Прямо сейчас наш специалист получает уведомление и свяжется с вами. "
                "Пожалуйста, оставайтесь на связи — мы здесь."
            )
        elif esc_type == "user_requested":
            return (
                f"Конечно{name_part}. Я передаю вас живому специалисту прямо сейчас. "
                "Он свяжется с вами в течение нескольких минут."
            )
        elif esc_type == "repeated_escalation":
            return (
                f"Я понимаю{name_part}, что нам нужен более глубокий разговор. "
                "Подключаю специалиста, который сможет полностью помочь вам."
            )
        else:
            return (
                f"Мы передаём ваш вопрос специалисту{name_part}. "
                "Он ответит вам в ближайшее время. Спасибо за терпение."
            )

    async def _notify_team(
        self,
        esc_result: Dict[str, Any],
        context_package: Dict[str, Any],
        session: Dict[str, Any],
    ) -> None:
        """Send escalation notification to Karen/Anna via Telegram."""
        if not NOTIFY_BOT_TOKEN:
            log.warning("[ESC] NOTIFY_BOT_TOKEN not set — skipping team notification")
            return

        user_id = context_package.get("user_id", "?")
        client_name = context_package.get("client_name", "неизвестен")
        route = context_package.get("route", "?")
        risk = float(context_package.get("last_risk_score", 0.0))
        intent = context_package.get("last_intent", "?")
        reason = esc_result.get("reason", "?")
        priority = esc_result.get("priority", 0)
        message_preview = context_package.get("message_text", "")[:150]

        msg = (
            f"🚨 ЭСКАЛАЦИЯ P{priority}\n"
            f"Клиент: {client_name} (id: {user_id})\n"
            f"Маршрут: {route} | Risk: {risk:.2f} | Intent: {intent}\n"
            f"Причина: {reason}\n"
            f"Сообщение: {message_preview}\n"
            f"---\n"
            f"Подключитесь к клиенту в Telegram."
        )

        targets = []
        if esc_result.get("notify_karen"):
            targets.append(KAREN_CHAT_ID)
        if esc_result.get("notify_anna"):
            targets.append(ANNA_CHAT_ID)

        for chat_id in targets:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        f"https://api.telegram.org/bot{NOTIFY_BOT_TOKEN}/sendMessage",
                        json={"chat_id": chat_id, "text": msg},
                    )
                log.info("[ESC] notified %s", chat_id)
            except Exception as e:
                log.error("[ESC] notify error for %s: %s", chat_id, e)

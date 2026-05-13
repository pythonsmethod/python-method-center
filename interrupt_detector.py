# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: interrupt_detector.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Detect critical interrupts that override or modify normal routing.
#          Runs after route_resolver, before priority_engine.
#          Output feeds into priority_engine for final resolution.
#
# Interrupt types (ordered by severity):
#   CRITICAL (P1):
#     medical_emergency    — "я умираю", "сердце остановилось", immediate danger
#     suicide_risk         — explicit or implicit suicidal intent
#     severe_panic         — severe panic attack requiring immediate human
#
#   HIGH (P2):
#     high_risk_oncology   — oncology + high risk (rs >= 0.75) + fear/despair
#     payment_dead_zone    — paid user getting no onboarding (post-payment silence)
#     post_payment_silence — paid user ignored > threshold messages
#     analysis_overdue     — analysis sent but no response loop
#
#   MEDIUM (P3):
#     payment_stuck        — user ready_to_pay but stuck > 3 msgs
#     onboarding_stuck     — paid user stuck in onboarding > 5 msgs
#     repeated_unanswered  — same question repeated 3+ times without resolution
#     trust_broken         — user explicitly withdrawing trust
#
#   LOW (P4):
#     confusion_loop       — user confused in same topic > 3 msgs
#     faq_loop             — FAQ route cycling without resolution
#     emotional_spike      — sudden risk_score jump (delta > 0.30)
#
#   NONE (P0):
#     none                 — no interrupt, normal flow
# =============================================================================

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger("interrupt_detector")

# ---------------------------------------------------------------------------
# Keyword banks (Russian + mixed)
# ---------------------------------------------------------------------------
_MEDICAL_EMERGENCY_KW = [
    r"я\s+умир[аею]", r"умираю", r"сердце\s+оста", r"не\s+могу\s+дышать",
    r"скорую", r"умер", r"emergency", r"я\s+теряю\s+сознание",
    r"кровотечени", r"нет\s+пульс", r"задыхаюсь",
]
_SUICIDE_KW = [
    r"хочу\s+умереть", r"лучше\s+умереть", r"смысла\s+нет\s+жить",
    r"не\s+хочу\s+жить", r"покончить\s+с\s+собой", r"суицид",
    r"самоубийств", r"конец\s+(жизни|всему)", r"прощайте\s+все",
    r"больше\s+не\s+могу\s+жить",
]
_SEVERE_PANIC_KW = [
    r"паника", r"паническ", r"я\s+в\s+панике", r"мне\s+очень\s+страшно",
    r"я\s+не\s+выдержу", r"помогите\s+мне", r"мне\s+плохо\s+очень",
    r"срочно\s+помогите",
]
_TRUST_BROKEN_KW = [
    r"это\s+развод", r"вы\s+мошенник", r"обман", r"верну\s+деньги",
    r"буду\s+жаловаться", r"в\s+суд", r"роспотребнадзор",
    r"никому\s+не\s+доверяю", r"хватит\s+мне\s+врать",
]


def _match_any(text: str, patterns: List[str]) -> bool:
    t = text.lower()
    for p in patterns:
        if re.search(p, t):
            return True
    return False


# ---------------------------------------------------------------------------
# InterruptDetector class
# ---------------------------------------------------------------------------
class InterruptDetector:
    """
    Scans each message + context_package for critical interrupts.

    Returns:
        {
            "interrupt_type": str | None,
            "priority": int (0-4, higher = more critical),
            "reason": str,
            "requires_human": bool,
            "requires_immediate_escalation": bool,
            "metadata": dict
        }
    """

    def scan(
        self,
        message_text: str,
        context_package: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            return self._scan(message_text, context_package, session)
        except Exception as e:
            log.error("[INTERRUPT] scan error: %s", e)
            return self._none()

    def _scan(
        self,
        message_text: str,
        context_package: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        txt = message_text.lower()
        risk = float(context_package.get("last_risk_score", 0.0))
        intent = context_package.get("last_intent", "question")
        state = context_package.get("last_state", "neutral")
        route = context_package.get("route", "reception")
        payment_status = context_package.get("payment_status", "new")
        history_len = int(context_package.get("history_len", 0))
        msg_count = int(context_package.get("msg_count", 0))
        escalation_count = int(context_package.get("escalation_count", 0))

        # -------------------------------------------------------------------
        # P1: CRITICAL — Medical emergency
        # -------------------------------------------------------------------
        if _match_any(txt, _MEDICAL_EMERGENCY_KW):
            return self._result(
                "medical_emergency", 1,
                "Medical emergency keywords detected",
                requires_human=True,
                requires_immediate=True,
            )

        # P1: CRITICAL — Suicide risk
        if _match_any(txt, _SUICIDE_KW):
            return self._result(
                "suicide_risk", 1,
                "Suicide risk keywords detected",
                requires_human=True,
                requires_immediate=True,
            )

        # P1: CRITICAL — Severe panic
        if _match_any(txt, _SEVERE_PANIC_KW) and risk >= 0.70:
            return self._result(
                "severe_panic", 1,
                f"Severe panic detected (risk={risk:.2f})",
                requires_human=True,
                requires_immediate=False,
            )

        # -------------------------------------------------------------------
        # P2: HIGH — High-risk oncology crisis
        # -------------------------------------------------------------------
        if risk >= 0.75 and intent in ("fear", "despair", "panic") and "онкол" in txt:
            return self._result(
                "high_risk_oncology", 2,
                f"Oncology high-risk crisis (risk={risk:.2f}, intent={intent})",
                requires_human=False,
                requires_immediate=False,
            )

        # P2: HIGH — Post-payment silence (paid but stuck in reception)
        if payment_status == "paid" and route in ("reception", "individual") and msg_count > 3:
            return self._result(
                "post_payment_silence", 2,
                f"Paid user still in pre-payment route after {msg_count} msgs",
                requires_human=False,
                requires_immediate=False,
                metadata={"route": route, "msg_count": msg_count},
            )

        # P2: HIGH — Payment dead zone
        if intent == "ready_to_pay" and route in ("payment_route",) and session.get("msgs_since_route_change", 0) > 5:
            return self._result(
                "payment_dead_zone", 2,
                "User ready to pay but stuck in payment route > 5 msgs",
                requires_human=False,
                requires_immediate=False,
            )

        # P2: HIGH — Analysis overdue
        if context_package.get("analysis_pending") and session.get("msgs_since_analysis_upload", 0) > 8:
            return self._result(
                "analysis_overdue", 2,
                "Analysis upload pending but no response for > 8 msgs",
                requires_human=True,
                requires_immediate=False,
            )

        # -------------------------------------------------------------------
        # P3: MEDIUM — Trust broken
        # -------------------------------------------------------------------
        if _match_any(txt, _TRUST_BROKEN_KW):
            return self._result(
                "trust_broken", 3,
                "Trust breakdown keywords detected",
                requires_human=False,
                requires_immediate=False,
            )

        # P3: MEDIUM — Payment stuck
        if intent == "ready_to_pay" and session.get("ready_to_pay_since_msg", 0) > 0:
            msgs_ready = msg_count - session.get("ready_to_pay_since_msg", 0)
            if msgs_ready >= 3:
                return self._result(
                    "payment_stuck", 3,
                    f"User ready_to_pay for {msgs_ready} messages without conversion",
                    requires_human=False,
                    requires_immediate=False,
                    metadata={"msgs_ready": msgs_ready},
                )

        # P3: MEDIUM — Onboarding stuck
        if payment_status == "paid" and route in ("onboarding_route", "onboarding"):
            ob_msgs = session.get("onboarding_msgs", 0)
            if ob_msgs > 7:
                return self._result(
                    "onboarding_stuck", 3,
                    f"Paid user stuck in onboarding for {ob_msgs} msgs",
                    requires_human=False,
                    requires_immediate=False,
                )

        # -------------------------------------------------------------------
        # P4: LOW — Emotional spike
        # -------------------------------------------------------------------
        risk_history = context_package.get("risk_history", [])
        if len(risk_history) >= 2:
            prev_risk = risk_history[-2]
            if risk - prev_risk >= 0.30:
                return self._result(
                    "emotional_spike", 4,
                    f"Risk spike: {prev_risk:.2f} -> {risk:.2f}",
                    requires_human=False,
                    requires_immediate=False,
                    metadata={"prev_risk": prev_risk, "current_risk": risk},
                )

        # P4: LOW — Confusion loop (detected by state)
        if state == "confused" and session.get("confusion_msgs", 0) >= 3:
            return self._result(
                "confusion_loop", 4,
                "User in confusion loop for 3+ messages",
                requires_human=False,
                requires_immediate=False,
            )

        return self._none()

    def _result(
        self,
        interrupt_type: str,
        priority: int,
        reason: str,
        requires_human: bool = False,
        requires_immediate: bool = False,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        log.info("[INTERRUPT] %s P%d: %s (human=%s immediate=%s)",
                 interrupt_type, priority, reason, requires_human, requires_immediate)
        return {
            "interrupt_type": interrupt_type,
            "priority": priority,
            "reason": reason,
            "requires_human": requires_human,
            "requires_immediate_escalation": requires_immediate,
            "metadata": metadata or {},
        }

    def _none(self) -> Dict[str, Any]:
        return {
            "interrupt_type": None,
            "priority": 0,
            "reason": "",
            "requires_human": False,
            "requires_immediate_escalation": False,
            "metadata": {},
        }

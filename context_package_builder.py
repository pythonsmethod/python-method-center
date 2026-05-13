# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: context_package_builder.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Assemble a full, normalized context snapshot for every incoming
#          message. This is the single source of truth for all downstream
#          orchestration subsystems.
#
# context_package schema:
#   user_id              int
#   message_text         str
#   message_len          int
#   message_ts           float (unix timestamp)
#   route                str  (current route)
#   agent                str  (current active agent)
#   payment_status       str  paid | pending | new
#   onboarding_step      int
#   analysis_pending     bool
#   history_len          int
#   last_intent          str
#   last_state           str
#   last_risk_score      float
#   risk_trend           str  rising | falling | stable
#   client_name          str
#   tariff               str
#   disease              str
#   has_analysis         bool
#   msg_count            int
#   msgs_since_route_chg int
#   overlay_type         str
#   overlay_consecutive  int
#   escalation_count     int
#   route_history        list[str] (last 10 routes)
#   intent_history       list[str] (last 10 intents)
#   flags                dict  (arbitrary flags set by any subsystem)
# =============================================================================

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("context_package_builder")

# ---------------------------------------------------------------------------
# Payment status inference (no DB — reads session only)
# ---------------------------------------------------------------------------
_PAID_ROUTES = {"onboarding_route", "analysis_route", "support_route", "onboarding", "analysis", "support"}
_PENDING_ROUTES = {"formula", "tariff_recommend", "escalation_route", "escalation", "payment_route"}


def _detect_payment_status(session: Dict[str, Any]) -> str:
    route = session.get("route", "reception")
    tariff = (session.get("client_data") or {}).get("tariff", "")
    payment_status = session.get("payment_status", "")

    if payment_status == "paid":
        return "paid"
    if route in _PAID_ROUTES:
        return "paid"
    if tariff and tariff != "unknown":
        return "pending"
    if route in _PENDING_ROUTES:
        return "pending"
    return "new"


# ---------------------------------------------------------------------------
# Risk trend detector (reads last N risk scores from session)
# ---------------------------------------------------------------------------
def _detect_risk_trend(session: Dict[str, Any]) -> str:
    risk_history: List[float] = session.get("risk_history", [])
    current_risk: float = float(session.get("last_risk_score", 0.0))
    if len(risk_history) < 2:
        return "stable"
    prev_avg = sum(risk_history[-3:]) / len(risk_history[-3:])
    if current_risk > prev_avg + 0.10:
        return "rising"
    if current_risk < prev_avg - 0.10:
        return "falling"
    return "stable"


# ---------------------------------------------------------------------------
# ContextPackageBuilder class
# ---------------------------------------------------------------------------
class ContextPackageBuilder:
    """
    Builds the canonical context_package dict for every incoming message.

    Usage:
        builder = ContextPackageBuilder()
        ctx = builder.build(session, message_text)

    The context_package is passed to every downstream subsystem as read-only
    reference. It must NOT be mutated by subsystems — they work on session instead.
    """

    def build(self, session: Dict[str, Any], message_text: str) -> Dict[str, Any]:
        try:
            return self._build(session, message_text)
        except Exception as e:
            log.error("[CTX] build error: %s", e)
            return self._empty(message_text)

    def _build(self, session: Dict[str, Any], message_text: str) -> Dict[str, Any]:
        client_data: Dict[str, Any] = session.get("client_data") or {}
        history: List[Any] = session.get("history") or []

        # Route history tracking
        route_history: List[str] = session.get("route_history", [])
        current_route: str = session.get("route", "reception")
        if not route_history or route_history[-1] != current_route:
            route_history = (route_history + [current_route])[-10:]
            session["route_history"] = route_history

        # Intent history tracking
        intent_history: List[str] = session.get("intent_history", [])
        last_intent: str = session.get("last_intent", "question")
        if not intent_history or intent_history[-1] != last_intent:
            intent_history = (intent_history + [last_intent])[-10:]
            session["intent_history"] = intent_history

        # Risk history tracking
        risk_history: List[float] = session.get("risk_history", [])
        last_risk: float = float(session.get("last_risk_score", 0.0))
        risk_history = (risk_history + [last_risk])[-20:]
        session["risk_history"] = risk_history

        # Payment status
        payment_status = _detect_payment_status(session)

        # Risk trend
        risk_trend = _detect_risk_trend(session)

        # Oscillation detection: same route appearing 3+ times in last 5 switches
        route_oscillation = False
        if len(route_history) >= 5:
            recent = route_history[-5:]
            if len(set(recent)) <= 2 and len(recent) == 5:
                from collections import Counter
                c = Counter(recent)
                if any(v >= 3 for v in c.values()):
                    route_oscillation = True
                    log.warning("[CTX] ROUTE OSCILLATION detected: %s", recent)

        ctx: Dict[str, Any] = {
            # Message
            "user_id":              session.get("user_id", 0),
            "message_text":         message_text,
            "message_len":          len(message_text),
            "message_ts":           time.time(),

            # Route & Agent
            "route":                current_route,
            "agent":                session.get("active_agent", "Lucky"),
            "proposed_route":       session.get("proposed_route", current_route),
            "proposed_agent":       session.get("proposed_agent", "Lucky"),
            "route_confidence":     float(session.get("route_confidence", 0.0)),
            "route_history":        route_history,
            "route_oscillation":    route_oscillation,
            "msgs_since_route_chg": int(session.get("msgs_since_route_change", 0)),

            # Payment & Onboarding
            "payment_status":       payment_status,
            "onboarding_step":      int(session.get("onboarding_step", 0)),
            "analysis_pending":     bool(session.get("analysis_upload_pending", False)),
            "has_analysis":         bool(session.get("has_analysis", False)),
            "tariff":               client_data.get("tariff", ""),

            # Client profile
            "client_name":          client_data.get("name", ""),
            "disease":              client_data.get("disease", ""),
            "client_data":          client_data,

            # Intent & State
            "last_intent":          last_intent,
            "last_state":           session.get("last_state", "neutral"),
            "last_risk_score":      last_risk,
            "risk_trend":           risk_trend,
            "risk_history":         risk_history[-5:],
            "intent_history":       intent_history,

            # Conversation
            "history_len":          len(history),
            "msg_count":            int(session.get("msg_count", 0)),

            # Overlay
            "overlay_type":         session.get("overlay_type", "none"),
            "overlay_consecutive":  int(session.get("overlay_consecutive_empathy", 0)),
            "overlay_last_high_msg":int(session.get("overlay_last_high_msg", 0)),

            # Escalation
            "escalation_count":     int(session.get("escalation_count", 0)),
            "awaiting_confirmation":bool(session.get("awaiting_confirmation", False)),

            # Route lock
            "route_locked":         bool(session.get("route_locked", False)),
            "route_lock_until_msg": int(session.get("route_lock_until_msg", 0)),

            # Trust
            "trust_entered_at_msg": int(session.get("trust_entered_at_msg", 0)),
            "trust_transition_reason": session.get("trust_transition_reason", ""),

            # Generic flags
            "flags":                session.get("orchestration_flags", {}),
        }

        return ctx

    def _empty(self, message_text: str) -> Dict[str, Any]:
        return {
            "user_id": 0, "message_text": message_text, "message_len": len(message_text),
            "message_ts": time.time(), "route": "reception", "agent": "Lucky",
            "proposed_route": "reception", "proposed_agent": "Lucky",
            "route_confidence": 0.0, "route_history": [], "route_oscillation": False,
            "msgs_since_route_chg": 0, "payment_status": "new", "onboarding_step": 0,
            "analysis_pending": False, "has_analysis": False, "tariff": "",
            "client_name": "", "disease": "", "client_data": {},
            "last_intent": "question", "last_state": "neutral", "last_risk_score": 0.0,
            "risk_trend": "stable", "risk_history": [], "intent_history": [],
            "history_len": 0, "msg_count": 0, "overlay_type": "none",
            "overlay_consecutive": 0, "overlay_last_high_msg": 0,
            "escalation_count": 0, "awaiting_confirmation": False,
            "route_locked": False, "route_lock_until_msg": 0,
            "trust_entered_at_msg": 0, "trust_transition_reason": "",
            "flags": {},
        }


# ---------------------------------------------------------------------------
# Module-level convenience function (backward compatibility with central_ai_core)
# ---------------------------------------------------------------------------
_builder_instance = ContextPackageBuilder()


def build_context_package(session: Dict[str, Any], message_text: str = "") -> Dict[str, Any]:
    """
    Drop-in replacement for central_ai_core.build_context_package().
    Agents.py can import from here or from central_ai_core — both work.
    """
    return _builder_instance.build(session, message_text)

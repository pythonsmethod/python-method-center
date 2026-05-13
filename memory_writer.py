# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: memory_writer.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Update long-term client memory after each interaction.
#          Tracks: intent history, state transitions, risk evolution,
#          route history, key facts extracted, emotional milestones,
#          payment events, analysis events, escalation events.
#
# Memory is stored in session['long_term_memory'] (JSONB in PostgreSQL).
# Each write is additive — never overwrites, only appends/updates.
#
# Memory schema (stored in session):
#   long_term_memory: {
#     "total_messages": int,
#     "first_contact_ts": float,
#     "last_contact_ts": float,
#     "intent_counts": {intent: count},
#     "max_risk_score": float,
#     "risk_spikes": [{ts, from, to, msg_count}],
#     "route_transitions": [{ts, from, to, reason, msg_count}],
#     "payment_events": [{ts, event, details}],
#     "escalation_events": [{ts, reason, type}],
#     "analysis_events": [{ts, event}],
#     "emotional_milestones": [{ts, type, risk, intent}],
#     "key_facts": {field: value},  (name, disease, tariff, etc.)
#     "ai_failed_count": int,
#     "last_overlay_types": [str],  (last 5 overlays)
#   }
# =============================================================================

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

log = logging.getLogger("memory_writer")

# ---------------------------------------------------------------------------
# Risk thresholds for milestone detection
# ---------------------------------------------------------------------------
_RISK_SPIKE_THRESHOLD = 0.25
_RISK_MILESTONE_THRESHOLD = 0.70
_EMOTIONAL_MILESTONES = {
    "panic":    0.85,
    "crisis":   0.75,
    "fear":     0.60,
    "relief":   0.30,  # risk dropping below this after spike
}


# ---------------------------------------------------------------------------
# MemoryWriter class
# ---------------------------------------------------------------------------
class MemoryWriter:
    """
    Updates long-term client memory after each AI interaction.

    Usage:
        writer = MemoryWriter()
        updated = writer.write(session, user_message, ai_reply, context_package)

    Returns True if memory was updated, False if error.
    Memory is stored in session["long_term_memory"] as a dict.
    """

    def write(
        self,
        session: Dict[str, Any],
        user_message: str,
        ai_reply: str,
        context_package: Dict[str, Any],
    ) -> bool:
        try:
            return self._write(session, user_message, ai_reply, context_package)
        except Exception as e:
            log.error("[MEMORY] write error: %s", e)
            return False

    def _write(
        self,
        session: Dict[str, Any],
        user_message: str,
        ai_reply: str,
        context_package: Dict[str, Any],
    ) -> bool:
        mem = session.setdefault("long_term_memory", {})
        ts = time.time()
        msg_count = int(context_package.get("msg_count", 0))

        # -------------------------------------------------------------------
        # Basic counters
        # -------------------------------------------------------------------
        mem["total_messages"] = mem.get("total_messages", 0) + 1
        if "first_contact_ts" not in mem:
            mem["first_contact_ts"] = ts
        mem["last_contact_ts"] = ts

        # -------------------------------------------------------------------
        # Intent history
        # -------------------------------------------------------------------
        intent = context_package.get("last_intent", "question")
        intent_counts: Dict[str, int] = mem.setdefault("intent_counts", {})
        intent_counts[intent] = intent_counts.get(intent, 0) + 1

        # -------------------------------------------------------------------
        # Risk tracking
        # -------------------------------------------------------------------
        risk = float(context_package.get("last_risk_score", 0.0))
        prev_max = float(mem.get("max_risk_score", 0.0))
        if risk > prev_max:
            mem["max_risk_score"] = risk

        # Risk spikes
        risk_history: List[float] = context_package.get("risk_history", [])
        if len(risk_history) >= 2:
            prev_risk = risk_history[-2]
            delta = risk - prev_risk
            if abs(delta) >= _RISK_SPIKE_THRESHOLD:
                spikes: List[Dict] = mem.setdefault("risk_spikes", [])
                spikes.append({
                    "ts": ts, "from": round(prev_risk, 3),
                    "to": round(risk, 3), "msg_count": msg_count
                })
                # Keep last 20 spikes
                mem["risk_spikes"] = spikes[-20:]

        # -------------------------------------------------------------------
        # Route transitions
        # -------------------------------------------------------------------
        route = context_package.get("route", "reception")
        route_history: List[str] = context_package.get("route_history", [])
        transitions: List[Dict] = mem.setdefault("route_transitions", [])
        if len(route_history) >= 2 and route_history[-1] != route_history[-2]:
            transitions.append({
                "ts": ts,
                "from": route_history[-2],
                "to": route_history[-1],
                "reason": session.get("last_route_switch_reason", "unknown"),
                "msg_count": msg_count,
            })
            mem["route_transitions"] = transitions[-30:]

        # -------------------------------------------------------------------
        # Payment events
        # -------------------------------------------------------------------
        payment_status = context_package.get("payment_status", "new")
        payment_events: List[Dict] = mem.setdefault("payment_events", [])
        last_payment_status = mem.get("_last_payment_status", "new")
        if payment_status != last_payment_status:
            payment_events.append({
                "ts": ts, "event": f"status_change:{last_payment_status}->{payment_status}",
                "msg_count": msg_count,
            })
            mem["_last_payment_status"] = payment_status
            mem["payment_events"] = payment_events[-20:]

        # -------------------------------------------------------------------
        # Escalation events
        # -------------------------------------------------------------------
        esc_count = int(context_package.get("escalation_count", 0))
        last_esc = int(mem.get("_last_escalation_count", 0))
        if esc_count > last_esc:
            esc_events: List[Dict] = mem.setdefault("escalation_events", [])
            esc_events.append({
                "ts": ts, "count": esc_count,
                "route": route, "risk": round(risk, 3),
            })
            mem["_last_escalation_count"] = esc_count
            mem["escalation_events"] = esc_events[-10:]

        # -------------------------------------------------------------------
        # Emotional milestones
        # -------------------------------------------------------------------
        if risk >= _RISK_MILESTONE_THRESHOLD:
            milestones: List[Dict] = mem.setdefault("emotional_milestones", [])
            milestone_type = (
                "panic" if risk >= 0.85
                else "crisis" if risk >= 0.75
                else "fear"
            )
            # Only log if not same type as last milestone
            if not milestones or milestones[-1].get("type") != milestone_type:
                milestones.append({
                    "ts": ts, "type": milestone_type,
                    "risk": round(risk, 3), "intent": intent,
                    "msg_count": msg_count,
                })
                mem["emotional_milestones"] = milestones[-20:]

        # -------------------------------------------------------------------
        # Key facts update (client profile facts)
        # -------------------------------------------------------------------
        key_facts: Dict[str, Any] = mem.setdefault("key_facts", {})
        client_data: Dict = context_package.get("client_data") or {}
        for field in ("name", "disease", "tariff", "phone", "email", "age"):
            val = client_data.get(field)
            if val and val != "unknown":
                key_facts[field] = val

        # -------------------------------------------------------------------
        # Overlay tracking
        # -------------------------------------------------------------------
        overlay = context_package.get("overlay_type", "none")
        last_overlays: List[str] = mem.setdefault("last_overlay_types", [])
        last_overlays.append(overlay)
        mem["last_overlay_types"] = last_overlays[-5:]

        # -------------------------------------------------------------------
        # Session summary (for Dashboard)
        # -------------------------------------------------------------------
        mem["last_route"] = route
        mem["last_agent"] = context_package.get("agent", "Lucky")
        mem["last_risk"] = round(risk, 3)
        mem["last_intent"] = intent

        session["long_term_memory"] = mem
        log.debug("[MEMORY] updated: msgs=%d risk=%.2f intent=%s route=%s",
                  mem["total_messages"], risk, intent, route)
        return True

    def get_summary(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a Dashboard-ready summary of client memory.
        """
        mem = session.get("long_term_memory", {})
        return {
            "total_messages":    mem.get("total_messages", 0),
            "first_contact_ts":  mem.get("first_contact_ts"),
            "last_contact_ts":   mem.get("last_contact_ts"),
            "max_risk_score":    mem.get("max_risk_score", 0.0),
            "escalation_count":  len(mem.get("escalation_events", [])),
            "payment_status":    mem.get("_last_payment_status", "new"),
            "key_facts":         mem.get("key_facts", {}),
            "route_transitions": len(mem.get("route_transitions", [])),
            "risk_spikes":       len(mem.get("risk_spikes", [])),
            "last_overlay":      mem.get("last_overlay_types", ["none"])[-1],
            "last_route":        mem.get("last_route", "reception"),
            "last_agent":        mem.get("last_agent", "Lucky"),
        }

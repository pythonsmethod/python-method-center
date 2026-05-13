# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: priority_engine.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Resolve competing signals (interrupt vs route_resolver vs current route)
#          into a single final routing decision.
#          Runs after interrupt_detector, before auto_router.
#
# Priority resolution rules:
#   1. P1 (CRITICAL) interrupts ALWAYS override everything
#   2. P2 (HIGH) interrupts override route_resolver if confidence < 0.80
#   3. P3 (MEDIUM) interrupts override route_resolver if confidence < 0.70
#   4. P4 (LOW) interrupts are advisory only — no route change
#   5. Route_resolver wins if interrupt is None or P0
#   6. Route_lock_manager can block ANY switch (except P1 critical)
#   7. Payment protection: paid user never goes back to reception/individual
#   8. Post-payment: paid users ALWAYS go to onboarding_route if route==reception
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("priority_engine")

# ---------------------------------------------------------------------------
# Interrupt -> Route mapping
# ---------------------------------------------------------------------------
_INTERRUPT_ROUTES: Dict[str, str] = {
    "medical_emergency":     "escalation_route",
    "suicide_risk":          "escalation_route",
    "severe_panic":          "support_route",
    "high_risk_oncology":    "support_route",
    "post_payment_silence":  "onboarding_route",
    "payment_dead_zone":     "payment_route",
    "analysis_overdue":      "analysis_route",
    "trust_broken":          "support_route",
    "payment_stuck":         "payment_route",
    "onboarding_stuck":      "support_route",
    "emotional_spike":       None,  # advisory — no route change
    "confusion_loop":        None,  # advisory
}

_INTERRUPT_AGENTS: Dict[str, str] = {
    "medical_emergency":     "Karen",
    "suicide_risk":          "Karen",
    "severe_panic":          "Karen",
    "high_risk_oncology":    "Nadia",
    "post_payment_silence":  "Iris",
    "payment_dead_zone":     "Maya",
    "analysis_overdue":      "Karen",
    "trust_broken":          "Sophia",
    "payment_stuck":         "Maya",
    "onboarding_stuck":      "Iris",
    "emotional_spike":       None,
    "confusion_loop":        None,
}

# Routes paid users can NEVER be returned to
_PREPAYMENT_ROUTES = {"reception", "individual"}

# ---------------------------------------------------------------------------
# PriorityEngine class
# ---------------------------------------------------------------------------
class PriorityEngine:
    """
    Resolves interrupt + route_resolver signals into a final route/agent decision.

    Returns:
        {
            "route": str,
            "agent": str,
            "source": str  (interrupt | route_resolver | current_route | protected),
            "reason": str,
            "interrupt_applied": bool,
            "payment_protection_applied": bool,
        }
    """

    def rank(
        self,
        interrupt_result: Dict[str, Any],
        route_result: Dict[str, Any],
        context_package: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            return self._rank(interrupt_result, route_result, context_package, session)
        except Exception as e:
            log.error("[PRIORITY] rank error: %s", e)
            current_route = session.get("route", "reception")
            return {
                "route": current_route,
                "agent": session.get("active_agent", "Lucky"),
                "source": "fallback",
                "reason": f"priority error: {e}",
                "interrupt_applied": False,
                "payment_protection_applied": False,
            }

    def _rank(
        self,
        interrupt_result: Dict[str, Any],
        route_result: Dict[str, Any],
        context_package: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_route = session.get("route", "reception")
        current_agent = session.get("active_agent", "Lucky")
        payment_status = context_package.get("payment_status", "new")
        route_locked = context_package.get("route_locked", False)

        interrupt_type = interrupt_result.get("interrupt_type")
        interrupt_priority = int(interrupt_result.get("priority", 0))
        requires_human = interrupt_result.get("requires_human", False)
        requires_immediate = interrupt_result.get("requires_immediate_escalation", False)

        proposed_route = route_result.get("proposed_route", current_route)
        proposed_agent = route_result.get("proposed_agent", current_agent)
        route_confidence = float(route_result.get("route_confidence", 0.0))

        # -------------------------------------------------------------------
        # Rule 1: P1 Critical interrupt (always applies, even if route locked)
        # -------------------------------------------------------------------
        if interrupt_type and interrupt_priority == 1:
            route = _INTERRUPT_ROUTES.get(interrupt_type, "escalation_route")
            agent = _INTERRUPT_AGENTS.get(interrupt_type, "Karen")
            log.info("[PRIORITY] P1 CRITICAL: %s -> route=%s agent=%s", interrupt_type, route, agent)
            return self._result(route, agent, "interrupt",
                f"P1 critical interrupt: {interrupt_type}", True, False)

        # -------------------------------------------------------------------
        # Rule 2: Payment protection — paid user never returns to pre-payment
        # -------------------------------------------------------------------
        if payment_status == "paid" and proposed_route in _PREPAYMENT_ROUTES:
            safe_route = "onboarding_route" if current_route in _PREPAYMENT_ROUTES else current_route
            log.warning("[PRIORITY] payment protection: blocking %s -> %s for paid user",
                        current_route, proposed_route)
            return self._result(safe_route, current_agent, "protected",
                f"Payment protection: paid user cannot return to {proposed_route}", False, True)

        # -------------------------------------------------------------------
        # Rule 3: Post-payment silence fix
        # -------------------------------------------------------------------
        if (payment_status == "paid"
                and current_route in _PREPAYMENT_ROUTES
                and interrupt_type != "post_payment_silence"):
            log.info("[PRIORITY] post-payment fix: moving paid user from %s to onboarding_route", current_route)
            return self._result("onboarding_route", "Iris", "protected",
                "Post-payment: paid user auto-moved to onboarding", False, True)

        # -------------------------------------------------------------------
        # Rule 4: P2 interrupt overrides if confidence < 0.80
        # -------------------------------------------------------------------
        if interrupt_type and interrupt_priority == 2:
            if route_confidence < 0.80 or route_locked:
                route = _INTERRUPT_ROUTES.get(interrupt_type) or current_route
                agent = _INTERRUPT_AGENTS.get(interrupt_type) or current_agent
                log.info("[PRIORITY] P2 interrupt wins: %s -> route=%s", interrupt_type, route)
                return self._result(route, agent, "interrupt",
                    f"P2 interrupt: {interrupt_type} (conf={route_confidence:.2f})", True, False)

        # -------------------------------------------------------------------
        # Rule 5: P3 interrupt overrides if confidence < 0.70
        # -------------------------------------------------------------------
        if interrupt_type and interrupt_priority == 3:
            if route_confidence < 0.70:
                route = _INTERRUPT_ROUTES.get(interrupt_type) or current_route
                agent = _INTERRUPT_AGENTS.get(interrupt_type) or current_agent
                log.info("[PRIORITY] P3 interrupt wins: %s -> route=%s", interrupt_type, route)
                return self._result(route, agent, "interrupt",
                    f"P3 interrupt: {interrupt_type} (conf={route_confidence:.2f})", True, False)

        # -------------------------------------------------------------------
        # Rule 6: Route lock blocks proposed route changes (except P1-2 handled above)
        # -------------------------------------------------------------------
        if route_locked and proposed_route != current_route:
            log.info("[PRIORITY] route locked: keeping %s, blocking %s", current_route, proposed_route)
            return self._result(current_route, current_agent, "current_route",
                f"Route locked, blocking proposed {proposed_route}", False, False)

        # -------------------------------------------------------------------
        # Rule 7: Route resolver wins (normal case)
        # -------------------------------------------------------------------
        if route_confidence >= 0.85 and proposed_route != current_route:
            log.info("[PRIORITY] route_resolver wins: %s -> %s (conf=%.2f)",
                     current_route, proposed_route, route_confidence)
            return self._result(proposed_route, proposed_agent, "route_resolver",
                f"route_resolver: {proposed_route} (conf={route_confidence:.2f})", False, False)

        # -------------------------------------------------------------------
        # Rule 8: Stay on current route (default)
        # -------------------------------------------------------------------
        return self._result(current_route, current_agent, "current_route",
            "Staying on current route (no override signal)", False, False)

    def _result(
        self,
        route: str,
        agent: str,
        source: str,
        reason: str,
        interrupt_applied: bool,
        payment_protection: bool,
    ) -> Dict[str, Any]:
        return {
            "route": route,
            "agent": agent,
            "source": source,
            "reason": reason,
            "interrupt_applied": interrupt_applied,
            "payment_protection_applied": payment_protection,
        }

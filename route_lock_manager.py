# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: route_lock_manager.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Enforce route stability by locking routes for N messages after a switch.
#          Prevents oscillation, premature exits from critical flows, and
#          paid-user rollbacks to pre-payment routes.
#
# Lock rules:
#   DEFAULT_LOCK_MSGS = 3     — any route switch locks for 3 msgs
#   PAYMENT_LOCK_MSGS = 5     — payment_route locks for 5 msgs
#   ONBOARDING_LOCK_MSGS = 7  — onboarding_route locks for 7 msgs
#   ANALYSIS_LOCK_MSGS = 5    — analysis_route locks for 5 msgs
#   ESCALATION_LOCK_MSGS = 10 — escalation_route locks for 10 msgs (breakable only by human)
#
# Lock breakers (routes that can always override a lock):
#   - escalation_route  (P1 always wins)
#   - recovery_route    (explicit re-engagement)
#
# Paid user protection:
#   - onboarding_route, analysis_route, support_route are LOCKED for paid users
#     against rollback to reception / individual / payment_route
#
# Session fields used:
#   route_lock_until_msg      int   (msg_count when lock expires)
#   route_lock_reason         str
#   route_lock_set_at_msg     int
#   msgs_since_route_change   int
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger("route_lock_manager")

# ---------------------------------------------------------------------------
# Lock durations per route (messages)
# ---------------------------------------------------------------------------
_LOCK_MSGS: Dict[str, int] = {
    "reception":         2,
    "individual":        3,
    "payment_route":     5,
    "payment":           5,
    "onboarding_route":  7,
    "onboarding":        7,
    "analysis_route":    5,
    "analysis":          5,
    "support_route":     4,
    "support":           4,
    "faq_route":         2,
    "trust_route":       5,
    "escalation_route":  10,
    "escalation":        10,
    "recovery_route":    3,
}

_DEFAULT_LOCK = 3

# Routes that can always break any lock (highest priority)
_LOCK_BREAKERS = {"escalation_route", "escalation", "recovery_route"}

# Pre-payment routes — paid users must be protected from returning here
_PRE_PAYMENT_ROUTES = {"reception", "individual", "payment_route", "payment"}

# Paid-user stable routes (lock prevents rollback from these)
_PAID_STABLE_ROUTES = {
    "onboarding_route", "onboarding",
    "analysis_route", "analysis",
    "support_route", "support",
    "trust_route",
}


# ---------------------------------------------------------------------------
# RouteLockManager class
# ---------------------------------------------------------------------------
class RouteLockManager:
    """
    Manages route locks to prevent oscillation and protect critical flows.

    Usage:
        lock_mgr = RouteLockManager()

        # Check if current route is locked
        result = lock_mgr.check(session)
        if result["locked"]:
            # Do not apply proposed route change

        # Apply a lock after a route switch
        lock_mgr.apply_lock(session, new_route)

        # Increment message counter (call after each message)
        lock_mgr.increment(session)
    """

    def check(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if the current route is locked against switching.

        Returns:
            {
                "locked": bool,
                "reason": str,
                "lock_expires_in": int  (messages remaining),
                "can_break_with": list[str]  (routes that break this lock),
            }
        """
        try:
            return self._check(session)
        except Exception as e:
            log.error("[LOCK] check error: %s", e)
            return {"locked": False, "reason": f"error: {e}", "lock_expires_in": 0, "can_break_with": list(_LOCK_BREAKERS)}

    def _check(self, session: Dict[str, Any]) -> Dict[str, Any]:
        msg_count = int(session.get("msg_count", 0))
        lock_until = int(session.get("route_lock_until_msg", 0))
        lock_reason = session.get("route_lock_reason", "")
        payment_status = session.get("payment_status", "new")
        current_route = session.get("route", "reception")

        # Paid user protection lock (permanent for pre-payment rollback)
        if payment_status == "paid" and current_route in _PAID_STABLE_ROUTES:
            proposed = session.get("proposed_route", current_route)
            if proposed in _PRE_PAYMENT_ROUTES:
                log.warning("[LOCK] paid user protection: blocking rollback %s -> %s",
                            current_route, proposed)
                return {
                    "locked": True,
                    "reason": f"paid_user_protection: cannot return to {proposed}",
                    "lock_expires_in": 9999,
                    "can_break_with": list(_LOCK_BREAKERS),
                }

        # Standard time-based lock
        if msg_count < lock_until:
            remaining = lock_until - msg_count
            log.debug("[LOCK] route locked (%d msgs remaining): %s", remaining, lock_reason)
            return {
                "locked": True,
                "reason": lock_reason,
                "lock_expires_in": remaining,
                "can_break_with": list(_LOCK_BREAKERS),
            }

        return {
            "locked": False,
            "reason": "",
            "lock_expires_in": 0,
            "can_break_with": list(_LOCK_BREAKERS),
        }

    def apply_lock(
        self,
        session: Dict[str, Any],
        new_route: str,
        reason: str = "route_switch",
        override_duration: int = None,
    ) -> None:
        """
        Apply a route lock after a route switch.
        Call this whenever auto_router or priority_engine switches the route.
        """
        try:
            msg_count = int(session.get("msg_count", 0))
            duration = override_duration or _LOCK_MSGS.get(new_route, _DEFAULT_LOCK)
            lock_until = msg_count + duration

            session["route_lock_until_msg"] = lock_until
            session["route_lock_reason"] = f"{reason} -> {new_route}"
            session["route_lock_set_at_msg"] = msg_count
            session["route_locked"] = True

            log.info("[LOCK] applied: route=%s lock_until_msg=%d duration=%d reason=%s",
                     new_route, lock_until, duration, reason)
        except Exception as e:
            log.error("[LOCK] apply_lock error: %s", e)

    def release_lock(self, session: Dict[str, Any]) -> None:
        """Manually release a route lock (e.g., after human escalation resolved)."""
        session["route_lock_until_msg"] = 0
        session["route_lock_reason"] = ""
        session["route_locked"] = False
        log.info("[LOCK] lock manually released")

    def increment(self, session: Dict[str, Any]) -> None:
        """
        Increment msgs_since_route_change counter.
        Also auto-release expired locks.
        """
        try:
            msg_count = int(session.get("msg_count", 0))
            lock_until = int(session.get("route_lock_until_msg", 0))

            session["msgs_since_route_change"] = session.get("msgs_since_route_change", 0) + 1

            # Auto-release expired lock
            if msg_count >= lock_until and session.get("route_locked"):
                session["route_locked"] = False
                log.debug("[LOCK] auto-released at msg_count=%d", msg_count)
        except Exception as e:
            log.error("[LOCK] increment error: %s", e)

    def on_route_switch(
        self,
        session: Dict[str, Any],
        old_route: str,
        new_route: str,
        reason: str = "auto_switch",
    ) -> None:
        """
        Call this whenever a route switch is confirmed (after guards pass).
        Resets msgs_since_route_change and applies new lock.
        """
        try:
            session["msgs_since_route_change"] = 0
            session["last_route_switch_reason"] = reason
            session["route_switch_from"] = old_route
            self.apply_lock(session, new_route, reason)
            log.info("[LOCK] route_switch: %s -> %s (%s)", old_route, new_route, reason)
        except Exception as e:
            log.error("[LOCK] on_route_switch error: %s", e)

    def can_switch_to(
        self,
        session: Dict[str, Any],
        proposed_route: str,
    ) -> Dict[str, Any]:
        """
        Convenience: check if switching to proposed_route is allowed right now.
        Returns {allowed: bool, reason: str}
        """
        # Lock breakers always allowed
        if proposed_route in _LOCK_BREAKERS:
            return {"allowed": True, "reason": "lock_breaker"}

        lock_result = self.check(session)
        if lock_result["locked"]:
            return {
                "allowed": False,
                "reason": lock_result["reason"],
                "expires_in": lock_result["lock_expires_in"],
            }

        return {"allowed": True, "reason": "no_lock"}

# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.1 — Persistent Memory & Infrastructure Core
# Module: dashboard_data.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Dashboard Data Exposure Layer
#
# Purpose: Unified read API for Anna Dashboard.
#          All Dashboard queries go through this module.
#          Returns clean, structured data ready for frontend rendering.
#
# Available APIs:
#   get_overview()                — system-wide health + stats
#   get_client_list()             — all active clients with risk scores
#   get_client_detail(user_id)    — full client profile + timeline
#   get_risk_dashboard()          — at-risk clients + predictions
#   get_escalation_feed()         — recent escalations
#   get_timeline_feed(user_id)    — client event timeline
#   get_orchestration_stats()     — pipeline performance metrics
#   get_queue_stats()             — async queue status
#   get_memory_stats(user_id)     — memory tier summary
#   get_recovery_plans()          — active recovery workflows
#   get_runtime_health()          — subsystem health grid
# =============================================================================

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("dashboard_data")


class DashboardData:
    """
    Read-only data exposure layer for Anna Dashboard.
    All methods are async. All return plain dicts/lists.
    Never writes — only reads from the database.
    """

    def __init__(self, db_pool=None):
        self._pool = db_pool
        log.info("[DASHBOARD] DashboardData initialized")

    # -----------------------------------------------------------------------
    # 1. System Overview
    # -----------------------------------------------------------------------

    async def get_overview(self) -> Dict[str, Any]:
        """Return system-wide health + aggregate stats."""
        if not self._pool:
            return {"error": "no_db"}
        try:
            async with self._pool.acquire() as conn:
                # Client counts
                total_clients = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_client_profiles WHERE is_active=TRUE"
                )
                paid_clients = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_client_profiles"
                    " WHERE payment_status='paid' AND is_active=TRUE"
                )
                at_risk = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_client_profiles"
                    " WHERE current_risk_level IN ('high','critical') AND is_active=TRUE"
                )
                # Today's messages
                todays_msgs = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_memory_timeline"
                    " WHERE ts >= NOW() - INTERVAL '24 hours'"
                    "   AND event_type = 'message_in'"
                )
                # Active escalations
                escalations = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_orchestration_events"
                    " WHERE escalated=TRUE AND ts >= NOW() - INTERVAL '24 hours'"
                )
                # Queue depth
                queue_depth = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_queue_jobs WHERE status='pending'::job_status"
                )
                # Recovery plans active
                recovery_active = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_recovery_plans"
                    " WHERE status IN ('pending','in_progress')"
                )
                # Avg processing time today
                avg_ms = await conn.fetchval(
                    "SELECT AVG(processing_ms) FROM pm_orchestration_events"
                    " WHERE ts >= NOW() - INTERVAL '1 hour'"
                )

            return {
                "clients": {
                    "total": int(total_clients or 0),
                    "paid": int(paid_clients or 0),
                    "at_risk": int(at_risk or 0),
                },
                "activity": {
                    "messages_24h": int(todays_msgs or 0),
                    "escalations_24h": int(escalations or 0),
                    "queue_depth": int(queue_depth or 0),
                    "recovery_plans_active": int(recovery_active or 0),
                },
                "performance": {
                    "avg_processing_ms": round(float(avg_ms or 0), 1),
                },
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            log.error("[DASHBOARD] get_overview error: %s", e)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 2. Client list
    # -----------------------------------------------------------------------

    async def get_client_list(
        self, limit: int = 50, filter_risk: str = None, filter_payment: str = None
    ) -> List[Dict[str, Any]]:
        """Return list of clients with key indicators."""
        if not self._pool:
            return []
        try:
            conditions = ["cp.is_active = TRUE"]
            if filter_risk:
                conditions.append(f"cp.current_risk_level = '{filter_risk}'")
            if filter_payment:
                conditions.append(f"cp.payment_status = '{filter_payment}'")
            where = " AND ".join(conditions)

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT cp.user_id, cp.display_name, cp.payment_status,"
                    f" cp.current_risk_level, cp.last_contact_at,"
                    f" cp.last_active_route, cp.last_active_agent,"
                    f" cp.escalation_count, cp.total_messages,"
                    f" cp.onboarding_completed, cp.active_tariff,"
                    f" rp.current_risk, rp.spike_probability, rp.trend"
                    f" FROM pm_client_profiles cp"
                    f" LEFT JOIN pm_risk_predictions rp"
                    f"   ON rp.user_id = cp.user_id AND rp.is_current = TRUE"
                    f" WHERE {where}"
                    f" ORDER BY cp.current_risk_level DESC, cp.last_contact_at DESC"
                    f" LIMIT {limit}",
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.error("[DASHBOARD] get_client_list error: %s", e)
            return []

    # -----------------------------------------------------------------------
    # 3. Client detail
    # -----------------------------------------------------------------------

    async def get_client_detail(self, user_id: int) -> Dict[str, Any]:
        """Return full client profile + recent timeline."""
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                # Profile
                profile = await conn.fetchrow(
                    "SELECT * FROM pm_client_profiles WHERE user_id=$1",
                    user_id
                )
                if not profile:
                    return {"error": "client_not_found"}

                # Short-term memory
                stm = await conn.fetchrow(
                    "SELECT context_snippet, peak_risk, routes_visited,"
                    " emotional_arc, message_count FROM pm_memory_short_term"
                    " WHERE user_id=$1 AND is_current=TRUE LIMIT 1",
                    user_id
                )

                # Active stage
                stage = await conn.fetchrow(
                    "SELECT stage_name, progress_pct, next_action, goals"
                    " FROM pm_memory_active_stage WHERE user_id=$1 AND is_current=TRUE LIMIT 1",
                    user_id
                )

                # Recent timeline
                timeline = await conn.fetch(
                    "SELECT id, ts, event_type, summary, priority, route, agent,"
                    " risk_score, overlay_type FROM pm_memory_timeline"
                    " WHERE user_id=$1 ORDER BY ts DESC LIMIT 20",
                    user_id
                )

                # Active recovery plan
                recovery = await conn.fetchrow(
                    "SELECT plan_type, trigger_type, status, current_step, total_steps,"
                    " next_action_at FROM pm_recovery_plans"
                    " WHERE user_id=$1 AND status IN ('pending','in_progress') LIMIT 1",
                    user_id
                )

            return {
                "profile": dict(profile),
                "short_term": dict(stm) if stm else None,
                "active_stage": dict(stage) if stage else None,
                "timeline": [dict(r) for r in timeline],
                "recovery_plan": dict(recovery) if recovery else None,
            }
        except Exception as e:
            log.error("[DASHBOARD] get_client_detail error user=%d: %s", user_id, e)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 4. Risk dashboard
    # -----------------------------------------------------------------------

    async def get_risk_dashboard(self) -> Dict[str, Any]:
        """Return at-risk clients + risk predictions."""
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                at_risk = await conn.fetch(
                    "SELECT cp.user_id, cp.display_name, cp.current_risk_level,"
                    " cp.last_contact_at, cp.last_active_route,"
                    " rp.current_risk, rp.spike_probability, rp.trend,"
                    " rp.recommended_route, rp.recommended_agent,"
                    " rp.recommended_actions"
                    " FROM pm_client_profiles cp"
                    " LEFT JOIN pm_risk_predictions rp"
                    "   ON rp.user_id = cp.user_id AND rp.is_current=TRUE"
                    " WHERE cp.current_risk_level IN ('medium','high','critical')"
                    "    OR rp.spike_probability > 0.40"
                    " ORDER BY rp.current_risk DESC NULLS LAST LIMIT 20",
                )

                recent_spikes = await conn.fetch(
                    "SELECT user_id, ts, risk_score, intent, route, agent, summary"
                    " FROM pm_memory_timeline"
                    " WHERE event_type='risk_spike'"
                    "   AND ts >= NOW() - INTERVAL '48 hours'"
                    " ORDER BY ts DESC LIMIT 10",
                )

            return {
                "at_risk_clients": [dict(r) for r in at_risk],
                "recent_spikes": [dict(r) for r in recent_spikes],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            log.error("[DASHBOARD] get_risk_dashboard error: %s", e)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 5. Escalation feed
    # -----------------------------------------------------------------------

    async def get_escalation_feed(self, hours: int = 48) -> List[Dict[str, Any]]:
        """Return recent escalation events."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT t.user_id, cp.display_name, t.ts, t.summary,"
                    " t.risk_score, t.route, t.agent, t.details"
                    " FROM pm_memory_timeline t"
                    " LEFT JOIN pm_client_profiles cp ON cp.user_id = t.user_id"
                    " WHERE t.event_type='escalation_triggered'"
                    "   AND t.ts >= NOW() - ($1 * INTERVAL '1 hour')"
                    " ORDER BY t.ts DESC LIMIT 50",
                    hours
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.error("[DASHBOARD] get_escalation_feed error: %s", e)
            return []

    # -----------------------------------------------------------------------
    # 6. Orchestration stats
    # -----------------------------------------------------------------------

    async def get_orchestration_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Return orchestration pipeline performance metrics."""
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                # Route distribution
                routes = await conn.fetch(
                    "SELECT route, COUNT(*) as cnt FROM pm_orchestration_events"
                    " WHERE ts >= NOW() - ($1 * INTERVAL '1 hour')"
                    " GROUP BY route ORDER BY cnt DESC",
                    hours
                )
                # Agent distribution
                agents = await conn.fetch(
                    "SELECT agent, COUNT(*) as cnt FROM pm_orchestration_events"
                    " WHERE ts >= NOW() - ($1 * INTERVAL '1 hour')"
                    " GROUP BY agent ORDER BY cnt DESC",
                    hours
                )
                # Performance
                perf = await conn.fetchrow(
                    "SELECT COUNT(*) as total, AVG(processing_ms) as avg_ms,"
                    " MAX(processing_ms) as max_ms, MIN(processing_ms) as min_ms,"
                    " SUM(CASE WHEN escalated THEN 1 ELSE 0 END) as escalations,"
                    " SUM(CASE WHEN route_switched THEN 1 ELSE 0 END) as switches"
                    " FROM pm_orchestration_events"
                    " WHERE ts >= NOW() - ($1 * INTERVAL '1 hour')",
                    hours
                )

            return {
                "routes": [dict(r) for r in routes],
                "agents": [dict(r) for r in agents],
                "performance": dict(perf) if perf else {},
                "period_hours": hours,
            }
        except Exception as e:
            log.error("[DASHBOARD] get_orchestration_stats error: %s", e)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 7. Queue stats
    # -----------------------------------------------------------------------

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Return async queue status."""
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT queue_name, job_type, status, COUNT(*) as cnt,"
                    " AVG(EXTRACT(EPOCH FROM (COALESCE(completed_at,NOW())-created_at))) as avg_s"
                    " FROM pm_queue_jobs"
                    " WHERE created_at > NOW() - INTERVAL '24 hours'"
                    " GROUP BY queue_name, job_type, status"
                    " ORDER BY queue_name, job_type",
                )
                return {"jobs": [dict(r) for r in rows]}
        except Exception as e:
            log.error("[DASHBOARD] get_queue_stats error: %s", e)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 8. Recovery plans
    # -----------------------------------------------------------------------

    async def get_recovery_plans(self) -> List[Dict[str, Any]]:
        """Return active recovery plans."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT rp.plan_id, rp.user_id, cp.display_name,"
                    " rp.trigger_type, rp.plan_type, rp.status,"
                    " rp.current_step, rp.total_steps, rp.next_action_at,"
                    " rp.created_at, rp.client_responded"
                    " FROM pm_recovery_plans rp"
                    " LEFT JOIN pm_client_profiles cp ON cp.user_id = rp.user_id"
                    " WHERE rp.status IN ('pending','in_progress')"
                    " ORDER BY rp.next_action_at NULLS LAST LIMIT 50",
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.error("[DASHBOARD] get_recovery_plans error: %s", e)
            return []

    # -----------------------------------------------------------------------
    # 9. Runtime health
    # -----------------------------------------------------------------------

    async def get_runtime_health(self) -> Dict[str, Any]:
        """Return latest health metrics per subsystem."""
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT DISTINCT ON (subsystem) subsystem, status,"
                    " latency_ms, error_rate, circuit_state, recorded_at"
                    " FROM pm_runtime_health"
                    " ORDER BY subsystem, recorded_at DESC",
                )
                overall = "ok"
                systems = [dict(r) for r in rows]
                if any(s["status"] in ("critical","down") for s in systems):
                    overall = "critical"
                elif any(s["status"] == "degraded" for s in systems):
                    overall = "degraded"
                return {"overall": overall, "subsystems": systems}
        except Exception as e:
            log.error("[DASHBOARD] get_runtime_health error: %s", e)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 10. Timeline feed
    # -----------------------------------------------------------------------

    async def get_timeline_feed(
        self, user_id: int = None, limit: int = 50,
        event_types: List[str] = None, min_priority: int = 0
    ) -> List[Dict[str, Any]]:
        """Return timeline events for Dashboard feed."""
        if not self._pool:
            return []
        try:
            conditions = [f"priority >= {min_priority}"]
            if user_id:
                conditions.append(f"user_id = {user_id}")
            if event_types:
                et_list = ",".join(f"'{e}'" for e in event_types)
                conditions.append(f"event_type IN ({et_list})")
            where = " AND ".join(conditions)

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT id, user_id, ts, event_type, summary, priority,"
                    f" route, agent, risk_score, overlay_type, intent"
                    f" FROM pm_memory_timeline"
                    f" WHERE {where}"
                    f" ORDER BY ts DESC LIMIT {limit}",
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.error("[DASHBOARD] get_timeline_feed error: %s", e)
            return []


    # -----------------------------------------------------------------------
    # 11. Risk Intelligence (Phase 3.2)
    # -----------------------------------------------------------------------

    async def get_risk_intelligence(self) -> Dict[str, Any]:
        """Full risk dashboard: high-risk clients, by type, by route, trends, unresolved."""
        from risk_predictor import get_risk_predictor
        predictor = get_risk_predictor()
        if not predictor or not self._pool:
            return {"error": "risk_predictor not initialized"}
        try:
            high_risk   = await predictor.get_high_risk_clients(limit=50)
            by_type     = await predictor.get_risk_by_type()
            unresolved  = await predictor.get_unresolved_risks()
            by_route    = await self._get_risk_by_route()
            by_stage    = await self._get_risk_by_stage()
            trends      = await self._get_risk_trends()
            critical    = [r for r in unresolved if r.get("risk_level") in ("high","critical")]
            return {
                "high_risk_clients":    high_risk,
                "risk_by_type":         by_type,
                "risk_by_route":        by_route,
                "risk_by_stage":        by_stage,
                "risk_trends":          trends,
                "unresolved_risks":     unresolved,
                "critical_escalations": critical,
                "summary": {
                    "total_unresolved":  len(unresolved),
                    "total_critical":    len(critical),
                    "total_high_risk":   len(high_risk),
                },
            }
        except Exception as e:
            log.error("[DASHBOARD] get_risk_intelligence error: %s", e)
            return {"error": str(e)}

    async def _get_risk_by_route(self) -> List[Dict]:
        """Risk aggregated by last known route."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT
                         cp.current_stage AS route,
                         rp.risk_level,
                         COUNT(*) AS count,
                         AVG(rp.current_risk_score) AS avg_score
                       FROM pm_risk_predictions rp
                       LEFT JOIN pm_client_profiles cp ON cp.user_id = rp.user_id
                       WHERE rp.resolved_at IS NULL
                       GROUP BY cp.current_stage, rp.risk_level
                       ORDER BY count DESC"""
                )
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("[DASHBOARD] _get_risk_by_route error: %s", e)
            return []

    async def _get_risk_by_stage(self) -> List[Dict]:
        """Risk aggregated by client onboarding stage."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT
                         COALESCE(cp.current_stage, 'unknown') AS stage,
                         COUNT(*) AS total_risks,
                         COUNT(*) FILTER (WHERE rp.risk_level IN ('high','critical')) AS high_count,
                         AVG(rp.current_risk_score) AS avg_score
                       FROM pm_risk_predictions rp
                       LEFT JOIN pm_client_profiles cp ON cp.user_id = rp.user_id
                       WHERE rp.resolved_at IS NULL
                       GROUP BY cp.current_stage
                       ORDER BY high_count DESC"""
                )
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("[DASHBOARD] _get_risk_by_stage error: %s", e)
            return []

    async def _get_risk_trends(self, days: int = 7) -> List[Dict]:
        """Risk counts per day for the last N days."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT
                         DATE_TRUNC('day', created_at) AS day,
                         risk_level,
                         COUNT(*) AS count
                       FROM pm_risk_predictions
                       WHERE created_at >= NOW() - INTERVAL '7 days'
                       GROUP BY day, risk_level
                       ORDER BY day DESC, risk_level"""
                )
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("[DASHBOARD] _get_risk_trends error: %s", e)
            return []


    async def get_recovery_governance(self) -> Dict[str, Any]:
        """
        Expose recovery policy governance data for the dashboard.
        Integrates RecoveryPolicyEngine.get_dashboard_data().
        """
        try:
            from recovery_policy_engine import get_recovery_policy_engine
            engine = get_recovery_policy_engine()
            if engine:
                return await engine.get_dashboard_data()
        except Exception as e:
            log.error("[DASHBOARD] get_recovery_governance error: %s", e)
        # Fallback: query directly from DB if engine not available
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                silence_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_client_profiles"
                    " WHERE silence_respect=TRUE AND is_active=TRUE"
                )
                cooldown_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_recovery_policy_log"
                    " WHERE cooldown_until > NOW() AND action != 'ALLOW'"
                )
                escalation_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_recovery_policy_log"
                    " WHERE human_escalation_required=TRUE"
                    " AND created_at > NOW() - INTERVAL '24 hours'"
                )
                recent_actions = await conn.fetch(
                    "SELECT action, COUNT(*) AS count"
                    " FROM pm_recovery_policy_log"
                    " WHERE created_at > NOW() - INTERVAL '24 hours'"
                    " GROUP BY action ORDER BY count DESC"
                )
            return {
                "silence_respect_count":  int(silence_count or 0),
                "active_cooldown_count":  int(cooldown_count or 0),
                "human_escalation_24h":   int(escalation_count or 0),
                "policy_actions_24h":     [dict(r) for r in recent_actions],
            }
        except Exception as e:
            log.error("[DASHBOARD] get_recovery_governance fallback error: %s", e)
            return {}

    async def get_silent_scanner_stats(self) -> dict:
        """Return Silent User Scanner stats for dashboard exposure."""
        try:
            from silent_user_scanner import get_scanner
            scanner = get_scanner()
            if not scanner:
                return {"error": "scanner_not_initialized"}
            return scanner.get_scanner_stats()
        except Exception as e:
            log.error("[DASHBOARD] get_silent_scanner_stats error: %s", e)
            return {}


    async def get_behaviour_stats(self) -> dict:
        """Return Adaptive Behaviour Engine stats for dashboard exposure."""
        try:
            from adaptive_behaviour_engine import get_behaviour_engine
            engine = get_behaviour_engine()
            if not engine:
                return {"error": "behaviour_engine_not_initialized"}
            return engine.get_engine_stats()
        except Exception as e:
            log.error("[DASHBOARD] get_behaviour_stats error: %s", e)
            return {}


_dashboard: Optional[DashboardData] = None

def get_dashboard() -> DashboardData:
    global _dashboard
    if _dashboard is None:
        _dashboard = DashboardData()
    return _dashboard

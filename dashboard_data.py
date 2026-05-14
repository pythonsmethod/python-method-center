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


    async def get_continuity_stats(self) -> dict:
        """Return Clinical Continuity Engine stats for dashboard exposure."""
        try:
            from clinical_continuity_engine import get_continuity_engine
            engine = get_continuity_engine()
            if not engine:
                return {"error": "continuity_engine_not_initialized"}
            try:
                from main import get_db_pool
                pool = get_db_pool()
            except Exception:
                pool = None
            import asyncio
            return asyncio.get_event_loop().run_until_complete(engine.get_engine_stats(pool))
        except Exception as e:
            log.error("[DASHBOARD] get_continuity_stats error: %s", e)
            return {}



    async def get_trajectory_stats(self) -> dict:
        """Return Trajectory Intelligence Engine stats for dashboard."""
        try:
            from trajectory_intelligence_engine import get_trajectory_engine
            engine = get_trajectory_engine()
            if not engine:
                return {"status": "not_initialized"}
            pool = self._pool
            if not pool:
                return {"status": "no_db"}
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE trajectory_state = 'accelerating_progression') AS accelerating,
                        COUNT(*) FILTER (WHERE trajectory_state = 'steady_progression') AS steady,
                        COUNT(*) FILTER (WHERE trajectory_state = 'stable_plateau') AS plateau,
                        COUNT(*) FILTER (WHERE trajectory_state = 'oscillating_active') AS oscillating_active,
                        COUNT(*) FILTER (WHERE trajectory_state = 'oscillating_at_risk') AS oscillating_at_risk,
                        COUNT(*) FILTER (WHERE trajectory_state = 'follow_through_gap') AS follow_through_gap,
                        COUNT(*) FILTER (WHERE trajectory_state = 'coherence_break') AS coherence_break,
                        COUNT(*) FILTER (WHERE trajectory_state = 'degrading') AS degrading,
                        COUNT(*) FILTER (WHERE trajectory_state = 'disengagement_trajectory') AS disengagement,
                        COUNT(*) FILTER (WHERE trajectory_state = 'needs_trajectory_review') AS needs_review,
                        COUNT(*) FILTER (WHERE trajectory_gap_detected = TRUE) AS gap_detected,
                        ROUND(AVG(trajectory_score)::numeric, 4) AS avg_score,
                        COUNT(*) FILTER (WHERE trajectory_direction = 'improving') AS improving,
                        COUNT(*) FILTER (WHERE trajectory_direction = 'declining') AS declining,
                        COUNT(*) FILTER (WHERE trajectory_direction = 'stable') AS stable,
                        COUNT(*) FILTER (WHERE last_trajectory_check IS NOT NULL) AS evaluated_total
                    FROM pm_client_profiles
                """)
                return {
                    "status": "ok",
                    "states": {
                        "accelerating_progression":  int(row["accelerating"] or 0),
                        "steady_progression":         int(row["steady"] or 0),
                        "stable_plateau":             int(row["plateau"] or 0),
                        "oscillating_active":         int(row["oscillating_active"] or 0),
                        "oscillating_at_risk":        int(row["oscillating_at_risk"] or 0),
                        "follow_through_gap":         int(row["follow_through_gap"] or 0),
                        "coherence_break":            int(row["coherence_break"] or 0),
                        "degrading":                  int(row["degrading"] or 0),
                        "disengagement_trajectory":   int(row["disengagement"] or 0),
                        "needs_trajectory_review":    int(row["needs_review"] or 0),
                    },
                    "gap_detected_count": int(row["gap_detected"] or 0),
                    "avg_trajectory_score": float(row["avg_score"] or 0),
                    "directions": {
                        "improving": int(row["improving"] or 0),
                        "declining": int(row["declining"] or 0),
                        "stable":    int(row["stable"] or 0),
                    },
                    "evaluated_total": int(row["evaluated_total"] or 0),
                }
        except Exception as e:
            log.warning("[DASHBOARD] get_trajectory_stats error: %s", e)
            return {}


    async def get_state_machine_stats(self) -> dict:
        """Return Rehabilitation State Machine stats for dashboard."""
        try:
            from rehabilitation_state_machine import get_state_machine
            sm = get_state_machine()
            if not sm:
                return {"status": "not_initialized"}
            pool = self._pool
            if not pool:
                return {"status": "no_db"}
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'initial_contact') AS initial_contact,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'needs_assessment') AS needs_assessment,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'awaiting_consultation') AS awaiting_consultation,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'consultation_active') AS consultation_active,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'awaiting_analysis') AS awaiting_analysis,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'analysis_review') AS analysis_review,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'treatment_planning') AS treatment_planning,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'treatment_active') AS treatment_active,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'monitoring') AS monitoring,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'follow_up') AS follow_up,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'maintenance') AS maintenance,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'paused') AS paused,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'stalled') AS stalled,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'lost_to_follow_up') AS lost_to_follow_up,
                        COUNT(*) FILTER (WHERE rehabilitation_state = 'completed') AS completed,
                        COUNT(*) FILTER (WHERE stage_stall_detected = TRUE) AS stall_count,
                        COUNT(*) FILTER (WHERE progression_gate_status = 'open') AS gate_open,
                        COUNT(*) FILTER (WHERE progression_gate_status = 'closed') AS gate_closed,
                        COUNT(*) FILTER (WHERE escalation_gate_status IN ('flagged','active')) AS escalation_flagged,
                        ROUND(AVG(stage_completion_score)::numeric, 4) AS avg_completion_score,
                        COUNT(*) FILTER (WHERE rehabilitation_stage = 'intake') AS stage_intake,
                        COUNT(*) FILTER (WHERE rehabilitation_stage = 'diagnostic') AS stage_diagnostic,
                        COUNT(*) FILTER (WHERE rehabilitation_stage = 'intervention') AS stage_intervention,
                        COUNT(*) FILTER (WHERE rehabilitation_stage = 'continuity') AS stage_continuity
                    FROM pm_client_profiles
                """)
                return {
                    "status": "ok",
                    "states": {
                        "initial_contact":       int(row["initial_contact"] or 0),
                        "needs_assessment":      int(row["needs_assessment"] or 0),
                        "awaiting_consultation": int(row["awaiting_consultation"] or 0),
                        "consultation_active":   int(row["consultation_active"] or 0),
                        "awaiting_analysis":     int(row["awaiting_analysis"] or 0),
                        "analysis_review":       int(row["analysis_review"] or 0),
                        "treatment_planning":    int(row["treatment_planning"] or 0),
                        "treatment_active":      int(row["treatment_active"] or 0),
                        "monitoring":            int(row["monitoring"] or 0),
                        "follow_up":             int(row["follow_up"] or 0),
                        "maintenance":           int(row["maintenance"] or 0),
                        "paused":                int(row["paused"] or 0),
                        "stalled":               int(row["stalled"] or 0),
                        "lost_to_follow_up":     int(row["lost_to_follow_up"] or 0),
                        "completed":             int(row["completed"] or 0),
                    },
                    "stages": {
                        "intake":       int(row["stage_intake"] or 0),
                        "diagnostic":   int(row["stage_diagnostic"] or 0),
                        "intervention": int(row["stage_intervention"] or 0),
                        "continuity":   int(row["stage_continuity"] or 0),
                    },
                    "stall_count":         int(row["stall_count"] or 0),
                    "gate_open":           int(row["gate_open"] or 0),
                    "gate_closed":         int(row["gate_closed"] or 0),
                    "escalation_flagged":  int(row["escalation_flagged"] or 0),
                    "avg_completion_score": float(row["avg_completion_score"] or 0),
                }
        except Exception as e:
            log.warning("[DASHBOARD] get_state_machine_stats error: %s", e)
            return {}

    async def get_multi_stage_orchestration_stats(self) -> dict:
        """Return Multi-Stage Orchestration Engine stats for dashboard."""
        try:
            from multi_stage_orchestration_engine import get_orchestration_engine
            eng = get_orchestration_engine()
            if not eng:
                return {"status": "not_initialized"}
            pool = self._pool
            if not pool:
                return {"status": "no_db"}
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE orchestration_state = 'CLEAR')             AS clear_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'MULTI_ACTIVE')       AS multi_active_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'CONFLICT')           AS conflict_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'OVERLOADED')         AS overloaded_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'HANDOFF_READY')      AS handoff_ready_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'BLOCKED')            AS blocked_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'ESCALATION_NEEDED')  AS escalation_needed_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'UNKNOWN')            AS unknown_count,
                        COUNT(*) FILTER (WHERE stage_conflict_detected = TRUE)             AS conflict_total,
                        COUNT(*) FILTER (WHERE handoff_ready = TRUE)                       AS handoff_total,
                        COUNT(*) FILTER (WHERE route_overload_score >= 0.70)               AS high_overload_count,
                        AVG(route_overload_score) FILTER (WHERE route_overload_score > 0)  AS avg_overload_score,
                        COUNT(*) FILTER (WHERE last_orchestration_check IS NOT NULL)       AS evaluated_count
                    FROM pm_client_profiles
                """)
                if not row:
                    return {}
                return {
                    "status": "ok",
                    "orchestration_states": {
                        "clear":             int(row["clear_count"] or 0),
                        "multi_active":      int(row["multi_active_count"] or 0),
                        "conflict":          int(row["conflict_count"] or 0),
                        "overloaded":        int(row["overloaded_count"] or 0),
                        "handoff_ready":     int(row["handoff_ready_count"] or 0),
                        "blocked":           int(row["blocked_count"] or 0),
                        "escalation_needed": int(row["escalation_needed_count"] or 0),
                        "unknown":           int(row["unknown_count"] or 0),
                    },
                    "conflict_total":      int(row["conflict_total"] or 0),
                    "handoff_total":       int(row["handoff_total"] or 0),
                    "high_overload_count": int(row["high_overload_count"] or 0),
                    "avg_overload_score":  float(row["avg_overload_score"] or 0.0),
                    "evaluated_count":     int(row["evaluated_count"] or 0),
                }
        except Exception as e:
            log.warning("[DASHBOARD] get_multi_stage_orchestration_stats error: %s", e)
            return {}

    async def get_pacing_stats(self) -> dict:
        """Return Dynamic Pacing Intelligence stats for dashboard."""
        try:
            from dynamic_pacing_intelligence import get_pacing_engine
            eng = get_pacing_engine()
            if not eng:
                return {"status": "not_initialized"}
            pool = self._pool
            if not pool:
                return {"status": "no_db"}
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE pacing_state = 'SUSTAINABLE')  AS sustainable_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'ACCELERATING') AS accelerating_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'DECELERATING') AS decelerating_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'PAUSED')       AS paused_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'OVERLOADED')   AS overloaded_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'RECOVERING')   AS recovering_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'STALLED')      AS stalled_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'UNKNOWN')      AS unknown_count,
                        COUNT(*) FILTER (WHERE adaptive_pause_needed = TRUE)  AS pause_needed_count,
                        COUNT(*) FILTER (WHERE pacing_overload_risk >= 0.65)  AS high_overload_count,
                        COUNT(*) FILTER (WHERE pacing_pressure_risk >= 0.60)  AS high_pressure_count,
                        AVG(pacing_score) FILTER (WHERE pacing_score > 0)     AS avg_pacing_score,
                        COUNT(*) FILTER (WHERE last_pacing_check IS NOT NULL) AS evaluated_count
                    FROM pm_client_profiles
                """)
                if not row:
                    return {}
                return {
                    "status": "ok",
                    "pacing_states": {
                        "sustainable":  int(row["sustainable_count"] or 0),
                        "accelerating": int(row["accelerating_count"] or 0),
                        "decelerating": int(row["decelerating_count"] or 0),
                        "paused":       int(row["paused_count"] or 0),
                        "overloaded":   int(row["overloaded_count"] or 0),
                        "recovering":   int(row["recovering_count"] or 0),
                        "stalled":      int(row["stalled_count"] or 0),
                        "unknown":      int(row["unknown_count"] or 0),
                    },
                    "pause_needed_count":  int(row["pause_needed_count"] or 0),
                    "high_overload_count": int(row["high_overload_count"] or 0),
                    "high_pressure_count": int(row["high_pressure_count"] or 0),
                    "avg_pacing_score":    float(row["avg_pacing_score"] or 0.0),
                    "evaluated_count":     int(row["evaluated_count"] or 0),
                }
        except Exception as e:
            log.warning("[DASHBOARD] get_pacing_stats error: %s", e)
            return {}

_dashboard: Optional[DashboardData] = None

def get_dashboard() -> DashboardData:
    global _dashboard
    if _dashboard is None:
        _dashboard = DashboardData()
    return _dashboard


async def get_load_balancing_stats(db) -> dict:
    """
    Phase 3.12 — Expert Load Balancing Intelligence dashboard stats.
    Returns aggregate metrics for expert load state distribution.
    Fail-safe: returns error dict on any exception.
    """
    try:
        rows = await db.fetch("""
            SELECT
                COUNT(*) AS total_evaluated,
                COUNT(*) FILTER (WHERE expert_load_state = 'BALANCED') AS balanced_count,
                COUNT(*) FILTER (WHERE expert_load_state = 'PRESSURED') AS pressured_count,
                COUNT(*) FILTER (WHERE expert_load_state = 'CONGESTED') AS congested_count,
                COUNT(*) FILTER (WHERE expert_load_state = 'OVERLOADED') AS overloaded_count,
                COUNT(*) FILTER (WHERE expert_load_state = 'RECOVERING') AS recovering_count,
                COUNT(*) FILTER (WHERE expert_load_state = 'HANDOFF_AT_RISK') AS handoff_at_risk_count,
                COUNT(*) FILTER (WHERE expert_load_state = 'QUEUE_CRITICAL') AS queue_critical_count,
                COUNT(*) FILTER (WHERE expert_load_state = 'UNKNOWN') AS unknown_count,
                ROUND(AVG(support_congestion_score)::numeric, 4) AS avg_congestion,
                ROUND(AVG(operational_stability_score)::numeric, 4) AS avg_stability,
                ROUND(AVG(human_support_integrity_score)::numeric, 4) AS avg_integrity,
                ROUND(AVG(response_sustainability_score)::numeric, 4) AS avg_sustainability,
                MAX(last_load_balancing_check) AS last_check
            FROM pm_client_profiles
            WHERE last_load_balancing_check IS NOT NULL
        """)
        if not rows:
            return {"total_evaluated": 0}
        r = rows[0]
        return {
            "total_evaluated": r["total_evaluated"],
            "state_distribution": {
                "BALANCED": r["balanced_count"],
                "PRESSURED": r["pressured_count"],
                "CONGESTED": r["congested_count"],
                "OVERLOADED": r["overloaded_count"],
                "RECOVERING": r["recovering_count"],
                "HANDOFF_AT_RISK": r["handoff_at_risk_count"],
                "QUEUE_CRITICAL": r["queue_critical_count"],
                "UNKNOWN": r["unknown_count"],
            },
            "avg_congestion_score": float(r["avg_congestion"] or 0),
            "avg_stability_score": float(r["avg_stability"] or 0),
            "avg_integrity_score": float(r["avg_integrity"] or 0),
            "avg_sustainability_score": float(r["avg_sustainability"] or 0),
            "overloaded_count": r["overloaded_count"],
            "queue_critical_count": r["queue_critical_count"],
            "last_check": r["last_check"].isoformat() if r["last_check"] else None,
        }
    except Exception as exc:
        return {"error": str(exc)}


async def get_cognitive_orchestrator_stats(db) -> dict:
    """
    Phase 3.13 — Central Cognitive Orchestrator dashboard stats.
    Returns aggregate metrics for system coherence state distribution.
    Fail-safe: returns error dict on any exception.
    """
    try:
        rows = await db.fetch("""
            SELECT
                COUNT(*) AS total_evaluated,
                COUNT(*) FILTER (WHERE system_coherence_state = 'COHERENT') AS coherent_count,
                COUNT(*) FILTER (WHERE system_coherence_state = 'DRIFT_DETECTED') AS drift_count,
                COUNT(*) FILTER (WHERE system_coherence_state = 'CONFLICT_DETECTED') AS conflict_count,
                COUNT(*) FILTER (WHERE system_coherence_state = 'OVERLOAD_CHAIN') AS overload_chain_count,
                COUNT(*) FILTER (WHERE system_coherence_state = 'INSTABILITY') AS instability_count,
                COUNT(*) FILTER (WHERE system_coherence_state = 'GOVERNANCE_BREACH_RISK') AS governance_risk_count,
                COUNT(*) FILTER (WHERE system_coherence_state = 'ESCALATION_REQUIRED') AS escalation_required_count,
                COUNT(*) FILTER (WHERE system_coherence_state = 'RECOVERING') AS recovering_count,
                COUNT(*) FILTER (WHERE governance_conflict_detected = TRUE) AS governance_conflicts,
                COUNT(*) FILTER (WHERE overload_chain_detected = TRUE) AS overload_chains,
                ROUND(AVG(overall_system_stability_score)::numeric, 4) AS avg_stability,
                ROUND(AVG(operational_drift_score)::numeric, 4) AS avg_drift,
                ROUND(AVG(continuity_integrity_score)::numeric, 4) AS avg_continuity_integrity,
                ROUND(AVG(emotional_safety_integrity_score)::numeric, 4) AS avg_emotional_safety,
                MAX(last_cognitive_orchestrator_check) AS last_check
            FROM pm_client_profiles
            WHERE last_cognitive_orchestrator_check IS NOT NULL
        """)
        if not rows:
            return {"total_evaluated": 0}
        r = rows[0]
        return {
            "total_evaluated": r["total_evaluated"],
            "state_distribution": {
                "COHERENT": r["coherent_count"],
                "DRIFT_DETECTED": r["drift_count"],
                "CONFLICT_DETECTED": r["conflict_count"],
                "OVERLOAD_CHAIN": r["overload_chain_count"],
                "INSTABILITY": r["instability_count"],
                "GOVERNANCE_BREACH_RISK": r["governance_risk_count"],
                "ESCALATION_REQUIRED": r["escalation_required_count"],
                "RECOVERING": r["recovering_count"],
            },
            "governance_conflicts_detected": r["governance_conflicts"],
            "overload_chains_detected": r["overload_chains"],
            "avg_stability_score": float(r["avg_stability"] or 0),
            "avg_drift_score": float(r["avg_drift"] or 0),
            "avg_continuity_integrity": float(r["avg_continuity_integrity"] or 0),
            "avg_emotional_safety_integrity": float(r["avg_emotional_safety"] or 0),
            "last_check": r["last_check"].isoformat() if r["last_check"] else None,
        }
    except Exception as exc:
        return {"error": str(exc)}


async def get_longitudinal_modeling_stats(db) -> dict:
    """Phase 3.14 — Longitudinal Rehabilitation Modeling stats for dashboard."""
    try:
        rows = await db.fetch(
            """
            SELECT
                long_term_rehabilitation_state,
                COUNT(*) AS cnt,
                AVG(longitudinal_stability_score) AS avg_stability,
                AVG(rehabilitation_resilience_score) AS avg_resilience,
                AVG(continuity_sustainability_score) AS avg_sustainability,
                AVG(pacing_adaptation_quality) AS avg_pacing_adaptation,
                AVG(recovery_after_disruption_score) AS avg_recovery,
                AVG(long_term_route_durability) AS avg_durability,
                AVG(continuity_erosion_risk) AS avg_erosion_risk,
                AVG(rehabilitation_persistence_score) AS avg_persistence,
                AVG(longitudinal_coherence_score) AS avg_coherence,
                COUNT(*) FILTER (WHERE recurring_instability_detected = TRUE) AS recurring_instability_count,
                COUNT(*) FILTER (WHERE disengagement_cycle_detected = TRUE) AS disengagement_cycle_count,
                COUNT(*) FILTER (WHERE last_longitudinal_check IS NOT NULL) AS checked_count
            FROM pm_client_profiles
            GROUP BY long_term_rehabilitation_state
            ORDER BY cnt DESC
            """
        )
        state_distribution = {}
        totals = {
            "avg_stability": [], "avg_resilience": [], "avg_sustainability": [],
            "avg_pacing_adaptation": [], "avg_recovery": [], "avg_durability": [],
            "avg_erosion_risk": [], "avg_persistence": [], "avg_coherence": [],
        }
        total_recurring_instability = 0
        total_disengagement_cycles = 0
        total_checked = 0
        for row in rows:
            state = row["long_term_rehabilitation_state"] or "UNKNOWN"
            state_distribution[state] = int(row["cnt"])
            total_recurring_instability += int(row["recurring_instability_count"] or 0)
            total_disengagement_cycles += int(row["disengagement_cycle_count"] or 0)
            total_checked += int(row["checked_count"] or 0)
            for key in totals:
                val = row[key]
                if val is not None:
                    totals[key].append(float(val))

        def safe_avg(lst):
            return round(sum(lst) / len(lst), 4) if lst else 0.0

        return {
            "phase": "3.14",
            "engine": "LongitudinalRehabilitationModelingEngine",
            "state_distribution": state_distribution,
            "avg_longitudinal_stability_score": safe_avg(totals["avg_stability"]),
            "avg_rehabilitation_resilience_score": safe_avg(totals["avg_resilience"]),
            "avg_continuity_sustainability_score": safe_avg(totals["avg_sustainability"]),
            "avg_pacing_adaptation_quality": safe_avg(totals["avg_pacing_adaptation"]),
            "avg_recovery_after_disruption_score": safe_avg(totals["avg_recovery"]),
            "avg_long_term_route_durability": safe_avg(totals["avg_durability"]),
            "avg_continuity_erosion_risk": safe_avg(totals["avg_erosion_risk"]),
            "avg_rehabilitation_persistence_score": safe_avg(totals["avg_persistence"]),
            "avg_longitudinal_coherence_score": safe_avg(totals["avg_coherence"]),
            "total_recurring_instability_detected": total_recurring_instability,
            "total_disengagement_cycles_detected": total_disengagement_cycles,
            "total_profiles_checked": total_checked,
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_adaptive_strategy_stats():
    try:
        import psycopg2
        import json as _json
        conn = psycopg2.connect(__import__('os').environ.get('DATABASE_URL', ''))
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        adaptive_strategy_state,
                        recommended_continuity_strategy,
                        strategy_confidence_score,
                        strategy_stability_score,
                        strategy_shift_needed,
                        continuity_support_mode,
                        longitudinal_strategy_fit,
                        emotional_safety_strategy_fit,
                        expert_handoff_strategy_fit,
                        last_strategy_check
                    FROM pm_client_profiles
                    WHERE last_strategy_check IS NOT NULL
                    ORDER BY last_strategy_check DESC
                    LIMIT 1000
                """)
                rows = cur.fetchall()
        finally:
            conn.close()

        state_dist = {}
        strategy_dist = {}
        mode_dist = {"active": 0, "standby": 0, "hold": 0}
        conf_vals = []
        stab_vals = []
        long_fit_vals = []
        emo_fit_vals = []
        expert_fit_vals = []
        shift_count = 0
        last_check = None

        for row in rows:
            (state, strategy, conf, stab, shift, mode,
             long_fit, emo_fit, expert_fit, check_ts) = row
            if state:
                state_dist[state] = state_dist.get(state, 0) + 1
            if strategy:
                strategy_dist[strategy] = strategy_dist.get(strategy, 0) + 1
            if mode and mode in mode_dist:
                mode_dist[mode] += 1
            if conf is not None:
                conf_vals.append(float(conf))
            if stab is not None:
                stab_vals.append(float(stab))
            if long_fit is not None:
                long_fit_vals.append(float(long_fit))
            if emo_fit is not None:
                emo_fit_vals.append(float(emo_fit))
            if expert_fit is not None:
                expert_fit_vals.append(float(expert_fit))
            if shift:
                shift_count += 1
            if check_ts and (last_check is None or check_ts > last_check):
                last_check = check_ts

        def safe_avg(lst):
            return round(sum(lst) / len(lst), 4) if lst else 0.0

        return {
            "engine": "AdaptiveRehabilitationStrategyEngine",
            "phase": "3.15",
            "total_evaluated": len(rows),
            "strategy_state_distribution": state_dist,
            "strategy_distribution": strategy_dist,
            "avg_confidence_score": safe_avg(conf_vals),
            "avg_stability_score": safe_avg(stab_vals),
            "shift_needed_count": shift_count,
            "continuity_support_mode_distribution": mode_dist,
            "avg_longitudinal_fit": safe_avg(long_fit_vals),
            "avg_emotional_safety_fit": safe_avg(emo_fit_vals),
            "avg_expert_handoff_fit": safe_avg(expert_fit_vals),
            "last_check": last_check.isoformat() if last_check else None,
        }
    except Exception as exc:
        log.debug("[DASHBOARD] get_adaptive_strategy_stats exception: %s", exc)
        return {
            "engine": "AdaptiveRehabilitationStrategyEngine",
            "phase": "3.15",
            "total_evaluated": 0,
            "error": str(exc),
        }


async def get_route_simulation_stats(db_pool) -> dict:
    """Phase 3.16 — Dashboard stats for Rehabilitation Route Simulation Engine."""
    import logging
    log = logging.getLogger(__name__)
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    COUNT(*) AS total,
                    AVG(simulation_stability_score) AS avg_stability_score,
                    AVG(simulation_coherence_score) AS avg_coherence_score,
                    AVG(route_erosion_risk_projection) AS avg_erosion_risk,
                    COUNT(*) FILTER (WHERE route_simulation_state = 'STABLE_SIMULATION') AS stable_count,
                    COUNT(*) FILTER (WHERE route_simulation_state = 'HIGH_UNCERTAINTY') AS high_uncertainty_count,
                    COUNT(*) FILTER (WHERE route_simulation_state = 'ROUTE_EROSION_RISK') AS erosion_risk_count,
                    COUNT(*) FILTER (WHERE simulation_stability_score >= 0.7) AS high_stability_count
                FROM pm_client_profiles
                WHERE last_route_simulation_check IS NOT NULL
            """)
            if not rows:
                return {"engine": "RehabilitationRouteSimulationEngine", "phase": "3.16", "total_evaluated": 0}
            r = dict(rows[0])
            def safe_round(v):
                return round(float(v), 4) if v is not None else 0.0
            return {
                "engine": "RehabilitationRouteSimulationEngine",
                "phase": "3.16",
                "total_evaluated": r.get("total", 0),
                "avg_simulation_stability_score": safe_round(r.get("avg_stability_score")),
                "avg_simulation_coherence_score": safe_round(r.get("avg_coherence_score")),
                "avg_route_erosion_risk": safe_round(r.get("avg_erosion_risk")),
                "stable_simulation_count": r.get("stable_count", 0),
                "high_uncertainty_count": r.get("high_uncertainty_count", 0),
                "erosion_risk_count": r.get("erosion_risk_count", 0),
                "high_stability_count": r.get("high_stability_count", 0),
            }
    except Exception as exc:
        log.debug("[DASHBOARD] get_route_simulation_stats exception: %s", exc)
        return {"engine": "RehabilitationRouteSimulationEngine", "phase": "3.16", "total_evaluated": 0}


async def get_governance_stabilization_stats() -> dict:
    """Phase 3.17 — Dashboard stats for SelfStabilizingGovernanceEngine."""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'STABLE_GOVERNANCE') AS stable_count,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'DRIFT_ACCUMULATING') AS drift_count,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'OVERLOAD_CASCADE_RISK') AS cascade_count,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'COHERENCE_DEGRADATION') AS coherence_count,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'PACING_PRESSURE') AS pacing_count,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'ROUTE_CONFLICT_PRESSURE') AS route_conflict_count,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'ESCALATION_INSTABILITY') AS escalation_count,
                    COUNT(*) FILTER (WHERE governance_stability_state = 'STABILIZATION_REQUIRED') AS stabilization_required_count,
                    COUNT(*) FILTER (WHERE stabilization_needed = TRUE) AS stabilization_needed_count,
                    AVG(governance_drift_score) AS avg_drift_score,
                    AVG(overload_cascade_risk) AS avg_cascade_risk,
                    AVG(coherence_degradation_score) AS avg_coherence_degradation,
                    AVG(escalation_stability_score) AS avg_escalation_stability,
                    AVG(dispatcher_safety_alignment) AS avg_dispatcher_safety
                FROM pm_client_profiles
                WHERE last_governance_stabilization_check IS NOT NULL
            """)
        if not rows:
            return {"engine": "SelfStabilizingGovernanceEngine", "phase": "3.17", "total_evaluated": 0}
        r = dict(rows[0])
        def safe_round(v):
            return round(float(v), 4) if v is not None else 0.0
        return {
            "engine": "SelfStabilizingGovernanceEngine",
            "phase": "3.17",
            "total_evaluated": r.get("total", 0),
            "stable_governance_count": r.get("stable_count", 0),
            "drift_accumulating_count": r.get("drift_count", 0),
            "overload_cascade_risk_count": r.get("cascade_count", 0),
            "coherence_degradation_count": r.get("coherence_count", 0),
            "pacing_pressure_count": r.get("pacing_count", 0),
            "route_conflict_pressure_count": r.get("route_conflict_count", 0),
            "escalation_instability_count": r.get("escalation_count", 0),
            "stabilization_required_count": r.get("stabilization_required_count", 0),
            "stabilization_needed_count": r.get("stabilization_needed_count", 0),
            "avg_governance_drift_score": safe_round(r.get("avg_drift_score")),
            "avg_overload_cascade_risk": safe_round(r.get("avg_cascade_risk")),
            "avg_coherence_degradation_score": safe_round(r.get("avg_coherence_degradation")),
            "avg_escalation_stability_score": safe_round(r.get("avg_escalation_stability")),
            "avg_dispatcher_safety_alignment": safe_round(r.get("avg_dispatcher_safety")),
        }
    except Exception as exc:
        log.debug("[DASHBOARD] get_governance_stabilization_stats exception: %s", exc)
        return {"engine": "SelfStabilizingGovernanceEngine", "phase": "3.17", "total_evaluated": 0}

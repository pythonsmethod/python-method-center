# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: orchestration_logger.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Persist every orchestration event to PostgreSQL for:
#   - Debugging and monitoring
#   - Anna Dashboard analytics
#   - Audit trail for escalations
#   - Performance metrics (processing_ms)
#   - Route oscillation detection
#   - Overlay effectiveness tracking
#
# Table: pm_orchestration_events
# Schema:
#   id               SERIAL PRIMARY KEY
#   user_id          BIGINT
#   ts               TIMESTAMPTZ DEFAULT NOW()
#   route            TEXT
#   agent            TEXT
#   intent           TEXT
#   state            TEXT
#   risk_score       FLOAT
#   overlay_type     TEXT
#   interrupt_type   TEXT
#   escalated        BOOLEAN
#   route_switched   BOOLEAN
#   route_locked     BOOLEAN
#   validation_ok    BOOLEAN
#   processing_ms    INTEGER
#   steps_json       JSONB
#   msg_preview      TEXT
#   session_id       TEXT
#
# Migration SQL (run once on Railway PostgreSQL):
#   CREATE TABLE IF NOT EXISTS pm_orchestration_events (
#     id             SERIAL PRIMARY KEY,
#     user_id        BIGINT,
#     ts             TIMESTAMPTZ DEFAULT NOW(),
#     route          TEXT,
#     agent          TEXT,
#     intent         TEXT,
#     state          TEXT,
#     risk_score     FLOAT,
#     overlay_type   TEXT,
#     interrupt_type TEXT,
#     escalated      BOOLEAN DEFAULT FALSE,
#     route_switched BOOLEAN DEFAULT FALSE,
#     route_locked   BOOLEAN DEFAULT FALSE,
#     validation_ok  BOOLEAN DEFAULT TRUE,
#     processing_ms  INTEGER,
#     steps_json     JSONB,
#     msg_preview    TEXT,
#     session_id     TEXT
#   );
#   CREATE INDEX IF NOT EXISTS idx_pm_orch_events_user_ts
#     ON pm_orchestration_events(user_id, ts DESC);
# =============================================================================

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

log = logging.getLogger("orchestration_logger")

# ---------------------------------------------------------------------------
# In-memory event ring buffer (for Dashboard real-time feed)
# ---------------------------------------------------------------------------
_EVENT_BUFFER: list = []
_EVENT_BUFFER_MAX = 500

# ---------------------------------------------------------------------------
# DB connection (reuses existing pool pattern from agents.py)
# ---------------------------------------------------------------------------
_DB_URL = os.environ.get("DATABASE_URL", "")


class OrchestrationLogger:
    """
    Logs every orchestration event to:
    1. Python logging (always)
    2. In-memory ring buffer (for Dashboard API)
    3. PostgreSQL pm_orchestration_events table (if DB available)

    Usage:
        logger = OrchestrationLogger()
        log_id = logger.log(orch_event, session)
    """

    def log(
        self,
        event: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Optional[str]:
        """
        Log an orchestration event. Returns a log_id string.
        Never raises — all errors are caught and logged.
        """
        log_id = str(uuid.uuid4())[:8]
        try:
            self._log_to_python(event, log_id)
            self._log_to_buffer(event, session, log_id)
            # PostgreSQL logging is async — caller can optionally await _log_to_db
            # For sync usage, silently skip DB write (will be batched separately)
        except Exception as e:
            log.error("[ORCH_LOG] log error: %s", e)
        return log_id

    async def log_async(
        self,
        event: Dict[str, Any],
        session: Dict[str, Any],
    ) -> Optional[str]:
        """Async version with PostgreSQL write."""
        log_id = self.log(event, session)
        try:
            await self._log_to_db(event, session, log_id)
        except Exception as e:
            log.error("[ORCH_LOG] async DB write error: %s", e)
        return log_id

    def _log_to_python(self, event: Dict[str, Any], log_id: str) -> None:
        user_id = event.get("user_id", "?")
        route = event.get("route", "?")
        agent = event.get("agent", "?")
        intent = event.get("intent", "?")
        risk = float(event.get("risk_score", 0.0))
        overlay = event.get("overlay", "none")
        escalated = event.get("escalated", False)
        interrupt = event.get("interrupt")
        ms = event.get("processing_ms", 0)
        switched = event.get("route_switched", False)
        locked = event.get("route_locked", False)

        log.info(
            "[ORCH_EVENT id=%s] user=%s route=%s agent=%s intent=%s "
            "risk=%.2f overlay=%s interrupt=%s escalated=%s switched=%s locked=%s ms=%d",
            log_id, user_id, route, agent, intent,
            risk, overlay, interrupt, escalated, switched, locked, ms
        )

    def _log_to_buffer(
        self,
        event: Dict[str, Any],
        session: Dict[str, Any],
        log_id: str,
    ) -> None:
        global _EVENT_BUFFER
        entry = {
            "log_id":        log_id,
            "ts":            time.time(),
            "user_id":       event.get("user_id"),
            "route":         event.get("route"),
            "agent":         event.get("agent"),
            "intent":        event.get("intent"),
            "risk_score":    event.get("risk_score"),
            "overlay":       event.get("overlay"),
            "interrupt":     event.get("interrupt"),
            "escalated":     event.get("escalated"),
            "route_switched":event.get("route_switched"),
            "route_locked":  event.get("route_locked"),
            "processing_ms": event.get("processing_ms"),
            "steps":         event.get("steps", []),
        }
        _EVENT_BUFFER.append(entry)
        if len(_EVENT_BUFFER) > _EVENT_BUFFER_MAX:
            _EVENT_BUFFER = _EVENT_BUFFER[-_EVENT_BUFFER_MAX:]

    async def _log_to_db(
        self,
        event: Dict[str, Any],
        session: Dict[str, Any],
        log_id: str,
    ) -> None:
        if not _DB_URL:
            return

        try:
            import asyncpg  # type: ignore
            conn = await asyncpg.connect(_DB_URL)
            try:
                await conn.execute(
                    """
                    INSERT INTO pm_orchestration_events
                        (user_id, route, agent, intent, state, risk_score,
                         overlay_type, interrupt_type, escalated, route_switched,
                         route_locked, validation_ok, processing_ms, steps_json,
                         msg_preview, session_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                    """,
                    int(event.get("user_id", 0)),
                    event.get("route", ""),
                    event.get("agent", ""),
                    event.get("intent", ""),
                    event.get("state", ""),
                    float(event.get("risk_score", 0.0)),
                    event.get("overlay", "none"),
                    event.get("interrupt") or "",
                    bool(event.get("escalated", False)),
                    bool(event.get("route_switched", False)),
                    bool(event.get("route_locked", False)),
                    bool(event.get("validation_passed", True)),
                    int(event.get("processing_ms", 0)),
                    json.dumps(event.get("steps", [])),
                    str(event.get("message", ""))[:200],
                    log_id,
                )
            finally:
                await conn.close()
        except ImportError:
            log.debug("[ORCH_LOG] asyncpg not available — skipping DB write")
        except Exception as e:
            log.error("[ORCH_LOG] DB write error: %s", e)


# ---------------------------------------------------------------------------
# Dashboard API accessors (module-level functions)
# ---------------------------------------------------------------------------
def get_recent_events(n: int = 100) -> list:
    """Return last N orchestration events from buffer (for Dashboard)."""
    return list(reversed(_EVENT_BUFFER[-n:]))


def get_events_for_user(user_id: int, n: int = 20) -> list:
    """Return last N events for a specific user."""
    user_events = [e for e in _EVENT_BUFFER if e.get("user_id") == user_id]
    return list(reversed(user_events[-n:]))


def get_escalation_events(n: int = 50) -> list:
    """Return last N escalation events."""
    return [e for e in reversed(_EVENT_BUFFER) if e.get("escalated")][:n]


def get_stats() -> Dict[str, Any]:
    """Return aggregate stats from buffer (for Dashboard health widget)."""
    if not _EVENT_BUFFER:
        return {}
    total = len(_EVENT_BUFFER)
    escalated = sum(1 for e in _EVENT_BUFFER if e.get("escalated"))
    switched = sum(1 for e in _EVENT_BUFFER if e.get("route_switched"))
    avg_ms = sum(e.get("processing_ms", 0) for e in _EVENT_BUFFER) / total
    routes = {}
    for e in _EVENT_BUFFER:
        r = e.get("route", "?")
        routes[r] = routes.get(r, 0) + 1
    return {
        "total_events":    total,
        "escalated_count": escalated,
        "route_switches":  switched,
        "avg_processing_ms": round(avg_ms, 1),
        "route_distribution": routes,
        "buffer_capacity": f"{total}/{_EVENT_BUFFER_MAX}",
    }


# ---------------------------------------------------------------------------
# Migration SQL helper
# ---------------------------------------------------------------------------
MIGRATION_SQL = """
-- Run once on Railway PostgreSQL to enable orchestration event logging:
CREATE TABLE IF NOT EXISTS pm_orchestration_events (
    id             SERIAL PRIMARY KEY,
    user_id        BIGINT,
    ts             TIMESTAMPTZ DEFAULT NOW(),
    route          TEXT,
    agent          TEXT,
    intent         TEXT,
    state          TEXT,
    risk_score     FLOAT,
    overlay_type   TEXT,
    interrupt_type TEXT,
    escalated      BOOLEAN DEFAULT FALSE,
    route_switched BOOLEAN DEFAULT FALSE,
    route_locked   BOOLEAN DEFAULT FALSE,
    validation_ok  BOOLEAN DEFAULT TRUE,
    processing_ms  INTEGER,
    steps_json     JSONB,
    msg_preview    TEXT,
    session_id     TEXT
);
CREATE INDEX IF NOT EXISTS idx_pm_orch_events_user_ts
    ON pm_orchestration_events(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_pm_orch_events_escalated
    ON pm_orchestration_events(escalated) WHERE escalated = TRUE;
"""

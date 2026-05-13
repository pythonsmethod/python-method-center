# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.1 — Persistent Memory & Infrastructure Core
# Module: runtime_supervisor.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Runtime Supervision Layer
#
# Purpose: Monitor all subsystems, detect failures, trigger circuit breakers,
#          maintain runtime health metrics, alert on anomalies.
#
# Monitored subsystems:
#   orchestrator     — process_message() pipeline
#   memory_engine    — DB reads/writes
#   event_bus        — publish/subscribe
#   async_queue      — job processing
#   recovery_engine  — recovery plan execution
#   ai_runtime       — Claude/GPT calls
#   telegram_api     — Telegram Bot API
#
# Circuit breaker states:
#   closed     — normal operation
#   open       — subsystem down, reject requests
#   half_open  — testing recovery
# =============================================================================

from __future__ import annotations
import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, Optional

log = logging.getLogger("runtime_supervisor")

# Circuit breaker config
_CB_FAILURE_THRESHOLD = 5      # open after N consecutive failures
_CB_TIMEOUT_S = 60             # stay open for 60s
_CB_SUCCESS_THRESHOLD = 2      # close after N successes in half_open

# Health check interval
_HEALTH_INTERVAL_S = 30


@dataclass
class SubsystemHealth:
    """Health state for one subsystem."""
    name: str
    status: str = "ok"               # ok | degraded | critical | down
    circuit_state: str = "closed"    # closed | open | half_open
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    circuit_open_at: float = 0.0
    latency_window: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    error_window: Deque[bool] = field(default_factory=lambda: deque(maxlen=100))
    requests_total: int = 0
    errors_total: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_window:
            return 0.0
        return sum(self.latency_window) / len(self.latency_window)

    @property
    def error_rate(self) -> float:
        if not self.error_window:
            return 0.0
        return sum(1 for e in self.error_window if e) / len(self.error_window)

    def is_available(self) -> bool:
        """Can requests be sent to this subsystem?"""
        if self.circuit_state == "open":
            if time.monotonic() - self.circuit_open_at >= _CB_TIMEOUT_S:
                self.circuit_state = "half_open"
                log.info("[SUPERVISOR] %s circuit -> half_open", self.name)
                return True
            return False
        return True


class RuntimeSupervisor:
    """
    Central runtime monitoring and circuit breaker system.
    Tracks latency, error rates, and controls subsystem availability.
    """

    def __init__(self, db_pool=None):
        self._pool = db_pool
        self._health: Dict[str, SubsystemHealth] = {}
        self._alert_handlers: list = []
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        self._init_subsystems()
        log.info("[SUPERVISOR] RuntimeSupervisor initialized")

    def _init_subsystems(self) -> None:
        for name in ("orchestrator", "memory_engine", "event_bus",
                     "async_queue", "recovery_engine", "ai_runtime",
                     "telegram_api", "database"):
            self._health[name] = SubsystemHealth(name=name)

    async def start(self) -> None:
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        log.info("[SUPERVISOR] monitoring started")

    async def stop(self) -> None:
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

    def on_alert(self, handler: Callable) -> None:
        """Register an alert handler (async fn(subsystem, status, details))."""
        self._alert_handlers.append(handler)

    # -----------------------------------------------------------------------
    # Recording: call these from each subsystem
    # -----------------------------------------------------------------------

    def record_success(self, subsystem: str, latency_ms: float) -> None:
        """Record a successful operation."""
        h = self._get_or_create(subsystem)
        h.requests_total += 1
        h.consecutive_failures = 0
        h.consecutive_successes += 1
        h.latency_window.append(latency_ms)
        h.error_window.append(False)

        if h.circuit_state == "half_open":
            if h.consecutive_successes >= _CB_SUCCESS_THRESHOLD:
                h.circuit_state = "closed"
                h.status = "ok"
                log.info("[SUPERVISOR] %s circuit -> closed (recovered)", subsystem)

        # Degraded if latency high
        if h.avg_latency_ms > 5000:
            h.status = "degraded"
        elif h.error_rate < 0.05:
            h.status = "ok"

    def record_failure(self, subsystem: str, error: str = "", latency_ms: float = 0) -> None:
        """Record a failed operation — may open circuit breaker."""
        h = self._get_or_create(subsystem)
        h.requests_total += 1
        h.errors_total += 1
        h.consecutive_failures += 1
        h.consecutive_successes = 0
        if latency_ms > 0:
            h.latency_window.append(latency_ms)
        h.error_window.append(True)

        # Update status
        if h.error_rate >= 0.50:
            h.status = "critical"
        elif h.error_rate >= 0.20:
            h.status = "degraded"

        # Open circuit breaker
        if (h.consecutive_failures >= _CB_FAILURE_THRESHOLD
                and h.circuit_state == "closed"):
            h.circuit_state = "open"
            h.circuit_open_at = time.monotonic()
            log.error("[SUPERVISOR] CIRCUIT OPEN: %s (failures=%d)",
                       subsystem, h.consecutive_failures)
            asyncio.create_task(self._trigger_alert(subsystem, "circuit_open", error))

    def is_available(self, subsystem: str) -> bool:
        """Check if a subsystem is available for requests."""
        return self._get_or_create(subsystem).is_available()

    def get_health(self, subsystem: str) -> Dict[str, Any]:
        """Get health snapshot for one subsystem."""
        h = self._get_or_create(subsystem)
        return {
            "name": h.name,
            "status": h.status,
            "circuit_state": h.circuit_state,
            "error_rate": round(h.error_rate, 4),
            "avg_latency_ms": round(h.avg_latency_ms, 1),
            "requests_total": h.requests_total,
            "errors_total": h.errors_total,
            "consecutive_failures": h.consecutive_failures,
        }

    def get_all_health(self) -> Dict[str, Dict]:
        """Get health snapshot for all subsystems."""
        return {name: self.get_health(name) for name in self._health}

    # -----------------------------------------------------------------------
    # Context manager for timing + recording
    # -----------------------------------------------------------------------

    class _Timer:
        def __init__(self, supervisor, subsystem):
            self._sv = supervisor
            self._sub = subsystem
            self._t0 = 0.0

        async def __aenter__(self):
            self._t0 = time.monotonic()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            ms = (time.monotonic() - self._t0) * 1000
            if exc_type:
                self._sv.record_failure(self._sub, str(exc), ms)
            else:
                self._sv.record_success(self._sub, ms)
            return False  # do not suppress exception

    def monitor(self, subsystem: str):
        """Context manager: auto-records success/failure + latency."""
        return self._Timer(self, subsystem)

    # -----------------------------------------------------------------------
    # Monitoring loop
    # -----------------------------------------------------------------------

    async def _monitoring_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(_HEALTH_INTERVAL_S)
                await self._persist_health()
                await self._check_alerts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[SUPERVISOR] monitoring loop error: %s", e)

    async def _persist_health(self) -> None:
        """Persist health metrics to pm_runtime_health."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                for name, h in self._health.items():
                    await conn.execute(
                        "INSERT INTO pm_runtime_health"
                        " (subsystem, status, latency_ms, error_rate,"
                        "  requests_total, errors_total, circuit_state)"
                        " VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        name, h.status, int(h.avg_latency_ms),
                        round(h.error_rate, 4),
                        h.requests_total, h.errors_total,
                        h.circuit_state,
                    )
        except Exception as e:
            log.error("[SUPERVISOR] persist_health error: %s", e)

    async def _check_alerts(self) -> None:
        """Check for subsystems that need alerting."""
        for name, h in self._health.items():
            if h.status in ("critical", "down") and h.circuit_state == "open":
                await self._trigger_alert(name, "subsystem_down", "")

    async def _trigger_alert(self, subsystem: str, alert_type: str, detail: str) -> None:
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(subsystem, alert_type, detail)
                else:
                    handler(subsystem, alert_type, detail)
            except Exception as e:
                log.error("[SUPERVISOR] alert handler error: %s", e)

    def _get_or_create(self, subsystem: str) -> SubsystemHealth:
        if subsystem not in self._health:
            self._health[subsystem] = SubsystemHealth(name=subsystem)
        return self._health[subsystem]


_supervisor: Optional[RuntimeSupervisor] = None

def get_supervisor() -> RuntimeSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = RuntimeSupervisor()
    return _supervisor

# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.1 — Persistent Memory & Infrastructure Core
# Module: event_bus.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Event Bus
#
# Purpose: Async publish/subscribe infrastructure.
#          Decouples event producers from consumers.
#          Backed by pm_event_bus PostgreSQL table for durability.
#
# Topics (built-in):
#   memory.compress         — trigger compression for user_id
#   memory.embed            — embed content into vectors
#   risk.alert              — high-risk signal detected
#   escalation.triggered    — escalation happened, notify team
#   recovery.trigger        — client went silent, start recovery
#   client.payment          — payment state change
#   client.onboarding       — onboarding state change
#   session.ended           — session ended, run cleanup
#   health.check            — periodic health check
# =============================================================================

from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional

log = logging.getLogger("event_bus")

# ---------------------------------------------------------------------------
# Built-in topics
# ---------------------------------------------------------------------------
class Topic:
    MEMORY_COMPRESS      = "memory.compress"
    MEMORY_EMBED         = "memory.embed"
    RISK_ALERT           = "risk.alert"
    ESCALATION_TRIGGERED = "escalation.triggered"
    ESCALATION_RESOLVED  = "escalation.resolved"
    RECOVERY_TRIGGER     = "recovery.trigger"
    RECOVERY_COMPLETED   = "recovery.completed"
    CLIENT_PAYMENT       = "client.payment"
    CLIENT_ONBOARDING    = "client.onboarding"
    SESSION_ENDED        = "session.ended"
    HEALTH_CHECK         = "health.check"
    ORCHESTRATION_DONE   = "orchestration.done"


# ---------------------------------------------------------------------------
# In-memory subscriber registry
# ---------------------------------------------------------------------------
_SUBSCRIBERS: Dict[str, List[Callable]] = {}


def subscribe(topic: str, handler: Callable) -> None:
    """Register an async handler for a topic."""
    if topic not in _SUBSCRIBERS:
        _SUBSCRIBERS[topic] = []
    _SUBSCRIBERS[topic].append(handler)
    log.debug("[BUS] subscribed: topic=%s handler=%s", topic, handler.__name__)


def unsubscribe(topic: str, handler: Callable) -> None:
    if topic in _SUBSCRIBERS:
        _SUBSCRIBERS[topic] = [h for h in _SUBSCRIBERS[topic] if h != handler]


# ---------------------------------------------------------------------------
# EventBus class
# ---------------------------------------------------------------------------
class EventBus:
    """
    Async event bus with PostgreSQL durability.
    In-memory dispatch + durable persistence for recovery.
    """

    def __init__(self, db_pool=None):
        self._pool = db_pool
        self._in_memory_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        log.info("[BUS] EventBus initialized")

    async def start(self) -> None:
        """Start the background worker."""
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        log.info("[BUS] worker started")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        log.info("[BUS] worker stopped")

    async def publish(self, topic: str, payload: Dict[str, Any],
                     publisher: str = "orchestrator",
                     partition_key: str = None) -> str:
        """
        Publish an event to a topic.
        Persists to PostgreSQL for durability.
        Returns event_id.
        """
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "topic": topic,
            "payload": payload,
            "publisher": publisher,
            "partition_key": partition_key or payload.get("user_id", "global"),
            "published_at": time.time(),
        }

        # Persist to DB
        await self._persist_event(topic, payload, publisher, partition_key, event_id)

        # Put in in-memory queue for immediate dispatch
        try:
            self._in_memory_queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("[BUS] queue full, dropping in-memory event: %s", topic)

        log.debug("[BUS] published: topic=%s event_id=%s", topic, event_id)
        return event_id

    async def _worker_loop(self) -> None:
        """Background worker that dispatches events to subscribers."""
        log.info("[BUS] worker loop started")
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._in_memory_queue.get(), timeout=1.0
                )
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[BUS] worker error: %s", e)

    async def _dispatch(self, event: Dict[str, Any]) -> None:
        """Dispatch event to all registered topic subscribers."""
        topic = event["topic"]
        handlers = _SUBSCRIBERS.get(topic, []) + _SUBSCRIBERS.get("*", [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                log.error("[BUS] handler error topic=%s handler=%s: %s",
                           topic, handler.__name__, e)

    async def _persist_event(self, topic: str, payload: Dict, publisher: str,
                             partition_key: str, event_id: str) -> None:
        """Persist event to pm_event_bus for durability."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO pm_event_bus"
                    " (event_id, topic, partition_key, payload, publisher, publisher_id)"
                    " VALUES ($1, $2, $3, $4, $5, $6)",
                    event_id, topic,
                    partition_key or str(payload.get("user_id", "global")),
                    json.dumps(payload), publisher, event_id
                )
        except Exception as e:
            log.error("[BUS] persist error: %s", e)

    async def replay_unconsumed(self, topic: str = None) -> int:
        """
        Replay unconsumed events from DB (after restart).
        Returns count of replayed events.
        """
        if not self._pool:
            return 0
        replayed = 0
        try:
            async with self._pool.acquire() as conn:
                q = ("SELECT event_id, topic, payload FROM pm_event_bus"
                     " WHERE is_consumed=FALSE AND dead_lettered=FALSE"
                     " AND expires_at > NOW()")
                if topic:
                    q += " AND topic=$1 ORDER BY published_at LIMIT 100"
                    rows = await conn.fetch(q, topic)
                else:
                    q += " ORDER BY published_at LIMIT 100"
                    rows = await conn.fetch(q)

                for row in rows:
                    payload = json.loads(row["payload"])
                    await self._in_memory_queue.put({
                        "event_id": row["event_id"],
                        "topic": row["topic"],
                        "payload": payload,
                        "publisher": "replay",
                        "published_at": time.time(),
                    })
                    replayed += 1
                log.info("[BUS] replayed %d events", replayed)
        except Exception as e:
            log.error("[BUS] replay error: %s", e)
        return replayed

    async def mark_consumed(self, event_id: str, consumer: str = "worker") -> None:
        """Mark a durable event as consumed."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pm_event_bus SET is_consumed=TRUE, consumed_at=NOW(), consumed_by=$2"
                    " WHERE event_id=$1",
                    event_id, consumer
                )
        except Exception as e:
            log.error("[BUS] mark_consumed error: %s", e)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_event_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


async def publish(topic: str, payload: Dict[str, Any], **kwargs) -> str:
    """Module-level convenience function."""
    return await get_event_bus().publish(topic, payload, **kwargs)

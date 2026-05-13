# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.1 — Persistent Memory & Infrastructure Core
# Module: async_queue.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Async Job Queue
#
# Purpose: Durable background job queue.
#          Workers pick up jobs from pm_queue_jobs.
#          Supports: priorities, retries, timeouts, dead letters.
#
# Job types:
#   memory.compress    — compress user memory
#   memory.embed       — embed content into vectors
#   risk.predict       — run risk prediction model
#   recovery.execute   — execute recovery plan step
#   client.sync        — sync client profile
#   health.ping        — health check probe
#   notify.team        — send team notification
# =============================================================================

from __future__ import annotations
import asyncio
import json
import logging
import os
import socket
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("async_queue")

# Worker identity
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

# Queue configuration
_LOCK_TIMEOUT_S = 60          # job lock expires after 60s
_POLL_INTERVAL_S = 2          # worker polls every 2s
_MAX_WORKERS = 3              # max concurrent workers


class JobType:
    MEMORY_COMPRESS  = "memory.compress"
    MEMORY_EMBED     = "memory.embed"
    RISK_PREDICT     = "risk.predict"
    RECOVERY_EXECUTE = "recovery.execute"
    CLIENT_SYNC      = "client.sync"
    HEALTH_PING      = "health.ping"
    NOTIFY_TEAM      = "notify.team"
    COMPRESSION_SCAN = "compression.scan"


class AsyncQueue:
    """
    Durable async job queue backed by PostgreSQL.
    Workers claim jobs with advisory locks to prevent double-processing.
    """

    def __init__(self, db_pool=None):
        self._pool = db_pool
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._semaphore = asyncio.Semaphore(_MAX_WORKERS)
        log.info("[QUEUE] AsyncQueue initialized worker_id=%s", WORKER_ID)

    def register(self, job_type: str, handler: Callable) -> None:
        """Register an async handler for a job type."""
        self._handlers[job_type] = handler
        log.debug("[QUEUE] registered handler: %s", job_type)

    async def start(self) -> None:
        """Start background workers."""
        self._running = True
        for i in range(_MAX_WORKERS):
            task = asyncio.create_task(self._worker_loop(worker_num=i))
            self._worker_tasks.append(task)
        # Also start zombie lock cleaner
        self._worker_tasks.append(
            asyncio.create_task(self._zombie_cleaner())
        )
        log.info("[QUEUE] %d workers started", _MAX_WORKERS)

    async def stop(self) -> None:
        self._running = False
        for t in self._worker_tasks:
            t.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        log.info("[QUEUE] workers stopped")

    async def enqueue(
        self,
        job_type: str,
        payload: Dict[str, Any],
        priority: int = 5,
        queue_name: str = "default",
        user_id: int = None,
        delay_s: int = 0,
        max_attempts: int = 3,
        triggered_by: str = None,
    ) -> Optional[str]:
        """
        Enqueue a job for background processing.
        Returns job_id or None on error.
        priority: 1=highest 10=lowest
        """
        if not self._pool:
            return None
        job_id = str(uuid.uuid4())
        try:
            scheduled_at = "NOW()" if delay_s == 0 else f"NOW() + INTERVAL '{delay_s} seconds'"
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO pm_queue_jobs"
                    " (job_id, job_type, job_payload, priority, queue_name,"
                    "  user_id, triggered_by, max_attempts, scheduled_at)"
                    " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW() + ($9 * INTERVAL '1 second'))",
                    job_id, job_type, json.dumps(payload), priority, queue_name,
                    user_id, triggered_by or "system", max_attempts, delay_s,
                )
            log.info("[QUEUE] enqueued: type=%s job_id=%s priority=%d", job_type, job_id, priority)
            return job_id
        except Exception as e:
            log.error("[QUEUE] enqueue error: %s", e)
            return None

    async def _worker_loop(self, worker_num: int) -> None:
        """Background worker loop — polls DB for jobs."""
        log.info("[QUEUE] worker %d started", worker_num)
        while self._running:
            try:
                job = await self._claim_job()
                if job:
                    async with self._semaphore:
                        await self._execute_job(job)
                else:
                    await asyncio.sleep(_POLL_INTERVAL_S)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[QUEUE] worker %d error: %s", worker_num, e)
                await asyncio.sleep(_POLL_INTERVAL_S)

    async def _claim_job(self) -> Optional[Dict]:
        """Atomically claim one pending job."""
        if not self._pool:
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE pm_queue_jobs SET status='running'::job_status,"
                    " worker_id=$1, locked_at=NOW(),"
                    " lock_expires_at=NOW() + INTERVAL '60 seconds',"
                    " started_at=COALESCE(started_at, NOW()),"
                    " attempts=attempts+1"
                    " WHERE id = ("
                    "   SELECT id FROM pm_queue_jobs"
                    "   WHERE status='pending'::job_status"
                    "     AND scheduled_at <= NOW()"
                    "     AND expires_at > NOW()"
                    "   ORDER BY priority ASC, scheduled_at ASC"
                    "   LIMIT 1 FOR UPDATE SKIP LOCKED"
                    " ) RETURNING id, job_id, job_type, job_payload, attempts, max_attempts, user_id",
                    WORKER_ID
                )
                return dict(row) if row else None
        except Exception as e:
            log.error("[QUEUE] claim_job error: %s", e)
            return None

    async def _execute_job(self, job: Dict) -> None:
        """Execute a claimed job."""
        job_type = job["job_type"]
        job_id = job["job_id"]
        t0 = time.monotonic()
        try:
            handler = self._handlers.get(job_type)
            if not handler:
                log.warning("[QUEUE] no handler for job_type=%s", job_type)
                await self._complete_job(job["id"], None, f"no_handler:{job_type}")
                return

            payload = json.loads(job["job_payload"])
            result = await handler(payload)
            ms = int((time.monotonic() - t0) * 1000)
            await self._complete_job(job["id"], result, None)
            log.info("[QUEUE] completed: type=%s job_id=%s ms=%d", job_type, job_id, ms)

        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            log.error("[QUEUE] job failed: type=%s job_id=%s error=%s ms=%d", job_type, job_id, e, ms)
            await self._fail_job(job, str(e))

    async def _complete_job(self, job_db_id: int, result: Any, error: str) -> None:
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                if error:
                    await conn.execute(
                        "UPDATE pm_queue_jobs SET status='failed'::job_status,"
                        " completed_at=NOW(), error_message=$2 WHERE id=$1",
                        job_db_id, error,
                    )
                else:
                    await conn.execute(
                        "UPDATE pm_queue_jobs SET status='completed'::job_status,"
                        " completed_at=NOW(), result=$2 WHERE id=$1",
                        job_db_id, json.dumps(result) if result is not None else None,
                    )
        except Exception as e:
            log.error("[QUEUE] _complete_job error: %s", e)

    async def _fail_job(self, job: Dict, error: str) -> None:
        """Handle job failure with retry logic."""
        if not self._pool:
            return
        try:
            attempts = int(job.get("attempts", 1))
            max_attempts = int(job.get("max_attempts", 3))
            if attempts < max_attempts:
                retry_delay = min(60 * attempts, 300)  # exponential backoff
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE pm_queue_jobs SET status='retrying'::job_status,"
                        " next_retry_at=NOW() + ($2 * INTERVAL '1 second'),"
                        " error_message=$3, worker_id=NULL WHERE id=$1",
                        job["id"], retry_delay, error[:500],
                    )
                log.info("[QUEUE] will retry job_id=%s in %ds", job["job_id"], retry_delay)
            else:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE pm_queue_jobs SET status='failed'::job_status,"
                        " completed_at=NOW(), error_message=$2 WHERE id=$1",
                        job["id"], error[:500],
                    )
                log.error("[QUEUE] job permanently failed: %s", job["job_id"])
        except Exception as e:
            log.error("[QUEUE] _fail_job error: %s", e)

    async def _zombie_cleaner(self) -> None:
        """Clean up expired job locks (zombie jobs)."""
        while self._running:
            try:
                await asyncio.sleep(30)
                if not self._pool:
                    continue
                async with self._pool.acquire() as conn:
                    count = await conn.fetchval(
                        "UPDATE pm_queue_jobs SET status='pending'::job_status,"
                        " worker_id=NULL, locked_at=NULL, lock_expires_at=NULL"
                        " WHERE status='running'::job_status"
                        "   AND lock_expires_at < NOW()"
                        " RETURNING COUNT(*)",
                    )
                if count:
                    log.warning("[QUEUE] cleaned %d zombie jobs", count)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[QUEUE] zombie cleaner error: %s", e)

    async def get_stats(self) -> Dict[str, Any]:
        """Return queue statistics."""
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT queue_name, job_type, status, COUNT(*) as cnt"
                    " FROM pm_queue_jobs WHERE created_at > NOW() - INTERVAL '1 hour'"
                    " GROUP BY queue_name, job_type, status",
                )
                return {"jobs": [dict(r) for r in rows], "worker_id": WORKER_ID}
        except Exception as e:
            log.error("[QUEUE] get_stats error: %s", e)
            return {}


_queue: Optional[AsyncQueue] = None

def get_queue() -> AsyncQueue:
    global _queue
    if _queue is None:
        _queue = AsyncQueue()
    return _queue

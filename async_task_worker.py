"""
async_task_worker.py - Non-Blocking Background Task Runner
Python Method Center - PHASE 3.1A

After AI response is sent to user, run these tasks in background:
- memory_writer.write()
- orchestration_logger.log()
- analytics update
- dashboard data refresh
- vector embedding generation
- event bus publish

CRITICAL: These must NEVER block user response delivery.
User gets response first. Background tasks run after, fire-and-forget.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable, Awaitable, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskPriority(int, Enum):
    CRITICAL = 0    # Must complete - e.g. memory write for escalations
    HIGH = 1        # Important but not blocking
    NORMAL = 2      # Standard background tasks
    LOW = 3         # Analytics, embeddings - can be deferred


@dataclass
class BackgroundTask:
    """A unit of background work to be executed after response is sent."""
    task_id: str
    task_type: str
    priority: TaskPriority
    user_id: int
    coro_factory: Callable  # Callable that returns a coroutine
    coro_args: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    max_retries: int = 2
    retry_delay: float = 1.0


class AsyncTaskWorker:
    """
    Fire-and-forget background task executor.
    
    Tasks are submitted with fire_and_forget() and run asynchronously
    without blocking the main response pipeline.
    
    Priority queue ensures critical tasks run first.
    Failed tasks are retried up to max_retries times.
    """

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._worker_task: Optional[asyncio.Task] = None
        self._task_counter = 0
        self._stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "retried": 0,
        }
        logger.info("[ASYNC_WORKER] AsyncTaskWorker initialized max_concurrent=%d", max_concurrent)

    async def start(self):
        """Start the background worker loop."""
        if self._worker_task and not self._worker_task.done():
            logger.debug("[ASYNC_WORKER] Already running")
            return
        self._worker_task = asyncio.create_task(
            self._worker_loop(),
            name="async_task_worker"
        )
        logger.info("[ASYNC_WORKER] Worker loop started")

    async def stop(self):
        """Gracefully stop the worker."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("[ASYNC_WORKER] Worker stopped")

    async def fire_and_forget(self, task_type: str, user_id: int,
                              coro_factory: Callable, coro_args: Dict = None,
                              priority: TaskPriority = TaskPriority.NORMAL,
                              max_retries: int = 2) -> str:
        """
        Submit a background task. Returns task_id immediately.
        Does NOT wait for completion. Never blocks caller.
        """
        self._task_counter += 1
        task_id = f"bg_{user_id}_{task_type}_{self._task_counter}"

        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            user_id=user_id,
            coro_factory=coro_factory,
            coro_args=coro_args or {},
            max_retries=max_retries
        )

        # PriorityQueue uses (priority_value, item) for ordering
        await self._queue.put((priority.value, task))
        self._stats["submitted"] += 1

        logger.debug("[ASYNC_WORKER] Task submitted task_id=%s type=%s user=%s priority=%s",
                     task_id, task_type, user_id, priority.name)

        # Ensure worker is running
        if not self._worker_task or self._worker_task.done():
            await self.start()

        return task_id

    async def _worker_loop(self):
        """Main worker loop - processes tasks from priority queue."""
        logger.info("[ASYNC_WORKER] Worker loop running")
        try:
            while True:
                try:
                    # Wait for next task (timeout to allow clean shutdown)
                    priority_val, task = await asyncio.wait_for(
                        self._queue.get(), timeout=30.0
                    )
                    # Execute without blocking queue
                    asyncio.create_task(
                        self._execute_task(task),
                        name=f"exec_{task.task_id}"
                    )
                except asyncio.TimeoutError:
                    # No tasks for 30s, loop continues
                    pass
        except asyncio.CancelledError:
            logger.info("[ASYNC_WORKER] Worker loop cancelled")
            raise

    async def _execute_task(self, task: BackgroundTask, attempt: int = 1):
        """Execute a single background task with retry logic."""
        async with self._semaphore:
            try:
                logger.debug("[ASYNC_WORKER] Executing task=%s attempt=%d", task.task_id, attempt)
                coro = task.coro_factory(**task.coro_args)
                await asyncio.wait_for(coro, timeout=30.0)
                self._stats["completed"] += 1
                logger.debug("[ASYNC_WORKER] Task DONE task=%s", task.task_id)
            except asyncio.TimeoutError:
                logger.error("[ASYNC_WORKER] Task TIMEOUT task=%s", task.task_id)
                await self._handle_retry(task, attempt, "timeout")
            except Exception as e:
                logger.error("[ASYNC_WORKER] Task ERROR task=%s: %s", task.task_id, e)
                await self._handle_retry(task, attempt, str(e))

    async def _handle_retry(self, task: BackgroundTask, attempt: int, reason: str):
        """Handle task failure with retry logic."""
        if attempt < task.max_retries:
            self._stats["retried"] += 1
            delay = task.retry_delay * attempt
            logger.info("[ASYNC_WORKER] Retrying task=%s attempt=%d/%d delay=%.1fs",
                        task.task_id, attempt + 1, task.max_retries, delay)
            await asyncio.sleep(delay)
            await self._execute_task(task, attempt + 1)
        else:
            self._stats["failed"] += 1
            logger.error("[ASYNC_WORKER] Task FAILED permanently task=%s reason=%s",
                         task.task_id, reason)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
            "worker_running": bool(self._worker_task and not self._worker_task.done()),
        }


# Standard task type helpers

async def submit_memory_write(worker: AsyncTaskWorker, user_id: int,
                              memory_writer, write_kwargs: Dict):
    """Submit memory write as background task (high priority)."""
    await worker.fire_and_forget(
        task_type="memory_write",
        user_id=user_id,
        coro_factory=memory_writer.write,
        coro_args=write_kwargs,
        priority=TaskPriority.HIGH,
        max_retries=3
    )


async def submit_orch_log(worker: AsyncTaskWorker, user_id: int,
                          orch_logger, log_kwargs: Dict):
    """Submit orchestration log as background task (normal priority)."""
    await worker.fire_and_forget(
        task_type="orch_log",
        user_id=user_id,
        coro_factory=orch_logger.log,
        coro_args=log_kwargs,
        priority=TaskPriority.NORMAL,
        max_retries=2
    )


async def submit_embedding_generation(worker: AsyncTaskWorker, user_id: int,
                                       embed_fn: Callable, embed_kwargs: Dict):
    """Submit vector embedding generation (low priority - can wait)."""
    await worker.fire_and_forget(
        task_type="embedding",
        user_id=user_id,
        coro_factory=embed_fn,
        coro_args=embed_kwargs,
        priority=TaskPriority.LOW,
        max_retries=1
    )


# Global singleton
async_worker = AsyncTaskWorker(max_concurrent=10)

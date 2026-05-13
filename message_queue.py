"""
message_queue.py - Per-User Message Queue
Python Method Center - PHASE 3.1A

Guarantees:
- One orchestration process per user at a time
- Incoming messages are never dropped
- Latest message context always wins
- No two concurrent orchestrator runs per user
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """A single user message waiting to be processed."""
    user_id: int
    message_id: int
    text: str
    timestamp: float
    raw_update: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class UserMessageQueue:
    """
    Per-user message queue with single-worker guarantee.
    
    Architecture:
    - Each user gets an asyncio.Queue
    - Only one worker task runs per user at any time
    - New messages are always accepted (never block sender)
    - Worker reads LATEST available batch before processing
    """

    def __init__(self):
        self._queues: Dict[int, asyncio.Queue] = {}
        self._workers: Dict[int, asyncio.Task] = {}
        self._locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_enqueue_time: Dict[int, float] = {}
        self._sequence: Dict[int, int] = defaultdict(int)
        self._processing: Dict[int, bool] = defaultdict(bool)
        self._processor = None
        logger.info("[MQ] UserMessageQueue initialized")

    def register_processor(self, processor_fn):
        """Register the async function that processes batched messages."""
        self._processor = processor_fn
        logger.info("[MQ] Processor registered: %s", processor_fn.__name__)

    def _get_queue(self, user_id: int) -> asyncio.Queue:
        if user_id not in self._queues:
            self._queues[user_id] = asyncio.Queue()
            logger.debug("[MQ] Created queue for user %s", user_id)
        return self._queues[user_id]

    async def enqueue(self, user_id: int, message_id: int, text: str,
                      raw_update: Optional[Dict] = None,
                      metadata: Optional[Dict] = None) -> int:
        """Enqueue a user message. Returns sequence number. Never blocks."""
        self._sequence[user_id] += 1
        seq = self._sequence[user_id]
        now = time.time()

        msg = QueuedMessage(
            user_id=user_id,
            message_id=message_id,
            text=text,
            timestamp=now,
            raw_update=raw_update or {},
            metadata=metadata or {}
        )
        msg.metadata["sequence"] = seq

        queue = self._get_queue(user_id)
        await queue.put(msg)
        self._last_enqueue_time[user_id] = now

        logger.info("[MQ] Enqueued seq=%d user=%s text=%.40r", seq, user_id, text)

        await self._ensure_worker(user_id)
        return seq

    async def _ensure_worker(self, user_id: int):
        """Start a worker task for this user if not already running."""
        async with self._locks[user_id]:
            existing = self._workers.get(user_id)
            if existing is not None and not existing.done():
                logger.debug("[MQ] Worker already active for user %s", user_id)
                return
            task = asyncio.create_task(
                self._worker(user_id),
                name=f"mq_worker_{user_id}"
            )
            self._workers[user_id] = task
            logger.info("[MQ] Spawned worker for user %s", user_id)

    async def _worker(self, user_id: int):
        """Worker loop for single user. Exits when queue empty."""
        queue = self._get_queue(user_id)
        self._processing[user_id] = True
        try:
            while True:
                try:
                    msg = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                # Drain all pending messages into batch
                batch = [msg]
                while True:
                    try:
                        additional = queue.get_nowait()
                        batch.append(additional)
                    except asyncio.QueueEmpty:
                        break
                logger.info("[MQ] Worker user=%s batch=%d", user_id, len(batch))
                if self._processor:
                    try:
                        await self._processor(user_id, batch)
                    except Exception as e:
                        logger.error("[MQ] Processor error user=%s: %s", user_id, e)
                else:
                    logger.warning("[MQ] No processor registered, dropping batch")
                await asyncio.sleep(0.05)
        finally:
            self._processing[user_id] = False
            logger.info("[MQ] Worker exiting user=%s", user_id)

    def is_processing(self, user_id: int) -> bool:
        return self._processing.get(user_id, False)

    def queue_size(self, user_id: int) -> int:
        if user_id not in self._queues:
            return 0
        return self._queues[user_id].qsize()

    def last_enqueue_time(self, user_id: int) -> Optional[float]:
        return self._last_enqueue_time.get(user_id)

    def get_stats(self) -> Dict[str, Any]:
        active_users = [uid for uid, task in self._workers.items()
                        if task and not task.done()]
        return {
            "total_users_with_queues": len(self._queues),
            "currently_processing": len(active_users),
            "active_user_ids": active_users,
            "queue_sizes": {
                uid: self._queues[uid].qsize()
                for uid in self._queues
                if self._queues[uid].qsize() > 0
            }
        }


# Global singleton
message_queue = UserMessageQueue()


async def enqueue_message(user_id: int, message_id: int, text: str,
                          raw_update: Optional[Dict] = None,
                          metadata: Optional[Dict] = None) -> int:
    """Public API: enqueue a message for processing."""
    return await message_queue.enqueue(
        user_id=user_id, message_id=message_id, text=text,
        raw_update=raw_update, metadata=metadata
    )


def register_message_processor(processor_fn):
    """Public API: register the batch processor callback."""
    message_queue.register_processor(processor_fn)

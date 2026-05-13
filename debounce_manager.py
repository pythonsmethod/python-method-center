"""
debounce_manager.py - Debounce Window + Message Batching
Python Method Center - PHASE 3.1A

When a user sends a message:
  1. Start a debounce timer (DEBOUNCE_WINDOW seconds)
  2. If more messages arrive before timer fires, accumulate them
  3. When timer fires, return the full batch as one input context
  4. Result: one orchestrator call with all context, not N sequential calls
"""

import asyncioh
import logging
import time
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Debounce window in seconds
# - Short enough to feel responsive
# - Long enough to catch rapid-fire messages
DEBOUNCE_WINDOW = 1.8  # seconds
DEBOUNCE_MAX_WAIT = 8.0  # never wait more than this even if messages keep arriving


@dataclass
class MessageBatch:
    """A batch of messages accumulated during debounce window."""
    user_id: int
    messages: List[Any]  # List of QueuedMessage
    batch_start: float
    batch_end: float
    merged_text: str
    message_count: int
    latest_sequence: int


class DebounceManager:
    """
    Debounce manager with per-user timer and batch accumulation.
    
    When user sends messages rapidly:
    msg1 -> start timer(1.8s) -> accumulate
    msg2 -> reset timer       -> accumulate
    msg3 -> reset timer       -> accumulate
    timer fires -> fire callback with [msg1, msg2, msg3] as one batch
    """

    def __init__(self,
                 debounce_window: float = DEBOUNCE_WINDOW,
                 max_wait: float = DEBOUNCE_MAX_WAIT):
        self.debounce_window = debounce_window
        self.max_wait = max_wait
        # Per-user accumulated messages waiting for debounce
        self._pending: Dict[int, List[Any]] = {}
        # Per-user debounce timer tasks
        self._timers: Dict[int, asyncio.Task] = {}
        # Per-user batch start time (for max_wait enforcement)
        self._batch_start: Dict[int, float] = {}
        # Registered callback for when batch is ready
        self._callback: Optional[Callable] = None
        logger.info("[DEBOUNCE] DebounceManager init window=%.1fs max_wait=%.1fs",
                    debounce_window, max_wait)

    def register_callback(self, callback: Callable):
        """Register async callback to call when batch is ready."""
        self._callback = callback
        logger.info("[DEBOUNCE] Callback registered: %s", callback.__name__)

    async def add_message(self, user_id: int, message: Any):
        """Add a message to this user queue. Resets debounce timer."""
        now = time.time()

        # Accumulate message
        if user_id not in self._pending:
            self._pending[user_id] = []
            self._batch_start[user_id] = now
            logger.debug("[DEBOUNCE] New batch started for user %s", user_id)

        self._pending[user_id].append(message)
        msg_count = len(self._pending[user_id])
        logger.info("[DEBOUNCE] Added msg user=%s total_in_batch=%d", user_id, msg_count)

        # Check if max_wait exceeded - fire immediately
        batch_age = now - self._batch_start.get(user_id, now)
        if batch_age >= self.max_wait:
            logger.warning("[DEBOUNCE] max_wait exceeded for user %s, firing immediately", user_id)
            await self._cancel_timer(user_id)
            await self._fire_batch(user_id)
            return

        # Cancel existing timer and start new one
        await self._cancel_timer(user_id)
        self._timers[user_id] = asyncio.create_task(
            self._debounce_timer(user_id),
            name=f"debounce_{user_id}"
        )

    async def _cancel_timer(self, user_id: int):
        """Cancel existing debounce timer for this user."""
        existing = self._timers.get(user_id)
        if existing and not existing.done():
            existing.cancel()
            try:
                await existing
            except asyncio.CancelledError:
                pass
            logger.debug("[DEBOUNCE] Timer cancelled for user %s", user_id)

    async def _debounce_timer(self, user_id: int):
        """Wait debounce window then fire batch."""
        try:
            await asyncio.sleep(self.debounce_window)
            await self._fire_batch(user_id)
        except asyncio.CancelledError:
            logger.debug("[DEBOUNCE] Timer task cancelled for user %s", user_id)
            raise

    async def _fire_batch(self, user_id: int):
        """Fire the accumulated batch for this user."""
        messages = self._pending.pop(user_id, [])
        self._batch_start.pop(user_id, None)
        self._timers.pop(user_id, None)

        if not messages:
            logger.debug("[DEBOUNCE] Empty batch for user %s, skipping", user_id)
            return

        batch_start = messages[0].timestamp
        batch_end = messages[-1].timestamp
        latest_seq = max(m.metadata.get("sequence", 0) for m in messages)

        # Merge texts: if single message, use as-is
        # If multiple, combine with context separator
        if len(messages) == 1:
            merged_text = messages[0].text
        else:
            parts = []
            for idx, m in enumerate(messages, start=1):
                if m.text.strip():
                    parts.append(f"[message_{idx}]:\n{m.text.strip()}")
                        merged_text = "\n\n".join(parts)
            logger.info("[DEBOUNCE] Merged %d messages for user %s into batch format",
                        len(messages), user_id)

        batch = MessageBatch(
            user_id=user_id,
            messages=messages,
            batch_start=batch_start,
            batch_end=batch_end,
            merged_text=merged_text,
            message_count=len(messages),
            latest_sequence=latest_seq
        )

        logger.info("[DEBOUNCE] Firing batch user=%s count=%d latest_seq=%d",
                    user_id, len(messages), latest_seq)

        if self._callback:
            try:
                await self._callback(batch)
            except Exception as e:
                logger.error("[DEBOUNCE] Callback error user=%s: %s", user_id, e)
        else:
            logger.warning("[DEBOUNCE] No callback registered, batch dropped")

    def is_pending(self, user_id: int) -> bool:
        """Check if user has messages pending debounce."""
        return user_id in self._pending and len(self._pending[user_id]) > 0

    def pending_count(self, user_id: int) -> int:
        """How many messages are pending for this user."""
        return len(self._pending.get(user_id, []))

    def get_stats(self) -> Dict[str, Any]:
        return {
            "users_with_pending": len(self._pending),
            "active_timers": len([t for t in self._timers.values() if t and not t.done()]),
            "pending_message_counts": {uid: len(msgs) for uid, msgs in self._pending.items()}
        }


# Global singleton
debounce_manager = DebounceManager()


async def add_to_debounce(user_id: int, message: Any):
    """Public API: add a message to debounce window."""
    await debounce_manager.add_message(user_id, message)


def register_debounce_callback(callback: Callable):
    """Public API: register the batch-ready callback."""
    debounce_manager.register_callback(callback)

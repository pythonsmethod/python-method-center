"""
response_speed_manager.py - Typing Indicator + Holding Message + Timeout Protection
Python Method Center - PHASE 3.1A

Responsibilities:
1. Send Telegram "typing..." indicator immediately on message receipt
2. If processing takes >6s, send a holding message once
3. Timeout protection: if AI takes too long, send safe fallback
4. Model routing: cheap model for classification, strong model for answers
5. Context compression before LLM: use context_package not full history
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable
from enum import Enum

logger = logging.getLogger(__name__)

# Timing configuration
TYPING_INDICATOR_INTERVAL = 4.0   # Resend typing every N seconds while processing
HOLDING_MESSAGE_THRESHOLD = 6.0   # Send holding message after this many seconds
AI_RESPONSE_TIMEOUT = 25.0        # Give up and send fallback after this many seconds
FAST_PATH_MAX_TIME = 0.3          # Fast paths must resolve in under this

# Safe fallback message (shown when AI times out)
TIMEOUT_FALLBACK_RU = (
    "Прошу прощения — обработка заняла больше времени, чем ожидалось. "
    "Я уже разбираюсь с вашим вопросом и отвечу через минуту."
)

HOLDING_MESSAGE_RU = (
    "Я вижу ваше сообщение, сейчас соберу всё в один понятный ответ."
)


class ModelTier(str, Enum):
    """Model routing tiers."""
    FAST = "fast"        # claude-haiku or gpt-3.5 — for classification
    STANDARD = "standard" # claude-sonnet — normal answers
    STRONG = "strong"    # claude-opus — complex/sensitive/escalation


# Route to model tier mapping
ROUTE_MODEL_MAP: Dict[str, ModelTier] = {
    "reception_route":   ModelTier.STANDARD,
    "individual_route":  ModelTier.STANDARD,
    "payment_route":     ModelTier.STANDARD,
    "onboarding_route":  ModelTier.STANDARD,
    "faq_route":         ModelTier.FAST,
    "support_route":     ModelTier.STRONG,   # Emotional, needs quality
    "recovery_route":    ModelTier.STRONG,   # Recovery, needs quality
    "trust_route":       ModelTier.STRONG,   # Trust repair, critical
    "analysis_route":    ModelTier.STANDARD,
    "escalation_route":  ModelTier.STRONG,   # Escalation summaries
}

# Intent type to model tier
TASK_MODEL_MAP: Dict[str, ModelTier] = {
    "classification":    ModelTier.FAST,
    "intent_detection":  ModelTier.FAST,
    "route_detection":   ModelTier.FAST,
    "emotional_state":   ModelTier.FAST,
    "complex_answer":    ModelTier.STRONG,
    "sensitive_case":    ModelTier.STRONG,
    "escalation_summary":ModelTier.STRONG,
    "long_synthesis":    ModelTier.STRONG,
    "normal_response":   ModelTier.STANDARD,
}


class ResponseSpeedManager:
    """
    Manages response timing, typing indicators, and model routing.
    
    Usage:
      async with ResponseSpeedManager.process(bot, chat_id, token) as ctx:
          response = await generate_ai_response(...)
          ctx.cancel_holding()
    """

    def __init__(self, bot, chat_id: int, user_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.user_id = user_id
        self._typing_task: Optional[asyncio.Task] = None
        self._holding_sent = False
        self._start_time = time.time()
        logger.debug("[SPEED] SpeedManager init user=%s chat=%s", user_id, chat_id)

    async def __aenter__(self):
        await self._start_typing()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._stop_typing()
        return False

    async def _start_typing(self):
        """Start sending typing indicators and schedule holding message."""
        # Send first typing indicator immediately
        await self._send_typing()
        # Start background typing loop
        self._typing_task = asyncio.create_task(
            self._typing_loop(),
            name=f"typing_{self.user_id}"
        )

    async def _stop_typing(self):
        """Cancel typing indicator loop."""
        if self._typing_task and not self._typing_task.done():
            self._typing_task.cancel()
            try:
                await self._typing_task
            except asyncio.CancelledError:
                pass
        elapsed = time.time() - self._start_time
        logger.debug("[SPEED] Typing stopped user=%s elapsed=%.1fs", self.user_id, elapsed)

    async def _send_typing(self):
        """Send Telegram typing action."""
        try:
            await self.bot.send_chat_action(self.chat_id, action="typing")
            logger.debug("[SPEED] Typing sent user=%s", self.user_id)
        except Exception as e:
            logger.debug("[SPEED] Typing send failed user=%s: %s", self.user_id, e)

    async def _typing_loop(self):
        """Continuously send typing and check for holding message threshold."""
        try:
            while True:
                await asyncio.sleep(TYPING_INDICATOR_INTERVAL)
                elapsed = time.time() - self._start_time

                # Send holding message once if threshold passed
                if elapsed >= HOLDING_MESSAGE_THRESHOLD and not self._holding_sent:
                    await self._send_holding_message()

                # Continue sending typing
                await self._send_typing()

        except asyncio.CancelledError:
            pass

    async def _send_holding_message(self):
        """Send one holding message. Only sent once per response cycle."""
        if self._holding_sent:
            return
        self._holding_sent = True
        try:
            await self.bot.send_message(self.chat_id, HOLDING_MESSAGE_RU)
            logger.info("[SPEED] Holding message sent user=%s elapsed=%.1fs",
                        self.user_id, time.time() - self._start_time)
        except Exception as e:
            logger.error("[SPEED] Holding message failed user=%s: %s", self.user_id, e)

    def holding_was_sent(self) -> bool:
        return self._holding_sent

    def elapsed(self) -> float:
        return time.time() - self._start_time


def get_model_tier(route: str, task_type: str = "normal_response") -> ModelTier:
    """
    Get the appropriate model tier for this route and task.
    Task-level override takes priority over route-level.
    """
    task_tier = TASK_MODEL_MAP.get(task_type)
    if task_tier:
        return task_tier
    return ROUTE_MODEL_MAP.get(route, ModelTier.STANDARD)


def get_model_name(tier: ModelTier) -> str:
    """Map model tier to actual model name used in API calls."""
    mapping = {
        ModelTier.FAST:     "claude-haiku-4-5",
        ModelTier.STANDARD: "claude-sonnet-4-5",
        ModelTier.STRONG:   "claude-opus-4-5",
    }
    return mapping.get(tier, "claude-sonnet-4-5")


async def run_with_timeout(coro, timeout: float = AI_RESPONSE_TIMEOUT, fallback: str = TIMEOUT_FALLBACK_RU):
    """
    Run a coroutine with timeout protection.
    Returns (result, timed_out) tuple.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result, False
    except asyncio.TimeoutError:
        logger.error("[SPEED] AI response TIMEOUT after %.1fs", timeout)
        return fallback, True
    except Exception as e:
        logger.error("[SPEED] AI response ERROR: %s", e)
        return fallback, True


def compress_context_for_llm(context_package: Dict, max_history: int = 5) -> Dict:
    """
    Compress context before sending to LLM.
    Never send full session history - use last N messages + memory summary.
    """
    if not context_package:
        return {}

    compressed = {
        "user_id": context_package.get("user_id"),
        "current_route": context_package.get("current_route"),
        "current_stage": context_package.get("current_stage"),
        "active_agent": context_package.get("active_agent"),
        "client_name": context_package.get("client_name"),
        "emotional_state": context_package.get("emotional_state"),
        "risk_level": context_package.get("risk_level"),
        "payment_status": context_package.get("payment_status"),
    }

    # Last N messages only
    history = context_package.get("message_history", [])
    if history:
        compressed["recent_messages"] = history[-max_history:]

    # Include memory summary if available
    if context_package.get("memory_summary"):
        compressed["memory_summary"] = context_package["memory_summary"]

    logger.debug("[SPEED] Context compressed: %d history items -> %d",
                 len(history), len(compressed.get("recent_messages", [])))
    return compressed

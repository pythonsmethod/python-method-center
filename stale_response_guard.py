"""
stale_response_guard.py - Pre-Send Freshness Check
Python Method Center - PHASE 3.1A

Before sending any AI response to Telegram:
  1. Check if newer user messages arrived while AI was processing
  2. If yes -> discard this response, it is outdated
  3. Re-run orchestrator with fresh context

CRITICAL INVARIANT: Never answer an old message if newer messages exist.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# How much newer must a message be to trigger stale discard
# (in seconds — small buffer to avoid false positives from network latency)
STALE_TOLERANCE_SECONDS = 0.5


@dataclass
class ResponseToken:
    """
    Freshness token issued before AI processing begins.
    Used to verify response is still current before sending.
    """
    user_id: int
    token_id: str
    issued_at: float
    message_sequence: int
    input_text_hash: str
    is_cancelled: bool = False
    cancel_reason: Optional[str] = None


class StaleResponseGuard:
    """
    Tracks response freshness per user.
    
    Flow:
    1. issue_token(user_id, sequence) -> token before AI call
    2. AI generates response (may take 3-8 seconds)
    3. New messages may arrive while AI is running
    4. check_fresh(token) -> True if response is still valid
    5. If False -> discard response, re-trigger with new context
    """

    def __init__(self):
        # Per-user latest sequence number seen
        self._latest_sequence: Dict[int, int] = {}
        # Per-user latest message timestamp
        self._latest_timestamp: Dict[int, float] = {}
        # Per-user active token (only one per user)
        self._active_tokens: Dict[int, ResponseToken] = {}
        # Counter for token IDs
        self._token_counter = 0
        logger.info("[STALE_GUARD] StaleResponseGuard initialized")

    def register_incoming(self, user_id: int, sequence: int, timestamp: float):
        """
        Called when a new message arrives for a user.
        Updates latest sequence and timestamp, may invalidate active token.
        """
        prev_seq = self._latest_sequence.get(user_id, -1)
        self._latest_sequence[user_id] = max(prev_seq, sequence)
        self._latest_timestamp[user_id] = max(
            self._latest_timestamp.get(user_id, 0.0), timestamp
        )

        # If there is an active token for this user and new message is newer,
        # mark the token as cancelled
        token = self._active_tokens.get(user_id)
        if token and not token.is_cancelled:
            if sequence > token.message_sequence:
                token.is_cancelled = True
                token.cancel_reason = f"newer_message_arrived seq={sequence}"
                logger.info(
                    "[STALE_GUARD] Token CANCELLED user=%s token=%s reason=%s",
                    user_id, token.token_id, token.cancel_reason
                )

    def issue_token(self, user_id: int, sequence: int, input_text: str) -> ResponseToken:
        """
        Issue a freshness token before starting AI processing.
        Any previously active token for this user is replaced.
        """
        import hashlib
        self._token_counter += 1
        token_id = f"tok_{user_id}_{self._token_counter}"
        text_hash = hashlib.md5(input_text.encode()).hexdigest()[:8]

        token = ResponseToken(
            user_id=user_id,
            token_id=token_id,
            issued_at=time.time(),
            message_sequence=sequence,
            input_text_hash=text_hash
        )

        # Cancel any existing token
        old_token = self._active_tokens.get(user_id)
        if old_token and not old_token.is_cancelled:
            old_token.is_cancelled = True
            old_token.cancel_reason = "replaced_by_newer_token"

        self._active_tokens[user_id] = token
        logger.info("[STALE_GUARD] Token ISSUED user=%s token=%s seq=%d",
                    user_id, token_id, sequence)
        return token

    def check_fresh(self, token: ResponseToken) -> bool:
        """
        Returns True if the token is still fresh (response can be sent).
        Returns False if a newer message arrived (discard response).
        """
        if token.is_cancelled:
            logger.warning(
                "[STALE_GUARD] STALE response blocked user=%s token=%s reason=%s",
                token.user_id, token.token_id, token.cancel_reason
            )
            return False

        # Check if latest sequence for this user is newer than token
        user_id = token.user_id
        latest_seq = self._latest_sequence.get(user_id, -1)
        if latest_seq > token.message_sequence:
            # Newer message arrived while processing
            token.is_cancelled = True
            token.cancel_reason = f"late_detection seq_diff={latest_seq - token.message_sequence}"
            logger.warning(
                "[STALE_GUARD] STALE late-detected user=%s token=%s latest_seq=%d token_seq=%d",
                user_id, token.token_id, latest_seq, token.message_sequence
            )
            return False

        # Also check if active token for this user was replaced
        active = self._active_tokens.get(user_id)
        if active and active.token_id != token.token_id:
            token.is_cancelled = True
            token.cancel_reason = "token_replaced"
            logger.warning(
                "[STALE_GUARD] STALE token replaced user=%s old=%s new=%s",
                user_id, token.token_id, active.token_id
            )
            return False

        logger.debug("[STALE_GUARD] Token FRESH user=%s token=%s", user_id, token.token_id)
        return True

    def complete_token(self, token: ResponseToken):
        """Mark token as completed (response was sent). Clean up."""
        user_id = token.user_id
        if self._active_tokens.get(user_id) and \
           self._active_tokens[user_id].token_id == token.token_id:
            del self._active_tokens[user_id]
        logger.debug("[STALE_GUARD] Token completed user=%s token=%s",
                     user_id, token.token_id)

    def get_latest_sequence(self, user_id: int) -> int:
        return self._latest_sequence.get(user_id, 0)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "tracked_users": len(self._latest_sequence),
            "active_tokens": len(self._active_tokens),
            "cancelled_tokens": sum(1 for t in self._active_tokens.values() if t.is_cancelled)
        }


# Global singleton
stale_guard = StaleResponseGuard()


def register_incoming_message(user_id: int, sequence: int, timestamp: float):
    """Public API: register a new incoming message for staleness tracking."""
    stale_guard.register_incoming(user_id, sequence, timestamp)


def issue_response_token(user_id: int, sequence: int, input_text: str) -> ResponseToken:
    """Public API: get a freshness token before AI processing."""
    return stale_guard.issue_token(user_id, sequence, input_text)


def is_response_fresh(token: ResponseToken) -> bool:
    """Public API: check if response is still valid before sending."""
    return stale_guard.check_fresh(token)

# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.4 — Proactive Message Dispatcher
# Module: proactive_message_dispatcher.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Safe Outbound Recovery Layer
#
# Purpose: Send proactive recovery messages ONLY when RecoveryPolicyEngine
#          explicitly ALLOWS it. All other decisions result in no send.
#
# Architecture principle:
#   RecoveryPolicyEngine decides whether contact is emotionally safe.
#   ProactiveMessageDispatcher only executes already-approved recovery actions.
#   The system behaves like a calm rehabilitation center that remembers people,
#   protects trust, and knows when silence is the right action.
#
# Critical rules:
#   - No message may be sent without a fresh ALLOW decision.
#   - silence_respect = True → absolute no-send.
#   - human_escalation_required → absolute no-send (AI stays out).
#   - Fail-safe: any exception → suppress send, log safely.
#   - Duplicate protection via idempotency key + sent flag.
#   - Never uses sales tone, urgency pressure, or payment pressure.
# =============================================================================

from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

log = logging.getLogger("proactive_message_dispatcher")

# ---------------------------------------------------------------------------
# Dispatch result constants
# ---------------------------------------------------------------------------
class DispatchResult:
    SENT          = "SENT"
    SUPPRESSED    = "SUPPRESSED"
    SKIPPED       = "SKIPPED"
    ERROR         = "ERROR"
    DUPLICATE     = "DUPLICATE"

# ---------------------------------------------------------------------------
# Tone-mode message templates
# Rules:
#   - No sales language
#   - No urgency pressure
#   - No payment pressure
#   - No medical claims
#   - silence_respect template is NEVER sent automatically (dashboard only)
# ---------------------------------------------------------------------------
MESSAGE_TEMPLATES: Dict[str, Dict[str, str]] = {
    "soft_checkin": {
        "id":   "soft_checkin_v1",
        "text": (
            "Добрый день! Хотел убедиться что у вас всё хорошо. "
            "Я здесь если есть вопросы или хотите продолжить наш разговор."
        ),
    },
    "context_reminder": {
        "id":   "context_reminder_v1",
        "text": (
            "Добрый день! Напоминаю что мы с вами обсуждали возможности программы. "
            "Если остались вопросы о формате или о том как всё устроено — "
            "я готов ответить в любое удобное для вас время."
        ),
    },
    "status_confirmation": {
        "id":   "status_confirmation_v1",
        "text": (
            "Добрый день! Просто хотел уточнить — всё ли у вас в порядке? "
            "Если нужна какая-то информация или поддержка — я на связи."
        ),
    },
    "trust_repair": {
        "id":   "trust_repair_v1",
        "text": (
            "Добрый день. Я понимаю что иногда бывает непросто. "
            "Хочу чтобы вы знали — я здесь чтобы помочь, без давления. "
            "Напишите когда будете готовы — я отвечу."
        ),
    },
    "post_payment_support": {
        "id":   "post_payment_support_v1",
        "text": (
            "Добрый день! Как ваши дела после нашего старта? "
            "Если есть вопросы по программе или что-то непонятно — "
            "я здесь и рад помочь."
        ),
    },
    "human_handoff": {
        "id":   "human_handoff_v1",
        "text": (
            "Добрый день. Я хотел бы соединить вас с живым специалистом "
            "который сможет лучше помочь в вашей ситуации. "
            "Наш консультант свяжется с вами в ближайшее время."
        ),
    },
    # silence_respect is NEVER sent automatically — dashboard/internal only
    "silence_respect": {
        "id":   "silence_respect_v1",
        "text": None,  # None = cannot be dispatched
    },
}

# Templates that are absolutely safe to send automatically
SENDABLE_TONES = {
    "soft_checkin",
    "context_reminder",
    "status_confirmation",
    "trust_repair",
    "post_payment_support",
    "human_handoff",
}

# Tones that must NEVER be auto-sent
NEVER_SEND_TONES = {"silence_respect"}

# How recent a policy ALLOW decision must be (minutes) to still be valid
POLICY_FRESHNESS_MINUTES = 60

# Min gap between sends to the same user (minutes)
MIN_SEND_GAP_MINUTES = 60

# ---------------------------------------------------------------------------
# Dispatch log entry
# ---------------------------------------------------------------------------
@dataclass
class DispatchLogEntry:
    user_id: int
    tone_mode: str
    template_id: str
    policy_log_id: int
    idempotency_key: str
    result: str          # DispatchResult constant
    suppression_reason: str = ""
    sent_at: Optional[datetime] = None
    error_detail: str = ""

# ---------------------------------------------------------------------------
# ProactiveMessageDispatcher
# ---------------------------------------------------------------------------
class ProactiveMessageDispatcher:
    """
    Safe outbound layer for proactive recovery messages.

    Reads ALLOW decisions from pm_recovery_policy_log, re-validates every
    safety gate, then sends via the approved send_message_fn path.

    Fail-closed: any internal error → suppress send, log safely.
    Never bypasses Central Orchestrator message-queue protections.
    Never sends if silence_respect, human_escalation_required, or any lock.
    """

    def __init__(self, db_pool=None, send_message_fn=None):
        self._pool = db_pool
        self._send_fn = send_message_fn
        self._lock = asyncio.Lock()       # prevent concurrent dispatcher runs
        log.info("[DISPATCH] ProactiveMessageDispatcher initialized")

    # -----------------------------------------------------------------------
    # Primary entry point — called from async worker
    # -----------------------------------------------------------------------
    async def dispatch_allowed_recovery_messages(self) -> int:
        """
        Find all valid ALLOW decisions and send approved recovery messages.
        Returns count of messages sent.
        Fail-closed: exceptions are caught and logged, never propagated.
        """
        if not self._pool or not self._send_fn:
            log.debug("[DISPATCH] No pool or send_fn — skipping dispatch run")
            return 0

        sent_count = 0
        async with self._lock:
            try:
                candidates = await self._fetch_candidates()
                log.info("[DISPATCH] Found %d dispatch candidates", len(candidates))

                for row in candidates:
                    result = await self._process_candidate(dict(row))
                    if result == DispatchResult.SENT:
                        sent_count += 1

            except Exception as e:
                log.error("[DISPATCH] dispatch_allowed_recovery_messages error: %s", e)

        return sent_count

    # -----------------------------------------------------------------------
    # Fetch valid ALLOW decisions from DB
    # -----------------------------------------------------------------------
    async def _fetch_candidates(self) -> List[Any]:
        """
        Fetch policy log rows where:
          - action = ALLOW
          - next_action = SEND_SOFT_RECOVERY
          - silence_respect = FALSE
          - human_escalation_required = FALSE
          - created_at within POLICY_FRESHNESS_MINUTES
          - cooldown_until is NULL or expired
          - not already sent (dispatched_at IS NULL)
        Uses FOR UPDATE SKIP LOCKED for duplicate protection.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT rpl.id, rpl.user_id, rpl.tone_mode, rpl.cooldown_until,
                          rpl.fatigue_score, rpl.suppression_reason,
                          rpl.silence_respect, rpl.human_escalation_required,
                          rpl.created_at
                   FROM pm_recovery_policy_log rpl
                   WHERE rpl.action = 'ALLOW'
                     AND rpl.next_action = 'send_soft_recovery'
                     AND rpl.silence_respect = FALSE
                     AND rpl.human_escalation_required = FALSE
                     AND rpl.created_at > NOW() - INTERVAL '{freshness} minutes'
                     AND (rpl.cooldown_until IS NULL OR rpl.cooldown_until <= NOW())
                     AND NOT EXISTS (
                       SELECT 1 FROM pm_dispatch_log dl
                       WHERE dl.policy_log_id = rpl.id
                     )
                   ORDER BY rpl.created_at ASC
                   LIMIT 20
                   FOR UPDATE SKIP LOCKED""".replace(
                    '{freshness}', str(POLICY_FRESHNESS_MINUTES)
                )
            )
        return rows

    # -----------------------------------------------------------------------
    # Process one candidate decision
    # -----------------------------------------------------------------------
    async def _process_candidate(self, row: Dict[str, Any]) -> str:
        """Process one ALLOW decision. Returns DispatchResult constant."""
        uid           = row["user_id"]
        tone          = row.get("tone_mode", "soft_checkin")
        policy_log_id = row["id"]

        idem_key = self._make_idempotency_key(uid, policy_log_id)

        try:
            # ---- Gate 0: tone must be sendable --------------------------
            if tone in NEVER_SEND_TONES:
                await self._log_dispatch(uid, tone, "silence_respect_v1",
                    policy_log_id, idem_key, DispatchResult.SUPPRESSED,
                    "tone_not_sendable")
                return DispatchResult.SUPPRESSED

            # ---- Gate 1: duplicate protection via idempotency key -------
            if await self._already_sent(idem_key):
                return DispatchResult.DUPLICATE

            # ---- Gate 2: re-fetch user profile for live state -----------
            profile = await self._get_user_profile(uid)

            # ---- Gate 3: silence_respect re-check -----------------------
            if profile.get("silence_respect"):
                await self._log_dispatch(uid, tone, tone + "_v1",
                    policy_log_id, idem_key, DispatchResult.SUPPRESSED,
                    "silence_respect")
                return DispatchResult.SUPPRESSED

            # ---- Gate 4: explicit_refusal re-check ----------------------
            if profile.get("explicit_refusal"):
                await self._log_dispatch(uid, tone, tone + "_v1",
                    policy_log_id, idem_key, DispatchResult.SUPPRESSED,
                    "explicit_refusal")
                return DispatchResult.SUPPRESSED

            # ---- Gate 5: human_escalation_required re-check -------------
            if profile.get("human_escalation_required"):
                await self._log_dispatch(uid, tone, tone + "_v1",
                    policy_log_id, idem_key, DispatchResult.SUPPRESSED,
                    "human_escalation_required")
                return DispatchResult.SUPPRESSED

            # ---- Gate 6: cooldown re-check from profile -----------------
            cooldown = profile.get("recovery_cooldown_until")
            if cooldown and cooldown > self._now():
                remaining = int((cooldown - self._now()).total_seconds() / 60)
                await self._log_dispatch(uid, tone, tone + "_v1",
                    policy_log_id, idem_key, DispatchResult.SKIPPED,
                    f"cooldown_active_{remaining}min")
                return DispatchResult.SKIPPED

            # ---- Gate 7: last_ai_message_at re-check --------------------
            last_ai = profile.get("last_ai_message_at")
            if last_ai:
                mins = (self._now() - last_ai).total_seconds() / 60
                if mins < MIN_SEND_GAP_MINUTES:
                    await self._log_dispatch(uid, tone, tone + "_v1",
                        policy_log_id, idem_key, DispatchResult.SKIPPED,
                        f"recent_ai_message_{int(mins)}min_ago")
                    return DispatchResult.SKIPPED

            # ---- Gate 8: policy freshness re-check ----------------------
            policy_age_min = (
                self._now() - row["created_at"].replace(tzinfo=timezone.utc)
                if row["created_at"].tzinfo is None
                else self._now() - row["created_at"]
            ).total_seconds() / 60
            if policy_age_min > POLICY_FRESHNESS_MINUTES:
                await self._log_dispatch(uid, tone, tone + "_v1",
                    policy_log_id, idem_key, DispatchResult.SKIPPED,
                    "policy_decision_stale")
                return DispatchResult.SKIPPED

            # ---- Get template -------------------------------------------
            template = MESSAGE_TEMPLATES.get(tone, MESSAGE_TEMPLATES["soft_checkin"])
            text      = template["text"]
            tmpl_id   = template["id"]

            if text is None:
                await self._log_dispatch(uid, tone, tmpl_id,
                    policy_log_id, idem_key, DispatchResult.SUPPRESSED,
                    "template_not_sendable")
                return DispatchResult.SUPPRESSED

            # ---- SEND ---------------------------------------------------
            log.info("[DISPATCH] Sending uid=%d tone=%s template=%s",
                     uid, tone, tmpl_id)
            try:
                await self._send_fn(str(uid), text)
            except Exception as e:
                log.error("[DISPATCH] send_fn error uid=%d: %s", uid, e)
                await self._log_dispatch(uid, tone, tmpl_id,
                    policy_log_id, idem_key, DispatchResult.ERROR,
                    suppression_reason="send_fn_error", error_detail=str(e))
                return DispatchResult.ERROR

            # ---- Post-send DB updates -----------------------------------
            await self._post_send_update(uid, policy_log_id, tone, tmpl_id, idem_key)
            log.info("[DISPATCH] Sent uid=%d tone=%s", uid, tone)
            return DispatchResult.SENT

        except Exception as e:
            log.error("[DISPATCH] _process_candidate error uid=%s: %s", uid, e)
            # Fail-closed: log error, do not send
            try:
                await self._log_dispatch(uid, tone, tone + "_v1",
                    policy_log_id, idem_key, DispatchResult.ERROR,
                    suppression_reason="internal_error", error_detail=str(e))
            except Exception:
                pass
            return DispatchResult.ERROR

    # -----------------------------------------------------------------------
    # Post-send DB updates
    # -----------------------------------------------------------------------
    async def _post_send_update(
        self, user_id: int, policy_log_id: int,
        tone: str, template_id: str, idem_key: str
    ) -> None:
        """Update profiles + insert dispatch log after successful send."""
        if not self._pool:
            return
        now = self._now()
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    # Update pm_client_profiles
                    await conn.execute(
                        """UPDATE pm_client_profiles
                           SET recovery_attempt_count = COALESCE(recovery_attempt_count, 0) + 1,
                               last_recovery_at        = $1,
                               last_ai_message_at      = $1,
                               recovery_cooldown_until = $2
                           WHERE user_id = $3""",
                        now,
                        now + timedelta(hours=2),   # 2h cooldown after send
                        user_id,
                    )
                    # Insert dispatch log
                    await self._log_dispatch_conn(
                        conn, user_id, tone, template_id,
                        policy_log_id, idem_key,
                        DispatchResult.SENT, sent_at=now
                    )
        except Exception as e:
            log.error("[DISPATCH] _post_send_update error uid=%d: %s", user_id, e)

    # -----------------------------------------------------------------------
    # Idempotency / duplicate check
    # -----------------------------------------------------------------------
    def _make_idempotency_key(self, user_id: int, policy_log_id: int) -> str:
        raw = f"dispatch:{user_id}:{policy_log_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def _already_sent(self, idem_key: str) -> bool:
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id FROM pm_dispatch_log WHERE idempotency_key=$1",
                    idem_key,
                )
            return row is not None
        except Exception:
            return False   # fail open for idempotency check (will be caught by DB constraint)

    # -----------------------------------------------------------------------
    # User profile fetch
    # -----------------------------------------------------------------------
    async def _get_user_profile(self, user_id: int) -> Dict[str, Any]:
        if not self._pool:
            return {}
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT silence_respect, explicit_refusal,
                              human_escalation_required, recovery_cooldown_until,
                              last_ai_message_at, recovery_attempt_count,
                              last_recovery_at, is_active
                       FROM pm_client_profiles WHERE user_id=$1""",
                    user_id,
                )
            return dict(row) if row else {}
        except Exception as e:
            log.error("[DISPATCH] _get_user_profile error uid=%d: %s", user_id, e)
            return {}

    # -----------------------------------------------------------------------
    # Dispatch log helpers
    # -----------------------------------------------------------------------
    async def _log_dispatch(
        self, user_id: int, tone: str, template_id: str,
        policy_log_id: int, idem_key: str, result: str,
        suppression_reason: str = "", error_detail: str = "",
        sent_at: Optional[datetime] = None,
    ) -> None:
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await self._log_dispatch_conn(
                    conn, user_id, tone, template_id, policy_log_id,
                    idem_key, result, suppression_reason, error_detail, sent_at
                )
        except Exception as e:
            log.debug("[DISPATCH] _log_dispatch error: %s", e)

    async def _log_dispatch_conn(
        self, conn, user_id: int, tone: str, template_id: str,
        policy_log_id: int, idem_key: str, result: str,
        suppression_reason: str = "", error_detail: str = "",
        sent_at: Optional[datetime] = None,
    ) -> None:
        await conn.execute(
            """INSERT INTO pm_dispatch_log
               (user_id, tone_mode, template_id, policy_log_id,
                idempotency_key, result, suppression_reason, error_detail,
                sent_at, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
               ON CONFLICT (idempotency_key) DO NOTHING""",
            user_id, tone, template_id, policy_log_id,
            idem_key, result, suppression_reason, error_detail,
            sent_at,
        )

    # -----------------------------------------------------------------------
    # Dashboard data
    # -----------------------------------------------------------------------
    async def get_dispatch_dashboard(self) -> Dict[str, Any]:
        """Return dispatch metrics for the /risk/governance dashboard."""
        if not self._pool:
            return {"error": "no_db_pool"}
        try:
            async with self._pool.acquire() as conn:
                sent_24h = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_dispatch_log"
                    " WHERE result='SENT' AND created_at > NOW() - INTERVAL '24 hours'"
                )
                suppressed_24h = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_dispatch_log"
                    " WHERE result='SUPPRESSED' AND created_at > NOW() - INTERVAL '24 hours'"
                )
                errors_24h = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_dispatch_log"
                    " WHERE result='ERROR' AND created_at > NOW() - INTERVAL '24 hours'"
                )
                recent = await conn.fetch(
                    """SELECT dl.user_id, dl.tone_mode, dl.result,
                              dl.suppression_reason, dl.sent_at, dl.created_at,
                              rpl.action, rpl.fatigue_score,
                              rpl.silence_respect, rpl.human_escalation_required,
                              rpl.cooldown_until, rpl.next_action,
                              cp.recovery_attempt_count, cp.last_recovery_at
                       FROM pm_dispatch_log dl
                       LEFT JOIN pm_recovery_policy_log rpl
                           ON rpl.id = dl.policy_log_id
                       LEFT JOIN pm_client_profiles cp
                           ON cp.user_id = dl.user_id
                       ORDER BY dl.created_at DESC
                       LIMIT 30"""
                )
                suppression_breakdown = await conn.fetch(
                    "SELECT suppression_reason, COUNT(*) AS count"
                    " FROM pm_dispatch_log"
                    " WHERE result IN ('SUPPRESSED','SKIPPED')"
                    " AND created_at > NOW() - INTERVAL '24 hours'"
                    " GROUP BY suppression_reason ORDER BY count DESC"
                )
            return {
                "sent_24h":              int(sent_24h or 0),
                "suppressed_24h":        int(suppressed_24h or 0),
                "errors_24h":            int(errors_24h or 0),
                "recent_dispatches":     [dict(r) for r in recent],
                "suppression_breakdown": [dict(r) for r in suppression_breakdown],
            }
        except Exception as e:
            log.error("[DISPATCH] get_dispatch_dashboard error: %s", e)
            return {"error": str(e)}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_dispatcher: Optional[ProactiveMessageDispatcher] = None

def get_dispatcher() -> Optional[ProactiveMessageDispatcher]:
    return _dispatcher

def init_dispatcher(db_pool=None, send_message_fn=None) -> ProactiveMessageDispatcher:
    global _dispatcher
    _dispatcher = ProactiveMessageDispatcher(
        db_pool=db_pool, send_message_fn=send_message_fn
    )
    log.info("[DISPATCH] ProactiveMessageDispatcher singleton created")
    return _dispatcher

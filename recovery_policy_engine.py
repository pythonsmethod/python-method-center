# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.3 — Proactive Engagement Governance
# Module: recovery_policy_engine.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Recovery Policy Engine
#
# Purpose: Decide whether proactive contact is allowed, suppressed, delayed,
#          softened, or escalated. Emotional-governed continuity infrastructure.
#          This is NOT marketing automation.
#
# Core method:
#   evaluate_recovery_policy(user_context, risk_profile, route_state,
#                            memory_state) -> RecoveryPolicyDecision
#
# Actions: ALLOW / DELAY / SUPPRESS / ESCALATE_HUMAN / SILENCE_RESPECT
#
# Architecture principle:
#   The system behaves like a calm, emotionally-governed rehabilitation center
#   that remembers people, protects trust, and knows when not to speak.
# =============================================================================

from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("recovery_policy_engine")

# ---------------------------------------------------------------------------
# Action constants
# ---------------------------------------------------------------------------
class PolicyAction:
    ALLOW             = "ALLOW"
    DELAY             = "DELAY"
    SUPPRESS          = "SUPPRESS"
    ESCALATE_HUMAN    = "ESCALATE_HUMAN"
    SILENCE_RESPECT   = "SILENCE_RESPECT"

# ---------------------------------------------------------------------------
# Tone mode constants
# ---------------------------------------------------------------------------
class ToneMode:
    SOFT_CHECKIN         = "soft_checkin"
    CONTEXT_REMINDER     = "context_reminder"
    STATUS_CONFIRMATION  = "status_confirmation"
    TRUST_REPAIR         = "trust_repair"
    POST_PAYMENT_SUPPORT = "post_payment_support"
    HUMAN_HANDOFF        = "human_handoff"
    SILENCE_RESPECT      = "silence_respect"

# ---------------------------------------------------------------------------
# Recovery channel constants
# ---------------------------------------------------------------------------
class RecoveryChannel:
    AI_MESSAGE      = "ai_message"
    HUMAN_AGENT     = "human_agent"
    DASHBOARD_ONLY  = "dashboard_only"
    NONE            = "none"

# ---------------------------------------------------------------------------
# Next-action constants
# ---------------------------------------------------------------------------
class NextAction:
    SEND_SOFT_RECOVERY   = "send_soft_recovery"
    WAIT                 = "wait"
    SUPPRESS             = "suppress"
    ESCALATE_TO_HUMAN    = "escalate_to_human"
    MARK_SILENCE_RESPECT = "mark_silence_respect"
    DASHBOARD_ONLY       = "dashboard_only"

# ---------------------------------------------------------------------------
# Stage cooldown matrix (minutes between outbound contacts)
# ---------------------------------------------------------------------------
STAGE_COOLDOWN_MINUTES: Dict[str, int] = {
    "pre_payment_interest":        180,
    "payment_hesitation":          240,
    "post_payment_silence":        720,
    "onboarding_incomplete":       360,
    "data_collection_incomplete":  480,
    "analysis_missing":            480,
    "emotional_overload":         1440,
    "distrust_loop":               720,
    "explicit_refusal":           4320,
    "repeated_failed_recovery":   2880,
    "default":                     120,
}

# Max automated recovery attempts before silence-respect kicks in
MAX_AUTO_ATTEMPTS: Dict[str, int] = {
    "pre_payment_interest":       4,
    "payment_hesitation":         2,
    "post_payment_silence":       3,
    "onboarding_incomplete":      3,
    "data_collection_incomplete": 3,
    "analysis_missing":           3,
    "emotional_overload":         1,
    "distrust_loop":              2,
    "explicit_refusal":           0,
    "repeated_failed_recovery":   0,
    "default":                    3,
}

IGNORED_SILENCE_MINUTES  = 120
FATIGUE_MEDIUM_THRESHOLD = 0.4
FATIGUE_HIGH_THRESHOLD   = 0.7

STOP_KEYWORDS = {
    "stop", "later", "not now", "leave me", "enough", "don't message",
    "don't contact", "no thanks", "no thank you", "go away",
    "stop", "ne pishi", "ne bespokoy", "ne seychas", "potom", "pozhe",
    "ostav menya", "hvatit", "dostatochno", "ne nado", "ne hochu",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class UserContext:
    user_id: int
    current_stage: str = "unknown"
    payment_status: str = "none"
    last_message_at: Optional[datetime] = None
    last_ai_message_at: Optional[datetime] = None
    last_recovery_at: Optional[datetime] = None
    recovery_attempt_count: int = 0
    is_human_escalated: bool = False
    route_lock_active: bool = False
    trust_route_active: bool = False
    silence_respect: bool = False
    explicit_refusal: bool = False
    recent_messages: List[str] = field(default_factory=list)

@dataclass
class RiskProfile:
    risk_type: str = "none"
    risk_level: str = "low"
    current_risk_score: float = 0.0
    confidence: float = 0.0
    recommended_action: str = ""

@dataclass
class RouteState:
    active_route: str = "general"
    route_locked: bool = False
    escalation_active: bool = False
    last_route_change_at: Optional[datetime] = None

@dataclass
class MemoryState:
    fear_signal_count: int = 0
    emotional_spike_count: int = 0
    recovery_ignored_count: int = 0
    repeated_question_count: int = 0
    irritation_signals: int = 0
    total_session_count: int = 0
    recent_text_signals: List[str] = field(default_factory=list)

@dataclass
class RecoveryPolicyDecision:
    user_id: int
    action: str
    reason: str
    cooldown_until: Optional[datetime]
    max_attempts_remaining: int
    tone_mode: str
    recovery_channel: str
    dashboard_flags: Dict[str, Any] = field(default_factory=dict)
    human_escalation_required: bool = False
    next_action: str = NextAction.WAIT
    fatigue_score: float = 0.0
    suppression_reason: str = ""
    silence_respect: bool = False
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.cooldown_until:
            d["cooldown_until"] = self.cooldown_until.isoformat()
        return d

SAFETY_NEVER_TRIGGER = {
    "medical_diagnosis",
    "payment_pressure",
    "emergency_override",
    "spam_recovery",
    "route_lock_bypass",
    "sales_tone",
    "urgency_pressure",
}

# ---------------------------------------------------------------------------
# RecoveryPolicyEngine
# ---------------------------------------------------------------------------
class RecoveryPolicyEngine:
    """
    Governs whether, when, how, and through which channel proactive contact
    can occur. Must be called before any outbound recovery message is sent.
    Fail-safe: if this engine raises an exception, proactive contact is suppressed.
    """

    def __init__(self, db_pool=None):
        self._pool = db_pool
        log.info("[POLICY] RecoveryPolicyEngine initialized")

    async def evaluate_recovery_policy(
        self,
        user_context: UserContext,
        risk_profile: RiskProfile,
        route_state: RouteState,
        memory_state: MemoryState,
    ) -> RecoveryPolicyDecision:
        """
        Evaluate governance rules — hard-stop gates ordered by severity.
        Gate order:
          1 silence_respect already set
          2 explicit refusal / stop keyword
          3 human escalation active
          4 route lock / trust lock
          5 emotional overload high/critical
          6 cooldown active
          7 max attempts reached
          8 recovery fatigue high
          9 recent AI message < 60 min ago
         10 unresolved critical risk → human
         11 payment pressure guard
         12 distrust loop → trust_repair
         13 ALLOW — all gates passed
        """
        uid = user_context.user_id
        try:
            fatigue  = self._compute_fatigue_score(user_context, memory_state)
            stage    = self._resolve_stage(user_context, risk_profile)
            cdmin    = STAGE_COOLDOWN_MINUTES.get(stage, STAGE_COOLDOWN_MINUTES["default"])
            maxatt   = MAX_AUTO_ATTEMPTS.get(stage, MAX_AUTO_ATTEMPTS["default"])
            att_done = user_context.recovery_attempt_count
            att_rem  = max(0, maxatt - att_done)

            # Gate 1
            if user_context.silence_respect:
                return self._dec(uid, PolicyAction.SILENCE_RESPECT,
                    "User is in silence_respect mode — no automated contact",
                    None, 0, ToneMode.SILENCE_RESPECT, RecoveryChannel.NONE,
                    fatigue, stage, NextAction.MARK_SILENCE_RESPECT,
                    silence_respect=True)

            # Gate 2
            if user_context.explicit_refusal or self._has_stop_signal(
                    user_context.recent_messages):
                cu = self._now() + timedelta(minutes=STAGE_COOLDOWN_MINUTES["explicit_refusal"])
                await self._persist(uid, PolicyAction.SUPPRESS, "explicit_refusal", cu)
                return self._dec(uid, PolicyAction.SUPPRESS,
                    "Explicit refusal detected — contact suppressed 72h",
                    cu, 0, ToneMode.SILENCE_RESPECT, RecoveryChannel.NONE,
                    fatigue, stage, NextAction.SUPPRESS, sr="explicit_refusal")

            # Gate 3
            if user_context.is_human_escalated or route_state.escalation_active:
                return self._dec(uid, PolicyAction.ESCALATE_HUMAN,
                    "Active human escalation — AI recovery suppressed",
                    None, att_rem, ToneMode.HUMAN_HANDOFF,
                    RecoveryChannel.HUMAN_AGENT, fatigue, stage,
                    NextAction.ESCALATE_TO_HUMAN, he=True)

            # Gate 4
            if route_state.route_locked or user_context.route_lock_active:
                return self._dec(uid, PolicyAction.SUPPRESS,
                    "Route lock or trust lock active — AI contact blocked",
                    None, att_rem, ToneMode.SILENCE_RESPECT,
                    RecoveryChannel.NONE, fatigue, stage,
                    NextAction.SUPPRESS, sr="route_lock_active")

            # Gate 5
            if risk_profile.risk_type == "emotional_overload_risk" and                risk_profile.risk_level in ("high", "critical"):
                cu = self._now() + timedelta(minutes=STAGE_COOLDOWN_MINUTES["emotional_overload"])
                await self._persist(uid, PolicyAction.SUPPRESS, "emotional_overload", cu)
                return self._dec(uid, PolicyAction.SUPPRESS,
                    "Emotional overload high — 24h silence enforced",
                    cu, att_rem, ToneMode.SILENCE_RESPECT,
                    RecoveryChannel.NONE, fatigue, stage,
                    NextAction.SUPPRESS, sr="emotional_overload")

            # Gate 6
            if user_context.last_recovery_at:
                elapsed = (self._now() - user_context.last_recovery_at).total_seconds() / 60
                if elapsed < cdmin:
                    rem = int(cdmin - elapsed)
                    cu  = user_context.last_recovery_at + timedelta(minutes=cdmin)
                    return self._dec(uid, PolicyAction.DELAY,
                        f"Cooldown active — {rem}min remaining for stage '{stage}'",
                        cu, att_rem, self._tone(risk_profile, stage),
                        RecoveryChannel.NONE, fatigue, stage, NextAction.WAIT)

            # Gate 7
            if att_rem <= 0:
                cu = self._now() + timedelta(minutes=STAGE_COOLDOWN_MINUTES["repeated_failed_recovery"])
                await self._persist(uid, PolicyAction.SILENCE_RESPECT, "max_attempts_reached", cu)
                return self._dec(uid, PolicyAction.SILENCE_RESPECT,
                    f"Max recovery attempts ({maxatt}) reached for stage '{stage}'",
                    cu, 0, ToneMode.SILENCE_RESPECT, RecoveryChannel.NONE,
                    fatigue, stage, NextAction.MARK_SILENCE_RESPECT, silence_respect=True)

            # Gate 8
            if fatigue >= FATIGUE_HIGH_THRESHOLD:
                if memory_state.recovery_ignored_count >= 2:
                    cu = self._now() + timedelta(minutes=STAGE_COOLDOWN_MINUTES["repeated_failed_recovery"])
                    await self._persist(uid, PolicyAction.SILENCE_RESPECT, "recovery_fatigue_high", cu)
                    return self._dec(uid, PolicyAction.SILENCE_RESPECT,
                        "High recovery fatigue — stopping automated outreach",
                        cu, 0, ToneMode.SILENCE_RESPECT, RecoveryChannel.NONE,
                        fatigue, stage, NextAction.MARK_SILENCE_RESPECT, silence_respect=True)
                else:
                    cu = self._now() + timedelta(minutes=cdmin * 2)
                    return self._dec(uid, PolicyAction.DELAY,
                        "Recovery fatigue high — doubling cooldown",
                        cu, att_rem, ToneMode.SOFT_CHECKIN,
                        RecoveryChannel.NONE, fatigue, stage, NextAction.WAIT)

            # Gate 9
            if user_context.last_ai_message_at:
                mins = (self._now() - user_context.last_ai_message_at).total_seconds() / 60
                if mins < 60:
                    cu = user_context.last_ai_message_at + timedelta(hours=1)
                    return self._dec(uid, PolicyAction.DELAY,
                        f"AI message sent {int(mins)}min ago — waiting 60min",
                        cu, att_rem, self._tone(risk_profile, stage),
                        RecoveryChannel.NONE, fatigue, stage, NextAction.WAIT)

            # Gate 10
            if risk_profile.risk_level == "critical" and                self._needs_human_critical(risk_profile, memory_state):
                return self._dec(uid, PolicyAction.ESCALATE_HUMAN,
                    f"Critical risk '{risk_profile.risk_type}' requires human review",
                    None, att_rem, ToneMode.HUMAN_HANDOFF,
                    RecoveryChannel.HUMAN_AGENT, fatigue, stage,
                    NextAction.ESCALATE_TO_HUMAN, he=True)

            # Gate 11
            if self._payment_pressure_risk(user_context, risk_profile):
                cu = self._now() + timedelta(minutes=cdmin)
                return self._dec(uid, PolicyAction.SUPPRESS,
                    "Payment pressure guard — contact suppressed",
                    cu, att_rem, ToneMode.SOFT_CHECKIN,
                    RecoveryChannel.NONE, fatigue, stage,
                    NextAction.SUPPRESS, sr="payment_pressure_guard")

            # Gate 12
            if risk_profile.risk_type == "trust_collapse_risk" and                risk_profile.risk_level in ("high", "critical"):
                cu = self._now() + timedelta(minutes=cdmin)
                return self._dec(uid, PolicyAction.ALLOW,
                    "Trust repair mode — minimal non-intrusive contact",
                    cu, att_rem - 1, ToneMode.TRUST_REPAIR,
                    RecoveryChannel.AI_MESSAGE, fatigue, stage,
                    NextAction.SEND_SOFT_RECOVERY)

            # Gate 13 — ALLOW
            tone = self._tone(risk_profile, stage)
            cu   = self._now() + timedelta(minutes=cdmin)
            await self._persist(uid, PolicyAction.ALLOW, stage, cu)
            return self._dec(uid, PolicyAction.ALLOW,
                f"All governance checks passed stage='{stage}' tone='{tone}'",
                cu, att_rem - 1, tone, RecoveryChannel.AI_MESSAGE,
                fatigue, stage, NextAction.SEND_SOFT_RECOVERY)

        except Exception as e:
            log.error("[POLICY] evaluate_recovery_policy error user=%s: %s", uid, e)
            return self._dec(uid, PolicyAction.SUPPRESS,
                f"Policy engine error — proactive suppressed (fail-safe): {e}",
                self._now() + timedelta(hours=2), 0,
                ToneMode.SILENCE_RESPECT, RecoveryChannel.NONE,
                0.0, "default", NextAction.SUPPRESS, sr="engine_error")

    # -----------------------------------------------------------------------
    # Fatigue score
    # -----------------------------------------------------------------------
    def _compute_fatigue_score(self, ctx: UserContext, mem: MemoryState) -> float:
        score  = min(ctx.recovery_attempt_count * 0.12, 0.36)
        score += min(mem.recovery_ignored_count  * 0.18, 0.54)
        score += min(mem.irritation_signals      * 0.08, 0.24)
        score += min(mem.emotional_spike_count   * 0.05, 0.15)
        stop_hits = sum(
            1 for msg in ctx.recent_messages
            if any(kw in msg.lower() for kw in STOP_KEYWORDS)
        )
        score += min(stop_hits * 0.20, 0.40)
        return min(round(score, 3), 1.0)

    # -----------------------------------------------------------------------
    # Stage resolver
    # -----------------------------------------------------------------------
    def _resolve_stage(self, ctx: UserContext, risk: RiskProfile) -> str:
        stage_map = {
            "payment_hesitation_risk":   "payment_hesitation",
            "post_payment_silence_risk": "post_payment_silence",
            "onboarding_drop_risk":      "onboarding_incomplete",
            "analysis_delay_risk":       "analysis_missing",
            "emotional_overload_risk":   "emotional_overload",
            "trust_collapse_risk":       "distrust_loop",
            "recovery_failure_risk":     "repeated_failed_recovery",
            "abandonment_risk":          "pre_payment_interest",
            "escalation_needed_risk":    "distrust_loop",
            "route_oscillation_risk":    "distrust_loop",
        }
        if risk.risk_type in stage_map:
            return stage_map[risk.risk_type]
        if ctx.payment_status == "pending":
            return "payment_hesitation"
        if ctx.payment_status == "paid":
            return "post_payment_silence"
        return "default"

    # -----------------------------------------------------------------------
    # Tone governance — never sales, never pressure
    # -----------------------------------------------------------------------
    def _tone(self, risk: RiskProfile, stage: str) -> str:
        if stage in ("payment_hesitation", "pre_payment_interest"):
            return ToneMode.CONTEXT_REMINDER
        if stage == "post_payment_silence":
            return ToneMode.POST_PAYMENT_SUPPORT
        if stage == "emotional_overload":
            return ToneMode.SILENCE_RESPECT
        if stage == "distrust_loop":
            return ToneMode.TRUST_REPAIR
        if risk.risk_level in ("high", "critical"):
            return ToneMode.STATUS_CONFIRMATION
        return ToneMode.SOFT_CHECKIN

    # -----------------------------------------------------------------------
    # Guard helpers
    # -----------------------------------------------------------------------
    def _has_stop_signal(self, messages: List[str]) -> bool:
        return any(
            any(kw in msg.lower() for kw in STOP_KEYWORDS)
            for msg in messages
        )

    def _needs_human_critical(self, risk: RiskProfile, mem: MemoryState) -> bool:
        if risk.risk_type in (
            "trust_collapse_risk", "emotional_overload_risk",
            "escalation_needed_risk"
        ):
            return True
        if mem.recovery_ignored_count >= 2:
            return True
        if mem.irritation_signals >= 2:
            return True
        return False

    def _payment_pressure_risk(self, ctx: UserContext, risk: RiskProfile) -> bool:
        return (
            ctx.payment_status == "pending"
            and risk.risk_type == "payment_hesitation_risk"
            and ctx.recovery_attempt_count >= 1
        )

    # -----------------------------------------------------------------------
    # Human escalation check (standalone)
    # -----------------------------------------------------------------------
    async def should_escalate_to_human(
        self,
        user_context: UserContext,
        risk_profile: RiskProfile,
        memory_state: MemoryState,
    ) -> Tuple[bool, str]:
        reasons = []
        if risk_profile.risk_type == "escalation_needed_risk":
            reasons.append("escalation_needed_risk flagged")
        if memory_state.recovery_ignored_count >= 3:
            reasons.append("3+ ignored recovery attempts")
        if risk_profile.risk_type == "trust_collapse_risk" and            risk_profile.risk_level == "critical":
            reasons.append("critical trust collapse")
        if risk_profile.risk_type == "emotional_overload_risk" and            risk_profile.risk_level in ("high", "critical"):
            reasons.append("high/critical emotional overload")
        if risk_profile.risk_type == "post_payment_silence_risk" and            risk_profile.risk_level == "critical":
            reasons.append("post-payment critical silence")
        if self._has_stop_signal(user_context.recent_messages):
            reasons.append("explicit stop signal from user")
        if user_context.recovery_attempt_count >= 4 and            memory_state.recovery_ignored_count >= 2:
            reasons.append("repeated failed AI recovery")
        return (True, "; ".join(reasons)) if reasons else (False, "")

    # -----------------------------------------------------------------------
    # Silence respect scanner
    # -----------------------------------------------------------------------
    async def scan_for_silence_respect(self) -> List[int]:
        if not self._pool:
            return []
        marked = []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT user_id FROM pm_client_profiles
                       WHERE is_active = TRUE
                         AND silence_respect = FALSE
                         AND recovery_attempt_count >= 3
                         AND (
                           last_recovery_at IS NULL
                           OR last_recovery_at < NOW() - INTERVAL '72 hours'
                         )"""
                )
                for row in rows:
                    uid = row["user_id"]
                    await conn.execute(
                        "UPDATE pm_client_profiles SET silence_respect=TRUE"
                        " WHERE user_id=$1", uid
                    )
                    log.info("[POLICY] Marked silence_respect user=%d", uid)
                    marked.append(uid)
        except Exception as e:
            log.error("[POLICY] scan_for_silence_respect error: %s", e)
        return marked

    # -----------------------------------------------------------------------
    # Dashboard exposure
    # -----------------------------------------------------------------------
    async def get_dashboard_data(self) -> Dict[str, Any]:
        if not self._pool:
            return {"error": "no_db_pool"}
        try:
            async with self._pool.acquire() as conn:
                silence_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_client_profiles"
                    " WHERE silence_respect=TRUE AND is_active=TRUE"
                )
                cooldown_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_recovery_policy_log"
                    " WHERE cooldown_until > NOW() AND action != 'ALLOW'"
                )
                escalation_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_recovery_policy_log"
                    " WHERE human_escalation_required=TRUE"
                    " AND created_at > NOW() - INTERVAL '24 hours'"
                )
                high_fatigue = await conn.fetch(
                    "SELECT user_id, fatigue_score, suppression_reason,"
                    " created_at, recovery_channel"
                    " FROM pm_recovery_policy_log"
                    " WHERE fatigue_score >= 0.7"
                    " AND created_at > NOW() - INTERVAL '24 hours'"
                    " ORDER BY fatigue_score DESC LIMIT 20"
                )
                suppression_rows = await conn.fetch(
                    "SELECT suppression_reason, COUNT(*) AS count"
                    " FROM pm_recovery_policy_log"
                    " WHERE action='SUPPRESS'"
                    " AND created_at > NOW() - INTERVAL '24 hours'"
                    " GROUP BY suppression_reason ORDER BY count DESC"
                )
            return {
                "silence_respect_count":     int(silence_count or 0),
                "active_cooldown_count":     int(cooldown_count or 0),
                "human_escalation_24h":      int(escalation_count or 0),
                "high_fatigue_users":        [dict(r) for r in high_fatigue],
                "suppression_breakdown_24h": [dict(r) for r in suppression_rows],
            }
        except Exception as e:
            log.error("[POLICY] get_dashboard_data error: %s", e)
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # DB persistence
    # -----------------------------------------------------------------------
    async def _persist(
        self, user_id: int, action: str,
        suppression_reason: str, cooldown_until: Optional[datetime]
    ) -> None:
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO pm_recovery_policy_log
                       (user_id, action, suppression_reason, cooldown_until, created_at)
                       VALUES ($1, $2, $3, $4, NOW())
                       ON CONFLICT DO NOTHING""",
                    user_id, action, suppression_reason, cooldown_until,
                )
        except Exception as e:
            log.debug("[POLICY] _persist error: %s", e)

    async def persist_full_decision(self, decision: RecoveryPolicyDecision) -> None:
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO pm_recovery_policy_log
                       (user_id, action, reason, cooldown_until,
                        max_attempts_remaining, tone_mode, recovery_channel,
                        human_escalation_required, next_action,
                        fatigue_score, suppression_reason, silence_respect,
                        created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW())
                       ON CONFLICT DO NOTHING""",
                    decision.user_id, decision.action, decision.reason,
                    decision.cooldown_until, decision.max_attempts_remaining,
                    decision.tone_mode, decision.recovery_channel,
                    decision.human_escalation_required, decision.next_action,
                    decision.fatigue_score, decision.suppression_reason,
                    decision.silence_respect,
                )
        except Exception as e:
            log.debug("[POLICY] persist_full_decision error: %s", e)

    # -----------------------------------------------------------------------
    # Private factory
    # -----------------------------------------------------------------------
    def _dec(
        self, user_id: int, action: str, reason: str,
        cooldown_until: Optional[datetime], attempts_remaining: int,
        tone_mode: str, channel: str, fatigue: float, stage: str,
        next_action: str, he: bool = False, silence_respect: bool = False,
        sr: str = "",
    ) -> RecoveryPolicyDecision:
        flags = {
            "recovery_status":           action,
            "cooldown_until":            cooldown_until.isoformat()
                                         if cooldown_until else None,
            "suppression_reason":        sr,
            "fatigue_score":             fatigue,
            "silence_respect":           silence_respect,
            "human_escalation_required": he,
            "recommended_next_action":   next_action,
            "stage":                     stage,
        }
        log.info("[POLICY] user=%d action=%s stage=%s fatigue=%.2f reason=%s",
                 user_id, action, stage, fatigue, reason[:80])
        return RecoveryPolicyDecision(
            user_id=user_id, action=action, reason=reason,
            cooldown_until=cooldown_until,
            max_attempts_remaining=attempts_remaining,
            tone_mode=tone_mode, recovery_channel=channel,
            dashboard_flags=flags,
            human_escalation_required=he,
            next_action=next_action,
            fatigue_score=fatigue,
            suppression_reason=sr,
            silence_respect=silence_respect,
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_policy_engine: Optional[RecoveryPolicyEngine] = None

def get_recovery_policy_engine() -> Optional[RecoveryPolicyEngine]:
    return _policy_engine

def init_recovery_policy_engine(db_pool=None) -> RecoveryPolicyEngine:
    global _policy_engine
    _policy_engine = RecoveryPolicyEngine(db_pool=db_pool)
    log.info("[POLICY] RecoveryPolicyEngine singleton created")
    return _policy_engine

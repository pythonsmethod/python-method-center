"""
risk_predictor.py — Phase 3.2: Predictive Risk Intelligence
Analyzes user behavioral trajectory and predicts risk before drop/abandon/trust collapse.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)

# ─── Risk Type Enum ──────────────────────────────────────────────────────────

class RiskType(str, Enum):
    ABANDONMENT_RISK         = "abandonment_risk"
    PAYMENT_HESITATION_RISK  = "payment_hesitation_risk"
    TRUST_COLLAPSE_RISK      = "trust_collapse_risk"
    EMOTIONAL_OVERLOAD_RISK  = "emotional_overload_risk"
    ONBOARDING_DROP_RISK     = "onboarding_drop_risk"
    ANALYSIS_DELAY_RISK      = "analysis_delay_risk"
    ESCALATION_NEEDED_RISK   = "escalation_needed_risk"
    ROUTE_OSCILLATION_RISK   = "route_oscillation_risk"
    POST_PAYMENT_SILENCE_RISK = "post_payment_silence_risk"
    RECOVERY_FAILURE_RISK    = "recovery_failure_risk"

class RiskLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

# ─── Result Dataclass ─────────────────────────────────────────────────────────

@dataclass
class RiskResult:
    user_id: int
    risk_type: str
    risk_level: str
    current_risk_score: float       # 0.0 – 1.0
    risk_reason: str
    confidence: float               # 0.0 – 1.0
    recommended_action: str
    next_check_at: datetime
    details: Dict[str, Any] = field(default_factory=dict)

# ─── Safety Constants ─────────────────────────────────────────────────────────

SAFETY_NEVER_TRIGGER = {
    "medical_diagnosis",
    "payment_pressure",
    "emergency_override",
    "spam_recovery",
    "route_lock_bypass",
}

# Cooldown in minutes between recovery actions per user
RECOVERY_COOLDOWN_MINUTES = 120

# Thresholds
SILENCE_ABANDON_HOURS   = 48    # no message → abandonment risk
SILENCE_POST_PAY_HOURS  = 24    # silence after payment → post_payment_silence
ONBOARDING_DELAY_HOURS  = 6     # stuck in onboarding
ANALYSIS_DELAY_HOURS    = 12    # hasn't uploaded analysis
PRICE_ASK_THRESHOLD     = 3     # repeated price questions
FEAR_MSG_THRESHOLD      = 2     # fear/trust signals
BURST_MSG_THRESHOLD     = 6     # many messages in short window (5 min)
ROUTE_SWITCH_THRESHOLD  = 3     # oscillation count
RECOVERY_FAIL_ATTEMPTS  = 2     # failed recovery triggers

# Score weights
W = {
    "silence":          0.30,
    "price_repeat":     0.25,
    "fear_signal":      0.25,
    "burst_msg":        0.15,
    "route_oscillation":0.20,
    "recovery_fail":    0.30,
    "onboarding_delay": 0.25,
    "analysis_delay":   0.20,
    "post_pay_silence": 0.30,
    "escalation_req":   0.25,
}

# Fear/trust keywords (Russian + English)
FEAR_KEYWORDS = [
    "боюсь", "страшно", "не доверяю", "сомневаюсь", "не уверен", "не уверена",
    "обман", "мошенник", "развод", "подозрительно", "не верю",
    "afraid", "scared", "don't trust", "doubt", "suspicious", "fraud", "scam",
]

PAYMENT_HESITATION_KEYWORDS = [
    "цена", "стоимость", "сколько стоит", "дорого", "дороговато", "за что плачу",
    "деньги", "оплата", "почему такая цена", "скидка",
    "price", "cost", "how much", "expensive", "payment", "why so much", "discount",
]

ESCALATION_KEYWORDS = [
    "хочу с человеком", "позвоните мне", "живой человек", "менеджер", "позвоните",
    "не помогаете", "хочу вернуть деньги", "верните деньги",
    "human", "real person", "speak to someone", "refund", "manager",
]

# ─── Main Predictor ───────────────────────────────────────────────────────────

class RiskPredictor:
    """
    Analyzes user behavioral trajectory and computes predictive risk scores.
    Integrates with: memory_engine, event_bus, recovery_engine, dashboard_data.
    Must never block user response — all methods are async.
    """

    def __init__(self, db_pool=None):
        self._pool = db_pool
        self._initialized = False
        log.info("[RISK] RiskPredictor created")

    async def init(self, db_pool=None):
        if db_pool:
            self._pool = db_pool
        await self._run_migration()
        self._initialized = True
        log.info("[RISK] RiskPredictor initialized")

    # ─── DB Migration ──────────────────────────────────────────────────────────

    async def _run_migration(self):
        """Idempotent migration — adds missing columns to pm_risk_predictions."""
        if not self._pool:
            log.warning("[RISK] No DB pool — skipping migration")
            return
        migrations = [
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS risk_type TEXT",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS risk_level TEXT DEFAULT 'low'",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS current_risk_score FLOAT DEFAULT 0.0",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS risk_reason TEXT",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 0.0",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS recommended_action TEXT",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS next_check_at TIMESTAMPTZ",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS details JSONB DEFAULT '{}'",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        ]
        async with self._pool.acquire() as conn:
            for sql in migrations:
                try:
                    await conn.execute(sql)
                except Exception as e:
                    log.debug(f"[RISK] Migration skipped ({e}): {sql[:60]}")
        log.info("[RISK] DB migration complete")

    # ─── Public Entry Points ───────────────────────────────────────────────────

    async def predict_for_user(self, user_id: int) -> Optional[RiskResult]:
        """
        Full risk prediction for one user based on their trajectory.
        Returns the highest-severity risk found, or None if low.
        Must be called as asyncio.create_task() to avoid blocking.
        """
        if not self._pool:
            return None
        try:
            signals = await self._gather_signals(user_id)
            result  = self._score_signals(user_id, signals)
            if result:
                await self._persist_risk(result)
                await self._publish_risk_event(result)
                if result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                    await self._trigger_recovery(result)
            return result
        except Exception as e:
            log.error(f"[RISK] predict_for_user({user_id}) error: {e}", exc_info=True)
            return None

    async def run_silent_user_scan(self):
        """
        Scheduled scan for users who have gone silent.
        Run periodically (e.g. every 30 min) from runtime_supervisor or main.py.
        """
        if not self._pool:
            return
        try:
            user_ids = await self._get_users_with_silence()
            log.info(f"[RISK] Silent scan: {len(user_ids)} candidates")
            for uid in user_ids:
                asyncio.create_task(self.predict_for_user(uid))
        except Exception as e:
            log.error(f"[RISK] silent scan error: {e}", exc_info=True)

    # ─── Signal Gathering ─────────────────────────────────────────────────────

    async def _gather_signals(self, user_id: int) -> Dict[str, Any]:
        """Query DB for behavioral signals from all relevant tables."""
        signals: Dict[str, Any] = {
            "user_id": user_id,
            "now": datetime.now(timezone.utc),
        }
        async with self._pool.acquire() as conn:
            # 1. Client profile
            profile = await conn.fetchrow(
                "SELECT * FROM pm_client_profiles WHERE user_id=$1", user_id
            )
            signals["profile"] = dict(profile) if profile else {}

            # 2. Recent timeline (last 50 events)
            timeline = await conn.fetch(
                """SELECT event_type, summary, route, risk_score, user_message,
                          created_at, user_state, intent
                   FROM pm_memory_timeline
                   WHERE user_id=$1
                   ORDER BY created_at DESC LIMIT 50""",
                user_id
            )
            signals["timeline"] = [dict(r) for r in timeline]

            # 3. Orchestration events (last 30)
            orch_events = await conn.fetch(
                """SELECT event_type, route, payload, created_at
                   FROM pm_orchestration_events
                   WHERE user_id=$1
                   ORDER BY created_at DESC LIMIT 30""",
                user_id
            )
            signals["orch_events"] = [dict(r) for r in orch_events]

            # 4. Recovery plans
            recovery = await conn.fetch(
                """SELECT status, plan_type, attempts, created_at, completed_at
                   FROM pm_recovery_plans
                   WHERE user_id=$1
                   ORDER BY created_at DESC LIMIT 5""",
                user_id
            )
            signals["recovery_plans"] = [dict(r) for r in recovery]

            # 5. Last message time
            last_msg = await conn.fetchval(
                """SELECT MAX(created_at) FROM pm_memory_timeline
                   WHERE user_id=$1 AND event_type='interaction'""",
                user_id
            )
            signals["last_message_at"] = last_msg

            # 6. Existing open risk predictions
            existing_risk = await conn.fetchrow(
                """SELECT risk_type, risk_level, current_risk_score, created_at
                   FROM pm_risk_predictions
                   WHERE user_id=$1 AND resolved_at IS NULL
                   ORDER BY created_at DESC LIMIT 1""",
                user_id
            )
            signals["existing_risk"] = dict(existing_risk) if existing_risk else {}

        return signals

    # ─── Scoring Engine ───────────────────────────────────────────────────────

    def _score_signals(self, user_id: int, signals: Dict[str, Any]) -> Optional[RiskResult]:
        """
        Evaluate all risk dimensions. Returns the highest-priority risk result.
        """
        now        = signals["now"]
        profile    = signals.get("profile", {})
        timeline   = signals.get("timeline", [])
        orch       = signals.get("orch_events", [])
        recovery   = signals.get("recovery_plans", [])
        last_msg   = signals.get("last_message_at")
        stage      = profile.get("current_stage", "unknown")

        scores: List[RiskResult] = []

        # ── 1. Abandonment Risk ───────────────────────────────────────────────
        if last_msg:
            silence_h = (now - last_msg.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if silence_h >= SILENCE_ABANDON_HOURS:
                score = min(0.4 + (silence_h - SILENCE_ABANDON_HOURS) * 0.01, 1.0)
                scores.append(RiskResult(
                    user_id=user_id,
                    risk_type=RiskType.ABANDONMENT_RISK,
                    risk_level=self._score_to_level(score),
                    current_risk_score=round(score, 3),
                    risk_reason=f"No message for {silence_h:.0f}h (threshold={SILENCE_ABANDON_HOURS}h)",
                    confidence=0.80,
                    recommended_action="send_re_engagement_nudge",
                    next_check_at=now + timedelta(hours=12),
                    details={"silence_hours": round(silence_h, 1), "stage": stage},
                ))

        # ── 2. Payment Hesitation ─────────────────────────────────────────────
        price_count = sum(
            1 for e in timeline
            if e.get("user_message") and
               any(kw in (e["user_message"] or "").lower() for kw in PAYMENT_HESITATION_KEYWORDS)
        )
        if price_count >= PRICE_ASK_THRESHOLD:
            score = min(0.3 + price_count * 0.12, 1.0)
            scores.append(RiskResult(
                user_id=user_id,
                risk_type=RiskType.PAYMENT_HESITATION_RISK,
                risk_level=self._score_to_level(score),
                current_risk_score=round(score, 3),
                risk_reason=f"User asked about price/payment {price_count}x",
                confidence=0.75,
                recommended_action="present_value_reinforcement",
                next_check_at=now + timedelta(hours=6),
                details={"price_question_count": price_count},
            ))

        # ── 3. Trust Collapse ─────────────────────────────────────────────────
        fear_count = sum(
            1 for e in timeline
            if e.get("user_message") and
               any(kw in (e["user_message"] or "").lower() for kw in FEAR_KEYWORDS)
        )
        if fear_count >= FEAR_MSG_THRESHOLD:
            score = min(0.35 + fear_count * 0.15, 1.0)
            scores.append(RiskResult(
                user_id=user_id,
                risk_type=RiskType.TRUST_COLLAPSE_RISK,
                risk_level=self._score_to_level(score),
                current_risk_score=round(score, 3),
                risk_reason=f"Fear/distrust signals detected {fear_count}x",
                confidence=0.80,
                recommended_action="activate_trust_route",
                next_check_at=now + timedelta(hours=4),
                details={"fear_count": fear_count},
            ))

        # ── 4. Emotional Overload ─────────────────────────────────────────────
        # Many messages in a short burst window
        recent_5min = [
            e for e in timeline
            if e.get("created_at") and
               (now - e["created_at"].replace(tzinfo=timezone.utc)).total_seconds() < 300
        ]
        if len(recent_5min) >= BURST_MSG_THRESHOLD:
            score = min(0.30 + len(recent_5min) * 0.06, 1.0)
            scores.append(RiskResult(
                user_id=user_id,
                risk_type=RiskType.EMOTIONAL_OVERLOAD_RISK,
                risk_level=self._score_to_level(score),
                current_risk_score=round(score, 3),
                risk_reason=f"{len(recent_5min)} messages in last 5 minutes",
                confidence=0.70,
                recommended_action="slow_down_response_pace",
                next_check_at=now + timedelta(minutes=30),
                details={"burst_count": len(recent_5min)},
            ))

        # ── 5. Onboarding Drop ────────────────────────────────────────────────
        if stage in ("onboarding", "intro", "greeting"):
            onboard_start = profile.get("created_at") or profile.get("first_seen_at")
            if onboard_start:
                delay_h = (now - onboard_start.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if delay_h >= ONBOARDING_DELAY_HOURS:
                    score = min(0.35 + delay_h * 0.015, 1.0)
                    scores.append(RiskResult(
                        user_id=user_id,
                        risk_type=RiskType.ONBOARDING_DROP_RISK,
                        risk_level=self._score_to_level(score),
                        current_risk_score=round(score, 3),
                        risk_reason=f"Stuck in onboarding for {delay_h:.0f}h",
                        confidence=0.75,
                        recommended_action="send_onboarding_nudge",
                        next_check_at=now + timedelta(hours=6),
                        details={"onboarding_delay_hours": round(delay_h, 1)},
                    ))

        # ── 6. Analysis Delay ─────────────────────────────────────────────────
        if stage in ("analysis_pending", "awaiting_upload", "analysis"):
            analysis_events = [e for e in timeline if "analysis" in (e.get("event_type") or "")]
            if analysis_events:
                oldest = min(
                    e["created_at"].replace(tzinfo=timezone.utc)
                    for e in analysis_events if e.get("created_at")
                )
                delay_h = (now - oldest).total_seconds() / 3600
                if delay_h >= ANALYSIS_DELAY_HOURS:
                    score = min(0.30 + delay_h * 0.01, 1.0)
                    scores.append(RiskResult(
                        user_id=user_id,
                        risk_type=RiskType.ANALYSIS_DELAY_RISK,
                        risk_level=self._score_to_level(score),
                        current_risk_score=round(score, 3),
                        risk_reason=f"Analysis upload delayed {delay_h:.0f}h",
                        confidence=0.70,
                        recommended_action="send_analysis_reminder",
                        next_check_at=now + timedelta(hours=6),
                        details={"analysis_delay_hours": round(delay_h, 1)},
                    ))

        # ── 7. Escalation Needed ──────────────────────────────────────────────
        escalation_count = sum(
            1 for e in timeline
            if e.get("user_message") and
               any(kw in (e["user_message"] or "").lower() for kw in ESCALATION_KEYWORDS)
        )
        if escalation_count >= 2:
            score = min(0.50 + escalation_count * 0.12, 1.0)
            scores.append(RiskResult(
                user_id=user_id,
                risk_type=RiskType.ESCALATION_NEEDED_RISK,
                risk_level=self._score_to_level(score),
                current_risk_score=round(score, 3),
                risk_reason=f"Human escalation requested {escalation_count}x",
                confidence=0.85,
                recommended_action="escalate_to_human_immediately",
                next_check_at=now + timedelta(hours=1),
                details={"escalation_request_count": escalation_count},
            ))

        # ── 8. Route Oscillation ──────────────────────────────────────────────
        routes = [e.get("route") for e in timeline if e.get("route")]
        switches = sum(1 for i in range(1, len(routes)) if routes[i] != routes[i-1])
        if switches >= ROUTE_SWITCH_THRESHOLD:
            score = min(0.25 + switches * 0.08, 1.0)
            scores.append(RiskResult(
                user_id=user_id,
                risk_type=RiskType.ROUTE_OSCILLATION_RISK,
                risk_level=self._score_to_level(score),
                current_risk_score=round(score, 3),
                risk_reason=f"Route changed {switches}x in recent history",
                confidence=0.65,
                recommended_action="stabilize_route_with_lock",
                next_check_at=now + timedelta(hours=2),
                details={"route_switches": switches, "routes_seen": list(set(routes))},
            ))

        # ── 9. Post-Payment Silence ───────────────────────────────────────────
        payment_events = [
            e for e in orch
            if (e.get("event_type") or "") in ("payment_received", "payment_confirmed")
        ]
        if payment_events:
            last_payment_at = max(
                e["created_at"].replace(tzinfo=timezone.utc)
                for e in payment_events if e.get("created_at")
            )
            # Check if there's been no message since payment
            msgs_after_pay = [
                e for e in timeline
                if e.get("created_at") and
                   e["created_at"].replace(tzinfo=timezone.utc) > last_payment_at and
                   e.get("event_type") == "interaction"
            ]
            if not msgs_after_pay:
                silence_h = (now - last_payment_at).total_seconds() / 3600
                if silence_h >= SILENCE_POST_PAY_HOURS:
                    score = min(0.50 + silence_h * 0.015, 1.0)
                    scores.append(RiskResult(
                        user_id=user_id,
                        risk_type=RiskType.POST_PAYMENT_SILENCE_RISK,
                        risk_level=self._score_to_level(score),
                        current_risk_score=round(score, 3),
                        risk_reason=f"No message {silence_h:.0f}h after payment",
                        confidence=0.85,
                        recommended_action="send_post_payment_welcome",
                        next_check_at=now + timedelta(hours=6),
                        details={"silence_after_payment_hours": round(silence_h, 1)},
                    ))

        # ── 10. Recovery Failure ──────────────────────────────────────────────
        failed_recovery = [
            p for p in recovery
            if p.get("status") in ("failed", "expired") or
               (p.get("attempts") or 0) >= RECOVERY_FAIL_ATTEMPTS
        ]
        if len(failed_recovery) >= RECOVERY_FAIL_ATTEMPTS:
            score = min(0.55 + len(failed_recovery) * 0.15, 1.0)
            scores.append(RiskResult(
                user_id=user_id,
                risk_type=RiskType.RECOVERY_FAILURE_RISK,
                risk_level=self._score_to_level(score),
                current_risk_score=round(score, 3),
                risk_reason=f"{len(failed_recovery)} recovery plan(s) failed",
                confidence=0.80,
                recommended_action="escalate_to_human_immediately",
                next_check_at=now + timedelta(hours=2),
                details={"failed_recovery_count": len(failed_recovery)},
            ))

        if not scores:
            return None

        # Return the highest severity
        level_order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        scores.sort(key=lambda r: (level_order.get(r.risk_level, 0), r.current_risk_score), reverse=True)
        return scores[0]

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _score_to_level(self, score: float) -> str:
        if score >= 0.80:
            return RiskLevel.CRITICAL
        if score >= 0.55:
            return RiskLevel.HIGH
        if score >= 0.30:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # ─── DB Persistence ───────────────────────────────────────────────────────

    async def _persist_risk(self, result: RiskResult):
        if not self._pool:
            return
        import json
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO pm_risk_predictions
                         (user_id, risk_type, risk_level, current_risk_score,
                          risk_reason, confidence, recommended_action,
                          next_check_at, details, updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                       ON CONFLICT (user_id) DO UPDATE SET
                         risk_type=EXCLUDED.risk_type,
                         risk_level=EXCLUDED.risk_level,
                         current_risk_score=EXCLUDED.current_risk_score,
                         risk_reason=EXCLUDED.risk_reason,
                         confidence=EXCLUDED.confidence,
                         recommended_action=EXCLUDED.recommended_action,
                         next_check_at=EXCLUDED.next_check_at,
                         details=EXCLUDED.details,
                         resolved_at=NULL,
                         updated_at=NOW()""",
                    result.user_id,
                    result.risk_type,
                    result.risk_level,
                    result.current_risk_score,
                    result.risk_reason,
                    result.confidence,
                    result.recommended_action,
                    result.next_check_at,
                    json.dumps(result.details),
                )
            log.info(f"[RISK] Persisted {result.risk_type}={result.risk_level} for user {result.user_id}")
        except Exception as e:
            log.error(f"[RISK] persist_risk error: {e}")

    async def resolve_risk(self, user_id: int, risk_type: Optional[str] = None):
        """Mark risk as resolved when user re-engages or pays."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                if risk_type:
                    await conn.execute(
                        """UPDATE pm_risk_predictions
                           SET resolved_at=NOW(), updated_at=NOW()
                           WHERE user_id=$1 AND risk_type=$2 AND resolved_at IS NULL""",
                        user_id, risk_type
                    )
                else:
                    await conn.execute(
                        """UPDATE pm_risk_predictions
                           SET resolved_at=NOW(), updated_at=NOW()
                           WHERE user_id=$1 AND resolved_at IS NULL""",
                        user_id
                    )
            log.info(f"[RISK] Resolved risk for user {user_id} type={risk_type}")
        except Exception as e:
            log.error(f"[RISK] resolve_risk error: {e}")

    # ─── Event Bus ────────────────────────────────────────────────────────────

    async def _publish_risk_event(self, result: RiskResult):
        try:
            from event_bus import get_event_bus, Topic
            bus = get_event_bus()
            if not bus:
                return

            if result.risk_level == RiskLevel.CRITICAL:
                topic = "risk.critical"
            elif result.risk_level == RiskLevel.HIGH:
                topic = "risk.increased"
            else:
                topic = "risk.detected"

            await bus.publish(topic, {
                "user_id":            result.user_id,
                "risk_type":          result.risk_type,
                "risk_level":         result.risk_level,
                "current_risk_score": result.current_risk_score,
                "risk_reason":        result.risk_reason,
                "recommended_action": result.recommended_action,
                "confidence":         result.confidence,
            })
            log.info(f"[RISK] Published {topic} for user {result.user_id}")
        except Exception as e:
            log.warning(f"[RISK] publish_risk_event error: {e}")

    async def publish_risk_resolved(self, user_id: int, risk_type: Optional[str] = None):
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            if bus:
                await bus.publish("risk.resolved", {
                    "user_id": user_id,
                    "risk_type": risk_type,
                })
        except Exception as e:
            log.warning(f"[RISK] publish_risk_resolved error: {e}")

    # ─── Recovery Integration ─────────────────────────────────────────────────

    async def _trigger_recovery(self, result: RiskResult):
        """
        For HIGH/CRITICAL risks: create or update recovery plan.
        Respects cooldown — does not spam.
        Never triggers payment pressure or medical advice.
        """
        if result.recommended_action in SAFETY_NEVER_TRIGGER:
            log.warning(f"[RISK] Blocked unsafe action: {result.recommended_action}")
            return
        try:
            from recovery_engine import RecoveryEngine
            engine = RecoveryEngine(self._pool)
            # Check cooldown
            if self._pool:
                async with self._pool.acquire() as conn:
                    last_plan = await conn.fetchval(
                        """SELECT MAX(created_at) FROM pm_recovery_plans
                           WHERE user_id=$1""",
                        result.user_id
                    )
                if last_plan:
                    elapsed_min = (result.next_check_at - last_plan.replace(tzinfo=timezone.utc)).total_seconds() / 60
                    if elapsed_min < RECOVERY_COOLDOWN_MINUTES:
                        log.info(f"[RISK] Recovery cooldown active for user {result.user_id}")
                        return
            await engine.create_plan(
                user_id=result.user_id,
                plan_type=result.risk_type,
                trigger_reason=result.risk_reason,
            )
            log.info(f"[RISK] Recovery plan created for user {result.user_id}: {result.risk_type}")
        except Exception as e:
            log.error(f"[RISK] trigger_recovery error: {e}")

    # ─── Silent User Query ────────────────────────────────────────────────────

    async def _get_users_with_silence(self) -> List[int]:
        """Return user_ids who haven't sent a message in the last SILENCE_ABANDON_HOURS."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT DISTINCT user_id
                       FROM pm_memory_timeline
                       WHERE event_type='interaction'
                       GROUP BY user_id
                       HAVING MAX(created_at) < NOW() - INTERVAL '48 hours'
                       LIMIT 100""",
                )
            return [r["user_id"] for r in rows]
        except Exception as e:
            log.error(f"[RISK] get_users_with_silence error: {e}")
            return []

    # ─── Dashboard Query ──────────────────────────────────────────────────────

    async def get_high_risk_clients(self, limit: int = 50) -> List[Dict]:
        """Returns high/critical risk clients for dashboard."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT user_id, risk_type, risk_level, current_risk_score,
                              risk_reason, recommended_action, confidence,
                              next_check_at, updated_at
                       FROM pm_risk_predictions
                       WHERE risk_level IN ('high','critical') AND resolved_at IS NULL
                       ORDER BY current_risk_score DESC
                       LIMIT $1""",
                    limit
                )
            return [dict(r) for r in rows]
        except Exception as e:
            log.error(f"[RISK] get_high_risk_clients error: {e}")
            return []

    async def get_risk_by_type(self) -> List[Dict]:
        """Aggregate risk counts by type."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT risk_type, risk_level, COUNT(*) as count,
                              AVG(current_risk_score) as avg_score
                       FROM pm_risk_predictions
                       WHERE resolved_at IS NULL
                       GROUP BY risk_type, risk_level
                       ORDER BY count DESC"""
                )
            return [dict(r) for r in rows]
        except Exception as e:
            log.error(f"[RISK] get_risk_by_type error: {e}")
            return []

    async def get_unresolved_risks(self) -> List[Dict]:
        """All unresolved risks ordered by severity."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT user_id, risk_type, risk_level, current_risk_score,
                              risk_reason, recommended_action, created_at, updated_at
                       FROM pm_risk_predictions
                       WHERE resolved_at IS NULL
                       ORDER BY
                         CASE risk_level WHEN 'critical' THEN 4
                                         WHEN 'high'     THEN 3
                                         WHEN 'medium'   THEN 2
                                         ELSE 1 END DESC,
                         current_risk_score DESC
                       LIMIT 200"""
                )
            return [dict(r) for r in rows]
        except Exception as e:
            log.error(f"[RISK] get_unresolved_risks error: {e}")
            return []


# ─── Singleton ────────────────────────────────────────────────────────────────

_risk_predictor: Optional[RiskPredictor] = None

def get_risk_predictor() -> Optional[RiskPredictor]:
    return _risk_predictor

async def init_risk_predictor(db_pool) -> RiskPredictor:
    global _risk_predictor
    _risk_predictor = RiskPredictor(db_pool)
    await _risk_predictor.init()
    return _risk_predictor

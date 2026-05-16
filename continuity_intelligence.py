# -*- coding: utf-8 -*-
"""
continuity_intelligence.py
PHASE 4 STEP 8: Continuity Intelligence Layer

Read-only layer that sees a user as a continuous journey, not just the last message.
Computes ContinuitySnapshot from session data and produces:
  - 20 continuity signals
  - ContinuityHealth score (0-100)
  - 11 dashboard flags
  - next_best_step recommendation
  - continuity warnings

CRITICAL: does NOT mutate session, does NOT send messages, does NOT change routes.
"""

import logging
import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

log = logging.getLogger("python-method")

# ---------------------------------------------------------------------------
# DASHBOARD FLAGS
# ---------------------------------------------------------------------------
FLAG_STUCK_USER                 = "STUCK_USER"
FLAG_RETURNED_AFTER_PAUSE       = "RETURNED_AFTER_PAUSE"
FLAG_PAYMENT_WITHOUT_ONBOARDING = "PAYMENT_WITHOUT_ONBOARDING"
FLAG_ONBOARDING_INCOMPLETE      = "ONBOARDING_INCOMPLETE"
FLAG_ANALYSIS_PENDING           = "ANALYSIS_PENDING"
FLAG_KAREN_HANDOFF_PENDING      = "KAREN_HANDOFF_PENDING"
FLAG_ESCALATION_NOT_ACKED       = "ESCALATION_NOT_ACKED"
FLAG_MEMORY_WEAK                = "MEMORY_WEAK"
FLAG_NEXT_STEP_MISSING          = "NEXT_STEP_MISSING"
FLAG_ROUTE_DRIFT                = "ROUTE_DRIFT"
FLAG_HIGH_DROPOUT_RISK          = "HIGH_DROPOUT_RISK"

ALL_FLAGS = [
    FLAG_STUCK_USER, FLAG_RETURNED_AFTER_PAUSE, FLAG_PAYMENT_WITHOUT_ONBOARDING,
    FLAG_ONBOARDING_INCOMPLETE, FLAG_ANALYSIS_PENDING, FLAG_KAREN_HANDOFF_PENDING,
    FLAG_ESCALATION_NOT_ACKED, FLAG_MEMORY_WEAK, FLAG_NEXT_STEP_MISSING,
    FLAG_ROUTE_DRIFT, FLAG_HIGH_DROPOUT_RISK,
]

# Thresholds
STUCK_HOURS = 72
PAUSE_HOURS = 24 * 7
MEMORY_WEAK_THRESHOLD = 30
DROPOUT_RISK_THRESHOLD = 65


@dataclass
class ContinuitySnapshot:
    """
    Read-only structured view of a user's current journey continuity.
    Generated on demand from session data.
    """
    contact_id:              str

    route:                   str = "unknown"
    stage:                   str = "unknown"
    status:                  str = "unknown"

    last_contact_at:         Optional[datetime.datetime] = None
    days_since_last_contact: Optional[float] = None

    last_meaningful_action:  Optional[str] = None
    pending_action:          Optional[str] = None
    unresolved_threads:      List[str] = field(default_factory=list)

    emotional_state:         Optional[str] = None
    last_user_emotional_state: Optional[str] = None
    last_ai_action:          Optional[str] = None

    risk_flags:              List[str] = field(default_factory=list)
    dropout_risk:            float = 0.0
    return_context:          Optional[str] = None
    return_after_pause:      bool = False

    repeated_question_pattern: bool = False
    route_stability:         str = "unknown"
    onboarding_completion:   float = 0.0
    payment_to_onboarding_gap: bool = False
    analysis_collection_status: str = "unknown"
    karen_handoff_status:    str = "unknown"
    escalation_pending:      bool = False
    memory_quality:          float = 0.0

    next_best_step:          Optional[str] = None
    continuity_health_score: int = 0
    health_band:             str = "broken"
    confidence:              float = 0.5

    generated_at:            Optional[datetime.datetime] = None
    warnings:                List[str] = field(default_factory=list)


class ContinuityAnalyzer:
    """
    Takes session + context and produces ContinuitySnapshot.
    Read-only: never mutates session, never sends messages.
    """

    def __init__(self, contact_id: str):
        self.contact_id = contact_id

    def analyze(
        self,
        session: dict,
        history=None,
        shadow_metrics=None,
        payment_status=None,
        onboarding_status=None,
        escalation_status=None,
        memory_fields=None,
    ) -> ContinuitySnapshot:
        s = session or {}
        h = history or []
        mf = memory_fields or {}
        now = datetime.datetime.utcnow()

        snap = ContinuitySnapshot(contact_id=self.contact_id, generated_at=now)

        snap.route = s.get("current_route") or s.get("route") or "unknown"
        snap.stage = s.get("current_stage") or s.get("stage") or s.get("onboarding_stage") or "unknown"
        snap.last_meaningful_action = s.get("last_completed_step") or s.get("last_action") or s.get("last_meaningful_action")
        snap.pending_action = s.get("pending_action") or s.get("unfinished_step") or s.get("awaiting_user_action")

        unresolved = []
        if s.get("open_question"):
            unresolved.append(s["open_question"])
        if s.get("unresolved_topic"):
            unresolved.append(s["unresolved_topic"])
        snap.unresolved_threads = unresolved

        last_contact = s.get("last_contact_at") or s.get("last_message_at") or s.get("updated_at")
        if last_contact:
            try:
                if isinstance(last_contact, str):
                    last_contact = datetime.datetime.fromisoformat(last_contact.replace("Z", ""))
                snap.last_contact_at = last_contact
                delta = now - last_contact
                snap.days_since_last_contact = round(delta.total_seconds() / 86400, 2)
            except Exception:
                pass

        snap.last_user_emotional_state = s.get("last_emotional_state") or s.get("emotional_tone") or s.get("user_emotion")
        snap.emotional_state = snap.last_user_emotional_state
        snap.last_ai_action = s.get("last_ai_action") or s.get("last_bot_action")

        try:
            snap.dropout_risk = float(s.get("dropout_risk") or s.get("churn_risk") or 0.0)
        except Exception:
            snap.dropout_risk = 0.0

        hours_since = (snap.days_since_last_contact or 0) * 24
        snap.return_after_pause = hours_since >= PAUSE_HOURS
        if snap.return_after_pause:
            snap.return_context = "returned_after_pause"
        elif snap.days_since_last_contact is None:
            snap.return_context = "first_contact"
        else:
            snap.return_context = "active"

        snap.repeated_question_pattern = bool(
            s.get("repeated_question") or s.get("question_loop") or
            (int(s.get("faq_repeat_count") or 0) > 2)
        )

        route_changes = int(s.get("route_change_count") or 0)
        snap.route_stability = "stable" if route_changes == 0 else ("drifting" if route_changes <= 2 else "volatile")

        onb_pct = s.get("onboarding_completion_pct") or s.get("onboarding_progress") or 0
        try:
            v = float(onb_pct)
            snap.onboarding_completion = v / 100.0 if v > 1 else v
        except Exception:
            snap.onboarding_completion = 0.0
        if onboarding_status == "complete":
            snap.onboarding_completion = 1.0
        elif onboarding_status == "started":
            snap.onboarding_completion = max(snap.onboarding_completion, 0.1)

        has_paid = (payment_status in ("paid", "confirmed", "active") or bool(s.get("payment_confirmed")) or bool(s.get("stripe_session_id")))
        has_onboarded = (onboarding_status == "complete" or snap.onboarding_completion >= 1.0 or bool(s.get("onboarding_complete")))
        snap.payment_to_onboarding_gap = has_paid and not has_onboarded

        snap.analysis_collection_status = (s.get("analysis_status") or s.get("data_collection_status") or ("pending" if s.get("awaiting_analysis") else "unknown"))
        snap.karen_handoff_status = escalation_status or s.get("karen_handoff_status") or s.get("handoff_status") or "not_started"
        snap.escalation_pending = bool(s.get("escalation_flag")) or bool(s.get("escalation_pending")) or (snap.karen_handoff_status in ("pending", "requested"))

        if mf:
            filled = sum(1 for v in mf.values() if v)
            snap.memory_quality = round(filled / max(len(mf), 1), 2)
        else:
            mem_score = s.get("memory_completeness") or s.get("memory_score") or 0
            try:
                v = float(mem_score)
                snap.memory_quality = v / 100.0 if v > 1 else v
            except Exception:
                snap.memory_quality = 0.0

        snap.next_best_step = self._compute_next_best_step(snap, s)
        snap.continuity_health_score, snap.health_band = self._compute_health_score(snap)
        if snap.dropout_risk == 0.0:
            snap.dropout_risk = self._estimate_dropout_risk(snap)
        snap.risk_flags = self._compute_flags(snap, s)
        snap.warnings = self._compute_warnings(snap)
        snap.status = self._compute_status(snap)
        snap.confidence = self._compute_confidence(snap, s)
        return snap

    def _compute_next_best_step(self, snap, s):
        if s.get("next_recommended_step"):
            return s["next_recommended_step"]
        if snap.escalation_pending:
            return "Resolve pending escalation / Karen handoff"
        if snap.payment_to_onboarding_gap:
            return "Complete onboarding — user has paid but not started program"
        if snap.analysis_collection_status in ("pending", "awaiting"):
            return "Collect remaining diagnostic analysis data"
        if snap.days_since_last_contact and snap.days_since_last_contact * 24 >= STUCK_HOURS:
            if snap.pending_action:
                return f"Re-engage user on pending action: {snap.pending_action}"
            return "Re-engage inactive user"
        if snap.onboarding_completion < 1.0 and snap.onboarding_completion > 0:
            return f"Continue onboarding ({int(snap.onboarding_completion * 100)}% complete)"
        if snap.unresolved_threads:
            return f"Resolve open thread: {snap.unresolved_threads[0]}"
        if snap.pending_action:
            return f"Awaiting user response: {snap.pending_action}"
        if snap.return_after_pause:
            return "Welcome back — restore context and re-anchor user journey"
        return None

    def _compute_health_score(self, snap):
        route_known = 1.0 if snap.route not in ("unknown", "", None) else 0.0
        stability_map = {"stable": 1.0, "drifting": 0.5, "volatile": 0.1, "unknown": 0.3}
        route_clarity = (route_known * 0.6 + stability_map.get(snap.route_stability, 0.3) * 0.4) * 100
        route_score = route_clarity * 0.20
        next_step_score = (100.0 if snap.next_best_step else 0.0) * 0.20
        memory_score = min(100.0, snap.memory_quality * 100) * 0.15
        days = snap.days_since_last_contact or 0
        if days == 0: freshness = 100.0
        elif days <= 1: freshness = 90.0
        elif days <= 3: freshness = 70.0
        elif days <= 7: freshness = 40.0
        elif days <= 14: freshness = 20.0
        else: freshness = 0.0
        freshness_score = freshness * 0.15
        risk_penalty = 0.0
        if snap.escalation_pending: risk_penalty += 50.0
        if snap.unresolved_threads: risk_penalty += min(30.0, len(snap.unresolved_threads) * 15)
        if snap.payment_to_onboarding_gap: risk_penalty += 20.0
        unresolved_score = max(0.0, 100.0 - risk_penalty) * 0.15
        onb_payment_score = min(100.0, snap.onboarding_completion * 100) * 0.10
        esc_integrity = 0.0 if (snap.escalation_pending and snap.karen_handoff_status in ("not_started", "unknown")) else 100.0
        esc_score = esc_integrity * 0.05
        total = int(route_score + next_step_score + memory_score + freshness_score + unresolved_score + onb_payment_score + esc_score)
        total = max(0, min(100, total))
        band = "healthy" if total >= 85 else ("watch" if total >= 65 else ("unstable" if total >= 40 else "broken"))
        return total, band

    def _estimate_dropout_risk(self, snap):
        risk = 0.0
        if snap.days_since_last_contact and snap.days_since_last_contact > 7: risk += 0.3
        if snap.continuity_health_score < DROPOUT_RISK_THRESHOLD: risk += 0.3
        if snap.onboarding_completion < 0.5: risk += 0.2
        if snap.repeated_question_pattern: risk += 0.1
        if snap.route_stability == "volatile": risk += 0.1
        return min(1.0, round(risk, 2))

    def _compute_flags(self, snap, s):
        flags = []
        if snap.pending_action and snap.days_since_last_contact is not None and snap.days_since_last_contact * 24 >= STUCK_HOURS:
            flags.append(FLAG_STUCK_USER)
        if snap.return_after_pause:
            flags.append(FLAG_RETURNED_AFTER_PAUSE)
        if snap.payment_to_onboarding_gap:
            flags.append(FLAG_PAYMENT_WITHOUT_ONBOARDING)
        if 0 < snap.onboarding_completion < 1.0:
            flags.append(FLAG_ONBOARDING_INCOMPLETE)
        if snap.analysis_collection_status in ("pending", "awaiting", "incomplete"):
            flags.append(FLAG_ANALYSIS_PENDING)
        if snap.karen_handoff_status in ("pending", "requested", "awaiting_karen"):
            flags.append(FLAG_KAREN_HANDOFF_PENDING)
        if snap.escalation_pending and snap.karen_handoff_status in ("not_started", "unknown"):
            flags.append(FLAG_ESCALATION_NOT_ACKED)
        if snap.memory_quality < (MEMORY_WEAK_THRESHOLD / 100.0):
            flags.append(FLAG_MEMORY_WEAK)
        if not snap.next_best_step:
            flags.append(FLAG_NEXT_STEP_MISSING)
        if snap.route_stability in ("drifting", "volatile"):
            flags.append(FLAG_ROUTE_DRIFT)
        if snap.dropout_risk >= 0.6:
            flags.append(FLAG_HIGH_DROPOUT_RISK)
        return flags

    def _compute_warnings(self, snap):
        warnings = []
        if FLAG_STUCK_USER in snap.risk_flags:
            warnings.append(f"User has not responded in {snap.days_since_last_contact:.1f} days despite pending action")
        if FLAG_PAYMENT_WITHOUT_ONBOARDING in snap.risk_flags:
            warnings.append("User has completed payment but onboarding is not complete")
        if FLAG_ESCALATION_NOT_ACKED in snap.risk_flags:
            warnings.append("Escalation flagged but Karen handoff has not been initiated")
        if FLAG_MEMORY_WEAK in snap.risk_flags:
            warnings.append(f"Memory completeness is low ({int(snap.memory_quality * 100)}%) — context may be missing")
        if FLAG_HIGH_DROPOUT_RISK in snap.risk_flags:
            warnings.append(f"High dropout risk detected ({snap.dropout_risk:.0%})")
        if snap.health_band == "broken":
            warnings.append(f"Continuity health is BROKEN (score: {snap.continuity_health_score})")
        elif snap.health_band == "unstable":
            warnings.append(f"Continuity health is UNSTABLE (score: {snap.continuity_health_score})")
        return warnings

    def _compute_status(self, snap):
        if snap.escalation_pending: return "escalation_pending"
        if snap.health_band == "broken": return "broken"
        if snap.health_band == "unstable": return "unstable"
        if snap.return_after_pause: return "returned"
        if snap.payment_to_onboarding_gap: return "payment_pending_onboarding"
        if snap.health_band == "healthy": return "healthy"
        return "watch"

    def _compute_confidence(self, snap, s):
        score = 0.0
        if snap.route not in ("unknown", None): score += 0.2
        if snap.stage not in ("unknown", None): score += 0.1
        if snap.last_contact_at is not None: score += 0.2
        if snap.memory_quality > 0.1: score += 0.2
        if len(s) > 5: score += 0.2
        if snap.next_best_step: score += 0.1
        return round(min(1.0, score), 2)


def snapshot_to_dict(snap: ContinuitySnapshot) -> dict:
    return {
        "contact_id":                snap.contact_id,
        "route":                     snap.route,
        "stage":                     snap.stage,
        "status":                    snap.status,
        "last_contact_at":           snap.last_contact_at.isoformat() + "Z" if snap.last_contact_at else None,
        "days_since_last_contact":   snap.days_since_last_contact,
        "last_meaningful_action":    snap.last_meaningful_action,
        "pending_action":            snap.pending_action,
        "unresolved_threads":        snap.unresolved_threads,
        "emotional_state":           snap.emotional_state,
        "last_ai_action":            snap.last_ai_action,
        "risk_flags":                snap.risk_flags,
        "dropout_risk":              snap.dropout_risk,
        "return_context":            snap.return_context,
        "return_after_pause":        snap.return_after_pause,
        "repeated_question_pattern": snap.repeated_question_pattern,
        "route_stability":           snap.route_stability,
        "onboarding_completion":     snap.onboarding_completion,
        "payment_to_onboarding_gap": snap.payment_to_onboarding_gap,
        "analysis_collection_status": snap.analysis_collection_status,
        "karen_handoff_status":      snap.karen_handoff_status,
        "escalation_pending":        snap.escalation_pending,
        "memory_quality":            snap.memory_quality,
        "next_best_step":            snap.next_best_step,
        "continuity_health_score":   snap.continuity_health_score,
        "health_band":               snap.health_band,
        "confidence":                snap.confidence,
        "generated_at":              snap.generated_at.isoformat() + "Z" if snap.generated_at else None,
        "warnings":                  snap.warnings,
    }


def analyze_continuity(
    contact_id: str,
    session: dict,
    history=None,
    shadow_metrics=None,
    payment_status=None,
    onboarding_status=None,
    escalation_status=None,
    memory_fields=None,
) -> ContinuitySnapshot:
    """Convenience wrapper — read-only, never mutates session."""
    analyzer = ContinuityAnalyzer(contact_id=contact_id)
    snap = analyzer.analyze(
        session=session, history=history, shadow_metrics=shadow_metrics,
        payment_status=payment_status, onboarding_status=onboarding_status,
        escalation_status=escalation_status, memory_fields=memory_fields,
    )
    log.info(
        "[CONTINUITY] contact_id=%s score=%d band=%s flags=%s next_step=%s",
        contact_id, snap.continuity_health_score, snap.health_band,
        snap.risk_flags, snap.next_best_step,
    )
    return snap

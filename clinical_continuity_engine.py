# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.7 — Clinical Continuity Intelligence
# Module: clinical_continuity_engine.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Evaluate long-term rehabilitation continuity state for each user.
#          Detects stage gaps, transition risks, unresolved loops, waiting
#          instability, and timeline coherence. Internal analysis only.
#
# ARCHITECTURE GUARANTEES:
#   - This engine NEVER sends messages to users.
#   - This engine NEVER calls Telegram, SendPulse, OpenAI, or any dispatcher.
#   - This engine NEVER diagnoses, prescribes, or makes medical claims.
#   - This engine NEVER creates fear, pressure, or urgency.
#   - Output is internal intelligence only: enriches dispatcher/governance.
#   - Human escalation overrides continuity logic.
#   - Silence respect overrides continuity logic.
#   - Recovery policy overrides continuity logic.
#   - Emotional safety overrides optimization.
#   - Any error returns a neutral safe ContinuityResult (no crash, no send).
#
# Central Orchestrator remains final authority over all outbound decisions.
# =============================================================================

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Continuity States (14 states)
# ---------------------------------------------------------------------------

class ContinuityState:
    STABLE_PROGRESSION          = "stable_progression"
    WAITING_STABLE              = "waiting_stable"
    WAITING_UNCLEAR             = "waiting_unclear"
    TRANSITION_PENDING          = "transition_pending"
    TRANSITION_FRAGILE          = "transition_fragile"
    DATA_COLLECTION_INCOMPLETE  = "data_collection_incomplete"
    ANALYSIS_PENDING            = "analysis_pending"
    EXPERT_REVIEW_PENDING       = "expert_review_pending"
    SUPPORT_CYCLE_ACTIVE        = "support_cycle_active"
    FOLLOW_UP_MISSING           = "follow_up_missing"
    CONTINUITY_GAP              = "continuity_gap"
    UNRESOLVED_LOOP             = "unresolved_loop"
    DORMANT_BUT_NOT_LOST        = "dormant_but_not_lost"
    NEEDS_HUMAN_REVIEW          = "needs_human_review"

# ---------------------------------------------------------------------------
# Recommended Actions (internal only — no outbound sends)
# ---------------------------------------------------------------------------

class ContinuityAction:
    NO_ACTION                         = "no_action"
    PRESERVE_WAITING_STATE            = "preserve_waiting_state"
    CLARIFY_NEXT_STEP                 = "clarify_next_step"
    MARK_TRANSITION_PENDING           = "mark_transition_pending"
    REQUEST_MISSING_DATA_VIA_DISPATCHER = "request_missing_data_via_dispatcher"
    PREPARE_HUMAN_REVIEW              = "prepare_human_review"
    PREPARE_KAREN_REVIEW              = "prepare_karen_review"
    REDUCE_MESSAGE_INTENSITY          = "reduce_message_intensity"
    HOLD_DUE_TO_SILENCE_RESPECT       = "hold_due_to_silence_respect"
    HOLD_DUE_TO_ESCALATION            = "hold_due_to_escalation"
    CLOSE_RESOLVED_LOOP               = "close_resolved_loop"

# ---------------------------------------------------------------------------
# Continuity Score Bands
# ---------------------------------------------------------------------------
# 0.00–0.20 = severe continuity breakdown
# 0.21–0.40 = continuity gap likely
# 0.41–0.60 = fragile continuity
# 0.61–0.80 = stable but needs monitoring
# 0.81–1.00 = coherent stable progression

# ---------------------------------------------------------------------------
# ContinuityResult
# ---------------------------------------------------------------------------

@dataclass
class ContinuityResult:
    safe_to_continue: bool              = True
    continuity_state: str               = ContinuityState.STABLE_PROGRESSION
    continuity_score: float             = 1.0
    continuity_gap_detected: bool       = False
    stage_transition_risk: bool         = False
    unresolved_loop: bool               = False
    waiting_stability: str              = "stable"
    recommended_action: str             = ContinuityAction.NO_ACTION
    escalation_hint: Optional[str]      = None
    reason_codes: List[str]             = field(default_factory=list)
    metadata: Dict[str, Any]           = field(default_factory=dict)
    evaluated_at: str                   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_fallback: bool                   = False
    error_message: Optional[str]        = None

    def to_dict(self) -> dict:
        return {
            "safe_to_continue":       self.safe_to_continue,
            "continuity_state":       self.continuity_state,
            "continuity_score":       round(self.continuity_score, 4),
            "continuity_gap_detected": self.continuity_gap_detected,
            "stage_transition_risk":  self.stage_transition_risk,
            "unresolved_loop":        self.unresolved_loop,
            "waiting_stability":      self.waiting_stability,
            "recommended_action":     self.recommended_action,
            "escalation_hint":        self.escalation_hint,
            "reason_codes":           self.reason_codes,
            "metadata":               self.metadata,
            "evaluated_at":           self.evaluated_at,
            "is_fallback":            self.is_fallback,
            "error_message":          self.error_message,
        }


def _neutral_result(error_message: Optional[str] = None) -> ContinuityResult:
    """
    Fail-safe neutral result.
    Returned on any exception inside evaluate_continuity().
    Never triggers outbound actions. Safe to inject into dispatcher context.
    """
    return ContinuityResult(
        safe_to_continue=True,
        continuity_state=ContinuityState.STABLE_PROGRESSION,
        continuity_score=0.75,
        continuity_gap_detected=False,
        stage_transition_risk=False,
        unresolved_loop=False,
        waiting_stability="stable",
        recommended_action=ContinuityAction.NO_ACTION,
        escalation_hint=None,
        reason_codes=["fallback_neutral"],
        metadata={},
        is_fallback=True,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# ClinicalContinuityEngine
# ---------------------------------------------------------------------------

class ClinicalContinuityEngine:
    """
    Evaluates long-term rehabilitation continuity for each user.

    This engine produces internal intelligence only.
    It does NOT diagnose, prescribe, or make medical recommendations.
    It does NOT send messages or call any outbound service.
    It enriches the dispatcher context so governance can make better decisions.

    Architecture position:
      after: behaviour_task
      before: dispatcher final decision packaging
      mode: parallel enrichment layer

    Override hierarchy (highest to lowest):
      human_escalation > silence_respect > recovery_policy >
      emotional_safety > continuity_logic
    """

    # Thresholds (days)
    _WAITING_STABLE_THRESHOLD_DAYS: int = 14    # waiting OK up to 14 days
    _WAITING_UNCLEAR_THRESHOLD_DAYS: int = 21   # waiting unclear 15–21 days
    _CONTINUITY_GAP_THRESHOLD_DAYS: int = 30    # gap if silent 30+ days
    _DORMANT_THRESHOLD_DAYS: int = 60           # dormant if silent 60+ days
    _LOOP_REPEAT_THRESHOLD: int = 3             # unresolved if repeated 3+ times

    async def evaluate_continuity(
        self,
        user_id: int,
        context_package: Dict[str, Any],
    ) -> ContinuityResult:
        """
        Main evaluation entry point.

        Always returns a ContinuityResult.
        Any internal exception triggers _neutral_result() — never crashes pipeline.

        IMMUTABLE CONSTRAINT:
        This method MUST NEVER produce recommendations that:
          - Send messages directly to users
          - Bypass human escalation
          - Bypass silence respect
          - Bypass recovery policy
          - Create medical diagnoses or recommendations
          - Create fear, pressure, or urgency
          - Override the Central Orchestrator as final authority
        """
        try:
            return await self._evaluate_safe(user_id, context_package)
        except Exception as exc:
            log.warning(
                "[CONTINUITY] Safe fallback activated for user %s: %s",
                user_id, exc
            )
            return _neutral_result(error_message=str(exc))

    async def _evaluate_safe(
        self,
        user_id: int,
        context_package: Dict[str, Any],
    ) -> ContinuityResult:
        """Core evaluation logic. Called inside try/except by evaluate_continuity()."""

        reason_codes: List[str] = []
        metadata: Dict[str, Any] = {"user_id": user_id}

        # ------------------------------------------------------------------
        # 1. Extract governance overrides — checked first, override everything
        # ------------------------------------------------------------------
        silence_respect: bool = bool(context_package.get("silence_respect", False))
        human_escalation: bool = bool(context_package.get("human_escalation_required", False))
        recovery_policy_blocked: bool = bool(context_package.get("recovery_policy_blocked", False))
        emotional_overload: bool = bool(context_package.get("emotional_overload", False))
        low_intensity_mode: bool = bool(context_package.get("behaviour_low_intensity", False))

        # ------------------------------------------------------------------
        # 2. Hard overrides — return immediately without further analysis
        # ------------------------------------------------------------------
        if human_escalation:
            log.info("[CONTINUITY] Hold — human escalation active for user %s", user_id)
            return ContinuityResult(
                safe_to_continue=False,
                continuity_state=ContinuityState.NEEDS_HUMAN_REVIEW,
                continuity_score=0.5,
                continuity_gap_detected=False,
                stage_transition_risk=False,
                unresolved_loop=False,
                waiting_stability="blocked_by_escalation",
                recommended_action=ContinuityAction.HOLD_DUE_TO_ESCALATION,
                escalation_hint="Human escalation is active — continuity engine defers to human.",
                reason_codes=["human_escalation_override"],
                metadata=metadata,
            )

        if silence_respect:
            log.info("[CONTINUITY] Hold — silence respect active for user %s", user_id)
            return ContinuityResult(
                safe_to_continue=False,
                continuity_state=ContinuityState.WAITING_STABLE,
                continuity_score=0.65,
                continuity_gap_detected=False,
                stage_transition_risk=False,
                unresolved_loop=False,
                waiting_stability="silence_respected",
                recommended_action=ContinuityAction.HOLD_DUE_TO_SILENCE_RESPECT,
                escalation_hint=None,
                reason_codes=["silence_respect_override"],
                metadata=metadata,
            )

        # ------------------------------------------------------------------
        # 3. Extract context fields
        # ------------------------------------------------------------------
        current_stage: str = context_package.get("current_stage", "")
        previous_stage: str = context_package.get("previous_stage", "")
        last_action: str = context_package.get("last_completed_action", "")
        next_expected_action: str = context_package.get("next_expected_action", "")
        days_since_progress: float = float(context_package.get("days_since_last_progress", 0))
        days_since_contact: float = float(context_package.get("days_since_last_contact", 0))
        user_is_waiting: bool = bool(context_package.get("user_is_waiting", False))
        system_is_waiting: bool = bool(context_package.get("system_is_waiting", False))
        expert_expected: bool = bool(context_package.get("expert_expected", False))
        karen_expected: bool = bool(context_package.get("karen_expected", False))
        analyses_incomplete: bool = bool(context_package.get("analyses_incomplete", False))
        data_incomplete: bool = bool(context_package.get("data_collection_incomplete", False))
        returned_after_pause: bool = bool(context_package.get("returned_after_pause", False))
        repeated_unresolved_count: int = int(context_package.get("repeated_unresolved_count", 0))
        prior_escalation_pending: bool = bool(context_package.get("prior_escalation_pending", False))
        cooldown_active: bool = bool(context_package.get("cooldown_active", False))
        payment_pending: bool = bool(context_package.get("payment_pending", False))
        support_cycle_active: bool = bool(context_package.get("support_cycle_active", False))

        # ------------------------------------------------------------------
        # 4. Compute continuity score
        # ------------------------------------------------------------------
        score = self._compute_score(
            days_since_progress=days_since_progress,
            days_since_contact=days_since_contact,
            analyses_incomplete=analyses_incomplete,
            data_incomplete=data_incomplete,
            repeated_unresolved_count=repeated_unresolved_count,
            prior_escalation_pending=prior_escalation_pending,
            returned_after_pause=returned_after_pause,
            stage_defined=bool(current_stage),
            next_action_defined=bool(next_expected_action),
            recovery_policy_blocked=recovery_policy_blocked,
        )
        metadata["continuity_score_raw"] = score

        # ------------------------------------------------------------------
        # 5. Detect continuity state
        # ------------------------------------------------------------------
        state, reason_codes, gap_detected, transition_risk, unresolved = (
            self._classify_state(
                current_stage=current_stage,
                previous_stage=previous_stage,
                days_since_progress=days_since_progress,
                days_since_contact=days_since_contact,
                user_is_waiting=user_is_waiting,
                system_is_waiting=system_is_waiting,
                expert_expected=expert_expected,
                karen_expected=karen_expected,
                analyses_incomplete=analyses_incomplete,
                data_incomplete=data_incomplete,
                returned_after_pause=returned_after_pause,
                repeated_unresolved_count=repeated_unresolved_count,
                prior_escalation_pending=prior_escalation_pending,
                support_cycle_active=support_cycle_active,
                payment_pending=payment_pending,
                score=score,
            )
        )

        if gap_detected:
            log.info("[CONTINUITY] Continuity gap detected for user %s (state=%s)", user_id, state)

        # ------------------------------------------------------------------
        # 6. Determine waiting stability
        # ------------------------------------------------------------------
        waiting_stability = self._assess_waiting_stability(
            user_is_waiting=user_is_waiting,
            system_is_waiting=system_is_waiting,
            days_since_progress=days_since_progress,
            expert_expected=expert_expected,
            karen_expected=karen_expected,
        )

        # ------------------------------------------------------------------
        # 7. Generate recommended action (internal only — no outbound sends)
        # ------------------------------------------------------------------
        action = self._recommend_action(
            state=state,
            gap_detected=gap_detected,
            transition_risk=transition_risk,
            unresolved=unresolved,
            recovery_policy_blocked=recovery_policy_blocked,
            emotional_overload=emotional_overload,
            low_intensity_mode=low_intensity_mode,
            data_incomplete=data_incomplete,
            analyses_incomplete=analyses_incomplete,
            prior_escalation_pending=prior_escalation_pending,
            karen_expected=karen_expected,
        )

        # ------------------------------------------------------------------
        # 8. Generate escalation hint if needed
        # ------------------------------------------------------------------
        escalation_hint = self._generate_escalation_hint(
            state=state,
            prior_escalation_pending=prior_escalation_pending,
            days_since_progress=days_since_progress,
            repeated_unresolved_count=repeated_unresolved_count,
        )

        if escalation_hint:
            log.info("[CONTINUITY] Escalation hint generated for user %s: %s", user_id, escalation_hint)

        # ------------------------------------------------------------------
        # 9. Build result
        # ------------------------------------------------------------------
        log.info(
            "[CONTINUITY] Continuity evaluation complete for user %s: state=%s score=%.2f gap=%s",
            user_id, state, score, gap_detected
        )

        return ContinuityResult(
            safe_to_continue=True,
            continuity_state=state,
            continuity_score=score,
            continuity_gap_detected=gap_detected,
            stage_transition_risk=transition_risk,
            unresolved_loop=unresolved,
            waiting_stability=waiting_stability,
            recommended_action=action,
            escalation_hint=escalation_hint,
            reason_codes=reason_codes,
            metadata=metadata,
        )

    # -----------------------------------------------------------------------
    # Score computation
    # -----------------------------------------------------------------------

    def _compute_score(
        self,
        days_since_progress: float,
        days_since_contact: float,
        analyses_incomplete: bool,
        data_incomplete: bool,
        repeated_unresolved_count: int,
        prior_escalation_pending: bool,
        returned_after_pause: bool,
        stage_defined: bool,
        next_action_defined: bool,
        recovery_policy_blocked: bool,
    ) -> float:
        """
        Compute a continuity score in [0.0, 1.0].
        Higher = more coherent stable progression.
        """
        score = 1.0

        # Penalise for time without meaningful progress
        if days_since_progress > self._DORMANT_THRESHOLD_DAYS:
            score -= 0.45
        elif days_since_progress > self._CONTINUITY_GAP_THRESHOLD_DAYS:
            score -= 0.30
        elif days_since_progress > self._WAITING_UNCLEAR_THRESHOLD_DAYS:
            score -= 0.15
        elif days_since_progress > self._WAITING_STABLE_THRESHOLD_DAYS:
            score -= 0.08

        # Penalise for incomplete data/analyses
        if data_incomplete:
            score -= 0.12
        if analyses_incomplete:
            score -= 0.10

        # Penalise for unresolved loops
        if repeated_unresolved_count >= self._LOOP_REPEAT_THRESHOLD:
            score -= 0.18
        elif repeated_unresolved_count == 2:
            score -= 0.10
        elif repeated_unresolved_count == 1:
            score -= 0.04

        # Penalise for pending escalation
        if prior_escalation_pending:
            score -= 0.12

        # Mild penalty for undefined next step
        if not next_action_defined:
            score -= 0.06
        if not stage_defined:
            score -= 0.06

        # Small bonus for returning after pause (re-engagement)
        if returned_after_pause:
            score = min(score + 0.05, 1.0)

        return max(0.0, min(1.0, round(score, 4)))

    # -----------------------------------------------------------------------
    # State classification
    # -----------------------------------------------------------------------

    def _classify_state(
        self,
        current_stage: str,
        previous_stage: str,
        days_since_progress: float,
        days_since_contact: float,
        user_is_waiting: bool,
        system_is_waiting: bool,
        expert_expected: bool,
        karen_expected: bool,
        analyses_incomplete: bool,
        data_incomplete: bool,
        returned_after_pause: bool,
        repeated_unresolved_count: int,
        prior_escalation_pending: bool,
        support_cycle_active: bool,
        payment_pending: bool,
        score: float,
    ):
        """
        Classify continuity state from context signals.
        Returns: (state, reason_codes, gap_detected, transition_risk, unresolved)
        """
        reason_codes = []
        gap_detected = False
        transition_risk = False
        unresolved = False

        # --- Priority 1: Human review needed ---
        if prior_escalation_pending:
            reason_codes.append("prior_escalation_pending")
            return (ContinuityState.NEEDS_HUMAN_REVIEW, reason_codes, False, False, False)

        # --- Priority 2: Unresolved loop ---
        if repeated_unresolved_count >= self._LOOP_REPEAT_THRESHOLD:
            unresolved = True
            reason_codes.append(f"repeated_unresolved_count={repeated_unresolved_count}")
            return (ContinuityState.UNRESOLVED_LOOP, reason_codes, False, False, True)

        # --- Priority 3: Dormant ---
        if days_since_contact > self._DORMANT_THRESHOLD_DAYS:
            gap_detected = True
            reason_codes.append(f"days_since_contact={days_since_contact:.0f}")
            return (ContinuityState.DORMANT_BUT_NOT_LOST, reason_codes, True, False, False)

        # --- Priority 4: Continuity gap ---
        if days_since_progress > self._CONTINUITY_GAP_THRESHOLD_DAYS:
            gap_detected = True
            reason_codes.append(f"days_since_progress={days_since_progress:.0f}")
            return (ContinuityState.CONTINUITY_GAP, reason_codes, True, False, False)

        # --- Priority 5: Follow-up missing ---
        if days_since_progress > self._WAITING_UNCLEAR_THRESHOLD_DAYS and not user_is_waiting:
            gap_detected = True
            reason_codes.append("follow_up_missing")
            return (ContinuityState.FOLLOW_UP_MISSING, reason_codes, True, False, False)

        # --- Priority 6: Data incomplete ---
        if data_incomplete:
            reason_codes.append("data_collection_incomplete")
            return (ContinuityState.DATA_COLLECTION_INCOMPLETE, reason_codes, False, False, False)

        # --- Priority 7: Analyses pending ---
        if analyses_incomplete:
            reason_codes.append("analyses_incomplete")
            return (ContinuityState.ANALYSIS_PENDING, reason_codes, False, False, False)

        # --- Priority 8: Expert/Karen review pending ---
        if expert_expected or karen_expected:
            reason_codes.append("expert_or_karen_expected")
            return (ContinuityState.EXPERT_REVIEW_PENDING, reason_codes, False, False, False)

        # --- Priority 9: Stage transition ---
        if previous_stage and current_stage and previous_stage != current_stage:
            transition_risk = True
            reason_codes.append(f"stage_changed: {previous_stage}->{current_stage}")
            if payment_pending:
                reason_codes.append("payment_pending")
                return (ContinuityState.TRANSITION_FRAGILE, reason_codes, False, True, False)
            return (ContinuityState.TRANSITION_PENDING, reason_codes, False, True, False)

        # --- Priority 10: Waiting states ---
        if user_is_waiting or system_is_waiting:
            if days_since_progress > self._WAITING_STABLE_THRESHOLD_DAYS:
                reason_codes.append(f"waiting_too_long={days_since_progress:.0f}d")
                return (ContinuityState.WAITING_UNCLEAR, reason_codes, False, False, False)
            reason_codes.append("waiting_within_threshold")
            return (ContinuityState.WAITING_STABLE, reason_codes, False, False, False)

        # --- Priority 11: Support cycle active ---
        if support_cycle_active:
            reason_codes.append("support_cycle_active")
            return (ContinuityState.SUPPORT_CYCLE_ACTIVE, reason_codes, False, False, False)

        # --- Priority 12: Stable progression ---
        reason_codes.append("stable_progression")
        return (ContinuityState.STABLE_PROGRESSION, reason_codes, False, False, False)

    # -----------------------------------------------------------------------
    # Waiting stability assessment
    # -----------------------------------------------------------------------

    def _assess_waiting_stability(
        self,
        user_is_waiting: bool,
        system_is_waiting: bool,
        days_since_progress: float,
        expert_expected: bool,
        karen_expected: bool,
    ) -> str:
        if not (user_is_waiting or system_is_waiting):
            return "not_waiting"
        if expert_expected or karen_expected:
            return "waiting_for_expert"
        if days_since_progress <= self._WAITING_STABLE_THRESHOLD_DAYS:
            return "stable"
        if days_since_progress <= self._WAITING_UNCLEAR_THRESHOLD_DAYS:
            return "borderline"
        return "unclear"

    # -----------------------------------------------------------------------
    # Action recommendation (internal only)
    # -----------------------------------------------------------------------

    def _recommend_action(
        self,
        state: str,
        gap_detected: bool,
        transition_risk: bool,
        unresolved: bool,
        recovery_policy_blocked: bool,
        emotional_overload: bool,
        low_intensity_mode: bool,
        data_incomplete: bool,
        analyses_incomplete: bool,
        prior_escalation_pending: bool,
        karen_expected: bool,
    ) -> str:
        """
        Determine recommended internal action.

        CONSTRAINT: All actions are internal governance signals only.
        They do NOT trigger outbound messages directly.
        The dispatcher remains the only proactive outbound path.
        """
        # Safety overrides first
        if recovery_policy_blocked:
            return ContinuityAction.NO_ACTION
        if emotional_overload:
            return ContinuityAction.REDUCE_MESSAGE_INTENSITY

        # State-driven recommendations
        if prior_escalation_pending or state == ContinuityState.NEEDS_HUMAN_REVIEW:
            return ContinuityAction.PREPARE_HUMAN_REVIEW

        if state == ContinuityState.UNRESOLVED_LOOP:
            return ContinuityAction.PREPARE_HUMAN_REVIEW

        if state in (ContinuityState.DORMANT_BUT_NOT_LOST, ContinuityState.CONTINUITY_GAP):
            if low_intensity_mode:
                return ContinuityAction.REDUCE_MESSAGE_INTENSITY
            return ContinuityAction.CLARIFY_NEXT_STEP

        if state == ContinuityState.FOLLOW_UP_MISSING:
            return ContinuityAction.CLARIFY_NEXT_STEP

        if state == ContinuityState.DATA_COLLECTION_INCOMPLETE:
            return ContinuityAction.REQUEST_MISSING_DATA_VIA_DISPATCHER

        if state == ContinuityState.ANALYSIS_PENDING:
            return ContinuityAction.PRESERVE_WAITING_STATE

        if state == ContinuityState.EXPERT_REVIEW_PENDING:
            if karen_expected:
                return ContinuityAction.PREPARE_KAREN_REVIEW
            return ContinuityAction.PREPARE_HUMAN_REVIEW

        if state in (ContinuityState.TRANSITION_PENDING, ContinuityState.TRANSITION_FRAGILE):
            return ContinuityAction.MARK_TRANSITION_PENDING

        if state in (ContinuityState.WAITING_STABLE, ContinuityState.WAITING_UNCLEAR):
            return ContinuityAction.PRESERVE_WAITING_STATE

        if state == ContinuityState.SUPPORT_CYCLE_ACTIVE:
            return ContinuityAction.NO_ACTION

        return ContinuityAction.NO_ACTION

    # -----------------------------------------------------------------------
    # Escalation hint generation
    # -----------------------------------------------------------------------

    def _generate_escalation_hint(
        self,
        state: str,
        prior_escalation_pending: bool,
        days_since_progress: float,
        repeated_unresolved_count: int,
    ) -> Optional[str]:
        """
        Generate an internal hint for dispatcher/governance layer.
        This is a guidance note only — not an outbound message.
        """
        if prior_escalation_pending:
            return "Prior escalation still pending — ensure human follow-through before resuming automated outreach."

        if state == ContinuityState.UNRESOLVED_LOOP:
            return (
                f"User has {repeated_unresolved_count} unresolved repeated cycles. "
                "Human review recommended before next automated contact."
            )

        if state == ContinuityState.NEEDS_HUMAN_REVIEW:
            return "Continuity state requires human review — escalate to support team."

        if state == ContinuityState.DORMANT_BUT_NOT_LOST and days_since_progress > self._DORMANT_THRESHOLD_DAYS:
            return (
                f"User has been dormant for {days_since_progress:.0f} days. "
                "Gentle human-led re-engagement may be more appropriate than automated contact."
            )

        if state == ContinuityState.TRANSITION_FRAGILE:
            return "Stage transition is fragile — ensure human verification before next automated step."

        return None

    # -----------------------------------------------------------------------
    # Persistence helper (stores to pm_client_profiles via asyncpg)
    # -----------------------------------------------------------------------

    async def persist_continuity_result(
        self,
        user_id: int,
        result: ContinuityResult,
        db_pool,
    ) -> None:
        """
        Persist key continuity fields to pm_client_profiles.
        Non-fatal: any DB error is logged and swallowed.
        """
        try:
            import json
            notes = {
                "state": result.continuity_state,
                "action": result.recommended_action,
                "reason_codes": result.reason_codes,
                "escalation_hint": result.escalation_hint,
                "metadata": result.metadata,
            }
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE pm_client_profiles SET
                        continuity_state = $1,
                        continuity_score = $2,
                        continuity_gap_detected = $3,
                        stage_transition_risk = $4,
                        unresolved_continuity_loop = $5,
                        waiting_stability = $6,
                        last_continuity_check = NOW() AT TIME ZONE 'UTC',
                        continuity_notes = $7::jsonb
                    WHERE user_id = $8
                    """,
                    result.continuity_state,
                    result.continuity_score,
                    result.continuity_gap_detected,
                    result.stage_transition_risk,
                    result.unresolved_loop,
                    result.waiting_stability,
                    json.dumps(notes),
                    user_id,
                )
        except Exception as exc:
            log.warning("[CONTINUITY] persist_continuity_result failed for user %s: %s", user_id, exc)

    # -----------------------------------------------------------------------
    # Stats for dashboard
    # -----------------------------------------------------------------------

    async def get_engine_stats(self, db_pool=None) -> dict:
        """Return aggregated continuity stats for dashboard exposure."""
        stats: dict = {
            "engine": "ClinicalContinuityEngine",
            "version": "3.7",
        }
        if not db_pool:
            stats["db_available"] = False
            return stats
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE continuity_gap_detected = TRUE)    AS total_gaps,
                        COUNT(*) FILTER (WHERE continuity_state = 'waiting_unclear') AS waiting_unclear_count,
                        COUNT(*) FILTER (WHERE continuity_state = 'transition_fragile') AS transition_fragile_count,
                        COUNT(*) FILTER (WHERE unresolved_continuity_loop = TRUE)  AS unresolved_loops,
                        COUNT(*) FILTER (WHERE continuity_state = 'expert_review_pending') AS expert_review_count,
                        COUNT(*) FILTER (WHERE continuity_state = 'needs_human_review') AS human_review_count,
                        AVG(continuity_score) AS avg_continuity_score,
                        COUNT(*) FILTER (WHERE last_continuity_check IS NOT NULL) AS evaluated_count
                    FROM pm_client_profiles
                    """
                )
                if rows:
                    r = rows[0]
                    stats.update({
                        "total_continuity_gaps":      int(r["total_gaps"] or 0),
                        "waiting_unclear_count":      int(r["waiting_unclear_count"] or 0),
                        "transition_fragile_count":   int(r["transition_fragile_count"] or 0),
                        "unresolved_loops":           int(r["unresolved_loops"] or 0),
                        "expert_review_pending":      int(r["expert_review_count"] or 0),
                        "human_review_needed":        int(r["human_review_count"] or 0),
                        "average_continuity_score":   round(float(r["avg_continuity_score"] or 0.0), 4),
                        "evaluated_users":            int(r["evaluated_count"] or 0),
                    })
        except Exception as exc:
            log.warning("[CONTINUITY] get_engine_stats DB error: %s", exc)
            stats["db_error"] = str(exc)
        return stats


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_engine: Optional[ClinicalContinuityEngine] = None
_engine_lock = asyncio.Lock()


def init_continuity_engine() -> ClinicalContinuityEngine:
    """
    Initialise and return the ClinicalContinuityEngine singleton.
    Idempotent — safe to call multiple times.
    """
    global _engine
    if _engine is None:
        _engine = ClinicalContinuityEngine()
        log.info("[CONTINUITY] ClinicalContinuityEngine singleton created")
    return _engine


def get_continuity_engine() -> Optional[ClinicalContinuityEngine]:
    """Return the singleton or None if not yet initialised."""
    return _engine

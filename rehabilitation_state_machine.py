# -*- coding: utf-8 -*-
# =============================================================================
# REHABILITATION STATE MACHINE — Phase 3.9
# =============================================================================
# Purpose  : Formal rehabilitation state machine — official route-state authority
#            for the rehabilitation operating system.
#            Defines official client journey states, allowed/blocked transitions,
#            stage completion rules, regression rules, stall detection,
#            progression/escalation gates, and continuity preservation rules.
#
# This is NOT chatbot flow logic.
# This is NOT medical diagnosis.
# This is NOT treatment recommendation.
#
# IMMUTABLE CONSTRAINT:
#   This module MUST NEVER produce recommendations that:
#   - Send messages directly to users
#   - Call Telegram, SendPulse, or any outbound sender
#   - Call the dispatcher directly
#   - Bypass human escalation
#   - Bypass silence respect
#   - Bypass recovery policy
#   - Make medical conclusions or diagnoses
#   - Prescribe treatment
#   - Create urgency or pressure
#   - Override the Central Orchestrator as final authority
#
# Override hierarchy (highest → lowest):
#   human_escalation > silence_respect > recovery_policy >
#   emotional_safety > continuity_logic > trajectory_intelligence >
#   rehabilitation_state_machine
#
# Integration: Task 5.8 in the fire-and-forget chain.
#              Runs AFTER trajectory_task, BEFORE dispatcher_task.
#              Enriches dispatcher context — never calls dispatcher directly.
# =============================================================================

from __future__ import annotations

import logging
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List, Set

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rehabilitation States
# ---------------------------------------------------------------------------

class RehabState(str, Enum):
    INITIAL_CONTACT       = "initial_contact"
    NEEDS_ASSESSMENT      = "needs_assessment"
    AWAITING_CONSULTATION = "awaiting_consultation"
    CONSULTATION_ACTIVE   = "consultation_active"
    AWAITING_ANALYSIS     = "awaiting_analysis"
    ANALYSIS_REVIEW       = "analysis_review"
    TREATMENT_PLANNING    = "treatment_planning"
    TREATMENT_ACTIVE      = "treatment_active"
    MONITORING            = "monitoring"
    FOLLOW_UP             = "follow_up"
    MAINTENANCE           = "maintenance"
    PAUSED                = "paused"
    STALLED               = "stalled"
    LOST_TO_FOLLOW_UP     = "lost_to_follow_up"
    COMPLETED             = "completed"
    UNKNOWN               = "unknown"


# ---------------------------------------------------------------------------
# Rehabilitation Stages
# ---------------------------------------------------------------------------

class RehabStage(str, Enum):
    INTAKE        = "intake"
    DIAGNOSTIC    = "diagnostic"
    INTERVENTION  = "intervention"
    CONTINUITY    = "continuity"
    UNKNOWN       = "unknown"


# State → Stage mapping
STATE_TO_STAGE: Dict[str, str] = {
    RehabState.INITIAL_CONTACT:       RehabStage.INTAKE,
    RehabState.NEEDS_ASSESSMENT:      RehabStage.INTAKE,
    RehabState.AWAITING_CONSULTATION: RehabStage.DIAGNOSTIC,
    RehabState.CONSULTATION_ACTIVE:   RehabStage.DIAGNOSTIC,
    RehabState.AWAITING_ANALYSIS:     RehabStage.DIAGNOSTIC,
    RehabState.ANALYSIS_REVIEW:       RehabStage.DIAGNOSTIC,
    RehabState.TREATMENT_PLANNING:    RehabStage.INTERVENTION,
    RehabState.TREATMENT_ACTIVE:      RehabStage.INTERVENTION,
    RehabState.MONITORING:            RehabStage.CONTINUITY,
    RehabState.FOLLOW_UP:             RehabStage.CONTINUITY,
    RehabState.MAINTENANCE:           RehabStage.CONTINUITY,
    RehabState.PAUSED:                RehabStage.CONTINUITY,
    RehabState.STALLED:               RehabStage.CONTINUITY,
    RehabState.LOST_TO_FOLLOW_UP:     RehabStage.CONTINUITY,
    RehabState.COMPLETED:             RehabStage.CONTINUITY,
    RehabState.UNKNOWN:               RehabStage.UNKNOWN,
}


# ---------------------------------------------------------------------------
# Transition Map — allowed forward transitions
# ---------------------------------------------------------------------------

ALLOWED_FORWARD: Dict[str, Set[str]] = {
    RehabState.INITIAL_CONTACT: {
        RehabState.NEEDS_ASSESSMENT,
    },
    RehabState.NEEDS_ASSESSMENT: {
        RehabState.AWAITING_CONSULTATION,
    },
    RehabState.AWAITING_CONSULTATION: {
        RehabState.CONSULTATION_ACTIVE,
    },
    RehabState.CONSULTATION_ACTIVE: {
        RehabState.AWAITING_ANALYSIS,
        RehabState.TREATMENT_PLANNING,
        RehabState.MONITORING,
    },
    RehabState.AWAITING_ANALYSIS: {
        RehabState.ANALYSIS_REVIEW,
    },
    RehabState.ANALYSIS_REVIEW: {
        RehabState.TREATMENT_PLANNING,
        RehabState.MONITORING,
    },
    RehabState.TREATMENT_PLANNING: {
        RehabState.TREATMENT_ACTIVE,
    },
    RehabState.TREATMENT_ACTIVE: {
        RehabState.MONITORING,
        RehabState.FOLLOW_UP,
    },
    RehabState.MONITORING: {
        RehabState.FOLLOW_UP,
        RehabState.MAINTENANCE,
        RehabState.COMPLETED,
    },
    RehabState.FOLLOW_UP: {
        RehabState.MAINTENANCE,
        RehabState.TREATMENT_ACTIVE,
        RehabState.COMPLETED,
    },
    RehabState.MAINTENANCE: {
        RehabState.FOLLOW_UP,
        RehabState.COMPLETED,
    },
    RehabState.PAUSED: set(),      # resume handled via previous_state
    RehabState.STALLED: set(),     # resume handled via previous_state
    RehabState.LOST_TO_FOLLOW_UP: set(),  # requires human review
    RehabState.COMPLETED: set(),   # journey over — no forward transitions
    RehabState.UNKNOWN: {
        RehabState.INITIAL_CONTACT,
        RehabState.NEEDS_ASSESSMENT,
    },
}

# Universal transitions valid from any non-completed state
UNIVERSAL_TRANSITIONS: Set[str] = {
    RehabState.PAUSED,
    RehabState.STALLED,
    RehabState.LOST_TO_FOLLOW_UP,
    RehabState.COMPLETED,
}

# Allowed regression transitions
ALLOWED_REGRESSION: Dict[str, Set[str]] = {
    RehabState.AWAITING_ANALYSIS:   {RehabState.AWAITING_CONSULTATION},
    RehabState.ANALYSIS_REVIEW:     {RehabState.AWAITING_ANALYSIS},
    RehabState.TREATMENT_PLANNING:  {RehabState.AWAITING_CONSULTATION, RehabState.ANALYSIS_REVIEW},
    RehabState.TREATMENT_ACTIVE:    {RehabState.TREATMENT_PLANNING},
    RehabState.MONITORING:          {RehabState.TREATMENT_ACTIVE},
    RehabState.FOLLOW_UP:           {RehabState.TREATMENT_ACTIVE, RehabState.MONITORING},
    RehabState.MAINTENANCE:         {RehabState.FOLLOW_UP},
}

# Hard-blocked transitions (from → blocked_to)
HARD_BLOCKED: Dict[str, Set[str]] = {
    RehabState.COMPLETED: {
        RehabState.INITIAL_CONTACT, RehabState.NEEDS_ASSESSMENT,
        RehabState.AWAITING_CONSULTATION, RehabState.CONSULTATION_ACTIVE,
        RehabState.AWAITING_ANALYSIS, RehabState.ANALYSIS_REVIEW,
        RehabState.TREATMENT_PLANNING, RehabState.TREATMENT_ACTIVE,
        RehabState.MONITORING, RehabState.FOLLOW_UP, RehabState.MAINTENANCE,
    },
    RehabState.INITIAL_CONTACT: {
        RehabState.TREATMENT_ACTIVE, RehabState.MONITORING, RehabState.FOLLOW_UP,
        RehabState.MAINTENANCE, RehabState.ANALYSIS_REVIEW, RehabState.TREATMENT_PLANNING,
    },
    RehabState.NEEDS_ASSESSMENT: {
        RehabState.TREATMENT_ACTIVE, RehabState.MONITORING, RehabState.FOLLOW_UP,
        RehabState.MAINTENANCE, RehabState.ANALYSIS_REVIEW,
    },
    RehabState.LOST_TO_FOLLOW_UP: {
        # All forward transitions blocked without human review
        RehabState.AWAITING_CONSULTATION, RehabState.CONSULTATION_ACTIVE,
        RehabState.AWAITING_ANALYSIS, RehabState.ANALYSIS_REVIEW,
        RehabState.TREATMENT_PLANNING, RehabState.TREATMENT_ACTIVE,
        RehabState.MONITORING, RehabState.FOLLOW_UP, RehabState.MAINTENANCE,
        RehabState.COMPLETED,
    },
}


# ---------------------------------------------------------------------------
# Stall Thresholds (days per state)
# ---------------------------------------------------------------------------

STALL_THRESHOLDS: Dict[str, int] = {
    RehabState.INITIAL_CONTACT:       3,
    RehabState.NEEDS_ASSESSMENT:      7,
    RehabState.AWAITING_CONSULTATION: 21,
    RehabState.CONSULTATION_ACTIVE:   14,
    RehabState.AWAITING_ANALYSIS:     30,
    RehabState.ANALYSIS_REVIEW:       14,
    RehabState.TREATMENT_PLANNING:    14,
    RehabState.TREATMENT_ACTIVE:      90,
    RehabState.MONITORING:            60,
    RehabState.FOLLOW_UP:             30,
    RehabState.MAINTENANCE:           180,
}


# ---------------------------------------------------------------------------
# Result Dataclass
# ---------------------------------------------------------------------------

@dataclass
class StateMachineResult:
    """
    Output of evaluate_state().
    Internal intelligence only — NEVER triggers outbound messages.
    """
    user_id:                      int
    rehabilitation_state:         str   = RehabState.UNKNOWN
    rehabilitation_stage:         str   = RehabStage.UNKNOWN
    rehabilitation_substage:      str   = ""
    previous_rehabilitation_state: str  = ""
    next_allowed_states:          List[str] = field(default_factory=list)
    blocked_transition_reason:    str   = ""
    stage_completion_score:       float = 0.5
    stage_stall_detected:         bool  = False
    stall_days:                   int   = 0
    progression_gate_status:      str   = "pending"   # open / closed / pending
    escalation_gate_status:       str   = "clear"      # clear / flagged / active
    state_machine_notes:          Dict[str, Any] = field(default_factory=dict)
    evaluated_at:                 Optional[datetime] = None
    error_message:                Optional[str] = None
    is_neutral_fallback:          bool  = False
    transition_attempted:         bool  = False
    transition_blocked:           bool  = False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RehabilitationStateMachine:
    """
    Phase 3.9 — Rehabilitation State Machine.

    Official route-state authority for the rehabilitation operating system.
    Defines formal rehabilitation states, allowed/blocked transitions,
    stage completion rules, regression, stall detection, and gate logic.

    NEVER diagnoses, prescribes, sends messages, or bypasses governance.
    """

    def __init__(self) -> None:
        self._initialized = False
        log.info("[STATE_MACHINE] RehabilitationStateMachine singleton created")

    async def initialize(self) -> None:
        self._initialized = True
        log.info("[STATE_MACHINE] RehabilitationStateMachine initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate_state(
        self,
        user_id:                int,
        profile:                Optional[Dict[str, Any]] = None,
        continuity_result:      Optional[Dict[str, Any]] = None,
        trajectory_result:      Optional[Dict[str, Any]] = None,
        behaviour_result:       Optional[Dict[str, Any]] = None,
        risk_result:            Optional[Dict[str, Any]] = None,
        requested_transition:   Optional[str]            = None,
        silence_respected:      bool                     = False,
        human_escalation:       bool                     = False,
        recovery_policy_active: bool                     = False,
    ) -> StateMachineResult:
        """
        Core evaluation method.

        IMMUTABLE CONSTRAINT:
            This method MUST NEVER produce recommendations that:
            - Send messages directly to users
            - Call Telegram, SendPulse, or any outbound sender
            - Call the dispatcher directly
            - Bypass human escalation, silence respect, or recovery policy
            - Make medical conclusions, diagnoses, or prescriptions
            - Create urgency, pressure, or fear
            - Override the Central Orchestrator as final authority

        Returns a StateMachineResult with internal intelligence only.
        On any exception, returns _neutral_result() — never crashes the pipeline.
        """
        try:
            # 1. Governance override checks (hierarchy: top priority)
            if human_escalation:
                return self._governance_override(
                    user_id, "human_escalation_active",
                    "Human escalation active — state evaluation skipped"
                )
            if silence_respected:
                return self._governance_override(
                    user_id, "silence_respect_active",
                    "Silence respect active — state evaluation skipped"
                )
            if recovery_policy_active:
                return self._governance_override(
                    user_id, "recovery_policy_active",
                    "Recovery policy active — state evaluation skipped"
                )

            profile = profile or {}
            continuity_result  = continuity_result  or {}
            trajectory_result  = trajectory_result  or {}
            behaviour_result   = behaviour_result   or {}
            risk_result        = risk_result        or {}

            # 2. Resolve current state
            current_state = self._resolve_current_state(profile)
            current_stage = STATE_TO_STAGE.get(current_state, RehabStage.UNKNOWN)
            previous_state = profile.get("previous_rehabilitation_state", "")

            # 3. Compute stage completion score
            completion_score = self._compute_completion_score(
                profile, continuity_result, trajectory_result, behaviour_result
            )

            # 4. Stall detection
            stall_detected, stall_days = self._detect_stall(current_state, profile)
            if stall_detected:
                log.info("[STATE_MACHINE] Stall detected: user_id=%s state=%s days=%d",
                         user_id, current_state, stall_days)

            # 5. Transition evaluation
            transition_blocked = False
            blocked_reason = ""
            if requested_transition:
                allowed, reason = self._evaluate_transition(
                    current_state, requested_transition, completion_score
                )
                transition_blocked = not allowed
                blocked_reason = reason if not allowed else ""
                if transition_blocked:
                    log.info("[STATE_MACHINE] Blocked transition: user_id=%s from=%s to=%s reason=%s",
                             user_id, current_state, requested_transition, reason)

            # 6. Compute next allowed states
            next_states = self._compute_next_states(current_state)

            # 7. Gate evaluation
            prog_gate = self._evaluate_progression_gate(current_state, completion_score, profile)
            esc_gate  = self._evaluate_escalation_gate(
                current_state, stall_detected, transition_blocked, trajectory_result
            )
            if esc_gate == "flagged":
                log.info("[STATE_MACHINE] Escalation gate flagged: user_id=%s state=%s",
                         user_id, current_state)

            # 8. Build notes
            notes = self._build_notes(
                current_state, current_stage, completion_score,
                stall_detected, stall_days, prog_gate, esc_gate
            )

            # 9. Persist (fire-and-forget, non-fatal)
            asyncio.create_task(self._persist_result(
                user_id, current_state, current_stage, previous_state,
                next_states, blocked_reason, completion_score,
                stall_detected, prog_gate, esc_gate, notes
            ))

            log.info("[STATE_MACHINE] State evaluation complete: user_id=%s state=%s stage=%s score=%.2f",
                     user_id, current_state, current_stage, completion_score)

            return StateMachineResult(
                user_id=user_id,
                rehabilitation_state=current_state,
                rehabilitation_stage=current_stage,
                rehabilitation_substage=profile.get("rehabilitation_substage", ""),
                previous_rehabilitation_state=previous_state,
                next_allowed_states=next_states,
                blocked_transition_reason=blocked_reason,
                stage_completion_score=round(completion_score, 4),
                stage_stall_detected=stall_detected,
                stall_days=stall_days,
                progression_gate_status=prog_gate,
                escalation_gate_status=esc_gate,
                state_machine_notes=notes,
                evaluated_at=datetime.now(timezone.utc),
                transition_attempted=bool(requested_transition),
                transition_blocked=transition_blocked,
            )

        except Exception as exc:
            log.warning("[STATE_MACHINE] Safe fallback activated: user_id=%s error=%s",
                        user_id, exc)
            return self._neutral_result(user_id, str(exc))

    # ------------------------------------------------------------------
    # State Resolution
    # ------------------------------------------------------------------

    def _resolve_current_state(self, profile: Dict[str, Any]) -> str:
        """Read rehabilitation_state from profile, default to INITIAL_CONTACT."""
        raw = profile.get("rehabilitation_state") or ""
        if raw in [s.value for s in RehabState]:
            return raw
        return RehabState.INITIAL_CONTACT

    # ------------------------------------------------------------------
    # Completion Score
    # ------------------------------------------------------------------

    def _compute_completion_score(
        self,
        profile:           Dict[str, Any],
        continuity_result: Dict[str, Any],
        trajectory_result: Dict[str, Any],
        behaviour_result:  Dict[str, Any],
    ) -> float:
        """
        Composite stage completion score (0.0–1.0).
        Uses available signals — never diagnoses or prescribes.
        """
        # Signal 1: consultation completion (from continuity state)
        cont_state = (continuity_result.get("continuity_state") or "").lower()
        consultation_signal = 1.0 if any(s in cont_state for s in (
            "consultation_active", "awaiting_analysis", "analysis_pending",
            "support_cycle_active", "stable_progression"
        )) else 0.0

        # Signal 2: analysis/follow-up completion
        analysis_signal = 1.0 if any(s in cont_state for s in (
            "analysis_pending", "expert_review_pending", "support_cycle_active"
        )) else 0.5 if "waiting_stable" in cont_state else 0.0

        # Signal 3: payment / commitment signal (from profile)
        payment_signal = 1.0 if profile.get("payment_confirmed") else                          0.7 if profile.get("stripe_customer_id") else 0.0

        # Signal 4: behaviour engagement score
        behaviour_score = float(behaviour_result.get("behaviour_score", 0.5) or 0.5)

        # Signal 5: trajectory progression
        trajectory_score = float(trajectory_result.get("trajectory_score", 0.5) or 0.5)

        score = (
            consultation_signal * 0.25 +
            analysis_signal     * 0.25 +
            payment_signal      * 0.15 +
            behaviour_score     * 0.20 +
            trajectory_score    * 0.15
        )
        return self._clamp(score)

    # ------------------------------------------------------------------
    # Stall Detection
    # ------------------------------------------------------------------

    def _detect_stall(
        self, state: str, profile: Dict[str, Any]
    ) -> tuple[bool, int]:
        """Detect stall: days in current state > threshold for that state."""
        threshold = STALL_THRESHOLDS.get(state)
        if threshold is None:
            return False, 0
        entered_at = profile.get("state_entered_at")
        if not entered_at:
            return False, 0
        try:
            if isinstance(entered_at, str):
                entered_at = datetime.fromisoformat(entered_at.replace("Z", "+00:00"))
            if not isinstance(entered_at, datetime):
                return False, 0
            if entered_at.tzinfo is None:
                entered_at = entered_at.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - entered_at).days
            return days >= threshold, days
        except Exception:
            return False, 0

    # ------------------------------------------------------------------
    # Transition Evaluation
    # ------------------------------------------------------------------

    def _evaluate_transition(
        self, from_state: str, to_state: str, completion_score: float
    ) -> tuple[bool, str]:
        """
        Evaluate whether a transition from_state → to_state is allowed.
        Returns (is_allowed, reason_if_blocked).
        """
        # Hard blocked?
        if to_state in HARD_BLOCKED.get(from_state, set()):
            reason = f"hard_blocked: {from_state} → {to_state} is explicitly prohibited"
            return False, reason

        # Universal transitions (paused, stalled, lost, completed)
        if to_state in UNIVERSAL_TRANSITIONS:
            if from_state == RehabState.COMPLETED and to_state != RehabState.COMPLETED:
                return False, "journey_completed: cannot transition from COMPLETED"
            return True, ""

        # Forward transition?
        if to_state in ALLOWED_FORWARD.get(from_state, set()):
            return True, ""

        # Regression?
        if to_state in ALLOWED_REGRESSION.get(from_state, set()):
            if completion_score >= 0.50:
                return False, (
                    f"regression_blocked: completion_score={completion_score:.2f} >= 0.50 "
                    f"— regression not warranted from {from_state}"
                )
            return True, ""

        return False, f"transition_not_defined: {from_state} → {to_state} is not in allowed map"

    # ------------------------------------------------------------------
    # Next Allowed States
    # ------------------------------------------------------------------

    def _compute_next_states(self, current_state: str) -> List[str]:
        """Return list of next allowed states from current state."""
        forward = list(ALLOWED_FORWARD.get(current_state, set()))
        regression = list(ALLOWED_REGRESSION.get(current_state, set()))
        universal = list(UNIVERSAL_TRANSITIONS - {current_state})
        return sorted(set(forward + regression + universal))

    # ------------------------------------------------------------------
    # Gate Evaluation
    # ------------------------------------------------------------------

    def _evaluate_progression_gate(
        self, state: str, completion_score: float, profile: Dict[str, Any]
    ) -> str:
        """
        Determine whether the progression gate is open, closed, or pending.
        Gate is open if completion_score ≥ state-specific threshold.
        """
        gate_thresholds = {
            RehabState.AWAITING_CONSULTATION: 0.30,
            RehabState.CONSULTATION_ACTIVE:   0.40,
            RehabState.AWAITING_ANALYSIS:     0.45,
            RehabState.ANALYSIS_REVIEW:       0.50,
            RehabState.TREATMENT_PLANNING:    0.55,
            RehabState.TREATMENT_ACTIVE:      0.60,
            RehabState.MONITORING:            0.65,
            RehabState.FOLLOW_UP:             0.65,
            RehabState.MAINTENANCE:           0.70,
            RehabState.COMPLETED:             1.00,
        }
        threshold = gate_thresholds.get(state)
        if threshold is None:
            return "pending"
        return "open" if completion_score >= threshold else "closed"

    def _evaluate_escalation_gate(
        self,
        state:              str,
        stall_detected:     bool,
        transition_blocked: bool,
        trajectory_result:  Dict[str, Any],
    ) -> str:
        """
        Determine whether the escalation gate is flagged.
        Flagged = human review recommended (not a send trigger).
        """
        escalation_states = {
            RehabState.STALLED,
            RehabState.LOST_TO_FOLLOW_UP,
        }
        traj_state = (trajectory_result.get("trajectory_state") or "").lower()
        traj_esc   = trajectory_result.get("escalation_hint", False)

        if state in escalation_states:
            return "active"
        if stall_detected or transition_blocked or traj_esc:
            return "flagged"
        if "disengagement" in traj_state or "degrading" in traj_state:
            return "flagged"
        return "clear"

    # ------------------------------------------------------------------
    # Notes Builder
    # ------------------------------------------------------------------

    def _build_notes(
        self,
        state:         str,
        stage:         str,
        score:         float,
        stall:         bool,
        stall_days:    int,
        prog_gate:     str,
        esc_gate:      str,
    ) -> Dict[str, Any]:
        return {
            "phase":                "3.9",
            "engine":               "RehabilitationStateMachine",
            "state":                state,
            "stage":                stage,
            "completion_score":     round(score, 4),
            "stall_detected":       stall,
            "stall_days":           stall_days,
            "progression_gate":     prog_gate,
            "escalation_gate":      esc_gate,
            "safety":               "no_outbound_action",
        }

    # ------------------------------------------------------------------
    # DB Persistence
    # ------------------------------------------------------------------

    async def _persist_result(
        self,
        user_id:          int,
        state:            str,
        stage:            str,
        previous_state:   str,
        next_states:      List[str],
        blocked_reason:   str,
        completion_score: float,
        stall_detected:   bool,
        prog_gate:        str,
        esc_gate:         str,
        notes:            Dict[str, Any],
    ) -> None:
        """Persist state machine result to DB. Non-fatal on error."""
        try:
            from db_pool import get_db_pool
            pool = get_db_pool()
            if not pool:
                return
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE pm_client_profiles SET
                        rehabilitation_state          = $2,
                        rehabilitation_stage          = $3,
                        previous_rehabilitation_state = $4,
                        next_allowed_states           = $5,
                        blocked_transition_reason     = $6,
                        stage_completion_score        = $7,
                        stage_stall_detected          = $8,
                        progression_gate_status       = $9,
                        escalation_gate_status        = $10,
                        last_state_transition_at      = NOW(),
                        state_machine_notes           = $11::jsonb
                    WHERE user_id = $1
                """,
                user_id,
                state,
                stage,
                previous_state,
                next_states,
                blocked_reason,
                round(completion_score, 4),
                stall_detected,
                prog_gate,
                esc_gate,
                json.dumps(notes),
                )
        except Exception as e:
            log.debug("[STATE_MACHINE] DB persist skipped (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

    def _neutral_result(self, user_id: int, error_message: str = "") -> StateMachineResult:
        """Safe neutral result on any engine error."""
        return StateMachineResult(
            user_id=user_id,
            rehabilitation_state=RehabState.UNKNOWN,
            rehabilitation_stage=RehabStage.UNKNOWN,
            progression_gate_status="pending",
            escalation_gate_status="clear",
            state_machine_notes={"fallback": True, "error": error_message},
            evaluated_at=datetime.now(timezone.utc),
            error_message=error_message,
            is_neutral_fallback=True,
        )

    def _governance_override(
        self, user_id: int, reason: str, note: str
    ) -> StateMachineResult:
        """Neutral result when a governance rule overrides state evaluation."""
        return StateMachineResult(
            user_id=user_id,
            rehabilitation_state=RehabState.UNKNOWN,
            rehabilitation_stage=RehabStage.UNKNOWN,
            progression_gate_status="pending",
            escalation_gate_status="clear",
            state_machine_notes={"governance_override": reason, "note": note},
            evaluated_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_state_machine: Optional[RehabilitationStateMachine] = None


def get_state_machine() -> Optional[RehabilitationStateMachine]:
    """Return singleton instance (None if not yet initialized)."""
    return _state_machine


async def init_state_machine() -> RehabilitationStateMachine:
    """
    Idempotent singleton initializer.
    Fails safely — any error is logged as WARNING, never crashes the pipeline.
    """
    global _state_machine
    if _state_machine is not None:
        return _state_machine
    sm = RehabilitationStateMachine()
    await sm.initialize()
    _state_machine = sm
    return _state_machine

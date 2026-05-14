# -*- coding: utf-8 -*-
# =============================================================================
# TRAJECTORY INTELLIGENCE ENGINE — Phase 3.8
# =============================================================================
# Purpose  : Analyse directional patterns over time for long-term rehabilitation
#            journey tracking.  This is NOT diagnosis, NOT medical advice, NOT
#            chatbot logic.  The engine produces internal intelligence only.
#
# IMMUTABLE CONSTRAINT:
#   This module MUST NEVER produce recommendations that:
#   - Send messages directly to users
#   - Bypass human escalation
#   - Bypass silence respect
#   - Bypass recovery policy
#   - Create medical diagnoses or recommendations
#   - Create fear, pressure, or urgency
#   - Override the Central Orchestrator as final authority
#
# Override hierarchy (highest → lowest):
#   human_escalation > silence_respect > recovery_policy >
#   emotional_safety > continuity_logic > trajectory_intelligence
#
# Integration : Runs as Task 5.7 in the fire-and-forget chain,
#               AFTER continuity_task and BEFORE dispatcher_task.
#               Enriches dispatcher context — never calls dispatcher directly.
# =============================================================================

from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trajectory States
# ---------------------------------------------------------------------------

class TrajectoryState(str, Enum):
    ACCELERATING_PROGRESSION  = "accelerating_progression"
    STEADY_PROGRESSION        = "steady_progression"
    STABLE_PLATEAU            = "stable_plateau"
    OSCILLATING_ACTIVE        = "oscillating_active"
    OSCILLATING_AT_RISK       = "oscillating_at_risk"
    PACING_TOO_FAST           = "pacing_too_fast"
    PACING_TOO_SLOW           = "pacing_too_slow"
    FOLLOW_THROUGH_GAP        = "follow_through_gap"
    COHERENCE_BREAK           = "coherence_break"
    DEGRADING                 = "degrading"
    DISENGAGEMENT_TRAJECTORY  = "disengagement_trajectory"
    NEEDS_TRAJECTORY_REVIEW   = "needs_trajectory_review"


# ---------------------------------------------------------------------------
# Trajectory Actions (internal flags for dispatcher enrichment only)
# ---------------------------------------------------------------------------

class TrajectoryAction(str, Enum):
    NO_ACTION                 = "no_action"
    FLAG_COHERENCE_BREAK      = "flag_coherence_break"
    FLAG_DISENGAGEMENT        = "flag_disengagement"
    FLAG_FOLLOW_THROUGH_GAP   = "flag_follow_through_gap"
    FLAG_PACING_ISSUE         = "flag_pacing_issue"
    FLAG_OSCILLATION_RISK     = "flag_oscillation_risk"
    FLAG_DEGRADATION          = "flag_degradation"
    SUGGEST_CONTINUITY_CHECK  = "suggest_continuity_check"
    SUGGEST_HUMAN_REVIEW      = "suggest_human_review"
    NEUTRAL_FALLBACK          = "neutral_fallback"


# ---------------------------------------------------------------------------
# Trajectory Dimension Scores
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryDimensions:
    """Individual dimension scores (0.0–1.0). Higher = healthier signal."""
    stabilization:            float = 0.5   # consistency over weeks
    degradation_resistance:   float = 0.5   # 1.0 = no degradation, 0.0 = severe
    oscillation_resistance:   float = 0.5   # 1.0 = stable, 0.0 = high oscillation
    coherence:                float = 0.5   # logical step-sequence alignment
    follow_through:           float = 0.5   # completion of started cycles
    pacing:                   float = 0.5   # 0.5 = appropriate, deviates both ways
    progression_readiness:    float = 0.5   # signals of next-stage readiness
    disengagement_resistance: float = 0.5   # 1.0 = engaged, 0.0 = drifting


# ---------------------------------------------------------------------------
# Result Dataclass
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryResult:
    """
    Output of evaluate_trajectory().
    Read-only intelligence for dispatcher enrichment.
    NEVER triggers outbound messages directly.
    """
    user_id:                  int
    trajectory_state:         str   = TrajectoryState.NEEDS_TRAJECTORY_REVIEW
    trajectory_score:         float = 0.5
    trajectory_direction:     str   = "unknown"   # improving / stable / declining / unknown
    stabilization_score:      float = 0.5
    degradation_score:        float = 0.5
    oscillation_score:        float = 0.5
    coherence_score:          float = 0.5
    follow_through_score:     float = 0.5
    pacing_score:             float = 0.5
    progression_readiness_score: float = 0.5
    disengagement_score:      float = 0.5
    trajectory_gap_detected:  bool  = False
    recommended_action:       str   = TrajectoryAction.NO_ACTION
    escalation_hint:          bool  = False
    trajectory_notes:         Dict[str, Any] = field(default_factory=dict)
    evaluated_at:             Optional[datetime] = None
    error_message:            Optional[str] = None
    is_neutral_fallback:      bool  = False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class TrajectoryIntelligenceEngine:
    """
    Phase 3.8 — Trajectory Intelligence Engine.

    Analyses directional patterns over time across 8 dimensions:
      stabilization, degradation, oscillation, coherence,
      follow_through, pacing, progression_readiness, disengagement.

    NEVER diagnoses, prescribes, sends messages, or bypasses governance.
    """

    # Dimension weights for composite score
    _WEIGHTS = {
        "stabilization":            0.20,
        "degradation_resistance":   0.15,
        "oscillation_resistance":   0.10,
        "coherence":                0.15,
        "follow_through":           0.20,
        "pacing":                   0.05,
        "progression_readiness":    0.10,
        "disengagement_resistance": 0.05,
    }

    # Score thresholds
    _SCORE_DISENGAGEMENT    = 0.20
    _SCORE_DEGRADING        = 0.40
    _SCORE_OSCILLATING      = 0.60
    _SCORE_STEADY           = 0.80
    _SCORE_ACCELERATING     = 1.00

    # Minimum history window to produce meaningful trajectory
    _MIN_DAYS_HISTORY       = 7

    def __init__(self) -> None:
        self._initialized = False
        log.info("[TRAJECTORY] TrajectoryIntelligenceEngine singleton created")

    async def initialize(self) -> None:
        """Async initialization — connect resources if needed."""
        self._initialized = True
        log.info("[TRAJECTORY] TrajectoryIntelligenceEngine initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate_trajectory(
        self,
        user_id:              int,
        profile:              Optional[Dict[str, Any]] = None,
        message_history:      Optional[list]           = None,
        continuity_result:    Optional[Dict[str, Any]] = None,
        risk_result:          Optional[Dict[str, Any]] = None,
        behaviour_result:     Optional[Dict[str, Any]] = None,
        silence_respected:    bool                     = False,
        human_escalation:     bool                     = False,
        recovery_policy_active: bool                   = False,
    ) -> TrajectoryResult:
        """
        Core evaluation method.

        IMMUTABLE CONSTRAINT:
            This method MUST NEVER produce recommendations that:
            - Send messages directly to users
            - Bypass human escalation
            - Bypass silence respect
            - Bypass recovery policy
            - Create medical diagnoses or recommendations
            - Create fear, pressure, or urgency
            - Override the Central Orchestrator as final authority

        Returns a TrajectoryResult with internal intelligence only.
        On any exception, returns _neutral_result() — never crashes the pipeline.
        """
        try:
            # 1. Governance override checks
            if human_escalation:
                return self._governance_override_result(
                    user_id, "human_escalation_active",
                    "Human escalation active — trajectory evaluation skipped"
                )

            if silence_respected:
                return self._governance_override_result(
                    user_id, "silence_respect_active",
                    "Silence respect active — trajectory evaluation skipped"
                )

            if recovery_policy_active:
                return self._governance_override_result(
                    user_id, "recovery_policy_active",
                    "Recovery policy active — trajectory evaluation skipped"
                )

            # 2. Check minimum data sufficiency
            profile = profile or {}
            first_seen = profile.get("created_at") or profile.get("first_message_at")
            if not self._has_sufficient_history(first_seen):
                return self._insufficient_history_result(user_id)

            # 3. Compute dimension scores
            dims = self._compute_dimensions(
                user_id, profile, message_history or [],
                continuity_result or {}, risk_result or {}, behaviour_result or {}
            )

            # 4. Compute composite trajectory score
            score = self._compute_composite_score(dims)

            # 5. Classify state
            state, direction = self._classify_state(score, dims)

            # 6. Detect gaps and flags
            gap_detected = self._detect_trajectory_gap(dims, state)
            escalation_hint = self._should_hint_escalation(state, dims)
            action = self._recommend_action(state, dims, escalation_hint)

            # 7. Build notes
            notes = self._build_notes(dims, state, score, gap_detected)

            # 8. Persist to DB (fire-and-forget, non-fatal)
            asyncio.create_task(self._persist_result(
                user_id, state, score, direction, dims, gap_detected, notes
            ))

            if gap_detected:
                log.info("[TRAJECTORY] Trajectory gap detected: user_id=%s state=%s score=%.2f",
                         user_id, state, score)
            if escalation_hint:
                log.info("[TRAJECTORY] Escalation hint generated: user_id=%s state=%s",
                         user_id, state)
            if state == TrajectoryState.DISENGAGEMENT_TRAJECTORY:
                log.info("[TRAJECTORY] Disengagement trajectory detected: user_id=%s score=%.2f",
                         user_id, score)

            log.info("[TRAJECTORY] Trajectory evaluation complete: user_id=%s state=%s score=%.2f direction=%s",
                     user_id, state, score, direction)

            return TrajectoryResult(
                user_id=user_id,
                trajectory_state=state,
                trajectory_score=round(score, 4),
                trajectory_direction=direction,
                stabilization_score=round(dims.stabilization, 4),
                degradation_score=round(dims.degradation_resistance, 4),
                oscillation_score=round(dims.oscillation_resistance, 4),
                coherence_score=round(dims.coherence, 4),
                follow_through_score=round(dims.follow_through, 4),
                pacing_score=round(dims.pacing, 4),
                progression_readiness_score=round(dims.progression_readiness, 4),
                disengagement_score=round(dims.disengagement_resistance, 4),
                trajectory_gap_detected=gap_detected,
                recommended_action=action,
                escalation_hint=escalation_hint,
                trajectory_notes=notes,
                evaluated_at=datetime.now(timezone.utc),
            )

        except Exception as exc:
            log.warning("[TRAJECTORY] Safe fallback activated: user_id=%s error=%s",
                        user_id, exc)
            return self._neutral_result(user_id, str(exc))

    # ------------------------------------------------------------------
    # Dimension Computation
    # ------------------------------------------------------------------

    def _compute_dimensions(
        self,
        user_id:           int,
        profile:           Dict[str, Any],
        message_history:   list,
        continuity_result: Dict[str, Any],
        risk_result:       Dict[str, Any],
        behaviour_result:  Dict[str, Any],
    ) -> TrajectoryDimensions:
        """Compute all 8 trajectory dimensions from available signals."""
        dims = TrajectoryDimensions()

        # --- Stabilization: consistency in engagement over time ---
        silent_count    = profile.get("silent_scan_count", 0) or 0
        risk_score      = float(risk_result.get("risk_score", 0.5) or 0.5)
        behaviour_score = float(behaviour_result.get("behaviour_score", 0.5) or 0.5)
        dims.stabilization = self._clamp(0.8 - (silent_count * 0.08) + (behaviour_score * 0.2))

        # --- Degradation resistance: higher = less degradation ---
        behaviour_label = (behaviour_result.get("behaviour_label") or "").lower()
        continuity_score = float(continuity_result.get("continuity_score", 0.5) or 0.5)
        degradation_penalty = 0.0
        if "degrading" in behaviour_label:
            degradation_penalty += 0.3
        if risk_score > 0.7:
            degradation_penalty += 0.2
        if continuity_score < 0.4:
            degradation_penalty += 0.2
        dims.degradation_resistance = self._clamp(0.8 - degradation_penalty)

        # --- Oscillation resistance: stable = high, oscillating = low ---
        unresolved_loop = continuity_result.get("unresolved_continuity_loop", False)
        gap_detected    = continuity_result.get("continuity_gap_detected", False)
        osc_penalty     = 0.0
        if unresolved_loop:
            osc_penalty += 0.3
        if gap_detected:
            osc_penalty += 0.2
        if silent_count > 3:
            osc_penalty += 0.15
        dims.oscillation_resistance = self._clamp(0.8 - osc_penalty)

        # --- Coherence: are actions logically sequential ---
        continuity_state = (continuity_result.get("continuity_state") or "").lower()
        coherence_penalty = 0.0
        if "unresolved_loop" in continuity_state:
            coherence_penalty += 0.25
        if "coherence_break" in continuity_state or "data_collection_incomplete" in continuity_state:
            coherence_penalty += 0.2
        if unresolved_loop:
            coherence_penalty += 0.15
        dims.coherence = self._clamp(0.8 - coherence_penalty)

        # --- Follow-through: completion of initiated cycles ---
        follow_through_missing = "follow_up_missing" in continuity_state
        analysis_pending       = "analysis_pending" in continuity_state
        ft_penalty             = 0.0
        if follow_through_missing:
            ft_penalty += 0.3
        if analysis_pending:
            ft_penalty += 0.15
        if unresolved_loop:
            ft_penalty += 0.2
        dims.follow_through = self._clamp(0.8 - ft_penalty)

        # --- Pacing: 0.5 is ideal, deviates both directions ---
        transition_pending = "transition_pending" in continuity_state
        transition_fragile = "transition_fragile" in continuity_state
        waiting_stability  = (continuity_result.get("waiting_stability") or "").lower()
        pacing_deviation   = 0.0
        if transition_fragile:
            pacing_deviation += 0.25
        if transition_pending and waiting_stability in ("unclear", "unstable"):
            pacing_deviation += 0.15
        dims.pacing = self._clamp(0.8 - pacing_deviation)

        # --- Progression readiness ---
        stable_states = ("stable_progression", "waiting_stable", "support_cycle_active")
        readiness_bonus = 0.0
        for s in stable_states:
            if s in continuity_state:
                readiness_bonus += 0.15
                break
        dims.progression_readiness = self._clamp(behaviour_score * 0.5 + readiness_bonus + 0.2)

        # --- Disengagement resistance ---
        dormant = "dormant" in continuity_state
        dis_penalty = (silent_count * 0.07) + (0.2 if dormant else 0.0)
        dims.disengagement_resistance = self._clamp(0.85 - dis_penalty)

        return dims

    # ------------------------------------------------------------------
    # Composite Score
    # ------------------------------------------------------------------

    def _compute_composite_score(self, dims: TrajectoryDimensions) -> float:
        score = (
            dims.stabilization            * self._WEIGHTS["stabilization"] +
            dims.degradation_resistance   * self._WEIGHTS["degradation_resistance"] +
            dims.oscillation_resistance   * self._WEIGHTS["oscillation_resistance"] +
            dims.coherence                * self._WEIGHTS["coherence"] +
            dims.follow_through           * self._WEIGHTS["follow_through"] +
            dims.pacing                   * self._WEIGHTS["pacing"] +
            dims.progression_readiness    * self._WEIGHTS["progression_readiness"] +
            dims.disengagement_resistance * self._WEIGHTS["disengagement_resistance"]
        )
        return self._clamp(score)

    # ------------------------------------------------------------------
    # State Classification
    # ------------------------------------------------------------------

    def _classify_state(
        self, score: float, dims: TrajectoryDimensions
    ) -> tuple[str, str]:
        """Return (TrajectoryState, direction)."""

        # Disengagement — overrides score if disengagement signal is strong
        if dims.disengagement_resistance < 0.25 and score < 0.35:
            return TrajectoryState.DISENGAGEMENT_TRAJECTORY, "declining"

        # Severe degradation
        if score <= self._SCORE_DISENGAGEMENT:
            return TrajectoryState.DEGRADING, "declining"

        # Follow-through gap dominant signal
        if dims.follow_through < 0.3:
            return TrajectoryState.FOLLOW_THROUGH_GAP, "declining"

        # Coherence break
        if dims.coherence < 0.3:
            return TrajectoryState.COHERENCE_BREAK, "declining"

        # Oscillation at risk
        if dims.oscillation_resistance < 0.35 and dims.degradation_resistance < 0.5:
            return TrajectoryState.OSCILLATING_AT_RISK, "declining"

        # Oscillating but active
        if dims.oscillation_resistance < 0.5:
            return TrajectoryState.OSCILLATING_ACTIVE, "stable"

        # Pacing issues
        if dims.pacing < 0.35:
            return TrajectoryState.PACING_TOO_SLOW, "stable"
        if dims.pacing > 0.85:
            return TrajectoryState.PACING_TOO_FAST, "stable"

        # Score-based classification
        if score <= self._SCORE_DEGRADING:
            return TrajectoryState.DEGRADING, "declining"

        if score <= self._SCORE_OSCILLATING:
            return TrajectoryState.STABLE_PLATEAU, "stable"

        if score <= self._SCORE_STEADY:
            return TrajectoryState.STEADY_PROGRESSION, "improving"

        return TrajectoryState.ACCELERATING_PROGRESSION, "improving"

    # ------------------------------------------------------------------
    # Gap Detection
    # ------------------------------------------------------------------

    def _detect_trajectory_gap(
        self, dims: TrajectoryDimensions, state: str
    ) -> bool:
        gap_states = {
            TrajectoryState.FOLLOW_THROUGH_GAP,
            TrajectoryState.COHERENCE_BREAK,
            TrajectoryState.DISENGAGEMENT_TRAJECTORY,
            TrajectoryState.DEGRADING,
            TrajectoryState.OSCILLATING_AT_RISK,
        }
        if state in gap_states:
            return True
        if dims.follow_through < 0.4 and dims.coherence < 0.4:
            return True
        return False

    # ------------------------------------------------------------------
    # Escalation Hint
    # ------------------------------------------------------------------

    def _should_hint_escalation(
        self, state: str, dims: TrajectoryDimensions
    ) -> bool:
        """Flag for human review — never triggers outbound message."""
        escalation_states = {
            TrajectoryState.DISENGAGEMENT_TRAJECTORY,
            TrajectoryState.COHERENCE_BREAK,
            TrajectoryState.DEGRADING,
            TrajectoryState.NEEDS_TRAJECTORY_REVIEW,
        }
        return state in escalation_states

    # ------------------------------------------------------------------
    # Action Recommendation (internal flags only)
    # ------------------------------------------------------------------

    def _recommend_action(
        self, state: str, dims: TrajectoryDimensions, escalation_hint: bool
    ) -> str:
        if escalation_hint:
            return TrajectoryAction.SUGGEST_HUMAN_REVIEW

        action_map = {
            TrajectoryState.FOLLOW_THROUGH_GAP:      TrajectoryAction.FLAG_FOLLOW_THROUGH_GAP,
            TrajectoryState.OSCILLATING_AT_RISK:     TrajectoryAction.FLAG_OSCILLATION_RISK,
            TrajectoryState.DISENGAGEMENT_TRAJECTORY: TrajectoryAction.FLAG_DISENGAGEMENT,
            TrajectoryState.COHERENCE_BREAK:         TrajectoryAction.FLAG_COHERENCE_BREAK,
            TrajectoryState.DEGRADING:               TrajectoryAction.FLAG_DEGRADATION,
            TrajectoryState.PACING_TOO_FAST:         TrajectoryAction.FLAG_PACING_ISSUE,
            TrajectoryState.PACING_TOO_SLOW:         TrajectoryAction.FLAG_PACING_ISSUE,
            TrajectoryState.OSCILLATING_ACTIVE:      TrajectoryAction.SUGGEST_CONTINUITY_CHECK,
        }
        return action_map.get(state, TrajectoryAction.NO_ACTION)

    # ------------------------------------------------------------------
    # Notes Builder
    # ------------------------------------------------------------------

    def _build_notes(
        self, dims: TrajectoryDimensions, state: str, score: float, gap: bool
    ) -> Dict[str, Any]:
        return {
            "phase": "3.8",
            "engine": "TrajectoryIntelligenceEngine",
            "state": state,
            "composite_score": round(score, 4),
            "gap_detected": gap,
            "dimensions": {
                "stabilization":            round(dims.stabilization, 4),
                "degradation_resistance":   round(dims.degradation_resistance, 4),
                "oscillation_resistance":   round(dims.oscillation_resistance, 4),
                "coherence":                round(dims.coherence, 4),
                "follow_through":           round(dims.follow_through, 4),
                "pacing":                   round(dims.pacing, 4),
                "progression_readiness":    round(dims.progression_readiness, 4),
                "disengagement_resistance": round(dims.disengagement_resistance, 4),
            },
            "safety": "no_outbound_action",
        }

    # ------------------------------------------------------------------
    # DB Persistence
    # ------------------------------------------------------------------

    async def _persist_result(
        self,
        user_id:     int,
        state:       str,
        score:       float,
        direction:   str,
        dims:        TrajectoryDimensions,
        gap:         bool,
        notes:       Dict[str, Any],
    ) -> None:
        """Persist trajectory result to DB. Non-fatal on error."""
        try:
            import json
            from db_pool import get_db_pool
            pool = get_db_pool()
            if not pool:
                return
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE pm_client_profiles SET
                        trajectory_state              = $2,
                        trajectory_score              = $3,
                        trajectory_direction          = $4,
                        stabilization_score           = $5,
                        degradation_score             = $6,
                        oscillation_score             = $7,
                        coherence_score               = $8,
                        follow_through_score          = $9,
                        pacing_score                  = $10,
                        progression_readiness_score   = $11,
                        disengagement_score           = $12,
                        trajectory_gap_detected       = $13,
                        last_trajectory_check         = NOW(),
                        trajectory_notes              = $14::jsonb
                    WHERE user_id = $1
                """,
                user_id,
                state,
                round(score, 4),
                direction,
                round(dims.stabilization, 4),
                round(dims.degradation_resistance, 4),
                round(dims.oscillation_resistance, 4),
                round(dims.coherence, 4),
                round(dims.follow_through, 4),
                round(dims.pacing, 4),
                round(dims.progression_readiness, 4),
                round(dims.disengagement_resistance, 4),
                gap,
                json.dumps(notes),
                )
        except Exception as e:
            log.debug("[TRAJECTORY] DB persist skipped (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # History Check
    # ------------------------------------------------------------------

    def _has_sufficient_history(self, first_seen: Any) -> bool:
        """Require at least _MIN_DAYS_HISTORY days of data."""
        if first_seen is None:
            return False
        try:
            if isinstance(first_seen, str):
                first_seen = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            if not isinstance(first_seen, datetime):
                return False
            delta = datetime.now(timezone.utc) - first_seen.replace(tzinfo=timezone.utc)                 if first_seen.tzinfo is None else                 datetime.now(timezone.utc) - first_seen
            return delta.days >= self._MIN_DAYS_HISTORY
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helper: clamp to [0, 1]
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

    # ------------------------------------------------------------------
    # Fallback results
    # ------------------------------------------------------------------

    def _neutral_result(self, user_id: int, error_message: str = "") -> TrajectoryResult:
        """Safe neutral result returned on any engine error."""
        log.warning("[TRAJECTORY] Safe fallback activated: user_id=%s", user_id)
        return TrajectoryResult(
            user_id=user_id,
            trajectory_state=TrajectoryState.NEEDS_TRAJECTORY_REVIEW,
            trajectory_score=0.5,
            trajectory_direction="unknown",
            recommended_action=TrajectoryAction.NEUTRAL_FALLBACK,
            trajectory_notes={"fallback": True, "error": error_message},
            evaluated_at=datetime.now(timezone.utc),
            error_message=error_message,
            is_neutral_fallback=True,
        )

    def _governance_override_result(
        self, user_id: int, reason: str, note: str
    ) -> TrajectoryResult:
        """Neutral result when a governance rule overrides trajectory evaluation."""
        return TrajectoryResult(
            user_id=user_id,
            trajectory_state=TrajectoryState.NEEDS_TRAJECTORY_REVIEW,
            trajectory_score=0.5,
            trajectory_direction="unknown",
            recommended_action=TrajectoryAction.NO_ACTION,
            trajectory_notes={"governance_override": reason, "note": note},
            evaluated_at=datetime.now(timezone.utc),
        )

    def _insufficient_history_result(self, user_id: int) -> TrajectoryResult:
        """Neutral result for new users with < 7 days of data."""
        return TrajectoryResult(
            user_id=user_id,
            trajectory_state=TrajectoryState.NEEDS_TRAJECTORY_REVIEW,
            trajectory_score=0.5,
            trajectory_direction="unknown",
            recommended_action=TrajectoryAction.NO_ACTION,
            trajectory_notes={"reason": "insufficient_history",
                               "min_days": TrajectoryIntelligenceEngine._MIN_DAYS_HISTORY},
            evaluated_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: Optional[TrajectoryIntelligenceEngine] = None


def get_trajectory_engine() -> Optional[TrajectoryIntelligenceEngine]:
    """Return singleton instance (None if not yet initialized)."""
    return _engine


async def init_trajectory_engine() -> TrajectoryIntelligenceEngine:
    """
    Idempotent singleton initializer.
    Fails safely — any error is logged as WARNING, never crashes the pipeline.
    """
    global _engine
    if _engine is not None:
        return _engine
    engine = TrajectoryIntelligenceEngine()
    await engine.initialize()
    _engine = engine
    return _engine

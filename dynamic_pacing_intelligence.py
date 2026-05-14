"""
dynamic_pacing_intelligence.py
Phase 3.11 — Dynamic Pacing Intelligence
Python Method Digital Rehabilitation Center

IMMUTABLE CONSTRAINT:
This module MUST NEVER produce actions that:
- Send messages directly to users
- Call Telegram, SendPulse, or any outbound sender
- Call the dispatcher directly
- Create urgency or pressure
- Accelerate conversion or progression
- Force pacing or rhythm onto the user
- Override state machine rules
- Override trajectory warnings
- Override continuity logic
- Override recovery policy
- Override silence respect
- Override human escalation
- Override the Central Orchestrator as final authority

Core principle:
The system adapts to the sustainable rhythm of the human — not the reverse.

Governance hierarchy (highest to lowest):
human_escalation > silence_respect > recovery_policy > emotional_safety >
continuity_logic > trajectory_intelligence > rehabilitation_state_machine >
multi_stage_orchestration > dynamic_pacing_intelligence

This engine is a PURE ANALYSIS LAYER. It evaluates pacing tolerance, stability,
pressure risk, overload risk, and engagement recovery capacity, then writes a
pacing profile to DB for the dispatcher to read.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

MODULE_TAG = "[PACING]"

# ---------------------------------------------------------------------------
# Pacing states
# ---------------------------------------------------------------------------

class PacingState:
    SUSTAINABLE  = "SUSTAINABLE"
    ACCELERATING = "ACCELERATING"
    DECELERATING = "DECELERATING"
    PAUSED       = "PAUSED"
    OVERLOADED   = "OVERLOADED"
    RECOVERING   = "RECOVERING"
    STALLED      = "STALLED"
    UNKNOWN      = "UNKNOWN"

ALL_PACING_STATES = [
    PacingState.SUSTAINABLE, PacingState.ACCELERATING, PacingState.DECELERATING,
    PacingState.PAUSED, PacingState.OVERLOADED, PacingState.RECOVERING,
    PacingState.STALLED, PacingState.UNKNOWN,
]

# Recommended route speed values
class RouteSpeed:
    NORMAL = "normal"
    SLOW   = "slow"
    HOLD   = "hold"

# Adaptive pause thresholds (days) by rehabilitation state
PAUSE_THRESHOLD_BY_STATE: Dict[str, int] = {
    "INITIAL_CONTACT":       3,
    "NEEDS_ASSESSMENT":      5,
    "AWAITING_CONSULTATION": 14,
    "CONSULTATION_ACTIVE":   7,
    "AWAITING_ANALYSIS":     14,
    "ANALYSIS_REVIEW":       10,
    "TREATMENT_PLANNING":    7,
    "TREATMENT_ACTIVE":      10,
    "MONITORING":            21,
    "FOLLOW_UP":             14,
    "MAINTENANCE":           45,
    "PAUSED":                7,
    "STALLED":               7,
}
DEFAULT_PAUSE_THRESHOLD = 7  # days

# Safe next step delay (hours) lookup table
# Key: (pacing_state, pressure_zone) where zone is 'low'(<0.30), 'mid'(0.30-0.59), 'high'(>=0.60)
SAFE_DELAY_HOURS: Dict[tuple, int] = {
    (PacingState.SUSTAINABLE,  "low"):  0,
    (PacingState.SUSTAINABLE,  "mid"):  24,
    (PacingState.SUSTAINABLE,  "high"): 48,
    (PacingState.ACCELERATING, "low"):  48,
    (PacingState.ACCELERATING, "mid"):  48,
    (PacingState.ACCELERATING, "high"): 72,
    (PacingState.DECELERATING, "low"):  12,
    (PacingState.DECELERATING, "mid"):  48,
    (PacingState.DECELERATING, "high"): 72,
    (PacingState.PAUSED,       "low"):  72,
    (PacingState.PAUSED,       "mid"):  72,
    (PacingState.PAUSED,       "high"): 96,
    (PacingState.RECOVERING,   "low"):  48,
    (PacingState.RECOVERING,   "mid"):  48,
    (PacingState.RECOVERING,   "high"): 72,
    (PacingState.OVERLOADED,   "low"):  96,
    (PacingState.OVERLOADED,   "mid"):  96,
    (PacingState.OVERLOADED,   "high"): 96,
    (PacingState.STALLED,      "low"):  24,
    (PacingState.STALLED,      "mid"):  24,
    (PacingState.STALLED,      "high"): 48,
    (PacingState.UNKNOWN,      "low"):  0,
    (PacingState.UNKNOWN,      "mid"):  0,
    (PacingState.UNKNOWN,      "high"): 0,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PacingResult:
    pacing_state:                  str
    pacing_score:                  float
    pacing_stability_score:        float
    pacing_pressure_risk:          float
    recommended_route_speed:       str
    adaptive_pause_needed:         bool
    pacing_overload_risk:          float
    engagement_recovery_capacity:  float
    progression_sustainability_score: float
    safe_next_step_delay:          int
    pacing_coherence:              float
    pacing_notes:                  Dict[str, Any]
    error_message:                 Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pacing_state":                    self.pacing_state,
            "pacing_score":                    self.pacing_score,
            "pacing_stability_score":          self.pacing_stability_score,
            "pacing_pressure_risk":            self.pacing_pressure_risk,
            "recommended_route_speed":         self.recommended_route_speed,
            "adaptive_pause_needed":           self.adaptive_pause_needed,
            "pacing_overload_risk":            self.pacing_overload_risk,
            "engagement_recovery_capacity":    self.engagement_recovery_capacity,
            "progression_sustainability_score": self.progression_sustainability_score,
            "safe_next_step_delay":            self.safe_next_step_delay,
            "pacing_coherence":                self.pacing_coherence,
            "pacing_notes":                    self.pacing_notes,
            "error_message":                   self.error_message,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DynamicPacingEngine:
    """
    Dynamic Pacing Intelligence Engine — Phase 3.11.

    Evaluates client pacing state, stability, pressure risk, overload risk,
    and engagement recovery capacity. Writes a pacing profile to DB for
    the dispatcher to read.

    This engine NEVER sends messages, calls Telegram, calls the dispatcher,
    or overrides any governance layer above it in the hierarchy.
    """

    _instance: Optional["DynamicPacingEngine"] = None
    _initialized: bool = False
    _lock: asyncio.Lock = None  # type: ignore

    def __init__(self) -> None:
        self._pool = None
        log.info("%s DynamicPacingEngine singleton created", MODULE_TAG)

    # ------------------------------------------------------------------
    # Singleton management
    # ------------------------------------------------------------------

    @classmethod
    async def create(cls) -> "DynamicPacingEngine":
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._init()
                cls._initialized = True
                log.info("%s DynamicPacingEngine initialized", MODULE_TAG)
        return cls._instance

    async def _init(self) -> None:
        """Initialise DB pool connection. Fail-safe."""
        try:
            import asyncpg  # type: ignore
            import os
            dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
            if dsn:
                self._pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
                log.debug("%s DB pool created", MODULE_TAG)
        except Exception as exc:
            log.warning("%s DB pool init failed (non-fatal): %s", MODULE_TAG, exc)
            self._pool = None

    # ------------------------------------------------------------------
    # Neutral result
    # ------------------------------------------------------------------

    def _neutral_result(self, reason: str = "", error_message: Optional[str] = None) -> PacingResult:
        return PacingResult(
            pacing_state=PacingState.UNKNOWN,
            pacing_score=0.0,
            pacing_stability_score=0.0,
            pacing_pressure_risk=0.0,
            recommended_route_speed=RouteSpeed.NORMAL,
            adaptive_pause_needed=False,
            pacing_overload_risk=0.0,
            engagement_recovery_capacity=0.0,
            progression_sustainability_score=0.0,
            safe_next_step_delay=0,
            pacing_coherence=0.0,
            pacing_notes={"neutral_reason": reason},
            error_message=error_message,
        )

    # ------------------------------------------------------------------
    # Pacing stability score
    # ------------------------------------------------------------------

    def _compute_pacing_stability(
        self,
        days_since_last_message: float,
        behaviour_score: float,
        stage_stall_detected: bool,
        trajectory_score: float,
    ) -> float:
        """
        Pacing stability (0.0–1.0): consistency of engagement rhythm.

        recency_score     = max(0, 1.0 - days/30) * 0.30
        frequency_score   (simulated from days pattern)  * 0.25
        behaviour_contrib = behaviour_score * 0.20
        stall_credit      = 0.15 if no stall else 0.0
        trajectory_boost  = trajectory_score * 0.10
        """
        recency_score = max(0.0, 1.0 - (days_since_last_message / 30.0)) * 0.30
        # Frequency variance penalty: longer gaps = higher variance penalty
        variance_penalty = min(days_since_last_message / 14.0, 1.0)
        frequency_score = max(0.0, 1.0 - variance_penalty) * 0.25
        behaviour_contrib = float(behaviour_score) * 0.20
        stall_credit = 0.0 if stage_stall_detected else 0.15
        trajectory_boost = float(trajectory_score) * 0.10
        score = recency_score + frequency_score + behaviour_contrib + stall_credit + trajectory_boost
        return round(min(score, 1.0), 4)

    # ------------------------------------------------------------------
    # Pacing pressure risk
    # ------------------------------------------------------------------

    def _compute_pacing_pressure_risk(
        self,
        route_overload_score: float,
        active_stage_count: int,
        stage_stall_detected: bool,
        escalation_gate: str,
    ) -> float:
        """
        Pacing pressure risk (0.0–1.0).

        overload_signal   = route_overload_score * 0.35
        active_stage_sig  = min(active_stage_count/4, 1.0) * 0.25
        stall_signal      = 1.0 if stall else 0.0 * 0.20
        escalation_signal = 1.0 if active else 0.0 * 0.20
        """
        overload_signal   = float(route_overload_score) * 0.35
        stage_signal      = min(active_stage_count / 4.0, 1.0) * 0.25
        stall_signal      = (1.0 if stage_stall_detected else 0.0) * 0.20
        escalation_signal = (1.0 if escalation_gate == "active" else 0.0) * 0.20
        score = overload_signal + stage_signal + stall_signal + escalation_signal
        return round(min(score, 1.0), 4)

    # ------------------------------------------------------------------
    # Pacing overload risk
    # ------------------------------------------------------------------

    def _compute_pacing_overload_risk(
        self,
        route_overload_score: float,
        active_stage_count: int,
        escalation_gate: str,
    ) -> float:
        """
        Pacing overload risk (0.0–1.0).

        overload_contrib   = route_overload_score * 0.50
        stage_contrib      = min(active_stage_count/4, 1.0) * 0.30
        escalation_contrib = 1.0 if active else 0.0 * 0.20
        """
        overload_contrib   = float(route_overload_score) * 0.50
        stage_contrib      = min(active_stage_count / 4.0, 1.0) * 0.30
        escalation_contrib = (1.0 if escalation_gate == "active" else 0.0) * 0.20
        score = overload_contrib + stage_contrib + escalation_contrib
        return round(min(score, 1.0), 4)

    # ------------------------------------------------------------------
    # Engagement recovery capacity
    # ------------------------------------------------------------------

    def _compute_engagement_recovery(
        self,
        trajectory_score: float,
        behaviour_score: float,
        continuity_score: float,
        stage_completion_score: float,
    ) -> float:
        """
        Engagement recovery capacity (0.0–1.0).

        trajectory_momentum = trajectory_score * 0.35
        behaviour_quality   = behaviour_score  * 0.30
        continuity_strength = continuity_score * 0.20
        stage_completion    = stage_completion_score * 0.15
        """
        trajectory_momentum = float(trajectory_score) * 0.35
        behaviour_quality   = float(behaviour_score)  * 0.30
        continuity_strength = float(continuity_score) * 0.20
        stage_completion    = float(stage_completion_score) * 0.15
        score = trajectory_momentum + behaviour_quality + continuity_strength + stage_completion
        return round(min(score, 1.0), 4)

    # ------------------------------------------------------------------
    # Progression sustainability
    # ------------------------------------------------------------------

    def _compute_progression_sustainability(
        self,
        pacing_stability_score: float,
        engagement_recovery_capacity: float,
        pacing_pressure_risk: float,
    ) -> float:
        """
        Progression sustainability (0.0–1.0).

        stability_contrib   = pacing_stability_score * 0.40
        recovery_contrib    = engagement_recovery_capacity * 0.35
        pressure_inverse    = (1.0 - pacing_pressure_risk) * 0.25
        """
        stability_contrib = pacing_stability_score * 0.40
        recovery_contrib  = engagement_recovery_capacity * 0.35
        pressure_inverse  = (1.0 - pacing_pressure_risk) * 0.25
        score = stability_contrib + recovery_contrib + pressure_inverse
        return round(min(score, 1.0), 4)

    # ------------------------------------------------------------------
    # Pacing score
    # ------------------------------------------------------------------

    def _compute_pacing_score(
        self,
        engagement_recovery_capacity: float,
        pacing_stability_score: float,
        progression_sustainability_score: float,
        pacing_overload_risk: float,
        pacing_pressure_risk: float,
    ) -> float:
        """
        Overall pacing health score (0.0–1.0).

        engagement_signal     = engagement_recovery_capacity * 0.25
        stability_signal      = pacing_stability_score * 0.25
        sustainability_signal = progression_sustainability_score * 0.20
        overload_inverse      = (1.0 - pacing_overload_risk) * 0.20
        pressure_inverse      = (1.0 - pacing_pressure_risk) * 0.10
        """
        eng_signal  = engagement_recovery_capacity    * 0.25
        stab_signal = pacing_stability_score          * 0.25
        sust_signal = progression_sustainability_score * 0.20
        ovl_inverse = (1.0 - pacing_overload_risk)   * 0.20
        prs_inverse = (1.0 - pacing_pressure_risk)   * 0.10
        score = eng_signal + stab_signal + sust_signal + ovl_inverse + prs_inverse
        return round(min(max(score, 0.0), 1.0), 4)

    # ------------------------------------------------------------------
    # Adaptive pause detection
    # ------------------------------------------------------------------

    def _check_adaptive_pause_needed(
        self,
        pacing_pressure_risk: float,
        pacing_overload_risk: float,
        pacing_state: str,
        stage_stall_detected: bool,
        pacing_stability_score: float,
        silence_respected: bool,
        days_since_last_message: float,
        rehab_state: str,
    ) -> bool:
        """Returns True if adaptive pause is needed."""
        if silence_respected:
            return True
        if pacing_pressure_risk >= 0.60:
            return True
        if pacing_overload_risk >= 0.65:
            return True
        if pacing_state == PacingState.OVERLOADED:
            return True
        if stage_stall_detected and pacing_stability_score < 0.40:
            return True
        threshold = PAUSE_THRESHOLD_BY_STATE.get(rehab_state.upper(), DEFAULT_PAUSE_THRESHOLD)
        if days_since_last_message > threshold:
            return True
        return False

    # ------------------------------------------------------------------
    # Pacing state determination
    # ------------------------------------------------------------------

    def _determine_pacing_state(
        self,
        pacing_score: float,
        pacing_overload_risk: float,
        stage_stall_detected: bool,
        days_since_last_message: float,
        rehab_state: str,
        trajectory_score: float,
    ) -> str:
        """Determine pacing state from score and directional signals."""
        if pacing_score >= 0.75:
            return PacingState.SUSTAINABLE
        if pacing_overload_risk >= 0.65:
            return PacingState.OVERLOADED
        if stage_stall_detected:
            if pacing_score < 0.35:
                return PacingState.STALLED
            return PacingState.DECELERATING
        # Check for pause (silence)
        threshold = PAUSE_THRESHOLD_BY_STATE.get(rehab_state.upper(), DEFAULT_PAUSE_THRESHOLD)
        if days_since_last_message > threshold * 2:
            return PacingState.PAUSED
        if pacing_score < 0.35:
            return PacingState.RECOVERING
        if pacing_score < 0.55:
            # Direction from trajectory
            if trajectory_score > 0.65:
                return PacingState.ACCELERATING
            return PacingState.DECELERATING
        # 0.55–0.74
        if trajectory_score > 0.70:
            return PacingState.ACCELERATING
        return PacingState.DECELERATING

    # ------------------------------------------------------------------
    # Route speed
    # ------------------------------------------------------------------

    def _determine_route_speed(self, pacing_state: str, pacing_pressure_risk: float) -> str:
        """Determine recommended_route_speed."""
        if pacing_state in (PacingState.OVERLOADED, PacingState.PAUSED):
            return RouteSpeed.HOLD
        if pacing_state in (PacingState.STALLED, PacingState.RECOVERING):
            return RouteSpeed.SLOW
        if pacing_pressure_risk >= 0.30:
            return RouteSpeed.SLOW
        return RouteSpeed.NORMAL

    # ------------------------------------------------------------------
    # Safe next step delay
    # ------------------------------------------------------------------

    def _compute_safe_delay(self, pacing_state: str, pacing_pressure_risk: float) -> int:
        """Look up safe next step delay in hours."""
        if pacing_pressure_risk < 0.30:
            zone = "low"
        elif pacing_pressure_risk < 0.60:
            zone = "mid"
        else:
            zone = "high"
        return SAFE_DELAY_HOURS.get((pacing_state, zone), 0)

    # ------------------------------------------------------------------
    # Pacing coherence
    # ------------------------------------------------------------------

    def _compute_pacing_coherence(
        self,
        pacing_stability_score: float,
        pacing_pressure_risk: float,
        pacing_overload_risk: float,
        progression_sustainability_score: float,
    ) -> float:
        """
        Coherence (0.0–1.0): alignment between pacing signals.
        coherence = 1.0 - stdev([stability, 1-pressure, 1-overload, sustainability])
        """
        signals = [
            pacing_stability_score,
            1.0 - pacing_pressure_risk,
            1.0 - pacing_overload_risk,
            progression_sustainability_score,
        ]
        try:
            stdev = statistics.stdev(signals)
        except statistics.StatisticsError:
            stdev = 0.0
        coherence = max(0.0, 1.0 - stdev)
        return round(min(coherence, 1.0), 4)

    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    async def _persist_result(self, user_id: str, result: PacingResult) -> None:
        """Write pacing result to pm_client_profiles. Fail-safe."""
        if not self._pool:
            return
        try:
            import json
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE pm_client_profiles SET
                        pacing_state                     = $1,
                        pacing_score                     = $2,
                        pacing_stability_score           = $3,
                        pacing_pressure_risk             = $4,
                        recommended_route_speed          = $5,
                        adaptive_pause_needed            = $6,
                        pacing_overload_risk             = $7,
                        engagement_recovery_capacity     = $8,
                        progression_sustainability_score = $9,
                        safe_next_step_delay             = $10,
                        pacing_notes                     = $11::jsonb,
                        last_pacing_check                = NOW()
                    WHERE user_id = $12
                    """,
                    result.pacing_state,
                    result.pacing_score,
                    result.pacing_stability_score,
                    result.pacing_pressure_risk,
                    result.recommended_route_speed,
                    result.adaptive_pause_needed,
                    result.pacing_overload_risk,
                    result.engagement_recovery_capacity,
                    result.progression_sustainability_score,
                    result.safe_next_step_delay,
                    json.dumps(result.pacing_notes),
                    str(user_id),
                )
        except Exception as exc:
            log.debug("%s DB persist error (non-fatal): %s", MODULE_TAG, exc)

    # ------------------------------------------------------------------
    # Main evaluation entry point
    # ------------------------------------------------------------------

    async def evaluate_pacing(
        self,
        user_id: str,
        *,
        state_machine_result: Optional[Dict[str, Any]] = None,
        trajectory_result: Optional[Dict[str, Any]] = None,
        continuity_result: Optional[Dict[str, Any]] = None,
        behaviour_result: Optional[Dict[str, Any]] = None,
        orchestration_result: Optional[Dict[str, Any]] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        # Governance flags
        human_escalation: bool = False,
        silence_respected: bool = False,
        recovery_policy_active: bool = False,
    ) -> PacingResult:
        """
        Evaluate dynamic pacing for a user.

        Governance hierarchy is respected: if human_escalation, silence_respected,
        or recovery_policy_active is True, returns neutral result immediately.

        Never raises. All exceptions return neutral result with error_message.
        """
        try:
            # ── Governance guards ──────────────────────────────────────────
            if human_escalation:
                return self._neutral_result("governance_guard: human_escalation_active")
            if silence_respected:
                return self._neutral_result("governance_guard: silence_respected_active")
            if recovery_policy_active:
                return self._neutral_result("governance_guard: recovery_policy_active")

            # ── Normalise inputs ───────────────────────────────────────────
            sm_r   = state_machine_result or {}
            traj_r = trajectory_result    or {}
            cont_r = continuity_result    or {}
            beh_r  = behaviour_result     or {}
            orch_r = orchestration_result or {}
            prof_r = profile_data         or {}

            # ── Extract signals ────────────────────────────────────────────
            days_since_last = float(
                prof_r.get("days_since_last_message")
                or prof_r.get("silence_days")
                or 0.0
            )
            behaviour_score = float(beh_r.get("behaviour_score", 0.5))
            trajectory_score = float(traj_r.get("trajectory_score", 0.5))
            continuity_score = float(cont_r.get("continuity_score", 0.5))

            stage_stall_detected = bool(
                sm_r.get("stage_stall_detected")
                or prof_r.get("stage_stall_detected")
                or False
            )
            stage_completion_score = float(
                sm_r.get("stage_completion_score")
                or prof_r.get("stage_completion_score")
                or 0.0
            )
            rehab_state = str(
                sm_r.get("rehabilitation_state")
                or prof_r.get("rehabilitation_state")
                or "UNKNOWN"
            )
            escalation_gate = str(
                sm_r.get("escalation_gate")
                or prof_r.get("escalation_gate_status")
                or "clear"
            )
            route_overload_score = float(
                orch_r.get("route_overload_score")
                or prof_r.get("route_overload_score")
                or 0.0
            )
            active_stage_count = int(
                orch_r.get("active_stage_count")
                or prof_r.get("active_stage_count")
                or 0
            )

            # ── Compute sub-scores ─────────────────────────────────────────
            pacing_stability_score = self._compute_pacing_stability(
                days_since_last, behaviour_score, stage_stall_detected, trajectory_score
            )
            pacing_pressure_risk = self._compute_pacing_pressure_risk(
                route_overload_score, active_stage_count, stage_stall_detected, escalation_gate
            )
            pacing_overload_risk = self._compute_pacing_overload_risk(
                route_overload_score, active_stage_count, escalation_gate
            )
            engagement_recovery_capacity = self._compute_engagement_recovery(
                trajectory_score, behaviour_score, continuity_score, stage_completion_score
            )
            progression_sustainability_score = self._compute_progression_sustainability(
                pacing_stability_score, engagement_recovery_capacity, pacing_pressure_risk
            )
            pacing_score = self._compute_pacing_score(
                engagement_recovery_capacity, pacing_stability_score,
                progression_sustainability_score, pacing_overload_risk, pacing_pressure_risk
            )

            # ── Determine pacing state ─────────────────────────────────────
            pacing_state = self._determine_pacing_state(
                pacing_score, pacing_overload_risk, stage_stall_detected,
                days_since_last, rehab_state, trajectory_score
            )

            # ── Adaptive pause ─────────────────────────────────────────────
            adaptive_pause_needed = self._check_adaptive_pause_needed(
                pacing_pressure_risk, pacing_overload_risk, pacing_state,
                stage_stall_detected, pacing_stability_score, silence_respected,
                days_since_last, rehab_state
            )

            # ── Route speed ────────────────────────────────────────────────
            recommended_route_speed = self._determine_route_speed(pacing_state, pacing_pressure_risk)

            # ── Safe delay ─────────────────────────────────────────────────
            safe_next_step_delay = self._compute_safe_delay(pacing_state, pacing_pressure_risk)

            # ── Pacing coherence ───────────────────────────────────────────
            pacing_coherence = self._compute_pacing_coherence(
                pacing_stability_score, pacing_pressure_risk,
                pacing_overload_risk, progression_sustainability_score
            )

            # ── Build notes ────────────────────────────────────────────────
            notes = {
                "evaluated_at":                    datetime.now(timezone.utc).isoformat(),
                "rehab_state":                     rehab_state,
                "days_since_last_message":         days_since_last,
                "behaviour_score":                 behaviour_score,
                "trajectory_score":                trajectory_score,
                "continuity_score":                continuity_score,
                "stage_stall_detected":            stage_stall_detected,
                "stage_completion_score":          stage_completion_score,
                "escalation_gate":                 escalation_gate,
                "route_overload_score":            route_overload_score,
                "active_stage_count":              active_stage_count,
                "pacing_stability_score":          pacing_stability_score,
                "pacing_pressure_risk":            pacing_pressure_risk,
                "pacing_overload_risk":            pacing_overload_risk,
                "engagement_recovery_capacity":    engagement_recovery_capacity,
                "progression_sustainability_score": progression_sustainability_score,
                "pacing_score":                    pacing_score,
                "pacing_state":                    pacing_state,
                "adaptive_pause_needed":           adaptive_pause_needed,
                "recommended_route_speed":         recommended_route_speed,
                "safe_next_step_delay":            safe_next_step_delay,
                "pacing_coherence":                pacing_coherence,
            }

            result = PacingResult(
                pacing_state=pacing_state,
                pacing_score=pacing_score,
                pacing_stability_score=pacing_stability_score,
                pacing_pressure_risk=pacing_pressure_risk,
                recommended_route_speed=recommended_route_speed,
                adaptive_pause_needed=adaptive_pause_needed,
                pacing_overload_risk=pacing_overload_risk,
                engagement_recovery_capacity=engagement_recovery_capacity,
                progression_sustainability_score=progression_sustainability_score,
                safe_next_step_delay=safe_next_step_delay,
                pacing_coherence=pacing_coherence,
                pacing_notes=notes,
            )

            # ── Persist to DB ──────────────────────────────────────────────
            await self._persist_result(user_id, result)

            log.debug(
                "%s user=%s state=%s score=%.2f pressure=%.2f delay=%dh speed=%s",
                MODULE_TAG, user_id, pacing_state, pacing_score,
                pacing_pressure_risk, safe_next_step_delay, recommended_route_speed,
            )

            return result

        except Exception as exc:
            log.warning("%s evaluate_pacing exception (non-fatal): %s", MODULE_TAG, exc)
            return self._neutral_result("exception", error_message=str(exc))

    # ------------------------------------------------------------------
    # Dashboard stats
    # ------------------------------------------------------------------

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Return pacing stats for dashboard. Fail-safe."""
        if not self._pool:
            return {"status": "no_db"}
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE pacing_state = 'SUSTAINABLE')  AS sustainable_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'ACCELERATING') AS accelerating_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'DECELERATING') AS decelerating_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'PAUSED')       AS paused_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'OVERLOADED')   AS overloaded_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'RECOVERING')   AS recovering_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'STALLED')      AS stalled_count,
                        COUNT(*) FILTER (WHERE pacing_state = 'UNKNOWN')      AS unknown_count,
                        COUNT(*) FILTER (WHERE adaptive_pause_needed = TRUE)  AS pause_needed_count,
                        COUNT(*) FILTER (WHERE pacing_overload_risk >= 0.65)  AS high_overload_count,
                        COUNT(*) FILTER (WHERE pacing_pressure_risk >= 0.60)  AS high_pressure_count,
                        AVG(pacing_score) FILTER (WHERE pacing_score > 0)     AS avg_pacing_score,
                        AVG(safe_next_step_delay) FILTER (WHERE safe_next_step_delay > 0) AS avg_delay,
                        COUNT(*) FILTER (WHERE last_pacing_check IS NOT NULL) AS evaluated_count
                    FROM pm_client_profiles
                """)
                if not row:
                    return {}
                return {
                    "status": "ok",
                    "pacing_states": {
                        "sustainable":  int(row["sustainable_count"] or 0),
                        "accelerating": int(row["accelerating_count"] or 0),
                        "decelerating": int(row["decelerating_count"] or 0),
                        "paused":       int(row["paused_count"] or 0),
                        "overloaded":   int(row["overloaded_count"] or 0),
                        "recovering":   int(row["recovering_count"] or 0),
                        "stalled":      int(row["stalled_count"] or 0),
                        "unknown":      int(row["unknown_count"] or 0),
                    },
                    "pause_needed_count":  int(row["pause_needed_count"] or 0),
                    "high_overload_count": int(row["high_overload_count"] or 0),
                    "high_pressure_count": int(row["high_pressure_count"] or 0),
                    "avg_pacing_score":    float(row["avg_pacing_score"] or 0.0),
                    "avg_delay_hours":     float(row["avg_delay"] or 0.0),
                    "evaluated_count":     int(row["evaluated_count"] or 0),
                }
        except Exception as exc:
            log.warning("%s get_dashboard_stats error: %s", MODULE_TAG, exc)
            return {}


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_engine_instance: Optional[DynamicPacingEngine] = None
_engine_lock: Optional[asyncio.Lock] = None


async def init_pacing_engine() -> DynamicPacingEngine:
    """Idempotent singleton initialiser. Safe to call multiple times."""
    global _engine_instance, _engine_lock
    if _engine_lock is None:
        _engine_lock = asyncio.Lock()
    async with _engine_lock:
        if _engine_instance is None:
            _engine_instance = await DynamicPacingEngine.create()
    return _engine_instance


def get_pacing_engine() -> Optional[DynamicPacingEngine]:
    """Return singleton if initialised, else None."""
    return _engine_instance

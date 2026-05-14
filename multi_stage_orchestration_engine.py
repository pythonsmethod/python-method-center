"""
multi_stage_orchestration_engine.py
Phase 3.10 — Multi-Stage Orchestration Engine
Python Method Digital Rehabilitation Center

IMMUTABLE CONSTRAINT:
This module MUST NEVER produce actions that:
- Send messages directly to users
- Call Telegram, SendPulse, or any outbound sender
- Call the dispatcher directly
- Override state machine rules or transitions
- Override trajectory warnings
- Override continuity logic
- Override recovery policy
- Make medical conclusions or diagnoses
- Prescribe treatment
- Create urgency or pressure
- Override human escalation
- Override silence respect
- Override the Central Orchestrator as final authority

Governance hierarchy (highest to lowest):
human_escalation > silence_respect > recovery_policy > emotional_safety >
continuity_logic > trajectory_intelligence > rehabilitation_state_machine >
multi_stage_orchestration

This engine is a PURE ANALYSIS LAYER. It evaluates active stage priority,
detects route conflicts, computes overload scores, and determines the single
safe next step. All results are written to DB for downstream consumption only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODULE_TAG = "[ORCHESTRATION]"

# Orchestration states
class OrchestrationState:
    CLEAR              = "CLEAR"
    MULTI_ACTIVE       = "MULTI_ACTIVE"
    CONFLICT           = "CONFLICT"
    OVERLOADED         = "OVERLOADED"
    HANDOFF_READY      = "HANDOFF_READY"
    BLOCKED            = "BLOCKED"
    ESCALATION_NEEDED  = "ESCALATION_NEEDED"
    UNKNOWN            = "UNKNOWN"

ALL_ORCHESTRATION_STATES = [
    OrchestrationState.CLEAR,
    OrchestrationState.MULTI_ACTIVE,
    OrchestrationState.CONFLICT,
    OrchestrationState.OVERLOADED,
    OrchestrationState.HANDOFF_READY,
    OrchestrationState.BLOCKED,
    OrchestrationState.ESCALATION_NEEDED,
    OrchestrationState.UNKNOWN,
]

# Stage priority weights (higher = more urgent)
STAGE_PRIORITY_WEIGHTS: Dict[str, float] = {
    "intake":       1.0,
    "diagnostic":   0.9,
    "intervention": 0.8,
    "continuity":   0.6,
}

# Orchestration action values
class OrchestrationAction:
    PROCEED_PRIMARY       = "proceed_primary_stage"
    WAIT_SECONDARY        = "wait_secondary_stages"
    AWAIT_CONFLICT        = "await_conflict_resolution"
    TRIGGER_HANDOFF       = "trigger_handoff"
    REDUCE_DEMANDS        = "reduce_active_demands"
    AWAIT_HUMAN           = "await_human_review"
    NO_ACTION             = "no_action_needed"
    NEUTRAL               = "neutral"

# Overload thresholds
OVERLOAD_THRESHOLD_WARN   = 0.30
OVERLOAD_THRESHOLD_ACTIVE = 0.70
OVERLOAD_THRESHOLD_ESCALATE = 1.0

# Handoff completion threshold
HANDOFF_COMPLETION_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class MultiStageOrchestrationResult:
    orchestration_state:    str
    current_primary_stage:  Optional[str]
    active_stage_count:     int
    active_stages:          List[str]
    blocked_stages:         List[str]
    waiting_stages:         List[str]
    stage_conflict_detected: bool
    route_overload_score:   float
    next_orchestration_action: str
    handoff_ready:          bool
    orchestration_notes:    Dict[str, Any]
    error_message:          Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orchestration_state":       self.orchestration_state,
            "current_primary_stage":     self.current_primary_stage,
            "active_stage_count":        self.active_stage_count,
            "active_stages":             self.active_stages,
            "blocked_stages":            self.blocked_stages,
            "waiting_stages":            self.waiting_stages,
            "stage_conflict_detected":   self.stage_conflict_detected,
            "route_overload_score":      self.route_overload_score,
            "next_orchestration_action": self.next_orchestration_action,
            "handoff_ready":             self.handoff_ready,
            "orchestration_notes":       self.orchestration_notes,
            "error_message":             self.error_message,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MultiStageOrchestrationEngine:
    """
    Multi-Stage Orchestration Engine — Phase 3.10.

    Determines stage priority, detects conflicts, computes overload scores,
    and identifies the single safe next orchestration action.

    This engine NEVER sends messages, calls Telegram, calls the dispatcher,
    or overrides any governance layer above it in the hierarchy.
    """

    _instance: Optional["MultiStageOrchestrationEngine"] = None
    _initialized: bool = False
    _lock: asyncio.Lock = None  # type: ignore

    def __init__(self) -> None:
        self._pool = None
        log.info("%s MultiStageOrchestrationEngine singleton created", MODULE_TAG)

    # ------------------------------------------------------------------
    # Singleton management
    # ------------------------------------------------------------------

    @classmethod
    async def create(cls) -> "MultiStageOrchestrationEngine":
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._init()
                cls._initialized = True
                log.info("%s MultiStageOrchestrationEngine initialized", MODULE_TAG)
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
    # Neutral result (returned on all exceptions)
    # ------------------------------------------------------------------

    def _neutral_result(self, reason: str = "", error_message: Optional[str] = None) -> MultiStageOrchestrationResult:
        return MultiStageOrchestrationResult(
            orchestration_state=OrchestrationState.UNKNOWN,
            current_primary_stage=None,
            active_stage_count=0,
            active_stages=[],
            blocked_stages=[],
            waiting_stages=[],
            stage_conflict_detected=False,
            route_overload_score=0.0,
            next_orchestration_action=OrchestrationAction.NEUTRAL,
            handoff_ready=False,
            orchestration_notes={"neutral_reason": reason},
            error_message=error_message,
        )

    # ------------------------------------------------------------------
    # Stage classification helpers
    # ------------------------------------------------------------------

    def _extract_stages_from_context(
        self,
        state_machine_result: Dict[str, Any],
        trajectory_result: Dict[str, Any],
        continuity_result: Dict[str, Any],
        behaviour_result: Dict[str, Any],
        profile_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract active/blocked/waiting stage lists from upstream engine results.
        Returns a dict with keys: active, blocked, waiting, rehab_state,
        escalation_gate, progression_gate, stage_completion_score,
        stage_stall_detected, behaviour_score, trajectory_score, continuity_score.
        """
        rehab_state = (
            state_machine_result.get("rehabilitation_state")
            or profile_data.get("rehabilitation_state")
            or "UNKNOWN"
        )
        rehab_stage = (
            state_machine_result.get("rehabilitation_stage")
            or profile_data.get("rehabilitation_stage")
            or ""
        )
        escalation_gate = (
            state_machine_result.get("escalation_gate")
            or profile_data.get("escalation_gate_status")
            or "clear"
        )
        progression_gate = (
            state_machine_result.get("progression_gate")
            or profile_data.get("progression_gate_status")
            or "open"
        )
        stage_completion = float(
            state_machine_result.get("stage_completion_score")
            or profile_data.get("stage_completion_score")
            or 0.0
        )
        stage_stall = bool(
            state_machine_result.get("stage_stall_detected")
            or profile_data.get("stage_stall_detected")
            or False
        )
        behaviour_score = float(behaviour_result.get("behaviour_score", 0.5))
        trajectory_score = float(trajectory_result.get("trajectory_score", 0.5))
        continuity_score = float(continuity_result.get("continuity_score", 0.5))

        # Determine active stages from current rehab state mapping
        state_to_stage = {
            "INITIAL_CONTACT":      "intake",
            "NEEDS_ASSESSMENT":     "intake",
            "AWAITING_CONSULTATION": "diagnostic",
            "CONSULTATION_ACTIVE":  "diagnostic",
            "AWAITING_ANALYSIS":    "diagnostic",
            "ANALYSIS_REVIEW":      "diagnostic",
            "TREATMENT_PLANNING":   "intervention",
            "TREATMENT_ACTIVE":     "intervention",
            "MONITORING":           "continuity",
            "FOLLOW_UP":            "continuity",
            "MAINTENANCE":          "continuity",
            "PAUSED":               None,
            "STALLED":              None,
            "LOST_TO_FOLLOW_UP":    None,
            "COMPLETED":            None,
            "UNKNOWN":              None,
        }

        current_stage = state_to_stage.get(rehab_state.upper()) if rehab_state else None

        # Active stages: current stage if not blocked by gates
        active_stages: List[str] = []
        blocked_stages: List[str] = []

        if current_stage:
            if escalation_gate == "active":
                blocked_stages.append(current_stage)
            elif progression_gate == "closed":
                blocked_stages.append(current_stage)
            else:
                active_stages.append(current_stage)

        # If continuity signals show a different stage is also engaged, add it
        continuity_stage = continuity_result.get("active_stage") or ""
        if continuity_stage and continuity_stage != current_stage and continuity_stage in STAGE_PRIORITY_WEIGHTS:
            if continuity_stage not in active_stages and continuity_stage not in blocked_stages:
                active_stages.append(continuity_stage)

        return {
            "active":             active_stages,
            "blocked":            blocked_stages,
            "rehab_state":        rehab_state,
            "rehab_stage":        rehab_stage,
            "escalation_gate":    escalation_gate,
            "progression_gate":   progression_gate,
            "stage_completion":   stage_completion,
            "stage_stall":        stage_stall,
            "behaviour_score":    behaviour_score,
            "trajectory_score":   trajectory_score,
            "continuity_score":   continuity_score,
        }

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflict(
        self,
        active_stages: List[str],
        blocked_stages: List[str],
        escalation_gate: str,
        rehab_state: str,
        stage_stall: bool,
    ) -> bool:
        """
        Detect route conflict. Returns True if conflict present.

        Conflict rules:
        1. Escalation gate active + any active stage
        2. TREATMENT_ACTIVE state + any pre-treatment stage also active (clinical skip)
        3. blocked_stages and active_stages have intersection
        4. stage_stall + escalation_gate == "active" simultaneously
        """
        if not active_stages and not blocked_stages:
            return False

        # Rule 1: escalation gate active with active stages
        if escalation_gate == "active" and active_stages:
            return True

        # Rule 2: clinical skip conflict
        treatment_states = {"TREATMENT_ACTIVE", "MONITORING"}
        pre_treatment_stages = {"intake", "diagnostic"}
        if rehab_state.upper() in treatment_states:
            for stage in active_stages:
                if stage in pre_treatment_stages:
                    return True

        # Rule 3: intersection of blocked and active
        if set(active_stages) & set(blocked_stages):
            return True

        # Rule 4: stall + escalation active
        if stage_stall and escalation_gate == "active":
            return True

        return False

    # ------------------------------------------------------------------
    # Overload scoring
    # ------------------------------------------------------------------

    def _compute_overload_score(
        self,
        active_stage_count: int,
        stage_conflict_detected: bool,
        escalation_gate: str,
        stage_stall: bool,
    ) -> float:
        """
        Compute route overload score (0.0–1.0).
        active_stage_count_signal * 0.40
        + conflict_signal * 0.25
        + escalation_signal * 0.20
        + stall_signal * 0.15
        """
        count_signal      = min(active_stage_count / 4.0, 1.0) * 0.40
        conflict_signal   = (1.0 if stage_conflict_detected else 0.0) * 0.25
        escalation_signal = (1.0 if escalation_gate == "active" else 0.0) * 0.20
        stall_signal      = (1.0 if stage_stall else 0.0) * 0.15
        score = count_signal + conflict_signal + escalation_signal + stall_signal
        return round(min(score, 1.0), 4)

    # ------------------------------------------------------------------
    # Primary stage determination
    # ------------------------------------------------------------------

    def _determine_primary_stage(self, active_stages: List[str]) -> Optional[str]:
        """Return highest-priority active stage by weight."""
        if not active_stages:
            return None
        return max(active_stages, key=lambda s: STAGE_PRIORITY_WEIGHTS.get(s, 0.0))

    # ------------------------------------------------------------------
    # Waiting stages
    # ------------------------------------------------------------------

    def _determine_waiting_stages(
        self, active_stages: List[str], primary_stage: Optional[str]
    ) -> List[str]:
        """All active stages except primary are waiting."""
        if not primary_stage:
            return []
        return [s for s in active_stages if s != primary_stage]

    # ------------------------------------------------------------------
    # Handoff readiness
    # ------------------------------------------------------------------

    def _check_handoff_ready(
        self,
        stage_completion: float,
        progression_gate: str,
        escalation_gate: str,
        stage_stall: bool,
        stage_conflict_detected: bool,
        orchestration_state: str,
    ) -> bool:
        """
        Returns True when the primary stage is ready to hand off to next stage.
        All conditions must be met:
        - stage_completion >= 0.85
        - progression_gate == "open"
        - escalation_gate != "active"
        - stage_stall == False
        - no conflict
        - orchestration_state not in CONFLICT, BLOCKED, ESCALATION_NEEDED
        """
        blocking_states = {
            OrchestrationState.CONFLICT,
            OrchestrationState.BLOCKED,
            OrchestrationState.ESCALATION_NEEDED,
        }
        if orchestration_state in blocking_states:
            return False
        return (
            stage_completion >= HANDOFF_COMPLETION_THRESHOLD
            and progression_gate == "open"
            and escalation_gate != "active"
            and not stage_stall
            and not stage_conflict_detected
        )

    # ------------------------------------------------------------------
    # Orchestration state determination
    # ------------------------------------------------------------------

    def _determine_orchestration_state(
        self,
        active_stages: List[str],
        blocked_stages: List[str],
        stage_conflict_detected: bool,
        route_overload_score: float,
        handoff_ready: bool,
        escalation_gate: str,
    ) -> str:
        if stage_conflict_detected and route_overload_score >= OVERLOAD_THRESHOLD_ESCALATE:
            return OrchestrationState.ESCALATION_NEEDED
        if stage_conflict_detected:
            return OrchestrationState.CONFLICT
        if route_overload_score >= OVERLOAD_THRESHOLD_ACTIVE:
            return OrchestrationState.OVERLOADED
        if not active_stages and blocked_stages:
            return OrchestrationState.BLOCKED
        if not active_stages and not blocked_stages:
            return OrchestrationState.CLEAR
        if handoff_ready:
            return OrchestrationState.HANDOFF_READY
        if len(active_stages) > 1:
            return OrchestrationState.MULTI_ACTIVE
        return OrchestrationState.CLEAR

    # ------------------------------------------------------------------
    # Next orchestration action
    # ------------------------------------------------------------------

    def _determine_action(
        self,
        orchestration_state: str,
        route_overload_score: float,
        handoff_ready: bool,
        waiting_stages: List[str],
    ) -> str:
        if orchestration_state == OrchestrationState.ESCALATION_NEEDED:
            return OrchestrationAction.AWAIT_HUMAN
        if orchestration_state == OrchestrationState.CONFLICT:
            return OrchestrationAction.AWAIT_CONFLICT
        if orchestration_state == OrchestrationState.OVERLOADED:
            return OrchestrationAction.REDUCE_DEMANDS
        if orchestration_state == OrchestrationState.BLOCKED:
            return OrchestrationAction.AWAIT_HUMAN
        if orchestration_state == OrchestrationState.HANDOFF_READY:
            return OrchestrationAction.TRIGGER_HANDOFF
        if orchestration_state == OrchestrationState.CLEAR and not waiting_stages:
            return OrchestrationAction.PROCEED_PRIMARY
        if orchestration_state in (OrchestrationState.MULTI_ACTIVE, OrchestrationState.CLEAR):
            if waiting_stages:
                return OrchestrationAction.WAIT_SECONDARY
            return OrchestrationAction.PROCEED_PRIMARY
        if orchestration_state == OrchestrationState.UNKNOWN:
            return OrchestrationAction.NEUTRAL
        return OrchestrationAction.NO_ACTION

    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    async def _persist_result(self, user_id: str, result: MultiStageOrchestrationResult) -> None:
        """Write orchestration result to pm_client_profiles. Fail-safe."""
        if not self._pool:
            return
        try:
            import json
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE pm_client_profiles SET
                        orchestration_state         = $1,
                        current_primary_stage       = $2,
                        active_stage_count          = $3,
                        active_stages               = $4::jsonb,
                        blocked_stages              = $5::jsonb,
                        waiting_stages              = $6::jsonb,
                        stage_conflict_detected     = $7,
                        route_overload_score        = $8,
                        next_orchestration_action   = $9,
                        handoff_ready               = $10,
                        orchestration_notes         = $11::jsonb,
                        last_orchestration_check    = NOW()
                    WHERE user_id = $12
                    """,
                    result.orchestration_state,
                    result.current_primary_stage,
                    result.active_stage_count,
                    json.dumps(result.active_stages),
                    json.dumps(result.blocked_stages),
                    json.dumps(result.waiting_stages),
                    result.stage_conflict_detected,
                    result.route_overload_score,
                    result.next_orchestration_action,
                    result.handoff_ready,
                    json.dumps(result.orchestration_notes),
                    str(user_id),
                )
        except Exception as exc:
            log.debug("%s DB persist error (non-fatal): %s", MODULE_TAG, exc)

    # ------------------------------------------------------------------
    # Main evaluation entry point
    # ------------------------------------------------------------------

    async def evaluate_orchestration(
        self,
        user_id: str,
        *,
        state_machine_result: Optional[Dict[str, Any]] = None,
        trajectory_result: Optional[Dict[str, Any]] = None,
        continuity_result: Optional[Dict[str, Any]] = None,
        behaviour_result: Optional[Dict[str, Any]] = None,
        profile_data: Optional[Dict[str, Any]] = None,
        # Governance flags
        human_escalation: bool = False,
        silence_respected: bool = False,
        recovery_policy_active: bool = False,
    ) -> MultiStageOrchestrationResult:
        """
        Evaluate multi-stage orchestration for a user.

        Governance hierarchy is respected: if human_escalation, silence_respected,
        or recovery_policy_active is True, returns neutral result immediately.

        Never raises. All exceptions return neutral result with error_message.
        """
        try:
            # ── Governance guards ─────────────────────────────────────────
            if human_escalation:
                return self._neutral_result("governance_guard: human_escalation_active")
            if silence_respected:
                return self._neutral_result("governance_guard: silence_respected_active")
            if recovery_policy_active:
                return self._neutral_result("governance_guard: recovery_policy_active")

            # ── Normalise inputs ─────────────────────────────────────────
            sm_r   = state_machine_result or {}
            traj_r = trajectory_result    or {}
            cont_r = continuity_result    or {}
            beh_r  = behaviour_result     or {}
            prof_r = profile_data         or {}

            # ── Stage classification ──────────────────────────────────────
            stage_data = self._extract_stages_from_context(sm_r, traj_r, cont_r, beh_r, prof_r)

            active_stages  = stage_data["active"]
            blocked_stages = stage_data["blocked"]
            escalation_gate  = stage_data["escalation_gate"]
            progression_gate = stage_data["progression_gate"]
            stage_completion = stage_data["stage_completion"]
            stage_stall      = stage_data["stage_stall"]
            rehab_state      = stage_data["rehab_state"]

            # ── Conflict detection ────────────────────────────────────────
            stage_conflict_detected = self._detect_conflict(
                active_stages, blocked_stages, escalation_gate, rehab_state, stage_stall
            )

            # ── Overload score ────────────────────────────────────────────
            active_stage_count = len(active_stages)
            route_overload_score = self._compute_overload_score(
                active_stage_count, stage_conflict_detected, escalation_gate, stage_stall
            )

            # ── Primary stage ─────────────────────────────────────────────
            primary_stage = self._determine_primary_stage(active_stages)
            waiting_stages = self._determine_waiting_stages(active_stages, primary_stage)

            # ── Preliminary orchestration state (for handoff check) ───────
            prelim_state = self._determine_orchestration_state(
                active_stages, blocked_stages, stage_conflict_detected,
                route_overload_score, False, escalation_gate
            )

            # ── Handoff readiness ─────────────────────────────────────────
            handoff_ready = self._check_handoff_ready(
                stage_completion, progression_gate, escalation_gate,
                stage_stall, stage_conflict_detected, prelim_state
            )

            # ── Final orchestration state ─────────────────────────────────
            orchestration_state = self._determine_orchestration_state(
                active_stages, blocked_stages, stage_conflict_detected,
                route_overload_score, handoff_ready, escalation_gate
            )

            # ── Next action ───────────────────────────────────────────────
            next_action = self._determine_action(
                orchestration_state, route_overload_score, handoff_ready, waiting_stages
            )

            # ── Build notes ───────────────────────────────────────────────
            notes = {
                "evaluated_at":          datetime.now(timezone.utc).isoformat(),
                "rehab_state":           rehab_state,
                "rehab_stage":           stage_data["rehab_stage"],
                "escalation_gate":       escalation_gate,
                "progression_gate":      progression_gate,
                "stage_completion":      stage_completion,
                "stage_stall":           stage_stall,
                "active_stages":         active_stages,
                "blocked_stages":        blocked_stages,
                "waiting_stages":        waiting_stages,
                "primary_stage":         primary_stage,
                "conflict_detected":     stage_conflict_detected,
                "overload_score":        route_overload_score,
                "handoff_ready":         handoff_ready,
                "orchestration_state":   orchestration_state,
                "next_action":           next_action,
                "behaviour_score":       stage_data["behaviour_score"],
                "trajectory_score":      stage_data["trajectory_score"],
                "continuity_score":      stage_data["continuity_score"],
            }

            result = MultiStageOrchestrationResult(
                orchestration_state=orchestration_state,
                current_primary_stage=primary_stage,
                active_stage_count=active_stage_count,
                active_stages=active_stages,
                blocked_stages=blocked_stages,
                waiting_stages=waiting_stages,
                stage_conflict_detected=stage_conflict_detected,
                route_overload_score=route_overload_score,
                next_orchestration_action=next_action,
                handoff_ready=handoff_ready,
                orchestration_notes=notes,
            )

            # ── Persist to DB ─────────────────────────────────────────────
            await self._persist_result(user_id, result)

            log.debug(
                "%s user=%s state=%s primary=%s overload=%.2f action=%s",
                MODULE_TAG, user_id, orchestration_state,
                primary_stage, route_overload_score, next_action,
            )

            return result

        except Exception as exc:
            log.warning("%s evaluate_orchestration exception (non-fatal): %s", MODULE_TAG, exc)
            return self._neutral_result("exception", error_message=str(exc))

    # ------------------------------------------------------------------
    # Dashboard stats
    # ------------------------------------------------------------------

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Return orchestration stats for dashboard. Fail-safe."""
        if not self._pool:
            return {"status": "no_db"}
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE orchestration_state = 'CLEAR')             AS clear_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'MULTI_ACTIVE')       AS multi_active_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'CONFLICT')           AS conflict_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'OVERLOADED')         AS overloaded_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'HANDOFF_READY')      AS handoff_ready_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'BLOCKED')            AS blocked_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'ESCALATION_NEEDED')  AS escalation_needed_count,
                        COUNT(*) FILTER (WHERE orchestration_state = 'UNKNOWN')            AS unknown_count,
                        COUNT(*) FILTER (WHERE stage_conflict_detected = TRUE)             AS conflict_total,
                        COUNT(*) FILTER (WHERE handoff_ready = TRUE)                       AS handoff_total,
                        COUNT(*) FILTER (WHERE route_overload_score >= 0.70)               AS high_overload_count,
                        AVG(route_overload_score) FILTER (WHERE route_overload_score > 0)  AS avg_overload_score,
                        AVG(active_stage_count) FILTER (WHERE active_stage_count > 0)      AS avg_active_stages,
                        COUNT(*) FILTER (WHERE last_orchestration_check IS NOT NULL)       AS evaluated_count
                    FROM pm_client_profiles
                """)
                if not row:
                    return {}
                return {
                    "status": "ok",
                    "orchestration_states": {
                        "clear":             int(row["clear_count"] or 0),
                        "multi_active":      int(row["multi_active_count"] or 0),
                        "conflict":          int(row["conflict_count"] or 0),
                        "overloaded":        int(row["overloaded_count"] or 0),
                        "handoff_ready":     int(row["handoff_ready_count"] or 0),
                        "blocked":           int(row["blocked_count"] or 0),
                        "escalation_needed": int(row["escalation_needed_count"] or 0),
                        "unknown":           int(row["unknown_count"] or 0),
                    },
                    "conflict_total":     int(row["conflict_total"] or 0),
                    "handoff_total":      int(row["handoff_total"] or 0),
                    "high_overload_count": int(row["high_overload_count"] or 0),
                    "avg_overload_score": float(row["avg_overload_score"] or 0.0),
                    "avg_active_stages":  float(row["avg_active_stages"] or 0.0),
                    "evaluated_count":    int(row["evaluated_count"] or 0),
                }
        except Exception as exc:
            log.warning("%s get_dashboard_stats error: %s", MODULE_TAG, exc)
            return {}


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_engine_instance: Optional[MultiStageOrchestrationEngine] = None
_engine_lock: Optional[asyncio.Lock] = None


async def init_orchestration_engine() -> MultiStageOrchestrationEngine:
    """Idempotent singleton initialiser. Safe to call multiple times."""
    global _engine_instance, _engine_lock
    if _engine_lock is None:
        _engine_lock = asyncio.Lock()
    async with _engine_lock:
        if _engine_instance is None:
            _engine_instance = await MultiStageOrchestrationEngine.create()
    return _engine_instance


def get_orchestration_engine() -> Optional[MultiStageOrchestrationEngine]:
    """Return singleton if initialised, else None."""
    return _engine_instance

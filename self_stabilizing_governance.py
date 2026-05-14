# -*- coding: utf-8 -*-
# self_stabilizing_governance.py
# Phase 3.17 — Self-Stabilizing Governance Engine
# Detects governance drift, overload cascades, coherence degradation,
# pacing pressure, route conflict, and escalation instability.
# Produces safe stabilization signals for dispatcher and orchestrator context.
#
# IMPORTANT: This is NOT autonomous decision-making, NOT medical reasoning,
# NOT treatment planning, NOT outbound messaging, NOT prediction.
# The engine stabilizes governance conditions, not human outcomes.
# Dispatcher remains the only outbound path.

import logging
import asyncio
from datetime import datetime
from typing import Optional

log = logging.getLogger("rehabilitation_self_stabilizing_governance")

# ---------------------------------------------------------------------------
# Governance stability states
# ---------------------------------------------------------------------------
GOVERNANCE_STATES = [
    "STABLE_GOVERNANCE",
    "DRIFT_ACCUMULATING",
    "OVERLOAD_CASCADE_RISK",
    "COHERENCE_DEGRADATION",
    "PACING_PRESSURE",
    "ROUTE_CONFLICT_PRESSURE",
    "ESCALATION_INSTABILITY",
    "STABILIZATION_REQUIRED",
    "UNKNOWN",
]

# Stabilization modes
STABILIZATION_MODES = [
    "no_change",
    "reduce_route_pressure",
    "hold_nonessential_actions",
    "protect_silence",
    "prioritize_recovery_policy",
    "reduce_dispatch_density",
    "escalate_for_human_review",
    "stabilize_route_conflicts",
    "maintain_current_governance",
]

# ---------------------------------------------------------------------------
# DB migration
# ---------------------------------------------------------------------------
_MIGRATION_SQL = """
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS governance_stability_state TEXT DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS governance_drift_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS overload_cascade_risk FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS coherence_degradation_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pacing_pressure_stability FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS route_conflict_stability FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS escalation_stability_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS silence_respect_integrity FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS recovery_policy_integrity FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS dispatcher_safety_alignment FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS stabilization_needed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS recommended_stabilization_mode TEXT DEFAULT 'no_change',
    ADD COLUMN IF NOT EXISTS governance_stabilization_notes JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS last_governance_stabilization_check TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_governance_stability_state
    ON pm_client_profiles(governance_stability_state);
CREATE INDEX IF NOT EXISTS idx_governance_drift_score
    ON pm_client_profiles(governance_drift_score);
CREATE INDEX IF NOT EXISTS idx_stabilization_needed
    ON pm_client_profiles(stabilization_needed);
CREATE INDEX IF NOT EXISTS idx_overload_cascade_risk
    ON pm_client_profiles(overload_cascade_risk);
CREATE INDEX IF NOT EXISTS idx_last_governance_stabilization_check
    ON pm_client_profiles(last_governance_stabilization_check);
"""


# ---------------------------------------------------------------------------
# Neutral result (fail-safe)
# ---------------------------------------------------------------------------
def _neutral_result() -> dict:
    return {
        "governance_stability_state": "UNKNOWN",
        "stabilization_needed": False,
        "governance_drift_score": 0.0,
        "overload_cascade_risk": 0.0,
        "coherence_degradation_score": 0.0,
        "pacing_pressure_stability": 0.0,
        "route_conflict_stability": 0.0,
        "escalation_stability_score": 0.0,
        "silence_respect_integrity": 0.0,
        "recovery_policy_integrity": 0.0,
        "dispatcher_safety_alignment": 0.0,
        "recommended_stabilization_mode": "no_change",
        "stabilization_notes": [],
        "is_neutral": True,
        "evaluated_at": datetime.utcnow().isoformat(),
    }


def _clamp(value: float) -> float:
    """Clamp score to [0.0, 1.0]."""
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Individual evaluators
# ---------------------------------------------------------------------------

def _eval_governance_drift(ctx: dict) -> float:
    """Measure cumulative deviation from governance baseline across layers."""
    try:
        signals = [
            ctx.get("trajectory_stability", 1.0),
            ctx.get("state_machine_coherence", 1.0),
            ctx.get("orchestration_alignment", 1.0),
            ctx.get("longitudinal_drift", 1.0),
            ctx.get("strategy_alignment", 1.0),
        ]
        valid = [_clamp(s) for s in signals if s is not None]
        if not valid:
            return 0.5
        avg = sum(valid) / len(valid)
        return _clamp(1.0 - avg)
    except Exception:
        return 0.5


def _eval_overload_cascade_risk(ctx: dict) -> float:
    """Detect convergence of simultaneous overload signals."""
    try:
        overload_signals = [
            ctx.get("pacing_overload_signal", 0.0),
            ctx.get("load_balancing_overload", 0.0),
            ctx.get("orchestration_queue_pressure", 0.0),
            ctx.get("cognitive_load_score", 0.0),
            ctx.get("dispatch_queue_depth_ratio", 0.0),
        ]
        valid = [_clamp(s) for s in overload_signals if s is not None]
        if not valid:
            return 0.0
        high_count = sum(1 for s in valid if s > 0.6)
        base_risk = sum(valid) / len(valid)
        cascade_multiplier = 1.0 + (high_count * 0.15)
        return _clamp(base_risk * cascade_multiplier)
    except Exception:
        return 0.0


def _eval_coherence_degradation(ctx: dict) -> float:
    """Measure alignment consistency between trajectory, state machine, longitudinal model."""
    try:
        layer_scores = [
            ctx.get("trajectory_coherence", 1.0),
            ctx.get("state_machine_stability", 1.0),
            ctx.get("longitudinal_coherence", 1.0),
            ctx.get("adaptive_strategy_coherence", 1.0),
            ctx.get("route_simulation_coherence", 1.0),
        ]
        valid = [_clamp(s) for s in layer_scores if s is not None]
        if not valid:
            return 0.0
        avg = sum(valid) / len(valid)
        return _clamp(1.0 - avg)
    except Exception:
        return 0.0


def _eval_pacing_pressure_stability(ctx: dict) -> float:
    """Evaluate whether pacing engine pressure is stable or accumulating."""
    try:
        pacing_score = _clamp(ctx.get("pacing_stability_score", 0.8))
        pacing_pressure = _clamp(ctx.get("pacing_pressure_level", 0.2))
        pacing_queue = _clamp(ctx.get("pacing_queue_ratio", 0.2))
        stability = pacing_score * (1.0 - pacing_pressure) * (1.0 - pacing_queue)
        return _clamp(stability)
    except Exception:
        return 0.5


def _eval_route_conflict_stability(ctx: dict) -> float:
    """Detect conflicts between route simulation output and adaptive strategy."""
    try:
        route_score = _clamp(ctx.get("route_simulation_score", 0.8))
        strategy_score = _clamp(ctx.get("adaptive_strategy_score", 0.8))
        route_state = ctx.get("route_simulation_state", "STABLE")
        strategy_state = ctx.get("adaptive_strategy_state", "STABLE")

        conflict_penalty = 0.0
        critical_route_states = {"CRITICAL", "REGRESSING", "CONFLICTING"}
        critical_strategy_states = {"CONFLICT", "OVERRIDDEN", "CRITICAL"}

        if route_state in critical_route_states:
            conflict_penalty += 0.3
        if strategy_state in critical_strategy_states:
            conflict_penalty += 0.3
        divergence = abs(route_score - strategy_score)
        conflict_penalty += divergence * 0.4

        return _clamp(1.0 - conflict_penalty)
    except Exception:
        return 0.5


def _eval_escalation_stability(ctx: dict) -> float:
    """Check whether escalation pathway is intact."""
    try:
        human_escalation_intact = ctx.get("human_escalation_pathway_intact", True)
        silence_respect_intact = ctx.get("silence_respect_pathway_intact", True)
        escalation_queue_health = _clamp(ctx.get("escalation_queue_health", 1.0))

        score = escalation_queue_health
        if not human_escalation_intact:
            score *= 0.3
        if not silence_respect_intact:
            score *= 0.5
        return _clamp(score)
    except Exception:
        return 0.5


def _eval_silence_respect_integrity(ctx: dict) -> float:
    """Verify silence respect signals are not suppressed or bypassed."""
    try:
        silence_respected = ctx.get("silence_respected", True)
        silence_bypass_detected = ctx.get("silence_bypass_detected", False)
        silence_override_count = ctx.get("silence_override_count", 0)

        score = 1.0
        if not silence_respected:
            score *= 0.6
        if silence_bypass_detected:
            score *= 0.3
        if silence_override_count and silence_override_count > 0:
            override_penalty = min(0.5, silence_override_count * 0.1)
            score = max(0.0, score - override_penalty)
        return _clamp(score)
    except Exception:
        return 0.5


def _eval_recovery_policy_integrity(ctx: dict) -> float:
    """Verify recovery policy layer is receiving and applying signals correctly."""
    try:
        policy_applied = ctx.get("recovery_policy_applied", True)
        policy_conflict = ctx.get("recovery_policy_conflict", False)
        policy_health = _clamp(ctx.get("recovery_policy_health", 1.0))

        score = policy_health
        if not policy_applied:
            score *= 0.5
        if policy_conflict:
            score *= 0.6
        return _clamp(score)
    except Exception:
        return 0.5


def _eval_dispatcher_safety_alignment(ctx: dict) -> float:
    """Confirm dispatcher is only outbound path and receiving safe signals."""
    try:
        dispatcher_is_sole_path = ctx.get("dispatcher_is_sole_outbound_path", True)
        dispatcher_health = _clamp(ctx.get("dispatcher_health", 1.0))
        bypass_detected = ctx.get("dispatcher_bypass_detected", False)
        signal_integrity = _clamp(ctx.get("dispatcher_signal_integrity", 1.0))

        score = dispatcher_health * signal_integrity
        if not dispatcher_is_sole_path:
            score *= 0.2
        if bypass_detected:
            score *= 0.1
        return _clamp(score)
    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# State and mode determination
# ---------------------------------------------------------------------------

def _determine_governance_state(scores: dict) -> str:
    """Map score vector to governance stability state."""
    try:
        drift = scores["governance_drift_score"]
        cascade = scores["overload_cascade_risk"]
        coherence_deg = scores["coherence_degradation_score"]
        pacing = scores["pacing_pressure_stability"]
        route = scores["route_conflict_stability"]
        escalation = scores["escalation_stability_score"]
        silence = scores["silence_respect_integrity"]
        policy = scores["recovery_policy_integrity"]
        dispatcher = scores["dispatcher_safety_alignment"]

        if (cascade > 0.75 or coherence_deg > 0.75 or escalation < 0.3
                or dispatcher < 0.3 or silence < 0.3 or policy < 0.3):
            return "STABILIZATION_REQUIRED"
        if escalation < 0.45:
            return "ESCALATION_INSTABILITY"
        if cascade > 0.6:
            return "OVERLOAD_CASCADE_RISK"
        if coherence_deg > 0.55:
            return "COHERENCE_DEGRADATION"
        if pacing < 0.4:
            return "PACING_PRESSURE"
        if route < 0.45:
            return "ROUTE_CONFLICT_PRESSURE"
        if drift > 0.4:
            return "DRIFT_ACCUMULATING"
        return "STABLE_GOVERNANCE"
    except Exception:
        return "UNKNOWN"


def _determine_stabilization_mode(state: str, scores: dict) -> str:
    """Map governance state and scores to recommended stabilization mode."""
    try:
        if state == "STABLE_GOVERNANCE":
            return "no_change"
        if state == "STABILIZATION_REQUIRED":
            escalation = scores.get("escalation_stability_score", 1.0)
            dispatcher = scores.get("dispatcher_safety_alignment", 1.0)
            if escalation < 0.3:
                return "escalate_for_human_review"
            if dispatcher < 0.3:
                return "reduce_dispatch_density"
            return "hold_nonessential_actions"
        if state == "ESCALATION_INSTABILITY":
            return "escalate_for_human_review"
        if state == "OVERLOAD_CASCADE_RISK":
            return "hold_nonessential_actions"
        if state == "COHERENCE_DEGRADATION":
            return "maintain_current_governance"
        if state == "PACING_PRESSURE":
            cascade = scores.get("overload_cascade_risk", 0.0)
            if cascade > 0.5:
                return "reduce_dispatch_density"
            return "maintain_current_governance"
        if state == "ROUTE_CONFLICT_PRESSURE":
            return "stabilize_route_conflicts"
        if state == "DRIFT_ACCUMULATING":
            silence = scores.get("silence_respect_integrity", 1.0)
            policy = scores.get("recovery_policy_integrity", 1.0)
            if silence < 0.5:
                return "protect_silence"
            if policy < 0.5:
                return "prioritize_recovery_policy"
            return "reduce_route_pressure"
        return "no_change"
    except Exception:
        return "no_change"


def _build_stabilization_notes(state: str, scores: dict) -> list:
    """Build human-readable stabilization signal summaries."""
    notes = []
    try:
        if scores.get("governance_drift_score", 0.0) > 0.4:
            notes.append(f"Governance drift accumulating: {scores['governance_drift_score']:.2f}")
        if scores.get("overload_cascade_risk", 0.0) > 0.5:
            notes.append(f"Overload cascade risk elevated: {scores['overload_cascade_risk']:.2f}")
        if scores.get("coherence_degradation_score", 0.0) > 0.4:
            notes.append(f"Coherence degradation detected: {scores['coherence_degradation_score']:.2f}")
        if scores.get("pacing_pressure_stability", 1.0) < 0.5:
            notes.append(f"Pacing pressure instability: {scores['pacing_pressure_stability']:.2f}")
        if scores.get("route_conflict_stability", 1.0) < 0.5:
            notes.append(f"Route conflict pressure: {scores['route_conflict_stability']:.2f}")
        if scores.get("escalation_stability_score", 1.0) < 0.5:
            notes.append(f"Escalation pathway integrity low: {scores['escalation_stability_score']:.2f}")
        if scores.get("silence_respect_integrity", 1.0) < 0.5:
            notes.append(f"Silence respect integrity compromised: {scores['silence_respect_integrity']:.2f}")
        if scores.get("recovery_policy_integrity", 1.0) < 0.5:
            notes.append(f"Recovery policy integrity degraded: {scores['recovery_policy_integrity']:.2f}")
        if scores.get("dispatcher_safety_alignment", 1.0) < 0.5:
            notes.append(f"Dispatcher safety alignment low: {scores['dispatcher_safety_alignment']:.2f}")
        if not notes:
            notes.append(f"Governance state: {state} — no critical signals")
    except Exception:
        pass
    return notes


# ---------------------------------------------------------------------------
# Engine class
# ---------------------------------------------------------------------------

class SelfStabilizingGovernanceEngine:
    """
    Phase 3.17 — Self-Stabilizing Governance Engine.
    Read-only observer — no state mutation, no direct messaging,
    no medical conclusions. Stabilizes governance conditions only.
    """

    _instance = None
    _initialized: bool = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            log.info("[GOV_STAB] SelfStabilizingGovernanceEngine singleton created")
        return cls._instance

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            from db import get_db_pool
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute(_MIGRATION_SQL)
            log.info("[GOV_STAB] DB migration complete")
        except Exception as e:
            log.debug("[GOV_STAB] DB migration skipped (non-fatal): %s", e)
        self._initialized = True
        log.info("[GOV_STAB] SelfStabilizingGovernanceEngine initialized")

    async def evaluate(self, context: dict) -> dict:
        """
        Evaluate governance stability. Returns stabilization signals.
        Never mutates state, never sends messages. All exceptions return neutral_result.
        """
        try:
            if not context or not isinstance(context, dict):
                return _neutral_result()

            drift = _eval_governance_drift(context)
            cascade = _eval_overload_cascade_risk(context)
            coherence_deg = _eval_coherence_degradation(context)
            pacing = _eval_pacing_pressure_stability(context)
            route = _eval_route_conflict_stability(context)
            escalation = _eval_escalation_stability(context)
            silence = _eval_silence_respect_integrity(context)
            policy = _eval_recovery_policy_integrity(context)
            dispatcher = _eval_dispatcher_safety_alignment(context)

            scores = {
                "governance_drift_score": _clamp(drift),
                "overload_cascade_risk": _clamp(cascade),
                "coherence_degradation_score": _clamp(coherence_deg),
                "pacing_pressure_stability": _clamp(pacing),
                "route_conflict_stability": _clamp(route),
                "escalation_stability_score": _clamp(escalation),
                "silence_respect_integrity": _clamp(silence),
                "recovery_policy_integrity": _clamp(policy),
                "dispatcher_safety_alignment": _clamp(dispatcher),
            }

            state = _determine_governance_state(scores)
            mode = _determine_stabilization_mode(state, scores)
            notes = _build_stabilization_notes(state, scores)
            stabilization_needed = state not in ("STABLE_GOVERNANCE", "UNKNOWN")

            return {
                "governance_stability_state": state,
                "stabilization_needed": stabilization_needed,
                **scores,
                "recommended_stabilization_mode": mode,
                "stabilization_notes": notes,
                "is_neutral": False,
                "evaluated_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            log.debug("[GOV_STAB] evaluate non-fatal exception: %s", e)
            return _neutral_result()


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_engine = None


def get_governance_stabilization_engine():
    global _engine
    if _engine is None:
        _engine = SelfStabilizingGovernanceEngine.get_instance()
    return _engine


async def init_governance_stabilization_engine() -> None:
    engine = get_governance_stabilization_engine()
    await engine.initialize()


async def evaluate_governance_stabilization(context: dict) -> dict:
    try:
        engine = get_governance_stabilization_engine()
        return await engine.evaluate(context)
    except Exception as e:
        log.debug("[GOV_STAB] evaluate_governance_stabilization non-fatal: %s", e)
        return _neutral_result()

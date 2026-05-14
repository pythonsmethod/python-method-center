# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.15 — Adaptive Rehabilitation Strategy Layer
# Module: adaptive_rehabilitation_strategy.py
# Python Method Digital Rehabilitation Center
#
# Goal:
# Determines the most sustainable rehabilitation continuity strategy for each
# client based on long-term behavior, pacing, trajectory, state machine,
# cognitive coherence, and operational safety signals.
#
# IMMUTABLE CONSTRAINT:
# This module MUST NEVER produce actions that:
# - Send messages directly to users
# - Call Telegram, SendPulse, OpenAI, or any outbound sender
# - Call the dispatcher directly
# - Recommend medical treatment or create clinical plans
# - Prescribe medications or therapies
# - Predict disease outcomes, relapse, or medical events
# - Override Karen, human experts, or governance layers
# - Override human_escalation, silence_respect, recovery_policy,
#   emotional_safety, or Central Orchestrator
# - Create pressure, urgency, or fear dynamics
# - Make medical conclusions of any kind
#
# This engine adapts the CONTINUITY STRATEGY, not the medical strategy.
#
# Governance hierarchy position:
# human_escalation > silence_respect > recovery_policy > emotional_safety >
# continuity_protection > trajectory_correction > longitudinal_modeling >
# adaptive_strategy  (bottom layer — read-only observer)
# =============================================================================

import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("adaptive_rehabilitation_strategy")

# ── Strategy States ────────────────────────────────────────────────────────────

STRATEGY_STATES = [
    "STABLE_STRATEGY",
    "STRATEGY_SHIFT_NEEDED",
    "LOW_CONFIDENCE",
    "CONTINUITY_PROTECTION",
    "PACING_REDUCTION",
    "HUMAN_SUPPORT_ALIGNMENT",
    "ROUTE_REPAIR",
    "LONGITUDINAL_STABILIZATION",
    "UNKNOWN",
]

# ── Continuity Strategies ──────────────────────────────────────────────────────

CONTINUITY_STRATEGIES = [
    "standard_continuity",
    "low_pressure_support",
    "stabilization_first",
    "pacing_reduction",
    "route_repair",
    "human_alignment",
    "post_disruption_rebuild",
    "long_term_maintenance",
    "hold_no_change",
]

# ── Thresholds ─────────────────────────────────────────────────────────────────

CONFIDENCE_HIGH_THRESHOLD = 0.70
CONFIDENCE_LOW_THRESHOLD  = 0.45
STABILITY_HIGH_THRESHOLD  = 0.70
STABILITY_LOW_THRESHOLD   = 0.40
EROSION_RISK_HIGH         = 0.55
PACING_LOW_THRESHOLD      = 0.40
ROUTE_LOW_THRESHOLD       = 0.40
TRAJECTORY_LOW_THRESHOLD  = 0.50
EXPERT_HANDOFF_THRESHOLD  = 0.65
SHIFT_PRESSURE_THRESHOLD  = 0.60
INSTABILITY_COUNT_TRIGGER = 2

# ── Support intensity levels ───────────────────────────────────────────────────

INTENSITY_HIGH   = 1.0
INTENSITY_MEDIUM = 0.60
INTENSITY_LOW    = 0.30
INTENSITY_NONE   = 0.0

# ── DB connection ──────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def _get_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


# ── Neutral result ─────────────────────────────────────────────────────────────

def _neutral_result(user_id: str = "") -> Dict[str, Any]:
    return {
        "user_id":                        user_id,
        "adaptive_strategy_state":        "UNKNOWN",
        "recommended_continuity_strategy":"hold_no_change",
        "strategy_confidence_score":      0.0,
        "strategy_stability_score":       0.0,
        "strategy_shift_needed":          False,
        "continuity_support_mode":        "hold",
        "route_support_intensity":        0.0,
        "pacing_strategy_alignment":      0.0,
        "longitudinal_strategy_fit":      0.0,
        "emotional_safety_strategy_fit":  0.0,
        "expert_handoff_strategy_fit":    0.0,
        "strategy_notes":                 {},
        "evaluated_at":                   datetime.now(timezone.utc).isoformat(),
        "is_neutral":                     True,
    }


# ── Engine ─────────────────────────────────────────────────────────────────────

class AdaptiveRehabilitationStrategyEngine:
    _instance = None
    _initialized = False

    def __init__(self):
        self._eval_count  = 0
        self._error_count = 0
        self._state_counts: Dict[str, int] = {s: 0 for s in STRATEGY_STATES}
        self._strategy_counts: Dict[str, int] = {s: 0 for s in CONTINUITY_STRATEGIES}

    @classmethod
    def get_instance(cls) -> "AdaptiveRehabilitationStrategyEngine":
        if cls._instance is None:
            cls._instance = cls()
            log.info("[STRATEGY] AdaptiveRehabilitationStrategyEngine singleton created")
        return cls._instance

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            self._initialized = True
            log.info("[STRATEGY] AdaptiveRehabilitationStrategyEngine initialized")
        except Exception as exc:
            log.debug("[STRATEGY] initialize exception (non-fatal): %s", exc)

    # ── Public entry point ─────────────────────────────────────────────────────

    async def evaluate(self, user_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if not user_id:
            return _neutral_result()
        try:
            return await self._run_evaluation(user_id, context)
        except Exception as exc:
            self._error_count += 1
            log.debug("[STRATEGY] evaluate exception (non-fatal): %s", exc)
            return _neutral_result(user_id)

    # ── Core evaluation ────────────────────────────────────────────────────────

    async def _run_evaluation(
        self, user_id: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        profile = await self._load_profile(user_id)
        signals = self._extract_signals(profile, context)
        scores  = self._compute_scores(signals)
        state   = self._determine_state(scores, signals)
        strategy = self._select_strategy(state, scores, signals)
        modes   = self._compute_modes(scores, signals, state)
        notes   = self._build_notes(state, strategy, scores, signals)

        result: Dict[str, Any] = {
            "user_id":                        user_id,
            "adaptive_strategy_state":        state,
            "recommended_continuity_strategy":strategy,
            "strategy_confidence_score":      scores["confidence"],
            "strategy_stability_score":       scores["stability"],
            "strategy_shift_needed":          state == "STRATEGY_SHIFT_NEEDED",
            "continuity_support_mode":        modes["support_mode"],
            "route_support_intensity":        scores["route_intensity"],
            "pacing_strategy_alignment":      scores["pacing_alignment"],
            "longitudinal_strategy_fit":      scores["longitudinal_fit"],
            "emotional_safety_strategy_fit":  scores["emotional_safety_fit"],
            "expert_handoff_strategy_fit":    scores["expert_handoff_fit"],
            "strategy_notes":                 notes,
            "evaluated_at":                   datetime.now(timezone.utc).isoformat(),
            "is_neutral":                     False,
        }

        self._eval_count += 1
        self._state_counts[state] = self._state_counts.get(state, 0) + 1
        self._strategy_counts[strategy] = self._strategy_counts.get(strategy, 0) + 1

        await self._persist(user_id, result)
        return result

    # ── Profile loader ─────────────────────────────────────────────────────────

    async def _load_profile(self, user_id: str) -> Dict[str, Any]:
        try:
            conn = _get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            engagement_score,
                            continuity_score,
                            pacing_score,
                            route_stability_score,
                            trajectory_score,
                            recovery_score,
                            risk_score,
                            escalation_level,
                            longitudinal_stability_score,
                            rehabilitation_resilience_score,
                            continuity_sustainability_score,
                            recurring_instability_detected,
                            disengagement_cycle_detected,
                            pacing_adaptation_quality,
                            long_term_route_durability,
                            continuity_erosion_risk,
                            longitudinal_coherence_score,
                            orchestration_coherence_score,
                            overall_system_stability_score,
                            emotional_safety_integrity_score,
                            disruption_count,
                            instability_count
                        FROM pm_client_profiles
                        WHERE user_id = %s
                        LIMIT 1
                        """,
                        (str(user_id),),
                    )
                    row = cur.fetchone()
            finally:
                conn.close()

            if not row:
                return {}

            cols = [
                "engagement_score", "continuity_score", "pacing_score",
                "route_stability_score", "trajectory_score", "recovery_score",
                "risk_score", "escalation_level",
                "longitudinal_stability_score", "rehabilitation_resilience_score",
                "continuity_sustainability_score", "recurring_instability_detected",
                "disengagement_cycle_detected", "pacing_adaptation_quality",
                "long_term_route_durability", "continuity_erosion_risk",
                "longitudinal_coherence_score", "orchestration_coherence_score",
                "overall_system_stability_score", "emotional_safety_integrity_score",
                "disruption_count", "instability_count",
            ]
            return dict(zip(cols, row))
        except Exception as exc:
            log.debug("[STRATEGY] _load_profile exception (non-fatal): %s", exc)
            return {}

    # ── Signal extraction ──────────────────────────────────────────────────────

    def _extract_signals(
        self, profile: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        def _f(key: str, default: float = 0.0) -> float:
            v = profile.get(key, default)
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        def _b(key: str) -> bool:
            v = profile.get(key, False)
            if isinstance(v, bool):
                return v
            return bool(v)

        def _ci(key: str, default: float = 0.0) -> float:
            v = context.get(key, default)
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        def _cb(key: str) -> bool:
            return bool(context.get(key, False))

        return {
            # Core engagement signals
            "engagement":          _f("engagement_score"),
            "continuity":          _f("continuity_score"),
            "pacing":              _f("pacing_score"),
            "route_stability":     _f("route_stability_score"),
            "trajectory":          _f("trajectory_score"),
            "recovery":            _f("recovery_score"),
            "risk":                _f("risk_score"),
            "escalation_level":    _f("escalation_level"),
            # Longitudinal signals (Phase 3.14)
            "long_stability":      _f("longitudinal_stability_score"),
            "resilience":          _f("rehabilitation_resilience_score"),
            "continuity_sustain":  _f("continuity_sustainability_score"),
            "recurring_instab":    _b("recurring_instability_detected"),
            "disengagement_cycle": _b("disengagement_cycle_detected"),
            "pacing_adapt":        _f("pacing_adaptation_quality"),
            "route_durability":    _f("long_term_route_durability"),
            "erosion_risk":        _f("continuity_erosion_risk"),
            "long_coherence":      _f("longitudinal_coherence_score"),
            # Cognitive signals (Phase 3.13)
            "orch_coherence":      _f("orchestration_coherence_score"),
            "system_stability":    _f("overall_system_stability_score"),
            "emotional_safety":    _f("emotional_safety_integrity_score"),
            # Disruption counters
            "disruption_count":    int(_f("disruption_count")),
            "instability_count":   int(_f("instability_count")),
            # Context signals
            "escalation_pending":  _cb("escalation_pending"),
            "silence_detected":    _cb("silence_detected"),
            "disruption_active":   _cb("disruption_active"),
            "human_esc_active":    _cb("human_escalation_active"),
            "silence_respected":   _cb("silence_respected"),
        }

    # ── Score computation ──────────────────────────────────────────────────────

    def _compute_scores(self, signals: Dict[str, Any]) -> Dict[str, float]:
        def _clamp(v: float) -> float:
            return max(0.0, min(1.0, v))

        # Confidence: average of core engagement + longitudinal coherence
        confidence = _clamp((
            signals["engagement"] * 0.20 +
            signals["continuity"] * 0.20 +
            signals["long_stability"] * 0.25 +
            signals["long_coherence"] * 0.20 +
            signals["system_stability"] * 0.15
        ))

        # Stability: route + trajectory + resilience
        stability = _clamp((
            signals["route_stability"] * 0.30 +
            signals["trajectory"] * 0.25 +
            signals["resilience"] * 0.25 +
            signals["continuity_sustain"] * 0.20
        ))

        # Shift pressure: instability signals
        recurring_factor = 0.30 if signals["recurring_instab"] else 0.0
        disengagement_factor = 0.20 if signals["disengagement_cycle"] else 0.0
        disruption_factor = _clamp(signals["disruption_count"] / 10.0) * 0.20
        risk_factor = signals["risk"] * 0.15
        erosion_factor = signals["erosion_risk"] * 0.15
        shift_pressure = _clamp(
            recurring_factor + disengagement_factor +
            disruption_factor + risk_factor + erosion_factor
        )

        # Pacing alignment
        pacing_alignment = _clamp((
            signals["pacing"] * 0.50 +
            signals["pacing_adapt"] * 0.50
        ))

        # Route support intensity: inverse of route stability
        route_intensity = _clamp(1.0 - signals["route_stability"])

        # Longitudinal fit
        longitudinal_fit = _clamp((
            signals["long_stability"] * 0.40 +
            signals["long_coherence"] * 0.35 +
            signals["route_durability"] * 0.25
        ))

        # Emotional safety fit
        emotional_safety_fit = _clamp(signals["emotional_safety"])

        # Expert handoff fit: escalation + risk
        expert_handoff_fit = _clamp((
            signals["escalation_level"] * 0.50 +
            signals["risk"] * 0.30 +
            (0.20 if signals["escalation_pending"] else 0.0)
        ))

        return {
            "confidence":           round(confidence, 4),
            "stability":            round(stability, 4),
            "shift_pressure":       round(shift_pressure, 4),
            "pacing_alignment":     round(pacing_alignment, 4),
            "route_intensity":      round(route_intensity, 4),
            "longitudinal_fit":     round(longitudinal_fit, 4),
            "emotional_safety_fit": round(emotional_safety_fit, 4),
            "expert_handoff_fit":   round(expert_handoff_fit, 4),
        }

    def _zero_scores(self) -> Dict[str, float]:
        return {
            "confidence": 0.0, "stability": 0.0, "shift_pressure": 0.0,
            "pacing_alignment": 0.0, "route_intensity": 0.0,
            "longitudinal_fit": 0.0, "emotional_safety_fit": 0.0,
            "expert_handoff_fit": 0.0,
        }

    # ── State determination ────────────────────────────────────────────────────

    def _determine_state(
        self, scores: Dict[str, float], signals: Dict[str, Any]
    ) -> str:
        # Governance priority checks first
        if signals["human_esc_active"] or signals["silence_respected"]:
            return "UNKNOWN"

        conf  = scores["confidence"]
        stab  = scores["stability"]
        shift = scores["shift_pressure"]

        # All-zero guard
        if conf == 0.0 and stab == 0.0:
            return "UNKNOWN"

        # Low confidence guard — insufficient data
        if conf < CONFIDENCE_LOW_THRESHOLD and stab < STABILITY_LOW_THRESHOLD:
            return "LOW_CONFIDENCE"

        # Human support alignment — escalation-driven
        if (signals["expert_handoff_fit"] >= EXPERT_HANDOFF_THRESHOLD or
                signals["escalation_pending"] or signals["escalation_level"] > 0.6):
            return "HUMAN_SUPPORT_ALIGNMENT"

        # Continuity protection — erosion detected
        if (signals["erosion_risk"] > EROSION_RISK_HIGH and
                signals["continuity"] < STABILITY_LOW_THRESHOLD):
            return "CONTINUITY_PROTECTION"

        # Route repair — route and trajectory both degraded
        if (signals["route_stability"] < ROUTE_LOW_THRESHOLD and
                signals["trajectory"] < TRAJECTORY_LOW_THRESHOLD):
            return "ROUTE_REPAIR"

        # Pacing reduction — pacing overloaded
        if signals["pacing"] < PACING_LOW_THRESHOLD:
            return "PACING_REDUCTION"

        # Longitudinal stabilization — chronic instability
        if (signals["recurring_instab"] and
                signals["disruption_count"] > INSTABILITY_COUNT_TRIGGER):
            return "LONGITUDINAL_STABILIZATION"

        # Strategy shift — acute pressure
        if shift > SHIFT_PRESSURE_THRESHOLD:
            return "STRATEGY_SHIFT_NEEDED"

        # Stable — high confidence and stability
        if conf >= CONFIDENCE_HIGH_THRESHOLD and stab >= STABILITY_HIGH_THRESHOLD:
            return "STABLE_STRATEGY"

        # Default to low confidence if nothing else matches
        if conf < CONFIDENCE_LOW_THRESHOLD:
            return "LOW_CONFIDENCE"

        return "UNKNOWN"

    # ── Strategy selection ─────────────────────────────────────────────────────

    def _select_strategy(
        self,
        state: str,
        scores: Dict[str, float],
        signals: Dict[str, Any],
    ) -> str:
        mapping = {
            "STABLE_STRATEGY":           "standard_continuity",
            "LOW_CONFIDENCE":            "hold_no_change",
            "CONTINUITY_PROTECTION":     "stabilization_first",
            "PACING_REDUCTION":          "pacing_reduction",
            "HUMAN_SUPPORT_ALIGNMENT":   "human_alignment",
            "ROUTE_REPAIR":              "route_repair",
            "LONGITUDINAL_STABILIZATION":"long_term_maintenance",
            "UNKNOWN":                   "hold_no_change",
        }
        if state in mapping:
            strategy = mapping[state]
        elif state == "STRATEGY_SHIFT_NEEDED":
            # Select between rebuild and pacing_reduction based on disruption
            if signals.get("disruption_count", 0) > 1 or signals.get("disruption_active"):
                strategy = "post_disruption_rebuild"
            else:
                strategy = "pacing_reduction"
        else:
            strategy = "hold_no_change"

        # Secondary gate: low longitudinal fit overrides to low_pressure_support
        if (strategy == "standard_continuity" and
                scores["longitudinal_fit"] < 0.45):
            strategy = "low_pressure_support"

        return strategy

    # ── Mode computation ───────────────────────────────────────────────────────

    def _compute_modes(
        self,
        scores: Dict[str, float],
        signals: Dict[str, Any],
        state: str,
    ) -> Dict[str, str]:
        if state in ("UNKNOWN", "LOW_CONFIDENCE"):
            return {"support_mode": "hold"}
        if (signals["escalation_pending"] or signals["human_esc_active"] or
                state == "HUMAN_SUPPORT_ALIGNMENT"):
            return {"support_mode": "active"}
        if scores["shift_pressure"] > 0.40 or state in (
            "STRATEGY_SHIFT_NEEDED", "CONTINUITY_PROTECTION",
            "ROUTE_REPAIR", "LONGITUDINAL_STABILIZATION"
        ):
            return {"support_mode": "active"}
        if state == "STABLE_STRATEGY" and scores["confidence"] >= CONFIDENCE_HIGH_THRESHOLD:
            return {"support_mode": "standby"}
        return {"support_mode": "standby"}

    # ── Notes builder ──────────────────────────────────────────────────────────

    def _build_notes(
        self,
        state: str,
        strategy: str,
        scores: Dict[str, float],
        signals: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            active_signals = []
            if signals.get("recurring_instab"):
                active_signals.append("recurring_instability")
            if signals.get("disengagement_cycle"):
                active_signals.append("disengagement_cycle")
            if signals.get("erosion_risk", 0) > EROSION_RISK_HIGH:
                active_signals.append("continuity_erosion")
            if signals.get("escalation_pending"):
                active_signals.append("escalation_pending")
            if signals.get("disruption_active"):
                active_signals.append("disruption_active")
            if signals.get("silence_detected"):
                active_signals.append("silence_detected")

            reason = (
                f"State={state} selected strategy={strategy}. "
                f"confidence={scores['confidence']:.3f} "
                f"stability={scores['stability']:.3f} "
                f"shift_pressure={scores['shift_pressure']:.3f}"
            )
            return {
                "reason":  reason,
                "signals": active_signals,
                "scores": {
                    k: round(v, 4) for k, v in scores.items()
                },
            }
        except Exception:
            return {}

    # ── Persist ────────────────────────────────────────────────────────────────

    async def _persist(self, user_id: str, result: Dict[str, Any]) -> None:
        try:
            import json as _json
            conn = _get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE pm_client_profiles SET
                            adaptive_strategy_state              = %s,
                            recommended_continuity_strategy      = %s,
                            strategy_confidence_score            = %s,
                            strategy_stability_score             = %s,
                            strategy_shift_needed                = %s,
                            continuity_support_mode              = %s,
                            route_support_intensity              = %s,
                            pacing_strategy_alignment            = %s,
                            longitudinal_strategy_fit            = %s,
                            emotional_safety_strategy_fit        = %s,
                            expert_handoff_strategy_fit          = %s,
                            strategy_notes                       = %s,
                            last_strategy_check                  = NOW()
                        WHERE user_id = %s
                        """,
                        (
                            result["adaptive_strategy_state"],
                            result["recommended_continuity_strategy"],
                            result["strategy_confidence_score"],
                            result["strategy_stability_score"],
                            result["strategy_shift_needed"],
                            result["continuity_support_mode"],
                            result["route_support_intensity"],
                            result["pacing_strategy_alignment"],
                            result["longitudinal_strategy_fit"],
                            result["emotional_safety_strategy_fit"],
                            result["expert_handoff_strategy_fit"],
                            _json.dumps(result["strategy_notes"]),
                            str(user_id),
                        ),
                    )
                    conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            log.debug("[STRATEGY] _persist exception (non-fatal): %s", exc)

    # ── Stats ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            "engine":           "AdaptiveRehabilitationStrategyEngine",
            "phase":            "3.15",
            "initialized":      self._initialized,
            "eval_count":       self._eval_count,
            "error_count":      self._error_count,
            "state_counts":     dict(self._state_counts),
            "strategy_counts":  dict(self._strategy_counts),
        }


# ── Module-level singletons ────────────────────────────────────────────────────

_engine: Optional[AdaptiveRehabilitationStrategyEngine] = None


def get_adaptive_strategy_engine() -> AdaptiveRehabilitationStrategyEngine:
    global _engine
    if _engine is None:
        _engine = AdaptiveRehabilitationStrategyEngine.get_instance()
    return _engine


async def init_adaptive_strategy_engine() -> None:
    engine = get_adaptive_strategy_engine()
    await engine.initialize()


async def evaluate_adaptive_strategy(
    user_id: str, context: Dict[str, Any]
) -> Dict[str, Any]:
    engine = get_adaptive_strategy_engine()
    return await engine.evaluate(user_id, context)

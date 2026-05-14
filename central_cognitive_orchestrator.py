"""
central_cognitive_orchestrator.py
Phase 3.13 — Central Cognitive Orchestrator
Python Method Digital Rehabilitation Center

IMMUTABLE CONSTRAINT:
This module MUST NEVER produce actions that:
- Send messages directly to users
- Call Telegram, SendPulse, OpenAI, or any outbound sender
- Call the dispatcher directly
- Override any governance layer
- Override human_escalation or silence_respect
- Make medical conclusions or prescriptions
- Create urgency or force progression
- Destabilize the coherence of the rehabilitation system
- Override the Central Orchestrator as final authority

Core principle:
No individual engine may destabilize the overall rehabilitation system coherence.

Governance position (lowest evaluated — synthesizes all above):
human_escalation > silence_respect > recovery_policy > emotional_safety >
continuity_logic > trajectory_intelligence > rehabilitation_state_machine >
multi_stage_orchestration > dynamic_pacing_intelligence > expert_load_balancing >
central_cognitive_orchestrator
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_TAG = "[COGNITIVE]"

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SystemCoherenceState(str, Enum):
    COHERENT = "COHERENT"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    OVERLOAD_CHAIN = "OVERLOAD_CHAIN"
    INSTABILITY = "INSTABILITY"
    GOVERNANCE_BREACH_RISK = "GOVERNANCE_BREACH_RISK"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"


class DominantPriority(str, Enum):
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    SILENCE_RESPECT = "SILENCE_RESPECT"
    RECOVERY_FIRST = "RECOVERY_FIRST"
    EMOTIONAL_SAFETY = "EMOTIONAL_SAFETY"
    CONTINUITY_PROTECTION = "CONTINUITY_PROTECTION"
    TRAJECTORY_CORRECTION = "TRAJECTORY_CORRECTION"
    LOAD_RELIEF = "LOAD_RELIEF"
    PACING_ADJUSTMENT = "PACING_ADJUSTMENT"
    ROUTE_STABILIZATION = "ROUTE_STABILIZATION"
    NORMAL_OPERATION = "NORMAL_OPERATION"


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

OVERLOAD_CHAIN_THRESHOLD = 3          # >= this many overload signals = chain
DRIFT_THRESHOLD = 0.65
CONTINUITY_RISK_THRESHOLD = 0.70
EMOTIONAL_SAFETY_LOW = 0.40
ROUTE_INTEGRITY_LOW = 0.35
STABILITY_INSTABILITY_THRESHOLD = 0.35
STABILITY_COHERENT_THRESHOLD = 0.70
GOVERNANCE_PRESSURE_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Helper: clamp
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value) if value is not None else lo))


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CognitiveOrchestrationResult:
    system_coherence_state: str = SystemCoherenceState.UNKNOWN.value
    dominant_operational_priority: str = DominantPriority.NORMAL_OPERATION.value
    governance_conflict_detected: bool = False
    operational_drift_score: float = 0.0
    continuity_integrity_score: float = 1.0
    emotional_safety_integrity_score: float = 1.0
    route_integrity_score: float = 1.0
    overload_chain_detected: bool = False
    escalation_coherence_score: float = 1.0
    orchestration_coherence_score: float = 1.0
    pacing_coherence_score: float = 1.0
    overall_system_stability_score: float = 1.0
    cognitive_orchestrator_notes: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: Optional[str] = None
    is_neutral: bool = False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CentralCognitiveOrchestrator:
    """
    Phase 3.13 — Central Cognitive Orchestrator.

    Aggregates all intelligence engine outputs into unified coherence picture.
    Detects contradictions, governance conflicts, systemic instability, drift.
    Produces read-only coherence signal. Never sends, overrides, or contacts anyone.
    """

    _instance: Optional["CentralCognitiveOrchestrator"] = None

    def __init__(self) -> None:
        self._initialized = False
        self._db = None
        log.info("%s CentralCognitiveOrchestrator singleton created", _TAG)

    @classmethod
    def get_instance(cls) -> "CentralCognitiveOrchestrator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, db=None) -> None:
        if self._initialized:
            return
        self._db = db
        self._initialized = True
        log.info("%s CentralCognitiveOrchestrator initialized", _TAG)

    # ------------------------------------------------------------------
    # Neutral result (fail-safe)
    # ------------------------------------------------------------------

    def _neutral_result(self, reason: str = "unknown") -> CognitiveOrchestrationResult:
        return CognitiveOrchestrationResult(
            system_coherence_state=SystemCoherenceState.UNKNOWN.value,
            dominant_operational_priority=DominantPriority.NORMAL_OPERATION.value,
            governance_conflict_detected=False,
            operational_drift_score=0.0,
            continuity_integrity_score=1.0,
            emotional_safety_integrity_score=1.0,
            route_integrity_score=1.0,
            overload_chain_detected=False,
            escalation_coherence_score=1.0,
            orchestration_coherence_score=1.0,
            pacing_coherence_score=1.0,
            overall_system_stability_score=1.0,
            cognitive_orchestrator_notes={"neutral_reason": reason},
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            is_neutral=True,
        )

    # ------------------------------------------------------------------
    # Signal extraction helpers
    # ------------------------------------------------------------------

    def _float(self, context: dict, key: str, default: float = 0.0) -> float:
        try:
            v = context.get(key, default)
            return _clamp(float(v) if v is not None else default)
        except Exception:
            return default

    def _bool(self, context: dict, key: str, default: bool = False) -> bool:
        try:
            v = context.get(key, default)
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes")
            return bool(v)
        except Exception:
            return default

    def _str(self, context: dict, key: str, default: str = "") -> str:
        try:
            v = context.get(key, default)
            return str(v) if v is not None else default
        except Exception:
            return default

    def _nested_float(self, context: dict, outer: str, inner: str, default: float = 0.0) -> float:
        try:
            obj = context.get(outer, {})
            if not isinstance(obj, dict):
                return default
            v = obj.get(inner, default)
            return _clamp(float(v) if v is not None else default)
        except Exception:
            return default

    def _nested_str(self, context: dict, outer: str, inner: str, default: str = "") -> str:
        try:
            obj = context.get(outer, {})
            if not isinstance(obj, dict):
                return default
            v = obj.get(inner, default)
            return str(v) if v is not None else default
        except Exception:
            return default

    def _nested_bool(self, context: dict, outer: str, inner: str, default: bool = False) -> bool:
        try:
            obj = context.get(outer, {})
            if not isinstance(obj, dict):
                return default
            v = obj.get(inner, default)
            if isinstance(v, bool):
                return v
            return bool(v)
        except Exception:
            return default

    # ------------------------------------------------------------------
    # Overload chain detection
    # ------------------------------------------------------------------

    def _detect_overload_chain(self, signals: Dict[str, Any]) -> tuple[bool, int, List[str]]:
        """
        Count overloaded signals across all engines.
        Returns (chain_detected, count, list_of_overloaded_engines).
        """
        overloaded = []

        if signals.get("risk_score", 0.0) >= 0.75:
            overloaded.append("risk_critical")
        if signals.get("orchestration_state") in ("OVERLOADED", "CONFLICT", "QUEUE_CRITICAL"):
            overloaded.append("orchestration_overloaded")
        if signals.get("pacing_state") in ("OVERLOADED", "PAUSED"):
            overloaded.append("pacing_overloaded")
        if signals.get("expert_load_state") in ("OVERLOADED", "QUEUE_CRITICAL"):
            overloaded.append("expert_overloaded")
        if signals.get("continuity_risk", 0.0) >= 0.70:
            overloaded.append("continuity_at_risk")
        if signals.get("route_overload_score", 0.0) >= 0.70:
            overloaded.append("route_overloaded")
        if signals.get("trajectory_drift", 0.0) >= 0.70:
            overloaded.append("trajectory_overloaded")

        count = len(overloaded)
        return count >= OVERLOAD_CHAIN_THRESHOLD, count, overloaded

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------

    def _detect_contradictions(self, signals: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Detect signal contradictions between engines.
        Returns (conflict_detected, list_of_contradiction_descriptions).
        """
        contradictions = []

        # Governance conflict: human_escalation + silence simultaneously
        if signals.get("human_escalation_active") and signals.get("silence_respected"):
            contradictions.append("governance_conflict:escalation+silence_simultaneous")

        # Drift + Acceleration contradiction
        if signals.get("trajectory_drift", 0.0) > 0.60 and signals.get("pacing_state") == "ACCELERATING":
            contradictions.append("trajectory_drift_with_pacing_acceleration")

        # Stability mismatch: orchestration overloaded but pacing sustainable
        if signals.get("orchestration_state") == "OVERLOADED" and signals.get("pacing_state") == "SUSTAINABLE":
            contradictions.append("orchestration_overloaded_pacing_sustainable_mismatch")

        # Continuity collapse chain
        if (signals.get("continuity_risk", 0.0) > 0.75
                and signals.get("trajectory_drift", 0.0) > 0.60):
            contradictions.append("continuity_collapse_chain_risk")

        # Expert overloaded but orchestration clear
        if (signals.get("expert_load_state") in ("OVERLOADED", "QUEUE_CRITICAL")
                and signals.get("orchestration_state") == "CLEAR"):
            contradictions.append("expert_overload_orchestration_clear_mismatch")

        return len(contradictions) > 0, contradictions

    # ------------------------------------------------------------------
    # Scoring formulas
    # ------------------------------------------------------------------

    def _compute_continuity_integrity(self, continuity_risk: float, drift_score: float) -> float:
        return _clamp(1.0 - (continuity_risk * 0.60 + drift_score * 0.40))

    def _compute_emotional_safety_integrity(
        self, engagement_score: float, risk_normalized: float, policy_safety: float
    ) -> float:
        return _clamp(engagement_score * 0.50 + (1.0 - risk_normalized) * 0.30 + policy_safety * 0.20)

    def _compute_route_integrity(
        self, route_overload: float, overload_chain_signal: float, drift_score: float
    ) -> float:
        return _clamp(1.0 - (route_overload * 0.40 + overload_chain_signal * 0.35 + drift_score * 0.25))

    def _compute_operational_drift(
        self, trajectory_drift: float, pacing_instability: float,
        state_regression: float, load_pressure: float
    ) -> float:
        return _clamp(
            trajectory_drift * 0.35
            + pacing_instability * 0.30
            + state_regression * 0.20
            + load_pressure * 0.15
        )

    def _compute_escalation_coherence(
        self, risk_score: float, governance_pressure: float, continuity_failure: float
    ) -> float:
        return _clamp(1.0 - (risk_score * 0.40 + governance_pressure * 0.35 + continuity_failure * 0.25))

    def _compute_orchestration_coherence(
        self, conflict_signal: float, overload_signal: float, pacing_mismatch: float
    ) -> float:
        return _clamp(1.0 - (conflict_signal * 0.40 + overload_signal * 0.35 + pacing_mismatch * 0.25))

    def _compute_pacing_coherence(
        self, pacing_instability: float, route_pressure: float, load_pressure: float
    ) -> float:
        return _clamp(1.0 - (pacing_instability * 0.50 + route_pressure * 0.30 + load_pressure * 0.20))

    def _compute_overall_stability(
        self,
        continuity_integrity: float,
        emotional_safety_integrity: float,
        route_integrity: float,
        escalation_coherence: float,
        orchestration_coherence: float,
        pacing_coherence: float,
        operational_drift: float,
    ) -> float:
        return _clamp(
            continuity_integrity * 0.20
            + emotional_safety_integrity * 0.20
            + route_integrity * 0.15
            + escalation_coherence * 0.15
            + orchestration_coherence * 0.15
            + pacing_coherence * 0.10
            + (1.0 - operational_drift) * 0.05
        )

    # ------------------------------------------------------------------
    # State classification
    # ------------------------------------------------------------------

    def _classify_coherence_state(
        self,
        stability: float,
        overload_chain: bool,
        conflict: bool,
        drift: float,
        governance_pressure: float,
        risk_score: float,
        continuity_risk: float,
        recovery_trend: float,
    ) -> SystemCoherenceState:
        # Priority order: most severe first
        if overload_chain and conflict:
            return SystemCoherenceState.INSTABILITY

        if risk_score >= 0.85 and continuity_risk >= 0.75:
            return SystemCoherenceState.ESCALATION_REQUIRED

        if overload_chain:
            return SystemCoherenceState.OVERLOAD_CHAIN

        if conflict:
            return SystemCoherenceState.CONFLICT_DETECTED

        if governance_pressure >= GOVERNANCE_PRESSURE_THRESHOLD:
            return SystemCoherenceState.GOVERNANCE_BREACH_RISK

        if stability <= STABILITY_INSTABILITY_THRESHOLD:
            return SystemCoherenceState.INSTABILITY

        if drift >= DRIFT_THRESHOLD:
            return SystemCoherenceState.DRIFT_DETECTED

        if recovery_trend >= 0.60 and stability < 0.65:
            return SystemCoherenceState.RECOVERING

        if stability >= STABILITY_COHERENT_THRESHOLD:
            return SystemCoherenceState.COHERENT

        return SystemCoherenceState.UNKNOWN

    # ------------------------------------------------------------------
    # Dominant priority
    # ------------------------------------------------------------------

    def _determine_dominant_priority(
        self,
        human_escalation: bool,
        silence_respected: bool,
        recovery_active: bool,
        emotional_safety_integrity: float,
        continuity_risk: float,
        trajectory_drift: float,
        expert_load_state: str,
        pacing_state: str,
        route_integrity: float,
    ) -> DominantPriority:
        if human_escalation:
            return DominantPriority.HUMAN_ESCALATION
        if silence_respected:
            return DominantPriority.SILENCE_RESPECT
        if recovery_active:
            return DominantPriority.RECOVERY_FIRST
        if emotional_safety_integrity < EMOTIONAL_SAFETY_LOW:
            return DominantPriority.EMOTIONAL_SAFETY
        if continuity_risk > CONTINUITY_RISK_THRESHOLD:
            return DominantPriority.CONTINUITY_PROTECTION
        if trajectory_drift > DRIFT_THRESHOLD:
            return DominantPriority.TRAJECTORY_CORRECTION
        if expert_load_state in ("OVERLOADED", "QUEUE_CRITICAL"):
            return DominantPriority.LOAD_RELIEF
        if pacing_state in ("OVERLOADED", "PAUSED"):
            return DominantPriority.PACING_ADJUSTMENT
        if route_integrity < ROUTE_INTEGRITY_LOW:
            return DominantPriority.ROUTE_STABILIZATION
        return DominantPriority.NORMAL_OPERATION

    # ------------------------------------------------------------------
    # Main evaluation
    # ------------------------------------------------------------------

    async def evaluate_system_coherence(
        self,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveOrchestrationResult:
        """
        Main entry point. Aggregates all upstream engine signals into unified coherence picture.
        Fully fail-safe — any exception returns neutral_result.
        Never sends, overrides, or contacts anyone.
        """
        try:
            if context is None:
                return self._neutral_result("no_context")

            # -------------------------------------------------------
            # Extract governance flags (highest priority)
            # -------------------------------------------------------
            human_escalation = self._bool(context, "human_escalation_active")
            silence_respected = self._bool(context, "silence_respected")
            recovery_active = self._bool(context, "recovery_policy_active")

            # -------------------------------------------------------
            # Extract engine signals
            # -------------------------------------------------------
            risk_score = self._float(context, "risk_score")
            engagement_score = self._float(context, "engagement_score", 0.5)
            continuity_risk = self._float(context, "continuity_risk")
            trajectory_drift = self._float(context, "trajectory_drift")
            recovery_trend = self._float(context, "recovery_trend")

            # Orchestration result (Phase 3.10)
            orchestration_state = self._nested_str(context, "orchestration_result", "orchestration_state", "UNKNOWN")
            route_overload_score = self._nested_float(context, "orchestration_result", "route_overload_score")

            # Pacing result (Phase 3.11)
            pacing_state = self._nested_str(context, "pacing_result", "pacing_state", "UNKNOWN")
            pacing_coherence_raw = self._nested_float(context, "pacing_result", "pacing_coherence_score", 1.0)

            # Load balancing result (Phase 3.12)
            expert_load_state = self._nested_str(context, "load_balancing_result", "expert_load_state", "UNKNOWN")
            operational_stability = self._nested_float(context, "load_balancing_result", "operational_stability_score", 1.0)
            load_congestion = self._nested_float(context, "load_balancing_result", "support_congestion_score", 0.0)

            # -------------------------------------------------------
            # Build signals dict for contradiction / overload analysis
            # -------------------------------------------------------
            signals = {
                "risk_score": risk_score,
                "continuity_risk": continuity_risk,
                "trajectory_drift": trajectory_drift,
                "orchestration_state": orchestration_state,
                "route_overload_score": route_overload_score,
                "pacing_state": pacing_state,
                "expert_load_state": expert_load_state,
                "human_escalation_active": human_escalation,
                "silence_respected": silence_respected,
                "recovery_trend": recovery_trend,
            }

            # -------------------------------------------------------
            # Detect overload chain
            # -------------------------------------------------------
            overload_chain, overload_count, overloaded_engines = self._detect_overload_chain(signals)

            # -------------------------------------------------------
            # Detect contradictions
            # -------------------------------------------------------
            conflict_detected, contradictions = self._detect_contradictions(signals)

            # -------------------------------------------------------
            # Derived intermediates
            # -------------------------------------------------------
            # Pacing instability: inverse of pacing coherence
            pacing_instability = _clamp(1.0 - pacing_coherence_raw)
            # Load pressure from congestion
            load_pressure = load_congestion
            # State regression: risk + continuity
            state_regression = _clamp((risk_score * 0.50) + (continuity_risk * 0.50))
            # Policy safety: inverse of risk
            policy_safety = _clamp(1.0 - risk_score)
            # Governance pressure: escalation + high risk
            governance_pressure = _clamp(
                (1.0 if human_escalation else 0.0) * 0.40
                + risk_score * 0.35
                + continuity_risk * 0.25
            )
            # Overload signal (normalized)
            overload_signal = _clamp(overload_count / 7.0)  # max 7 overload signals
            # Conflict signal
            conflict_signal = 1.0 if conflict_detected else 0.0
            # Pacing mismatch
            pacing_mismatch = 1.0 if (
                orchestration_state == "OVERLOADED" and pacing_state == "SUSTAINABLE"
            ) else 0.0
            # Route pressure
            route_pressure = route_overload_score
            # Continuity failure signal
            continuity_failure = continuity_risk

            # -------------------------------------------------------
            # Compute all scores
            # -------------------------------------------------------
            continuity_integrity = self._compute_continuity_integrity(continuity_risk, trajectory_drift)
            emotional_safety_integrity = self._compute_emotional_safety_integrity(
                engagement_score, risk_score, policy_safety
            )
            route_integrity = self._compute_route_integrity(route_overload_score, overload_signal, trajectory_drift)
            operational_drift = self._compute_operational_drift(
                trajectory_drift, pacing_instability, state_regression, load_pressure
            )
            escalation_coherence = self._compute_escalation_coherence(
                risk_score, governance_pressure, continuity_failure
            )
            orchestration_coherence = self._compute_orchestration_coherence(
                conflict_signal, overload_signal, pacing_mismatch
            )
            pacing_coherence = self._compute_pacing_coherence(
                pacing_instability, route_pressure, load_pressure
            )
            overall_stability = self._compute_overall_stability(
                continuity_integrity, emotional_safety_integrity, route_integrity,
                escalation_coherence, orchestration_coherence, pacing_coherence, operational_drift
            )

            # -------------------------------------------------------
            # Classify coherence state
            # -------------------------------------------------------
            coherence_state = self._classify_coherence_state(
                stability=overall_stability,
                overload_chain=overload_chain,
                conflict=conflict_detected,
                drift=operational_drift,
                governance_pressure=governance_pressure,
                risk_score=risk_score,
                continuity_risk=continuity_risk,
                recovery_trend=recovery_trend,
            )

            # -------------------------------------------------------
            # Determine dominant priority
            # -------------------------------------------------------
            dominant_priority = self._determine_dominant_priority(
                human_escalation=human_escalation,
                silence_respected=silence_respected,
                recovery_active=recovery_active,
                emotional_safety_integrity=emotional_safety_integrity,
                continuity_risk=continuity_risk,
                trajectory_drift=trajectory_drift,
                expert_load_state=expert_load_state,
                pacing_state=pacing_state,
                route_integrity=route_integrity,
            )

            now_iso = datetime.now(timezone.utc).isoformat()

            # -------------------------------------------------------
            # Build notes
            # -------------------------------------------------------
            notes = {
                "signals": {
                    "risk_score": round(risk_score, 4),
                    "engagement_score": round(engagement_score, 4),
                    "continuity_risk": round(continuity_risk, 4),
                    "trajectory_drift": round(trajectory_drift, 4),
                    "orchestration_state": orchestration_state,
                    "route_overload_score": round(route_overload_score, 4),
                    "pacing_state": pacing_state,
                    "pacing_coherence_raw": round(pacing_coherence_raw, 4),
                    "expert_load_state": expert_load_state,
                    "operational_stability": round(operational_stability, 4),
                    "load_congestion": round(load_congestion, 4),
                    "human_escalation_active": human_escalation,
                    "silence_respected": silence_respected,
                    "recovery_active": recovery_active,
                },
                "overload_chain": {
                    "detected": overload_chain,
                    "count": overload_count,
                    "engines": overloaded_engines,
                },
                "contradictions": {
                    "detected": conflict_detected,
                    "list": contradictions,
                },
                "scores": {
                    "continuity_integrity": round(continuity_integrity, 4),
                    "emotional_safety_integrity": round(emotional_safety_integrity, 4),
                    "route_integrity": round(route_integrity, 4),
                    "operational_drift": round(operational_drift, 4),
                    "escalation_coherence": round(escalation_coherence, 4),
                    "orchestration_coherence": round(orchestration_coherence, 4),
                    "pacing_coherence": round(pacing_coherence, 4),
                    "overall_stability": round(overall_stability, 4),
                },
                "coherence_state": coherence_state.value,
                "dominant_priority": dominant_priority.value,
                "evaluated_at": now_iso,
            }

            result = CognitiveOrchestrationResult(
                system_coherence_state=coherence_state.value,
                dominant_operational_priority=dominant_priority.value,
                governance_conflict_detected=conflict_detected,
                operational_drift_score=round(operational_drift, 4),
                continuity_integrity_score=round(continuity_integrity, 4),
                emotional_safety_integrity_score=round(emotional_safety_integrity, 4),
                route_integrity_score=round(route_integrity, 4),
                overload_chain_detected=overload_chain,
                escalation_coherence_score=round(escalation_coherence, 4),
                orchestration_coherence_score=round(orchestration_coherence, 4),
                pacing_coherence_score=round(pacing_coherence, 4),
                overall_system_stability_score=round(overall_stability, 4),
                cognitive_orchestrator_notes=notes,
                evaluated_at=now_iso,
                is_neutral=False,
            )

            await self._persist(user_id, result)
            return result

        except Exception as exc:
            log.debug("%s evaluate_system_coherence exception (non-fatal): %s", _TAG, exc)
            return self._neutral_result("exception")

    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    async def _persist(self, user_id: str, result: CognitiveOrchestrationResult) -> None:
        """Persist result to pm_client_profiles. Fail-safe — never raises."""
        try:
            db = getattr(self, "_db", None)
            if db is None:
                return
            import json
            query = """
                UPDATE pm_client_profiles SET
                    system_coherence_state = $1,
                    dominant_operational_priority = $2,
                    governance_conflict_detected = $3,
                    operational_drift_score = $4,
                    continuity_integrity_score = $5,
                    emotional_safety_integrity_score = $6,
                    route_integrity_score = $7,
                    overload_chain_detected = $8,
                    escalation_coherence_score = $9,
                    orchestration_coherence_score = $10,
                    pacing_coherence_score = $11,
                    overall_system_stability_score = $12,
                    cognitive_orchestrator_notes = $13,
                    last_cognitive_orchestrator_check = NOW()
                WHERE user_id = $14
            """
            await db.execute(
                query,
                result.system_coherence_state,
                result.dominant_operational_priority,
                result.governance_conflict_detected,
                result.operational_drift_score,
                result.continuity_integrity_score,
                result.emotional_safety_integrity_score,
                result.route_integrity_score,
                result.overload_chain_detected,
                result.escalation_coherence_score,
                result.orchestration_coherence_score,
                result.pacing_coherence_score,
                result.overall_system_stability_score,
                json.dumps(result.cognitive_orchestrator_notes),
                user_id,
            )
        except Exception as exc:
            log.debug("%s _persist error (non-fatal): %s", _TAG, exc)

    # ------------------------------------------------------------------
    # Dashboard stats
    # ------------------------------------------------------------------

    async def get_stats(self, db=None) -> Dict[str, Any]:
        """Returns dashboard statistics. Fail-safe."""
        try:
            _db = db or getattr(self, "_db", None)
            if _db is None:
                return {"error": "no_db"}
            rows = await _db.fetch("""
                SELECT
                    COUNT(*) AS total_evaluated,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'COHERENT') AS coherent_count,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'DRIFT_DETECTED') AS drift_count,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'CONFLICT_DETECTED') AS conflict_count,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'OVERLOAD_CHAIN') AS overload_chain_count,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'INSTABILITY') AS instability_count,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'GOVERNANCE_BREACH_RISK') AS governance_risk_count,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'ESCALATION_REQUIRED') AS escalation_required_count,
                    COUNT(*) FILTER (WHERE system_coherence_state = 'RECOVERING') AS recovering_count,
                    COUNT(*) FILTER (WHERE governance_conflict_detected = TRUE) AS governance_conflicts,
                    COUNT(*) FILTER (WHERE overload_chain_detected = TRUE) AS overload_chains,
                    ROUND(AVG(overall_system_stability_score)::numeric, 4) AS avg_stability,
                    ROUND(AVG(operational_drift_score)::numeric, 4) AS avg_drift,
                    ROUND(AVG(continuity_integrity_score)::numeric, 4) AS avg_continuity_integrity,
                    ROUND(AVG(emotional_safety_integrity_score)::numeric, 4) AS avg_emotional_safety,
                    MAX(last_cognitive_orchestrator_check) AS last_check
                FROM pm_client_profiles
                WHERE last_cognitive_orchestrator_check IS NOT NULL
            """)
            if not rows:
                return {"total_evaluated": 0}
            r = rows[0]
            return {
                "total_evaluated": r["total_evaluated"],
                "state_distribution": {
                    "COHERENT": r["coherent_count"],
                    "DRIFT_DETECTED": r["drift_count"],
                    "CONFLICT_DETECTED": r["conflict_count"],
                    "OVERLOAD_CHAIN": r["overload_chain_count"],
                    "INSTABILITY": r["instability_count"],
                    "GOVERNANCE_BREACH_RISK": r["governance_risk_count"],
                    "ESCALATION_REQUIRED": r["escalation_required_count"],
                    "RECOVERING": r["recovering_count"],
                },
                "governance_conflicts_detected": r["governance_conflicts"],
                "overload_chains_detected": r["overload_chains"],
                "avg_stability_score": float(r["avg_stability"] or 0),
                "avg_drift_score": float(r["avg_drift"] or 0),
                "avg_continuity_integrity": float(r["avg_continuity_integrity"] or 0),
                "avg_emotional_safety_integrity": float(r["avg_emotional_safety"] or 0),
                "last_check": r["last_check"].isoformat() if r["last_check"] else None,
            }
        except Exception as exc:
            log.debug("%s get_stats error (non-fatal): %s", _TAG, exc)
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

_engine_instance: Optional[CentralCognitiveOrchestrator] = None


def get_cognitive_orchestrator() -> Optional[CentralCognitiveOrchestrator]:
    """Return singleton if initialized, else None."""
    return CentralCognitiveOrchestrator._instance


async def init_cognitive_orchestrator(db=None) -> CentralCognitiveOrchestrator:
    """Initialize and return singleton. Safe to call multiple times."""
    global _engine_instance
    engine = CentralCognitiveOrchestrator.get_instance()
    await engine.initialize(db=db)
    _engine_instance = engine
    return engine

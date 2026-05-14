"""
expert_load_balancing_engine.py
Phase 3.12 — Expert Load Balancing Intelligence
Python Method Digital Rehabilitation Center

IMMUTABLE CONSTRAINT:
This module MUST NEVER produce actions that:
- Send messages directly to users
- Call Telegram, SendPulse, or any outbound sender
- Call the dispatcher directly
- Assign medical responsibility autonomously
- Override human decisions or governance layers
- Force handoffs or assignments
- Bypass escalation governance
- Manipulate urgency or emotional safety for optimization
- Override human_escalation, silence_respect, or Central Orchestrator as final authority

Governance position (lowest evaluated):
human_escalation > silence_respect > recovery_policy > emotional_safety >
continuity_logic > trajectory_intelligence > rehabilitation_state_machine >
multi_stage_orchestration > dynamic_pacing_intelligence > expert_load_balancing
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_TAG = "[LOAD_BALANCING]"

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ExpertLoadState(str, Enum):
    BALANCED = "BALANCED"
    PRESSURED = "PRESSURED"
    CONGESTED = "CONGESTED"
    OVERLOADED = "OVERLOADED"
    RECOVERING = "RECOVERING"
    HANDOFF_AT_RISK = "HANDOFF_AT_RISK"
    QUEUE_CRITICAL = "QUEUE_CRITICAL"
    UNKNOWN = "UNKNOWN"


class SafeAssignmentCapacity(str, Enum):
    FULL = "full"
    REDUCED = "reduced"
    MINIMAL = "minimal"
    ZERO = "zero"
    PARTIAL = "partial"
    RESTRICTED = "restricted"
    EMERGENCY = "emergency"
    CONSERVATIVE = "conservative"


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

CONGESTION_THRESHOLDS = {
    "balanced_max": 0.30,
    "pressured_max": 0.55,
    "congested_max": 0.75,
    "overloaded_min": 0.76,
}

OVERLOAD_RISK_THRESHOLDS = {
    "low_max": 0.30,
    "moderate_max": 0.55,
    "high_max": 0.75,
    "critical_min": 0.76,
}

STABILITY_THRESHOLDS = {
    "stable_min": 0.70,
    "pressured_min": 0.50,
    "unstable_max": 0.49,
}

INTEGRITY_AT_RISK = 0.50

CAPACITY_MAP: Dict[ExpertLoadState, SafeAssignmentCapacity] = {
    ExpertLoadState.BALANCED: SafeAssignmentCapacity.FULL,
    ExpertLoadState.PRESSURED: SafeAssignmentCapacity.REDUCED,
    ExpertLoadState.CONGESTED: SafeAssignmentCapacity.MINIMAL,
    ExpertLoadState.OVERLOADED: SafeAssignmentCapacity.ZERO,
    ExpertLoadState.RECOVERING: SafeAssignmentCapacity.PARTIAL,
    ExpertLoadState.HANDOFF_AT_RISK: SafeAssignmentCapacity.RESTRICTED,
    ExpertLoadState.QUEUE_CRITICAL: SafeAssignmentCapacity.EMERGENCY,
    ExpertLoadState.UNKNOWN: SafeAssignmentCapacity.CONSERVATIVE,
}

# Context signal keys consumed from orchestrator pipeline
CONTEXT_KEYS = {
    "active_escalations": "active_escalations",
    "recent_escalations_24h": "recent_escalations_24h",
    "expert_caseload_ratio": "expert_caseload_ratio",
    "escalation_density": "escalation_density",
    "handoff_volume": "handoff_volume",
    "capacity_headroom": "capacity_headroom",
    "distribution_balance": "distribution_balance",
    "recovery_trend": "recovery_trend",
    "response_lag": "response_lag",
    "continuity_handoff_risk": "continuity_handoff_risk",
    "emotional_safety_buffer": "emotional_safety_buffer",
    "route_complexity": "route_complexity",
    "queue_depth": "queue_depth",
    "per_expert_loads": "per_expert_loads",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class LoadBalancingResult:
    expert_load_state: str = ExpertLoadState.UNKNOWN.value
    support_congestion_score: float = 0.0
    escalation_queue_pressure: float = 0.0
    expert_overload_risk: float = 0.0
    continuity_handoff_risk: float = 0.0
    operational_stability_score: float = 1.0
    safe_assignment_capacity: str = SafeAssignmentCapacity.CONSERVATIVE.value
    escalation_distribution_balance: float = 1.0
    response_sustainability_score: float = 1.0
    human_support_integrity_score: float = 1.0
    load_balancing_notes: Dict[str, Any] = field(default_factory=dict)
    integrity_at_risk: bool = False
    evaluated_at: Optional[str] = None
    is_neutral: bool = False


# ---------------------------------------------------------------------------
# Helper: clamp
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ExpertLoadBalancingEngine:
    """
    Phase 3.12 — Expert Load Balancing Intelligence.

    Read-only intelligence layer. Evaluates operational health of expert/human-support
    load distribution. Produces signals consumed by dispatcher. Never sends, assigns,
    overrides, or contacts anyone directly.
    """

    _instance: Optional["ExpertLoadBalancingEngine"] = None
    _lock: asyncio.Lock = None  # type: ignore

    def __init__(self) -> None:
        self._initialized = False
        log.info("%s ExpertLoadBalancingEngine singleton created", _TAG)

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "ExpertLoadBalancingEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, db=None) -> None:
        if self._initialized:
            return
        self._db = db
        self._initialized = True
        log.info("%s ExpertLoadBalancingEngine initialized", _TAG)

    # ------------------------------------------------------------------
    # Neutral result (fail-safe)
    # ------------------------------------------------------------------

    def _neutral_result(self, reason: str = "unknown") -> LoadBalancingResult:
        return LoadBalancingResult(
            expert_load_state=ExpertLoadState.UNKNOWN.value,
            support_congestion_score=0.0,
            escalation_queue_pressure=0.0,
            expert_overload_risk=0.0,
            continuity_handoff_risk=0.0,
            operational_stability_score=1.0,
            safe_assignment_capacity=SafeAssignmentCapacity.CONSERVATIVE.value,
            escalation_distribution_balance=1.0,
            response_sustainability_score=1.0,
            human_support_integrity_score=1.0,
            load_balancing_notes={"neutral_reason": reason},
            integrity_at_risk=False,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            is_neutral=True,
        )

    # ------------------------------------------------------------------
    # Signal extraction from context
    # ------------------------------------------------------------------

    def _extract_signal(self, context: dict, key: str, default: float = 0.0) -> float:
        try:
            raw = context.get(key, default)
            if raw is None:
                return default
            return _clamp(float(raw))
        except Exception:
            return default

    def _extract_list(self, context: dict, key: str) -> List[float]:
        try:
            raw = context.get(key, [])
            if not isinstance(raw, list):
                return []
            return [_clamp(float(v)) for v in raw if v is not None]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Scoring formulas
    # ------------------------------------------------------------------

    def _compute_escalation_queue_pressure(
        self,
        active_escalations: float,
        recent_escalations_24h: float,
        queue_depth: float,
    ) -> float:
        """
        Queue pressure from escalation volume signals.
        active_escalations: 0.0–1.0 ratio of active vs capacity
        recent_escalations_24h: 0.0–1.0 normalized recent count
        queue_depth: 0.0–1.0 depth ratio
        """
        pressure = (
            active_escalations * 0.40
            + recent_escalations_24h * 0.35
            + queue_depth * 0.25
        )
        return _clamp(pressure)

    def _compute_expert_overload_risk(
        self,
        caseload_ratio: float,
        escalation_density: float,
        handoff_volume: float,
    ) -> float:
        """
        Per-expert overload risk composite.
        """
        risk = (
            caseload_ratio * 0.40
            + escalation_density * 0.35
            + handoff_volume * 0.25
        )
        return _clamp(risk)

    def _compute_support_congestion_score(
        self,
        active_load: float,
        queue_pressure: float,
        overload_risk: float,
        response_lag: float,
    ) -> float:
        """
        Support channel congestion composite.
        """
        congestion = (
            active_load * 0.35
            + queue_pressure * 0.30
            + overload_risk * 0.20
            + response_lag * 0.15
        )
        return _clamp(congestion)

    def _compute_operational_stability_score(
        self,
        congestion: float,
        overload_risk: float,
        handoff_risk: float,
    ) -> float:
        """
        Overall operational stability — higher is more stable.
        """
        instability = (
            congestion * 0.40
            + overload_risk * 0.35
            + handoff_risk * 0.25
        )
        stability = 1.0 - instability
        return _clamp(stability)

    def _compute_response_sustainability(
        self,
        capacity_headroom: float,
        distribution_balance: float,
        recovery_trend: float,
    ) -> float:
        """
        Response sustainability — higher means more sustainable.
        """
        sustainability = (
            capacity_headroom * 0.50
            + distribution_balance * 0.30
            + recovery_trend * 0.20
        )
        return _clamp(sustainability)

    def _compute_escalation_distribution_balance(
        self,
        per_expert_loads: List[float],
    ) -> float:
        """
        Escalation distribution balance across experts.
        Higher = more balanced.
        Returns 1.0 if insufficient data.
        """
        if len(per_expert_loads) < 2:
            return 1.0
        try:
            std = statistics.stdev(per_expert_loads)
            max_possible = 1.0  # loads are 0.0–1.0
            balance = 1.0 - _clamp(std / max_possible)
            return _clamp(balance)
        except Exception:
            return 1.0

    def _compute_human_support_integrity(
        self,
        response_sustainability: float,
        continuity_handoff_safety: float,
        emotional_safety_buffer: float,
    ) -> float:
        """
        Human support integrity — must never drop below 0.50 without flag.
        """
        integrity = (
            response_sustainability * 0.40
            + continuity_handoff_safety * 0.35
            + emotional_safety_buffer * 0.25
        )
        return _clamp(min(1.0, integrity))

    # ------------------------------------------------------------------
    # State classification
    # ------------------------------------------------------------------

    def _classify_load_state(
        self,
        congestion: float,
        overload_risk: float,
        queue_pressure: float,
        handoff_risk: float,
        stability: float,
        recovery_trend: float,
    ) -> ExpertLoadState:
        """
        Classify expert load state from composite signals.
        Priority: QUEUE_CRITICAL > OVERLOADED > HANDOFF_AT_RISK > CONGESTED > RECOVERING > PRESSURED > BALANCED > UNKNOWN
        """
        # Critical queue state — highest priority flag
        if queue_pressure >= 0.85:
            return ExpertLoadState.QUEUE_CRITICAL

        # Overloaded
        if congestion >= CONGESTION_THRESHOLDS["overloaded_min"] or overload_risk >= OVERLOAD_RISK_THRESHOLDS["critical_min"]:
            return ExpertLoadState.OVERLOADED

        # Handoff at risk — continuity concern
        if handoff_risk >= 0.70:
            return ExpertLoadState.HANDOFF_AT_RISK

        # Congested
        if congestion >= CONGESTION_THRESHOLDS["pressured_max"] + 0.01:
            return ExpertLoadState.CONGESTED

        # Recovering — load decreasing from high
        if recovery_trend >= 0.60 and congestion >= 0.40:
            return ExpertLoadState.RECOVERING

        # Pressured
        if congestion >= CONGESTION_THRESHOLDS["balanced_max"] + 0.01:
            return ExpertLoadState.PRESSURED

        # Balanced
        if congestion <= CONGESTION_THRESHOLDS["balanced_max"]:
            return ExpertLoadState.BALANCED

        return ExpertLoadState.UNKNOWN

    # ------------------------------------------------------------------
    # Main evaluation
    # ------------------------------------------------------------------

    async def evaluate_load_balance(
        self,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> LoadBalancingResult:
        """
        Main entry point. Evaluates expert load balance for the given user context.
        Fully fail-safe — any exception returns neutral_result.
        Never sends, assigns, overrides, or contacts anyone.
        """
        try:
            if not context:
                return self._neutral_result("no_context")

            # --- Extract signals from context ---
            active_escalations = self._extract_signal(context, "active_escalations", 0.0)
            recent_escalations_24h = self._extract_signal(context, "recent_escalations_24h", 0.0)
            queue_depth = self._extract_signal(context, "queue_depth", 0.0)
            caseload_ratio = self._extract_signal(context, "expert_caseload_ratio", 0.0)
            escalation_density = self._extract_signal(context, "escalation_density", 0.0)
            handoff_volume = self._extract_signal(context, "handoff_volume", 0.0)
            capacity_headroom = self._extract_signal(context, "capacity_headroom", 1.0)
            distribution_balance_raw = self._extract_signal(context, "distribution_balance", 1.0)
            recovery_trend = self._extract_signal(context, "recovery_trend", 0.0)
            response_lag = self._extract_signal(context, "response_lag", 0.0)
            continuity_handoff_risk = self._extract_signal(context, "continuity_handoff_risk", 0.0)
            emotional_safety_buffer = self._extract_signal(context, "emotional_safety_buffer", 1.0)
            per_expert_loads = self._extract_list(context, "per_expert_loads")

            # --- Active load derived ---
            active_load = _clamp((active_escalations * 0.60) + (caseload_ratio * 0.40))

            # --- Compute scores ---
            queue_pressure = self._compute_escalation_queue_pressure(
                active_escalations, recent_escalations_24h, queue_depth
            )
            overload_risk = self._compute_expert_overload_risk(
                caseload_ratio, escalation_density, handoff_volume
            )
            congestion = self._compute_support_congestion_score(
                active_load, queue_pressure, overload_risk, response_lag
            )
            stability = self._compute_operational_stability_score(
                congestion, overload_risk, continuity_handoff_risk
            )
            sustainability = self._compute_response_sustainability(
                capacity_headroom, distribution_balance_raw, recovery_trend
            )
            dist_balance = self._compute_escalation_distribution_balance(per_expert_loads)
            integrity = self._compute_human_support_integrity(
                sustainability, 1.0 - continuity_handoff_risk, emotional_safety_buffer
            )

            # --- Classify state ---
            load_state = self._classify_load_state(
                congestion=congestion,
                overload_risk=overload_risk,
                queue_pressure=queue_pressure,
                handoff_risk=continuity_handoff_risk,
                stability=stability,
                recovery_trend=recovery_trend,
            )

            # --- Capacity ---
            capacity = CAPACITY_MAP.get(load_state, SafeAssignmentCapacity.CONSERVATIVE)

            # --- Integrity flag ---
            integrity_at_risk = integrity < INTEGRITY_AT_RISK

            now_iso = datetime.now(timezone.utc).isoformat()

            # --- Notes ---
            notes = {
                "active_escalations": round(active_escalations, 4),
                "recent_escalations_24h": round(recent_escalations_24h, 4),
                "queue_depth": round(queue_depth, 4),
                "caseload_ratio": round(caseload_ratio, 4),
                "escalation_density": round(escalation_density, 4),
                "handoff_volume": round(handoff_volume, 4),
                "capacity_headroom": round(capacity_headroom, 4),
                "recovery_trend": round(recovery_trend, 4),
                "response_lag": round(response_lag, 4),
                "per_expert_loads_count": len(per_expert_loads),
                "active_load_derived": round(active_load, 4),
                "queue_pressure": round(queue_pressure, 4),
                "overload_risk": round(overload_risk, 4),
                "congestion": round(congestion, 4),
                "stability": round(stability, 4),
                "sustainability": round(sustainability, 4),
                "dist_balance": round(dist_balance, 4),
                "integrity": round(integrity, 4),
                "integrity_at_risk": integrity_at_risk,
                "load_state": load_state.value,
                "capacity": capacity.value,
                "evaluated_at": now_iso,
            }

            result = LoadBalancingResult(
                expert_load_state=load_state.value,
                support_congestion_score=round(congestion, 4),
                escalation_queue_pressure=round(queue_pressure, 4),
                expert_overload_risk=round(overload_risk, 4),
                continuity_handoff_risk=round(continuity_handoff_risk, 4),
                operational_stability_score=round(stability, 4),
                safe_assignment_capacity=capacity.value,
                escalation_distribution_balance=round(dist_balance, 4),
                response_sustainability_score=round(sustainability, 4),
                human_support_integrity_score=round(integrity, 4),
                load_balancing_notes=notes,
                integrity_at_risk=integrity_at_risk,
                evaluated_at=now_iso,
                is_neutral=False,
            )

            # --- Persist to DB ---
            await self._persist(user_id, result)

            return result

        except Exception as exc:
            log.debug("%s evaluate_load_balance exception (non-fatal): %s", _TAG, exc)
            return self._neutral_result("exception")

    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    async def _persist(self, user_id: str, result: LoadBalancingResult) -> None:
        """Persist result to pm_client_profiles. Fail-safe — never raises."""
        try:
            db = getattr(self, "_db", None)
            if db is None:
                return
            import json
            query = """
                UPDATE pm_client_profiles SET
                    expert_load_state = $1,
                    support_congestion_score = $2,
                    escalation_queue_pressure = $3,
                    expert_overload_risk = $4,
                    continuity_handoff_risk = $5,
                    operational_stability_score = $6,
                    safe_assignment_capacity = $7,
                    escalation_distribution_balance = $8,
                    response_sustainability_score = $9,
                    human_support_integrity_score = $10,
                    load_balancing_notes = $11,
                    last_load_balancing_check = NOW()
                WHERE user_id = $12
            """
            await db.execute(
                query,
                result.expert_load_state,
                result.support_congestion_score,
                result.escalation_queue_pressure,
                result.expert_overload_risk,
                result.continuity_handoff_risk,
                result.operational_stability_score,
                result.safe_assignment_capacity,
                result.escalation_distribution_balance,
                result.response_sustainability_score,
                result.human_support_integrity_score,
                json.dumps(result.load_balancing_notes),
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
                    COUNT(*) FILTER (WHERE expert_load_state = 'BALANCED') AS balanced_count,
                    COUNT(*) FILTER (WHERE expert_load_state = 'PRESSURED') AS pressured_count,
                    COUNT(*) FILTER (WHERE expert_load_state = 'CONGESTED') AS congested_count,
                    COUNT(*) FILTER (WHERE expert_load_state = 'OVERLOADED') AS overloaded_count,
                    COUNT(*) FILTER (WHERE expert_load_state = 'RECOVERING') AS recovering_count,
                    COUNT(*) FILTER (WHERE expert_load_state = 'HANDOFF_AT_RISK') AS handoff_at_risk_count,
                    COUNT(*) FILTER (WHERE expert_load_state = 'QUEUE_CRITICAL') AS queue_critical_count,
                    COUNT(*) FILTER (WHERE expert_load_state = 'UNKNOWN') AS unknown_count,
                    ROUND(AVG(support_congestion_score)::numeric, 4) AS avg_congestion,
                    ROUND(AVG(operational_stability_score)::numeric, 4) AS avg_stability,
                    ROUND(AVG(human_support_integrity_score)::numeric, 4) AS avg_integrity,
                    ROUND(AVG(response_sustainability_score)::numeric, 4) AS avg_sustainability,
                    MAX(last_load_balancing_check) AS last_check
                FROM pm_client_profiles
                WHERE last_load_balancing_check IS NOT NULL
            """)
            if not rows:
                return {"total_evaluated": 0}
            r = rows[0]
            return {
                "total_evaluated": r["total_evaluated"],
                "state_distribution": {
                    "BALANCED": r["balanced_count"],
                    "PRESSURED": r["pressured_count"],
                    "CONGESTED": r["congested_count"],
                    "OVERLOADED": r["overloaded_count"],
                    "RECOVERING": r["recovering_count"],
                    "HANDOFF_AT_RISK": r["handoff_at_risk_count"],
                    "QUEUE_CRITICAL": r["queue_critical_count"],
                    "UNKNOWN": r["unknown_count"],
                },
                "avg_congestion_score": float(r["avg_congestion"] or 0),
                "avg_stability_score": float(r["avg_stability"] or 0),
                "avg_integrity_score": float(r["avg_integrity"] or 0),
                "avg_sustainability_score": float(r["avg_sustainability"] or 0),
                "overloaded_count": r["overloaded_count"],
                "queue_critical_count": r["queue_critical_count"],
                "last_check": r["last_check"].isoformat() if r["last_check"] else None,
            }
        except Exception as exc:
            log.debug("%s get_stats error (non-fatal): %s", _TAG, exc)
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

_engine_instance: Optional[ExpertLoadBalancingEngine] = None


def get_load_balancing_engine() -> Optional[ExpertLoadBalancingEngine]:
    """Return singleton engine if initialized, else None."""
    return ExpertLoadBalancingEngine._instance


async def init_load_balancing_engine(db=None) -> ExpertLoadBalancingEngine:
    """Initialize and return singleton. Safe to call multiple times."""
    global _engine_instance
    engine = ExpertLoadBalancingEngine.get_instance()
    await engine.initialize(db=db)
    _engine_instance = engine
    return engine

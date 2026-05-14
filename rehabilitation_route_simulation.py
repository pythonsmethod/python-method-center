import asyncio
import logging
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simulation States
# ---------------------------------------------------------------------------
SIMULATION_STATES = [
    "STABLE_SIMULATION",
    "CONTINUITY_RECOVERY_PATH",
    "PACING_STABILIZATION_PATH",
    "OVERLOAD_MITIGATION_PATH",
    "ROUTE_EROSION_RISK",
    "DISENGAGEMENT_RECOVERY_PATH",
    "LONGITUDINAL_STABILIZATION_PATH",
    "HIGH_UNCERTAINTY",
    "UNKNOWN",
]

# ---------------------------------------------------------------------------
# Threshold Constants
# ---------------------------------------------------------------------------
STABILITY_HIGH_THRESHOLD = 0.70
STABILITY_LOW_THRESHOLD = 0.35
COHERENCE_HIGH_THRESHOLD = 0.70
COHERENCE_LOW_THRESHOLD = 0.35
EROSION_RISK_HIGH = 0.65
PACING_LOW_THRESHOLD = 0.40
CONTINUITY_LOW_THRESHOLD = 0.40
TRAJECTORY_LOW_THRESHOLD = 0.40
ENGAGEMENT_LOW_THRESHOLD = 0.40
LOAD_LOW_THRESHOLD = 0.40
LONGITUDINAL_LOW_THRESHOLD = 0.40
RISK_HIGH_THRESHOLD = 0.65
ORCHESTRATION_LOW_THRESHOLD = 0.40
STRATEGY_LOW_THRESHOLD = 0.40

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------

def _get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

# ---------------------------------------------------------------------------
# Neutral result
# ---------------------------------------------------------------------------

def _neutral_result(user_id: str = "") -> dict:
    return {
        "user_id": user_id,
        "route_simulation_state": "UNKNOWN",
        "simulation_stability_score": 0.0,
        "continuity_recovery_probability": 0.0,
        "pacing_stabilization_effect": 0.0,
        "overload_mitigation_effect": 0.0,
        "route_erosion_risk_projection": 0.0,
        "disengagement_recovery_projection": 0.0,
        "orchestration_balance_projection": 0.0,
        "longitudinal_stability_projection": 0.0,
        "adaptive_strategy_projection": 0.0,
        "simulation_coherence_score": 0.0,
        "simulation_notes": {},
        "is_neutral": True,
    }

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RehabilitationRouteSimulationEngine:
    """Phase 3.16 — Governance-safe probabilistic route simulation engine.

    Read-only observer. Simulates rehabilitation route stability conditions.
    Never predicts medical outcomes. Never overrides governance layers.
    """

    _instance = None
    _initialized = False

    def __init__(self):
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "RehabilitationRouteSimulationEngine":
        if cls._instance is None:
            cls._instance = cls()
            log.info("[ROUTE_SIM] RehabilitationRouteSimulationEngine singleton created")
        return cls._instance

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            try:
                await asyncio.get_event_loop().run_in_executor(None, self._run_migration)
            except Exception as e:
                log.debug("[ROUTE_SIM] Migration skipped: %s", e)
            self._initialized = True
            log.info("[ROUTE_SIM] RehabilitationRouteSimulationEngine initialized")

    def _run_migration(self) -> None:
        conn = _get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        ALTER TABLE pm_client_profiles
                            ADD COLUMN IF NOT EXISTS route_simulation_state VARCHAR(64) DEFAULT 'UNKNOWN',
                            ADD COLUMN IF NOT EXISTS simulation_stability_score FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS continuity_recovery_probability FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS pacing_stabilization_effect FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS overload_mitigation_effect FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS route_erosion_risk_projection FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS disengagement_recovery_projection FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS orchestration_balance_projection FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS longitudinal_stability_projection FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS adaptive_strategy_projection FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS simulation_coherence_score FLOAT DEFAULT 0.0,
                            ADD COLUMN IF NOT EXISTS simulation_notes JSONB DEFAULT '{}',
                            ADD COLUMN IF NOT EXISTS last_route_simulation_check TIMESTAMPTZ DEFAULT NOW();
                        CREATE INDEX IF NOT EXISTS idx_pm_route_simulation_state
                            ON pm_client_profiles (route_simulation_state);
                        CREATE INDEX IF NOT EXISTS idx_pm_simulation_stability_score
                            ON pm_client_profiles (simulation_stability_score);
                        CREATE INDEX IF NOT EXISTS idx_pm_simulation_coherence_score
                            ON pm_client_profiles (simulation_coherence_score);
                        CREATE INDEX IF NOT EXISTS idx_pm_last_route_simulation_check
                            ON pm_client_profiles (last_route_simulation_check);
                        CREATE INDEX IF NOT EXISTS idx_pm_route_erosion_risk_projection
                            ON pm_client_profiles (route_erosion_risk_projection);
                    """)
            log.info("[ROUTE_SIM] DB migration complete")
        finally:
            conn.close()

    async def evaluate(self, user_id: str, context: dict) -> dict:
        """Public entry point. Always returns a dict. Never raises."""
        try:
            return await self._run_evaluation(user_id, context)
        except Exception as e:
            log.debug("[ROUTE_SIM] evaluate exception: %s", e)
            return _neutral_result(user_id)

    async def _run_evaluation(self, user_id: str, context: dict) -> dict:
        # Governance check — highest priority
        if context.get("human_esc") or context.get("silence_respected"):
            return _neutral_result(user_id)

        profile = await asyncio.get_event_loop().run_in_executor(
            None, self._load_profile, user_id
        )
        if not profile:
            return _neutral_result(user_id)

        signals = self._extract_signals(profile, context)
        scores = self._compute_scores(signals)
        coherence = self._compute_coherence(signals)
        state = self._determine_state(scores, coherence)
        notes = self._build_notes(signals, scores, state)

        result = {
            "user_id": user_id,
            "route_simulation_state": state,
            "simulation_stability_score": scores["simulation_stability_score"],
            "continuity_recovery_probability": scores["continuity_recovery_probability"],
            "pacing_stabilization_effect": scores["pacing_stabilization_effect"],
            "overload_mitigation_effect": scores["overload_mitigation_effect"],
            "route_erosion_risk_projection": scores["route_erosion_risk_projection"],
            "disengagement_recovery_projection": scores["disengagement_recovery_projection"],
            "orchestration_balance_projection": scores["orchestration_balance_projection"],
            "longitudinal_stability_projection": scores["longitudinal_stability_projection"],
            "adaptive_strategy_projection": scores["adaptive_strategy_projection"],
            "simulation_coherence_score": coherence,
            "simulation_notes": notes,
            "is_neutral": False,
        }

        asyncio.get_event_loop().run_in_executor(None, self._persist, user_id, result)
        return result

    def _load_profile(self, user_id: str) -> dict:
        try:
            conn = _get_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM pm_client_profiles WHERE user_id = %s",
                            (user_id,),
                        )
                        row = cur.fetchone()
                        return dict(row) if row else {}
            finally:
                conn.close()
        except Exception as e:
            log.debug("[ROUTE_SIM] _load_profile error: %s", e)
            return {}

    def _extract_signals(self, profile: dict, context: dict) -> dict:
        def _f(key: str, default: float = 0.5) -> float:
            val = profile.get(key) or context.get(key)
            try:
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        def _s(key: str, default: str = "") -> str:
            return str(profile.get(key) or context.get(key) or default)

        return {
            "continuity_score": _f("continuity_score"),
            "continuity_state": _s("continuity_state"),
            "trajectory_score": _f("trajectory_score"),
            "trajectory_state": _s("trajectory_state"),
            "rehabilitation_state": _s("rehabilitation_state"),
            "pacing_score": _f("pacing_score"),
            "pacing_intensity": _s("pacing_intensity"),
            "load_balancing_score": _f("load_balancing_score"),
            "orchestration_score": _f("orchestration_score"),
            "longitudinal_stability_score": _f("longitudinal_stability_score"),
            "longitudinal_state": _s("longitudinal_state"),
            "strategy_stability_score": _f("strategy_stability_score"),
            "strategy_state": _s("strategy_state"),
            "risk_score": _f("risk_score", 0.3),
            "behaviour_engagement_score": _f("behaviour_engagement_score"),
        }

    # ------------------------------------------------------------------
    # Scenario simulators
    # ------------------------------------------------------------------

    def _scenario_continuity_stabilization(self, s: dict) -> float:
        """Simulates continuity stabilization path projection."""
        c = s["continuity_score"]
        t = s["trajectory_score"]
        r = s["risk_score"]
        base = (c * 0.5 + t * 0.3 + (1.0 - r) * 0.2)
        if s["continuity_state"] in ("STABLE", "STRENGTHENING"):
            base = min(1.0, base + 0.10)
        return self._clamp(base)

    def _scenario_pacing_reduction(self, s: dict) -> float:
        """Simulates pacing reduction stabilization effect."""
        p = s["pacing_score"]
        c = s["continuity_score"]
        base = (p * 0.6 + c * 0.4)
        if s["pacing_intensity"] in ("LOW", "NONE"):
            base = min(1.0, base + 0.10)
        return self._clamp(base)

    def _scenario_overload_mitigation(self, s: dict) -> float:
        """Simulates overload mitigation effect projection."""
        lb = s["load_balancing_score"]
        orch = s["orchestration_score"]
        base = (lb * 0.55 + orch * 0.45)
        if lb >= LOAD_LOW_THRESHOLD and orch >= ORCHESTRATION_LOW_THRESHOLD:
            base = min(1.0, base + 0.05)
        return self._clamp(base)

    def _scenario_disengagement_recovery(self, s: dict) -> float:
        """Simulates disengagement recovery projection."""
        eng = s["behaviour_engagement_score"]
        c = s["continuity_score"]
        t = s["trajectory_score"]
        base = (eng * 0.5 + c * 0.3 + t * 0.2)
        if eng < ENGAGEMENT_LOW_THRESHOLD:
            base = max(0.0, base - 0.05)
        return self._clamp(base)

    def _scenario_route_erosion(self, s: dict) -> float:
        """Simulates route erosion risk projection (higher = more erosion risk)."""
        c = s["continuity_score"]
        t = s["trajectory_score"]
        eng = s["behaviour_engagement_score"]
        r = s["risk_score"]
        erosion = ((1.0 - c) * 0.35 + (1.0 - t) * 0.30 + (1.0 - eng) * 0.20 + r * 0.15)
        return self._clamp(erosion)

    def _scenario_orchestration_balancing(self, s: dict) -> float:
        """Simulates orchestration balancing projection."""
        orch = s["orchestration_score"]
        lb = s["load_balancing_score"]
        p = s["pacing_score"]
        base = (orch * 0.45 + lb * 0.35 + p * 0.20)
        return self._clamp(base)

    def _scenario_longitudinal_stabilization(self, s: dict) -> float:
        """Simulates longitudinal stabilization projection."""
        ls = s["longitudinal_stability_score"]
        c = s["continuity_score"]
        t = s["trajectory_score"]
        base = (ls * 0.55 + c * 0.25 + t * 0.20)
        if s["longitudinal_state"] in ("STABLE", "IMPROVING"):
            base = min(1.0, base + 0.08)
        return self._clamp(base)

    def _scenario_expert_load_redistribution(self, s: dict) -> float:
        """Simulates expert load redistribution effect."""
        lb = s["load_balancing_score"]
        orch = s["orchestration_score"]
        base = (lb * 0.60 + orch * 0.40)
        return self._clamp(base)

    def _scenario_continuity_recovery_after_disruption(self, s: dict) -> float:
        """Simulates continuity recovery after disruption."""
        c = s["continuity_score"]
        t = s["trajectory_score"]
        eng = s["behaviour_engagement_score"]
        r = s["risk_score"]
        base = (c * 0.40 + t * 0.25 + eng * 0.25 + (1.0 - r) * 0.10)
        if s["continuity_state"] in ("DISRUPTED", "FRAGILE"):
            base = max(0.0, base - 0.10)
        return self._clamp(base)

    def _scenario_adaptive_strategy_impact(self, s: dict) -> float:
        """Simulates adaptive strategy impact projection."""
        ss = s["strategy_stability_score"]
        c = s["continuity_score"]
        ls = s["longitudinal_stability_score"]
        base = (ss * 0.50 + c * 0.30 + ls * 0.20)
        if s["strategy_state"] in ("MAINTAIN", "REINFORCE"):
            base = min(1.0, base + 0.07)
        return self._clamp(base)

    # ------------------------------------------------------------------
    # Score aggregation
    # ------------------------------------------------------------------

    def _compute_scores(self, s: dict) -> dict:
        continuity_recovery = (
            self._scenario_continuity_stabilization(s) * 0.55
            + self._scenario_continuity_recovery_after_disruption(s) * 0.45
        )
        pacing_stab = self._scenario_pacing_reduction(s)
        overload_mit = self._scenario_overload_mitigation(s)
        disengagement = self._scenario_disengagement_recovery(s)
        erosion = self._scenario_route_erosion(s)
        orchestration = (
            self._scenario_orchestration_balancing(s) * 0.55
            + self._scenario_expert_load_redistribution(s) * 0.45
        )
        longitudinal = self._scenario_longitudinal_stabilization(s)
        adaptive = self._scenario_adaptive_strategy_impact(s)

        # Overall stability: positive projections weighted, minus erosion penalty
        positive = (
            continuity_recovery * 0.20
            + pacing_stab * 0.12
            + overload_mit * 0.12
            + disengagement * 0.15
            + orchestration * 0.13
            + longitudinal * 0.15
            + adaptive * 0.13
        )
        stability = self._clamp(positive - erosion * 0.20)

        return {
            "simulation_stability_score": self._clamp(stability),
            "continuity_recovery_probability": self._clamp(continuity_recovery),
            "pacing_stabilization_effect": self._clamp(pacing_stab),
            "overload_mitigation_effect": self._clamp(overload_mit),
            "route_erosion_risk_projection": self._clamp(erosion),
            "disengagement_recovery_projection": self._clamp(disengagement),
            "orchestration_balance_projection": self._clamp(orchestration),
            "longitudinal_stability_projection": self._clamp(longitudinal),
            "adaptive_strategy_projection": self._clamp(adaptive),
        }

    def _compute_coherence(self, s: dict) -> float:
        """Coherence = internal signal consistency (low variance = high coherence)."""
        scores = [
            s["continuity_score"],
            s["trajectory_score"],
            s["pacing_score"],
            s["load_balancing_score"],
            s["orchestration_score"],
            s["longitudinal_stability_score"],
            s["strategy_stability_score"],
            s["behaviour_engagement_score"],
        ]
        if not scores:
            return 0.0
        mean = sum(scores) / len(scores)
        variance = sum((x - mean) ** 2 for x in scores) / len(scores)
        # Low variance → high coherence
        coherence = max(0.0, 1.0 - (variance * 4.0))
        return self._clamp(coherence)

    def _determine_state(self, scores: dict, coherence: float) -> str:
        """Map scores → simulation state."""
        if coherence < COHERENCE_LOW_THRESHOLD:
            return "HIGH_UNCERTAINTY"

        stability = scores["simulation_stability_score"]
        erosion = scores["route_erosion_risk_projection"]
        continuity = scores["continuity_recovery_probability"]
        pacing = scores["pacing_stabilization_effect"]
        overload = scores["overload_mitigation_effect"]
        disengagement = scores["disengagement_recovery_projection"]
        longitudinal = scores["longitudinal_stability_projection"]

        if stability >= STABILITY_HIGH_THRESHOLD and erosion < 0.35:
            return "STABLE_SIMULATION"

        if erosion >= EROSION_RISK_HIGH:
            return "ROUTE_EROSION_RISK"

        # Dominant projection wins
        projections = {
            "CONTINUITY_RECOVERY_PATH": continuity,
            "PACING_STABILIZATION_PATH": pacing,
            "OVERLOAD_MITIGATION_PATH": overload,
            "DISENGAGEMENT_RECOVERY_PATH": disengagement,
            "LONGITUDINAL_STABILIZATION_PATH": longitudinal,
        }
        dominant = max(projections, key=projections.get)
        dominant_score = projections[dominant]

        if dominant_score >= STABILITY_LOW_THRESHOLD:
            return dominant

        return "UNKNOWN"

    def _build_notes(self, signals: dict, scores: dict, state: str) -> dict:
        return {
            "state": state,
            "simulation_stability_score": scores["simulation_stability_score"],
            "route_erosion_risk_projection": scores["route_erosion_risk_projection"],
            "simulation_coherence_note": (
                "high_coherence" if scores.get("simulation_stability_score", 0) >= COHERENCE_HIGH_THRESHOLD
                else "moderate_coherence"
            ),
            "dominant_signals": {
                "continuity_score": signals["continuity_score"],
                "trajectory_score": signals["trajectory_score"],
                "pacing_score": signals["pacing_score"],
                "behaviour_engagement_score": signals["behaviour_engagement_score"],
                "longitudinal_stability_score": signals["longitudinal_stability_score"],
                "strategy_stability_score": signals["strategy_stability_score"],
            },
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def _persist(self, user_id: str, result: dict) -> None:
        try:
            conn = _get_conn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE pm_client_profiles SET
                                route_simulation_state = %s,
                                simulation_stability_score = %s,
                                continuity_recovery_probability = %s,
                                pacing_stabilization_effect = %s,
                                overload_mitigation_effect = %s,
                                route_erosion_risk_projection = %s,
                                disengagement_recovery_projection = %s,
                                orchestration_balance_projection = %s,
                                longitudinal_stability_projection = %s,
                                adaptive_strategy_projection = %s,
                                simulation_coherence_score = %s,
                                simulation_notes = %s,
                                last_route_simulation_check = NOW()
                            WHERE user_id = %s
                        """, (
                            result["route_simulation_state"],
                            result["simulation_stability_score"],
                            result["continuity_recovery_probability"],
                            result["pacing_stabilization_effect"],
                            result["overload_mitigation_effect"],
                            result["route_erosion_risk_projection"],
                            result["disengagement_recovery_projection"],
                            result["orchestration_balance_projection"],
                            result["longitudinal_stability_projection"],
                            result["adaptive_strategy_projection"],
                            result["simulation_coherence_score"],
                            psycopg2.extras.Json(result["simulation_notes"]),
                            user_id,
                        ))
            finally:
                conn.close()
        except Exception as e:
            log.debug("[ROUTE_SIM] _persist error: %s", e)

    async def get_stats(self) -> dict:
        """Dashboard stats aggregation."""
        try:
            def _query():
                conn = _get_conn()
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT
                                    COUNT(*) AS total,
                                    AVG(simulation_stability_score) AS avg_stability,
                                    AVG(simulation_coherence_score) AS avg_coherence,
                                    AVG(route_erosion_risk_projection) AS avg_erosion_risk,
                                    COUNT(*) FILTER (WHERE route_simulation_state = 'STABLE_SIMULATION') AS stable_count,
                                    COUNT(*) FILTER (WHERE route_simulation_state = 'HIGH_UNCERTAINTY') AS high_uncertainty_count,
                                    COUNT(*) FILTER (WHERE route_simulation_state = 'ROUTE_EROSION_RISK') AS erosion_risk_count,
                                    COUNT(*) FILTER (WHERE simulation_stability_score >= 0.7) AS high_stability_count
                                FROM pm_client_profiles
                                WHERE last_route_simulation_check IS NOT NULL
                            """)
                            row = cur.fetchone()
                            return dict(row) if row else {}
                finally:
                    conn.close()

            return await asyncio.get_event_loop().run_in_executor(None, _query)
        except Exception as e:
            log.debug("[ROUTE_SIM] get_stats error: %s", e)
            return {}


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_engine: RehabilitationRouteSimulationEngine = None


def get_route_simulation_engine() -> RehabilitationRouteSimulationEngine:
    global _engine
    if _engine is None:
        _engine = RehabilitationRouteSimulationEngine.get_instance()
    return _engine


async def init_route_simulation_engine() -> None:
    """Initialize the singleton engine. Called once at startup."""
    engine = get_route_simulation_engine()
    await engine.initialize()


async def evaluate_route_simulation(user_id: str, context: dict) -> dict:
    """Evaluate route simulation for a user. Always returns a dict."""
    try:
        engine = get_route_simulation_engine()
        return await engine.evaluate(user_id, context)
    except Exception as e:
        log.debug("[ROUTE_SIM] evaluate_route_simulation error: %s", e)
        return _neutral_result(user_id)

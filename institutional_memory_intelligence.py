import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 3.19 — Institutional Memory Intelligence
# Read-only historical pattern observer. No outbound calls.
# No self-modification. No autonomous learning. No governance mutation.
# No individual client identifiers. All scores clamped [0.0, 1.0].
# neutral_result on all exceptions.
# ---------------------------------------------------------------------------

INSTITUTIONAL_MEMORY_STATES = [
    "STABLE_INSTITUTIONAL_MEMORY",
    "CONTINUITY_PATTERN_FORMING",
    "OVERLOAD_PATTERN_DETECTED",
    "GOVERNANCE_STRAIN_PATTERN",
    "PACING_EVOLUTION_PATTERN",
    "STABILIZATION_EFFECTIVENESS_PATTERN",
    "ROUTE_EROSION_HISTORY",
    "RECOVERY_RESILIENCE_PATTERN",
    "UNKNOWN",
]

HISTORY_WINDOW = 48
MIN_HISTORY_SAMPLE = 3


def neutral_result() -> dict:
    return {
        "institutional_memory_state": "UNKNOWN",
        "governance_pattern_score": 0.0,
        "overload_pattern_score": 0.0,
        "pacing_pattern_score": 0.0,
        "continuity_resilience_score": 0.0,
        "stabilization_effectiveness_score": 0.0,
        "route_erosion_pattern_score": 0.0,
        "recovery_resilience_pattern_score": 0.0,
        "dispatcher_safety_pattern_score": 0.0,
        "silence_integrity_pattern_score": 0.0,
        "institutional_stability_score": 0.0,
        "historical_sample_size": 0,
        "institutional_memory_notes": {},
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "is_neutral": True,
    }


def _clamp(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


class InstitutionalMemoryEngine:
    _instance = None
    _initialized = False

    def __init__(self):
        log.info("[INST_MEM] InstitutionalMemoryEngine singleton created")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = InstitutionalMemoryEngine()
        return cls._instance

    async def initialize(self, db_pool) -> None:
        if self._initialized:
            return
        self._db_pool = db_pool
        self._initialized = True
        log.info("[INST_MEM] InstitutionalMemoryEngine initialized")

    # ------------------------------------------------------------------
    # Fetch historical window from pm_center_continuity_metrics
    # ------------------------------------------------------------------

    async def _fetch_history(self, conn) -> list:
        try:
            rows = await conn.fetch(
                "SELECT * FROM pm_center_continuity_metrics "
                "ORDER BY checked_at DESC LIMIT $1",
                HISTORY_WINDOW,
            )
            return list(rows) if rows else []
        except Exception as e:
            log.debug(f"[INST_MEM] _fetch_history error: {e}")
            return []

    # ------------------------------------------------------------------
    # Evaluators — each returns float [0.0, 1.0], never raises
    # ------------------------------------------------------------------

    def _evaluate_governance_pattern(self, rows: list) -> float:
        try:
            vals = [r["governance_stability_score"] for r in rows if r["governance_stability_score"] is not None]
            if not vals:
                return 0.0
            return _clamp(sum(vals) / len(vals))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_governance_pattern error: {e}")
            return 0.0

    def _evaluate_overload_pattern(self, rows: list) -> float:
        try:
            vals = [r["systemic_overload_score"] for r in rows if r["systemic_overload_score"] is not None]
            if not vals:
                return 0.0
            return _clamp(sum(vals) / len(vals))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_overload_pattern error: {e}")
            return 0.0

    def _evaluate_pacing_pattern(self, rows: list) -> float:
        try:
            vals = [r["pacing_sustainability_score"] for r in rows if r["pacing_sustainability_score"] is not None]
            if not vals:
                return 0.0
            return _clamp(sum(vals) / len(vals))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_pacing_pattern error: {e}")
            return 0.0

    def _evaluate_continuity_resilience(self, rows: list) -> float:
        try:
            vals = [r["global_continuity_health_score"] for r in rows if r["global_continuity_health_score"] is not None]
            if not vals:
                return 0.0
            return _clamp(sum(vals) / len(vals))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_continuity_resilience error: {e}")
            return 0.0

    def _evaluate_stabilization_effectiveness(self, rows: list) -> float:
        try:
            vals = [r["systemic_disengagement_score"] for r in rows if r["systemic_disengagement_score"] is not None]
            if not vals:
                return 0.0
            avg_disengagement = sum(vals) / len(vals)
            return _clamp(1.0 - avg_disengagement)
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_stabilization_effectiveness error: {e}")
            return 0.0

    def _evaluate_route_erosion_pattern(self, rows: list) -> float:
        try:
            if not rows:
                return 0.0
            erosion_count = sum(1 for r in rows if r["continuity_erosion_cluster_detected"] is True)
            return _clamp(erosion_count / len(rows))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_route_erosion_pattern error: {e}")
            return 0.0

    def _evaluate_recovery_resilience(self, rows: list) -> float:
        try:
            vals = [r["recovery_pattern_strength"] for r in rows if r["recovery_pattern_strength"] is not None]
            if not vals:
                return 0.0
            return _clamp(sum(vals) / len(vals))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_recovery_resilience error: {e}")
            return 0.0

    def _evaluate_dispatcher_safety_pattern(self, rows: list) -> float:
        try:
            vals = [r["dispatcher_alignment_score"] for r in rows if r["dispatcher_alignment_score"] is not None]
            if not vals:
                return 0.0
            return _clamp(sum(vals) / len(vals))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_dispatcher_safety_pattern error: {e}")
            return 0.0

    def _evaluate_silence_integrity_pattern(self, rows: list) -> float:
        try:
            vals = [r["center_silence_integrity_score"] for r in rows if r["center_silence_integrity_score"] is not None]
            if not vals:
                return 0.0
            return _clamp(sum(vals) / len(vals))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_silence_integrity_pattern error: {e}")
            return 0.0

    def _evaluate_institutional_stability(
        self,
        governance: float,
        overload: float,
        pacing: float,
        continuity: float,
        stabilization: float,
        route_erosion: float,
        recovery: float,
        dispatcher: float,
        silence: float,
    ) -> float:
        try:
            scores = [
                governance,
                1.0 - overload,
                pacing,
                continuity,
                stabilization,
                1.0 - route_erosion,
                recovery,
                dispatcher,
                silence,
            ]
            return _clamp(sum(scores) / len(scores))
        except Exception as e:
            log.debug(f"[INST_MEM] _evaluate_institutional_stability error: {e}")
            return 0.0

    # ------------------------------------------------------------------
    # State classification
    # ------------------------------------------------------------------

    def _classify_state(
        self,
        sample_size: int,
        institutional_stability: float,
        governance: float,
        overload: float,
        route_erosion: float,
        recovery: float,
        pacing: float,
        stabilization: float,
        continuity: float,
    ) -> str:
        if sample_size < MIN_HISTORY_SAMPLE:
            return "UNKNOWN"
        if institutional_stability >= 0.75 and governance >= 0.70:
            return "STABLE_INSTITUTIONAL_MEMORY"
        if overload >= 0.40:
            return "OVERLOAD_PATTERN_DETECTED"
        if governance <= 0.35:
            return "GOVERNANCE_STRAIN_PATTERN"
        if route_erosion >= 0.35:
            return "ROUTE_EROSION_HISTORY"
        if recovery >= 0.55:
            return "RECOVERY_RESILIENCE_PATTERN"
        if pacing <= 0.40 or pacing >= 0.80:
            return "PACING_EVOLUTION_PATTERN"
        if stabilization >= 0.70:
            return "STABILIZATION_EFFECTIVENESS_PATTERN"
        if continuity <= 0.60:
            return "CONTINUITY_PATTERN_FORMING"
        return "STABLE_INSTITUTIONAL_MEMORY"

    # ------------------------------------------------------------------
    # Write snapshot to pm_institutional_memory
    # ------------------------------------------------------------------

    async def _write_snapshot(self, conn, result: dict) -> None:
        try:
            import json
            await conn.execute(
                "INSERT INTO pm_institutional_memory ("
                "recorded_at, institutional_memory_state, governance_pattern_score, "
                "overload_pattern_score, pacing_pattern_score, continuity_resilience_score, "
                "stabilization_effectiveness_score, route_erosion_pattern_score, "
                "recovery_resilience_pattern_score, dispatcher_safety_pattern_score, "
                "silence_integrity_pattern_score, institutional_stability_score, "
                "historical_sample_size, institutional_memory_notes"
                ") VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
                result["institutional_memory_state"],
                result["governance_pattern_score"],
                result["overload_pattern_score"],
                result["pacing_pattern_score"],
                result["continuity_resilience_score"],
                result["stabilization_effectiveness_score"],
                result["route_erosion_pattern_score"],
                result["recovery_resilience_pattern_score"],
                result["dispatcher_safety_pattern_score"],
                result["silence_integrity_pattern_score"],
                result["institutional_stability_score"],
                result["historical_sample_size"],
                json.dumps(result["institutional_memory_notes"]),
            )
        except Exception as e:
            log.debug(f"[INST_MEM] _write_snapshot error: {e}")

    # ------------------------------------------------------------------
    # Main evaluate
    # ------------------------------------------------------------------

    async def evaluate(self) -> dict:
        try:
            if not self._initialized or not self._db_pool:
                return neutral_result()

            async with self._db_pool.acquire() as conn:
                rows = await self._fetch_history(conn)
                sample_size = len(rows)

                governance = self._evaluate_governance_pattern(rows)
                overload = self._evaluate_overload_pattern(rows)
                pacing = self._evaluate_pacing_pattern(rows)
                continuity = self._evaluate_continuity_resilience(rows)
                stabilization = self._evaluate_stabilization_effectiveness(rows)
                route_erosion = self._evaluate_route_erosion_pattern(rows)
                recovery = self._evaluate_recovery_resilience(rows)
                dispatcher = self._evaluate_dispatcher_safety_pattern(rows)
                silence = self._evaluate_silence_integrity_pattern(rows)
                institutional = self._evaluate_institutional_stability(
                    governance=governance,
                    overload=overload,
                    pacing=pacing,
                    continuity=continuity,
                    stabilization=stabilization,
                    route_erosion=route_erosion,
                    recovery=recovery,
                    dispatcher=dispatcher,
                    silence=silence,
                )

                state = self._classify_state(
                    sample_size=sample_size,
                    institutional_stability=institutional,
                    governance=governance,
                    overload=overload,
                    route_erosion=route_erosion,
                    recovery=recovery,
                    pacing=pacing,
                    stabilization=stabilization,
                    continuity=continuity,
                )

                result = {
                    "institutional_memory_state": state,
                    "governance_pattern_score": governance,
                    "overload_pattern_score": overload,
                    "pacing_pattern_score": pacing,
                    "continuity_resilience_score": continuity,
                    "stabilization_effectiveness_score": stabilization,
                    "route_erosion_pattern_score": route_erosion,
                    "recovery_resilience_pattern_score": recovery,
                    "dispatcher_safety_pattern_score": dispatcher,
                    "silence_integrity_pattern_score": silence,
                    "institutional_stability_score": institutional,
                    "historical_sample_size": sample_size,
                    "institutional_memory_notes": {
                        "history_window": HISTORY_WINDOW,
                        "rows_used": sample_size,
                        "source": "pm_center_continuity_metrics",
                    },
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                    "is_neutral": False,
                }

                await self._write_snapshot(conn, result)
                return result

        except Exception as e:
            log.debug(f"[INST_MEM] evaluate error: {e}")
            return neutral_result()


# ---------------------------------------------------------------------------
# Module-level interface
# ---------------------------------------------------------------------------

_engine = None


def get_institutional_memory_engine():
    global _engine
    return _engine


async def init_institutional_memory_engine(db_pool) -> None:
    global _engine
    engine = InstitutionalMemoryEngine.get_instance()
    await engine.initialize(db_pool)
    _engine = engine


async def evaluate_institutional_memory() -> dict:
    global _engine
    if _engine is None:
        return neutral_result()
    return await _engine.evaluate()

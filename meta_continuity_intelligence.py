import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 3.18 — Meta-Continuity Intelligence
# Center-wide continuity health observer.
# Read-only aggregator. No outbound calls. No individual client mutation.
# No prediction language. No medical conclusions.
# All scores clamped [0.0, 1.0]. neutral_result on all exceptions.
# ---------------------------------------------------------------------------

META_CONTINUITY_STATES = [
    "HEALTHY_CONTINUITY",
    "CONTINUITY_STRAIN",
    "SYSTEMIC_DISENGAGEMENT",
    "OVERLOAD_CLUSTER",
    "PACING_INSTABILITY_CLUSTER",
    "GOVERNANCE_STRAIN",
    "ROUTE_EROSION_CLUSTER",
    "RECOVERY_PATTERN_ACTIVE",
    "UNKNOWN",
]

MIN_SAMPLE_SIZE = 3


def neutral_result() -> dict:
    return {
        "meta_continuity_state": "UNKNOWN",
        "global_continuity_health_score": 0.0,
        "center_route_stability_score": 0.0,
        "systemic_disengagement_score": 0.0,
        "systemic_overload_score": 0.0,
        "pacing_sustainability_score": 0.0,
        "governance_stability_score": 0.0,
        "continuity_erosion_cluster_detected": False,
        "recovery_pattern_strength": 0.0,
        "strategy_effectiveness_signal": 0.0,
        "route_durability_signal": 0.0,
        "center_silence_integrity_score": 0.0,
        "dispatcher_alignment_score": 0.0,
        "sample_size": 0,
        "meta_continuity_notes": {},
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "is_neutral": True,
    }


def _clamp(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


class MetaContinuityEngine:
    _instance = None
    _initialized = False

    def __init__(self):
        log.info("[META_CONT] MetaContinuityEngine singleton created")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = MetaContinuityEngine()
        return cls._instance

    async def initialize(self, db_pool) -> None:
        if self._initialized:
            return
        self._db_pool = db_pool
        self._initialized = True
        log.info("[META_CONT] MetaContinuityEngine initialized")

    async def _evaluate_global_continuity_health(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT AVG(COALESCE(continuity_score, 0.5)) as avg_score, COUNT(*) as cnt "
                "FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or (row["cnt"] or 0) < MIN_SAMPLE_SIZE:
                return 0.0
            return _clamp(row["avg_score"] or 0.0)
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_global_continuity_health error: {e}")
            return 0.0

    async def _evaluate_center_route_stability(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FILTER (WHERE route_state IN ('ACTIVE','STABLE','ENGAGED')) AS stable_cnt, "
                "COUNT(*) AS total_cnt FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or (row["total_cnt"] or 0) < MIN_SAMPLE_SIZE:
                return 0.0
            return _clamp((row["stable_cnt"] or 0) / (row["total_cnt"] or 1))
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_center_route_stability error: {e}")
            return 0.0

    async def _evaluate_systemic_disengagement(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FILTER (WHERE silence_respected = TRUE "
                "OR route_state IN ('SILENT','DISENGAGED','DROPOUT')) AS disengaged_cnt, "
                "COUNT(*) AS total_cnt FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or (row["total_cnt"] or 0) < MIN_SAMPLE_SIZE:
                return 0.0
            return _clamp((row["disengaged_cnt"] or 0) / (row["total_cnt"] or 1))
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_systemic_disengagement error: {e}")
            return 0.0

    async def _evaluate_systemic_overload(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FILTER (WHERE load_balancing_state IN ('OVERLOADED','CRITICAL','HIGH_LOAD')) AS overloaded_cnt, "
                "COUNT(*) AS total_cnt FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or (row["total_cnt"] or 0) < MIN_SAMPLE_SIZE:
                return 0.0
            return _clamp((row["overloaded_cnt"] or 0) / (row["total_cnt"] or 1))
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_systemic_overload error: {e}")
            return 0.0

    async def _evaluate_pacing_sustainability(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT AVG(COALESCE(pacing_score, 0.5)) as avg_pacing "
                "FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or row["avg_pacing"] is None:
                return 0.0
            return _clamp(row["avg_pacing"])
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_pacing_sustainability error: {e}")
            return 0.0

    async def _evaluate_governance_stability(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT AVG(COALESCE(governance_stability_score, 0.5)) as avg_gov "
                "FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or row["avg_gov"] is None:
                return 0.0
            return _clamp(row["avg_gov"])
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_governance_stability error: {e}")
            return 0.0

    async def _evaluate_continuity_erosion_cluster(self, conn) -> tuple:
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FILTER (WHERE continuity_trend IN ('DECLINING','ERODING','DEGRADED') "
                "OR continuity_score < 0.35) AS eroding_cnt, "
                "COUNT(*) AS total_cnt FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or (row["total_cnt"] or 0) < MIN_SAMPLE_SIZE:
                return False, 0.0
            ratio = (row["eroding_cnt"] or 0) / (row["total_cnt"] or 1)
            return ratio >= 0.30, _clamp(ratio)
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_continuity_erosion_cluster error: {e}")
            return False, 0.0

    async def _evaluate_recovery_pattern_strength(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FILTER (WHERE route_state IN ('RECOVERY','RECOVERING','RESUMED')) AS recovery_cnt, "
                "COUNT(*) AS total_cnt FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or (row["total_cnt"] or 0) < MIN_SAMPLE_SIZE:
                return 0.0
            return _clamp((row["recovery_cnt"] or 0) / (row["total_cnt"] or 1))
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_recovery_pattern_strength error: {e}")
            return 0.0

    async def _evaluate_strategy_effectiveness(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT AVG(COALESCE(strategy_alignment_score, 0.5)) as avg_strategy "
                "FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or row["avg_strategy"] is None:
                return 0.0
            return _clamp(row["avg_strategy"])
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_strategy_effectiveness error: {e}")
            return 0.0

    async def _evaluate_route_durability(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT AVG(COALESCE(route_durability_score, 0.5)) as avg_durability "
                "FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or row["avg_durability"] is None:
                return 0.0
            return _clamp(row["avg_durability"])
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_route_durability error: {e}")
            return 0.0

    async def _evaluate_center_silence_integrity(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FILTER (WHERE silence_policy_compliant = TRUE) AS compliant_cnt, "
                "COUNT(*) FILTER (WHERE silence_respected IS NOT NULL) AS checked_cnt "
                "FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or (row["checked_cnt"] or 0) < MIN_SAMPLE_SIZE:
                return 1.0
            return _clamp((row["compliant_cnt"] or 0) / (row["checked_cnt"] or 1))
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_center_silence_integrity error: {e}")
            return 0.0

    async def _evaluate_dispatcher_alignment(self, conn) -> float:
        try:
            row = await conn.fetchrow(
                "SELECT AVG(COALESCE(dispatcher_safety_score, 0.8)) as avg_disp "
                "FROM pm_client_profiles WHERE is_active = TRUE"
            )
            if not row or row["avg_disp"] is None:
                return 0.0
            return _clamp(row["avg_disp"])
        except Exception as e:
            log.debug(f"[META_CONT] _evaluate_dispatcher_alignment error: {e}")
            return 0.0

    def _classify_state(
        self,
        sample_size,
        global_health,
        disengagement,
        overload,
        pacing,
        governance,
        erosion_detected,
        route_durability,
        recovery_strength,
    ) -> str:
        if sample_size < MIN_SAMPLE_SIZE:
            return "UNKNOWN"
        if global_health >= 0.75 and governance >= 0.70:
            return "HEALTHY_CONTINUITY"
        if disengagement >= 0.40:
            return "SYSTEMIC_DISENGAGEMENT"
        if overload >= 0.40:
            return "OVERLOAD_CLUSTER"
        if pacing <= 0.35:
            return "PACING_INSTABILITY_CLUSTER"
        if governance <= 0.35:
            return "GOVERNANCE_STRAIN"
        if erosion_detected and route_durability <= 0.40:
            return "ROUTE_EROSION_CLUSTER"
        if recovery_strength >= 0.50:
            return "RECOVERY_PATTERN_ACTIVE"
        if global_health <= 0.55:
            return "CONTINUITY_STRAIN"
        return "HEALTHY_CONTINUITY"

    async def _write_result(self, conn, result: dict) -> None:
        try:
            import json
            await conn.execute(
                "INSERT INTO pm_center_continuity_metrics ("
                "checked_at, meta_continuity_state, global_continuity_health_score, "
                "center_route_stability_score, systemic_disengagement_score, "
                "systemic_overload_score, pacing_sustainability_score, "
                "governance_stability_score, continuity_erosion_cluster_detected, "
                "recovery_pattern_strength, strategy_effectiveness_signal, "
                "route_durability_signal, center_silence_integrity_score, "
                "dispatcher_alignment_score, sample_size, meta_continuity_notes"
                ") VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
                result["meta_continuity_state"],
                result["global_continuity_health_score"],
                result["center_route_stability_score"],
                result["systemic_disengagement_score"],
                result["systemic_overload_score"],
                result["pacing_sustainability_score"],
                result["governance_stability_score"],
                result["continuity_erosion_cluster_detected"],
                result["recovery_pattern_strength"],
                result["strategy_effectiveness_signal"],
                result["route_durability_signal"],
                result["center_silence_integrity_score"],
                result["dispatcher_alignment_score"],
                result["sample_size"],
                json.dumps(result["meta_continuity_notes"]),
            )
        except Exception as e:
            log.debug(f"[META_CONT] _write_result error: {e}")

    async def evaluate(self) -> dict:
        try:
            if not self._initialized or not self._db_pool:
                return neutral_result()
            async with self._db_pool.acquire() as conn:
                try:
                    sample_row = await conn.fetchrow(
                        "SELECT COUNT(*) AS cnt FROM pm_client_profiles WHERE is_active = TRUE"
                    )
                    sample_size = int(sample_row["cnt"] or 0) if sample_row else 0
                except Exception:
                    sample_size = 0

                global_health = await self._evaluate_global_continuity_health(conn)
                route_stability = await self._evaluate_center_route_stability(conn)
                disengagement = await self._evaluate_systemic_disengagement(conn)
                overload = await self._evaluate_systemic_overload(conn)
                pacing = await self._evaluate_pacing_sustainability(conn)
                governance = await self._evaluate_governance_stability(conn)
                erosion_detected, erosion_score = await self._evaluate_continuity_erosion_cluster(conn)
                recovery_strength = await self._evaluate_recovery_pattern_strength(conn)
                strategy = await self._evaluate_strategy_effectiveness(conn)
                route_durability = await self._evaluate_route_durability(conn)
                silence_integrity = await self._evaluate_center_silence_integrity(conn)
                dispatcher_align = await self._evaluate_dispatcher_alignment(conn)

                state = self._classify_state(
                    sample_size=sample_size,
                    global_health=global_health,
                    disengagement=disengagement,
                    overload=overload,
                    pacing=pacing,
                    governance=governance,
                    erosion_detected=erosion_detected,
                    route_durability=route_durability,
                    recovery_strength=recovery_strength,
                )

                result = {
                    "meta_continuity_state": state,
                    "global_continuity_health_score": global_health,
                    "center_route_stability_score": route_stability,
                    "systemic_disengagement_score": disengagement,
                    "systemic_overload_score": overload,
                    "pacing_sustainability_score": pacing,
                    "governance_stability_score": governance,
                    "continuity_erosion_cluster_detected": erosion_detected,
                    "recovery_pattern_strength": recovery_strength,
                    "strategy_effectiveness_signal": strategy,
                    "route_durability_signal": route_durability,
                    "center_silence_integrity_score": silence_integrity,
                    "dispatcher_alignment_score": dispatcher_align,
                    "sample_size": sample_size,
                    "meta_continuity_notes": {
                        "erosion_score": round(erosion_score, 4),
                        "state_basis": "center_wide_aggregation",
                    },
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                    "is_neutral": False,
                }
                await self._write_result(conn, result)
                return result
        except Exception as e:
            log.debug(f"[META_CONT] evaluate error: {e}")
            return neutral_result()


# ---------------------------------------------------------------------------
# Module-level interface
# ---------------------------------------------------------------------------

_engine = None


def get_meta_continuity_engine():
    global _engine
    return _engine


async def init_meta_continuity_engine(db_pool) -> None:
    global _engine
    engine = MetaContinuityEngine.get_instance()
    await engine.initialize(db_pool)
    _engine = engine


async def evaluate_meta_continuity() -> dict:
    global _engine
    if _engine is None:
        return neutral_result()
    return await _engine.evaluate()

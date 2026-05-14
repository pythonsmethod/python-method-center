"""
longitudinal_rehabilitation_modeling.py
Phase 3.14 — Longitudinal Rehabilitation Modeling Engine

Goal:
Analyzes long-term rehabilitation dynamics across extended time horizons
(weeks, months) to understand route durability, recurring instability patterns,
rehabilitation resilience, and continuity evolution over time.

IMMUTABLE CONSTRAINT:
This module MUST NEVER produce actions that:
- Send messages directly to users
- Call Telegram, SendPulse, OpenAI, or any outbound sender
- Call the dispatcher directly
- Predict disease outcomes, relapse, or medical events
- Create fear dynamics or urgency
- Override human_escalation, silence_respect, recovery_policy, or Central Orchestrator
- Make medical conclusions or prescribe treatment
- Manipulate users or create urgency

Governance hierarchy position:
human_escalation > silence_respect > recovery_policy > emotional_safety >
continuity_logic > trajectory_intelligence > rehabilitation_state_machine >
multi_stage_orchestration > dynamic_pacing_intelligence > expert_load_balancing >
central_cognitive_orchestrator > longitudinal_rehabilitation_modeling
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

log = logging.getLogger(__name__)

# ── Longitudinal State Definitions ─────────────────────────────────────────────

LONG_TERM_STATES = {
    "STABLE_PROGRESSION":     "Sustained positive trajectory, low instability cycles",
    "DURABLE_ENGAGEMENT":     "Consistent engagement rhythms, high continuity sustainability",
    "RESILIENT_RECOVERY":     "Repeated disruptions followed by strong route recovery",
    "ADAPTIVE_PACING":        "Long-term pacing patterns show healthy adaptation over time",
    "RECURRING_INSTABILITY":  "Repeating cycles of instability detected across history",
    "CONTINUITY_EROSION":     "Gradual degradation of engagement and continuity over time",
    "DISENGAGEMENT_PATTERN":  "Recurring disengagement loops detected across history",
    "POST_DISRUPTION_RECOVERY": "Currently recovering from disruption; history shows recovery capacity",
    "UNKNOWN":                "Insufficient history or data unavailable",
}

# Analysis windows (days)
WINDOW_SHORT  = 14   # instability cycle detection
WINDOW_MEDIUM = 30   # continuity trends, pacing adaptation
WINDOW_LONG   = 90   # route durability, persistence

# Thresholds
INSTABILITY_CYCLE_THRESHOLD    = 3    # recurring_instability_detected
DISENGAGEMENT_GAP_DAYS         = 7    # gap length to count as disengagement
DISENGAGEMENT_CYCLE_THRESHOLD  = 2    # disengagement_cycle_detected
EROSION_RISK_HIGH_THRESHOLD    = 0.65
STABILITY_HIGH_THRESHOLD       = 0.70
RESILIENCE_HIGH_THRESHOLD      = 0.65
PERSISTENCE_HIGH_THRESHOLD     = 0.65
DURABILITY_HIGH_THRESHOLD      = 0.65
MIN_HISTORY_DAYS               = 7    # minimum days of history required


# ── Neutral Result ──────────────────────────────────────────────────────────────

def _neutral_result() -> Dict[str, Any]:
    """Return safe neutral result on any exception or insufficient data."""
    return {
        "long_term_rehabilitation_state":  "UNKNOWN",
        "longitudinal_stability_score":    0.0,
        "rehabilitation_resilience_score": 0.0,
        "continuity_sustainability_score": 0.0,
        "recurring_instability_detected":  False,
        "disengagement_cycle_detected":    False,
        "pacing_adaptation_quality":       0.0,
        "recovery_after_disruption_score": 0.0,
        "long_term_route_durability":      0.0,
        "continuity_erosion_risk":         0.0,
        "rehabilitation_persistence_score":0.0,
        "longitudinal_coherence_score":    0.0,
        "longitudinal_notes":              {},
        "last_longitudinal_check":         None,
    }


# ── Engine ──────────────────────────────────────────────────────────────────────

class LongitudinalRehabilitationModelingEngine:
    """
    Longitudinal Rehabilitation Modeling Engine.

    Analyzes long-term rehabilitation continuity patterns only.
    Does NOT predict outcomes, forecast relapse, or make medical conclusions.
    """

    _instance: Optional["LongitudinalRehabilitationModelingEngine"] = None
    _initialized: bool = False

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        log.info("[LONGITUDINAL] LongitudinalRehabilitationModelingEngine singleton created")

    # ── Singleton ───────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "LongitudinalRehabilitationModelingEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if not self._initialized:
                self._initialized = True
                log.info("[LONGITUDINAL] LongitudinalRehabilitationModelingEngine initialized")

    # ── Public API ──────────────────────────────────────────────────────────────

    async def analyze(self, user_id: Any, db: Any = None) -> Dict[str, Any]:
        """
        Perform longitudinal analysis for a user.
        Always returns a valid dict — never raises.
        """
        try:
            if not user_id:
                return _neutral_result()
            return await self._run_analysis(user_id, db)
        except Exception as exc:
            log.warning("[LONGITUDINAL] analyze exception for user %s: %s", user_id, exc)
            return _neutral_result()

    # ── Core Analysis ───────────────────────────────────────────────────────────

    async def _run_analysis(self, user_id: Any, db: Any) -> Dict[str, Any]:
        """Execute full longitudinal analysis pipeline."""
        try:
            profile = await self._load_profile(user_id, db)
            if profile is None:
                return _neutral_result()

            history = self._extract_history(profile)
            if not history or len(history) < MIN_HISTORY_DAYS:
                result = _neutral_result()
                result["longitudinal_notes"] = {"reason": "insufficient_history"}
                return result

            signals = self._compute_signals(history, profile)
            scores  = self._compute_scores(signals)
            booleans = self._compute_booleans(signals)
            state   = self._determine_state(scores, booleans, signals)
            notes   = self._build_notes(signals, scores, booleans, state)

            return {
                "long_term_rehabilitation_state":   state,
                "longitudinal_stability_score":     scores["stability"],
                "rehabilitation_resilience_score":  scores["resilience"],
                "continuity_sustainability_score":  scores["sustainability"],
                "recurring_instability_detected":   booleans["recurring_instability"],
                "disengagement_cycle_detected":     booleans["disengagement_cycle"],
                "pacing_adaptation_quality":        scores["pacing_adaptation"],
                "recovery_after_disruption_score":  scores["recovery_after_disruption"],
                "long_term_route_durability":       scores["route_durability"],
                "continuity_erosion_risk":          scores["erosion_risk"],
                "rehabilitation_persistence_score": scores["persistence"],
                "longitudinal_coherence_score":     scores["coherence"],
                "longitudinal_notes":               notes,
                "last_longitudinal_check":          datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            log.warning("[LONGITUDINAL] _run_analysis exception for user %s: %s", user_id, exc)
            return _neutral_result()

    # ── Profile Loading ─────────────────────────────────────────────────────────

    async def _load_profile(self, user_id: Any, db: Any) -> Optional[Dict]:
        """Load client profile from DB. Returns None on any failure."""
        try:
            if db is None:
                return self._build_synthetic_profile(user_id)

            rows = await db.fetch(
                """
                SELECT
                    user_id,
                    created_at,
                    last_active,
                    engagement_score,
                    continuity_score,
                    risk_score,
                    pacing_score,
                    route_stability_score,
                    trajectory_score,
                    recovery_score,
                    disruption_count,
                    instability_count,
                    gap_history,
                    stability_history,
                    continuity_history,
                    pacing_history,
                    trajectory_history,
                    route_history,
                    rehabilitation_state,
                    last_disruption_at,
                    last_recovery_at
                FROM pm_client_profiles
                WHERE user_id = $1
                LIMIT 1
                """,
                str(user_id),
            )
            if not rows:
                return None
            row = rows[0]
            return dict(row)
        except Exception as exc:
            log.warning("[LONGITUDINAL] _load_profile exception: %s", exc)
            return None

    def _build_synthetic_profile(self, user_id: Any) -> Dict:
        """Build minimal synthetic profile when no DB available (for testing)."""
        now = datetime.now(timezone.utc)
        return {
            "user_id": user_id,
            "created_at": now - timedelta(days=45),
            "last_active": now - timedelta(hours=2),
            "engagement_score": 0.65,
            "continuity_score": 0.70,
            "risk_score": 0.30,
            "pacing_score": 0.60,
            "route_stability_score": 0.68,
            "trajectory_score": 0.55,
            "recovery_score": 0.72,
            "disruption_count": 2,
            "instability_count": 1,
            "gap_history": None,
            "stability_history": None,
            "continuity_history": None,
            "pacing_history": None,
            "trajectory_history": None,
            "route_history": None,
            "rehabilitation_state": "active",
            "last_disruption_at": now - timedelta(days=12),
            "last_recovery_at": now - timedelta(days=8),
        }

    # ── History Extraction ──────────────────────────────────────────────────────

    def _extract_history(self, profile: Dict) -> List[Dict]:
        """
        Extract usable history data points from profile.
        Constructs synthetic daily snapshots from available signals.
        """
        try:
            created_at = profile.get("created_at")
            if created_at is None:
                return []

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

            now = datetime.now(timezone.utc)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            age_days = max(0, (now - created_at).days)
            if age_days < MIN_HISTORY_DAYS:
                return []

            # Build synthetic daily snapshots from current signal scores
            history = []
            base_engagement   = float(profile.get("engagement_score") or 0.0)
            base_continuity   = float(profile.get("continuity_score") or 0.0)
            base_pacing       = float(profile.get("pacing_score") or 0.0)
            base_stability    = float(profile.get("route_stability_score") or 0.0)
            base_trajectory   = float(profile.get("trajectory_score") or 0.0)
            base_risk         = float(profile.get("risk_score") or 0.0)
            disruption_count  = int(profile.get("disruption_count") or 0)
            instability_count = int(profile.get("instability_count") or 0)

            # Parse JSONB history fields if available
            gap_history        = self._parse_jsonb(profile.get("gap_history"))
            stability_history  = self._parse_jsonb(profile.get("stability_history"))
            continuity_history = self._parse_jsonb(profile.get("continuity_history"))
            pacing_history     = self._parse_jsonb(profile.get("pacing_history"))

            # Create representative snapshots across windows
            for day_offset in range(min(age_days, WINDOW_LONG)):
                day = now - timedelta(days=day_offset)
                snapshot = {
                    "day": day_offset,
                    "date": day,
                    "engagement":   self._history_value(continuity_history, day_offset, base_engagement),
                    "continuity":   self._history_value(continuity_history, day_offset, base_continuity),
                    "pacing":       self._history_value(pacing_history, day_offset, base_pacing),
                    "stability":    self._history_value(stability_history, day_offset, base_stability),
                    "trajectory":   base_trajectory * max(0.7, 1.0 - day_offset * 0.002),
                    "risk":         base_risk,
                    "disruption":   1 if day_offset < disruption_count * 7 and disruption_count > 0 and (day_offset % 15 == 0) else 0,
                    "instability":  1 if instability_count > 0 and (day_offset % 10 == 0) and day_offset < WINDOW_SHORT else 0,
                }
                history.append(snapshot)

            # Annotate with gap information
            last_disruption_at = profile.get("last_disruption_at")
            last_recovery_at   = profile.get("last_recovery_at")
            if last_disruption_at:
                if isinstance(last_disruption_at, str):
                    last_disruption_at = datetime.fromisoformat(last_disruption_at.replace("Z", "+00:00"))
                if last_disruption_at.tzinfo is None:
                    last_disruption_at = last_disruption_at.replace(tzinfo=timezone.utc)
                days_since_disruption = (now - last_disruption_at).days
                for s in history:
                    if s["day"] == days_since_disruption:
                        s["disruption"] = 1

            return history

        except Exception as exc:
            log.warning("[LONGITUDINAL] _extract_history exception: %s", exc)
            return []

    def _history_value(self, history_list: Optional[List], day_offset: int, fallback: float) -> float:
        """Get value from history list by offset, or return fallback."""
        try:
            if history_list and isinstance(history_list, list) and day_offset < len(history_list):
                v = history_list[day_offset]
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, dict):
                    return float(v.get("value", fallback))
            return fallback
        except Exception:
            return fallback

    def _parse_jsonb(self, value: Any) -> Optional[List]:
        """Safely parse JSONB field."""
        try:
            if value is None:
                return None
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                import json
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else None
            return None
        except Exception:
            return None

    # ── Signal Computation ──────────────────────────────────────────────────────

    def _compute_signals(self, history: List[Dict], profile: Dict) -> Dict[str, Any]:
        """Compute intermediate signals from history across all windows."""
        try:
            now_days = 0

            short_window  = [h for h in history if h["day"] <= WINDOW_SHORT]
            medium_window = [h for h in history if h["day"] <= WINDOW_MEDIUM]
            long_window   = history  # already capped at WINDOW_LONG

            # Instability cycle count (short window)
            instability_days = sum(1 for h in short_window if h.get("instability", 0) > 0)
            instability_cycle_count = instability_days

            # Disruption events across long window
            disruption_events = [h for h in long_window if h.get("disruption", 0) > 0]
            disruption_count = len(disruption_events)

            # Gap detection (days with very low continuity)
            continuity_values = [h.get("continuity", 0.5) for h in long_window]
            gaps = self._detect_gaps(continuity_values, threshold=0.20, min_gap_length=DISENGAGEMENT_GAP_DAYS)
            gap_count = len(gaps)

            # Continuity trend (medium window)
            continuity_medium = [h.get("continuity", 0.5) for h in medium_window]
            continuity_trend  = self._compute_trend(continuity_medium)
            continuity_mean   = self._safe_mean(continuity_medium)

            # Stability values across windows
            stability_short  = self._safe_mean([h.get("stability", 0.5) for h in short_window])
            stability_medium = self._safe_mean([h.get("stability", 0.5) for h in medium_window])
            stability_long   = self._safe_mean([h.get("stability", 0.5) for h in long_window])

            # Pacing values
            pacing_medium = [h.get("pacing", 0.5) for h in medium_window]
            pacing_mean   = self._safe_mean(pacing_medium)
            pacing_variance = self._safe_variance(pacing_medium)

            # Engagement values
            engagement_long = [h.get("engagement", 0.5) for h in long_window]
            engagement_mean = self._safe_mean(engagement_long)
            engagement_consistency = 1.0 - self._safe_variance(engagement_long)

            # Trajectory values
            trajectory_long = [h.get("trajectory", 0.5) for h in long_window]
            trajectory_mean = self._safe_mean(trajectory_long)

            # Recovery analysis
            recovery_count = 0
            recovery_quality_scores = []
            if disruption_count > 0:
                # Each disruption followed by stability recovery
                for event in disruption_events:
                    post_event = [h for h in long_window if h["day"] > event["day"] and h["day"] <= event["day"] + 14]
                    if post_event:
                        recovery_count += 1
                        post_stability = self._safe_mean([h.get("stability", 0.5) for h in post_event])
                        recovery_quality_scores.append(post_stability)

            recovery_rate = recovery_count / disruption_count if disruption_count > 0 else 0.8
            avg_recovery_quality = self._safe_mean(recovery_quality_scores) if recovery_quality_scores else 0.5

            # Route age (normalized 0–1 over WINDOW_LONG)
            created_at = profile.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if hasattr(created_at, 'tzinfo') and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - created_at).days
                route_age_normalized = min(1.0, age_days / WINDOW_LONG)
            else:
                route_age_normalized = 0.5

            # Cross-engine signal consistency
            current_scores = [
                float(profile.get("engagement_score") or 0.5),
                float(profile.get("continuity_score") or 0.5),
                float(profile.get("pacing_score") or 0.5),
                float(profile.get("route_stability_score") or 0.5),
                float(profile.get("trajectory_score") or 0.5),
            ]
            cross_engine_variance = self._safe_variance(current_scores)
            cross_engine_consistency = max(0.0, 1.0 - cross_engine_variance * 2.0)

            return {
                "instability_cycle_count":  instability_cycle_count,
                "disruption_count":         disruption_count,
                "gap_count":                gap_count,
                "continuity_trend":         continuity_trend,
                "continuity_mean":          continuity_mean,
                "stability_short":          stability_short,
                "stability_medium":         stability_medium,
                "stability_long":           stability_long,
                "pacing_mean":              pacing_mean,
                "pacing_variance":          pacing_variance,
                "engagement_mean":          engagement_mean,
                "engagement_consistency":   engagement_consistency,
                "trajectory_mean":          trajectory_mean,
                "recovery_rate":            recovery_rate,
                "avg_recovery_quality":     avg_recovery_quality,
                "recovery_quality_scores":  recovery_quality_scores,
                "route_age_normalized":     route_age_normalized,
                "cross_engine_consistency": cross_engine_consistency,
                "history_length":           len(history),
                "short_window_length":      len(short_window),
                "medium_window_length":     len(medium_window),
            }
        except Exception as exc:
            log.warning("[LONGITUDINAL] _compute_signals exception: %s", exc)
            return {}

    def _detect_gaps(self, values: List[float], threshold: float, min_gap_length: int) -> List[Dict]:
        """Detect continuous low-value gaps in a time series."""
        gaps = []
        in_gap = False
        gap_start = 0
        try:
            for i, v in enumerate(values):
                if v < threshold and not in_gap:
                    in_gap = True
                    gap_start = i
                elif v >= threshold and in_gap:
                    gap_length = i - gap_start
                    if gap_length >= min_gap_length:
                        gaps.append({"start": gap_start, "length": gap_length})
                    in_gap = False
            if in_gap:
                gap_length = len(values) - gap_start
                if gap_length >= min_gap_length:
                    gaps.append({"start": gap_start, "length": gap_length})
        except Exception:
            pass
        return gaps

    def _compute_trend(self, values: List[float]) -> float:
        """Compute normalized linear trend slope (-1.0 to 1.0)."""
        try:
            if len(values) < 2:
                return 0.0
            n = len(values)
            x_mean = (n - 1) / 2.0
            y_mean = sum(values) / n
            numerator   = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            if denominator == 0:
                return 0.0
            slope = numerator / denominator
            # Normalize: typical slope range ~[-0.05, 0.05] per day
            return max(-1.0, min(1.0, slope * 20.0))
        except Exception:
            return 0.0

    def _safe_mean(self, values: List[float]) -> float:
        try:
            if not values:
                return 0.0
            return max(0.0, min(1.0, sum(values) / len(values)))
        except Exception:
            return 0.0

    def _safe_variance(self, values: List[float]) -> float:
        try:
            if len(values) < 2:
                return 0.0
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            return min(1.0, variance)
        except Exception:
            return 0.0

    # ── Score Computation ───────────────────────────────────────────────────────

    def _compute_scores(self, signals: Dict[str, Any]) -> Dict[str, float]:
        """Compute all 0.0–1.0 scores from signals."""
        try:
            if not signals:
                return self._zero_scores()

            # Derived inputs
            instability_frequency = min(1.0, signals.get("instability_cycle_count", 0) / 10.0)
            continuity_consistency = signals.get("continuity_mean", 0.5)
            route_recovery_rate   = signals.get("recovery_rate", 0.5)

            # Trend normalization: 0.5 = no trend, 1.0 = strong positive
            trend = signals.get("continuity_trend", 0.0)
            continuity_trend_norm = max(0.0, min(1.0, (trend + 1.0) / 2.0))

            engagement_consistency = signals.get("engagement_consistency", 0.5)
            pacing_stability       = max(0.0, 1.0 - signals.get("pacing_variance", 0.5))

            recovery_quality = signals.get("avg_recovery_quality", 0.5)
            disruption_count = signals.get("disruption_count", 0)

            # Recovery speed: approximate from disruption count
            recovery_speed = max(0.0, 1.0 - disruption_count * 0.05) if disruption_count > 0 else 0.8
            post_disruption_stability = signals.get("stability_medium", 0.5)

            # Pacing adaptation
            pacing_mean     = signals.get("pacing_mean", 0.5)
            pacing_variance = signals.get("pacing_variance", 0.3)
            pacing_variance_normalized = max(0.0, 1.0 - pacing_variance * 2.0)
            rhythm_consistency = signals.get("engagement_consistency", 0.5)
            # Adaptation delta: positive trend in pacing
            adaptation_delta = max(0.0, min(1.0, (signals.get("continuity_trend", 0.0) + 1.0) / 2.0))

            # Route durability
            route_age_normalized = signals.get("route_age_normalized", 0.5)
            disruption_survival  = route_recovery_rate
            stability_long       = signals.get("stability_long", 0.5)

            # Engagement duration
            history_length           = signals.get("history_length", 0)
            engagement_duration_norm = min(1.0, history_length / WINDOW_LONG)
            gap_count                = signals.get("gap_count", 0)
            return_after_gap         = max(0.0, 1.0 - gap_count * 0.15)
            consistency_over_time    = signals.get("stability_medium", 0.5)

            # Cross-engine coherence
            cross_engine_consistency = signals.get("cross_engine_consistency", 0.5)
            pattern_clarity = max(0.0, 1.0 - instability_frequency)

            # ── Core formulas ──────────────────────────────────────────────────

            stability = (
                (1.0 - instability_frequency)  * 0.40 +
                continuity_consistency          * 0.35 +
                route_recovery_rate             * 0.25
            )

            resilience = (
                route_recovery_rate             * 0.50 +
                recovery_speed                  * 0.30 +
                post_disruption_stability       * 0.20
            )

            sustainability = (
                continuity_trend_norm           * 0.45 +
                engagement_consistency          * 0.35 +
                pacing_stability                * 0.20
            )

            pacing_adaptation = (
                pacing_variance_normalized      * 0.40 +
                rhythm_consistency              * 0.35 +
                adaptation_delta                * 0.25
            )

            recovery_after_disruption = (
                disruption_survival             * 0.60 +
                recovery_speed                  * 0.40
            ) if disruption_count > 0 else 0.75

            route_durability = (
                route_age_normalized            * 0.30 +
                disruption_survival             * 0.40 +
                stability_long                  * 0.30
            )

            persistence = (
                engagement_duration_norm        * 0.40 +
                return_after_gap                * 0.35 +
                consistency_over_time           * 0.25
            )

            coherence = (
                cross_engine_consistency        * 0.35 +
                stability_long                  * 0.30 +
                pattern_clarity                 * 0.35
            )

            # Erosion risk (higher = worse)
            erosion_risk = max(0.0, min(1.0,
                1.0 - sustainability * 0.50 - stability * 0.50
            ))

            return {
                "stability":               max(0.0, min(1.0, stability)),
                "resilience":              max(0.0, min(1.0, resilience)),
                "sustainability":          max(0.0, min(1.0, sustainability)),
                "pacing_adaptation":       max(0.0, min(1.0, pacing_adaptation)),
                "recovery_after_disruption": max(0.0, min(1.0, recovery_after_disruption)),
                "route_durability":        max(0.0, min(1.0, route_durability)),
                "persistence":             max(0.0, min(1.0, persistence)),
                "coherence":               max(0.0, min(1.0, coherence)),
                "erosion_risk":            erosion_risk,
            }
        except Exception as exc:
            log.warning("[LONGITUDINAL] _compute_scores exception: %s", exc)
            return self._zero_scores()

    def _zero_scores(self) -> Dict[str, float]:
        return {
            "stability": 0.0, "resilience": 0.0, "sustainability": 0.0,
            "pacing_adaptation": 0.0, "recovery_after_disruption": 0.0,
            "route_durability": 0.0, "persistence": 0.0,
            "coherence": 0.0, "erosion_risk": 0.0,
        }

    # ── Boolean Flags ───────────────────────────────────────────────────────────

    def _compute_booleans(self, signals: Dict[str, Any]) -> Dict[str, bool]:
        """Compute boolean flags from signals."""
        try:
            recurring_instability = (
                signals.get("instability_cycle_count", 0) >= INSTABILITY_CYCLE_THRESHOLD
            )
            disengagement_cycle = (
                signals.get("gap_count", 0) >= DISENGAGEMENT_CYCLE_THRESHOLD
            )
            return {
                "recurring_instability": recurring_instability,
                "disengagement_cycle":   disengagement_cycle,
            }
        except Exception:
            return {"recurring_instability": False, "disengagement_cycle": False}

    # ── State Determination ─────────────────────────────────────────────────────

    def _determine_state(
        self,
        scores: Dict[str, float],
        booleans: Dict[str, bool],
        signals: Dict[str, Any],
    ) -> str:
        """Determine dominant long-term rehabilitation state."""
        try:
            if not scores or not signals:
                return "UNKNOWN"

            erosion_risk     = scores.get("erosion_risk", 0.0)
            stability        = scores.get("stability", 0.0)
            resilience       = scores.get("resilience", 0.0)
            sustainability   = scores.get("sustainability", 0.0)
            pacing_adaptation = scores.get("pacing_adaptation", 0.0)
            persistence      = scores.get("persistence", 0.0)
            route_durability = scores.get("route_durability", 0.0)
            recovery_score   = scores.get("recovery_after_disruption", 0.0)

            recurring_instability = booleans.get("recurring_instability", False)
            disengagement_cycle   = booleans.get("disengagement_cycle", False)
            disruption_count      = signals.get("disruption_count", 0)

            # Priority ordering — most severe first
            if disengagement_cycle and persistence < 0.40:
                return "DISENGAGEMENT_PATTERN"

            if erosion_risk > EROSION_RISK_HIGH_THRESHOLD:
                return "CONTINUITY_EROSION"

            if recurring_instability:
                return "RECURRING_INSTABILITY"

            if disruption_count > 0 and recovery_score > 0.60:
                # Currently in post-disruption recovery with good recovery capacity
                if stability < 0.55:
                    return "POST_DISRUPTION_RECOVERY"

            if disruption_count >= 2 and resilience > RESILIENCE_HIGH_THRESHOLD:
                return "RESILIENT_RECOVERY"

            if pacing_adaptation > 0.65 and stability >= 0.50:
                return "ADAPTIVE_PACING"

            if persistence > PERSISTENCE_HIGH_THRESHOLD and sustainability > 0.60:
                return "DURABLE_ENGAGEMENT"

            if stability > STABILITY_HIGH_THRESHOLD and route_durability > DURABILITY_HIGH_THRESHOLD:
                return "STABLE_PROGRESSION"

            if stability > 0.55 and not recurring_instability and not disengagement_cycle:
                return "STABLE_PROGRESSION"

            return "UNKNOWN"

        except Exception as exc:
            log.warning("[LONGITUDINAL] _determine_state exception: %s", exc)
            return "UNKNOWN"

    # ── Notes Builder ───────────────────────────────────────────────────────────

    def _build_notes(
        self,
        signals: Dict[str, Any],
        scores: Dict[str, float],
        booleans: Dict[str, bool],
        state: str,
    ) -> Dict[str, Any]:
        """Build structured notes for audit trail."""
        try:
            return {
                "state":                   state,
                "windows": {
                    "short_days":          WINDOW_SHORT,
                    "medium_days":         WINDOW_MEDIUM,
                    "long_days":           WINDOW_LONG,
                    "history_length":      signals.get("history_length", 0),
                },
                "cycle_detection": {
                    "instability_cycles":  signals.get("instability_cycle_count", 0),
                    "gap_count":           signals.get("gap_count", 0),
                    "disruption_count":    signals.get("disruption_count", 0),
                },
                "trend": {
                    "continuity_trend":    round(signals.get("continuity_trend", 0.0), 4),
                    "stability_long":      round(signals.get("stability_long", 0.0), 4),
                },
                "scores": {k: round(v, 4) for k, v in scores.items()},
                "flags": booleans,
                "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            return {}

    # ── Stats ────────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return engine runtime stats for dashboard."""
        try:
            return {
                "engine":       "LongitudinalRehabilitationModelingEngine",
                "phase":        "3.14",
                "initialized":  self._initialized,
                "windows": {
                    "short_days":  WINDOW_SHORT,
                    "medium_days": WINDOW_MEDIUM,
                    "long_days":   WINDOW_LONG,
                },
                "states":                list(LONG_TERM_STATES.keys()),
                "state_count":           len(LONG_TERM_STATES),
                "instability_threshold": INSTABILITY_CYCLE_THRESHOLD,
                "disengagement_threshold": DISENGAGEMENT_CYCLE_THRESHOLD,
                "governance_position":   "bottom_of_hierarchy",
            }
        except Exception:
            return {"engine": "LongitudinalRehabilitationModelingEngine", "error": "stats_unavailable"}


# ── Module-Level API ─────────────────────────────────────────────────────────────

_engine: Optional[LongitudinalRehabilitationModelingEngine] = None


def get_longitudinal_modeling_engine() -> LongitudinalRehabilitationModelingEngine:
    """Get or create singleton engine instance."""
    global _engine
    if _engine is None:
        _engine = LongitudinalRehabilitationModelingEngine.get_instance()
    return _engine


async def init_longitudinal_modeling_engine() -> None:
    """Initialize the singleton engine. Safe to call multiple times."""
    engine = get_longitudinal_modeling_engine()
    await engine.initialize()


async def analyze_longitudinal(user_id: Any, db: Any = None) -> Dict[str, Any]:
    """Module-level analysis entry point."""
    engine = get_longitudinal_modeling_engine()
    return await engine.analyze(user_id, db)

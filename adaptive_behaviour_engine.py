"""
adaptive_behaviour_engine.py
Phase 3.6 — Adaptive Behavioural Intelligence

Purpose:
    Detects long-term behavioural patterns for each user and produces adaptation
    recommendations that improve emotional timing, routing accuracy, pacing, and
    support quality WITHOUT ever increasing persuasion pressure.

Architecture:
    Input:  user_context, memory_state, risk_profile, interaction_history
    Output: BehaviourProfile (dimensions + classification + adaptations)
    Integration: runs AFTER policy_task, BEFORE dispatcher_task in orchestrator

Critical principles:
    - Adaptation must REDUCE chaos and pressure — never increase persuasion.
    - Emotional governance overrides optimisation.
    - Human dignity overrides conversion.
    - If engine fails, system falls back to neutral BehaviourProfile.
    - Central Orchestrator remains final authority.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class BehaviourClassification(str, Enum):
    """Top-level behavioural classification labels."""
    CAUTIOUS_SLOW              = "cautious_slow"
    HIGH_TRUST_FAST            = "high_trust_fast"
    OVERWHELMED_FRAGMENTED     = "overwhelmed_fragmented"
    ANALYTICAL_REPETITIVE      = "analytical_repetitive"
    EMOTIONALLY_UNSTABLE       = "emotionally_unstable"
    SILENT_OBSERVER            = "silent_observer"
    DEPENDENT_ON_HUMAN         = "dependent_on_human"
    HIGH_CONTINUITY            = "high_continuity"
    RECOVERY_RESISTANT         = "recovery_resistant"
    NEUTRAL                    = "neutral"


class AdaptationCategory(str, Enum):
    """Categories of allowable adaptation."""
    PACING                  = "pacing"
    MESSAGE_LENGTH          = "message_length"
    REMINDER_SPACING        = "reminder_spacing"
    EXPLANATION_DEPTH       = "explanation_depth"
    ONBOARDING_SPEED        = "onboarding_speed"
    RECOVERY_TIMING         = "recovery_timing"
    ESCALATION_TIMING       = "escalation_timing"
    TRUST_REPAIR_INTENSITY  = "trust_repair_intensity"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class BehaviourDimensions:
    """
    11 behavioural profile dimensions.
    All values in [0.0, 1.0] unless noted; None = insufficient data.
    """
    # How regularly and predictably the user engages (1=very regular)
    engagement_rhythm: Optional[float] = None
    # Typical response latency percentile (0=instant, 1=very slow)
    response_latency_pattern: Optional[float] = None
    # Speed at which user builds trust (1=fast)
    trust_building_speed: Optional[float] = None
    # Sensitivity to information overload (1=highly sensitive)
    overwhelm_sensitivity: Optional[float] = None
    # Pace of decision-making (0=impulsive, 1=very deliberate)
    decision_pacing: Optional[float] = None
    # Responsiveness to recovery messaging (1=very responsive)
    recovery_responsiveness: Optional[float] = None
    # Route stability over time (1=very stable)
    route_stability: Optional[float] = None
    # Degree of dependency on human support (1=highly dependent)
    escalation_dependency: Optional[float] = None
    # Tolerance for information density (1=high tolerance)
    information_tolerance: Optional[float] = None
    # Pattern of voluntary silence (0=never silent, 1=frequent long silences)
    silence_pattern: Optional[float] = None
    # Variance in emotional tone across interactions (1=highly variable)
    emotional_variability: Optional[float] = None


@dataclass
class AdaptationRecommendation:
    """A single recommended adaptation."""
    category: AdaptationCategory
    direction: str    # "increase" | "decrease" | "maintain"
    magnitude: str    # "minor" | "moderate" | "significant"
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category":  self.category.value,
            "direction": self.direction,
            "magnitude": self.magnitude,
            "rationale": self.rationale,
        }


@dataclass
class BehaviourShift:
    """Detected shift in behavioural pattern."""
    dimension: str
    previous_value: Optional[float]
    current_value: Optional[float]
    shift_magnitude: float          # absolute change
    shift_type: str                 # "positive" | "negative" | "neutral"
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension":       self.dimension,
            "previous_value":  self.previous_value,
            "current_value":   self.current_value,
            "shift_magnitude": round(self.shift_magnitude, 3),
            "shift_type":      self.shift_type,
            "detected_at":     self.detected_at.isoformat(),
        }


@dataclass
class BehaviourProfile:
    """
    Full output of AdaptiveBehaviourEngine.evaluate_behaviour_profile().
    Persisted to DB + exposed via dashboard.
    """
    user_id: str = ""
    classification: BehaviourClassification = BehaviourClassification.NEUTRAL
    dimensions: BehaviourDimensions = field(default_factory=BehaviourDimensions)
    confidence: float = 0.0          # 0.0–1.0
    volatility_score: float = 0.0    # 0.0–1.0; high = unstable behaviour
    adaptation_recommendations: List[AdaptationRecommendation] = field(default_factory=list)
    detected_shifts: List[BehaviourShift] = field(default_factory=list)
    shift_detected: bool = False
    last_updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Error / fallback flag
    is_fallback: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id":                   self.user_id,
            "classification":            self.classification.value,
            "dimensions": {
                "engagement_rhythm":       self.dimensions.engagement_rhythm,
                "response_latency_pattern":self.dimensions.response_latency_pattern,
                "trust_building_speed":    self.dimensions.trust_building_speed,
                "overwhelm_sensitivity":   self.dimensions.overwhelm_sensitivity,
                "decision_pacing":         self.dimensions.decision_pacing,
                "recovery_responsiveness": self.dimensions.recovery_responsiveness,
                "route_stability":         self.dimensions.route_stability,
                "escalation_dependency":   self.dimensions.escalation_dependency,
                "information_tolerance":   self.dimensions.information_tolerance,
                "silence_pattern":         self.dimensions.silence_pattern,
                "emotional_variability":   self.dimensions.emotional_variability,
            },
            "confidence":                round(self.confidence, 3),
            "volatility_score":          round(self.volatility_score, 3),
            "adaptation_recommendations":[r.to_dict() for r in self.adaptation_recommendations],
            "detected_shifts":           [s.to_dict() for s in self.detected_shifts],
            "shift_detected":            self.shift_detected,
            "last_updated_at":           self.last_updated_at.isoformat(),
            "is_fallback":               self.is_fallback,
            "error_message":             self.error_message,
        }


# ---------------------------------------------------------------------------
# Helper — neutral fallback profile
# ---------------------------------------------------------------------------

def _neutral_profile(user_id: str = "", error: Optional[str] = None) -> BehaviourProfile:
    """Return a safe, neutral BehaviourProfile used as fallback on any error."""
    return BehaviourProfile(
        user_id=user_id,
        classification=BehaviourClassification.NEUTRAL,
        confidence=0.0,
        is_fallback=True,
        error_message=error,
    )


# ---------------------------------------------------------------------------
# AdaptiveBehaviourEngine
# ---------------------------------------------------------------------------

class AdaptiveBehaviourEngine:
    """
    Evaluates long-term behavioural patterns and produces safe adaptations.

    Immutable safety constraints:
      - NEVER recommends increasing pressure, urgency, or persuasion.
      - NEVER exploits emotional vulnerability.
      - NEVER bypasses escalation, silence_respect, or route locks.
      - If any exception occurs, returns neutral fallback profile.
      - Central Orchestrator remains final authority on routing decisions.
    """

    # Minimum interaction count before reliable classification is possible.
    _MIN_INTERACTIONS_FOR_CLASSIFICATION = 3

    # Shift threshold — change in dimension value that counts as a shift
    _SHIFT_THRESHOLD = 0.20

    # ---------------------------------------------------------------------------
    # Core evaluation
    # ---------------------------------------------------------------------------

    async def evaluate_behaviour_profile(
        self,
        user_context: Dict[str, Any],
        memory_state: Dict[str, Any],
        risk_profile: Dict[str, Any],
        interaction_history: List[Dict[str, Any]],
    ) -> BehaviourProfile:
        """
        Main entry point.

        Parameters
        ----------
        user_context : dict
            Fields: user_id, current_stage, silence_respect, explicit_refusal,
                    human_escalation_required, route_lock, trust_lock, cooldown_active,
                    last_user_message_at, ai_message_count, user_message_count
        memory_state : dict
            Fields: emotional_tone_history, escalation_history, stage_transitions,
                    trust_score, session_count
        risk_profile : dict
            Fields: risk_level, risk_score, risk_flags, emotional_overload_detected
        interaction_history : list[dict]
            Each entry: {timestamp, message_type (user|ai), latency_seconds,
                         emotional_tone, route, stage}

        Returns
        -------
        BehaviourProfile
            Always returns a valid profile; fallback on any error.
        """
        user_id = str(user_context.get("user_id", ""))
        try:
            return await self._evaluate_safe(
                user_id, user_context, memory_state, risk_profile, interaction_history
            )
        except Exception as exc:
            log.warning("[BEHAVIOUR] evaluate_behaviour_profile failed for %s: %s", user_id, exc)
            return _neutral_profile(user_id=user_id, error=str(exc))

    async def _evaluate_safe(
        self,
        user_id: str,
        user_context: Dict[str, Any],
        memory_state: Dict[str, Any],
        risk_profile: Dict[str, Any],
        interaction_history: List[Dict[str, Any]],
    ) -> BehaviourProfile:
        """Internal evaluation logic (may raise — caller handles)."""

        # ------------------------------------------------------------------
        # 1. Compute dimensions from available signals
        # ------------------------------------------------------------------
        dims = self._compute_dimensions(
            user_context, memory_state, risk_profile, interaction_history
        )

        # ------------------------------------------------------------------
        # 2. Compute volatility score
        # ------------------------------------------------------------------
        volatility = self._compute_volatility(dims, risk_profile, interaction_history)

        # ------------------------------------------------------------------
        # 3. Classify behaviour
        # ------------------------------------------------------------------
        n_interactions = len(interaction_history)
        if n_interactions < self._MIN_INTERACTIONS_FOR_CLASSIFICATION:
            classification = BehaviourClassification.NEUTRAL
            confidence = 0.2
        else:
            classification, confidence = self._classify(dims, user_context, memory_state, risk_profile)

        # ------------------------------------------------------------------
        # 4. Detect shifts against previous profile (from memory_state)
        # ------------------------------------------------------------------
        prev_dims_raw: Dict[str, Any] = memory_state.get("behaviour_dimensions", {})
        shifts = self._detect_shifts(dims, prev_dims_raw)
        shift_detected = len(shifts) > 0

        # ------------------------------------------------------------------
        # 5. Generate adaptation recommendations (NEVER increases pressure)
        # ------------------------------------------------------------------
        recommendations = self._generate_adaptations(
            classification, dims, volatility, risk_profile, user_context
        )

        return BehaviourProfile(
            user_id=user_id,
            classification=classification,
            dimensions=dims,
            confidence=round(confidence, 3),
            volatility_score=round(volatility, 3),
            adaptation_recommendations=recommendations,
            detected_shifts=shifts,
            shift_detected=shift_detected,
            last_updated_at=datetime.now(timezone.utc),
            is_fallback=False,
        )

    # ---------------------------------------------------------------------------
    # Dimension computation
    # ---------------------------------------------------------------------------

    def _compute_dimensions(
        self,
        user_context: Dict[str, Any],
        memory_state: Dict[str, Any],
        risk_profile: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> BehaviourDimensions:
        """Compute all 11 dimensions from available signals."""
        dims = BehaviourDimensions()

        if not history:
            return dims

        # --- engagement_rhythm ---
        # Measure inter-message gaps; regularity = low CV of gaps
        user_msgs = [h for h in history if h.get("message_type") == "user"]
        if len(user_msgs) >= 2:
            timestamps = sorted(
                m.get("timestamp", 0) for m in user_msgs if m.get("timestamp")
            )
            gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                if avg_gap > 0:
                    variance = sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)
                    cv = (variance ** 0.5) / avg_gap  # coefficient of variation
                    dims.engagement_rhythm = round(max(0.0, min(1.0, 1.0 - min(cv, 2.0) / 2.0)), 3)

        # --- response_latency_pattern ---
        latencies = [h.get("latency_seconds", 0) for h in user_msgs if h.get("latency_seconds")]
        if latencies:
            avg_latency_hours = (sum(latencies) / len(latencies)) / 3600.0
            # Normalise: 0h→0.0, 24h+→1.0
            dims.response_latency_pattern = round(min(1.0, avg_latency_hours / 24.0), 3)

        # --- trust_building_speed ---
        trust_score = float(memory_state.get("trust_score", 0.5))
        session_count = int(memory_state.get("session_count", 1))
        if session_count > 0:
            # High trust early in lifecycle = fast building
            dims.trust_building_speed = round(min(1.0, trust_score / max(session_count * 0.1, 0.1)), 3)

        # --- overwhelm_sensitivity ---
        # Proxy: emotional_overload in risk profile + escalaion history frequency
        overload_flag = bool(risk_profile.get("emotional_overload_detected", False))
        escalation_history = memory_state.get("escalation_history", [])
        esc_count = len(escalation_history)
        base_overload = 0.7 if overload_flag else 0.3
        esc_factor = min(0.3, esc_count * 0.05)
        dims.overwhelm_sensitivity = round(min(1.0, base_overload + esc_factor), 3)

        # --- decision_pacing ---
        stage_transitions = memory_state.get("stage_transitions", [])
        if stage_transitions:
            # Many transitions relative to sessions = faster pacing
            sessions = max(session_count, 1)
            transition_rate = len(stage_transitions) / sessions
            # High transition rate = impulsive (low decision_pacing)
            dims.decision_pacing = round(max(0.0, min(1.0, 1.0 - min(transition_rate / 3.0, 1.0))), 3)
        else:
            dims.decision_pacing = 0.5  # neutral default

        # --- recovery_responsiveness ---
        # How often user has re-engaged after silence periods
        re_engagements = int(memory_state.get("re_engagement_count", 0))
        silence_periods = max(int(memory_state.get("silence_period_count", 1)), 1)
        dims.recovery_responsiveness = round(min(1.0, re_engagements / silence_periods), 3)

        # --- route_stability ---
        # Fraction of history messages that stayed on same route
        routes = [h.get("route") for h in history if h.get("route")]
        if routes:
            if len(routes) > 1:
                same = sum(1 for i in range(1, len(routes)) if routes[i] == routes[i-1])
                dims.route_stability = round(same / (len(routes) - 1), 3)
            else:
                dims.route_stability = 1.0

        # --- escalation_dependency ---
        if session_count > 0:
            esc_rate = esc_count / session_count
            dims.escalation_dependency = round(min(1.0, esc_rate), 3)

        # --- information_tolerance ---
        # Proxy: inverse of overwhelm_sensitivity, adjusted for analytical pattern
        tone_history = memory_state.get("emotional_tone_history", [])
        confusion_count = sum(1 for t in tone_history if t in ("confused", "frustrated"))
        if tone_history:
            confusion_rate = confusion_count / len(tone_history)
            dims.information_tolerance = round(max(0.0, 1.0 - confusion_rate - 0.2 * (dims.overwhelm_sensitivity or 0.5)), 3)
        else:
            dims.information_tolerance = 0.5

        # --- silence_pattern ---
        if dims.response_latency_pattern is not None:
            dims.silence_pattern = round(dims.response_latency_pattern, 3)

        # --- emotional_variability ---
        if tone_history:
            unique_tones = len(set(tone_history))
            total_tones = len(tone_history)
            dims.emotional_variability = round(min(1.0, unique_tones / max(total_tones, 1)), 3)

        return dims

    # ---------------------------------------------------------------------------
    # Volatility computation
    # ---------------------------------------------------------------------------

    def _compute_volatility(
        self,
        dims: BehaviourDimensions,
        risk_profile: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> float:
        """
        Volatility score [0.0–1.0].
        High = unpredictable behaviour requiring careful pacing.
        """
        signals = []
        if dims.emotional_variability is not None:
            signals.append(dims.emotional_variability)
        if dims.route_stability is not None:
            signals.append(1.0 - dims.route_stability)
        if dims.overwhelm_sensitivity is not None:
            signals.append(dims.overwhelm_sensitivity * 0.5)
        risk_score = float(risk_profile.get("risk_score", 0.3))
        signals.append(min(1.0, risk_score))

        if not signals:
            return 0.3
        return round(sum(signals) / len(signals), 3)

    # ---------------------------------------------------------------------------
    # Classification
    # ---------------------------------------------------------------------------

    def _classify(
        self,
        dims: BehaviourDimensions,
        user_context: Dict[str, Any],
        memory_state: Dict[str, Any],
        risk_profile: Dict[str, Any],
    ) -> tuple[BehaviourClassification, float]:
        """
        Map dimensions to a BehaviourClassification.
        Returns (classification, confidence).
        """
        # Helper
        def d(v: Optional[float], default: float = 0.5) -> float:
            return v if v is not None else default

        trust = d(dims.trust_building_speed)
        overwhelm = d(dims.overwhelm_sensitivity)
        latency = d(dims.response_latency_pattern)
        variability = d(dims.emotional_variability)
        escalation_dep = d(dims.escalation_dependency)
        route_stab = d(dims.route_stability)
        recovery_resp = d(dims.recovery_responsiveness)
        info_tol = d(dims.information_tolerance)
        silence = d(dims.silence_pattern)
        pacing = d(dims.decision_pacing)
        engagement = d(dims.engagement_rhythm)

        # Scoring rules (non-exclusive; highest score wins)
        scores: Dict[BehaviourClassification, float] = {
            c: 0.0 for c in BehaviourClassification
        }

        # CAUTIOUS_SLOW: slow latency, low trust, deliberate decisions, high pacing
        scores[BehaviourClassification.CAUTIOUS_SLOW] += (latency * 0.3 + (1 - trust) * 0.3 + pacing * 0.2 + (1 - engagement) * 0.2)

        # HIGH_TRUST_FAST: high trust, fast latency, high recovery responsiveness
        scores[BehaviourClassification.HIGH_TRUST_FAST] += (trust * 0.4 + (1 - latency) * 0.3 + recovery_resp * 0.3)

        # OVERWHELMED_FRAGMENTED: high overwhelm, high variability, low info tolerance, low route stability
        scores[BehaviourClassification.OVERWHELMED_FRAGMENTED] += (
            overwhelm * 0.35 + variability * 0.25 + (1 - info_tol) * 0.25 + (1 - route_stab) * 0.15
        )

        # ANALYTICAL_REPETITIVE: high info tolerance, high pacing, low variability
        scores[BehaviourClassification.ANALYTICAL_REPETITIVE] += (
            info_tol * 0.4 + pacing * 0.3 + (1 - variability) * 0.3
        )

        # EMOTIONALLY_UNSTABLE: high variability, high overwhelm, low route stability
        overload = 1.0 if risk_profile.get("emotional_overload_detected") else 0.5
        scores[BehaviourClassification.EMOTIONALLY_UNSTABLE] += (
            variability * 0.4 + overwhelm * 0.3 + (1 - route_stab) * 0.2 + overload * 0.1
        )

        # SILENT_OBSERVER: high silence, low engagement, high latency
        scores[BehaviourClassification.SILENT_OBSERVER] += (
            silence * 0.4 + (1 - engagement) * 0.35 + latency * 0.25
        )

        # DEPENDENT_ON_HUMAN: high escalation dependency
        esc_count = len(memory_state.get("escalation_history", []))
        scores[BehaviourClassification.DEPENDENT_ON_HUMAN] += (
            escalation_dep * 0.6 + (1 - recovery_resp) * 0.4
        )

        # HIGH_CONTINUITY: high engagement, high route stability, high trust
        scores[BehaviourClassification.HIGH_CONTINUITY] += (
            engagement * 0.4 + route_stab * 0.35 + trust * 0.25
        )

        # RECOVERY_RESISTANT: low recovery responsiveness, high silence, high latency
        scores[BehaviourClassification.RECOVERY_RESISTANT] += (
            (1 - recovery_resp) * 0.45 + silence * 0.35 + latency * 0.2
        )

        # NEUTRAL is last resort
        scores[BehaviourClassification.NEUTRAL] = 0.1

        best = max(scores, key=lambda c: scores[c])
        best_score = scores[best]
        second_score = sorted(scores.values(), reverse=True)[1]
        # Confidence = separation between top-2 scores
        confidence = min(1.0, max(0.2, best_score - second_score + 0.4))

        return best, round(confidence, 3)

    # ---------------------------------------------------------------------------
    # Shift detection
    # ---------------------------------------------------------------------------

    def _detect_shifts(
        self,
        current: BehaviourDimensions,
        previous_raw: Dict[str, float],
    ) -> List[BehaviourShift]:
        """Detect dimension-level behavioural shifts vs previous profile."""
        shifts: List[BehaviourShift] = []
        dimension_names = [
            "engagement_rhythm", "response_latency_pattern", "trust_building_speed",
            "overwhelm_sensitivity", "decision_pacing", "recovery_responsiveness",
            "route_stability", "escalation_dependency", "information_tolerance",
            "silence_pattern", "emotional_variability",
        ]
        for dim_name in dimension_names:
            current_val = getattr(current, dim_name, None)
            prev_val = previous_raw.get(dim_name)
            if current_val is None or prev_val is None:
                continue
            magnitude = abs(current_val - prev_val)
            if magnitude >= self._SHIFT_THRESHOLD:
                # Determine shift direction valence
                positive_dims = {
                    "engagement_rhythm", "trust_building_speed",
                    "recovery_responsiveness", "route_stability", "information_tolerance",
                }
                if dim_name in positive_dims:
                    shift_type = "positive" if current_val > prev_val else "negative"
                else:
                    shift_type = "negative" if current_val > prev_val else "positive"

                shifts.append(BehaviourShift(
                    dimension=dim_name,
                    previous_value=round(prev_val, 3),
                    current_value=round(current_val, 3),
                    shift_magnitude=round(magnitude, 3),
                    shift_type=shift_type,
                ))
        return shifts

    # ---------------------------------------------------------------------------
    # Adaptation generation (CRITICAL: pressure-reduction only)
    # ---------------------------------------------------------------------------

    def _generate_adaptations(
        self,
        classification: BehaviourClassification,
        dims: BehaviourDimensions,
        volatility: float,
        risk_profile: Dict[str, Any],
        user_context: Dict[str, Any],
    ) -> List[AdaptationRecommendation]:
        """
        Generate adaptation recommendations.

        IMMUTABLE CONSTRAINT:
            This method MUST NEVER produce recommendations that:
            - Increase contact frequency
            - Increase urgency or pressure language
            - Exploit fear, confusion, or emotional vulnerability
            - Bypass human escalation or silence respect
        """
        recs: List[AdaptationRecommendation] = []

        def d(v: Optional[float], default: float = 0.5) -> float:
            return v if v is not None else default

        overwhelm = d(dims.overwhelm_sensitivity)
        latency = d(dims.response_latency_pattern)
        recovery_resp = d(dims.recovery_responsiveness)
        escalation_dep = d(dims.escalation_dependency)
        info_tol = d(dims.information_tolerance)
        trust = d(dims.trust_building_speed)
        engagement = d(dims.engagement_rhythm)

        # --- PACING ---
        if classification in (BehaviourClassification.CAUTIOUS_SLOW, BehaviourClassification.OVERWHELMED_FRAGMENTED):
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.PACING,
                direction="decrease",
                magnitude="moderate",
                rationale="User shows slow or fragmented engagement; slower pacing reduces overwhelm.",
            ))
        elif classification == BehaviourClassification.HIGH_TRUST_FAST:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.PACING,
                direction="increase",
                magnitude="minor",
                rationale="High-trust fast-moving user; slightly faster pacing maintains momentum without pressure.",
            ))

        # --- MESSAGE LENGTH ---
        if overwhelm > 0.6 or classification == BehaviourClassification.OVERWHELMED_FRAGMENTED:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.MESSAGE_LENGTH,
                direction="decrease",
                magnitude="significant" if overwhelm > 0.8 else "moderate",
                rationale="High overwhelm sensitivity detected; shorter messages reduce cognitive load.",
            ))
        elif info_tol > 0.7 and classification == BehaviourClassification.ANALYTICAL_REPETITIVE:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.MESSAGE_LENGTH,
                direction="increase",
                magnitude="minor",
                rationale="Analytical user with high information tolerance; richer detail improves satisfaction.",
            ))

        # --- REMINDER SPACING ---
        if classification == BehaviourClassification.RECOVERY_RESISTANT or recovery_resp < 0.3:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.REMINDER_SPACING,
                direction="increase",
                magnitude="significant",
                rationale="Low recovery responsiveness; spacing out reminders avoids desensitisation.",
            ))
        elif latency > 0.7 or classification == BehaviourClassification.SILENT_OBSERVER:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.REMINDER_SPACING,
                direction="increase",
                magnitude="moderate",
                rationale="High latency / silent observer pattern; extended spacing respects natural rhythm.",
            ))

        # --- EXPLANATION DEPTH ---
        if classification == BehaviourClassification.ANALYTICAL_REPETITIVE:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.EXPLANATION_DEPTH,
                direction="increase",
                magnitude="moderate",
                rationale="Analytical repetitive pattern; deeper explanations satisfy information needs.",
            ))
        elif classification in (BehaviourClassification.OVERWHELMED_FRAGMENTED,
                                BehaviourClassification.EMOTIONALLY_UNSTABLE):
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.EXPLANATION_DEPTH,
                direction="decrease",
                magnitude="moderate",
                rationale="Overwhelm or emotional instability detected; simplified messaging reduces confusion.",
            ))

        # --- ONBOARDING SPEED ---
        if classification == BehaviourClassification.CAUTIOUS_SLOW:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.ONBOARDING_SPEED,
                direction="decrease",
                magnitude="moderate",
                rationale="Cautious slow user; slower onboarding reduces drop-off from pressure.",
            ))

        # --- RECOVERY TIMING ---
        if classification == BehaviourClassification.RECOVERY_RESISTANT:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.RECOVERY_TIMING,
                direction="increase",
                magnitude="significant",
                rationale="Recovery-resistant pattern; longer waiting intervals before recovery outreach.",
            ))
        elif classification == BehaviourClassification.EMOTIONALLY_UNSTABLE:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.RECOVERY_TIMING,
                direction="increase",
                magnitude="moderate",
                rationale="Emotional instability detected; extended recovery timing protects trust.",
            ))

        # --- ESCALATION TIMING ---
        if classification == BehaviourClassification.DEPENDENT_ON_HUMAN or escalation_dep > 0.6:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.ESCALATION_TIMING,
                direction="decrease",
                magnitude="moderate",
                rationale="High human dependency; escalate to human support earlier to meet user needs.",
            ))

        # --- TRUST REPAIR INTENSITY ---
        if trust < 0.3 and volatility > 0.5:
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.TRUST_REPAIR_INTENSITY,
                direction="increase",
                magnitude="moderate",
                rationale="Low trust with high volatility; intensified but calm trust-repair approach.",
            ))

        # High volatility override — always increase spacing if highly volatile
        if volatility > 0.75 and not any(r.category == AdaptationCategory.REMINDER_SPACING for r in recs):
            recs.append(AdaptationRecommendation(
                category=AdaptationCategory.REMINDER_SPACING,
                direction="increase",
                magnitude="significant",
                rationale="High behavioural volatility; extended spacing reduces destabilisation risk.",
            ))

        return recs

    # ---------------------------------------------------------------------------
    # DB persistence
    # ---------------------------------------------------------------------------

    async def persist_profile(
        self,
        db_pool,
        profile: BehaviourProfile,
    ) -> bool:
        """
        Persist behavioural profile fields to pm_client_profiles.
        Safe: does not raise — returns bool success.
        """
        if not db_pool or profile.is_fallback:
            return False
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE pm_client_profiles
                    SET
                        behavioural_profile            = $1,
                        behavioural_confidence         = $2,
                        last_behaviour_update_at       = $3,
                        behavioural_shift_detected     = $4,
                        behavioural_volatility_score   = $5
                    WHERE user_id = $6
                    """,
                    profile.to_dict().__str__(),   # stored as JSON string for simplicity
                    profile.confidence,
                    profile.last_updated_at,
                    profile.shift_detected,
                    profile.volatility_score,
                    profile.user_id,
                )
            log.debug("[BEHAVIOUR] Profile persisted for user %s", profile.user_id)
            return True
        except Exception as e:
            log.warning("[BEHAVIOUR] persist_profile failed for %s: %s", profile.user_id, e)
            return False

    async def persist_profile_json(
        self,
        db_pool,
        profile: BehaviourProfile,
    ) -> bool:
        """
        Persist behavioural profile as JSONB to pm_client_profiles.
        Preferred if column type is JSONB.
        """
        if not db_pool or profile.is_fallback:
            return False
        import json
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE pm_client_profiles
                    SET
                        behavioural_profile            = $1::jsonb,
                        behavioural_confidence         = $2,
                        last_behaviour_update_at       = $3,
                        behavioural_shift_detected     = $4,
                        behavioural_volatility_score   = $5
                    WHERE user_id = $6
                    """,
                    json.dumps(profile.to_dict()),
                    profile.confidence,
                    profile.last_updated_at,
                    profile.shift_detected,
                    profile.volatility_score,
                    profile.user_id,
                )
            log.debug("[BEHAVIOUR] JSON profile persisted for user %s", profile.user_id)
            return True
        except Exception as e:
            log.warning("[BEHAVIOUR] persist_profile_json failed for %s: %s", profile.user_id, e)
            return False

    # ---------------------------------------------------------------------------
    # Dashboard stats
    # ---------------------------------------------------------------------------

    def get_engine_stats(self) -> Dict[str, Any]:
        """Return engine-level stats for dashboard."""
        return {
            "engine": "AdaptiveBehaviourEngine",
            "version": "3.6.0",
            "status": "operational",
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: Optional[AdaptiveBehaviourEngine] = None
_engine_lock = asyncio.Lock()


def init_behaviour_engine() -> AdaptiveBehaviourEngine:
    """Initialise (or return existing) AdaptiveBehaviourEngine singleton."""
    global _engine
    if _engine is None:
        _engine = AdaptiveBehaviourEngine()
        log.info("[BEHAVIOUR] AdaptiveBehaviourEngine singleton created")
    return _engine


def get_behaviour_engine() -> Optional[AdaptiveBehaviourEngine]:
    """Return existing singleton or None if not yet initialised."""
    return _engine

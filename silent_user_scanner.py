# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.5 — Silent User Scanner
# Module: silent_user_scanner.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Proactive Silence Detection Layer
#
# Purpose: Periodically scan for users who have gone silent and feed them
# into the existing risk → policy → dispatch governance chain.
#
# CRITICAL RULE: This scanner does NOT send messages.
# It only creates risk/policy evaluation candidates.
# All outbound messages must still go through:
#   RiskPredictor → RecoveryPolicyEngine → ProactiveMessageDispatcher
#
# Architecture:
#   SilentUserScanner (radar) → observes silence
#   RiskPredictor (interpreter) → evaluates risk
#   RecoveryPolicyEngine (permission) → governs contact
#   ProactiveMessageDispatcher (sender) → the ONLY outbound path
# =============================================================================

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("silent_user_scanner")

# ---------------------------------------------------------------------------
# Scan thresholds (hours of silence before candidate is eligible)
# ---------------------------------------------------------------------------
SCAN_THRESHOLDS_HOURS: Dict[str, float] = {
    "pre_payment_interest":       12.0,
    "payment_hesitation":          6.0,
    "post_payment_silence":        6.0,
    "onboarding_incomplete":      12.0,
    "data_collection_incomplete": 24.0,
    "analysis_missing":           24.0,
    "waiting":                    24.0,
    "trust_collapse":             12.0,
    "emotional_overload":         48.0,   # only after long cooldown
    "default":                    12.0,
}

# Minimum interval between scans of the same user (minutes)
MIN_SCAN_INTERVAL_MINUTES: int = 30

# Safety: never re-scan a user scanned within this many minutes
MIN_RESCAN_MINUTES: int = 25

# Priority stage groups (ordered highest → lowest priority)
PRIORITY_STAGES = [
    "payment_hesitation",
    "post_payment_silence",
    "onboarding_incomplete",
    "data_collection_incomplete",
    "analysis_missing",
    "waiting",
    "trust_collapse",
    "emotional_overload",
    "pre_payment_interest",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScanCandidate:
    """A user selected for silent scan evaluation."""
    user_id: int
    stage: str
    silence_hours: float
    scan_reason: str
    last_user_message_at: Optional[datetime]
    recovery_attempt_count: int = 0
    fatigue_score: float = 0.0


@dataclass
class ScanResult:
    """Result of one scanner run."""
    scan_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    candidates_found: int = 0
    candidates_skipped: int = 0
    policies_created: int = 0
    dispatch_eligible: int = 0
    scan_errors: int = 0
    top_scan_reasons: List[str] = field(default_factory=list)
    skipped_reasons: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SilentUserScanner
# ---------------------------------------------------------------------------

class SilentUserScanner:
    """
    Scheduled scanner that detects silent users and feeds them
    into the risk → policy → dispatch governance chain.

    Does NOT send messages directly.
    """

    def __init__(self, db_pool=None):
        self._pool = db_pool
        self._running = False
        self._scan_loop_task: Optional[asyncio.Task] = None
        self._last_result: Optional[ScanResult] = None
        self._scan_count: int = 0
        log.info("[SCANNER] SilentUserScanner initialized")

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def run_scan(self) -> ScanResult:
        """
        Run one full silent user scan cycle.
        Returns a ScanResult with stats.
        Fails closed: any exception suppresses outbound action.
        """
        result = ScanResult()
        if not self._pool:
            log.warning("[SCANNER] No DB pool — skipping scan")
            return result

        try:
            candidates = await self._select_candidates()
            result.candidates_found = len(candidates)

            for candidate in candidates:
                try:
                    skip_reason = await self._check_safety_gates(candidate)
                    if skip_reason:
                        result.candidates_skipped += 1
                        result.skipped_reasons[skip_reason] = (
                            result.skipped_reasons.get(skip_reason, 0) + 1
                        )
                        log.debug(
                            "[SCANNER] user=%s skipped: %s",
                            candidate.user_id, skip_reason,
                        )
                        continue

                    # Feed into risk → policy chain (no direct send)
                    policy_created, dispatch_eligible = await self._feed_governance_chain(
                        candidate
                    )
                    if policy_created:
                        result.policies_created += 1
                    if dispatch_eligible:
                        result.dispatch_eligible += 1

                    # Update scan tracking fields
                    await self._update_scan_tracking(candidate)

                except Exception as e:
                    result.scan_errors += 1
                    log.error(
                        "[SCANNER] error processing user=%s: %s",
                        candidate.user_id, e, exc_info=True,
                    )

            # Collect top scan reasons
            from collections import Counter
            reason_counter: Counter = Counter(
                c.scan_reason for c in candidates
            )
            result.top_scan_reasons = [r for r, _ in reason_counter.most_common(5)]

            self._last_result = result
            self._scan_count += 1
            log.info(
                "[SCANNER] Scan #%d complete — found=%d skipped=%d policies=%d eligible=%d errors=%d",
                self._scan_count,
                result.candidates_found,
                result.candidates_skipped,
                result.policies_created,
                result.dispatch_eligible,
                result.scan_errors,
            )

        except Exception as e:
            result.scan_errors += 1
            log.error("[SCANNER] run_scan fatal error: %s", e, exc_info=True)

        return result

    def get_last_result(self) -> Optional[ScanResult]:
        """Return the last scan result for dashboard exposure."""
        return self._last_result

    def get_scan_count(self) -> int:
        return self._scan_count

    # -----------------------------------------------------------------------
    # Candidate selection
    # -----------------------------------------------------------------------

    async def _select_candidates(self) -> List[ScanCandidate]:
        """
        Query pm_client_profiles for users who:
        - Have been silent past the stage threshold
        - Are not already protected by safety flags
        - Have not been scanned recently
        """
        if not self._pool:
            return []

        candidates: List[ScanCandidate] = []

        try:
            async with self._pool.acquire() as conn:
                # Base query: active users with silence past threshold
                # We check each stage threshold using CASE logic
                rows = await conn.fetch(
                    """
                    SELECT
                        user_id,
                        COALESCE(current_stage, 'default') AS stage,
                        last_user_message_at,
                        last_silent_scan_at,
                        silent_scan_count,
                        recovery_attempt_count,
                        fatigue_score,
                        silence_respect,
                        explicit_refusal,
                        human_escalation_required,
                        route_lock,
                        trust_lock,
                        recovery_cooldown_until,
                        last_ai_message_at,
                        emotional_overload_flag,
                        EXTRACT(EPOCH FROM (NOW() - last_user_message_at)) / 3600.0
                            AS silence_hours
                    FROM pm_client_profiles
                    WHERE
                        -- Must have messaged at some point
                        last_user_message_at IS NOT NULL
                        -- Not silence respect
                        AND COALESCE(silence_respect, FALSE) = FALSE
                        -- Not explicit refusal
                        AND COALESCE(explicit_refusal, FALSE) = FALSE
                        -- Not human escalation
                        AND COALESCE(human_escalation_required, FALSE) = FALSE
                        -- Not route locked
                        AND COALESCE(route_lock, FALSE) = FALSE
                        -- Not trust locked
                        AND COALESCE(trust_lock, FALSE) = FALSE
                        -- Cooldown expired or null
                        AND (recovery_cooldown_until IS NULL
                             OR recovery_cooldown_until < NOW())
                        -- Not messaged by AI in last 60 minutes
                        AND (last_ai_message_at IS NULL
                             OR last_ai_message_at < NOW() - INTERVAL '60 minutes')
                        -- Not scanned within minimum interval
                        AND (last_silent_scan_at IS NULL
                             OR last_silent_scan_at < NOW() - INTERVAL '25 minutes')
                        -- Has been silent for at least 6 hours (minimum threshold)
                        AND last_user_message_at < NOW() - INTERVAL '6 hours'
                    ORDER BY
                        -- Prioritise payment hesitation & post-payment first
                        CASE COALESCE(current_stage, 'default')
                            WHEN 'payment_hesitation'          THEN 1
                            WHEN 'post_payment_silence'        THEN 2
                            WHEN 'onboarding_incomplete'       THEN 3
                            WHEN 'data_collection_incomplete'  THEN 4
                            WHEN 'analysis_missing'            THEN 5
                            WHEN 'waiting'                     THEN 6
                            WHEN 'trust_collapse'              THEN 7
                            WHEN 'emotional_overload'          THEN 8
                            ELSE 9
                        END,
                        last_user_message_at ASC
                    LIMIT 50
                    """
                )

                for row in rows:
                    stage = row["stage"]
                    silence_hours = float(row["silence_hours"] or 0)
                    threshold = SCAN_THRESHOLDS_HOURS.get(
                        stage, SCAN_THRESHOLDS_HOURS["default"]
                    )

                    # Apply stage-specific threshold
                    if silence_hours < threshold:
                        continue

                    scan_reason = self._determine_scan_reason(stage, silence_hours)

                    candidates.append(
                        ScanCandidate(
                            user_id=int(row["user_id"]),
                            stage=stage,
                            silence_hours=round(silence_hours, 1),
                            scan_reason=scan_reason,
                            last_user_message_at=row["last_user_message_at"],
                            recovery_attempt_count=int(
                                row["recovery_attempt_count"] or 0
                            ),
                            fatigue_score=float(row["fatigue_score"] or 0.0),
                        )
                    )

        except Exception as e:
            log.error("[SCANNER] _select_candidates error: %s", e, exc_info=True)

        return candidates

    def _determine_scan_reason(self, stage: str, silence_hours: float) -> str:
        """Return a human-readable scan reason."""
        if stage == "payment_hesitation":
            return f"payment_hesitation_silent_{int(silence_hours)}h"
        if stage == "post_payment_silence":
            return f"post_payment_silent_{int(silence_hours)}h"
        if stage == "onboarding_incomplete":
            return f"onboarding_incomplete_{int(silence_hours)}h"
        if stage == "data_collection_incomplete":
            return f"data_collection_gap_{int(silence_hours)}h"
        if stage == "analysis_missing":
            return f"analysis_missing_{int(silence_hours)}h"
        if stage == "trust_collapse":
            return f"trust_collapse_silent_{int(silence_hours)}h"
        if stage == "emotional_overload":
            return f"emotional_overload_window_{int(silence_hours)}h"
        if silence_hours >= 48:
            return f"extended_silence_{int(silence_hours)}h"
        return f"silent_{stage}_{int(silence_hours)}h"

    # -----------------------------------------------------------------------
    # Safety gates
    # -----------------------------------------------------------------------

    async def _check_safety_gates(self, candidate: ScanCandidate) -> Optional[str]:
        """
        Re-check all safety flags from the DB (fresh read).
        Returns a skip reason string if the candidate should be skipped,
        or None if safe to process.

        Safety gates are absolute — any hit = skip.
        """
        if not self._pool:
            return "no_db_pool"

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        silence_respect,
                        explicit_refusal,
                        human_escalation_required,
                        route_lock,
                        trust_lock,
                        recovery_cooldown_until,
                        last_ai_message_at,
                        last_silent_scan_at,
                        emotional_overload_flag,
                        fatigue_score
                    FROM pm_client_profiles
                    WHERE user_id = $1
                    """,
                    candidate.user_id,
                )

            if not row:
                return "user_not_found"

            # Absolute safety gates
            if row["silence_respect"]:
                return "silence_respect"
            if row["explicit_refusal"]:
                return "explicit_refusal"
            if row["human_escalation_required"]:
                return "human_escalation_active"
            if row["route_lock"]:
                return "route_lock"
            if row["trust_lock"]:
                return "trust_lock"

            # Cooldown gate
            cooldown_until = row["recovery_cooldown_until"]
            if cooldown_until:
                now = datetime.now(timezone.utc)
                if cooldown_until.tzinfo is None:
                    cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
                if cooldown_until > now:
                    return "cooldown_active"

            # Recent AI message gate (60 minute protection)
            last_ai = row["last_ai_message_at"]
            if last_ai:
                now = datetime.now(timezone.utc)
                if last_ai.tzinfo is None:
                    last_ai = last_ai.replace(tzinfo=timezone.utc)
                age_min = (now - last_ai).total_seconds() / 60
                if age_min < 60:
                    return "recent_ai_message"

            # Recent scan gate
            last_scan = row["last_silent_scan_at"]
            if last_scan:
                now = datetime.now(timezone.utc)
                if last_scan.tzinfo is None:
                    last_scan = last_scan.replace(tzinfo=timezone.utc)
                age_min = (now - last_scan).total_seconds() / 60
                if age_min < MIN_RESCAN_MINUTES:
                    return "recently_scanned"

            # Emotional overload — only process after full cooldown
            if row["emotional_overload_flag"] and candidate.stage != "emotional_overload":
                return "emotional_overload_active"

            return None  # safe to process

        except Exception as e:
            log.error(
                "[SCANNER] _check_safety_gates error user=%s: %s",
                candidate.user_id, e, exc_info=True,
            )
            return "safety_gate_error"

    # -----------------------------------------------------------------------
    # Governance chain feed
    # -----------------------------------------------------------------------

    async def _feed_governance_chain(
        self, candidate: ScanCandidate
    ) -> tuple[bool, bool]:
        """
        Feed candidate into: RiskPredictor → RecoveryPolicyEngine.
        Returns (policy_created, dispatch_eligible).

        Does NOT send messages. Dispatcher picks up approved decisions.
        """
        policy_created = False
        dispatch_eligible = False

        try:
            # Step 1 — RiskPredictor
            from risk_predictor import get_risk_predictor
            risk_predictor = get_risk_predictor()
            if risk_predictor:
                risk_result = await risk_predictor.predict_for_user(candidate.user_id)
                if risk_result:
                    log.debug(
                        "[SCANNER] user=%s risk=%s level=%s",
                        candidate.user_id,
                        risk_result.risk_type,
                        risk_result.risk_level,
                    )

            # Step 2 — RecoveryPolicyEngine
            from recovery_policy_engine import get_policy_engine
            policy_engine = get_policy_engine()
            if policy_engine:
                decision = await policy_engine.evaluate_recovery_policy_for_user(
                    candidate.user_id
                )
                if decision:
                    policy_created = True
                    if (
                        decision.action == "ALLOW"
                        and decision.next_action == "SEND_SOFT_RECOVERY"
                        and not decision.silence_respect
                        and not decision.human_escalation_required
                    ):
                        dispatch_eligible = True
                    log.debug(
                        "[SCANNER] user=%s policy=%s next=%s",
                        candidate.user_id,
                        decision.action,
                        decision.next_action,
                    )

        except ImportError as e:
            log.warning("[SCANNER] governance import error: %s", e)
        except Exception as e:
            log.error(
                "[SCANNER] _feed_governance_chain error user=%s: %s",
                candidate.user_id, e, exc_info=True,
            )

        return policy_created, dispatch_eligible

    # -----------------------------------------------------------------------
    # Scan tracking update
    # -----------------------------------------------------------------------

    async def _update_scan_tracking(self, candidate: ScanCandidate) -> None:
        """
        Update pm_client_profiles scan tracking fields after processing.
        Idempotent: uses INSERT ON CONFLICT pattern via UPDATE.
        """
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE pm_client_profiles
                    SET
                        last_silent_scan_at = NOW(),
                        silent_scan_count   = COALESCE(silent_scan_count, 0) + 1,
                        silent_scan_reason  = $2
                    WHERE user_id = $1
                    """,
                    candidate.user_id,
                    candidate.scan_reason,
                )
        except Exception as e:
            log.error(
                "[SCANNER] _update_scan_tracking error user=%s: %s",
                candidate.user_id, e, exc_info=True,
            )

    # -----------------------------------------------------------------------
    # Scheduled loop (called from runtime_supervisor / main.py)
    # -----------------------------------------------------------------------

    async def start_scheduled_loop(self, interval_minutes: int = 30) -> None:
        """
        Start the background 30-minute scan loop.
        Safe singleton: if already running, does nothing.
        """
        if self._running:
            log.warning("[SCANNER] Scan loop already running — ignoring duplicate start")
            return

        self._running = True
        self._scan_loop_task = asyncio.create_task(
            self._scan_loop(interval_minutes)
        )
        log.info(
            "[SCANNER] Scheduled scan loop started (interval=%dm)",
            interval_minutes,
        )

    async def stop(self) -> None:
        """Stop the scan loop gracefully."""
        self._running = False
        if self._scan_loop_task:
            self._scan_loop_task.cancel()
            try:
                await self._scan_loop_task
            except asyncio.CancelledError:
                pass
        log.info("[SCANNER] Scan loop stopped")

    async def _scan_loop(self, interval_minutes: int) -> None:
        """Internal loop — runs scan every interval_minutes."""
        interval_s = interval_minutes * 60
        while self._running:
            try:
                await asyncio.sleep(interval_s)
                if self._running:
                    log.info("[SCANNER] Starting scheduled silent scan")
                    await self.run_scan()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[SCANNER] scan_loop error: %s", e, exc_info=True)
                # Wait before retrying to avoid tight error loop
                await asyncio.sleep(60)

    # -----------------------------------------------------------------------
    # Dashboard stats
    # -----------------------------------------------------------------------

    def get_scanner_stats(self) -> Dict[str, Any]:
        """Return stats dict for dashboard exposure."""
        result = self._last_result
        return {
            "scan_count":           self._scan_count,
            "last_scan_at":         result.scan_at.isoformat() if result else None,
            "candidates_found":     result.candidates_found if result else 0,
            "candidates_skipped":   result.candidates_skipped if result else 0,
            "policies_created":     result.policies_created if result else 0,
            "dispatch_eligible":    result.dispatch_eligible if result else 0,
            "scan_errors":          result.scan_errors if result else 0,
            "top_scan_reasons":     result.top_scan_reasons if result else [],
            "skipped_reasons":      result.skipped_reasons if result else {},
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scanner: Optional[SilentUserScanner] = None


def get_scanner() -> Optional[SilentUserScanner]:
    """Return the module-level scanner singleton (may be None if not initialised)."""
    return _scanner


def init_scanner(db_pool=None) -> SilentUserScanner:
    """Initialise and return the module-level scanner singleton."""
    global _scanner
    if _scanner is None:
        _scanner = SilentUserScanner(db_pool=db_pool)
        log.info("[SCANNER] SilentUserScanner singleton created")
    return _scanner

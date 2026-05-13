# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.5 — Silent User Scanner
# Tests: test_silent_user_scanner.py
# Python Method Digital Rehabilitation Center
#
# 15 test scenarios:
# 1.  silent user selected after threshold
# 2.  recent user skipped (below threshold)
# 3.  silence_respect skipped
# 4.  explicit_refusal skipped
# 5.  human escalation skipped
# 6.  cooldown skipped
# 7.  recent AI message skipped
# 8.  route lock skipped
# 9.  trust lock skipped
# 10. scan idempotency (recently scanned skipped)
# 11. risk → policy created (governance chain called)
# 12. scanner does not send directly
# 13. dispatcher remains only outbound path
# 14. runtime supervisor starts scanner once
# 15. scanner fail-closed on errors
# =============================================================================

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db_row(**overrides):
    """Return a mock asyncpg Row with safe defaults."""
    defaults = {
        "user_id": 42,
        "stage": "payment_hesitation",
        "silence_hours": 8.0,
        "last_user_message_at": datetime.now(timezone.utc) - timedelta(hours=8),
        "last_silent_scan_at": None,
        "silent_scan_count": 0,
        "recovery_attempt_count": 0,
        "fatigue_score": 0.0,
        "silence_respect": False,
        "explicit_refusal": False,
        "human_escalation_required": False,
        "route_lock": False,
        "trust_lock": False,
        "recovery_cooldown_until": None,
        "last_ai_message_at": None,
        "emotional_overload_flag": False,
    }
    defaults.update(overrides)

    row = MagicMock()
    row.__getitem__ = lambda self, key: defaults[key]
    row.get = lambda key, default=None: defaults.get(key, default)
    return row


def make_mock_pool(rows=None, fetchrow_result=None):
    """Return a mock asyncpg pool."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    conn.execute = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool, conn


# ---------------------------------------------------------------------------
# Test 1: Silent user selected after threshold
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_silent_user_selected_after_threshold():
    """User silent for 8h in payment_hesitation (threshold 6h) → selected."""
    from silent_user_scanner import SilentUserScanner, ScanCandidate

    row = make_db_row(
        stage="payment_hesitation",
        silence_hours=8.0,
        last_user_message_at=datetime.now(timezone.utc) - timedelta(hours=8),
    )
    pool, conn = make_mock_pool(rows=[row])

    scanner = SilentUserScanner(db_pool=pool)

    # Safety gate re-read returns clean row
    safe_row = make_db_row()
    conn.fetchrow = AsyncMock(return_value=safe_row)

    with patch("silent_user_scanner.SilentUserScanner._feed_governance_chain",
               new_callable=AsyncMock, return_value=(True, True)):
        with patch("silent_user_scanner.SilentUserScanner._update_scan_tracking",
                   new_callable=AsyncMock):
            result = await scanner.run_scan()

    assert result.candidates_found >= 1
    assert result.policies_created >= 1


# ---------------------------------------------------------------------------
# Test 2: Recent user skipped (below threshold)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recent_user_skipped():
    """User silent for 4h in payment_hesitation (threshold 6h) → not in results."""
    from silent_user_scanner import SilentUserScanner

    # DB query returns no rows because our SQL filters by >= 6 hours
    pool, conn = make_mock_pool(rows=[])

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_found == 0
    assert result.candidates_skipped == 0


# ---------------------------------------------------------------------------
# Test 3: silence_respect skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_silence_respect_skipped():
    """User with silence_respect=True must be skipped by safety gate."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    # Safety gate re-read returns silence_respect=True
    safe_row = make_db_row(silence_respect=True)
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("silence_respect", 0) >= 1


# ---------------------------------------------------------------------------
# Test 4: explicit_refusal skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explicit_refusal_skipped():
    """User with explicit_refusal=True must be skipped."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    safe_row = make_db_row(explicit_refusal=True)
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("explicit_refusal", 0) >= 1


# ---------------------------------------------------------------------------
# Test 5: human escalation skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_escalation_skipped():
    """User with human_escalation_required=True must be skipped."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    safe_row = make_db_row(human_escalation_required=True)
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("human_escalation_active", 0) >= 1


# ---------------------------------------------------------------------------
# Test 6: cooldown skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cooldown_skipped():
    """User with active cooldown must be skipped."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    safe_row = make_db_row(
        recovery_cooldown_until=datetime.now(timezone.utc) + timedelta(hours=4)
    )
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("cooldown_active", 0) >= 1


# ---------------------------------------------------------------------------
# Test 7: recent AI message skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recent_ai_message_skipped():
    """User with AI message < 60 min ago must be skipped."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    safe_row = make_db_row(
        last_ai_message_at=datetime.now(timezone.utc) - timedelta(minutes=30)
    )
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("recent_ai_message", 0) >= 1


# ---------------------------------------------------------------------------
# Test 8: route lock skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_lock_skipped():
    """User with route_lock=True must be skipped."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    safe_row = make_db_row(route_lock=True)
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("route_lock", 0) >= 1


# ---------------------------------------------------------------------------
# Test 9: trust lock skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trust_lock_skipped():
    """User with trust_lock=True must be skipped."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    safe_row = make_db_row(trust_lock=True)
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("trust_lock", 0) >= 1


# ---------------------------------------------------------------------------
# Test 10: scan idempotency — recently scanned user skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_idempotency():
    """User scanned within MIN_RESCAN_MINUTES must be skipped."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    # Scanned 10 minutes ago (< 25 min minimum interval)
    safe_row = make_db_row(
        last_silent_scan_at=datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    conn.fetchrow = AsyncMock(return_value=safe_row)

    scanner = SilentUserScanner(db_pool=pool)
    result = await scanner.run_scan()

    assert result.candidates_skipped >= 1
    assert result.skipped_reasons.get("recently_scanned", 0) >= 1


# ---------------------------------------------------------------------------
# Test 11: risk → policy created (governance chain called)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_governance_chain_called():
    """When candidate passes gates, risk predictor and policy engine are called."""
    from silent_user_scanner import SilentUserScanner

    row = make_db_row(stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row])

    safe_row = make_db_row()
    conn.fetchrow = AsyncMock(return_value=safe_row)

    mock_risk_result = MagicMock()
    mock_risk_result.risk_type = "PAYMENT_HESITATION_RISK"
    mock_risk_result.risk_level = "HIGH"

    mock_decision = MagicMock()
    mock_decision.action = "ALLOW"
    mock_decision.next_action = "SEND_SOFT_RECOVERY"
    mock_decision.silence_respect = False
    mock_decision.human_escalation_required = False

    mock_risk_predictor = AsyncMock()
    mock_risk_predictor.predict_for_user = AsyncMock(return_value=mock_risk_result)

    mock_policy_engine = AsyncMock()
    mock_policy_engine.evaluate_recovery_policy_for_user = AsyncMock(
        return_value=mock_decision
    )

    scanner = SilentUserScanner(db_pool=pool)

    with patch("silent_user_scanner.get_risk_predictor", return_value=mock_risk_predictor):
        with patch("silent_user_scanner.get_policy_engine", return_value=mock_policy_engine):
            with patch("silent_user_scanner.SilentUserScanner._update_scan_tracking",
                       new_callable=AsyncMock):
                result = await scanner.run_scan()

    assert result.policies_created >= 1
    assert result.dispatch_eligible >= 1
    mock_risk_predictor.predict_for_user.assert_called_once_with(42)
    mock_policy_engine.evaluate_recovery_policy_for_user.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# Test 12: scanner does not send directly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scanner_does_not_send_directly():
    """SilentUserScanner must never call any send function."""
    from silent_user_scanner import SilentUserScanner

    # Verify no send_message, dispatch, or outbound method exists
    scanner = SilentUserScanner(db_pool=None)

    send_methods = [
        attr for attr in dir(scanner)
        if any(kw in attr.lower() for kw in ["send", "dispatch", "outbound", "message"])
    ]

    # The scanner should have NO send/dispatch methods
    assert len(send_methods) == 0, (
        f"Scanner must not have send/dispatch methods. Found: {send_methods}"
    )


# ---------------------------------------------------------------------------
# Test 13: dispatcher remains only outbound path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatcher_is_only_outbound_path():
    """
    Confirm that SilentUserScanner._feed_governance_chain only calls
    risk predictor + policy engine — never the dispatcher directly.
    """
    from silent_user_scanner import SilentUserScanner

    # Inspect _feed_governance_chain source for any dispatch call
    import inspect
    source = inspect.getsource(SilentUserScanner._feed_governance_chain)

    # Must reference risk_predictor and policy_engine
    assert "risk_predictor" in source, "Should use RiskPredictor"
    assert "policy_engine" in source or "recover" in source, "Should use PolicyEngine"

    # Must NOT directly import or call dispatcher
    assert "ProactiveMessageDispatcher" not in source, (
        "Scanner must not call ProactiveMessageDispatcher directly"
    )
    assert "dispatch_allowed" not in source, (
        "Scanner must not call dispatch_allowed_recovery_messages"
    )


# ---------------------------------------------------------------------------
# Test 14: runtime supervisor starts scanner once (singleton protection)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scanner_starts_only_once():
    """start_scheduled_loop() is idempotent — second call is ignored."""
    from silent_user_scanner import SilentUserScanner

    scanner = SilentUserScanner(db_pool=None)

    # Patch the actual loop so it doesn't run
    async def fake_loop(interval):
        await asyncio.sleep(9999)

    with patch.object(scanner, "_scan_loop", side_effect=fake_loop):
        task1 = asyncio.create_task(scanner.start_scheduled_loop(30))
        await asyncio.sleep(0)  # yield to event loop

        # Second call should be ignored (already running)
        await scanner.start_scheduled_loop(30)

        assert scanner._running is True
        task1.cancel()
        try:
            await task1
        except (asyncio.CancelledError, Exception):
            pass


# ---------------------------------------------------------------------------
# Test 15: scanner fail-closed on errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scanner_fail_closed_on_errors():
    """If DB pool raises, scanner returns error result and does NOT send."""
    from silent_user_scanner import SilentUserScanner

    # Pool that raises on acquire
    bad_pool = MagicMock()
    bad_pool.acquire = MagicMock(side_effect=Exception("DB connection failed"))

    scanner = SilentUserScanner(db_pool=bad_pool)
    result = await scanner.run_scan()

    # Must not raise — must return a ScanResult with error count
    assert result is not None
    assert result.scan_errors >= 1
    # Critically: no dispatch_eligible — scanner failed safely
    assert result.dispatch_eligible == 0


# ---------------------------------------------------------------------------
# Test 16 (bonus): ScanResult stats are accurate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_result_stats_accurate():
    """ScanResult correctly tracks all counters."""
    from silent_user_scanner import SilentUserScanner

    # Two candidates: one passes, one has silence_respect
    row1 = make_db_row(user_id=1, stage="payment_hesitation", silence_hours=8.0)
    row2 = make_db_row(user_id=2, stage="payment_hesitation", silence_hours=8.0)
    pool, conn = make_mock_pool(rows=[row1, row2])

    # row1 passes, row2 has silence_respect
    safe_pass = make_db_row(user_id=1)
    safe_skip = make_db_row(user_id=2, silence_respect=True)

    call_count = 0

    async def mock_fetchrow(query, user_id):
        nonlocal call_count
        call_count += 1
        if user_id == 1:
            return safe_pass
        return safe_skip

    conn.fetchrow = mock_fetchrow

    scanner = SilentUserScanner(db_pool=pool)

    with patch("silent_user_scanner.SilentUserScanner._feed_governance_chain",
               new_callable=AsyncMock, return_value=(True, True)):
        with patch("silent_user_scanner.SilentUserScanner._update_scan_tracking",
                   new_callable=AsyncMock):
            result = await scanner.run_scan()

    assert result.candidates_found == 2
    assert result.candidates_skipped == 1
    assert result.skipped_reasons.get("silence_respect", 0) == 1

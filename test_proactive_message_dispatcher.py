# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.4 — Proactive Message Dispatcher Tests
# Module: test_proactive_message_dispatcher.py
# 14 scenarios covering all send/block/fail-closed cases
# =============================================================================

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proactive_message_dispatcher import (
    ProactiveMessageDispatcher,
    DispatchResult,
    MESSAGE_TEMPLATES,
    SENDABLE_TONES,
    NEVER_SEND_TONES,
    POLICY_FRESHNESS_MINUTES,
    MIN_SEND_GAP_MINUTES,
)


def _now():
    return datetime.now(timezone.utc)


def _make_row(
    uid=12345, tone='soft_checkin', policy_id=1,
    silence=False, he=False,
    cooldown=None, created_at=None
):
    return {
        'id': policy_id,
        'user_id': uid,
        'tone_mode': tone,
        'silence_respect': silence,
        'human_escalation_required': he,
        'cooldown_until': cooldown,
        'fatigue_score': 0.1,
        'suppression_reason': '',
        'created_at': created_at or _now(),
    }


def _make_profile(
    silence=False, explicit_refusal=False, he=False,
    cooldown_until=None, last_ai=None,
    attempt_count=0, is_active=True
):
    return {
        'silence_respect': silence,
        'explicit_refusal': explicit_refusal,
        'human_escalation_required': he,
        'recovery_cooldown_until': cooldown_until,
        'last_ai_message_at': last_ai,
        'recovery_attempt_count': attempt_count,
        'last_recovery_at': None,
        'is_active': is_active,
    }


def _make_dispatcher(send_fn=None, pool=None):
    d = ProactiveMessageDispatcher(db_pool=pool, send_message_fn=send_fn)
    return d


# ---------------------------------------------------------------------------
# Scenario 1 — ALLOW sends one message
# ---------------------------------------------------------------------------
def test_allow_sends_message():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    conn.fetchrow = AsyncMock(return_value=None)       # not already sent
    conn.fetch = AsyncMock(return_value=[])            # no existing
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)

    d = _make_dispatcher(send_fn=send_fn, pool=pool)

    profile = _make_profile()
    row = _make_row()

    # Patch internal methods
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=profile)
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[row])

    result_count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )

    assert result_count == 1, f'Expected 1 sent, got {result_count}'
    assert len(sent) == 1
    print('PASS: test_allow_sends_message')


# ---------------------------------------------------------------------------
# Scenario 2 — SUPPRESS does not send
# ---------------------------------------------------------------------------
def test_suppress_does_not_send():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=_make_profile(silence=True))
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    assert len(sent) == 0
    print('PASS: test_suppress_does_not_send')


# ---------------------------------------------------------------------------
# Scenario 3 — DELAY (cooldown) does not send
# ---------------------------------------------------------------------------
def test_cooldown_does_not_send():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=_make_profile(
        cooldown_until=_now() + timedelta(hours=2)
    ))
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    assert len(sent) == 0
    print('PASS: test_cooldown_does_not_send')


# ---------------------------------------------------------------------------
# Scenario 4 — ESCALATE_HUMAN does not send automated recovery
# ---------------------------------------------------------------------------
def test_human_escalation_blocks_send():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=_make_profile(he=True))
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    print('PASS: test_human_escalation_blocks_send')


# ---------------------------------------------------------------------------
# Scenario 5 — SILENCE_RESPECT does not send
# ---------------------------------------------------------------------------
def test_silence_respect_never_sends():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    # Even if profile allows, silence_respect tone must not be sent
    d._get_user_profile = AsyncMock(return_value=_make_profile())
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[
        _make_row(tone='silence_respect')
    ])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    assert len(sent) == 0
    print('PASS: test_silence_respect_never_sends')


# ---------------------------------------------------------------------------
# Scenario 6 — Duplicate does not double-send
# ---------------------------------------------------------------------------
def test_duplicate_policy_log_does_not_double_send():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=True)   # simulate already sent
    d._get_user_profile = AsyncMock(return_value=_make_profile())
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    assert len(sent) == 0
    print('PASS: test_duplicate_policy_log_does_not_double_send')


# ---------------------------------------------------------------------------
# Scenario 7 — Recent AI message blocks send
# ---------------------------------------------------------------------------
def test_recent_ai_message_blocks_send():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=_make_profile(
        last_ai=_now() - timedelta(minutes=30)  # only 30 min ago
    ))
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    print('PASS: test_recent_ai_message_blocks_send')


# ---------------------------------------------------------------------------
# Scenario 8 — Explicit refusal blocks send
# ---------------------------------------------------------------------------
def test_explicit_refusal_blocks_send():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=_make_profile(explicit_refusal=True))
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    print('PASS: test_explicit_refusal_blocks_send')


# ---------------------------------------------------------------------------
# Scenario 9 — Stale policy decision does not send
# ---------------------------------------------------------------------------
def test_stale_policy_does_not_send():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=_make_profile())
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    stale_time = _now() - timedelta(minutes=POLICY_FRESHNESS_MINUTES + 10)
    d._fetch_candidates = AsyncMock(return_value=[
        _make_row(created_at=stale_time)
    ])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    print('PASS: test_stale_policy_does_not_send')


# ---------------------------------------------------------------------------
# Scenario 10 — Dispatcher error fails closed
# ---------------------------------------------------------------------------
def test_dispatcher_error_fails_closed():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(side_effect=Exception('DB connection lost'))
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    assert len(sent) == 0
    print('PASS: test_dispatcher_error_fails_closed')


# ---------------------------------------------------------------------------
# Scenario 11 — send_fn error fails closed
# ---------------------------------------------------------------------------
def test_send_fn_error_fails_closed():
    async def failing_send(uid, text):
        raise Exception('SendPulse timeout')

    d = _make_dispatcher(send_fn=failing_send)
    d._already_sent = AsyncMock(return_value=False)
    d._get_user_profile = AsyncMock(return_value=_make_profile())
    d._post_send_update = AsyncMock()
    d._log_dispatch = AsyncMock()
    d._fetch_candidates = AsyncMock(return_value=[_make_row()])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    print('PASS: test_send_fn_error_fails_closed')


# ---------------------------------------------------------------------------
# Scenario 12 — No candidates = 0 sends
# ---------------------------------------------------------------------------
def test_no_candidates_sends_nothing():
    sent = []
    async def send_fn(uid, text): sent.append((uid, text))

    d = _make_dispatcher(send_fn=send_fn)
    d._fetch_candidates = AsyncMock(return_value=[])

    count = asyncio.get_event_loop().run_until_complete(
        d.dispatch_allowed_recovery_messages()
    )
    assert count == 0
    assert len(sent) == 0
    print('PASS: test_no_candidates_sends_nothing')


# ---------------------------------------------------------------------------
# Scenario 13 — Template tone never uses pressure/sales language
# ---------------------------------------------------------------------------
def test_templates_never_sales_language():
    banned_words = [
        'купи', 'buy now', 'hurry', 'срочно', 'limited offer',
        'last chance', 'давление', 'давите', 'платите', 'немедленно',
        'скидка только сейчас', 'pay now', 'urgent'
    ]
    for tone, tmpl in MESSAGE_TEMPLATES.items():
        text = tmpl.get('text') or ''
        for word in banned_words:
            assert word.lower() not in text.lower(), (
                f"Banned word '{word}' found in template '{tone}'"
            )
    print('PASS: test_templates_never_sales_language')


# ---------------------------------------------------------------------------
# Scenario 14 — silence_respect template text is None (never sendable)
# ---------------------------------------------------------------------------
def test_silence_respect_template_is_none():
    assert MESSAGE_TEMPLATES['silence_respect']['text'] is None
    assert 'silence_respect' in NEVER_SEND_TONES
    assert 'silence_respect' not in SENDABLE_TONES
    print('PASS: test_silence_respect_template_is_none')


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    tests = [
        test_allow_sends_message,
        test_suppress_does_not_send,
        test_cooldown_does_not_send,
        test_human_escalation_blocks_send,
        test_silence_respect_never_sends,
        test_duplicate_policy_log_does_not_double_send,
        test_recent_ai_message_blocks_send,
        test_explicit_refusal_blocks_send,
        test_stale_policy_does_not_send,
        test_dispatcher_error_fails_closed,
        test_send_fn_error_fails_closed,
        test_no_candidates_sends_nothing,
        test_templates_never_sales_language,
        test_silence_respect_template_is_none,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f'FAIL: {t.__name__}: {e}')
    print(f'
Results: {passed}/{len(tests)} passed, {failed} failed')
    if failed == 0:
        print('ALL TESTS PASSED')

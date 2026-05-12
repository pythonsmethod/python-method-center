# -*- coding: utf-8 -*-
# Central AI Core v2.0 — Layer 4: Soft Auto-Routing Phase 2B + Phase 2C Governance
# Module: auto_router.py
# Purpose: Apply SAFE automatic route switches based on Route Resolver recommendations.
#          Phase 2B: faq_route enabled with FAQ Persistence Protection.
#          Phase 2C PREP: Trust Governance Layer (Guards 8-10 + trust lock) prepared.
#                         trust_route is NOT yet in _SAFE_ROUTES — observation only.
# Protection layers:
#   Guard 0:  no-op if proposed == current
#   Guard 1:  only SAFE routes (safe set gate)
#   Guard 2:  confidence gate >= 0.85
#   Guard 3:  rollback / cooldown (min 3 msgs between switches)
#   Guard 4:  analysis_route -> support_route blocked if msgs_since < 2
#   Guard 5:  onboarding_route -> support_route blocked if analysis_upload pending
#   Guard 6:  faq_route blocked if state == choosing OR intent == ready_to_pay
#   Guard 7:  faq_route blocked if onboarding_route + payment_status == paid
#   Guard 8:  [TRUST] trust_route blocked if intent != fear (rs-override NOT auto-trigger)
#   Guard 9:  [TRUST] trust_route blocked if analysis_route active or analysis_upload pending
#   Guard 10: [TRUST] trust_route blocked if onboarding_route + paid
#   Trust Lock: after switch to trust_route — 5-msg lock (only escalation/recovery can break)
# Connected in: agents.py -> process_message() after resolve_route()

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, Set

log = logging.getLogger('auto_router')

# ---------------------------------------------------------------------------
# SAFE ROUTES — PHASE 2B
# Phase 1: escalation_route, onboarding_route, analysis_route, recovery_route, payment_route
# Phase 2A: + support_route  (with Support Transition Protection)
# Phase 2B: + faq_route      (with FAQ Persistence Protection)
# Phase 2C: trust_route      (NOT YET ACTIVE — governance layer prepared below)
# ---------------------------------------------------------------------------
_SAFE_ROUTES = {
    'escalation_route',   # escalation_request intent → Karen
    'onboarding_route',   # paid intent/state → Iris
    'analysis_route',     # analysis_upload intent → Vera
    'recovery_route',     # stuck state / hang_stage → Nadia
    'payment_route',      # ready_to_pay intent/state → Maya
    'support_route',      # Phase 2A: emotional support / waiting paid → Gabriel
    'faq_route',          # Phase 2B: doubt/confusion → Sarah
    # 'trust_route',      # Phase 2C: NOT ACTIVE — enable after governance validation
}

# ---------------------------------------------------------------------------
# CONFIDENCE GATE — minimum confidence to allow automatic switching
# ---------------------------------------------------------------------------
_MIN_CONFIDENCE: float = 0.85

# ---------------------------------------------------------------------------
# ROLLBACK PROTECTION — max switches per N messages
# ---------------------------------------------------------------------------
_SWITCH_COOLDOWN_MSGS: int = 3

# ---------------------------------------------------------------------------
# SUPPORT TRANSITION PROTECTION (Phase 2A)
# Guard 4: block analysis_route → support_route too soon
# Guard 5: block onboarding_route → support_route when analysis_upload is pending
# ---------------------------------------------------------------------------
_SUPPORT_ANALYSIS_MIN_MSGS: int = 2   # Guard 4: min msgs since last switch when from=analysis

# ---------------------------------------------------------------------------
# FAQ PERSISTENCE PROTECTION (Phase 2B)
# Guard 6: payment_route priority over faq when choosing/ready_to_pay
# Guard 7: block faq during paid onboarding flow
# ---------------------------------------------------------------------------
# (no extra constants needed — conditions use session/intent/state directly)

# ---------------------------------------------------------------------------
# TRUST GOVERNANCE LAYER — Phase 2C preparation
# trust_route is NOT in _SAFE_ROUTES yet. These constants and guards are
# prepared in advance so activation requires only one-line change to _SAFE_ROUTES.
#
# Design principles:
#   1. Only EXPLICIT fear intent triggers trust auto-switch (not rs-override).
#      rs >= 0.75 override stays observation-only.
#   2. Active analysis flow must never be interrupted by trust_route.
#   3. Paid onboarding flow must never be diverted to trust_route.
#   4. Once in trust_route, a 5-message lock applies:
#      only escalation_route and recovery_route can break the lock.
# ---------------------------------------------------------------------------
_TRUST_MIN_CONFIDENCE: float = 0.90   # Higher bar than standard 0.85

_TRUST_LOCK_MSGS: int = 5             # Trust route lock duration (messages)

# Routes allowed to break trust lock — critical safety overrides only
_TRUST_LOCK_BREAKERS: Set[str] = {
    'escalation_route',   # User explicitly requests human — always allowed
    'recovery_route',     # User is stuck — always allowed
}

# ---------------------------------------------------------------------------
# ROUTE → AGENT MAP
# ---------------------------------------------------------------------------
_ROUTE_AGENTS: Dict[str, str] = {
    'reception':        'Lucky',
    'individual':       'Hannah',
    'trust_route':      'Sophia',
    'payment_route':    'Maya',
    'onboarding_route': 'Iris',
    'analysis_route':   'Vera',
    'escalation_route': 'Karen',
    'recovery_route':   'Nadia',
    'support_route':    'Gabriel',
    'faq_route':        'Sarah',
    'escalation':       'Karen',
    'tariff_recommend': 'Sarah',
    'onboarding':       'Iris',
    'support':          'Gabriel',
}


def _build_log_entry(
    contact_id: str,
    from_route: str,
    to_route: str,
    reason: str,
    confidence: float,
    intent: str,
    state: str,
    msg_count: int,
    switched: bool,
    block_reason: Optional[str] = None,
    trust_transition_reason: Optional[str] = None,
) -> Dict[str, Any]:
    entry = {
        'ts':           datetime.utcnow().isoformat(),
        'contact_id':   contact_id,
        'from':         from_route,
        'to':           to_route,
        'reason':       reason,
        'confidence':   confidence,
        'intent':       intent,
        'state':        state,
        'msg_count':    msg_count,
        'switched':     switched,
        'block_reason': block_reason,
    }
    if trust_transition_reason is not None:
        entry['trust_transition_reason'] = trust_transition_reason
    return entry


def _check_trust_guards(
    contact_id: str,
    current_route: str,
    proposed_route: str,
    route_confidence: float,
    route_reason: str,
    intent: str,
    state: str,
    history_len: int,
    payment_status: str,
    session: Dict[str, Any],
) -> Optional[str]:
    """
    Run trust-specific guards (8, 9, 10) for trust_route proposals.
    Returns block_reason string if blocked, None if all pass.
    These guards run BEFORE the switch is applied, regardless of safe-set status.
    When trust_route is added to _SAFE_ROUTES, these guards are already active.
    """
    if proposed_route != 'trust_route':
        return None

    # ── Guard 8: Trust Explicit Fear Guard ────────────────────────────
    # Only auto-switch to trust_route when intent is explicitly 'fear'.
    # rs-override (risk_score >= 0.75 triggering _rule_fear) must NOT trigger
    # auto-switch — it remains observation-only. rs-override cases will have
    # intent != 'fear' (e.g. intent='analysis_upload' with high rs).
    if intent != 'fear':
        block = (f'trust_guard8_explicit_fear_required:'
                 f'intent={intent}_not_fear'
                 f'(rs_override_stays_observation_only)')
        log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD8 trust requires explicit fear, got intent=%s',
                 contact_id, intent)
        return block

    # ── Guard 9: Trust Analysis Protection ────────────────────────────
    # Block trust_route if user is in analysis_route (active analysis flow)
    # or if proposed_route from resolver was analysis_route (analysis pending).
    # Vera's analysis conversation must never be interrupted by Sophia.
    if current_route == 'analysis_route':
        block = ('trust_guard9_analysis_protection:'
                 'analysis_route_active_cannot_switch_to_trust')
        log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD9 trust blocked: analysis_route active',
                 contact_id)
        return block

    proposed_analysis = session.get('proposed_route', '')
    if proposed_analysis == 'analysis_route' and intent == 'analysis_upload':
        block = ('trust_guard9_analysis_protection:'
                 'analysis_upload_pending_proposed_analysis')
        log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD9 trust blocked: analysis_upload pending',
                 contact_id)
        return block

    # ── Guard 10: Trust Onboarding Protection ─────────────────────────
    # Block trust_route if user is in onboarding flow AND has paid.
    # Paid onboarding is a structured critical flow — trust diversion
    # would interrupt Iris's onboarding sequence.
    if current_route == 'onboarding_route' and payment_status == 'paid':
        block = ('trust_guard10_onboarding_protection:'
                 'paid_onboarding_flow_active')
        log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD10 trust blocked: paid onboarding active',
                 contact_id)
        return block

    # ── Trust Confidence Gate (higher threshold) ───────────────────────
    if route_confidence < _TRUST_MIN_CONFIDENCE:
        block = (f'trust_confidence_gate:'
                 f'{route_confidence:.2f}<{_TRUST_MIN_CONFIDENCE}'
                 f'(trust_requires_higher_confidence)')
        log.info('[AUTO-ROUTE] BLOCKED contact=%s TRUST_CONF trust conf=%.2f < %.2f',
                 contact_id, route_confidence, _TRUST_MIN_CONFIDENCE)
        return block

    return None  # all trust guards passed


def _check_trust_lock(
    contact_id: str,
    current_route: str,
    proposed_route: str,
    session: Dict[str, Any],
    history_len: int,
) -> Optional[str]:
    """
    Enforce trust persistence lock.
    If the user is currently in trust_route, block all switches EXCEPT
    escalation_route and recovery_route for _TRUST_LOCK_MSGS messages
    after the trust switch occurred.
    Returns block_reason if locked, None if not locked or lock expired.
    """
    if current_route != 'trust_route':
        return None

    # Check if we are within the trust lock window
    trust_entered_at = session.get('trust_entered_at_msg', 0)
    msgs_in_trust = history_len - trust_entered_at

    if msgs_in_trust < _TRUST_LOCK_MSGS:
        # Lock is active — only breakers allowed
        if proposed_route not in _TRUST_LOCK_BREAKERS:
            block = (f'trust_lock_active:'
                     f'{msgs_in_trust}msgs_in_trust(lock={_TRUST_LOCK_MSGS}):'
                     f'only_escalation_recovery_can_break')
            log.info('[AUTO-ROUTE] BLOCKED contact=%s TRUST_LOCK active %d/%d proposed=%s',
                     contact_id, msgs_in_trust, _TRUST_LOCK_MSGS, proposed_route)
            return block

    return None  # lock expired or proposed is a breaker


def apply_auto_route(
    contact_id: str,
    session: Dict[str, Any],
    proposed_route: str,
    route_confidence: float,
    route_reason: str,
    intent: str,
    state: str,
) -> Dict[str, Any]:
    """
    Attempt to apply an automatic route switch.

    Returns a result dict with keys:
        switched                bool
        new_route               str
        block_reason            str|None
        trust_transition_reason str|None
        log_entry               dict
    """
    current_route   = session.get('route', 'reception')
    history_len     = len(session.get('history', []))
    last_switch_msg = session.get('route_last_switch_msg', 0)
    msgs_since_last = history_len - last_switch_msg
    payment_status  = session.get('payment_status', 'new')

    # ── Trust Lock Check (runs before all other guards) ───────────────
    # If currently in trust_route and lock is active, block non-breaker switches.
    trust_lock_block = _check_trust_lock(
        contact_id, current_route, proposed_route, session, history_len
    )
    if trust_lock_block:
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len,
                                 False, trust_lock_block)
        return {'switched': False, 'new_route': current_route,
                'block_reason': trust_lock_block, 'trust_transition_reason': None,
                'log_entry': entry}

    # ── Guard 0: no-op if proposed == current ─────────────────────────
    if proposed_route == current_route:
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, 'same_route')
        return {'switched': False, 'new_route': current_route,
                'block_reason': 'same_route', 'trust_transition_reason': None,
                'log_entry': entry}

    # ── Guard 1: only SAFE routes ──────────────────────────────────────
    if proposed_route not in _SAFE_ROUTES:
        block = 'route_not_in_safe_set:' + proposed_route
        log.info('[AUTO-ROUTE] BLOCKED contact=%s from=%s to=%s block=%s',
                 contact_id, current_route, proposed_route, block)
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, block)
        return {'switched': False, 'new_route': current_route, 'block_reason': block,
                'trust_transition_reason': None, 'log_entry': entry}

    # ── Guard 2: confidence gate ───────────────────────────────────────
    if route_confidence < _MIN_CONFIDENCE:
        block = f'confidence_below_threshold:{route_confidence:.2f}<{_MIN_CONFIDENCE}'
        log.info('[AUTO-ROUTE] BLOCKED contact=%s from=%s to=%s conf=%.2f',
                 contact_id, current_route, proposed_route, route_confidence)
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, block)
        return {'switched': False, 'new_route': current_route, 'block_reason': block,
                'trust_transition_reason': None, 'log_entry': entry}

    # ── Guard 3: rollback / cooldown ──────────────────────────────────
    if msgs_since_last < _SWITCH_COOLDOWN_MSGS:
        block = f'cooldown:{msgs_since_last}msgs_since_last_switch(min={_SWITCH_COOLDOWN_MSGS})'
        log.info('[AUTO-ROUTE] BLOCKED contact=%s cooldown=%d/%d from=%s to=%s',
                 contact_id, msgs_since_last, _SWITCH_COOLDOWN_MSGS, current_route, proposed_route)
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, block)
        return {'switched': False, 'new_route': current_route, 'block_reason': block,
                'trust_transition_reason': None, 'log_entry': entry}

    # ── Guard 4: Support Transition Protection — analysis flow guard ───
    if proposed_route == 'support_route' and current_route == 'analysis_route':
        if msgs_since_last < _SUPPORT_ANALYSIS_MIN_MSGS:
            block = (f'support_hijack_guard:analysis_flow_active:'
                     f'{msgs_since_last}msgs_since_switch(min={_SUPPORT_ANALYSIS_MIN_MSGS})')
            log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD4 analysis->support too_soon=%d/%d',
                     contact_id, msgs_since_last, _SUPPORT_ANALYSIS_MIN_MSGS)
            entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                     route_confidence, intent, state, history_len, False, block)
            return {'switched': False, 'new_route': current_route, 'block_reason': block,
                    'trust_transition_reason': None, 'log_entry': entry}

    # ── Guard 5: Support Transition Protection — onboarding flow guard ─
    if proposed_route == 'support_route' and current_route == 'onboarding_route':
        if intent == 'analysis_upload':
            block = 'support_hijack_guard:analysis_upload_pending_in_onboarding'
            log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD5 onboarding->support analysis_upload_pending',
                     contact_id)
            entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                     route_confidence, intent, state, history_len, False, block)
            return {'switched': False, 'new_route': current_route, 'block_reason': block,
                    'trust_transition_reason': None, 'log_entry': entry}

    # ── Guard 6: FAQ Persistence Protection — payment priority ─────────
    if proposed_route == 'faq_route':
        if state == 'choosing' or intent == 'ready_to_pay':
            block = (f'faq_payment_priority_guard:payment_context_active:'
                     f'state={state},intent={intent}')
            log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD6 faq blocked by payment context',
                     contact_id)
            entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                     route_confidence, intent, state, history_len, False, block)
            return {'switched': False, 'new_route': current_route, 'block_reason': block,
                    'trust_transition_reason': None, 'log_entry': entry}

    # ── Guard 7: FAQ Hijack Protection — paid onboarding guard ────────
    if proposed_route == 'faq_route' and current_route == 'onboarding_route':
        if payment_status == 'paid':
            block = 'faq_hijack_guard:paid_user_in_onboarding_flow'
            log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD7 faq blocked: paid onboarding active',
                     contact_id)
            entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                     route_confidence, intent, state, history_len, False, block)
            return {'switched': False, 'new_route': current_route, 'block_reason': block,
                    'trust_transition_reason': None, 'log_entry': entry}

    # ── Guards 8-10 + Trust Confidence Gate (Phase 2C) ────────────────
    # These guards run even though trust_route is not yet in _SAFE_ROUTES.
    # They are validated here so that activation is a safe one-line change.
    trust_block = _check_trust_guards(
        contact_id, current_route, proposed_route, route_confidence,
        route_reason, intent, state, history_len, payment_status, session,
    )
    if trust_block:
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len,
                                 False, trust_block)
        return {'switched': False, 'new_route': current_route, 'block_reason': trust_block,
                'trust_transition_reason': None, 'log_entry': entry}

    # ── ALL GUARDS PASSED — apply switch ──────────────────────────────
    new_agent = _ROUTE_AGENTS.get(proposed_route, proposed_route)

    # Build trust_transition_reason if switching to trust_route
    trust_transition_reason = None
    if proposed_route == 'trust_route':
        trust_transition_reason = (
            f'trust_switch:intent={intent},state={state},'
            f'conf={route_confidence:.2f},reason={route_reason}'
        )

    log.info(
        '[AUTO-ROUTE] SWITCHED contact=%s from=%s to=%s agent=%s '
        'intent=%s state=%s confidence=%.2f reason=%s msgs_since_last=%d',
        contact_id, current_route, proposed_route, new_agent,
        intent, state, route_confidence, route_reason, msgs_since_last,
    )

    entry = _build_log_entry(
        contact_id, current_route, proposed_route, route_reason,
        route_confidence, intent, state, history_len, True,
        trust_transition_reason=trust_transition_reason,
    )

    return {
        'switched':               True,
        'new_route':              proposed_route,
        'new_agent':              new_agent,
        'previous_route':         current_route,
        'block_reason':           None,
        'trust_transition_reason': trust_transition_reason,
        'log_entry':              entry,
    }

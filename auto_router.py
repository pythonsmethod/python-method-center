# -*- coding: utf-8 -*-
# Central AI Core v2.0 — Layer 4: Soft Auto-Routing Phase 2A
# Module: auto_router.py
# Purpose: Apply SAFE automatic route switches based on Route Resolver recommendations.
#          Phase 2A adds support_route with Support Transition Protection guards.
#          Observation layer (proposed_route) continues to run in parallel.
#          Unsafe routes (trust_route, fear-based rerouting) are NOT enabled.
# Protection:
#   - confidence gate: must be >= 0.85 to switch
#   - rollback protection: max 1 switch per 3 messages
#   - Guard 4: analysis_route -> support_route blocked if msgs_since_last_switch < 2
#   - Guard 5: onboarding_route -> support_route blocked if analysis_upload pending
# Connected in: agents.py -> process_message() after resolve_route()

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional

log = logging.getLogger('auto_router')

# ---------------------------------------------------------------------------
# SAFE ROUTES — PHASE 2A
# Phase 1: escalation_route, onboarding_route, analysis_route, recovery_route, payment_route
# Phase 2A adds: support_route  (with Support Transition Protection guards)
# trust_route, faq_route, fear-based rerouting NOT yet included.
# ---------------------------------------------------------------------------
_SAFE_ROUTES = {
    'escalation_route',   # escalation_request intent → Karen
    'onboarding_route',   # paid intent/state → Iris
    'analysis_route',     # analysis_upload intent → Vera
    'recovery_route',     # stuck state / hang_stage → Nadia
    'payment_route',      # ready_to_pay intent/state → Maya
    'support_route',      # Phase 2A: emotional support / waiting paid → Gabriel
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
# SUPPORT TRANSITION PROTECTION
# Guard 4: block analysis_route → support_route too soon
# Guard 5: block onboarding_route → support_route when analysis_upload is pending
# ---------------------------------------------------------------------------
_SUPPORT_ANALYSIS_MIN_MSGS: int = 2   # Guard 4: min messages since last switch when from=analysis

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
) -> Dict[str, Any]:
    return {
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
        switched        bool   — True if route was actually changed
        new_route       str    — final route after call (may be unchanged)
        block_reason    str|None
        log_entry       dict
    """
    current_route   = session.get('route', 'reception')
    history_len     = len(session.get('history', []))
    last_switch_msg = session.get('route_last_switch_msg', 0)
    msgs_since_last = history_len - last_switch_msg

    # ── Guard 0: no-op if proposed == current ─────────────────────────
    if proposed_route == current_route:
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, 'same_route')
        return {'switched': False, 'new_route': current_route,
                'block_reason': 'same_route', 'log_entry': entry}

    # ── Guard 1: only SAFE routes ──────────────────────────────────────
    if proposed_route not in _SAFE_ROUTES:
        block = 'route_not_in_safe_set:' + proposed_route
        log.info('[AUTO-ROUTE] BLOCKED contact=%s from=%s to=%s reason=%s block=%s',
                 contact_id, current_route, proposed_route, route_reason, block)
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, block)
        return {'switched': False, 'new_route': current_route, 'block_reason': block, 'log_entry': entry}

    # ── Guard 2: confidence gate ───────────────────────────────────────
    if route_confidence < _MIN_CONFIDENCE:
        block = f'confidence_below_threshold:{route_confidence:.2f}<{_MIN_CONFIDENCE}'
        log.info('[AUTO-ROUTE] BLOCKED contact=%s from=%s to=%s conf=%.2f threshold=%.2f',
                 contact_id, current_route, proposed_route, route_confidence, _MIN_CONFIDENCE)
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, block)
        return {'switched': False, 'new_route': current_route, 'block_reason': block, 'log_entry': entry}

    # ── Guard 3: rollback / cooldown ──────────────────────────────────
    if msgs_since_last < _SWITCH_COOLDOWN_MSGS:
        block = f'cooldown:{msgs_since_last}msgs_since_last_switch(min={_SWITCH_COOLDOWN_MSGS})'
        log.info('[AUTO-ROUTE] BLOCKED contact=%s cooldown=%d/%d from=%s to=%s',
                 contact_id, msgs_since_last, _SWITCH_COOLDOWN_MSGS, current_route, proposed_route)
        entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                 route_confidence, intent, state, history_len, False, block)
        return {'switched': False, 'new_route': current_route, 'block_reason': block, 'log_entry': entry}

    # ── Guard 4: Support Transition Protection — analysis flow guard ───
    # Block: analysis_route → support_route if too soon after last switch.
    # Support must not hijack an active analysis flow.
    if proposed_route == 'support_route' and current_route == 'analysis_route':
        if msgs_since_last < _SUPPORT_ANALYSIS_MIN_MSGS:
            block = (f'support_hijack_guard:analysis_flow_active:'
                     f'{msgs_since_last}msgs_since_switch(min={_SUPPORT_ANALYSIS_MIN_MSGS})')
            log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD4 analysis->support too_soon=%d/%d',
                     contact_id, msgs_since_last, _SUPPORT_ANALYSIS_MIN_MSGS)
            entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                     route_confidence, intent, state, history_len, False, block)
            return {'switched': False, 'new_route': current_route, 'block_reason': block, 'log_entry': entry}

    # ── Guard 5: Support Transition Protection — onboarding flow guard ─
    # Block: onboarding_route → support_route when analysis_upload is the
    # active intent (analysis_route would have higher confidence than support_route).
    # This prevents support from intercepting an analysis hand-off during onboarding.
    if proposed_route == 'support_route' and current_route == 'onboarding_route':
        if intent == 'analysis_upload':
            block = 'support_hijack_guard:analysis_upload_pending_in_onboarding'
            log.info('[AUTO-ROUTE] BLOCKED contact=%s GUARD5 onboarding->support analysis_upload_pending',
                     contact_id)
            entry = _build_log_entry(contact_id, current_route, proposed_route, route_reason,
                                     route_confidence, intent, state, history_len, False, block)
            return {'switched': False, 'new_route': current_route, 'block_reason': block, 'log_entry': entry}

    # ── ALL GUARDS PASSED — apply switch ──────────────────────────────
    new_agent = _ROUTE_AGENTS.get(proposed_route, proposed_route)

    log.info(
        '[AUTO-ROUTE] SWITCHED contact=%s from=%s to=%s agent=%s '
        'intent=%s state=%s confidence=%.2f reason=%s msgs_since_last=%d',
        contact_id, current_route, proposed_route, new_agent,
        intent, state, route_confidence, route_reason, msgs_since_last,
    )

    entry = _build_log_entry(
        contact_id, current_route, proposed_route, route_reason,
        route_confidence, intent, state, history_len, True,
    )

    return {
        'switched':      True,
        'new_route':     proposed_route,
        'new_agent':     new_agent,
        'previous_route': current_route,
        'block_reason':  None,
        'log_entry':     entry,
    }

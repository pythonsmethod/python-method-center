# -*- coding: utf-8 -*-
# Central AI Core v2.0 — Layer 3: Route Resolver Engine
# Module: route_resolver.py
# Purpose: Analyse intent+state+context and recommend optimal route.
#          OBSERVATION ONLY — does NOT switch session['route'] automatically.
#          Stores: proposed_route, proposed_agent, route_confidence, route_reason
# Safe to import: read-only recommendations, no side effects on routing.
# Connected in: agents.py -> process_message() after state_analyze()

import logging
from typing import Dict, Any, Optional

log = logging.getLogger('route_resolver')

# ---------------------------------------------------------------------------
# ROUTE MAP
# Maps internal route names to human-readable agent labels.
# ---------------------------------------------------------------------------
ROUTE_AGENTS: Dict[str, str] = {
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
    # aliases used by existing bot routing
    'escalation':       'Karen',
    'tariff_recommend': 'Sarah',
}

# ---------------------------------------------------------------------------
# ROUTE RULES
# Each rule is a tuple: (priority, label, condition_fn, route, reason)
# Evaluated in priority order (lower number = higher priority).
# First matching rule wins.
# ---------------------------------------------------------------------------

def _rule_escalation(intent, state, ctx, session):
    return intent == 'escalation_request'

def _rule_fear(intent, state, ctx, session):
    rs = float(ctx.get('risk_score', 0))
    # Original: explicit fear+anxious pair
    if intent == 'fear' and state == 'anxious':
        return True
    # Original: anxious state + elevated risk
    if state == 'anxious' and rs >= 0.6:
        return True
    # BUG-L3-2 FIX: high risk score overrides intent/state (e.g. "рак метастазы" → analysis_upload hijack)
    if rs >= 0.75:
        return True
    # BUG-L3-3 FIX: fear intent inside support/onboarding route (deterministic state blocks anxious)
    if intent == 'fear' and rs >= 0.4:
        return True
    return False

def _rule_paid(intent, state, ctx, session):
    return intent == 'paid' or ctx.get('payment_status') == 'paid'

def _rule_ready_to_pay(intent, state, ctx, session):
    # BUG-L3-5 FIX: state=choosing (tariff_recommend route) also implies readiness to pay
    return intent == 'ready_to_pay' or state == 'ready' or state == 'choosing'

def _rule_analysis(intent, state, ctx, session):
    return intent == 'analysis_upload'

def _rule_stuck(intent, state, ctx, session):
    ps = ctx.get('payment_status', 'new')
    hs = ctx.get('hang_stage')
    return (state == 'stuck') or (hs is not None and str(hs).strip() != '')

def _rule_waiting_paid(intent, state, ctx, session):
    return intent == 'waiting' and ctx.get('payment_status') == 'paid'

def _rule_support(intent, state, ctx, session):
    return intent == 'support' or state == 'support'

def _rule_doubt_confused(intent, state, ctx, session):
    return (intent == 'doubt' and state == 'confused') or (intent == 'doubt' and state == 'choosing')

def _rule_new_question(intent, state, ctx, session):
    return intent == 'question' and state == 'new'

def _rule_onboarding(intent, state, ctx, session):
    # BUG-L3-1 FIX: exclude waiting intent — paid user waiting needs support_route, not onboarding
    ps = ctx.get('payment_status', 'new')
    paid_context = (ps == 'paid')
    paid_signal = intent in ('onboarding', 'paid') or state in ('onboarding', 'paid')
    return paid_context and paid_signal and intent != 'waiting'


_RULES = [
    # (priority, route_name,        agent_key,        condition_fn,           reason)
    # Priority 1: escalation is always highest
    (1,  'escalation_route', 'escalation_route', _rule_escalation,   'User requested human / escalation'),
    # Priority 2: emotional crisis — trust/fear route
    (2,  'trust_route',      'trust_route',      _rule_fear,          'High fear/anxiety detected'),
    # Priority 3: analysis upload — explicit action, specific routing
    (3,  'analysis_route',   'analysis_route',   _rule_analysis,      'User uploading/discussing analysis'),
    # Priority 4: onboarding for paid users
    (4,  'onboarding_route', 'onboarding_route', _rule_onboarding,    'User is paid and in onboarding phase'),
    # Priority 5: payment intent
    (5,  'payment_route',    'payment_route',    _rule_ready_to_pay,  'User is ready to pay'),
    # Priority 6: paid user waiting — needs support
    (6,  'support_route',    'support_route',    _rule_waiting_paid,  'Paid user in waiting — needs support'),
    # Priority 7: stuck / no progress
    (7,  'recovery_route',   'recovery_route',   _rule_stuck,         'User is stuck / no progress detected'),
    # Priority 8: general support
    (8,  'support_route',    'support_route',    _rule_support,       'User needs support/help'),
    # Priority 9: doubt/confusion
    (9,  'faq_route',        'faq_route',        _rule_doubt_confused,'User has doubts/confusion'),
    # Priority 10: new user with question
    (10, 'reception',        'reception',        _rule_new_question,  'New user asking questions'),
]

# ---------------------------------------------------------------------------
# CONFIDENCE SCORING
# ---------------------------------------------------------------------------

def _calc_confidence(intent: str, state: str, ctx: Dict, rule_priority: int) -> float:
    score = 1.0

    # Lower confidence for high-priority rules that match weakly
    if rule_priority <= 2 and ctx.get('risk_score', 0) < 0.3:
        score -= 0.15

    # Boost if intent and state are strongly aligned
    strong_pairs = {
        ('escalation_request', 'escalated'),
        ('fear', 'anxious'),
        ('ready_to_pay', 'ready'),
        ('paid', 'paid'),
        ('onboarding', 'onboarding'),
        ('analysis_upload', 'onboarding'),
        ('waiting', 'waiting'),
        ('support', 'support'),
        ('doubt', 'confused'),
        ('question', 'new'),
        ('question', 'interested'),
    }
    if (intent, state) in strong_pairs:
        score = min(1.0, score + 0.15)

    # Reduce confidence for ambiguous mid-funnel states
    ambiguous_states = {'choosing', 'interested', 'stuck'}
    if state in ambiguous_states:
        score -= 0.10

    # Penalty for short history (less context = lower certainty)
    history_len = ctx.get('history_len', 0)
    if history_len < 2:
        score -= 0.10

    return round(max(0.0, min(1.0, score)), 2)


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def resolve_route(
    intent: str,
    state: str,
    context: Dict[str, Any],
    session: Dict[str, Any],
) -> Dict[str, Any]:
    intent  = (intent or 'question').strip()
    state   = (state  or 'new').strip()

    matched_route  = None
    matched_reason = 'No rule matched — keeping current route'
    matched_prio   = 99

    for prio, route_name, agent_key, condition_fn, reason in _RULES:
        try:
            if condition_fn(intent, state, context, session):
                matched_route  = route_name
                matched_reason = reason
                matched_prio   = prio
                break
        except Exception as e:
            log.warning('[ROUTE RESOLVER] rule %s error: %s', route_name, e)

    if matched_route is None:
        # Fallback: keep current route
        current_route  = session.get('route', 'reception')
        matched_route  = current_route
        matched_reason = 'No rule matched — keeping current route: ' + current_route
        matched_prio   = 99

    proposed_agent     = ROUTE_AGENTS.get(matched_route, matched_route)
    route_confidence   = _calc_confidence(intent, state, context, matched_prio)
    current_route      = session.get('route', 'reception')
    route_changed      = (matched_route != current_route)

    result = {
        'proposed_route':    matched_route,
        'proposed_agent':    proposed_agent,
        'route_confidence':  route_confidence,
        'route_reason':      matched_reason,
        'route_changed':     route_changed,
        'current_route':     current_route,
    }

    log.info(
        '[ROUTE RESOLVER] contact=%s intent=%s state=%s risk=%.2f '
        'pay=%s hang=%s hist=%d | rule#%d -> %s (%s) conf=%.2f changed=%s',
        session.get('contact_id', '?'),
        intent, state,
        float(context.get('risk_score', 0)),
        context.get('payment_status', '?'),
        context.get('hang_stage', '-'),
        int(context.get('history_len', 0)),
        matched_prio,
        matched_route,
        proposed_agent,
        route_confidence,
        route_changed,
    )

    return result

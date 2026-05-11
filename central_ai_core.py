# -*- coding: utf-8 -*-
# Central AI Core v2.0
# Module: build_context_package
# Purpose: Assembles a context snapshot per user for each incoming message.
# Safe to import: does NOT modify any existing logic.
# Connected in: agents.py -> process_message()

import logging

log = logging.getLogger('central_ai_core')

# ---------------------------------------------------------------------------
# Payment status detector (no DB access — reads session only)
# ---------------------------------------------------------------------------

_PAID_ROUTES = {'onboarding', 'analysis', 'support'}
_PENDING_ROUTES = {'formula', 'tariff_recommend', 'escalation'}


def _detect_payment_status(session: dict) -> str:
    """
    Infer payment status from session state.
    Returns: 'paid' | 'pending' | 'new'
    Does not query DB — reads only the in-memory session dict.
    """
    route = session.get('route', 'reception')
    tariff = session.get('client_data', {}).get('tariff', '')

    if route in _PAID_ROUTES:
        return 'paid'
    if route in _PENDING_ROUTES or tariff:
        return 'pending'
    return 'new'


# ---------------------------------------------------------------------------
# Hang-stage detector
# ---------------------------------------------------------------------------

_HANG_THRESHOLD = 5  # consecutive user msgs without route change = 'hang'


def _detect_hang_stage(session: dict):
    """
    Detect if user is stuck in a stage.
    Returns route name (str) if hanging, None otherwise.
    """
    history = session.get('history', [])
    route = session.get('route', 'reception')

    if len(history) < _HANG_THRESHOLD * 2:
        return None

    recent = history[-(_HANG_THRESHOLD * 2):]
    user_msgs = [m for m in recent if m.get('role') == 'user']
    if len(user_msgs) >= _HANG_THRESHOLD:
        return route
    return None


# ---------------------------------------------------------------------------
# Risk score calculator (keyword-based, v1 — no ML)
# ---------------------------------------------------------------------------

_CRISIS_KEYWORDS = [
    'суицид', 'убить себя', 'причинить себе', 'нет смысла жить',
    'хочу умереть', 'покончить', 'не хочу жить', 'жить не хочу',
    'вред себе', 'жизнь не нужна', 'умереть', 'смерть',
]
_HIGH_RISK_KEYWORDS = [
    'рак', 'онкология', 'метастаз', 'химиотерапия', 'операция',
    'последняя стадия', '4 стадия', 'терминальная',
]
_MEDIUM_RISK_KEYWORDS = [
    'боюсь', 'страшно', 'тревога', 'паника', 'плохо', 'боль',
    'не сплю', 'не ем', 'отчаяние', 'безнадёжно',
]


def _compute_risk_score(user_message: str, history: list) -> float:
    """
    Compute a risk score 0.0-1.0 based on message content.
    v1: keyword matching only.
    0.0 = no risk | 0.4-0.6 = elevated | 0.9 = crisis
    """
    if not user_message:
        return 0.0

    msg_lower = user_message.lower()

    for kw in _CRISIS_KEYWORDS:
        if kw in msg_lower:
            return 0.9

    score = 0.0
    for kw in _HIGH_RISK_KEYWORDS:
        if kw in msg_lower:
            score = max(score, 0.6)

    for kw in _MEDIUM_RISK_KEYWORDS:
        if kw in msg_lower:
            score = max(score, 0.4)

    if len(history) > 20:
        score = min(score + 0.05, 1.0)

    return round(score, 2)


# ---------------------------------------------------------------------------
# Next-step resolver
# ---------------------------------------------------------------------------

_ROUTE_NEXT_STEPS = {
    'reception':        'qualify_intent',
    'navigation':       'determine_path',
    'faq':              'answer_and_reassure',
    'prevention':       'introduce_method',
    'individual':       'gather_medical_context',
    'formula':          'present_tariff',
    'tariff_recommend': 'confirm_tariff_choice',
    'onboarding':       'complete_onboarding',
    'analysis':         'review_analysis',
    'support':          'ongoing_support',
    'escalation':       'connect_to_karen',
}


def _resolve_next_step(route: str) -> str:
    return _ROUTE_NEXT_STEPS.get(route, 'continue_dialogue')


# ---------------------------------------------------------------------------
# Main function: build_context_package
# ---------------------------------------------------------------------------

def build_context_package(contact_id: str, session: dict, user_message: str = '') -> dict:
    """
    Build a context snapshot for the current user interaction.

    Args:
        contact_id  : SendPulse contact ID (str)
        session     : Current session dict from get_session()
        user_message: The current incoming message text (optional)

    Returns:
        dict with keys: agent_current, route, payment_status, risk_score,
                        hang_stage, history_len, last_user_message,
                        client_name, tariff, next_step

    Side effects: NONE — read-only, does not modify session or DB.
    """
    route = session.get('route', 'reception')
    history = session.get('history', [])
    client_data = session.get('client_data', {})

    last_user_msg = user_message
    if not last_user_msg:
        for m in reversed(history):
            if m.get('role') == 'user':
                last_user_msg = m.get('content', '')
                break

    context = {
        'agent_current':    route,
        'route':            route,
        'payment_status':   _detect_payment_status(session),
        'risk_score':       _compute_risk_score(user_message, history),
        'hang_stage':       _detect_hang_stage(session),
        'history_len':      len(history),
        'last_user_message': last_user_msg[:200] if last_user_msg else '',
        'client_name':      client_data.get('name', ''),
        'tariff':           client_data.get('tariff', ''),
        'next_step':        _resolve_next_step(route),
    }

    log.info(
        '[CORE v2.0] contact=%s | route=%s | payment=%s | risk=%.2f | '
        'hang=%s | history_len=%d | next_step=%s',
        contact_id,
        context['route'],
        context['payment_status'],
        context['risk_score'],
        context['hang_stage'] or '-',
        context['history_len'],
        context['next_step'],
    )

    return context

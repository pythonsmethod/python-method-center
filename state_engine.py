# -*- coding: utf-8 -*-
# Central AI Core v2.0 — Layer 2: Intent + State Engine
# Module: state_engine.py
# Purpose: Detect user intent and emotional/behavioral state from each message.
# Safe to import: read-only, no side effects, no DB access.
# Connected in: agents.py -> process_message() after build_context_package()

import re
import logging
from typing import Optional

log = logging.getLogger('state_engine')


# ===========================================================================
# INTENT DEFINITIONS
# ===========================================================================
#
# intent          meaning
# --------------- ----------------------------------------------------------
# question        User is asking something (informational request)
# doubt           User expresses uncertainty about the method / center
# fear            User expresses worry, anxiety, risk-related concern
# ready_to_pay    User signals willingness / readiness to purchase
# paid            User mentions they have already paid
# onboarding      User is in post-payment setup phase
# analysis_upload User is uploading or asking about analysis/documents
# waiting         User signals they are waiting (for reply, for call, etc.)
# support         User asks for ongoing help / support check-in
# escalation_request  User explicitly wants to speak with Karen / human
# ===========================================================================

_INTENT_PATTERNS: dict[str, list[str]] = {
    'escalation_request': [
        'карен', 'karen', 'поговорить с человеком', 'живой человек',
        'хочу к специалисту', 'соедините', 'оператор', 'переведите',
        'хочу поговорить', 'позвоните мне', 'перезвоните',
    ],
    'ready_to_pay': [
        'хочу оплатить', 'готов оплатить', 'готова оплатить',
        'как оплатить', 'как платить', 'хочу купить', 'хочу записаться',
        'оформить', 'оплату', 'реквизиты', 'ссылку на оплату',
        'хочу начать', 'готов начать', 'готова начать',
        'выбрал тариф', 'выбрала тариф', 'беру', 'оплачу',
    ],
    'paid': [
        'оплатил', 'оплатила', 'уже заплатил', 'уже заплатила',
        'оплата прошла', 'деньги отправил', 'перевёл', 'перевела',
        'чек', 'квитанция', 'оплата прошла',
    ],
    'analysis_upload': [
        'анализ', 'анализы', 'результаты анализов', 'загрузить',
        'прикрепить', 'отправить документ', 'мрт', 'кт', 'узи',
        'снимок', 'выписка', 'заключение врача', 'гистология',
        'биопсия', 'онкомаркеры', 'пет', 'пэт', 'сцинтиграфия',
    ],
    'fear': [
        'боюсь', 'страшно', 'страх', 'пугает', 'опасаюсь',
        'тревога', 'тревожно', 'беспокоит', 'переживаю', 'не уверен',
        'не уверена', 'а вдруг', 'что если', 'а если не поможет',
        'это опасно', 'это безопасно', 'побочные', 'побочки',
        'не хочу рисковать', 'нет смысла', 'безнадёжно',
    ],
    'doubt': [
        'сомневаюсь', 'сомнение', 'не знаю', 'не уверен', 'не уверена',
        'это работает', 'а это поможет', 'поможет ли', 'докажите',
        'доказательства', 'нет доверия', 'не доверяю', 'скептически',
        'звучит как развод', 'это развод', 'шарлатан', 'не верю',
        'слишком дорого', 'почему так дорого', 'стоит ли',
    ],
    'waiting': [
        'жду', 'ожидаю', 'когда', 'долго', 'ещё не ответили',
        'не получил', 'не получила', 'где мой', 'почему молчит',
        'нет ответа', 'давно жду', 'забыли обо мне',
    ],
    'onboarding': [
        'что дальше', 'следующий шаг', 'как начать', 'с чего начать',
        'инструкция', 'как пользоваться', 'что нужно сделать',
        'программа', 'план', 'расписание', 'график', 'курс',
    ],
    'support': [
        'как дела', 'как я', 'моё состояние', 'хочу рассказать',
        'есть обновление', 'есть новость', 'результаты', 'улучшение',
        'ухудшение', 'побочка', 'новый симптом', 'всё хорошо',
        'всё плохо', 'нужна помощь', 'помогите', 'поддержка',
    ],
    'question': [
        'что такое', 'как работает', 'расскажите', 'объясните',
        'почему', 'зачем', 'для чего', 'можно ли', 'нельзя ли',
        'что значит', 'что такое метод', 'как это', 'сколько стоит',
        'сколько длится', 'сколько времени', 'где', 'когда',
    ],
}

# Priority order — first match wins
_INTENT_PRIORITY = [
    'escalation_request',
    'paid',
    'ready_to_pay',
    'analysis_upload',
    'fear',
    'doubt',
    'waiting',
    'onboarding',
    'support',
    'question',
]


def detect_intent(user_message: str, session: dict, context: dict) -> str:
    """
    Detect the primary intent of the current user message.

    Args:
        user_message : raw text from user
        session      : current session dict
        context      : context package from build_context_package()

    Returns:
        str — one of the defined intent labels

    Side effects: NONE — read-only.
    """
    if not user_message:
        return 'question'

    msg = user_message.lower().strip()
    route = context.get('route', 'reception')

    # Route-based fast-path: if already in a route, some intents are obvious
    if route == 'onboarding':
        # Messages in onboarding are almost always onboarding-related
        for kw in _INTENT_PATTERNS['analysis_upload']:
            if kw in msg:
                return 'analysis_upload'

    if route in ('analysis', 'support'):
        for kw in _INTENT_PATTERNS['analysis_upload']:
            if kw in msg:
                return 'analysis_upload'
        for kw in _INTENT_PATTERNS['support']:
            if kw in msg:
                return 'support'

    # General keyword scan in priority order
    for intent in _INTENT_PRIORITY:
        for kw in _INTENT_PATTERNS[intent]:
            if kw in msg:
                return intent

    # Question marks → question intent
    if '?' in msg:
        return 'question'

    # Default: question (safest neutral label)
    return 'question'


# ===========================================================================
# STATE DEFINITIONS
# ===========================================================================
#
# state       meaning
# ----------- --------------------------------------------------------------
# new         First contact, no context yet
# interested  User is engaged, asking about the method
# confused    User seems lost or doesn't understand something
# anxious     User shows emotional distress, fear, worry
# choosing    User is in tariff/decision phase
# ready       User has expressed payment readiness
# paid        User has paid
# onboarding  User is in post-payment setup
# waiting     User is passively waiting
# stuck       User is repeating messages without progress (hang detected)
# support     User is in active support phase
# escalated   User has been escalated to Karen
# ===========================================================================

def _state_from_route(route: str) -> Optional[str]:
    """Map route directly to state when unambiguous."""
    _ROUTE_STATE_MAP = {
        'onboarding': 'onboarding',
        'analysis':   'onboarding',
        'support':    'support',
        'escalation': 'escalated',
    }
    return _ROUTE_STATE_MAP.get(route)


def detect_user_state(
    user_message: str,
    session: dict,
    context: dict,
    intent: Optional[str] = None,
) -> str:
    """
    Detect the current behavioral/emotional state of the user.

    Args:
        user_message : raw text from user
        session      : current session dict
        context      : context package from build_context_package()
        intent       : pre-computed intent (optional, avoids double-scanning)

    Returns:
        str — one of the defined state labels

    Side effects: NONE — read-only.
    """
    route = context.get('route', 'reception')
    payment_status = context.get('payment_status', 'new')
    hang_stage = context.get('hang_stage')
    history_len = context.get('history_len', 0)
    risk_score = context.get('risk_score', 0.0)

    # 1. Route-based deterministic states (highest confidence)
    route_state = _state_from_route(route)
    if route_state:
        return route_state

    # 2. Payment-confirmed state
    if payment_status == 'paid':
        return 'paid'

    # 3. Stuck / hang
    if hang_stage:
        return 'stuck'

    # 4. Intent-based states (if intent already computed, use it)
    if intent:
        if intent == 'escalation_request':
            return 'escalated'
        if intent == 'paid':
            return 'paid'
        if intent == 'ready_to_pay':
            return 'ready'
        if intent == 'fear':
            return 'anxious'
        if intent == 'doubt':
            return 'confused'
        if intent == 'waiting':
            return 'waiting'
        if intent in ('onboarding', 'analysis_upload'):
            return 'onboarding'
        if intent == 'support':
            return 'support'

    # 5. Risk score → anxious
    if risk_score >= 0.5:
        return 'anxious'

    # 6. Route-based soft states
    if route in ('formula', 'tariff_recommend'):
        return 'choosing'
    if route in ('faq', 'prevention'):
        return 'interested'
    if route == 'navigation':
        return 'confused'

    # 7. History length heuristic
    if history_len == 0:
        return 'new'
    if history_len <= 3:
        return 'new'
    if history_len <= 10:
        return 'interested'

    # Default
    return 'interested'


# ===========================================================================
# COMBINED ANALYSIS (convenience wrapper)
# ===========================================================================

def analyze(contact_id: str, user_message: str, session: dict, context: dict) -> dict:
    """
    Run both detectors and return a combined result dict.
    This is the main entry point called from process_message().

    Args:
        contact_id   : user ID (for logging)
        user_message : raw message text
        session      : current session dict
        context      : context package from central_ai_core

    Returns:
        dict: { 'intent': str, 'state': str }

    Side effects: logs only.
    """
    intent = detect_intent(user_message, session, context)
    state  = detect_user_state(user_message, session, context, intent=intent)

    log.info(
        '[STATE ENGINE v2.0] contact=%s | route=%s | intent=%s | state=%s | risk=%.2f | history=%d',
        contact_id,
        context.get('route', '-'),
        intent,
        state,
        context.get('risk_score', 0.0),
        context.get('history_len', 0),
    )

    return {'intent': intent, 'state': state}

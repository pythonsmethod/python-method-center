# -*- coding: utf-8 -*-
# Central AI Core v2.0 — Layer 5: Emotional Overlay Engine
# Module: emotional_overlay.py
# Purpose: Inject emotional intelligence ABOVE existing route agents,
#          WITHOUT changing route, active agent, or orchestration continuity.
#
# Overlay types (ordered by priority):
#   emotional_high_risk      - critical fear/death/oncology panic (rs >= 0.75)
#   emotional_fear           - explicit fear intent (rs >= 0.40)
#   emotional_grief          - loss, hopelessness, despair signals
#   emotional_support        - explicit support request or loneliness
#   emotional_confusion      - confusion/overwhelm blocking decisions
#   emotional_payment_anxiety - financial fear during payment flow
#   none                     - no overlay needed
#
# What overlay DOES NOT change:
#   - session['route']
#   - active agent (Lucky/Maya/Iris/Vera/Karen/Nadia/Gabriel/Sarah/Sophia)
#   - route_resolver proposals
#   - auto_router decisions
#
# What overlay CHANGES in agent prompt injection:
#   - response tone (warm/deep/grounded/neutral)
#   - empathy level (explicit/implicit/none)
#   - reassurance style (direct/indirect/validating)
#   - pacing (slow/normal/fast)
#   - warmth (high/medium/low)
#   - validation patterns (active/passive/none)
#
# Protections:
#   - overlay_cooldown: min 2 msgs between HIGH overlays (prevents empathy spam)
#   - anti-overempathy: max 3 consecutive empathy-heavy responses
#   - no_fake_empathy: blocks overlay if no genuine emotional signal detected
#   - no_repetitive_reassurance: tracks last overlay type to prevent loops
#
# Connected in: agents.py -> process_message() BEFORE agent prompt generation

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

log = logging.getLogger('emotional_overlay')

# ---------------------------------------------------------------------------
# OVERLAY TYPES
# ---------------------------------------------------------------------------
OVERLAY_NONE             = 'none'
OVERLAY_HIGH_RISK        = 'emotional_high_risk'
OVERLAY_FEAR             = 'emotional_fear'
OVERLAY_GRIEF            = 'emotional_grief'
OVERLAY_SUPPORT          = 'emotional_support'
OVERLAY_CONFUSION        = 'emotional_confusion'
OVERLAY_PAYMENT_ANXIETY  = 'emotional_payment_anxiety'

# ---------------------------------------------------------------------------
# OVERLAY PRIORITY MAP (lower number = higher priority)
# ---------------------------------------------------------------------------
_OVERLAY_PRIORITY: Dict[str, int] = {
    OVERLAY_HIGH_RISK:       1,
    OVERLAY_FEAR:            2,
    OVERLAY_GRIEF:           3,
    OVERLAY_SUPPORT:         4,
    OVERLAY_CONFUSION:       5,
    OVERLAY_PAYMENT_ANXIETY: 6,
    OVERLAY_NONE:            99,
}

# ---------------------------------------------------------------------------
# THRESHOLDS
# ---------------------------------------------------------------------------
_RS_HIGH_RISK     = 0.75
_RS_FEAR          = 0.40
_RS_GRIEF         = 0.55
_OVERLAY_COOLDOWN = 2
_MAX_CONSECUTIVE  = 3
_MIN_CONFIDENCE   = 0.65

# ---------------------------------------------------------------------------
# OVERLAY TONE PROFILES
# Per overlay type: defines what gets injected into agent prompt
# ---------------------------------------------------------------------------
_TONE_PROFILES: Dict[str, Dict[str, Any]] = {
    OVERLAY_HIGH_RISK: {
        'tone':            'deep_grounded',
        'empathy_level':   'explicit',
        'reassurance':     'validating',
        'pacing':          'slow',
        'warmth':          'high',
        'validation':      'active',
        'prompt_prefix':   (
            '[EMOTIONAL OVERLAY: high_risk] '
            'The client is experiencing acute fear or panic (oncology/death/crisis). '
            'BEFORE answering substantively: '
            '1) Acknowledge the client feeling in one short sentence. '
            '2) Do not rush to solutions. '
            '3) Use slow pace, warm tone. '
            '4) Do NOT minimize the fear. '
            '5) Do NOT say everything will be fine without basis. '
            'THEN continue in your agent role as usual.'
        ),
        'forbidden_phrases': [
            'ne volnujtes', 'vsyo budet horosho', 'ne perezhivajte',
            'uspokojtes', 'ne stoit boyatsya',
        ],
    },
    OVERLAY_FEAR: {
        'tone':            'warm_present',
        'empathy_level':   'explicit',
        'reassurance':     'direct',
        'pacing':          'slow',
        'warmth':          'high',
        'validation':      'active',
        'prompt_prefix':   (
            '[EMOTIONAL OVERLAY: fear] '
            'The client is expressing fear or anxiety. '
            'First say one phrase that acknowledges the feeling (does not dismiss it). '
            'Then continue as usual in your agent role.'
        ),
        'forbidden_phrases': [
            'ne volnujtes', 'uspokojtes', 'net prichin boyatsya',
        ],
    },
    OVERLAY_GRIEF: {
        'tone':            'quiet_presence',
        'empathy_level':   'implicit',
        'reassurance':     'indirect',
        'pacing':          'very_slow',
        'warmth':          'high',
        'validation':      'passive',
        'prompt_prefix':   (
            '[EMOTIONAL OVERLAY: grief] '
            'The client is experiencing grief, loss of hope, or despair. '
            'Do NOT rush to give solutions. '
            'First simply be present: one sentence of presence without advice. '
            'Then gently continue your role.'
        ),
        'forbidden_phrases': [
            'derzhites', 'nado borotsya', 'ne sdavajtes',
            'vsyo projdet', 'vremya lechit',
        ],
    },
    OVERLAY_SUPPORT: {
        'tone':            'warm_listening',
        'empathy_level':   'explicit',
        'reassurance':     'validating',
        'pacing':          'normal',
        'warmth':          'high',
        'validation':      'active',
        'prompt_prefix':   (
            '[EMOTIONAL OVERLAY: support] '
            'The client is seeking support and understanding. '
            'Show that you hear them (one phrase). '
            'Then continue your agent role without losing warmth.'
        ),
        'forbidden_phrases': [
            'u menya net vremeni', 'eto ne po teme', 'davajte k delu',
        ],
    },
    OVERLAY_CONFUSION: {
        'tone':            'clear_patient',
        'empathy_level':   'implicit',
        'reassurance':     'structural',
        'pacing':          'normal',
        'warmth':          'medium',
        'validation':      'passive',
        'prompt_prefix':   (
            '[EMOTIONAL OVERLAY: confusion] '
            'The client is in cognitive overload or confusion. '
            'Use simple short sentences. '
            'Do not give too much information at once. '
            'One step at a time. Patiently.'
        ),
        'forbidden_phrases': [
            'kak ya uzhe govoril', 'eto ochevidno', 'vsyo prosto',
        ],
    },
    OVERLAY_PAYMENT_ANXIETY: {
        'tone':            'confident_reassuring',
        'empathy_level':   'implicit',
        'reassurance':     'factual',
        'pacing':          'normal',
        'warmth':          'medium',
        'validation':      'active',
        'prompt_prefix':   (
            '[EMOTIONAL OVERLAY: payment_anxiety] '
            'The client is experiencing anxiety about a financial decision. '
            'Do not rush toward payment. '
            'First acknowledge that this is a serious decision. '
            'Give a concrete fact or guarantee. '
            'Then continue payment agent logic.'
        ),
        'forbidden_phrases': [
            'ne dumajte', 'prosto oplatite', 'eto nedorogo',
            'chego vy bojtes',
        ],
    },
    OVERLAY_NONE: {
        'tone':            'neutral',
        'empathy_level':   'none',
        'reassurance':     'none',
        'pacing':          'normal',
        'warmth':          'low',
        'validation':      'none',
        'prompt_prefix':   '',
        'forbidden_phrases': [],
    },
}

# ---------------------------------------------------------------------------
# DETECTION SIGNALS
# ---------------------------------------------------------------------------
_GRIEF_SIGNALS = frozenset([
    'умру', 'умираю', 'конец', 'безнадёжно', 'бессмысленно',
    'сдаюсь', 'нет смысла', 'не выдержу', 'не справлюсь',
    'зачем', 'поздно', 'обречена', 'обречён',
])
_SUPPORT_SIGNALS = frozenset([
    'одна', 'один', 'никто не понимает', 'не с кем', 'поговорите',
    'тяжело', 'плохо', 'помогите', 'поддержите', 'выслушайте',
    'некому', 'никому', 'бросили',
])
_PAYMENT_ANXIETY_SIGNALS = frozenset([
    'деньги', 'дорого', 'пропадут', 'потрачу зря',
    'не могу позволить', 'боюсь платить', 'жалею', 'зря потрачу',
    'обман', 'развод', 'верните',
])
_CONFUSION_SIGNALS = frozenset([
    'не понимаю', 'запутался', 'запуталась', 'не знаю', 'объясни',
    'не разобралась', 'слишком много', 'голова кругом', 'непонятно',
    'забыла', 'забыл', 'потерялась', 'потерялся',
])


def _detect_signals(message_lower: str, signal_set: frozenset) -> bool:
    return any(sig in message_lower for sig in signal_set)


# ---------------------------------------------------------------------------
# MAIN DETECTION FUNCTION
# ---------------------------------------------------------------------------
def detect_emotional_overlay(
    intent:            str,
    state:             str,
    risk_score:        float,
    current_route:     str,
    session:           Dict[str, Any],
    last_user_message: str = '',
) -> Dict[str, Any]:
    intent  = (intent  or '').strip()
    state   = (state   or '').strip()
    msg_low = last_user_message.lower()
    rs      = float(risk_score or 0.0)

    overlay_history:       List[Dict] = session.get('overlay_history', [])
    last_high_overlay_msg: int        = session.get('overlay_last_high_msg', 0)
    consecutive_empathy:   int        = session.get('overlay_consecutive_empathy', 0)
    history_len:           int        = len(session.get('history', []))
    msgs_since_last_high:  int        = history_len - last_high_overlay_msg

    candidate  = OVERLAY_NONE
    confidence = 0.0

    # P1: high risk
    if rs >= _RS_HIGH_RISK or (intent == 'fear' and rs >= 0.65):
        candidate  = OVERLAY_HIGH_RISK
        confidence = min(1.0, rs + 0.10)

    # P2: fear
    elif intent == 'fear' and rs >= _RS_FEAR:
        candidate  = OVERLAY_FEAR
        confidence = min(1.0, rs + 0.15)

    # P3: grief (keyword-based)
    elif _detect_signals(msg_low, _GRIEF_SIGNALS) and rs >= _RS_GRIEF:
        candidate  = OVERLAY_GRIEF
        confidence = min(1.0, rs + 0.05)

    # P4: support
    elif intent == 'support' or _detect_signals(msg_low, _SUPPORT_SIGNALS):
        candidate  = OVERLAY_SUPPORT
        confidence = 0.80

    # P5: confusion
    elif state == 'confused' or _detect_signals(msg_low, _CONFUSION_SIGNALS):
        candidate  = OVERLAY_CONFUSION
        confidence = 0.75

    # P6: payment anxiety
    elif (
        current_route in ('payment_route', 'reception')
        and _detect_signals(msg_low, _PAYMENT_ANXIETY_SIGNALS)
        and intent not in ('paid', 'ready_to_pay')
    ):
        candidate  = OVERLAY_PAYMENT_ANXIETY
        confidence = 0.78

    block_reason: Optional[str] = None

    # Protection A: confidence gate
    if candidate != OVERLAY_NONE and confidence < _MIN_CONFIDENCE:
        block_reason = f'overlay_confidence_gate:{confidence:.2f}<{_MIN_CONFIDENCE}'
        candidate    = OVERLAY_NONE

    # Protection B: cooldown for high-priority overlays
    if candidate in (OVERLAY_HIGH_RISK, OVERLAY_FEAR, OVERLAY_GRIEF):
        if msgs_since_last_high < _OVERLAY_COOLDOWN:
            block_reason = (
                f'overlay_cooldown:{msgs_since_last_high}msgs'
                f'_since_last_high(min={_OVERLAY_COOLDOWN})'
            )
            if _detect_signals(msg_low, _SUPPORT_SIGNALS):
                candidate    = OVERLAY_SUPPORT
                block_reason = None
            else:
                candidate = OVERLAY_NONE

    # Protection C: anti-overempathy
    if candidate in (OVERLAY_HIGH_RISK, OVERLAY_FEAR, OVERLAY_GRIEF, OVERLAY_SUPPORT):
        if consecutive_empathy >= _MAX_CONSECUTIVE:
            block_reason = (
                f'anti_overempathy:{consecutive_empathy}_consecutive'
                f'(max={_MAX_CONSECUTIVE})'
            )
            candidate = OVERLAY_NONE

    # Protection D: no-fake-empathy
    if candidate in (OVERLAY_HIGH_RISK, OVERLAY_FEAR) and rs < _RS_FEAR and intent != 'fear':
        block_reason = 'no_fake_empathy:no_genuine_fear_signal'
        candidate    = OVERLAY_NONE

    # Protection E: no repetitive reassurance
    if overlay_history:
        last_ov = overlay_history[-1].get('overlay_type', OVERLAY_NONE)
        if (
            candidate == last_ov
            and candidate in (OVERLAY_FEAR, OVERLAY_SUPPORT, OVERLAY_CONFUSION)
            and msgs_since_last_high < 2
        ):
            block_reason = f'no_repetitive_reassurance:same_{candidate}_repeated'
            candidate    = OVERLAY_NONE

    final_priority = _OVERLAY_PRIORITY.get(candidate, 99)
    final_tone     = _TONE_PROFILES[candidate]
    should_inject  = (candidate != OVERLAY_NONE)

    log_entry = {
        'ts':                  datetime.utcnow().isoformat(),
        'overlay_type':        candidate,
        'priority':            final_priority,
        'confidence':          round(confidence, 3),
        'intent':              intent,
        'state':               state,
        'risk_score':          round(rs, 3),
        'current_route':       current_route,
        'should_inject':       should_inject,
        'block_reason':        block_reason,
        'msgs_since_high':     msgs_since_last_high,
        'consecutive_empathy': consecutive_empathy,
    }

    log.info(
        '[OVERLAY] route=%s overlay=%s conf=%.2f rs=%.2f inject=%s%s',
        current_route, candidate, confidence, rs, should_inject,
        f' block={block_reason}' if block_reason else '',
    )

    return {
        'overlay_type':       candidate,
        'overlay_priority':   final_priority,
        'overlay_confidence': round(confidence, 3),
        'overlay_tone':       final_tone,
        'overlay_log':        log_entry,
        'should_inject':      should_inject,
        'block_reason':       block_reason,
        'prompt_prefix':      final_tone.get('prompt_prefix', ''),
        'forbidden_phrases':  final_tone.get('forbidden_phrases', []),
    }


# ---------------------------------------------------------------------------
# SESSION UPDATE HELPER
# ---------------------------------------------------------------------------
def update_overlay_session(
    session:         Dict[str, Any],
    overlay_package: Dict[str, Any],
) -> None:
    overlay_type  = overlay_package['overlay_type']
    should_inject = overlay_package['should_inject']
    history_len   = len(session.get('history', []))

    session.setdefault('overlay_history',             [])
    session.setdefault('overlay_last_high_msg',       0)
    session.setdefault('overlay_consecutive_empathy', 0)

    session['overlay_history'].append(overlay_package['overlay_log'])
    if len(session['overlay_history']) > 20:
        session['overlay_history'] = session['overlay_history'][-20:]

    if should_inject and overlay_package['overlay_priority'] <= 3:
        session['overlay_last_high_msg'] = history_len

    _HIGH_EMPATHY = {OVERLAY_HIGH_RISK, OVERLAY_FEAR, OVERLAY_GRIEF, OVERLAY_SUPPORT}
    if should_inject and overlay_type in _HIGH_EMPATHY:
        session['overlay_consecutive_empathy'] += 1
    else:
        session['overlay_consecutive_empathy'] = 0


# ---------------------------------------------------------------------------
# PROMPT INJECTION BUILDER
# ---------------------------------------------------------------------------
def build_overlay_injection(
    overlay_package: Dict[str, Any],
    agent_name:      str,
    current_route:   str,
) -> str:
    if not overlay_package.get('should_inject'):
        return ''
    prefix   = overlay_package.get('prompt_prefix', '')
    tone     = overlay_package.get('overlay_tone', {})
    warnings = overlay_package.get('forbidden_phrases', [])
    injection  = prefix
    if warnings:
        injection += f' FORBIDDEN: {", ".join(warnings[:4])}.'
    injection += (
        f' [Agent: {agent_name} | Route: {current_route} | '
        f'Tone: {tone.get("tone","neutral")} | '
        f'Pacing: {tone.get("pacing","normal")} | '
        f'Warmth: {tone.get("warmth","low")}]'
    )
    return injection


# ---------------------------------------------------------------------------
# MIGRATION SQL (run once on Railway PostgreSQL)
# ---------------------------------------------------------------------------
# ALTER TABLE pm_sessions
#     ADD COLUMN IF NOT EXISTS overlay_last_high_msg       INTEGER  DEFAULT 0,
#     ADD COLUMN IF NOT EXISTS overlay_consecutive_empathy INTEGER  DEFAULT 0,
#     ADD COLUMN IF NOT EXISTS overlay_history             JSONB    DEFAULT '[]';
#
# agents.py integration (3 lines):
#   from emotional_overlay import (detect_emotional_overlay,
#                                  update_overlay_session,
#                                  build_overlay_injection)
#   # BEFORE agent prompt generation:
#   overlay = detect_emotional_overlay(intent, state, rs, route, session, user_msg)
#   prefix  = build_overlay_injection(overlay, agent_name, route)
#   # Prepend prefix to agent system prompt string
#   # AFTER generating response:
#   update_overlay_session(session, overlay)

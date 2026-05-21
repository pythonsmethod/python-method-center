# -*- coding: utf-8 -*-
# Testimonials / Life Outcomes Archive
# Module: testimonials_module.py
# Purpose: Detect, categorize, anonymize and archive patient testimonials,
#          positive life outcomes and recovery milestones for Anna's review.
# Design:  Additive-only — no side effects on routing, risk, or dispatcher.
#          Called from agents.py process_message() after checkin detection.
# Phase 5 / Step 7 — Testimonials Archive Module
import logging
import re
import json
import os
from datetime import timezone, datetime
from typing import Dict, Any, List, Optional

log = logging.getLogger('testimonials_module')

# ---------------------------------------------------------------------------
# CATEGORY KEYWORDS
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    'family_reconnection': [
        'дочь', 'сын', 'внук', 'внучка', 'семья', 'родители', 'муж', 'жена',
        'дети', 'родственники', 'близкие', 'мама', 'папа', 'бабушка', 'дедушка',
        'поехал к', 'поехала к', 'навестил', 'навестила', 'увиделся', 'увиделась',
        'провёл время', 'провела время', 'встретился', 'встретилась',
        'в другую страну', 'в другой город', 'смог поехать', 'смогла поехать',
    ],
    'method_result': [
        'благодаря методу', 'благодаря программе', 'благодаря вам',
        'ваш метод', 'ваша программа', 'эта программа', 'этот метод',
        'если бы не метод', 'если бы не программа', 'если бы не вы',
        'без вас не смог', 'без вас не смогла', 'метод помог',
        'программа помогла', 'помогли мне', 'изменили жизнь',
        'вернули жизнь', 'спасибо за метод', 'благодарю за программу',
    ],
    'physical_improvement': [
        'хожу', 'хожу лучше', 'встаю', 'встаю сам', 'без трости', 'без помощи',
        'боль прошла', 'боль уменьшилась', 'меньше боли', 'без боли',
        'двигаюсь лучше', 'могу ходить', 'могу стоять', 'стал активнее',
        'стала активнее', 'физически лучше', 'тело работает', 'сила вернулась',
        'мышцы', 'равновесие', 'координация', 'упражнения помогли',
    ],
    'emotional_improvement': [
        'настроение улучшилось', 'чувствую себя счастливым', 'чувствую себя счастливой',
        'радость вернулась', 'снова радуюсь', 'снова улыбаюсь', 'меньше тревоги',
        'тревога прошла', 'депрессия прошла', 'стало легче', 'душа спокойна',
        'эмоционально лучше', 'внутренне лучше', 'позитивно смотрю',
        'вижу смысл', 'хочется жить', 'хочу жить',
    ],
    'gratitude': [
        'спасибо', 'благодарю', 'благодарен', 'благодарна', 'признателен',
        'признательна', 'огромная благодарность', 'большое спасибо',
        'от всей души', 'слова не передают', 'так благодарен', 'так благодарна',
        'вы изменили', 'вы помогли', 'не забуду', 'помню вашу помощь',
    ],
    'life_event': [
        'поехал', 'поехала', 'путешествие', 'поездка', 'отпуск', 'праздник',
        'день рождения', 'свадьба', 'юбилей', 'встреча', 'концерт', 'театр',
        'прогулка', 'парк', 'ресторан', 'кино', 'событие', 'вышел на работу',
        'вышла на работу', 'вернулся к работе', 'вернулась к работе',
        'снова вожу машину', 'снова хожу', 'смог поучаствовать',
    ],
    'recovery_milestone': [
        'первый раз за', 'впервые за', 'давно не мог', 'давно не могла',
        'раньше не мог', 'раньше не могла', 'раньше не получалось',
        'теперь могу', 'теперь получается', 'достижение', 'победа',
        'преодолел', 'преодолела', 'рекорд', 'шаг вперёд', 'прорыв',
        'прошёл весь курс', 'прошла весь курс', 'завершил', 'завершила',
    ],
}

# ---------------------------------------------------------------------------
# POSITIVE OUTCOME SIGNALS (triggers testimonial capture)
# ---------------------------------------------------------------------------

_TESTIMONIAL_TRIGGERS = [
    'благодаря', 'спасибо', 'смог', 'смогла', 'помогли', 'помог',
    'счастлив', 'счастлива', 'радость', 'результат', 'улучшение',
    'впервые за', 'первый раз', 'если бы не', 'без вас', 'метод помог',
    'программа помогла', 'изменилась жизнь', 'изменился', 'изменилась',
    'могу снова', 'снова могу', 'вернулась способность', 'вернулся',
    'поехал', 'поехала', 'навестил', 'навестила', 'провёл', 'провела',
]

# ---------------------------------------------------------------------------
# ANONYMIZATION — replace personal patterns
# ---------------------------------------------------------------------------

_ANON_PATTERNS = [
    # Russian names (common patterns)
    (r'\b(меня зовут|зовут меня|я — |я–|я - )\s*[А-ЯЁ][а-яё]+', r'\1[ИМЯ]'),
    # Phone numbers
    (r'[+]?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '[ТЕЛЕФОН]'),
    # Emails
    (r'[\w.+-]+@[\w-]+\.[a-z]{2,}', '[EMAIL]'),
    # Cities + countries (common in travel context)
    # Keep general — remove specific daughter/child names
    (r'\b(дочь|сын|внук|внучка)\s+([А-ЯЁ][а-яё]+)', r'\1 [ИМЯ_РЕБЁНКА]'),
    # Ages
    (r'\b(мне|мне сейчас)\s+(\d{2})\s+(лет|год|года)', r'\1 [ВОЗРАСТ] лет'),
]

def _anonymize(text: str) -> str:
    result = text
    for pattern, replacement in _ANON_PATTERNS:
        try:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE | re.UNICODE)
        except Exception:
            pass
    return result

# ---------------------------------------------------------------------------
# CATEGORY DETECTION
# ---------------------------------------------------------------------------

def _detect_category(text: str) -> str:
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[cat] = count
    if not scores:
        return 'life_event'
    return max(scores, key=lambda k: scores[k])

# ---------------------------------------------------------------------------
# EMOTIONAL TONE DETECTION
# ---------------------------------------------------------------------------

_TONE_POSITIVE = [
    'счастлив', 'счастлива', 'радость', 'радуюсь', 'улыбаюсь',
    'прекрасно', 'замечательно', 'отлично', 'хорошо', 'благодарен',
    'благодарна', 'тронут', 'тронута', 'восторг', 'восхищён',
]
_TONE_GRATEFUL = ['спасибо', 'благодарю', 'признателен', 'признательна']
_TONE_HOPEFUL = ['надежда', 'верю', 'буду продолжать', 'впереди', 'возможности']

def _detect_emotional_tone(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in _TONE_GRATEFUL):
        if any(kw in text_lower for kw in _TONE_POSITIVE):
            return 'grateful_joyful'
        return 'grateful'
    if any(kw in text_lower for kw in _TONE_POSITIVE):
        return 'joyful'
    if any(kw in text_lower for kw in _TONE_HOPEFUL):
        return 'hopeful'
    return 'positive'

# ---------------------------------------------------------------------------
# SUMMARY GENERATION
# ---------------------------------------------------------------------------

def _generate_summary(text: str, category: str, emotional_tone: str) -> str:
    max_len = 200
    short = text.strip()
    if len(short) > max_len:
        short = short[:max_len].rsplit(' ', 1)[0] + '...'
    return f'[{category.upper()}] [{emotional_tone}] {short}'

# ---------------------------------------------------------------------------
# TESTIMONIAL-WORTHY DETECTION
# ---------------------------------------------------------------------------

def detect_testimonial_worthy(
    user_message: str,
    checkin_intent: Optional[str],
    positive_life_outcome: bool = False,
) -> bool:
    if positive_life_outcome:
        return True
    if checkin_intent in (
        'patient_reports_progress',
        'patient_reports_life_event',
        'patient_reports_emotional_shift',
    ):
        return True
    msg_lower = user_message.lower()
    trigger_count = sum(1 for t in _TESTIMONIAL_TRIGGERS if t in msg_lower)
    return trigger_count >= 2

# ---------------------------------------------------------------------------
# CONSENT PROMPT TEMPLATE
# ---------------------------------------------------------------------------

CONSENT_PROMPT = """
[РЕЖИМ СОХРАНЕНИЯ ОТЗЫВА — testimonial_consent_mode]
Пациент поделился важным жизненным результатом или положительным изменением.
Твоя задача: после эмоциональной поддержки — мягко, в конце ответа, спросить разрешение.
Используй такой текст (адаптируй под контекст):

'Спасибо, что поделились этим. Это очень ценный и важный результат. 
Можно ли Анна сохранит этот момент как часть внутренней истории центра? 
А если когда-нибудь захотим поделиться им в соцсетях — обязательно спросим вас отдельно.'

Правила:
- Согласие только добровольное — никакого давления
- Не задавай больше одного вопроса за раз
- Если пациент отказывается — принять спокойно и не возвращаться к теме
- Если соглашается — поблагодарить тепло
"""

# ---------------------------------------------------------------------------
# SAVE TESTIMONIAL TO DB
# ---------------------------------------------------------------------------

def save_testimonial(
    contact_id: str,
    user_message: str,
    session: Dict[str, Any],
    checkin_intent: Optional[str],
    db_conn_fn,
) -> Optional[Dict[str, Any]]:
    try:
        category      = _detect_category(user_message)
        emotional_tone = _detect_emotional_tone(user_message)
        cleaned_summary = _generate_summary(user_message, category, emotional_tone)
        anonymized    = _anonymize(user_message)
        life_event    = session.get('life_event_note') or {}
        result_type   = checkin_intent or 'patient_reports_life_event'
        is_positive   = session.get('positive_life_outcome', False)

        conn = db_conn_fn()
        cur  = conn.cursor()

        # Create table if not exists
        cur.execute(
            'CREATE TABLE IF NOT EXISTS patient_testimonials ('
            '    id SERIAL PRIMARY KEY,'
            '    contact_id TEXT NOT NULL,'
            '    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
            '    source_message TEXT NOT NULL,'
            '    cleaned_summary TEXT NOT NULL DEFAULT $$$$,'
            '    category TEXT NOT NULL DEFAULT $$life_event$$,'
            '    emotional_tone TEXT NOT NULL DEFAULT $$positive$$,'
            '    life_event JSONB,'
            '    result_type TEXT NOT NULL DEFAULT $$patient_reports_life_event$$,'
            '    is_social_ready BOOLEAN NOT NULL DEFAULT FALSE,'
            '    consent_status TEXT NOT NULL DEFAULT $$unknown$$,'
            '    anonymized_version TEXT,'
            '    needs_anna_review BOOLEAN NOT NULL DEFAULT TRUE'
            ')'
        )

        cur.execute(
            'INSERT INTO patient_testimonials '
            '(contact_id, source_message, cleaned_summary, category, '
            ' emotional_tone, life_event, result_type, '
            ' is_social_ready, consent_status, anonymized_version, needs_anna_review) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (
                contact_id,
                user_message,
                cleaned_summary,
                category,
                emotional_tone,
                json.dumps(life_event, ensure_ascii=False) if life_event else None,
                result_type,
                False,        # is_social_ready — never auto-publish
                'unknown',    # consent_status
                anonymized,
                True,         # needs_anna_review
            )
        )
        conn.commit()
        cur.close()
        conn.close()

        log.warning(
            '[TESTIMONIAL CAPTURED] contact=%s | category=%s | tone=%s | '
            'result_type=%s | is_social_ready=False | consent_status=unknown | needs_anna_review=True',
            contact_id, category, emotional_tone, result_type
        )
        log.warning(
            '[TESTIMONIAL REVIEW NEEDED] contact=%s | category=%s',
            contact_id, category
        )
        log.warning(
            '[TESTIMONIAL CONSENT UNKNOWN] contact=%s — consent not yet collected',
            contact_id
        )

        return {
            'saved':             True,
            'category':          category,
            'emotional_tone':    emotional_tone,
            'cleaned_summary':   cleaned_summary,
            'is_social_ready':   False,
            'consent_status':    'unknown',
            'needs_anna_review': True,
        }

    except Exception as e:
        log.error('[TESTIMONIAL ERROR] contact=%s | error=%s', contact_id, str(e))
        return None

# ---------------------------------------------------------------------------
# ANNA FILTER QUERIES
# ---------------------------------------------------------------------------

ANNA_FILTER_QUERIES = {
    'all': (
        'SELECT id, contact_id, created_at, cleaned_summary, category, '
        'emotional_tone, result_type, is_social_ready, consent_status, needs_anna_review '
        'FROM patient_testimonials ORDER BY created_at DESC LIMIT 50'
    ),
    'new': (
        'SELECT id, contact_id, created_at, cleaned_summary, category, '
        'emotional_tone, result_type, is_social_ready, consent_status, needs_anna_review '
        'FROM patient_testimonials WHERE needs_anna_review = TRUE ORDER BY created_at DESC LIMIT 20'
    ),
    'social_ready': (
        'SELECT id, contact_id, created_at, cleaned_summary, category, '
        'emotional_tone, anonymized_version, consent_status '
        'FROM patient_testimonials WHERE is_social_ready = TRUE '
        'AND consent_status = $consent_given$ ORDER BY created_at DESC LIMIT 20'
    ),
    'needs_consent': (
        'SELECT id, contact_id, created_at, cleaned_summary, category, '
        'emotional_tone, consent_status '
        'FROM patient_testimonials WHERE consent_status = $unknown$ ORDER BY created_at DESC LIMIT 20'
    ),
    'positive_outcomes': (
        'SELECT id, contact_id, created_at, cleaned_summary, category, '
        'emotional_tone, result_type, anonymized_version '
        'FROM patient_testimonials '
        'WHERE result_type IN ($patient_reports_life_event$, $patient_reports_progress$) '
        'ORDER BY created_at DESC LIMIT 20'
    ),
}

def get_anna_testimonials(filter_key: str, db_conn_fn) -> List[Dict[str, Any]]:
    query = ANNA_FILTER_QUERIES.get(filter_key, ANNA_FILTER_QUERIES['all'])
    try:
        import psycopg2.extras
        conn = db_conn_fn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error('[TESTIMONIAL QUERY ERROR] filter=%s | error=%s', filter_key, str(e))
        return []

def update_consent_status(
    testimonial_id: int,
    consent: str,
    db_conn_fn,
    make_social_ready: bool = False,
) -> bool:
    try:
        conn = db_conn_fn()
        cur  = conn.cursor()
        cur.execute(
            'UPDATE patient_testimonials SET consent_status = %s, '
            'is_social_ready = %s, needs_anna_review = FALSE '
            'WHERE id = %s',
            (consent, make_social_ready, testimonial_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        if make_social_ready:
            log.warning('[TESTIMONIAL SOCIAL_READY] id=%s | consent=%s', testimonial_id, consent)
        return True
    except Exception as e:
        log.error('[TESTIMONIAL CONSENT UPDATE ERROR] id=%s | error=%s', testimonial_id, str(e))
        return False

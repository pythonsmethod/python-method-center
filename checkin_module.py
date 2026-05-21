# -*- coding: utf-8 -*-
# Patient State Check-in / Life Progress Diary
# Module: checkin_module.py
# Purpose: Detect check-in intents, update session state fields, classify
#          positive life outcomes, and flag for Karen escalation.
# Design:  Additive-only — no side effects outside session dict.
#          Called from agents.py process_message() after state_engine.analyze().
# Phase 5 / Step 6 — Patient State Check-in Module
import logging
from datetime import timezone, datetime

log = logging.getLogger('checkin_module')

# ---------------------------------------------------------------------------
# CHECK-IN INTENT KEYWORDS
# These complement state_engine intents. Matched after state_engine runs.
# ---------------------------------------------------------------------------

_CHECKIN_KW = {
    'patient_reports_progress': [
        'стало лучше', 'чувствую себя лучше', 'улучшение', 'улучшилось',
        'прогресс', 'результат', 'результаты', 'вижу результат',
        'вижу результаты', 'есть результат', 'есть результаты',
        'всё лучше', 'намного лучше', 'заметно лучше', 'гораздо лучше',
        'замечаю изменения', 'изменения есть', 'есть изменения',
        'сдвиг', 'двигаюсь вперёд', 'иду вперёд',
    ],
    'patient_reports_life_event': [
        'поехал', 'поехала', 'полетел', 'полетела', 'съездил', 'съездила',
        'посетил', 'посетила', 'встретил', 'встретила', 'встретились',
        'побывал', 'побывала', 'провёл время', 'провела время',
        'смог поехать', 'смогла поехать', 'смог пойти', 'смогла пойти',
        'благодаря методу', 'благодаря вам', 'благодаря программе',
        'если бы не метод', 'если бы не программа', 'если бы не вы',
        'без вас не смог', 'без вас не смогла',
        'дочь', 'сын', 'внук', 'внучка', 'семья', 'семьёй',
        'праздник', 'день рождения', 'свадьба', 'путешествие',
        'поездка', 'отпуск', 'отдых', 'вернулся с', 'вернулась с',
    ],
    'patient_reports_emotional_shift': [
        'счастлив', 'счастлива', 'радость', 'радуюсь', 'рад', 'рада',
        'доволен', 'довольна', 'спокойно', 'стало спокойнее',
        'меньше тревоги', 'тревоги меньше', 'тревога ушла',
        'спокойствие', 'умиротворение', 'легче', 'стало легче',
        'надежда', 'есть надежда', 'оптимизм', 'верю', 'верю в лучшее',
        'сил больше', 'появились силы', 'больше энергии', 'энергия',
        'настроение хорошее', 'хорошее настроение', 'на подъёме',
        'улыбаюсь', 'смеюсь', 'смеялся', 'смеялась',
        'очень счастлив', 'очень счастлива', 'огромная радость',
    ],
    'patient_reports_decline': [
        'хуже', 'стало хуже', 'ухудшение', 'ухудшилось', 'становится хуже',
        'болью', 'боль усилилась', 'боль сильнее', 'сильная боль',
        'очень плохо', 'совсем плохо', 'не могу', 'не справляюсь',
        'сил нет', 'нет сил', 'упадок', 'упадок сил',
        'не помогает', 'ничего не помогает', 'без изменений',
        'всё плохо', 'плохо себя чувствую', 'чувствую себя плохо',
        'депрессия', 'тяжело', 'тяжело стало', 'хуже чем раньше',
        'почти не встаю', 'не встаю', 'слабость', 'слабею',
        'кризис', 'снова плохо',
    ],
    'scheduled_state_check': [
        'как дела', 'как вы', 'как ты', 'как поживаете', 'как поживаешь',
        'как себя чувствуете', 'как себя чувствуешь', 'как состояние',
        'как здоровье', 'как настроение', 'что нового', 'что изменилось',
        'расскажи как', 'расскажите как', 'давно не писали', 'давно молчали',
    ],
}

# Trigger words that confirm a positive_life_outcome event
_POSITIVE_OUTCOME_KW = [
    'смог поехать', 'смогла поехать', 'смог пойти', 'смогла пойти',
    'благодаря методу', 'благодаря вам', 'благодаря программе',
    'если бы не метод', 'если бы не программа', 'если бы не вы',
    'без вас не смог', 'без вас не смогла',
    'очень счастлив', 'очень счастлива', 'огромная радость',
    'счастлив', 'счастлива',
]

# Karen escalation triggers (decline signals)
_KAREN_ESCALATION_KW = [
    'хуже', 'стало хуже', 'ухудшение', 'ухудшилось', 'становится хуже',
    'очень плохо', 'совсем плохо', 'не справляюсь',
    'нет сил', 'депрессия', 'тяжело стало', 'кризис',
    'почти не встаю', 'не встаю', 'слабость', 'слабею',
    'снова плохо', 'хуже чем раньше',
]


def detect_checkin_intent(user_message: str, current_intent: str) -> str:
    """
    Detect check-in specific intent from the user message.
    Only fires when state_engine has not already classified the message
    as a more specific clinical intent.
    Returns one of the 5 check-in intent labels or None.
    """
    if not user_message:
        return None
    msg = user_message.lower().strip()

    # If state_engine already classified something specific — keep it
    # but still overlay checkin context on top (see update_checkin_fields)
    _CLINICAL_INTENTS = {
        'escalation_request', 'paid', 'ready_to_pay',
        'analysis_upload', 'payment_question',
    }
    if current_intent in _CLINICAL_INTENTS:
        return None

    # Priority order for check-in intents
    for label in [
        'patient_reports_decline',
        'patient_reports_life_event',
        'patient_reports_emotional_shift',
        'patient_reports_progress',
        'scheduled_state_check',
    ]:
        for kw in _CHECKIN_KW[label]:
            if kw in msg:
                return label

    return None


def _detect_positive_outcome(user_message: str) -> bool:
    """Return True if message contains a positive life outcome signal."""
    msg = user_message.lower()
    return any(kw in msg for kw in _POSITIVE_OUTCOME_KW)


def _detect_karen_needed(user_message: str) -> bool:
    """Return True if message contains a decline/escalation signal."""
    msg = user_message.lower()
    return any(kw in msg for kw in _KAREN_ESCALATION_KW)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_checkin_fields(session: dict, user_message: str, checkin_intent: str) -> dict:
    """
    Update session check-in memory fields in-place (additive, non-destructive).
    Returns a dict of changes made (for logging).
    This function ONLY writes to the new check-in fields.
    It never overwrites route, history, payment_status, or any existing field.
    """
    if checkin_intent is None:
        return {}

    changes = {}
    msg = user_message.lower().strip()

    # ── Always update last_state_check_at ───────────────────────────────────
    session['last_state_check_at'] = _now_iso()
    changes['last_state_check_at'] = session['last_state_check_at']

    # ── Map intent to mood/physical/emotional status ─────────────────────────
    if checkin_intent == 'patient_reports_decline':
        session['mood_status'] = 'declining'
        session['physical_status'] = 'declining'
        session['emotional_status'] = 'distressed'
        changes.update({'mood_status': 'declining', 'physical_status': 'declining', 'emotional_status': 'distressed'})

    elif checkin_intent == 'patient_reports_emotional_shift':
        session['mood_status'] = 'positive'
        session['emotional_status'] = 'uplifted'
        changes.update({'mood_status': 'positive', 'emotional_status': 'uplifted'})

    elif checkin_intent == 'patient_reports_progress':
        session['mood_status'] = 'stable_positive'
        session['physical_status'] = 'improving'
        changes.update({'mood_status': 'stable_positive', 'physical_status': 'improving'})

    elif checkin_intent == 'patient_reports_life_event':
        # Life event — set positive mood unless also declining
        if not _detect_karen_needed(user_message):
            session['mood_status'] = 'positive'
            session['emotional_status'] = 'uplifted'
            changes.update({'mood_status': 'positive', 'emotional_status': 'uplifted'})

    elif checkin_intent == 'scheduled_state_check':
        # Triggered by AI asking — no status change, just timestamp
        pass

    # ── Positive life outcome detection ─────────────────────────────────────
    if _detect_positive_outcome(user_message):
        session['positive_life_outcome'] = True
        # Append to life_event_note (keep last 5 events as list)
        note_entry = {'ts': _now_iso(), 'msg': user_message[:300]}
        notes = session.get('life_event_note') or []
        if not isinstance(notes, list):
            notes = []
        notes.append(note_entry)
        session['life_event_note'] = notes[-5:]  # keep last 5
        # Update patient_win_summary (last win text)
        session['patient_win_summary'] = user_message[:300]
        changes.update({
            'positive_life_outcome': True,
            'life_event_note': 'appended',
            'patient_win_summary': 'updated',
        })

    # ── Karen escalation flag ────────────────────────────────────────────────
    if checkin_intent == 'patient_reports_decline' or _detect_karen_needed(user_message):
        session['needs_karen_review'] = True
        changes['needs_karen_review'] = True

    log.info(
        '[CHECKIN] intent=%s | mood=%s | physical=%s | emotional=%s | outcome=%s | karen=%s',
        checkin_intent,
        session.get('mood_status', '-'),
        session.get('physical_status', '-'),
        session.get('emotional_status', '-'),
        session.get('positive_life_outcome', False),
        session.get('needs_karen_review', False),
    )

    return changes


def get_checkin_response_template(checkin_intent: str, session: dict) -> str:
    """
    Return the appropriate message template key for this check-in intent.
    The actual AI prompt will use these templates to shape its response.
    Returns one of: 'soft_checkin', 'joy_for_outcome', 'post_event_follow_up',
                    'capture_improvement', 'karen_escalation', or None.
    """
    if checkin_intent == 'patient_reports_decline':
        return 'karen_escalation'
    if checkin_intent == 'patient_reports_life_event':
        if _detect_positive_outcome(session.get('patient_win_summary', '')):
            return 'joy_for_outcome'
        return 'post_event_follow_up'
    if checkin_intent == 'patient_reports_emotional_shift':
        return 'joy_for_outcome'
    if checkin_intent == 'patient_reports_progress':
        return 'capture_improvement'
    if checkin_intent == 'scheduled_state_check':
        return 'soft_checkin'
    return None


# ---------------------------------------------------------------------------
# MESSAGE TEMPLATES
# These are injected as prefix instructions into the agent system prompt
# when a check-in intent is detected.
# ---------------------------------------------------------------------------

CHECKIN_TEMPLATES = {
    'soft_checkin': """
[РЕЖИМ ПРОВЕРКИ СОСТОЯНИЯ — state_checkin_mode]
Пациент поделился чем-то о своём состоянии или жизни.
Задача: мягко спросить как он/она себя чувствует — физически и эмоционально.
Правила:
- Тон тёплый, спокойный, без давления
- Не звучи как врач и не ставь диагноз
- Одно-два коротких вопроса максимум
- Покажи, что тебе важно знать как человек, а не как система
Пример интонации: "Рада слышать тебя. Как ты сейчас — физически и душевно?"
""",

    'joy_for_outcome': """
[РЕЖИМ ПОЗИТИВНОГО РЕЗУЛЬТАТА — state_checkin_mode]
Пациент сообщил о позитивном жизненном событии или результате, возможно связанном с методом.
Это ВАЖНЫЙ момент восстановления. Отнесись к нему с искренней радостью и теплотой.
Задача:
1. Сначала искренне обрадуйся за человека — без дежурных фраз
2. Отметь, что это важный шаг и часть его/её восстановления
3. Затем мягко уточни: как он/она себя чувствует физически после этого события?
4. И как эмоционально — что он/она ощущает сейчас?
Правила:
- Тон живой, тёплый, человечный
- Не звучи как бот или врач
- Один экран = одна мысль
- Не переходи к новым темам — останься в этом моменте
""",

    'post_event_follow_up': """
[РЕЖИМ ПОСЛЕ СОБЫТИЯ — state_checkin_mode]
Пациент рассказал о каком-то событии или поездке.
Задача: уточнить как он/она себя чувствует после этого события.
Вопросы:
- Физически — как тело отреагировало? Есть ли усталость, боль, или наоборот — энергия?
- Эмоционально — что он/она чувствует сейчас после этого?
Правила:
- Тёплый, заботливый тон
- Не давить и не торопить
- Короткие вопросы, один экран
""",

    'capture_improvement': """
[РЕЖИМ ФИКСАЦИИ УЛУЧШЕНИЯ — state_checkin_mode]
Пациент сообщил об улучшении или прогрессе.
Задача: зафиксировать это и уточнить детали.
1. Искренне отметь прогресс — это важно для пациента слышать
2. Спроси: в чём именно он/она замечает улучшение?
3. Уточни физическое и эмоциональное состояние
Правила:
- Не преувеличивай и не преуменьшай
- Тон поддерживающий, не оценивающий
- Зафиксируй ощущения человека, не интерпретируй их
""",

    'karen_escalation': """
[РЕЖИМ УХУДШЕНИЯ — ПЕРЕДАЧА КАРЕНУ — state_checkin_mode]
Пациент сообщил об ухудшении состояния или тревожных сигналах.
Задача:
1. Выслушай внимательно, не минимизируй и не обесценивай
2. Выражай искреннее участие и заботу
3. Мягко сообщи, что это важно, и что ты передаёшь информацию куратору (Карену)
4. Спроси: есть ли что-то срочное прямо сейчас?
Правила:
- Не пытайся решить медицинскую проблему
- Не ставь диагноз
- Не давай медицинских советов
- Передай ситуацию живому человеку (Карену)
- Тон мягкий, без паники, с участием
""",
}


def build_checkin_prompt_prefix(template_key: str) -> str:
    """Return the prompt prefix for injection, or empty string."""
    return CHECKIN_TEMPLATES.get(template_key, '')

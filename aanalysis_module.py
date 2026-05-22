# -*- coding: utf-8 -*-
# analysis_module.py — Phase 5 Analysis Route Integration
# Manages analysis uploads as a first-class stage in the patient journey.
#
# Responsibilities:
#   save_analysis_to_session()      — persist analysis metadata into session (no new DB columns)
#   build_analysis_flow_response()  — structured AI-safe response after upload
#   evaluate_escalation()           — auto-flag for Karen review
#   check_analysis_completeness()   — detect missing/incomplete materials
#   get_analysis_continuity_msg()   — return user flow messaging for waiting state
#   guard_medical_interpretation()  — hard constraint: block AI diagnosing
#   detect_analysis_stage()         — read current analysis stage from session
#
# Session fields used (all in existing session dict, no new DB columns needed):
#   analysis_stage          (existing DB column, TEXT)
#   karen_access            (existing DB column, BOOLEAN)
#   analysis_received_at    (in continuity_state JSON)
#   analysis_ocr_status     (in continuity_state JSON)
#   analysis_pages_count    (in continuity_state JSON)
#   analysis_last_upload_at (in continuity_state JSON)
#   analysis_ocr_text       (in continuity_state JSON — last extracted text)
#   analysis_escalation_pending (in continuity_state JSON)
#
# LOGGING tags:
#   [ANALYSIS] analysis_route_entered
#   [ANALYSIS] analysis_saved
#   [ANALYSIS] escalation_created
#   [ANALYSIS] waiting_state_started
#   [ANALYSIS] missing_analysis_requested

import logging
import re
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger('analysis_module')

# ─── Analysis Stage Constants ─────────────────────────────────────────────────

STAGE_RECEIVED    = 'analysis_received'
STAGE_WAITING     = 'analysis_waiting'
STAGE_INCOMPLETE  = 'analysis_incomplete'
STAGE_ESCALATED   = 'analysis_escalated'
STAGE_REVIEWED    = 'analysis_reviewed'

# ─── Oncology / high-priority keyword detection ───────────────────────────────

_ONCOLOGY_KEYWORDS = [
    'рак', 'онкология', 'опухоль', 'метастаз', 'лимфома', 'саркома',
    'гистология', 'биопсия', 'онкомаркер', 'карцинома', 'меланома',
    'злокачественн', 'неоплазия', 'пет-кт', 'пэт', 'пет скан',
    'стадия', 'ремиссия', 'химиотерапия', 'лучевая',
    'cancer', 'tumor', 'metastasis', 'oncology', 'biopsy',
]

_BLOOD_ANALYSIS_KEYWORDS = [
    'гемоглобин', 'лейкоцит', 'эритроцит', 'тромбоцит', 'соэ', 'срб',
    'глюкоза', 'инсулин', 'холестерин', 'билирубин', 'АЛТ', 'АСТ',
    'кератинин', 'мочевина', 'ферритин', 'витамин', 'гормон', 'тсг',
    'т3', 'т4', 'ттг', 'общий анализ крови', 'биохимия',
    'hemoglobin', 'leukocyte', 'glucose', 'creatinine',
]

# ─── Medical Interpretation Guard ────────────────────────────────────────────

MEDICAL_GUARD_INSTRUCTION = (
    "КРИТИЧЕСКИ ВАЖНО — ЗАПРЕТ НА МЕДИЦИНСКУЮ ИНТЕРПРЕТАЦИЮ:\n"
    "- НЕ интерпретируй значения анализов\n"
    "- НЕ делай выводы о здоровье\n"
    "- НЕ предлагай лечение или диагноз\n"
    "- НЕ комментируй отклонения от нормы\n"
    "- Твоя роль: КООРДИНАТОР. Принять данные, подтвердить получение, передать Карену.\n"
    "- Если клиент просит прокомментировать анализы — скажи: "
    \"'Я не интерпретирую медицинские данные — это задача Карена. Я уже передала материалы на проверку.'\""
)

def guard_medical_interpretation(system_prompt: str) -> str:
    """Prepend medical interpretation hard constraints to any system prompt used for analysis route."""
    return MEDICAL_GUARD_INSTRUCTION + "\n\n" + system_prompt

# ─── Flow Response Messages ───────────────────────────────────────────────────

def get_receipt_confirmation(pages_count: int = 1, ocr_confidence: str = 'high', has_caption: bool = False) -> str:
    """
    Structured confirmation message after successful analysis upload.
    Used in ANALYSIS_COLLECTION_MODE.
    """
    if ocr_confidence == 'high':
        quality_note = "Данные считаны успешно."
    elif ocr_confidence == 'low':
        quality_note = "Качество изображения немного низкое — если есть возможность, пришлите более чёткое фото."
    else:
        quality_note = "Файл получен. Если данные не считались — пришлите фото чуть ближе или чётче."

    msg = (
        f"Мы получили ваши анализы. {quality_note} "
        "Сейчас система структурирует данные и подготовит их для Карена. "
        "Он изучит материалы и подготовит индивидуальный протокол. "
        "Я сообщу вам, когда будет готово."
    )
    return msg

def get_waiting_state_message(days_since_upload: int = 0) -> str:
    """Continuity messaging for users in waiting state after upload."""
    if days_since_upload == 0:
        return (
            "Ваши анализы получены и находятся на рассмотрении у Карена. "
            "Это займёт некоторое время — процесс идёт, вы не забыты."
        )
    elif days_since_upload <= 3:
        return (
            "Карен изучает ваши материалы. "
            "Индивидуальный протокол требует внимательного анализа — "
            "именно поэтому это занимает время. Мы на связи."
        )
    else:
        return (
            "Мы помним о вас. Ваши анализы у Карена. "
            "Если хотите уточнить статус — можете написать, я узнаю."
        )

def get_missing_analysis_request(missing_items: list) -> str:
    """Request only specific missing materials, never ask to resend everything."""
    if not missing_items:
        return ""
    items_str = ", ".join(missing_items)
    return (
        f"Чтобы подготовить полный протокол, нужно ещё: {items_str}. "
        "Если этого нет — не беспокойтесь, Карен работает с тем, что есть."
    )

def get_return_flow_message(session: dict) -> str:
    """
    Generate continuity message for returning user who already uploaded analyses.
    Never says 'please send analyses again'.
    """
    stage = detect_analysis_stage(session)
    cs = session.get('continuity_state') or {}
    upload_ts = cs.get('analysis_last_upload_at')

    if stage == STAGE_REVIEWED:
        return (
            "Карен уже изучил ваши анализы. "
            "Если хотите продолжить — я готова помочь с следующим шагом."
        )
    elif stage == STAGE_ESCALATED:
        return (
            "Ваши анализы переданы Карену на проверку. "
            "Он скоро вернётся с индивидуальным протоколом."
        )
    elif stage in (STAGE_WAITING, STAGE_RECEIVED):
        # Calculate days
        days = 0
        if upload_ts:
            try:
                uploaded = datetime.fromisoformat(upload_ts.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                days = (now - uploaded).days
            except Exception:
                pass
        return get_waiting_state_message(days)
    elif stage == STAGE_INCOMPLETE:
        missing = cs.get('analysis_missing_items', [])
        return get_missing_analysis_request(missing)
    return ""

# ─── Escalation Logic ────────────────────────────────────────────────────────

def evaluate_escalation(ocr_text: str, attachment_type: str, ocr_confidence: str, pages_count: int = 1) -> dict:
    """
    Determine whether this analysis upload should auto-flag for Karen escalation.

    Returns:
        {
            'needs_escalation': bool,
            'escalation_reason': str,
            'priority': 'high' | 'normal',
        }
    """
    text_lower = (ocr_text or '').lower()
    reason_parts = []
    priority = 'normal'

    # Blood analysis detected
    blood_detected = any(kw.lower() in text_lower for kw in _BLOOD_ANALYSIS_KEYWORDS)
    if blood_detected:
        reason_parts.append('blood_analysis_detected')

    # Oncology keywords
    onco_detected = any(kw.lower() in text_lower for kw in _ONCOLOGY_KEYWORDS)
    if onco_detected:
        reason_parts.append('oncology_keywords_detected')
        priority = 'high'

    # Medical document (PDF / formal document)
    if attachment_type == 'document':
        reason_parts.append('medical_document_uploaded')

    # Multi-page upload
    if pages_count > 1:
        reason_parts.append('multi_page_upload')

    # OCR confidence sufficient
    if ocr_confidence in ('high', 'low') and ocr_text:
        reason_parts.append('ocr_data_available')

    needs_escalation = len(reason_parts) > 0
    reason = ', '.join(reason_parts) if reason_parts else 'no_escalation_trigger'

    if needs_escalation:
        log.info('[ANALYSIS] escalation_created reason=%s priority=%s', reason, priority)

    return {
        'needs_escalation': needs_escalation,
        'escalation_reason': reason,
        'priority': priority,
    }

# ─── Completeness Check ──────────────────────────────────────────────────────

_REQUIRED_FOR_FULL_PANEL = [
    'общий анализ крови',
    'биохимия',
]

def check_analysis_completeness(ocr_text: str, session: dict) -> dict:
    """
    Check if uploaded analysis appears complete or has obvious gaps.
    Based on OCR text content.

    Returns:
        {
            'is_complete': bool,
            'missing_items': list[str],
            'confidence': 'high' | 'low',
        }
    """
    text_lower = (ocr_text or '').lower()
    missing = []

    # Check for key blood panel components
    has_general = any(kw in text_lower for kw in ['гемоглобин', 'лейкоцит', 'эритроцит', 'общий'])
    has_biochem  = any(kw in text_lower for kw in ['глюкоза', 'холестерин', 'билирубин', 'алт', 'аст', 'биохим'])

    # Only suggest missing items if OCR is reasonably good (>100 chars)
    if len(ocr_text or '') < 100:
        return {'is_complete': True, 'missing_items': [], 'confidence': 'low'}

    if not has_general:
        missing.append('общий анализ крови')
    if not has_biochem:
        missing.append('биохимический анализ крови')

    # Store for return flow
    cs = session.get('continuity_state') or {}
    cs['analysis_missing_items'] = missing
    session['continuity_state'] = cs

    return {
        'is_complete': len(missing) == 0,
        'missing_items': missing,
        'confidence': 'high' if len(ocr_text or '') > 200 else 'low',
    }

# ─── Session Persistence ─────────────────────────────────────────────────────

def save_analysis_to_session(
    session: dict,
    attachment_meta: dict,
    ocr_result: dict,
    escalation_result: dict,
    completeness_result: dict,
) -> dict:
    """
    Persist analysis upload metadata into session using existing fields.
    Uses analysis_stage (DB column) and continuity_state (JSON blob).
    No new DB columns needed.

    Returns updated session.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    ocr_text = ocr_result.get('text', '')
    ocr_confidence = ocr_result.get('confidence', 'failed')
    ocr_success = ocr_result.get('success', False)
    attachment_type = attachment_meta.get('attachment_type', 'unknown')
    pages_count = attachment_meta.get('pages_count', 1)

    # 1. Update analysis_stage (existing DB column)
    if escalation_result.get('needs_escalation'):
        new_stage = STAGE_ESCALATED
    elif not completeness_result.get('is_complete') and completeness_result.get('confidence') == 'high':
        new_stage = STAGE_INCOMPLETE
    else:
        new_stage = STAGE_RECEIVED

    session['analysis_stage'] = new_stage

    # 2. Update karen_access (existing DB column)
    if escalation_result.get('needs_escalation'):
        session['karen_access'] = True
        session['needs_karen_review'] = True

    # 3. Store rich metadata in continuity_state (existing JSON blob column)
    cs = session.get('continuity_state') or {}
    cs.update({
        'analysis_received_at':    cs.get('analysis_received_at') or now_iso,  # don't overwrite first upload
        'analysis_last_upload_at': now_iso,
        'analysis_ocr_status':     'success' if ocr_success else 'failed',
        'analysis_ocr_confidence': ocr_confidence,
        'analysis_pages_count':    pages_count,
        'analysis_attachment_type': attachment_type,
        'analysis_escalation_pending': escalation_result.get('needs_escalation', False),
        'analysis_escalation_reason':  escalation_result.get('escalation_reason', ''),
        'analysis_escalation_priority': escalation_result.get('priority', 'normal'),
        'analysis_missing_items':  completeness_result.get('missing_items', []),
        'analysis_ocr_text_snippet': ocr_text[:500] if ocr_text else '',
    })
    session['continuity_state'] = cs

    # 4. Update route to analysis_route so the right agent (Vera) handles response
    session['route'] = 'analysis_route'
    session['current_intent'] = 'analysis_upload'
    session['current_state'] = STAGE_RECEIVED

    log.info(
        '[ANALYSIS] analysis_saved stage=%s ocr=%s escalation=%s missing=%s',
        new_stage, ocr_confidence,
        escalation_result.get('needs_escalation'),
        completeness_result.get('missing_items')
    )
    log.info('[ANALYSIS] analysis_route_entered contact_stage=%s', new_stage)

    return session

# ─── Stage Detection ─────────────────────────────────────────────────────────

def detect_analysis_stage(session: dict) -> Optional[str]:
    """Read current analysis stage from session."""
    return session.get('analysis_stage') or session.get('continuity_state', {}).get('analysis_stage')

def is_in_analysis_route(session: dict) -> bool:
    """Check if user is currently in analysis collection route."""
    route = session.get('route', '')
    stage = detect_analysis_stage(session)
    return route in ('analysis_route', 'analysis') or stage in (
        STAGE_RECEIVED, STAGE_WAITING, STAGE_INCOMPLETE, STAGE_ESCALATED
    )

def has_analysis_uploaded(session: dict) -> bool:
    """True if user has ever uploaded analysis files."""
    cs = session.get('continuity_state') or {}
    return bool(cs.get('analysis_received_at') or detect_analysis_stage(session))

# ─── Waiting State Logger ─────────────────────────────────────────────────────

def enter_waiting_state(session: dict, contact_id: str = '') -> None:
    """Mark session as in waiting state after analysis receipt."""
    session['analysis_stage'] = STAGE_WAITING
    cs = session.get('continuity_state') or {}
    cs['analysis_waiting_since'] = datetime.now(timezone.utc).isoformat()
    session['continuity_state'] = cs
    log.info('[ANALYSIS] waiting_state_started contact=%s', contact_id)

# ─── Missing Analysis Request Logger ─────────────────────────────────────────

def log_missing_analysis_request(missing_items: list, contact_id: str = '') -> None:
    """Log when we request specific missing analysis materials."""
    log.info('[ANALYSIS] missing_analysis_requested contact=%s items=%s',
             contact_id, missing_items)


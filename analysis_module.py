# -*- coding: utf-8 -*-
# analysis_module.py - Phase 5 Analysis Route Integration
# Manages analysis uploads as a first-class stage in the patient journey.
# Uses ONLY existing session fields: analysis_stage (DB), karen_access (DB),
# continuity_state JSON blob. No new DB columns needed.

import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger('analysis_module')

STAGE_RECEIVED   = 'analysis_received'
STAGE_WAITING    = 'analysis_waiting'
STAGE_INCOMPLETE = 'analysis_incomplete'
STAGE_ESCALATED  = 'analysis_escalated'
STAGE_REVIEWED   = 'analysis_reviewed'

_ONCOLOGY_KEYWORDS = [
    'rak', 'onkologiya', 'opuhol', 'metastaz', 'limfoma', 'sarkoma',
    'gistologiya', 'biopsiya', 'onkomarker', 'karcinoma', 'melanoma',
    'zlokachestven', 'neoplaziya', 'pet-kt', 'pet skan',
    'cancer', 'tumor', 'metastasis', 'oncology', 'biopsy',
    'рак', 'онкология', 'опухоль', 'метастаз', 'лимфома', 'саркома',
    'гистология', 'биопсия', 'онкомаркер', 'карцинома', 'меланома',
    'злокачествен', 'неоплазия', 'пэт', 'стадия', 'ремиссия',
    'химиотерапия', 'лучевая',
]

_BLOOD_KEYWORDS = [
    'гемоглобин', 'лейкоцит', 'эритроцит', 'тромбоцит', 'соэ', 'срб',
    'глюкоза', 'инсулин', 'холестерин', 'билирубин', 'алт', 'аст',
    'креатинин', 'мочевина', 'ферритин', 'витамин', 'гормон', 'ттг',
    'т3', 'т4', 'общий анализ крови', 'биохимия',
    'hemoglobin', 'leukocyte', 'glucose', 'creatinine',
]

MEDICAL_GUARD = (
    "КРИТИЧЕСКИ ВАЖНО — ЗАПРЕТ НА МЕДИЦИНСКУЮ ИНТЕРПРЕТАЦИЮ:\n"
    "- НЕ интерпретируй значения анализов\n"
    "- НЕ делай выводы о здоровье\n"
    "- НЕ предлагай лечение или диагноз\n"
    "- НЕ комментируй отклонения от нормы\n"
    "- Твоя роль: КООРДИНАТОР. Принять данные, подтвердить получение, передать Карену.\n"
    "- Если клиент просит прокомментировать анализы: "
    "'Я не интерпретирую медицинские данные — это задача Карена. Материалы уже переданы на проверку.'\n"
)

def guard_medical_interpretation(system_prompt: str) -> str:
    return MEDICAL_GUARD + "\n\n" + system_prompt

def get_receipt_confirmation(ocr_confidence: str = 'high') -> str:
    if ocr_confidence == 'high':
        quality = "Данные считаны успешно."
    elif ocr_confidence == 'low':
        quality = "Качество изображения немного низкое — если есть возможность, пришлите более чёткое фото."
    else:
        quality = "Файл получен. Если данные не считались — пришлите фото чуть ближе или чётче."
    return (
        "Мы получили ваши анализы. " + quality + " "
        "Сейчас система структурирует данные и подготовит их для Карена. "
        "Он изучит материалы и подготовит индивидуальный протокол. "
        "Я сообщу вам, когда будет готово."
    )

def get_waiting_state_message(days: int = 0) -> str:
    if days == 0:
        return (
            "Ваши анализы получены и находятся на рассмотрении у Карена. "
            "Это займёт некоторое время — процесс идёт, вы не забыты."
        )
    elif days <= 3:
        return (
            "Карен изучает ваши материалы. "
            "Индивидуальный протокол требует внимательного анализа — "
            "именно поэтому это занимает время. Мы на связи."
        )
    else:
        return (
            "Мы помним о вас. Ваши анализы у Карена. "
            "Если хотите уточнить статус — напишите, я узнаю."
        )

def get_missing_analysis_request(missing_items: list) -> str:
    if not missing_items:
        return ""
    items_str = ", ".join(missing_items)
    return (
        "Чтобы подготовить полный протокол, нужно ещё: " + items_str + ". "
        "Если этого нет — не беспокойтесь, Карен работает с тем, что есть."
    )

def get_return_flow_message(session: dict) -> str:
    stage = detect_analysis_stage(session)
    cs = session.get('continuity_state') or {}
    upload_ts = cs.get('analysis_last_upload_at')
    if stage == STAGE_REVIEWED:
        return (
            "Карен уже изучил ваши анализы. "
            "Если хотите продолжить — я готова помочь со следующим шагом."
        )
    elif stage == STAGE_ESCALATED:
        return (
            "Ваши анализы переданы Карену на проверку. "
            "Он скоро вернётся с индивидуальным протоколом."
        )
    elif stage in (STAGE_WAITING, STAGE_RECEIVED):
        days = 0
        if upload_ts:
            try:
                uploaded = datetime.fromisoformat(upload_ts.replace('Z', '+00:00'))
                days = (datetime.now(timezone.utc) - uploaded).days
            except Exception:
                pass
        return get_waiting_state_message(days)
    elif stage == STAGE_INCOMPLETE:
        missing = cs.get('analysis_missing_items', [])
        return get_missing_analysis_request(missing)
    return ""

def evaluate_escalation(ocr_text: str, attachment_type: str, ocr_confidence: str, pages_count: int = 1) -> dict:
    text_lower = (ocr_text or '').lower()
    reason_parts = []
    priority = 'normal'
    if any(kw.lower() in text_lower for kw in _BLOOD_KEYWORDS):
        reason_parts.append('blood_analysis_detected')
    if any(kw.lower() in text_lower for kw in _ONCOLOGY_KEYWORDS):
        reason_parts.append('oncology_keywords_detected')
        priority = 'high'
    if attachment_type == 'document':
        reason_parts.append('medical_document_uploaded')
    if pages_count > 1:
        reason_parts.append('multi_page_upload')
    if ocr_confidence in ('high', 'low') and ocr_text:
        reason_parts.append('ocr_data_available')
    needs = len(reason_parts) > 0
    reason = ', '.join(reason_parts) if reason_parts else 'no_escalation_trigger'
    if needs:
        log.info('[ANALYSIS] escalation_created reason=%s priority=%s', reason, priority)
    return {'needs_escalation': needs, 'escalation_reason': reason, 'priority': priority}

def check_analysis_completeness(ocr_text: str, session: dict) -> dict:
    text_lower = (ocr_text or '').lower()
    if len(ocr_text or '') < 100:
        return {'is_complete': True, 'missing_items': [], 'confidence': 'low'}
    missing = []
    if not any(kw in text_lower for kw in ['гемоглобин', 'лейкоцит', 'эритроцит', 'общий']):
        missing.append('общий анализ крови')
    if not any(kw in text_lower for kw in ['глюкоза', 'холестерин', 'билирубин', 'алт', 'аст', 'биохим']):
        missing.append('биохимический анализ крови')
    cs = session.get('continuity_state') or {}
    cs['analysis_missing_items'] = missing
    session['continuity_state'] = cs
    return {'is_complete': len(missing) == 0, 'missing_items': missing,
            'confidence': 'high' if len(ocr_text or '') > 200 else 'low'}

def save_analysis_to_session(session, attachment_meta, ocr_result, escalation_result, completeness_result):
    now_iso = datetime.now(timezone.utc).isoformat()
    ocr_text = ocr_result.get('text', '')
    ocr_confidence = ocr_result.get('confidence', 'failed')
    ocr_success = ocr_result.get('success', False)
    attachment_type = attachment_meta.get('attachment_type', 'unknown')
    pages_count = attachment_meta.get('pages_count', 1)

    if escalation_result.get('needs_escalation'):
        new_stage = STAGE_ESCALATED
    elif not completeness_result.get('is_complete') and completeness_result.get('confidence') == 'high':
        new_stage = STAGE_INCOMPLETE
    else:
        new_stage = STAGE_RECEIVED

    session['analysis_stage'] = new_stage
    if escalation_result.get('needs_escalation'):
        session['karen_access'] = True
        session['needs_karen_review'] = True

    cs = session.get('continuity_state') or {}
    cs.update({
        'analysis_received_at':    cs.get('analysis_received_at') or now_iso,
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

    session['route'] = 'analysis_route'
    session['current_intent'] = 'analysis_upload'
    session['current_state'] = STAGE_RECEIVED

    log.info('[ANALYSIS] analysis_saved stage=%s ocr=%s escalation=%s missing=%s',
             new_stage, ocr_confidence, escalation_result.get('needs_escalation'),
             completeness_result.get('missing_items'))
    log.info('[ANALYSIS] analysis_route_entered stage=%s', new_stage)
    return session

def detect_analysis_stage(session: dict) -> Optional[str]:
    return session.get('analysis_stage') or (session.get('continuity_state') or {}).get('analysis_stage')

def is_in_analysis_route(session: dict) -> bool:
    route = session.get('route', '')
    stage = detect_analysis_stage(session)
    return route in ('analysis_route', 'analysis') or stage in (
        STAGE_RECEIVED, STAGE_WAITING, STAGE_INCOMPLETE, STAGE_ESCALATED)

def has_analysis_uploaded(session: dict) -> bool:
    cs = session.get('continuity_state') or {}
    return bool(cs.get('analysis_received_at') or detect_analysis_stage(session))

def enter_waiting_state(session: dict, contact_id: str = '') -> None:
    session['analysis_stage'] = STAGE_WAITING
    cs = session.get('continuity_state') or {}
    cs['analysis_waiting_since'] = datetime.now(timezone.utc).isoformat()
    session['continuity_state'] = cs
    log.info('[ANALYSIS] waiting_state_started contact=%s', contact_id)

def log_missing_analysis_request(missing_items: list, contact_id: str = '') -> None:
    log.info('[ANALYSIS] missing_analysis_requested contact=%s items=%s', contact_id, missing_items)

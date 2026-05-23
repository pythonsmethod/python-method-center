# -*- coding: utf-8 -*-
# analysis_module.py - Phase 5 Analysis Route Integration
# Manages analysis uploads as a first-class stage in the patient journey.
# Uses ONLY existing session fields: analysis_stage (DB), karen_access (DB),
# continuity_state JSON blob. No new DB columns needed.

import logging
from datetime import datetime, timezone
from typing import Optional
from normalization_module import normalize_ocr_result, build_chronology, build_karen_dossier

log = logging.getLogger('analysis_module')

STAGE_RECEIVED   = 'analysis_received'
STAGE_WAITING    = 'analysis_waiting'
STAGE_INCOMPLETE = 'analysis_incomplete'
STAGE_ESCALATED  = 'analysis_escalated'
STAGE_REVIEWED   = 'analysis_reviewed'


# ============================================================
# EXPERT REVIEW LIFECYCLE STATES — Phase 5.1 Step 5
# Deterministic state machine for Karen expert review workflow.
# No medical logic. No diagnosis. No autonomous decisions.
# All state transitions require explicit external trigger or wiring call.
# ============================================================

# Expert review lifecycle state constants
REVIEW_STATE_DOSSIER_READY      = 'DOSSIER_READY'
REVIEW_STATE_QUEUED             = 'QUEUED_FOR_KAREN'
REVIEW_STATE_UNDER_REVIEW       = 'UNDER_REVIEW'
REVIEW_STATE_WAITING_MORE_DATA  = 'WAITING_MORE_DATA'
REVIEW_STATE_COMPLETED          = 'REVIEW_COMPLETED'
REVIEW_STATE_RETURNED           = 'RETURNED_TO_ANALYSIS'
REVIEW_STATE_FOLLOWUP           = 'FOLLOWUP_REQUIRED'

# Valid transition map: {from_state: {to_state, ...}}
# Enforces lifecycle order. No skipping states.
_VALID_REVIEW_TRANSITIONS = {
    None:                               {REVIEW_STATE_DOSSIER_READY, REVIEW_STATE_QUEUED},
    REVIEW_STATE_DOSSIER_READY:         {REVIEW_STATE_QUEUED, REVIEW_STATE_RETURNED},
    REVIEW_STATE_QUEUED:                {REVIEW_STATE_UNDER_REVIEW, REVIEW_STATE_RETURNED,
                                         REVIEW_STATE_WAITING_MORE_DATA},
    REVIEW_STATE_UNDER_REVIEW:          {REVIEW_STATE_COMPLETED, REVIEW_STATE_WAITING_MORE_DATA,
                                         REVIEW_STATE_RETURNED, REVIEW_STATE_FOLLOWUP},
    REVIEW_STATE_WAITING_MORE_DATA:     {REVIEW_STATE_QUEUED, REVIEW_STATE_RETURNED},
    REVIEW_STATE_COMPLETED:             {REVIEW_STATE_FOLLOWUP},
    REVIEW_STATE_RETURNED:              {REVIEW_STATE_DOSSIER_READY, REVIEW_STATE_QUEUED},
    REVIEW_STATE_FOLLOWUP:              {REVIEW_STATE_COMPLETED, REVIEW_STATE_RETURNED},
}

# States that block escalation completion (cannot be marked done while in these states)
_ESCALATION_BLOCKING_REVIEW_STATES = {
    REVIEW_STATE_WAITING_MORE_DATA,
    REVIEW_STATE_RETURNED,
}


def validate_review_transition(current_state: Optional[str], target_state: str) -> bool:
    """
    Check whether a lifecycle transition is permitted.

    Returns True if transition is valid, False otherwise.
    Logs a warning on invalid transition attempt.
    SAFE: never raises.
    """
    try:
        allowed = _VALID_REVIEW_TRANSITIONS.get(current_state, set())
        if target_state in allowed:
            return True
        log.warning(
            '[REVIEW] invalid_transition attempted from=%s to=%s allowed=%s',
            current_state, target_state, sorted(allowed),
        )
        return False
    except Exception as e:
        log.warning('[REVIEW] validate_review_transition error: %s', e)
        return False


def initialize_expert_review_state(session: dict, contact_id: str = '') -> None:
    """
    Initialize the expert review lifecycle state when dossier is first ready.
    Transitions from None → DOSSIER_READY → QUEUED_FOR_KAREN.
    Called once per upload when escalation_verdict == READY_FOR_KAREN.

    SAFE: non-fatal. Idempotent if already initialized.
    No medical logic. No autonomous decisions.
    """
    try:
        cs = session.get('continuity_state') or {}
        current_state = cs.get('expert_review_state')

        # Idempotent: do not re-initialize if already queued or beyond
        if current_state in (
            REVIEW_STATE_QUEUED, REVIEW_STATE_UNDER_REVIEW,
            REVIEW_STATE_COMPLETED, REVIEW_STATE_FOLLOWUP,
        ):
            log.info('[REVIEW] review_state_already_active contact=%s state=%s',
                     contact_id, current_state)
            return

        now_iso = datetime.now(timezone.utc).isoformat()

        # Transition: None → DOSSIER_READY
        if validate_review_transition(current_state, REVIEW_STATE_DOSSIER_READY):
            cs['expert_review_state']            = REVIEW_STATE_DOSSIER_READY
            cs['expert_review_last_transition']  = now_iso
            cs['expert_review_blockers']         = []
            cs['expert_followup_required']       = False
            session['continuity_state'] = cs
            log.info('[REVIEW] review_state_initialized contact=%s state=%s',
                     contact_id, REVIEW_STATE_DOSSIER_READY)

        # Auto-advance: DOSSIER_READY → QUEUED_FOR_KAREN
        if validate_review_transition(REVIEW_STATE_DOSSIER_READY, REVIEW_STATE_QUEUED):
            cs['expert_review_state']            = REVIEW_STATE_QUEUED
            cs['expert_review_started_at']       = now_iso
            cs['expert_review_last_transition']  = now_iso
            session['continuity_state'] = cs
            log.info('[REVIEW] review_transition contact=%s from=%s to=%s',
                     contact_id, REVIEW_STATE_DOSSIER_READY, REVIEW_STATE_QUEUED)

    except Exception as e:
        log.warning('[REVIEW] initialize_expert_review_state failed: %s', e)


def transition_expert_review_state(
    session: dict,
    target_state: str,
    contact_id: str = '',
    blockers: Optional[list] = None,
    followup_required: bool = False,
) -> bool:
    """
    Transition the expert review lifecycle to a new state.
    Validates transition before applying. Stores result in continuity_state.

    Returns True if transition was applied, False if blocked.
    SAFE: non-fatal. Does not interpret medical data.

    Args:
        session: full session dict
        target_state: one of the REVIEW_STATE_* constants
        contact_id: for logging
        blockers: list of operational blocker strings (no medical language)
        followup_required: flag to mark that follow-up action is needed
    """
    try:
        cs = session.get('continuity_state') or {}
        current_state = cs.get('expert_review_state')
        now_iso = datetime.now(timezone.utc).isoformat()

        if not validate_review_transition(current_state, target_state):
            log.warning('[REVIEW] review_blocked contact=%s from=%s to=%s',
                        contact_id, current_state, target_state)
            return False

        # Safety rules
        if target_state == REVIEW_STATE_COMPLETED and current_state != REVIEW_STATE_UNDER_REVIEW:
            log.warning('[REVIEW] review_blocked cannot_complete: must be UNDER_REVIEW first '
                        'contact=%s current=%s', contact_id, current_state)
            return False

        if target_state == REVIEW_STATE_UNDER_REVIEW:
            dossier = cs.get('karen_expert_dossier') or {}
            handoff = dossier.get('handoff_notes') or {}
            if not handoff.get('ready_for_karen', False):
                log.warning('[REVIEW] review_blocked incomplete_dossier_cannot_enter_UNDER_REVIEW '
                            'contact=%s', contact_id)
                # Add blocker but do not crash
                cs['expert_review_blockers'] = list(
                    set(cs.get('expert_review_blockers') or []) |
                    {'incomplete_dossier'}
                )
                session['continuity_state'] = cs
                return False

        # Apply transition
        cs['expert_review_state']           = target_state
        cs['expert_review_last_transition'] = now_iso
        cs['expert_followup_required']      = followup_required

        if blockers is not None:
            cs['expert_review_blockers'] = blockers
        elif target_state not in _ESCALATION_BLOCKING_REVIEW_STATES:
            cs['expert_review_blockers'] = []

        if target_state == REVIEW_STATE_COMPLETED:
            cs['expert_review_completed_at'] = now_iso

        if target_state == REVIEW_STATE_FOLLOWUP:
            cs['expert_followup_required'] = True

        session['continuity_state'] = cs

        log.info('[REVIEW] review_transition contact=%s from=%s to=%s followup=%s blockers=%s',
                 contact_id, current_state, target_state, followup_required, blockers)

        if target_state == REVIEW_STATE_COMPLETED:
            log.info('[REVIEW] review_completed contact=%s', contact_id)
        elif target_state == REVIEW_STATE_FOLLOWUP:
            log.info('[REVIEW] followup_requested contact=%s', contact_id)

        return True

    except Exception as e:
        log.warning('[REVIEW] transition_expert_review_state failed: %s', e)
        return False



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
        "Документ получен и добавлен в кейс. " + quality + "\n\n"
        "Материалы зафиксированы. Карен сможет приступить к просмотру, как только комплект будет готов.\n\n"
        "Я уточню, если потребуется что-то ещё."
    )

def get_waiting_state_message(days: int = 0) -> str:
    if days == 0:
        return (
            "Материалы зафиксированы и переданы Карену.\n\n"
            "Процесс идёт — вы не забыты. Как только будет что сообщить, я напишу."
        )
    elif days <= 3:
        return (
            "Карен изучает ваши материалы.\n\n"
            "Индивидуальная работа требует времени — именно поэтому она точная. Мы на связи."
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
        "Для более полной картины пригодится ещё: " + items_str + ".\n\n"
        "Если этого нет — не беспокойтесь. Карен начнёт просмотр материалов с тем, что уже есть."
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
            "Материалы переданы Карену.\n\n"
            "Он изучит их и обсудит, какой формат сопровождения может быть полезен в вашей ситуации."
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



# ============================================================
# DOSSIER-AWARE ESCALATION — Phase 5.1 Step 4
# Deterministic. No diagnosis. No medical interpretation.
# Reads existing dossier fields to gate escalation safely.
# ============================================================

# Escalation verdict constants
ESCALATION_VERDICT_READY      = 'READY_FOR_KAREN'
ESCALATION_VERDICT_INCOMPLETE = 'INCOMPLETE_CASE'
ESCALATION_VERDICT_RETRY      = 'NEEDS_UPLOAD_RETRY'

# Blocking gaps that indicate a corrupted/unreadable upload (retry needed)
_RETRY_GAPS = {
    'ocr_failed_or_not_run',
    'no_biomarkers_extracted',
    'normalization_not_completed',
}

# Blocking gaps that indicate missing data but upload was valid (keep in flow)
_INCOMPLETE_GAPS = {
    'no_chronology_available',
    'route_or_stage_not_escalation_compatible',
    'all_uploads_missing_dates',
}


def dossier_escalation_check(cs: dict) -> dict:
    """
    Determine safe escalation verdict from dossier readiness data.

    Input: continuity_state dict (after dossier assembly).
    Output: {
        "verdict": str,           # READY_FOR_KAREN | INCOMPLETE_CASE | NEEDS_UPLOAD_RETRY
        "reason": str,            # human-readable operational note
        "blocking_gaps": [str],   # list of gap keys from dossier
    }

    SAFE: never raises. Defaults to INCOMPLETE_CASE on error.
    Deterministic. No AI. No medical interpretation.
    """
    result = {
        'verdict': ESCALATION_VERDICT_INCOMPLETE,
        'reason': 'default_incomplete',
        'blocking_gaps': [],
    }
    try:
        dossier = cs.get('karen_expert_dossier') or {}
        handoff = dossier.get('handoff_notes') or {}
        ready = handoff.get('ready_for_karen', False)
        blocking_gaps = handoff.get('blocking_gaps') or []
        result['blocking_gaps'] = blocking_gaps

        if ready:
            result['verdict'] = ESCALATION_VERDICT_READY
            result['reason'] = handoff.get('safe_escalation_reason', 'dossier_ready')
            log.info('[DOSSIER] dossier_ready contact escalation_verdict=READY_FOR_KAREN gaps=0')
            return result

        # Classify gap type
        gap_set = set(blocking_gaps)
        is_retry = bool(gap_set & _RETRY_GAPS)
        is_incomplete = bool(gap_set & _INCOMPLETE_GAPS)

        if is_retry:
            result['verdict'] = ESCALATION_VERDICT_RETRY
            result['reason'] = 'upload_requires_retry: ' + ', '.join(gap_set & _RETRY_GAPS)
            log.info('[DOSSIER] dossier_blocked verdict=NEEDS_UPLOAD_RETRY gaps=%s', blocking_gaps)
        elif is_incomplete or blocking_gaps:
            result['verdict'] = ESCALATION_VERDICT_INCOMPLETE
            result['reason'] = 'case_incomplete: ' + ', '.join(blocking_gaps)
            log.info('[DOSSIER] dossier_blocked verdict=INCOMPLETE_CASE gaps=%s', blocking_gaps)
        else:
            result['verdict'] = ESCALATION_VERDICT_INCOMPLETE
            result['reason'] = 'dossier_not_ready_unknown_reason'
            log.info('[DOSSIER] dossier_blocked verdict=INCOMPLETE_CASE gaps=none_specified')

    except Exception as e:
        log.warning('[DOSSIER] dossier_escalation_check failed: %s', e)
        result['verdict'] = ESCALATION_VERDICT_INCOMPLETE
        result['reason'] = 'escalation_check_exception'

    return result


def apply_dossier_escalation_verdict(session: dict, cs: dict, verdict_result: dict) -> None:
    """
    Apply escalation verdict to session and continuity_state.
    Overrides analysis_stage, karen_access, needs_karen_review based on dossier verdict.
    Stores verdict fields in continuity_state.

    SAFE: never raises. Logs all transitions.
    Does NOT interpret biomarkers. Does NOT assign medical priority.
    """
    try:
        verdict = verdict_result.get('verdict', ESCALATION_VERDICT_INCOMPLETE)
        reason = verdict_result.get('reason', '')
        blocking_gaps = verdict_result.get('blocking_gaps', [])

        # Store verdict in continuity_state
        cs['escalation_verdict'] = verdict
        cs['escalation_verdict_reason'] = reason
        cs['escalation_blocked_by'] = blocking_gaps
        session['continuity_state'] = cs

        if verdict == ESCALATION_VERDICT_READY:
            # Dossier is ready — escalation may proceed (existing flags stay set)
            log.info('[DOSSIER] escalation_allowed verdict=READY_FOR_KAREN stage=%s',
                     session.get('analysis_stage'))

        elif verdict == ESCALATION_VERDICT_RETRY:
            # Upload was unreadable — pull back escalation, keep in analysis route
            session['analysis_stage'] = STAGE_INCOMPLETE
            session['karen_access'] = False
            session['needs_karen_review'] = False
            log.info('[DOSSIER] upload_retry_requested verdict=NEEDS_UPLOAD_RETRY '
                     'stage forced to=%s gaps=%s', STAGE_INCOMPLETE, blocking_gaps)

        elif verdict == ESCALATION_VERDICT_INCOMPLETE:
            # Valid upload but missing data — keep in waiting state, delay escalation
            if session.get('analysis_stage') == STAGE_ESCALATED:
                session['analysis_stage'] = STAGE_WAITING
                session['karen_access'] = False
                session['needs_karen_review'] = False
                log.info('[DOSSIER] escalation_delayed verdict=INCOMPLETE_CASE '
                         'stage reverted from ESCALATED to WAITING gaps=%s', blocking_gaps)
            else:
                log.info('[DOSSIER] escalation_delayed verdict=INCOMPLETE_CASE '
                         'stage unchanged=%s gaps=%s', session.get('analysis_stage'), blocking_gaps)

    except Exception as e:
        log.warning('[DOSSIER] apply_dossier_escalation_verdict failed: %s', e)


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

    # Phase 5.1: Canonical normalization — deterministic, no AI, no diagnosis
    try:
        source_upload_id = (
            attachment_meta.get('file_id', '') or
            attachment_meta.get('file_name', '') or
            datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        )
        ocr_result = normalize_ocr_result(ocr_result, source_upload_id=source_upload_id)
        _norm = ocr_result.get('normalized', {})
        log.info('[ANALYSIS] normalization_complete upload_id=%s biomarkers=%d ok=%s',
                 source_upload_id, _norm.get('biomarker_count', 0), _norm.get('normalization_ok'))
    except Exception as _norm_err:
        log.warning('[ANALYSIS] normalization_skipped err=%s', _norm_err)
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
        'normalized_biomarkers':   ocr_result.get('normalized', {}).get('biomarkers', []),
        'normalized_upload_date':  ocr_result.get('normalized', {}).get('upload_date'),
        'normalization_version':   ocr_result.get('normalized', {}).get('version'),
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

    # Phase 5.1 Step 2: Chronology merge — accumulate uploads history and build timeline
    try:
        _existing_history = cs.get('normalized_biomarkers_history', [])
        _current_biomarkers = ocr_result.get('normalized', {}).get('biomarkers', [])
        if _current_biomarkers:
            _existing_history = list(_existing_history) + [_current_biomarkers]
        cs['normalized_biomarkers_history'] = _existing_history

        _chronology = build_chronology(_existing_history)
        cs['analysis_chronology'] = _chronology
        cs['chronology_version'] = _chronology.get('chronology_version', '')
        cs['reconciled_biomarkers'] = [
            b
            for date_entry in _chronology.get('dates', [])
            for b in date_entry.get('biomarkers', [])
        ]
        cs['repeated_biomarkers'] = _chronology.get('repeated_biomarkers', {})
        session['continuity_state'] = cs
        log.info('[CHRONOLOGY] chronology_merged dates=%d biomarkers=%d repeated=%d',
                 len(_chronology.get('dates', [])),
                 _chronology.get('biomarkers_count', 0),
                 len(_chronology.get('repeated_biomarkers', {})))
    except Exception as _chron_err:
        log.warning('[CHRONOLOGY] chronology_merge_failed: %s', _chron_err)

    # Phase 5.1 Step 3: Karen expert dossier assembly — deterministic, no diagnosis, no AI
    try:
        _dossier = build_karen_dossier(cs, session=session)
        cs['karen_expert_dossier'] = _dossier
        cs['dossier_version'] = _dossier.get('dossier_version', '')
        cs['dossier_ready_for_karen'] = _dossier.get('handoff_notes', {}).get('ready_for_karen', False)
        session['continuity_state'] = cs
        log.info('[DOSSIER] dossier_assembled ready=%s gaps=%s',
                 cs['dossier_ready_for_karen'],
                 _dossier.get('handoff_notes', {}).get('blocking_gaps', []))
    except Exception as _dossier_err:
        log.warning('[DOSSIER] dossier_assembly_failed: %s', _dossier_err)



    # Phase 5.1 Step 4: Dossier-aware escalation check — gates Karen access
    try:
        _verdict_result = dossier_escalation_check(cs)
        apply_dossier_escalation_verdict(session, cs, _verdict_result)
        _verdict = _verdict_result.get('verdict', '')
        log.info('[DOSSIER] escalation_verdict=%s reason=%.120s',
                 _verdict, _verdict_result.get('reason', ''))
    except Exception as _verdict_err:
        log.warning('[DOSSIER] escalation_verdict_check_failed: %s', _verdict_err)

    session['route'] = 'analysis_route'
    session['current_intent'] = 'analysis_upload'
    session['current_state'] = STAGE_RECEIVED

    log.info('[ANALYSIS] analysis_saved stage=%s ocr=%s escalation=%s missing=%s',
             new_stage, ocr_confidence, escalation_result.get('needs_escalation'),
             completeness_result.get('missing_items'))
    log.info('[ANALYSIS] analysis_route_entered stage=%s', new_stage)

    # Phase 5.1 Step 5: Expert review lifecycle initialization
    try:
        _esc_verdict = cs.get('escalation_verdict', '')
        if _esc_verdict == ESCALATION_VERDICT_READY:
            initialize_expert_review_state(session)
            log.info('[REVIEW] review_state_initialized_after_escalation verdict=%s', _esc_verdict)
        elif _esc_verdict in (ESCALATION_VERDICT_RETRY, ESCALATION_VERDICT_INCOMPLETE):
            # Dossier not ready — mark lifecycle state as WAITING_MORE_DATA if already queued
            _current_review_state = cs.get('expert_review_state')
            if _current_review_state == REVIEW_STATE_QUEUED:
                transition_expert_review_state(
                    session, REVIEW_STATE_WAITING_MORE_DATA,
                    blockers=cs.get('escalation_blocked_by', []),
                )
    except Exception as _lifecycle_err:
        log.warning('[REVIEW] lifecycle_init_failed: %s', _lifecycle_err)


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
    """
    Transition session to waiting state.
    Phase 5.1 Step 5: Lifecycle-aware — does not downgrade a QUEUED_FOR_KAREN review state.
    """
    cs = session.get('continuity_state') or {}
    review_state = cs.get('expert_review_state')

    # Do not override an active review queue with a waiting state
    if review_state in (REVIEW_STATE_QUEUED, REVIEW_STATE_UNDER_REVIEW):
        log.info('[ANALYSIS] waiting_state_skipped contact=%s review_state=%s',
                 contact_id, review_state)
        return

    session['analysis_stage'] = STAGE_WAITING
    cs['analysis_waiting_since'] = datetime.now(timezone.utc).isoformat()
    session['continuity_state'] = cs
    log.info('[ANALYSIS] waiting_state_started contact=%s', contact_id)


def log_missing_analysis_request(missing_items: list, contact_id: str = '') -> None:
    log.info('[ANALYSIS] missing_analysis_requested contact=%s items=%s', contact_id, missing_items)

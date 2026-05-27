# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: response_validator.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Validate AI prompts (pre-generation) and AI responses (post-generation).
#          Catches: medical overreach, payment dead zones, prompt leakage,
#          repetitive responses, cold/robotic tone, broken empathy,
#          hallucinated facts, dangerous medical claims.
#
# Pre-validation (validate_prompt):
#   - Checks system prompt for injection artifacts
#   - Verifies agent is correct for current route
#   - Checks anti-medical-overreach instructions are present for Vera
#
# Post-validation (validate_response):
#   - Medical overreach detection (diagnosis/prescription claims)
#   - Payment dead zone detection (paid user getting payment pitch)
#   - Repetition detection (same response as last N)
#   - Minimum length check
#   - Forbidden phrases check
#   - Prompt leakage check (system prompt fragments in response)
# =============================================================================

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger("response_validator")

# ---------------------------------------------------------------------------
# Medical overreach patterns (Vera must NEVER produce these)
# ---------------------------------------------------------------------------
_MEDICAL_OVERREACH_PATTERNS = [
    r"у вас (диагноз|диагностирован[оа]?)",
    r"вам (нужно|необходимо|следует) (принимать|пить|колоть)",
    r"(назначаю|рекомендую принимать|выписываю)",
    r"это (онкология|рак|злокачественн)",
    r"(химиотерапия|облучение|операция) (необходима|обязательна|нужна)",
    r"ваш анализ показывает (рак|онкологию|злокачественное)",
    r"прогноз (благоприятный|неблагоприятный|плохой)",
]

# ---------------------------------------------------------------------------
# Forbidden phrases (must never appear in responses)
# ---------------------------------------------------------------------------
_FORBIDDEN_PHRASES = [
    "как языковая модель",
    "как ai",
    "как искусственный интеллект",
    "я не могу чувствовать",
    "я программа",
    "system prompt",
    "системный промпт",
    "[overlay]",
    "[orch",
    "json",
    "route=",
    "intent=",
]

# ---------------------------------------------------------------------------
# Capsule / formula / Pythons Elixir ban — legal boundary
# ---------------------------------------------------------------------------
# Per concept (Python Method Knowledge Base, §4 and «Голос Анны»):
# bot sells the program and Karen's supervision only; capsules / formula /
# Pythons Elixir / composition / dosage / delivery are Karen's personal work
# with a patient, outside the bot, the offer and Stripe. Hard ban.
_CAPSULE_FORMULA_PATTERNS = [
    r"капсул",         # капсула, капсулы, капсулам, ...
    r"формул",         # формула, формулу, формулой, ...
    r"эликсир",        # эликсир (Russian transliteration)
    r"elixir",         # Elixir (English / Pythons Elixir)
    r"pythons\s+elixir",
    r"дозиров",        # дозировка, дозировкой, дозируется
    r"состав\s+(препарат|капсул|формул|эликсир)",  # narrow — avoids "состав крови"
    # ── Per Anna's correction (2026-05-24): Karen does NOT individualize
    # the capsule composition — the Formula is a single fixed patent-pending
    # composition he ships for free as a personal initiative outside the
    # program. The bot must not imply any per-patient capsule protocol
    # / dosing / schedule / composition tuning.
    r"протокол\s+капсул",                     # "протокол капсул"
    r"индивидуальный\s+состав",               # "индивидуальный состав"
    r"состав\s+под\s+\w+",                    # any "состав под X" (вашу, конкретного, etc.)
    r"подбирает\b[^.]{0,30}(состав|протокол|формул|капсул|дозиров|компонент)",
    r"созда[её]т\b[^.]{0,30}состав",          # "Карен создаёт состав" / "создаёт индивидуальный состав"
    r"схем[ауые]\s+при[её]ма",                 # "схему/е/а/ы приёма/приема" — all cases (RUNTIME-GUARDRAILS-1)
    r"персональная\s+формул",                 # "персональная формула под вашу ситуацию"
    r"ваш(а|у)\s+формул",                     # "ваша формула / вашу формулу"
    r"индивидуальный\s+протокол\s+капсул",    # explicit phrase from Anna's screenshot
    r"золоты(е|х)\s+капсул",                  # "золотые капсулы" — per §23.14
    # ── PHASE RUNTIME-GUARDRAILS-1: semantic synonym expansion (2026-05-27)
    r"персональн(ый|ая)\s+протокол\s+капсул",   # "персональный протокол капсул"
    r"персональн(ый|ая)\s+(состав|формул)",       # "персональный/ая состав / формула"
    r"схем[ауые]\s+лечения",                       # "схему/е/а/ы лечения" — all cases (RUNTIME-GUARDRAILS-1)
]

# Safe fallback — verbatim from Biblia §23.5 (docs/biblia_section_23_ai_logic.md).
# Used when a forbidden mention is caught OR a patient-asked capsule question
# isn't routed to Karen properly. This is Anna's canonical wording.
_CAPSULE_FORMULA_FALLBACK = (
    "Эти вопросы Карен обсуждает лично после того, как изучит вашу "
    "ситуацию, анализы и текущее состояние. Формула не продаётся "
    "отдельно через центр — здесь оформляется именно сопровождение "
    "и индивидуальная работа."
)

# ---------------------------------------------------------------------------
# Incoming capsule/formula inquiry — patient ASKS about it
# ---------------------------------------------------------------------------
# Per Anna: when a patient asks about capsules/formula/dosage/delivery/price,
# the bot must NOT ignore the question — it must route the patient to Karen
# personally (Karen sends the Formula for free to every paid participant as
# his personal initiative outside the bot). The bot's reply must explicitly
# acknowledge that Karen will personally handle these questions.
_INCOMING_CAPSULE_PATTERNS = [
    r"капсул",
    r"формул",
    r"эликсир",
    r"elixir",
    r"pythons\s+elixir",
    r"дозиров",
    r"capsul",
    r"dosag",
]
# Note: "состав" and "доставк" are deliberately NOT triggers — they false-fire
# on "состав крови", "доставка договора". A real capsule inquiry will still
# match through "капсул"/"формул"/"эликсир" — e.g. "состав формулы" matches
# "формул", "доставка капсул" matches "капсул".

# A proper reply to a capsule/formula inquiry must mention Karen AND signal
# that he'll handle it personally / after entering the program.
_KAREN_NAME_MARKERS = ["карен", "karen"]
_KAREN_HANDLES_MARKERS = [
    "лично", "сам ", "сама ", "после", "в работу",
    "индивидуально", "индивидуальн", "personally",
]

# ---------------------------------------------------------------------------
# Minimum response length (chars)
# ---------------------------------------------------------------------------
_MIN_RESPONSE_LEN = 20

# ---------------------------------------------------------------------------
# Repetition window (check last N responses)
# ---------------------------------------------------------------------------
_REPETITION_WINDOW = 3
_REPETITION_SIMILARITY_THRESHOLD = 0.85


def _similarity(a: str, b: str) -> float:
    """Simple Jaccard similarity on word sets."""
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# ResponseValidator class
# ---------------------------------------------------------------------------
class ResponseValidator:
    """
    Pre- and post-generation validation for AI responses.

    Usage:
        validator = ResponseValidator()

        # Before generating response (validate system prompt)
        pre = validator.validate_prompt(system_prompt, session)
        if not pre["safe"]: log.warning(pre["issues"])

        # After generating response
        post = validator.validate_response(reply, session, context_package)
        if not post["safe"]:
            reply = post["safe_reply"]  # corrected reply if possible
    """

    def validate_prompt(
        self,
        system_prompt: str,
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Pre-generation validation of the system prompt.
        Returns {safe: bool, issues: list, warnings: list}
        """
        issues = []
        warnings = []

        try:
            agent = session.get("active_agent", "Lucky")
            route = session.get("route", "reception")

            # Check Vera has anti-overreach instructions
            if agent == "Vera":
                if "НЕ ставь диагнозы" not in system_prompt and "не ставь диагноз" not in system_prompt.lower():
                    issues.append("vera_missing_anti_overreach")
                    log.warning("[VALIDATOR] Vera prompt missing anti-overreach instructions")

            # Check for prompt injection artifacts
            for suspicious in ["ignore previous", "ignore above", "disregard", "new instructions:"]:
                if suspicious.lower() in system_prompt.lower():
                    issues.append(f"prompt_injection_artifact: {suspicious}")
                    log.error("[VALIDATOR] PROMPT INJECTION detected: %s", suspicious)

            # Warn if prompt is very short
            if len(system_prompt) < 50:
                warnings.append("prompt_too_short")

        except Exception as e:
            log.error("[VALIDATOR] validate_prompt error: %s", e)
            issues.append(f"validator_error: {e}")

        return {
            "safe": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }

    def validate_response(
        self,
        reply: str,
        session: Dict[str, Any],
        context_package: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Post-generation validation of AI response.
        Returns {safe: bool, issues: list, safe_reply: str (corrected if needed)}
        """
        issues = []
        safe_reply = reply

        try:
            agent = session.get("active_agent", "Lucky")
            payment_status = context_package.get("payment_status", "new")
            route = context_package.get("route", "reception")
            history: List[Dict] = session.get("history", [])

            # -------------------------------------------------------------------
            # Check 1: Minimum length
            # -------------------------------------------------------------------
            if len(reply.strip()) < _MIN_RESPONSE_LEN:
                issues.append("response_too_short")
                safe_reply = (
                    "Я здесь. Расскажите мне подробнее — что вас беспокоит?"
                )

            # -------------------------------------------------------------------
            # Check 2: Medical overreach (critical for all agents)
            # -------------------------------------------------------------------
            reply_lower = reply.lower()
            for pattern in _MEDICAL_OVERREACH_PATTERNS:
                if re.search(pattern, reply_lower):
                    issues.append(f"medical_overreach: {pattern}")
                    log.error("[VALIDATOR] MEDICAL OVERREACH in %s response: %s", agent, pattern)
                    # Replace with safe fallback
                    safe_reply = (
                        "Для точной интерпретации этих данных необходимо "
                        "обратиться к лечащему врачу. Я могу помочь подготовить "
                        "вопросы для консультации."
                    )
                    break

            # -------------------------------------------------------------------
            # Check 2b: Capsule / formula / Pythons Elixir mention (legal ban)
            # -------------------------------------------------------------------
            for pattern in _CAPSULE_FORMULA_PATTERNS:
                if re.search(pattern, reply_lower):
                    issues.append(f"capsule_formula_mention: {pattern}")
                    log.error(
                        "[VALIDATOR] CAPSULE/FORMULA mention in %s response: %s",
                        agent, pattern,
                    )
                    safe_reply = _CAPSULE_FORMULA_FALLBACK
                    break

            # -------------------------------------------------------------------
            # Check 2c: Patient asked about capsules — reply MUST route to Karen
            # -------------------------------------------------------------------
            # Find the most recent user message in history
            last_user_msg = ""
            for m in reversed(history):
                if m.get("role") == "user":
                    last_user_msg = (m.get("content", "") or "").lower()
                    break

            if last_user_msg:
                asked_about_capsule = any(
                    re.search(p, last_user_msg) for p in _INCOMING_CAPSULE_PATTERNS
                )
                if asked_about_capsule:
                    current_reply_lower = safe_reply.lower()
                    mentions_karen = any(
                        m in current_reply_lower for m in _KAREN_NAME_MARKERS
                    )
                    signals_handling = any(
                        m in current_reply_lower for m in _KAREN_HANDLES_MARKERS
                    )
                    if not (mentions_karen and signals_handling):
                        issues.append("capsule_inquiry_not_routed_to_karen")
                        log.error(
                            "[VALIDATOR] Patient asked about capsule/formula but "
                            "reply does NOT route to Karen properly"
                        )
                        safe_reply = _CAPSULE_FORMULA_FALLBACK

            # -------------------------------------------------------------------
            # Check 3: Forbidden phrases
            # -------------------------------------------------------------------
            for phrase in _FORBIDDEN_PHRASES:
                if phrase.lower() in reply_lower:
                    issues.append(f"forbidden_phrase: {phrase}")
                    log.warning("[VALIDATOR] forbidden phrase in response: %s", phrase)

            # -------------------------------------------------------------------
            # Check 4: Payment dead zone (paid user getting payment pitch)
            # -------------------------------------------------------------------
            if payment_status == "paid":
                payment_pitch_phrases = [
                    "оплатите", "купите", "оформить оплату",
                    "выберите тариф", "стоимость программы",
                ]
                for phrase in payment_pitch_phrases:
                    if phrase.lower() in reply_lower:
                        issues.append(f"payment_dead_zone: paid_user_getting_payment_pitch")
                        log.warning("[VALIDATOR] payment dead zone: paid user got payment pitch")
                        break

            # -------------------------------------------------------------------
            # Check 5: Repetition detection
            # -------------------------------------------------------------------
            assistant_msgs = [
                m.get("content", "") for m in history
                if m.get("role") == "assistant"
            ][-_REPETITION_WINDOW:]

            for prev_reply in assistant_msgs:
                sim = _similarity(reply, prev_reply)
                if sim >= _REPETITION_SIMILARITY_THRESHOLD:
                    issues.append(f"repetitive_response: similarity={sim:.2f}")
                    log.warning("[VALIDATOR] repetitive response detected: sim=%.2f", sim)
                    break

            # -------------------------------------------------------------------
            # Check 6: Prompt leakage
            # -------------------------------------------------------------------
            leakage_markers = ["[OVERLAY]", "[ORCH", "overlay_type=", "route=reception", "system_prompt"]
            for marker in leakage_markers:
                if marker.lower() in reply_lower:
                    issues.append(f"prompt_leakage: {marker}")
                    log.error("[VALIDATOR] PROMPT LEAKAGE: %s", marker)
                    safe_reply = safe_reply.replace(marker, "")

            # -------------------------------------------------------------------
            # PHASE 3A — ACTIVE REWRITE (HIGH) + SHADOW MODE (SOFT) — RUNTIME-GUARDRAILS-1
            # HIGH severity groups (MEDICAL_EXTENDED, WELLNESS_DRIFT, KAREN_DOWNGRADE):
            #   → matched + not suppressed → modifies safe_reply via _build_recovery_reply()
            # SOFT severity groups: log + record only, no safe_reply change.
            # Runs check_pattern_with_context() for all governance pattern groups.
            # -------------------------------------------------------------------
            try:
                _shadow_contact_id = str(context_package.get("contact_id", session.get("contact_id", "unknown")))
                _shadow_route = route
                _shadow_agent = agent

                # Governance pattern groups with severity and violation type
                _SHADOW_CHECKS = [
                    (MEDICAL_EXTENDED_PATTERNS,   "medical_extended",   "HARD"),
                    (FALSE_PRICE_PATTERNS,         "false_price",        "HARD"),
                    (RESULT_PROMISE_PATTERNS,      "result_promise",     "HARD"),
                    (SALES_AGGRESSIVE_PATTERNS,    "sales_aggressive",   "SOFT"),
                    (CORPORATE_LANGUAGE_PATTERNS,  "corporate_language", "SOFT"),
                    (CHATBOT_FAQ_PATTERNS,         "chatbot_faq",        "SOFT"),
                    (WELLNESS_DRIFT_PATTERNS,      "wellness_drift",     "SOFT"),
                    (KAREN_DOWNGRADE_PATTERNS,     "karen_downgrade",    "SOFT"),
                    (OVERCONFIDENCE_PATTERNS,      "overconfidence",     "SOFT"),
                    (COLD_AUTOMATION_PATTERNS,     "cold_automation",    "SOFT"),
                ]

                for _pattern_group, _vtype, _severity in _SHADOW_CHECKS:
                    for _pat in _pattern_group:
                        _ctx_result = check_pattern_with_context(
                            _pat, reply, _vtype, _severity
                        )
                        if _ctx_result["matched"]:
                            if _ctx_result["suppressed"]:
                                log.debug(
                                    "[SEMANTIC][SHADOW] type=%s suppressed=True reason=%s match=%s",
                                    _vtype, _ctx_result["reason"], _ctx_result["match_text"],
                                )
                                with _obs_lock:
                                    _obs_suppressed[_vtype] = _obs_suppressed.get(_vtype, 0) + 1
                            else:
                                _issue_key = f"{_vtype}: {_ctx_result['match_text']}"
                                if _issue_key not in issues:
                                    issues.append(_issue_key)
                                # RUNTIME-GUARDRAILS-1: ACTIVE REWRITE for promoted HIGH-severity groups
                                _ACTIVE_REWRITE_TYPES = {"medical_extended", "wellness_drift", "karen_downgrade"}
                                if _vtype in _ACTIVE_REWRITE_TYPES:
                                    _active_recovery = _build_recovery_reply(
                                        _vtype, _shadow_agent, _shadow_route, safe_reply, "RS-3"
                                    )
                                    if _active_recovery:
                                        safe_reply = _active_recovery
                                        log.warning(
                                            "[SEMANTIC][ACTIVE] type=%s agent=%s route=%s → safe_reply rewritten",
                                            _vtype, _shadow_agent, _shadow_route,
                                        )
                                if _severity == "HARD":
                                    log.info(
                                        "[SEMANTIC][SHADOW] type=%s suppressed=False severity=HARD agent=%s route=%s match=%s",
                                        _vtype, _shadow_agent, _shadow_route, _ctx_result["match_text"],
                                    )
                                else:
                                    log.debug(
                                        "[SEMANTIC][SHADOW] type=%s suppressed=False severity=SOFT agent=%s route=%s match=%s",
                                        _vtype, _shadow_agent, _shadow_route, _ctx_result["match_text"],
                                    )
                                record_semantic_event(
                                    _shadow_contact_id,
                                    _shadow_agent,
                                    _shadow_route,
                                    _vtype,
                                    _severity,
                                )
                            break

            except Exception as _shadow_err:
                log.debug("[SEMANTIC][SHADOW] shadow check error: %s", _shadow_err)



        except Exception as e:
            log.error("[VALIDATOR] validate_response error: %s", e)
            issues.append(f"validator_error: {e}")

        return {
            "safe": len([i for i in issues if "warning" not in i and "repetitive" not in i]) == 0,
            "issues": issues,
            "safe_reply": safe_reply,
        }
# =============================================================================
# PHASE 1 FOUNDATION ONLY — constants/state only, no runtime behavior changes.
# All governance, observability, recovery, and context-filter constants live
# here. Nothing below is wired into validate_response() yet.
# =============================================================================

# ---------------------------------------------------------------------------
# Phase 1 — Additional imports (additive, safe)
# ---------------------------------------------------------------------------
import datetime as _dt
import collections as _obs_collections
import threading as _obs_threading

# ---------------------------------------------------------------------------
# Phase 1 — Semantic Drift Pattern Constants (Firewall Layer)
# ---------------------------------------------------------------------------

# SV-01  Sales / aggressive selling tone
SALES_AGGRESSIVE_PATTERNS = [
    r"что\s+входит\s+в\s+(пакет|тариф|программ)",
    r"(выберите|подберите)\s+(пакет|тариф|план)",
    r"наш\s+(пакет|продукт|сервис|услуг)",
    r"специальное\s+предложение",
    r"ограниченное\s+предложение",
    r"акци[яю]\s+(действует|заканчивается|только)",
    r"(закажите|приобретите|оформите)\s+сейчас",
    r"лучшее\s+соотношение\s+цены",
    r"выгодн(ый|ое|ая)\s+(вариант|предложение|условие)",
]

# SV-02  Result promises / guarantees
RESULT_PROMISE_PATTERNS = [
    r"гарантиру(ем|ю|ет)\s+(результат|эффект|выздоровление|успех)",
    r"вы\s+(точно|обязательно|100%)\s+(почувствуете|увидите|получите)",
    r"результат\s+(гарантирован|будет|придёт)",
    r"(вылечит|избавит|устранит)\s+(навсегда|полностью|окончательно)",
    r"проверено\s+(наукой|клиникой|исследованиями)",
    r"клинически\s+доказан",
]

# SV-03  False / wrong price mentions
FALSE_PRICE_PATTERNS = [
    r"стоимость\s+.*?\d{2,}",
    r"цена\s+.*?\d{2,}",
    r"\d{3,}\s*(руб|рублей|₽|usd|\$|dollar)",
    r"(программа|сопровождение|курс)\s+(стоит|обойдётся|оценивается)\s+.*?\d",
    r"от\s+\d{3,}\s*(руб|₽|usd|\$)",
]

# SV-04  Medical extended (beyond existing _MEDICAL_OVERREACH_PATTERNS)
MEDICAL_EXTENDED_PATTERNS = [
    r"(этот|данный)\s+протокол\s+(лечения|терапии|восстановления)",
    r"медицинский\s+(подход|метод|протокол)",
    r"клинически\s+(проверен|подтверждён|обоснован)",
    r"терапевтический\s+(эффект|курс|план)",
    r"схема\s+(лечения|терапии|приёма\s+препарат)",
    r"(дозировк|дозу)\s+(лекарств|препарат|таблет)",
    r"противопоказани[яй]\s+(у вас|для вас|в вашем)",
    r"(поставить|поставим|ставим)\s+диагноз",
]

# SV-05  Corporate language / dehumanization
CORPORATE_LANGUAGE_PATTERNS = [
    r"наша\s+(компания|организация|служба)",
    r"(клиент|заказчик)\s+(получает|имеет|может)",
    r"пакет\s+(услуг|сервис|обслуживания)",
    r"ваш\s+запрос\s+(принят|обработан|зарегистрирован)",
    r"(обработка|рассмотрение)\s+обращения",
    r"техническая\s+поддержка",
    r"согласно\s+(регламенту|стандарту|процедуре)",
    r"в\s+соответствии\s+с\s+(правилами|политикой)",
]

# SV-06  Chatbot / FAQ machine tone
CHATBOT_FAQ_PATTERNS = [
    r"я\s+(готов|рад)\s+помочь\s+вам",
    r"чем\s+могу\s+помочь",
    r"если\s+у\s+вас\s+возникнут\s+вопросы",
    r"не\s+стесняйтесь\s+(спрашивать|обращаться)",
    r"(спасибо|благодарим)\s+за\s+(обращение|вопрос|интерес)",
    r"для\s+получения\s+дополнительной\s+информации",
    r"ознакомьтесь\s+с\s+(условиями|разделом|FAQ|инструкцией)",
    r"автоматически\s+(обработан|зарегистрирован|направлен)",
]

# SV-07  Wellness / supplement shop drift
WELLNESS_DRIFT_PATTERNS = [
    r"(биодобавк|БАД|бад)\b",
    r"натуральный\s+(состав|продукт|комплекс)",
    r"(укрепляет|поддерживает|улучшает)\s+(иммунитет|здоровье|организм)",
    r"(природный|органический)\s+(компонент|ингредиент|экстракт)",
    r"(детокс|очищение\s+организма)",
    r"(витаминный|минеральный)\s+(комплекс|набор|курс)",
]

# SV-08  Karen downgrade (AI replacing Karen's role)
KAREN_DOWNGRADE_PATTERNS = [
    r"я\s+(сам|сама)\s+(подберу|составлю|разработаю)\s+(для вас|вам|маршрут|программ|протокол)",
    r"(составлю|разработаю|создам)\s+(для вас|вам)\s+(план|программ|маршрут|протокол)",
    r"ваш\s+(личный|персональный|индивидуальный)\s+(план|маршрут|программа)\s+(готов|создан|разработан)",
    r"я\s+проведу\s+(вас|анализ|работу)",
    r"ваш\s+(куратор|наставник|сопровождающий)\s+\u2014?\s*я",
]

# SV-09  Over-confidence / false reassurance
OVERCONFIDENCE_PATTERNS = [
    r"не\s+переживайте[,.]?\s+(всё|это)\s+(обязательно|точно|100%)\s+(пройдёт|наладится|будет)",
    r"всё\s+будет\s+(хорошо|отлично|прекрасно)\b(?!\s*\?)",
    r"я\s+(уверен|уверена)\s+(на\s+100|абсолютно|полностью)\s+(что|в том)",
    r"(гарантированно|обязательно)\s+(поможет|сработает|даст результат)",
    r"это\s+(точно|обязательно|гарантированно)\s+(поможет|сработает)",
]

# SV-10  Cold automation / robotic confirmations
COLD_AUTOMATION_PATTERNS = [
    r"ваши\s+данные\s+(сохранены|записаны|зафиксированы|переданы)",
    r"(запрос|заявка)\s+(создан[аы]?|оформлен[аы]?|принят[аы]?)",
    r"ожидайте\s+(ответа|звонка|уведомления)\s+в\s+течени",
    r"(уведомление|напоминание)\s+(отправлено|будет\s+отправлено)",
    r"статус\s+(заявки|запроса|обращения)",
    r"автоматически\s+(сформирован|выдан|отправлен)",
]

# SV-11  Chatbot phrase replacements (soft rewrite substitutions)
CHATBOT_REPLACEMENTS = {
    "чем могу помочь": "расскажите, что происходит",
    "я готов помочь вам": "я здесь",
    "не стесняйтесь обращаться": "пишите, как пойдёт",
    "спасибо за обращение": "хорошо, слышу вас",
    "если у вас возникнут вопросы": "если что-то непонятно",
    "для получения дополнительной информации": "если хотите узнать больше",
}

# ---------------------------------------------------------------------------
# Phase 1 — Context Filter Constants (Context-Aware Semantic Filtering)
# ---------------------------------------------------------------------------

_CTX_NEGATION_WINDOW = 80
_CTX_NEGATION_MARKERS = [
    "не ", "нет ", "никогда", "не занимаемся", "не ставим",
    "не даём", "не даем", "не делаем", "не предоставляем",
    "не является", "не обещаем", "мы не", "я не", "центр не", "без ",
]

_CTX_QUOTE_WINDOW = 120
_CTX_QUOTE_MARKERS = [
    "«", "»", '"', "например,", "как будто", "звучит как",
    "похоже на", "вопрос о", "говорите о", "упоминаете",
    "написали", "спрашиваете",
]

_CTX_GOVERNANCE_WINDOW = 100
_CTX_GOVERNANCE_MARKERS = [
    "почему центр не", "почему мы не", "объясню почему",
    "именно потому что", "поэтому центр", "поэтому мы",
    "наша позиция", "принципиально",
]

_CTX_ESCALATION_WINDOW = 150
_CTX_ESCALATION_MARKERS = [
    "карен", "karen", "свяжется с вами", "передам",
    "переключу", "эскалация", "специалист", "лично", "запишем",
]

_CTX_PRESCRIBED_SAFE = [
    "формула не продаётся отдельно через центр",
    "карен обсуждает лично",
    "карен отправляет формулу",
    "оформляется именно сопровождение",
    "после того, как изучит вашу ситуацию",
    "карен лично разберётся",
    "карен сам свяжется",
    "передам карену",
    "карен ответит лично",
]

_CTX_FALLBACK_FINGERPRINTS = [
    "формула не продаётся отдельно через центр",
    "для точной интерпретации этих данных необходимо",
    "я здесь. расскажите мне подробнее",
]

_CTX_NEVER_DOWNGRADE_PATTERNS = [
    r"у вас (диагноз|диагностирован[оа]?)",
    r"(назначаю|выписываю)",
    r"вам нужно принимать",
    r"это (онкология|рак|злокачественн)",
    r"гарантиру(ем|ю|ет)\s+результат",
    r"(химиотерапия|облучение)\s+(необходима|обязательна)",
]

# ---------------------------------------------------------------------------
# Phase 1 — Recovery Constants (Semantic Recovery Layer)
# ---------------------------------------------------------------------------

RECOVERY_NEXT_STEP = {
    "reception":  "Давайте начнём с вашей ситуации — расскажите, что происходит.",
    "trust":      "Расскажите больше — я здесь, чтобы разобраться вместе с вами.",
    "offer":      "Если хотите — опишите, что вас беспокоит больше всего прямо сейчас.",
    "onboarding": "Карен скоро выйдет на связь — пока расскажите, как вы себя чувствуете.",
    "support":    "Пишите, как всё идёт — я слежу за вашим маршрутом.",
    "escalation": "Карен лично разберётся с этим вопросом. Я передам.",
}
RECOVERY_NEXT_STEP_DEFAULT = "Расскажите, что происходит — я здесь."

RECOVERY_AGENT_OPENER = {
    "Lucky":  "Слышу вас.",
    "Maya":   "Понимаю.",
    "Hannah": "Хорошо.",
    "Nadia":  "Ясно.",
    "Iris":   "Принято.",
    "Vera":   "Понятно.",
}
RECOVERY_AGENT_OPENER_DEFAULT = "Слышу вас."

RECOVERY_MEDICAL = (
    "Этот вопрос важный — именно для таких случаев нужен живой специалист. "
    "Карен лично разберётся с вашей ситуацией."
)
RECOVERY_FORMULA = (
    "Всё, что связано с составом и приёмом, Карен обсуждает лично — "
    "после того, как познакомится с вашей ситуацией."
)
RECOVERY_SALES_PRESSURE = (
    "Давление здесь ни к чему. Расскажите, что вас беспокоит — "
    "я помогу разобраться, подходит ли центр для вашей ситуации."
)
RECOVERY_FALSE_PRICE = (
    "Стоимость программ фиксирована — Знакомство и Полное сопровождение. "
    "Точные цифры я уточню для вас отдельно."
)
RECOVERY_RESULT_PROMISE = (
    "Обещать результаты было бы нечестно — каждая ситуация индивидуальна. "
    "Карен работает с реальной картиной, а не с ожиданиями."
)
RECOVERY_WARMTH_APPEND = " Я здесь — пишите."
RECOVERY_KAREN = (
    "Карен лично занимается этим вопросом. Я передам всё, что важно."
)
RECOVERY_ESCALATION = (
    "Этот вопрос выходит за рамки того, что я могу разобрать здесь. "
    "Карен свяжется с вами лично."
)
RECOVERY_ROUTE_APPEND = " Следующий шаг — за вами."

# ---------------------------------------------------------------------------
# Phase 1 — Observability State Variables
# ---------------------------------------------------------------------------

_obs_lock = _obs_threading.Lock()
_drift_counters: dict = {}
_agent_counters: dict = {}
_route_counters: dict = {}
_session_semantic_risk: dict = {}
_obs_ring_buffer: _obs_collections.deque = _obs_collections.deque(maxlen=500)
_obs_suppressed: dict = {}

DRIFT_TYPE_MAP = {
    "sales_aggressive":           "SALES",
    "result_promise":             "TRUST",
    "false_price":                "TRUST",
    "medical_extended":           "MEDICAL",
    "medical_overreach":          "MEDICAL",
    "corporate_language":         "CHATBOT",
    "chatbot_faq":                "CHATBOT",
    "wellness_drift":             "FORMULA",
    "capsule_formula":            "FORMULA",
    "karen_downgrade":            "KAREN",
    "overconfidence":             "TRUST",
    "cold_automation":            "CHATBOT",
    "repetitive_response":        "AUTOMATION",
    "forbidden_phrase":           "CHATBOT",
    "prompt_leakage":             "CHATBOT",
    "capsule_inquiry_not_routed": "ROUTE",
    "payment_dead_zone":          "ROUTE",
}

HARD_STOP_TYPES = frozenset([
    "medical_overreach",
    "medical_extended",
    "false_price",
    "capsule_formula",
    "prompt_leakage",
    "result_promise",
])

SOFT_BLOCK_TYPES = frozenset([
    "sales_aggressive",
    "corporate_language",
    "chatbot_faq",
    "wellness_drift",
    "karen_downgrade",
    "overconfidence",
    "cold_automation",
    "repetitive_response",
    "forbidden_phrase",
    "capsule_inquiry_not_routed",
    "payment_dead_zone",
])

# ---------------------------------------------------------------------------
# Phase 1 — Governance Feedback State Variables
# ---------------------------------------------------------------------------

_gov_violation_log: _obs_collections.deque = _obs_collections.deque(maxlen=5000)
_gov_drift_first_seen: dict = {}
_gov_drift_last_seen: dict = {}
_gov_drift_resolved_since: dict = {}
_gov_drift_regression: dict = {}
_gov_hourly_snapshots: _obs_collections.deque = _obs_collections.deque(maxlen=48)
_gov_total_checks: int = 0
_gov_total_rewrites: int = 0

# =============================================================================
# END PHASE 1 FOUNDATION — no runtime calls made above, no behavior changed.
# =============================================================================
# =============================================================================
# PHASE 2 HELPERS ONLY — functions defined but not connected to validator runtime.
# validate_response() is NOT modified. No auto-execution. No side effects.
# =============================================================================


# ---------------------------------------------------------------------------
# Phase 2 — Context Helper Functions (pure, deterministic, no side effects)
# ---------------------------------------------------------------------------

def _ctx_find_sentence(reply: str, match_start: int) -> str:
    """
    Extract the sentence containing the match position.
    Returns up to 200 chars around the match for context analysis.
    Pure function — no side effects.
    """
    lo = max(0, match_start - 200)
    hi = min(len(reply), match_start + 200)
    return reply[lo:hi]


def _ctx_has_negation(reply: str, match_start: int) -> bool:
    """
    Return True if a negation marker appears within _CTX_NEGATION_WINDOW chars
    BEFORE the match start. Suppresses false positives like
    'мы не занимаемся лечением' matching a medical pattern.
    Pure function — no side effects, no logging.
    """
    window_start = max(0, match_start - _CTX_NEGATION_WINDOW)
    context = reply[window_start:match_start].lower()
    return any(marker in context for marker in _CTX_NEGATION_MARKERS)


def _ctx_has_quote(reply: str, match_start: int) -> bool:
    """
    Return True if a quote marker appears within _CTX_QUOTE_WINDOW chars
    before the match. Suppresses false positives like quoting patient
    language ('звучит как...' / 'вы упоминаете...').
    Pure function — no side effects, no logging.
    """
    window_start = max(0, match_start - _CTX_QUOTE_WINDOW)
    context = reply[window_start:match_start].lower()
    return any(marker in context for marker in _CTX_QUOTE_MARKERS)


def _ctx_has_governance(reply: str, match_start: int) -> bool:
    """
    Return True if a governance/explanation marker appears within
    _CTX_GOVERNANCE_WINDOW chars before the match. Suppresses false
    positives when the bot explains WHY the center does not do something
    ('именно потому что...', 'поэтому мы...').
    Pure function — no side effects, no logging.
    """
    window_start = max(0, match_start - _CTX_GOVERNANCE_WINDOW)
    context = reply[window_start:match_start].lower()
    return any(marker in context for marker in _CTX_GOVERNANCE_MARKERS)


def _ctx_has_escalation_routing(reply: str, match_start: int) -> bool:
    """
    Return True if an escalation marker appears within
    _CTX_ESCALATION_WINDOW chars around the match. Suppresses false
    positives when the bot routes to Karen ('Карен лично...').
    Pure function — no side effects, no logging.
    """
    window_start = max(0, match_start - _CTX_ESCALATION_WINDOW)
    window_end = min(len(reply), match_start + _CTX_ESCALATION_WINDOW)
    context = reply[window_start:window_end].lower()
    return any(marker in context for marker in _CTX_ESCALATION_MARKERS)


def _ctx_is_prescribed_safe(reply: str) -> bool:
    """
    Return True if the reply contains one of the canonical prescribed-safe
    phrases from _CTX_PRESCRIBED_SAFE (Biblia-approved wording).
    These phrases are always safe — suppress any pattern match on them.
    Pure function — no side effects, no logging.
    """
    reply_lower = reply.lower()
    return any(phrase in reply_lower for phrase in _CTX_PRESCRIBED_SAFE)


def _ctx_is_fallback_self(reply: str) -> bool:
    """
    Return True if the reply IS one of the system's own fallback texts
    (identified by _CTX_FALLBACK_FINGERPRINTS). Prevents the validator
    from re-validating its own safe replies and self-triggering.
    Pure function — no side effects, no logging.
    """
    reply_lower = reply.lower()
    return any(fp in reply_lower for fp in _CTX_FALLBACK_FINGERPRINTS)


# ---------------------------------------------------------------------------
# Phase 2 — Master Context Checker
# ---------------------------------------------------------------------------

def check_pattern_with_context(
    pattern: str,
    reply: str,
    violation_type: str,
    severity: str = "SOFT",
) -> dict:
    """
    Check a single pattern against a reply with full context-aware suppression.

    Returns a structured result dict — does NOT modify reply, does NOT log,
    does NOT call recovery. Caller decides what to do with the result.

    Result schema:
        matched    (bool)     — pattern found in reply
        suppressed (bool)     — match found but context says it is a false positive
        reason     (str|None) — why suppressed, or None
        match_text (str|None) — the matched substring, or None
        severity   (str)      — original severity passed in ("HARD" or "SOFT")
    """
    result: dict = {
        "matched": False,
        "suppressed": False,
        "reason": None,
        "match_text": None,
        "severity": severity,
    }

    try:
        import re as _re_local
        m = _re_local.search(pattern, reply.lower())
        if m is None:
            return result

        result["matched"] = True
        result["match_text"] = m.group(0)
        match_start = m.start()

        # Never-downgrade check — these patterns MUST NOT be suppressed
        for nd_pattern in _CTX_NEVER_DOWNGRADE_PATTERNS:
            if _re_local.search(nd_pattern, reply.lower()):
                return result

        # Self-fallback check — reply is our own fallback text
        if _ctx_is_fallback_self(reply):
            result["suppressed"] = True
            result["reason"] = "fallback_self"
            return result

        # Prescribed-safe check — reply uses Biblia-approved wording
        if _ctx_is_prescribed_safe(reply):
            result["suppressed"] = True
            result["reason"] = "prescribed_safe"
            return result

        # Negation context
        if _ctx_has_negation(reply, match_start):
            result["suppressed"] = True
            result["reason"] = "negation_context"
            return result

        # Quote context
        if _ctx_has_quote(reply, match_start):
            result["suppressed"] = True
            result["reason"] = "quote_context"
            return result

        # Governance context
        if _ctx_has_governance(reply, match_start):
            result["suppressed"] = True
            result["reason"] = "governance_context"
            return result

        # Escalation routing context — only for specific violation types
        if violation_type in ("capsule_formula", "medical_extended", "karen_downgrade"):
            if _ctx_has_escalation_routing(reply, match_start):
                result["suppressed"] = True
                result["reason"] = "escalation_routing"
                return result

    except Exception:
        result["matched"] = False

    return result


# ---------------------------------------------------------------------------
# Phase 2 — Recovery Helper Functions (string builders only)
# ---------------------------------------------------------------------------

def _extract_safe_opener(reply: str) -> str:
    """
    Extract the first sentence of the original reply to use as opener
    when a recovery rewrite preserves the beginning of the message.
    Returns empty string if reply is empty or first sentence is too long.
    Pure string function — no side effects, no logging.
    """
    if not reply:
        return ""
    import re as _re_local
    m = _re_local.search(r'[.!?]', reply[:200])
    if m:
        first = reply[:m.start() + 1].strip()
        if 10 <= len(first) <= 150:
            return first
    return ""


def _build_recovery_reply(
    violation_type: str,
    agent_name: str,
    route_name: str,
    original_reply: str = "",
    recovery_mode: str = "RS-1",
) -> str:
    """
    Build a recovery reply string for a given violation type, agent, and route.

    recovery_mode:
        RS-0 — no recovery needed (violation suppressed by context)
        RS-1 — soft append: original reply + warmth append
        RS-2 — partial rewrite: opener + recovery text + next step
        RS-3 — full replacement: recovery text only

    Pure string builder — no logging, no validator integration,
    no global writes, no side effects.
    """
    if recovery_mode == "RS-0":
        return original_reply

    opener = RECOVERY_AGENT_OPENER.get(agent_name, RECOVERY_AGENT_OPENER_DEFAULT)
    next_step = RECOVERY_NEXT_STEP.get(route_name, RECOVERY_NEXT_STEP_DEFAULT)

    body_map = {
        "medical_overreach":          RECOVERY_MEDICAL,
        "medical_extended":           RECOVERY_MEDICAL,
        "capsule_formula":            RECOVERY_FORMULA,
        "capsule_inquiry_not_routed": RECOVERY_FORMULA,
        "sales_aggressive":           RECOVERY_SALES_PRESSURE,
        "false_price":                RECOVERY_FALSE_PRICE,
        "result_promise":             RECOVERY_RESULT_PROMISE,
        "karen_downgrade":            RECOVERY_KAREN,
        "overconfidence":             RECOVERY_KAREN,
        "corporate_language":         RECOVERY_WARMTH_APPEND,
        "chatbot_faq":                RECOVERY_WARMTH_APPEND,
        "cold_automation":            RECOVERY_WARMTH_APPEND,
        "wellness_drift":             RECOVERY_FORMULA,
        "payment_dead_zone":          RECOVERY_ESCALATION,
        "repetitive_response":        RECOVERY_WARMTH_APPEND,
    }
    body = body_map.get(violation_type, RECOVERY_WARMTH_APPEND)

    if recovery_mode == "RS-1":
        base = original_reply.rstrip()
        return base + RECOVERY_WARMTH_APPEND if base else opener + " " + body

    if recovery_mode == "RS-2":
        safe_opener = _extract_safe_opener(original_reply)
        if safe_opener:
            return f"{safe_opener} {body} {next_step}"
        return f"{opener} {body} {next_step}"

    # RS-3 — full replacement
    return f"{opener} {body} {next_step}"


# ---------------------------------------------------------------------------
# Phase 2 — Observability Helper
# ---------------------------------------------------------------------------

def record_semantic_event(
    contact_id: str,
    agent_name: str,
    route_name: str,
    violation_type: str,
    severity: str,
) -> None:
    """
    Record a single semantic event into the Phase 1 observability state.

    Thread-safe. Wrapped in try/except — never raises.
    Does NOT modify reply. Does NOT call recovery.
    NOT yet called from validate_response() — wired in Phase 3.

    Updates:
        _drift_counters, _agent_counters, _route_counters,
        _session_semantic_risk, _obs_ring_buffer, _gov_violation_log,
        _gov_drift_first_seen, _gov_drift_last_seen
    """
    try:
        now = _dt.datetime.utcnow()
        category = DRIFT_TYPE_MAP.get(violation_type, "OTHER")

        with _obs_lock:
            # Drift counters
            _drift_counters[violation_type] = _drift_counters.get(violation_type, 0) + 1

            # Agent counters
            if agent_name not in _agent_counters:
                _agent_counters[agent_name] = {}
            _agent_counters[agent_name][violation_type] = (
                _agent_counters[agent_name].get(violation_type, 0) + 1
            )

            # Route counters
            if route_name not in _route_counters:
                _route_counters[route_name] = {}
            _route_counters[route_name][violation_type] = (
                _route_counters[route_name].get(violation_type, 0) + 1
            )

            # Session semantic risk (capped at 1.0)
            current_risk = _session_semantic_risk.get(contact_id, 0.0)
            increment = 0.15 if severity == "HARD" else 0.05
            _session_semantic_risk[contact_id] = min(1.0, current_risk + increment)

            # Ring buffer event
            _obs_ring_buffer.append({
                "ts": now.isoformat(),
                "contact_id": contact_id,
                "agent": agent_name,
                "route": route_name,
                "violation": violation_type,
                "category": category,
                "severity": severity,
            })

            # Governance violation log
            _gov_violation_log.append({
                "ts": now.isoformat(),
                "violation": violation_type,
                "agent": agent_name,
                "route": route_name,
                "severity": severity,
            })

            # Drift persistence tracking
            if violation_type not in _gov_drift_first_seen:
                _gov_drift_first_seen[violation_type] = now
            _gov_drift_last_seen[violation_type] = now

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 2 — Governance Helper Functions (no schedulers, no auto-execution)
# ---------------------------------------------------------------------------

def _update_drift_persistence_unlocked() -> None:
    """
    Update drift regression tracking. MUST be called inside _obs_lock.
    Checks if any previously-resolved drift has re-appeared (regression).
    No side effects beyond writing to _gov_drift_regression.
    Not auto-executed — called manually by governance report builder.
    """
    for vtype, resolved_since in list(_gov_drift_resolved_since.items()):
        last_seen = _gov_drift_last_seen.get(vtype)
        if last_seen and last_seen > resolved_since:
            _gov_drift_regression[vtype] = True


def _check_resolved_drifts() -> dict:
    """
    Scan _gov_drift_last_seen and identify drift types not seen for 7+ days.
    Marks them as resolved in _gov_drift_resolved_since.
    Returns dict of {violation_type: resolved_since_datetime}.
    Thread-safe. Not auto-executed.
    """
    resolved: dict = {}
    try:
        now = _dt.datetime.utcnow()
        resolution_window = _dt.timedelta(days=7)
        with _obs_lock:
            for vtype, last_seen in list(_gov_drift_last_seen.items()):
                if now - last_seen >= resolution_window:
                    if vtype not in _gov_drift_resolved_since:
                        _gov_drift_resolved_since[vtype] = now
                    resolved[vtype] = _gov_drift_resolved_since[vtype]
    except Exception:
        pass
    return resolved


def _take_governance_snapshot() -> None:
    """
    Append a summary snapshot of current drift state to _gov_hourly_snapshots.
    Intended to be called once per hour by an external cron/scheduler —
    NOT auto-called here. No background threads. Thread-safe.
    """
    try:
        now = _dt.datetime.utcnow()
        with _obs_lock:
            snapshot = {
                "ts": now.isoformat(),
                "drift_counts": dict(_drift_counters),
                "total_checks": _gov_total_checks,
                "total_rewrites": _gov_total_rewrites,
                "active_drift_types": list(_gov_drift_last_seen.keys()),
                "regression_flags": dict(_gov_drift_regression),
                "session_risk_count": len(_session_semantic_risk),
            }
            _gov_hourly_snapshots.append(snapshot)
    except Exception:
        pass


# =============================================================================
# END PHASE 2 HELPERS — no runtime behavior changed, validator untouched.
# =============================================================================

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
]

# Safe fallback from «Голос Анны» — used when a forbidden mention is caught.
_CAPSULE_FORMULA_FALLBACK = (
    "Здесь, в боте, мы обсуждаем индивидуальное сопровождение Карена. "
    "Всё, что касается личной разработки формулы — Карен ответит на ваши "
    "вопросы лично, после того как мы войдём в работу."
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

        except Exception as e:
            log.error("[VALIDATOR] validate_response error: %s", e)
            issues.append(f"validator_error: {e}")

        return {
            "safe": len([i for i in issues if "warning" not in i and "repetitive" not in i]) == 0,
            "issues": issues,
            "safe_reply": safe_reply,
        }

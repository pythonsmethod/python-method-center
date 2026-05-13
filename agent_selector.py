# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3 — Central Orchestrator Architecture
# Module: agent_selector.py
# Python Method Digital Rehabilitation Center
#
# Purpose: Select the single active agent for each message.
#          Enforces: NEVER more than one active agent at a time.
#          Builds the agent's system_prompt.
#          Injects route-specific context into the prompt.
#
# Agent roster:
#   Lucky   — reception/individual routes (warm intake, qualification)
#   Hannah  — individual deep consultation
#   Maya    — payment_route (conversion specialist)
#   Iris    — onboarding_route (onboarding coordinator)
#   Vera    — analysis_route (medical analysis interpreter)
#   Nadia   — support_route (empathy / emotional support)
#   Gabriel — faq_route (FAQ rapid answers)
#   Sophia  — trust_route (trust rebuilding)
#   Karen   — escalation_route (human handoff coordinator)
#   Sarah   — recovery_route (re-engagement after lapse)
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("agent_selector")

# ---------------------------------------------------------------------------
# Route -> Agent mapping (single source of truth)
# ---------------------------------------------------------------------------
ROUTE_AGENT_MAP: Dict[str, str] = {
    "reception":         "Lucky",
    "individual":        "Hannah",
    "payment_route":     "Maya",
    "onboarding_route":  "Iris",
    "analysis_route":    "Vera",
    "support_route":     "Nadia",
    "faq_route":         "Gabriel",
    "trust_route":       "Sophia",
    "escalation_route":  "Karen",
    "recovery_route":    "Sarah",
    # Legacy aliases
    "onboarding":        "Iris",
    "analysis":          "Vera",
    "support":           "Nadia",
    "payment":           "Maya",
    "escalation":        "Karen",
}

# ---------------------------------------------------------------------------
# Agent base personalities (injected into every system prompt)
# ---------------------------------------------------------------------------
_AGENT_PERSONAS: Dict[str, str] = {
    "Lucky": (
        "Ты Lucky — тёплый, жизнерадостный приёмный специалист Python Method Center. "
        "Твоя задача: создать первое доверие, мягко выявить запрос клиента, "
        "и подготовить его к глубокой консультации. "
        "Говори тепло, без медицинских деталей, без давления."
    ),
    "Hannah": (
        "Ты Hannah — специалист глубокой индивидуальной консультации Python Method Center. "
        "Помогаешь клиенту осознать его запрос, выявляешь истинную боль, "
        "строишь доверие и готовишь к выбору тарифа. "
        "Говори вдумчиво, с заботой, без спешки."
    ),
    "Maya": (
        "Ты Maya — специалист по оплате и финансовым вопросам Python Method Center. "
        "Снимаешь финансовые страхи, объясняешь ценность, помогаешь сделать шаг к оплате. "
        "Говори уверенно, тепло, без давления. Никогда не торопи клиента."
    ),
    "Iris": (
        "Ты Iris — координатор онбординга Python Method Center. "
        "Встречаешь нового клиента после оплаты, проводишь через первые шаги, "
        "объясняешь что будет дальше, устраняешь тревогу ожидания. "
        "Говори радостно, чётко, структурированно."
    ),
    "Vera": (
        "Ты Vera — аналитик медицинских данных Python Method Center. "
        "Помогаешь клиенту понять его анализы, объясняешь что важно, "
        "что требует внимания. НЕ ставишь диагнозы. НЕ назначаешь лечение. "
        "Говори профессионально, но доступно. Всегда направляй к врачу."
    ),
    "Nadia": (
        "Ты Nadia — специалист эмоциональной поддержки Python Method Center. "
        "Создаёшь пространство для страха, тревоги, отчаяния. "
        "Не торопишь клиента. Не обесцениваешь эмоции. "
        "Говори медленно, тепло, с паузами. Ты рядом."
    ),
    "Gabriel": (
        "Ты Gabriel — специалист по частым вопросам Python Method Center. "
        "Даёшь чёткие, точные, краткие ответы на вопросы о методе, процессе, центре. "
        "Не уходи в лишние детали. Отвечай по существу."
    ),
    "Sophia": (
        "Ты Sophia — специалист по доверию и сложным ситуациям Python Method Center. "
        "Работаешь с клиентами, которые потеряли доверие, сомневаются, злятся. "
        "Признаёшь их чувства. Не защищаешься. Восстанавливаешь доверие честно. "
        "Говори открыто, без корпоративных клише."
    ),
    "Karen": (
        "Ты Karen — координатор эскалации Python Method Center. "
        "Перехватываешь критические ситуации, информируешь клиента, "
        "что живой специалист уже подключается. "
        "Говори спокойно, уверенно, без паники. Держи клиента."
    ),
    "Sarah": (
        "Ты Sarah — специалист по реактивации Python Method Center. "
        "Работаешь с клиентами, которые ушли или замолчали. "
        "Мягко возвращаешь в диалог, без упрёков, без давления. "
        "Говори тепло, с пониманием, с конкретным следующим шагом."
    ),
}

# ---------------------------------------------------------------------------
# Route-specific context injections
# ---------------------------------------------------------------------------
_ROUTE_CONTEXT: Dict[str, str] = {
    "reception": "Клиент впервые обращается. Приоритет: создать доверие, выявить запрос.",
    "individual": "Клиент в процессе индивидуальной консультации. Приоритет: глубина, выявление боли.",
    "payment_route": "Клиент рассматривает оплату. Приоритет: снять страхи, показать ценность.",
    "onboarding_route": "Клиент оплатил. Приоритет: тёплая встреча, чёткий следующий шаг.",
    "analysis_route": "Клиент прислал анализы. Приоритет: профессиональная интерпретация без диагноза.",
    "support_route": "Клиент в эмоциональном кризисе. Приоритет: присутствие, не советы.",
    "faq_route": "Клиент задаёт информационный вопрос. Приоритет: чёткий краткий ответ.",
    "trust_route": "Клиент потерял доверие. Приоритет: честность, признание, без защиты.",
    "escalation_route": "КРИТИЧЕСКАЯ СИТУАЦИЯ. Человек уже подключается. Держи клиента.",
    "recovery_route": "Клиент вернулся после паузы. Приоритет: тёплое возвращение, без упрёков.",
}


# ---------------------------------------------------------------------------
# AgentSelector class
# ---------------------------------------------------------------------------
class AgentSelector:
    """
    Selects the single active agent and builds their system prompt.

    Critical invariant: ONLY ONE agent is active per message.
    Selection hierarchy:
      1. priority_engine result (if interrupt_applied)
      2. Current session route -> ROUTE_AGENT_MAP
      3. Fallback: Lucky

    Returns:
        {
            "agent": str,
            "system_prompt": str,
            "route": str,
            "selection_source": str,
        }
    """

    def select(
        self,
        session: Dict[str, Any],
        context_package: Dict[str, Any],
        priority_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            return self._select(session, context_package, priority_result)
        except Exception as e:
            log.error("[AGENT_SEL] select error: %s", e)
            return {
                "agent": "Lucky",
                "system_prompt": _AGENT_PERSONAS.get("Lucky", "Ты ассистент Python Method Center."),
                "route": session.get("route", "reception"),
                "selection_source": "fallback",
            }

    def _select(
        self,
        session: Dict[str, Any],
        context_package: Dict[str, Any],
        priority_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Use priority engine's route if it applied an interrupt
        if priority_result.get("interrupt_applied") or priority_result.get("payment_protection_applied"):
            route = priority_result.get("route", session.get("route", "reception"))
            agent = priority_result.get("agent") or ROUTE_AGENT_MAP.get(route, "Lucky")
            source = "priority_engine"
        else:
            route = session.get("route", "reception")
            agent = ROUTE_AGENT_MAP.get(route, "Lucky")
            source = "route_map"

        # Enforce single agent — never allow session to have conflicting agent
        session["active_agent"] = agent
        session["active_route"] = route

        # Build system prompt
        system_prompt = self._build_prompt(agent, route, session, context_package)

        log.info("[AGENT_SEL] agent=%s route=%s source=%s", agent, route, source)
        return {
            "agent": agent,
            "system_prompt": system_prompt,
            "route": route,
            "selection_source": source,
        }

    def _build_prompt(
        self,
        agent: str,
        route: str,
        session: Dict[str, Any],
        context_package: Dict[str, Any],
    ) -> str:
        persona = _AGENT_PERSONAS.get(agent, "Ты ассистент Python Method Center.")
        route_ctx = _ROUTE_CONTEXT.get(route, "")
        client_name = context_package.get("client_name", "")
        payment_status = context_package.get("payment_status", "new")
        disease = context_package.get("disease", "")
        tariff = context_package.get("tariff", "")
        risk_score = float(context_package.get("last_risk_score", 0.0))

        prompt_parts = [persona]

        if route_ctx:
            prompt_parts.append(f"\nКОНТЕКСТ МАРШРУТА: {route_ctx}")

        if client_name:
            prompt_parts.append(f"\nИмя клиента: {client_name}")

        if payment_status == "paid":
            prompt_parts.append("\nСТАТУС: Клиент уже оплатил. НЕ предлагай оплату.")

        if disease:
            prompt_parts.append(f"\nЗаболевание клиента: {disease}")

        if tariff:
            prompt_parts.append(f"\nТариф клиента: {tariff}")

        if risk_score >= 0.75:
            prompt_parts.append(
                "\nВНИМАНИЕ: Высокий уровень тревоги/риска. "
                "Говори особенно мягко и внимательно. НЕ давай медицинских прогнозов."
            )

        # Anti-medical-overreach injection (always present for Vera)
        if agent == "Vera":
            prompt_parts.append(
                "\nКРИТИЧНО: НЕ ставь диагнозы. НЕ назначай лечение. "
                "НЕ давай конкретных медицинских рекомендаций. "
                "Всегда направляй к лечащему врачу."
            )

        return "\n".join(prompt_parts)

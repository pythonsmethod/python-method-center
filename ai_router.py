# -*- coding: utf-8 -*-
# ai_router.py - AI Provider Router for Python Method Center
# Routes requests between Anthropic Claude and OpenAI GPT based on task type
#
# ROUTING LOGIC:
#   Claude  -> emotional dialogue, client communication, empathy, trust, objections
#   GPT     -> system logic, routing, classification, DB, Stripe, SendPulse, summaries

import os
import logging
import json
from anthropic import Anthropic
from openai import OpenAI

log = logging.getLogger("ai_router")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# ─── Clients ─────────────────────────────────────────────────────────────────
_anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
_openai_key    = os.environ.get("OPENAI_API_KEY")

claude_client = Anthropic(api_key=_anthropic_key) if _anthropic_key else None
gpt_client    = OpenAI(api_key=_openai_key)       if _openai_key    else None

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
GPT_MODEL    = "gpt-4o"

# ─── Route classification ─────────────────────────────────────────────────────

# Agent routes that always use Claude (live human dialogue)
CLAUDE_ROUTES = {
    "reception",       # Lucky — first contact
    "navigation",      # Gabriel — orientation
    "faq",             # Sarah — questions
    "prevention",      # Sophia — prevention path
    "individual",      # Hannah — individual collection
    "formula",         # Maya — formula
    "onboarding",      # Iris — post-payment onboarding
    "analysis",        # Vera — analysis review
    "support",         # Nadia — ongoing support
    "escalation",      # escalation to Karen
    "tariff_recommend",# Lucky tariff stage
}

# Agent routes that use GPT (system / structural logic)
GPT_ROUTES = {
    "classify",        # request classification
    "route_decision",  # which route to send client to
    "summary_karen",   # case summary for Karen
    "summary_anna",    # summary for Anna
    "status_check",    # client status determination
    "stripe_handler",  # Stripe webhook logic
    "sendpulse_sync",  # SendPulse automation
    "db_write",        # database operations
    "memory_update",   # client memory update
}

# Emotional/trust keywords that force Claude even in ambiguous cases
EMOTIONAL_KEYWORDS = [
    "боюсь", "страшно", "тревог", "сомнева", "не уверен", "не уверена",
    "помогите", "не знаю", "как быть", "что делать", "плохо", "больно",
    "устал", "устала", "надоело", "хочу", "мне нужно", "переживаю",
    "доверя", "оплатить", "оплачивать", "дорого", "нет денег",
    "суицид", "не хочу жить", "смысла нет", "безнадёжно",
    "рак", "диагноз", "лечение", "анализы", "врач", "операция",
    "привет", "здравствуй", "добрый", "спасибо", "пожалуйста",
]

# System/technical keywords that suggest GPT
SYSTEM_KEYWORDS = [
    "webhook", "stripe", "payment", "checkout", "invoice",
    "sendpulse", "contact_id", "session_id", "database",
    "classify", "route", "status", "stage", "next_step",
    "summary", "резюме", "сводка", "досье",
]


def classify_request(task_type: str, message: str = "", route: str = "", context: dict = None) -> str:
    """
    Determine which AI provider to use.
    
    Returns: "claude" or "gpt"
    
    Decision tree:
    1. If task_type is in GPT_ROUTES → GPT
    2. If task_type is in CLAUDE_ROUTES → Claude
    3. If message contains emotional keywords → Claude
    4. If message contains system keywords → GPT
    5. Default → Claude (safe fallback for anything client-facing)
    """
    context = context or {}

    # 1. Explicit GPT task
    if task_type in GPT_ROUTES:
        return "gpt"

    # 2. Explicit Claude task (agent route)
    if task_type in CLAUDE_ROUTES or route in CLAUDE_ROUTES:
        return "claude"

    msg_lower = message.lower() if message else ""

    # 3. Emotional / human message → Claude
    for kw in EMOTIONAL_KEYWORDS:
        if kw in msg_lower:
            return "claude"

    # 4. System/technical keyword → GPT
    for kw in SYSTEM_KEYWORDS:
        if kw in msg_lower:
            return "gpt"

    # 5. Safe default
    return "claude"


def log_routing(provider: str, task_type: str, reason: str, route: str = "",
                stage: str = "", next_step: str = "", message_preview: str = ""):
    """Structured routing log entry."""
    preview = message_preview[:80].replace("\n", " ") if message_preview else ""
    log.info(
        f"[AI_ROUTER] provider={provider.upper()} | task={task_type} | "
        f"route={route or '-'} | stage={stage or '-'} | "
        f"next_step={next_step or '-'} | reason={reason} | "
        f"msg_preview={repr(preview)}"
    )


# ─── Claude call ─────────────────────────────────────────────────────────────

def ask_claude(system_prompt: str, messages: list, max_tokens: int = 600,
               task_type: str = "dialogue", route: str = "",
               stage: str = "", next_step: str = "") -> str:
    """
    Call Anthropic Claude. Used for all live client dialogue.
    Raises RuntimeError if Claude client is not configured.
    """
    if not claude_client:
        raise RuntimeError(
            "Claude client not configured. Check ANTHROPIC_API_KEY in Railway."
        )

    reason = f"Claude route: {route or task_type}"
    log_routing("claude", task_type, reason, route=route,
                stage=stage, next_step=next_step,
                message_preview=messages[-1]["content"] if messages else "")

    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text.strip()


# ─── GPT call ────────────────────────────────────────────────────────────────

def ask_gpt(system_prompt: str, messages: list, max_tokens: int = 600,
            task_type: str = "system", route: str = "",
            stage: str = "", next_step: str = "",
            response_format: str = "text") -> str:
    """
    Call OpenAI GPT. Used for system logic, classification, summaries.
    Falls back to Claude if GPT client is not configured.
    """
    if not gpt_client:
        log.warning(
            "[AI_ROUTER] GPT not configured (no OPENAI_API_KEY). "
            "Falling back to Claude for task: %s", task_type
        )
        if not claude_client:
            raise RuntimeError("Neither Claude nor GPT client is configured.")
        return ask_claude(system_prompt, messages, max_tokens,
                          task_type=task_type, route=route,
                          stage=stage, next_step=next_step)

    reason = f"GPT system task: {task_type}"
    log_routing("gpt", task_type, reason, route=route,
                stage=stage, next_step=next_step,
                message_preview=messages[-1]["content"] if messages else "")

    # Build GPT messages: prepend system
    gpt_messages = [{"role": "system", "content": system_prompt}] + messages

    kwargs = dict(
        model=GPT_MODEL,
        max_tokens=max_tokens,
        messages=gpt_messages,
    )
    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}

    response = gpt_client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()


# ─── Smart router ─────────────────────────────────────────────────────────────

def ask_ai(system_prompt: str, messages: list, max_tokens: int = 600,
           task_type: str = "auto", route: str = "",
           stage: str = "", next_step: str = "",
           message: str = "") -> str:
    """
    Universal AI call. Automatically routes to Claude or GPT based on task.
    
    Use this for any call where the provider choice should be automatic.
    For explicit provider control use ask_claude() or ask_gpt() directly.
    """
    msg_for_classify = message or (messages[-1]["content"] if messages else "")
    provider = classify_request(task_type, msg_for_classify, route)

    if provider == "gpt":
        return ask_gpt(system_prompt, messages, max_tokens,
                       task_type=task_type, route=route,
                       stage=stage, next_step=next_step)
    else:
        return ask_claude(system_prompt, messages, max_tokens,
                          task_type=task_type, route=route,
                          stage=stage, next_step=next_step)


# ─── Specialized helpers ─────────────────────────────────────────────────────

def gpt_classify_route(user_message: str, history_summary: str = "") -> dict:
    """
    Use GPT to classify a user message and determine the next route.
    Returns dict: {"route": str, "reason": str, "confidence": float}
    """
    system = (
        "You are a routing classifier for Python Method Center bot. "
        "Analyze the user message and return JSON with keys: "
        "'route' (one of: reception, navigation, faq, prevention, individual, "
        "formula, onboarding, analysis, support, escalation, tariff_recommend), "
        "'reason' (brief explanation in Russian), "
        "'confidence' (0.0-1.0). "
        "Return ONLY valid JSON, no markdown."
    )
    msgs = [{"role": "user", "content": f"Message: {user_message}\nHistory: {history_summary}"}]

    log_routing("gpt", "route_decision", "GPT classifying route",
                message_preview=user_message)

    if not gpt_client:
        log.warning("[AI_ROUTER] GPT not available for route classification, returning default.")
        return {"route": "reception", "reason": "GPT unavailable, default", "confidence": 0.5}

    try:
        raw = ask_gpt(system, msgs, max_tokens=200,
                      task_type="route_decision", response_format="json")
        return json.loads(raw)
    except Exception as e:
        log.error("[AI_ROUTER] gpt_classify_route error: %s", e)
        return {"route": "reception", "reason": f"error: {e}", "confidence": 0.0}


def gpt_generate_summary(history: list, summary_type: str = "karen") -> str:
    """
    Use GPT to generate internal case summary for Karen or Anna.
    summary_type: "karen" or "anna"
    """
    history_text = "\n".join([
        f"{'Клиент' if m['role'] == 'user' else 'Бот'}: {m['content']}"
        for m in history[-20:]
    ])

    if summary_type == "karen":
        system = (
            "Ты — медицинский координатор. Составь краткое профессиональное досье "
            "клиента для реабилитолога Карена. Только на основе переписки. "
            "Структура: имя, диагноз/стадия, текущее лечение, ключевые жалобы, "
            "важные детали. Без выводов и рекомендаций. Максимум 300 слов. "
            "Язык: русский."
        )
    else:
        system = (
            "Составь краткую оперативную сводку для куратора Анны. "
            "Ситуация клиента, статус, что нужно сделать. "
            "Максимум 150 слов. Язык: русский."
        )

    msgs = [{"role": "user", "content": history_text}]
    log_routing("gpt", "summary_karen" if summary_type == "karen" else "summary_anna",
                f"GPT generating {summary_type} summary")

    return ask_gpt(system, msgs, max_tokens=400,
                   task_type=f"summary_{summary_type}")


def gpt_analyze_client_status(history: list, db_data: dict = None) -> dict:
    """
    Use GPT to analyze client status from history and DB data.
    Returns: {"status": str, "stage": str, "next_step": str, "flags": list}
    """
    history_text = "\n".join([
        f"{'Клиент' if m['role'] == 'user' else 'Бот'}: {m['content']}"
        for m in history[-15:]
    ])
    db_str = json.dumps(db_data, ensure_ascii=False) if db_data else "нет данных"

    system = (
        "Проанализируй историю клиента и верни JSON: "
        "{'status': 'new|active|pending_payment|paid|onboarding|analysis|support|escalated', "
        "'stage': string, 'next_step': string, "
        "'flags': ['emotional', 'crisis', 'payment_ready', 'needs_analyses', ...]}. "
        "Только JSON, без markdown."
    )
    msgs = [{"role": "user", "content": f"История:\n{history_text}\n\nДанные БД: {db_str}"}]

    log_routing("gpt", "status_check", "GPT analyzing client status")

    if not gpt_client:
        return {"status": "unknown", "stage": "-", "next_step": "-", "flags": []}

    try:
        raw = ask_gpt(system, msgs, max_tokens=300,
                      task_type="status_check", response_format="json")
        return json.loads(raw)
    except Exception as e:
        log.error("[AI_ROUTER] gpt_analyze_client_status error: %s", e)
        return {"status": "error", "stage": "-", "next_step": "-", "flags": []}


# ─── Health check ─────────────────────────────────────────────────────────────

def health_check() -> dict:
    """
    Check which AI providers are available.
    Returns dict with status of each provider.
    """
    result = {
        "claude": {"available": bool(claude_client), "model": CLAUDE_MODEL},
        "gpt":    {"available": bool(gpt_client),    "model": GPT_MODEL},
    }
    log.info("[AI_ROUTER] Health check: %s", result)
    return result

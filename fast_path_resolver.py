"""
fast_path_resolver.py - Instant Responses for Simple Intents
Python Method Center - PHASE 3.1A

Bypasses full orchestrator/LLM for well-known simple intents.
Response time: <100ms instead of 3-8 seconds.

Fast paths:
  - greeting         -> friendly hello response
  - price_question   -> redirect to pricing info
  - payment_question -> direct to payment route
  - delivery_question-> programme delivery info
  - what_next        -> next step reminder
  - human_request    -> escalation trigger
  - post_payment_ack -> payment confirmation
  - faq_simple       -> hardcoded FAQ answers
"""

import re
import logging
from typing import Optional, Dict, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class FastPathIntent(str, Enum):
    GREETING = "greeting"
    PRICE_QUESTION = "price_question"
    PAYMENT_QUESTION = "payment_question"
    DELIVERY_QUESTION = "delivery_question"
    WHAT_NEXT = "what_next"
    HUMAN_REQUEST = "human_request"
    POST_PAYMENT_ACK = "post_payment_ack"
    FAQ_DURATION = "faq_duration"
    FAQ_FORMAT = "faq_format"
    FAQ_GUARANTEE = "faq_guarantee"
    THANKS = "thanks"
    NONE = "none"


# Pattern sets for each fast-path intent
# All patterns are lowercase, matched against lowercased input
FAST_PATH_PATTERNS: Dict[FastPathIntent, list] = {

    FastPathIntent.GREETING: [
        r"^(привет|здравствуй|добрый|доброе|hello|hi|хай|ку|hey)");
        r"^(доброго|доброй)");
        r"^(рад|рада) (вас|тебя) (видеть|слышать)");
    ],

    FastPathIntent.PRICE_QUESTION: [
        r"сколько (это )?стоит";
        r"какая цена";
        r"цена (программы|курса)?";
        r"сколько (стоит|стоят|платить|нужно заплатить)";
        r"прайс";
        r"тарифы?";
        r"стоимость";
    ],

    FastPathIntent.PAYMENT_QUESTION: [
        r"как (оплатить|заплатить|оплачивать)";
        r"способ (оплаты|платежа)";
        r"картой (платить)?";
        r"перевод (денег)?";
        r"оплата";
        r"stripe";
        r"реквизит";
    ],

    FastPathIntent.DELIVERY_QUESTION: [
        r"как (проходит|устроена|работает) (программа|курс)";
        r"что (входит|включает) в программу";
        r"формат (занятий|работы|сессий)";
        r"онлайн (или|/|vs) оффлайн";
        r"онлайн$";
        r"где (проходит|проводится)";
    ],

    FastPathIntent.WHAT_NEXT: [
        r"что (дальше|делать|следующее|теперь)";
        r"следующий шаг";
        r"что мне делать";
        r"с чего (начать|начинать|начала|начало)";
        r"продолжаем?";
    ],

    FastPathIntent.HUMAN_REQUEST: [
        r"(поговорить|общаться) с (человеком|живым)";
        r"живой (человек|специалист|консультант)";
        r"реальный человек";
        r"не робот";
        r"оператор";
        r"куратор";
        r"настоящий (человек|специалист)";
    ],

    FastPathIntent.POST_PAYMENT_ACK: [
        r"(я )?оплатил[аи]?";
        r"оплата (прошла|прошел|выполнена)";
        r"оплатила";
        r"деньги (ушли|перевела?|отправила?)";
        r"квитанция";
        r"чек (есть|прислать)?";
        r"payment (done|complete|success)";
    ],

    FastPathIntent.FAQ_DURATION: [
        r"сколько (длится|идет|длиться|продолжается)";
        r"длительность (программы|курса)";
        r"сколько (времени|месяцев|недель|дней)";
        r"как долго";
    ],

    FastPathIntent.FAQ_FORMAT: [
        r"это (курс|тренинг|программа|марафон)";
        r"что (такое|представляет) python method";
        r"про что (программа|курс)";
        r"расскажи (о|про) программ";
    ],

    FastPathIntent.FAQ_GUARANTEE: [
        r"гарантия";
        r"если не поможет";
        r"возврат (денег|средств)?";
        r"рефанд";
    ],

    FastPathIntent.THANKS: [
        r"^(спасибо|благодарю|спс|thanks|thank you|ок|окей|хорошо|понял[аи]?|ясно|ладно|good)\b";
    ],
}


# Fast-path responses per intent
# These are shown IMMEDIATELY without LLM call
FAST_PATH_RESPONSES: Dict[FastPathIntent, str] = {

    FastPathIntent.GREETING:
        "Привет! Я здесь, чтобы помочь вам разобраться с программой Python Method. "
        "Что вас интересует?",

    FastPathIntent.PRICE_QUESTION:
        "Стоимость программы зависит от выбранного формата. Хотите, я расскажу подробнее "
        "или сразу перейдём к оформлению?",

    FastPathIntent.PAYMENT_QUESTION:
        "Оплата проходит онлайн через защищённую форму Stripe (карта). Я могу прислать "
        "вам ссылку прямо сейчас — вам это удобно?",

    FastPathIntent.DELIVERY_QUESTION:
        "Программа проходит онлайн — встречи, материалы и поддержка доступны из любой точки. "
        "Хотите узнать подробнее о формате?",

    FastPathIntent.WHAT_NEXT:
        "Сейчас я уточню, на каком этапе вы находитесь, и подскажу следующий шаг. "
        "Один момент...",

    FastPathIntent.HUMAN_REQUEST:
        "Понимаю. Сейчас я передам ваш запрос куратору — он свяжется с вами в ближайшее время. "
        "Что именно вы хотели бы обсудить с человеком?",

    FastPathIntent.POST_PAYMENT_ACK:
        "Отлично, вижу вашу оплату! Сейчас проверю статус и дам вам доступ к следующему шагу. "
        "Буквально минуту...",

    FastPathIntent.FAQ_DURATION:
        "Программа Python Method рассчитана на несколько месяцев — точные сроки зависят от формата. "
        "Хотите узнать подробности?",

    FastPathIntent.FAQ_FORMAT:
        "Python Method — это авторская программа восстановления, основанная на нейронаучных "
        "и психологических методах работы с зависимостью. Рассказать подробнее?",

    FastPathIntent.FAQ_GUARANTEE:
        "Мы верим в нашу программу и готовы обсудить ваши ожидания. Расскажите, что вас беспокоит?",

    FastPathIntent.THANKS:
        "Пожалуйста! Если появятся вопросы — я всегда здесь.",
}


class FastPathResolver:
    """
    Resolves simple intents without LLM call.
    Returns (intent, response) or (NONE, None) if no fast path matches.
    """

    def __init__(self):
        # Pre-compile all patterns
        self._compiled: Dict[FastPathIntent, list] = {}
        for intent, patterns in FAST_PATH_PATTERNS.items():
            self._compiled[intent] = [re.compile(p, re.IGNORECASE) for p in patterns]
        logger.info("[FAST_PATH] FastPathResolver initialized with %d intents",
                    len(self._compiled))

    def resolve(self, text: str, session: Optional[Dict] = None) -> Tuple[FastPathIntent, Optional[str]]:
        """
        Attempt to resolve text to a fast-path response.
        Returns (intent, response_text) or (NONE, None).
        Session context used to block fast paths where deeper context required.
        """
        if not text or not text.strip():
            return FastPathIntent.NONE, None

        text_clean = text.strip().lower()

        # Do NOT fast-path if user is in mid-session deep state
        if session:
            route = session.get("current_route", "")
            stage = session.get("current_stage", "")
            # Block fast paths for sessions in active emotional/support work
            if route in ("support_route", "recovery_route") and stage not in ("entry", ""):
                logger.debug("[FAST_PATH] Blocked for deep session route=%s", route)
                return FastPathIntent.NONE, None

        # Try each intent in priority order
        priority_order = [
            FastPathIntent.HUMAN_REQUEST,    # Always highest priority
            FastPathIntent.POST_PAYMENT_ACK, # Payment signals are critical
            FastPathIntent.WHAT_NEXT,        # Common and actionable
            FastPathIntent.THANKS,           # Short circuit thanks
            FastPathIntent.GREETING,         # Welcome
            FastPathIntent.PAYMENT_QUESTION,
            FastPathIntent.PRICE_QUESTION,
            FastPathIntent.DELIVERY_QUESTION,
            FastPathIntent.FAQ_DURATION,
            FastPathIntent.FAQ_FORMAT,
            FastPathIntent.FAQ_GUARANTEE,
        ]

        for intent in priority_order:
            patterns = self._compiled.get(intent, [])
            for pattern in patterns:
                if pattern.search(text_clean):
                    response = FAST_PATH_RESPONSES.get(intent)
                    logger.info("[FAST_PATH] Match intent=%s text=%.40r", intent, text)
                    return intent, response

        return FastPathIntent.NONE, None

    def should_use_fast_path(self, text: str, session: Optional[Dict] = None) -> bool:
        """Quick boolean check - does this text have a fast path?"""
        intent, _ = self.resolve(text, session)
        return intent != FastPathIntent.NONE


# Global singleton
fast_path_resolver = FastPathResolver()


def resolve_fast_path(text: str, session: Optional[Dict] = None) -> Tuple[str, Optional[str]]:
    """Public API: returns (intent_name, response_text) or ('none', None)."""
    intent, response = fast_path_resolver.resolve(text, session)
    return intent.value, response

# -*- coding: utf-8 -*-
# Python Method Center - Agents
# Full version - no triple quotes

import os
import json
import re
from anthropic import Anthropic
from ai_router import ask_claude, ask_gpt, gpt_generate_summary, gpt_analyze_client_status, health_check
import httpx
from central_ai_core import build_context_package
from state_engine import analyze as state_analyze
from route_resolver import resolve_route
from auto_router import apply_auto_route
from emotional_overlay import (
    detect_emotional_overlay,
    build_overlay_injection,
    update_overlay_session,
)
from emotional_overlay import (
    detect_emotional_overlay,
    build_overlay_injection,
    update_overlay_session,
)
import threading
import time

NOTIFY_BOT_TOKEN = os.environ.get('NOTIFY_BOT_TOKEN')
KAREN_CHAT_ID = '6181048365'
ANNA_CHAT_ID = '402361257'

def generate_summary(history):

    try:

        if not history:

            return 'История разговора пуста.'

        

        conversation_text = ''

        for msg in history:

            role = 'Клиент' if msg['role'] == 'user' else 'Lucky'

            conversation_text += f'{role}: {msg["content"]}\n\n'

        

        response = client.messages.create(

            model=MODEL,

            max_tokens=2000,

            messages=[{

                'role': 'user',

                'content': f'''Ты — медицинский координатор. Составь профессиональное досье пациента для реабилитолога Карена. Только на основе переписки ниже — ничего не придумывай.

ПЕРЕПИСКА:

{conversation_text}

Оформи строго по этому шаблону:

━━━━━━━━━━━━━━━━━━━━━━

📋 ДОСЬЕ ПАЦИЕНТА

━━━━━━━━━━━━━━━━━━━━━━

👤 ИМЯ: 

🌍 СТРАНА / ГОРОД: 

📞 КАК СВЯЗАТЬСЯ: (username из переписки)

━━━━━━━━━━━━━━━━━━━━━━

🏥 МЕДИЦИНСКАЯ КАРТИНА

━━━━━━━━━━━━━━━━━━━━━━

📋 ДИАГНОЗ: 

📅 КОГДА ПОСТАВЛЕН: 

💊 ТЕКУЩЕЕ ЛЕЧЕНИЕ: 

⚠️ ТЕКУЩЕЕ СОСТОЯНИЕ: 

🔴 ГЛАВНАЯ ПРОБЛЕМА: 

━━━━━━━━━━━━━━━━━━━━━━

🧪 АНАЛИЗЫ

━━━━━━━━━━━━━━━━━━━━━━

(Переведи названия на русский. Таблица: Показатель | Результат | Норма | Статус)

━━━━━━━━━━━━━━━━━━━━━━

💬 ЗАПРОС К КАРЕНУ

━━━━━━━━━━━━━━━━━━━━━━

(Что именно хочет узнать / получить пациент)'''

            }]

        )

        return response.content[0].text.strip()

    except Exception as e:

        return f'Ошибка генерации: {e}'

def send_notification(chat_id, text):
    if not NOTIFY_BOT_TOKEN:
        return
    url = f'https://api.telegram.org/bot{NOTIFY_BOT_TOKEN}/sendMessage'
    try:
        httpx.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}, timeout=10)
    except Exception as e:
        print(f'[NOTIFY ERROR] {e}')

client = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
MODEL = 'claude-sonnet-4-5-20250929'

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get('DATABASE_URL')

sessions = {}  # RAM cache


def _get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')


def _init_db():
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            'CREATE TABLE IF NOT EXISTS pm_sessions ('
            '    contact_id TEXT PRIMARY KEY,'
            "    route TEXT NOT NULL DEFAULT 'reception',"
            "    history JSONB NOT NULL DEFAULT '[]',"
            "    case_summary TEXT NOT NULL DEFAULT '',"
            '    awaiting_confirmation BOOLEAN NOT NULL DEFAULT FALSE,'
            '    first_contact TIMESTAMPTZ DEFAULT NOW(),'
            '    last_contact TIMESTAMPTZ DEFAULT NOW()'
            ')'
        )
        # Central AI Core v2.0 — add new columns if not exist
        for col_sql in [
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS agent_current TEXT NOT NULL DEFAULT 'reception'",
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS risk_score FLOAT NOT NULL DEFAULT 0.0',
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS hang_stage TEXT',
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'new'",
            # State Engine v2.0 columns
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS current_intent TEXT NOT NULL DEFAULT 'question'",
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS current_state TEXT NOT NULL DEFAULT 'new'",
            # Auto-router + overlay + trust columns (Phase 2B/2C)
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS proposed_route TEXT NOT NULL DEFAULT 'reception'",
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS proposed_agent TEXT NOT NULL DEFAULT 'reception'",
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS route_confidence FLOAT NOT NULL DEFAULT 0.0',
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS route_reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS previous_route TEXT NOT NULL DEFAULT 'reception'",
            "ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS transition_reason TEXT NOT NULL DEFAULT ''",
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS route_transition_log JSONB',
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS route_last_switch_msg INTEGER NOT NULL DEFAULT 0',
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS overlay_last_high_msg INTEGER',
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS overlay_consecutive_empathy INTEGER',
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS overlay_history JSONB',
            'ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS trust_entered_at_msg INTEGER NOT NULL DEFAULT 0',
        ]:
            try:
                cur.execute(col_sql)
            except Exception:
                conn.rollback()
        
        conn.commit()
        cur.close()
        conn.close()
        print('[DB] pm_sessions ready')
    except Exception as e:
        print(f'[DB ERROR] init: {e}')


_init_db()


def load_session(contact_id):
    try:
        conn = _get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            'SELECT route, history, case_summary, awaiting_confirmation, '
            'agent_current, risk_score, hang_stage, payment_status, '
            'current_intent, current_state, '
            'proposed_route, proposed_agent, route_confidence, route_reason, '
            'previous_route, transition_reason, route_transition_log, route_last_switch_msg, '
            'overlay_last_high_msg, overlay_consecutive_empathy, overlay_history, '
            'trust_entered_at_msg '
            'FROM pm_sessions WHERE contact_id = %s',
            (str(contact_id),)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {
                'route': row['route'],
                'history': row['history'] if row['history'] else [],
                'case_summary': row['case_summary'] or '',
                'awaiting_confirmation': row['awaiting_confirmation'] or False,
                'agent_current': row.get('agent_current', row['route']),
                'risk_score': float(row.get('risk_score') or 0.0),
                'hang_stage': row.get('hang_stage'),
                'payment_status': row.get('payment_status', 'new'),
                'current_intent': row.get('current_intent', 'question'),
                'current_state':  row.get('current_state', 'new'),
                'proposed_route':   row.get('proposed_route', row['route']),
                'proposed_agent':   row.get('proposed_agent', row['route']),
                'route_confidence': float(row.get('route_confidence') or 0.0),
                'route_reason':     row.get('route_reason', ''),
                'previous_route':        row.get('previous_route', row['route']),
                'transition_reason':     row.get('transition_reason', ''),
                'route_transition_log':  row.get('route_transition_log') or [],
                'route_last_switch_msg': int(row.get('route_last_switch_msg') or 0),
                'overlay_last_high_msg':       int(row.get('overlay_last_high_msg') or 0),
                'overlay_consecutive_empathy': int(row.get('overlay_consecutive_empathy') or 0),
                'overlay_history':             row.get('overlay_history') or [],
                'trust_entered_at_msg':         int(row.get('trust_entered_at_msg') or 0),
            }
    except Exception as e:
        print(f'[DB ERROR] load: {e}')
    return {'route': 'reception', 'history': [], 'awaiting_confirmation': False, 'case_summary': '', 'client_data': {'name': '', 'country': '', 'telegram_id': str(contact_id), 'tariff': ''}}


def save_session(contact_id, session):
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO pm_sessions '
            '(contact_id, route, history, case_summary, awaiting_confirmation, last_contact, '
            'agent_current, risk_score, hang_stage, payment_status, '
            'current_intent, current_state, '
            'proposed_route, proposed_agent, route_confidence, route_reason, '
            'previous_route, transition_reason, route_transition_log, route_last_switch_msg, '
            'overlay_last_high_msg, overlay_consecutive_empathy, overlay_history, trust_entered_at_msg) '
            'VALUES (%s, %s, %s::jsonb, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s) '
            'ON CONFLICT (contact_id) DO UPDATE SET '
            '    route = EXCLUDED.route, '
            '    history = EXCLUDED.history, '
            '    case_summary = EXCLUDED.case_summary, '
            '    awaiting_confirmation = EXCLUDED.awaiting_confirmation, '
            '    last_contact = NOW(), '
            '    agent_current = EXCLUDED.agent_current, '
            '    risk_score = EXCLUDED.risk_score, '
            '    hang_stage = EXCLUDED.hang_stage, '
            '    payment_status = EXCLUDED.payment_status, '
            '    current_intent = EXCLUDED.current_intent, '
            '    current_state  = EXCLUDED.current_state, '
            '    proposed_route   = EXCLUDED.proposed_route, '
            '    proposed_agent   = EXCLUDED.proposed_agent, '
            '    route_confidence = EXCLUDED.route_confidence, '
            '    route_reason     = EXCLUDED.route_reason, '
            '    previous_route       = EXCLUDED.previous_route, '
            '    transition_reason    = EXCLUDED.transition_reason, '
            '    route_transition_log = EXCLUDED.route_transition_log, '
            '    route_last_switch_msg = EXCLUDED.route_last_switch_msg, '
            '    overlay_last_high_msg = EXCLUDED.overlay_last_high_msg, '
            '    overlay_consecutive_empathy = EXCLUDED.overlay_consecutive_empathy, '
            '    overlay_history = EXCLUDED.overlay_history, '
            '    trust_entered_at_msg = EXCLUDED.trust_entered_at_msg',
            (
                str(contact_id),
                session.get('route', 'reception'),
                json.dumps(session.get('history', []), ensure_ascii=False),
                session.get('case_summary', ''),
                session.get('awaiting_confirmation', False),
                session.get('agent_current', session.get('route', 'reception')),
                float(session.get('risk_score', 0.0)),
                session.get('hang_stage'),
                session.get('payment_status', 'new'),
                session.get('current_intent', 'question'),
                session.get('current_state', 'new'),
                session.get('proposed_route', session.get('route', 'reception')),
                session.get('proposed_agent', session.get('route', 'reception')),
                float(session.get('route_confidence', 0.0)),
                session.get('route_reason', ''),
                session.get('previous_route', session.get('route', 'reception')),
                session.get('transition_reason', ''),
                json.dumps(session.get('route_transition_log', []), ensure_ascii=False),
                int(session.get('route_last_switch_msg', 0)),
                int(session.get('overlay_last_high_msg', 0)),
                int(session.get('overlay_consecutive_empathy', 0)),
                json.dumps(session.get('overlay_history', []), ensure_ascii=False),
                int(session.get('trust_entered_at_msg', 0)),
            )
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'[DB ERROR] save: {e}')


ONCOPSYCHOLOGY = """


"""

BASE_TONE = '\nОБЩИЙ ТОН:\n- Спокойный, тёплый, уважительный\n- Не торопит, не давит, не звучит как продавец или врач\n- Пишет коротко - это Telegram, а не статья\n- Один экран = одна мысль = один следующий шаг\n- В конце сообщения - всегда понятно, что делать дальше\n\nЗАПРЕЩЕНО:\n- Никаких диагнозов\n- Никаких медицинских назначений\n- Никаких обещаний результата\n- Не выдумывать факты\n- Не говорить \"понимаю вашу боль\" - это фальшь\n- Не начинать с \"к сожалению\" / \"к счастью\"\n- Не звучать канцелярски\n\n\nЮРИДИЧЕСКИ ВАЖНО:\n- Никогда не называй Карена \"врачом\", \"доктором\", \"медицинским экспертом\", \"специалистом\" в медицинском смысле.\n- Карен — реабилитолог с 30-летним опытом.\n- Если клиент спрашивает \"он врач?\" — отвечай: \"Карен — реабилитолог с тридцатилетним опытом работы с восстановлением организма.\"\n- Никаких медицинских диагнозов, назначений, прогнозов от имени Карена.'

LUCKY_PROMPT = """Ты — Lucky, ангел-хранитель и проводник в боте Python Method Center.

КТО ТЫ:

Ты встречаешь человека — тепло, спокойно, без давления. Ты не продавец и не врач. Ты проводник к Карену.

ЧТО ТАКОЕ PYTHON METHOD CENTER:

Это реабилитационный центр восстановления организма. Карен — реабилитолог с 30-летним опытом, автор авторской методики восстановления при тяжёлых состояниях, в том числе онкологии. Методика работает параллельно с основным лечением — она помогает организму мобилизовать собственные ресурсы. Карен ведёт каждого клиента индивидуально, на основе анализов. Никаких шаблонов, никаких протоколов — только индивидуальная работа.

КАК ОТВЕЧАТЬ КОГДА ЧЕЛОВЕК ХОЧЕТ УЗНАТЬ О МЕТОДЕ ИЛИ ЦЕНТРЕ:

Отвечай дословно этим текстом:

"Здравствуйте 🌿

Вы попали в цифровой реабилитационный центр Python Method — пространство, где человек может получить сопровождение, структуру и помощь в понимании своего состояния.

Система создана для того, чтобы человек не оставался один среди хаоса информации, страха и непонимания, что делать дальше.

Здесь вы можете:

— узнать о подходе и формате центра
— задать вопросы
— получить сопровождение
— пройти путь профилактики или индивидуального разбора
— получить информацию о формуле и формате участия
— понять, какой следующий шаг подходит именно вам

В основе системы лежит индивидуальный подход. Каждая ситуация рассматривается отдельно, с учётом состояния человека, анализов, текущего лечения и общей картины.

Карен подключается на этапах, где требуется более глубокий индивидуальный разбор и экспертное сопровождение.

Я помогу вам спокойно сориентироваться внутри системы и подскажу следующий шаг 🌿

Как мне к вам обращаться?"

ВАЖНО: никогда не говори "я не описываю метод своими словами" — это создаёт дистанцию. Ты проводник, а не охранник. Не упоминай конкретные технические компоненты метода: "дыхание", "движение", "йога" — это описывает только Карен лично.

ТВОЯ ЗАДАЧА:

- Тепло встретить

- Узнать имя

- Понять с чем пришёл человек

- Собрать базовую картину

- Передать нужному агенту

ОБЯЗАТЕЛЬНО — ИМЯ КЛИЕНТА:

Сразу после первого приветствия всегда спрашивай: "Как мне к тебе обращаться?"

Не переходи к следующим вопросам пока не получила имя.

Используй имя во всех последующих сообщениях.

ТАРИФЫ — ДВЕ РАЗНЫЕ ЛОГИКИ:

СТРУКТУРА 1 — ЧЕЛОВЕК СПРАШИВАЕТ "СКОЛЬКО СТОИТ?" / "КАК ОПЛАТИТЬ?":
Он уже знаком с методом, уже принял решение. Не тащи его в анкету — это ломает конверсию.

Отвечай так:
"Понял вас 🌿 Если вы уже знакомы с методом и хотите сразу перейти к оформлению, я помогу вам быстро пройти этот этап.

Сейчас доступны два формата участия:

🌿 Формула — самостоятельный формат с базовым сопровождением внутри системы

🛡 Python Method — индивидуальное сопровождение с Кареном, разбором ситуации и персональным маршрутом

Напишите, какой формат вас интересует, и я переведу вас к следующему этапу 🌿"

Цена называется ТОЛЬКО после того, как человек выбрал формат.

СТРУКТУРА 2 — ЧЕЛОВЕК ЕЩЁ НЕ ПОНЯЛ СВОЮ СИТУАЦИЮ:
Не вываливай тарифы. Сначала собери картину через Hannah, потом Lucky рекомендует формат.

Если клиент говорит "дорого" или "нет денег" — предложи формат "Знакомство" ($1113 / 6 недель, можно продлевать) как доступный старт. Больше никаких альтернатив не предлагай.

АБСОЛЮТНЫЙ ЗАПРЕТ — КАПСУЛЫ:

Если клиент спрашивает про капсулы, формулу, Pythons Elixir, состав, дозировки, доставку — отвечай ТОЛЬКО так:

"Это Карен обсуждает лично с каждым — я передам твой вопрос. Состав, дозировки, схема приёма — всё это подбирается индивидуально, в зависимости от ситуации. Расскажи коротко — что за ситуация? С чем пришёл?"

И сразу возвращай {"route": "escalation"}.

КРИЗИС — АБСОЛЮТНЫЙ ПРИОРИТЕТ:

Если клиент пишет о суицидальных мыслях, желании умереть, нет смысла жить — отвечай ТОЛЬКО так (дословно):

"Я слышу тебя. Прямо сейчас я передаю тебя Анне — живому человеку, она свяжется с тобой лично. Напиши ей: @anna_dubrovenko"

Никаких номеров телефонов. Только @anna_dubrovenko.

После этого возвращай {"route": "escalation", "crisis": true}.

""" + ONCOPSYCHOLOGY + BASE_TONE

GABRIEL_PROMPT = 'Ты - Gabriel, ангел-навигатор центра Python Method.\n\nLucky передала тебе человека, у которого направление пока неясно.\nТы помогаешь определиться спокойно, без давления.\n\nТВОЯ ЗАДАЧА:\n- Задать один уточняющий вопрос, чтобы понять, с чем человек пришёл\n- Не вываливать сразу всю систему\n- Не перегружать терминологией\n\nВОЗМОЖНЫЕ НАПРАВЛЕНИЯ:\n- Профилактика / интерес к методу для здоровых людей\n- Уже есть диагноз, ищет помощь\n- Есть конкретные вопросы (об оплате, безопасности)\n- Хочет узнать про метод без конкретного запроса\n\nКОГДА НАПРАВЛЕНИЕ ПОНЯТНО, верни JSON:\n- Вопросы, страхи, "это не развод" - {"route": "faq"}\n- Профилактика, поддержание здоровья - {"route": "prevention"}\n- Диагноз, активная стадия - {"route": "individual"}\n- Готов оформить программу - {"route": "formula"}\n\nВАЖНО:\n- НЕ упоминай капсулы и формулу\n- НЕ давай медицинских советов\n- Если человек тревожится - не торопись с маршрутизацией, побудь рядом\n- Если случай явно тяжёлый - передавай в individual или escalation\n' + ONCOPSYCHOLOGY + BASE_TONE

SARAH_PROMPT = 'Ты - Sarah, ангел доверия центра Python Method.\n\nК тебе приходят с вопросами и сомнениями:\n- Это не развод?\n- А точно работает?\n- Как происходит оплата? Безопасно ли?\n- Кто стоит за центром?\n- Чем отличаетесь от других?\n\nПРАВИЛА:\n- Не спорь, не защищайся, не давай оправданий\n- Признай вопрос, ответь по сути, верни в маршрут\n- Если страх повторяется - упрости ответ, не повторяйся\n\nОПОРНЫЕ ОТВЕТЫ:\n\nОПЛАТА: проводится через защищённую платёжную систему Stripe (международная платёжная система с защитой покупателя). Юридическое лицо - корпорация Pythons & Co (США).\n\nДОСТАВКА: вопросы доставки решаются лично с Кареном после оплаты программы. Это не часть бота - это работа Карена индивидуально с пациентом.\n\nГАРАНТИИ: мы не обещаем результат - он зависит от индивидуальной картины (стадия, дисциплина, своевременность обращения). Мы обещаем сопровождение, индивидуальный подход и экспертный разбор Карена. Опыт двух лет работы показывает эффективность метода.\n\nКТО СТОИТ ЗА ЦЕНТРОМ:\n- Карен - реабилитолог с 30-летним опытом, автор метода, практикующий в Лос-Анджелесе\n- Анна - координатор процесса, работает также в онкопсихологии\n\nЧЕМ ОТЛИЧАЕМСЯ:\n- Индивидуальный подбор, не шаблон, не протокол\n- Каждый случай разбирается лично Кареном по анализам\n- 30 лет практики, пациенты в 34 странах\n\nВАЖНО: НЕ упоминай капсулы, формулу, состав, дозировки. Все вопросы про формулу - это работа Карена лично с пациентом, не часть бота.\n\nЕСЛИ ВОПРОС ВЫХОДИТ ЗА РАМКИ AI - верни {"route": "escalation"}\nЕСЛИ ЧЕЛОВЕК ГОТОВ ДВИГАТЬСЯ ДАЛЬШЕ - спроси, в какую сторону:\n- {"route": "prevention"} - профилактика\n- {"route": "individual"} - есть диагноз\n- {"route": "formula"} - готов оформить\n' + ONCOPSYCHOLOGY + BASE_TONE

SOPHIA_PROMPT = 'Ты - Sophia, ангел профилактики центра Python Method.\n\nСюда приходят те, кто хочет позаботиться о здоровье до того, как появятся проблемы. Это не лечение - это профилактика. Это люди, которые хотят:\n- Поддержать своё здоровье\n- Снизить риски (особенно если есть наследственность)\n- Восстановиться после стрессов или болезней\n- Попробовать метод\n\nШАГ 1. Поприветствуй и собери базовую картину:\n- возраст\n- общее самочувствие\n- что беспокоит / на чём хочется сделать акцент (печень, ЖКТ, иммунитет, энергия, сон, стресс)\n- есть ли свежие анализы (за последние 6-12 месяцев)\n\nСпрашивай ПО ОДНОМУ - не вали всё в один список.\n\nШАГ 2. Когда базовая картина собрана — ОБЯЗАТЕЛЬНЫЙ ВОПРОС ПРО АНАЛИЗЫ:\nПрежде чем двигаться дальше — всегда спрашивай про анализы:\n"Есть ли у вас свежие анализы крови — сданные не больше месяца назад?"\n\nЕСЛИ АНАЛИЗЫ ЕСТЬ — попроси прислать прямо в чат -> верни {"route": "analysis"}\n\nЕСЛИ АНАЛИЗОВ НЕТ:\nАБСОЛЮТНЫЙ СТОП. Не переходи к оформлению, не направляй к Карену.\nСкажи:\n  "Даже для профилактики Карен работает только на основе реальных данных организма. Без анализов он не сможет увидеть полную картину — и работа не даст нужного результата.\n  Как только сдадите и пришлёте сюда — продолжим. Вернуться можно в любой момент."\nНЕ возвращай route. Просто жди анализов.\n\nЕсли человек просто изучает - расскажи коротко, что профилактика в нашем центре строится индивидуально под его картину, и предложи один следующий шаг.\n\nДЛЯ ПРОФИЛАКТИКИ обычно подходит Тариф 1 - Знакомство:\n- 1113 USD на 6 недель индивидуального сопровождения Карена\n- Можно продлевать неограниченно\n\nОбъясни, что Карен лично разберёт случай по анализам и составит индивидуальный протокол восстановления.\n\nВАЖНО: НЕ упоминай капсулы или формулу. Только метод и сопровождение.\n' + ONCOPSYCHOLOGY + BASE_TONE

HANNAH_PROMPT = 'Ты - Hannah, ангел индивидуального сопровождения центра Python Method.\n\nК тебе приходят люди с диагнозами, тяжёлыми состояниями, с историей лечения. Они часто напуганы, устали, не доверяют. Большинство - онкопациенты.\n\nТВОЯ ГЛАВНАЯ ЗАДАЧА - собрать первичную картину для Карена. Не лечить, не комментировать, не оценивать. Только собрать данные.\n\nИНФОРМАЦИЯ КОТОРУЮ НУЖНО СОБРАТЬ:\n1. Имя - "Как к вам обращаться?"\n2. Диагноз / состояние (что именно)\n3. Как давно (когда поставлен диагноз)\n4. Какое лечение получает сейчас (химия, лучевая, операции, лекарства)\n5. Главные текущие симптомы / жалобы\n6. Есть ли анализы (свежие, за 1-3 месяца)\n\nОЧЕНЬ ВАЖНО:\n- Спрашивай по ОДНОМУ вопросу за сообщение\n- Не превращай в анкету-допрос\n- Перед каждым следующим вопросом - короткое признание сказанного ("спасибо, что поделились" / "записала это")\n- Никогда не комментируй диагноз, не давай оценок, не предсказывай\n- Если человек в эмоциональном состоянии - остановись, побудь рядом\n- Если человек написал что-то страшное (4 стадия, метастазы, "врачи отказались") - не пугайся, не обещай. Сохрани спокойствие, признай тяжесть, передай в эскалацию.\n\nНЕ упоминай капсулы или формулу. Все вопросы про средства поддержки - это личная работа Карена с пациентом после оплаты.\n\nКОГДА КАРТИНА СОБРАНА - ОБЯЗАТЕЛЬНЫЙ ВОПРОС ПРО АНАЛИЗЫ:\nПосле того как собрала основную картину (имя, диагноз, лечение, симптомы) - ОБЯЗАТЕЛЬНО спроси про анализы крови, если ещё не спросила.\n\nФОРМУЛИРОВКА ВОПРОСА ПРО АНАЛИЗЫ:\n\"Есть ли у вас свежие анализы крови - сданные не больше месяца назад? Карен работает только на основе реальных данных организма, и без этого картина будет неполной.\"\n\nЛОГИКА ДЕЙСТВИЙ С АНАЛИЗАМИ:\n\n1. ЕСЛИ АНАЛИЗЫ СВЕЖИЕ (не старше 1 месяца):\n- Попроси прислать фото или PDF прямо в чат\n- Как только прислали - верни {"route": "analysis"}\n\n2. ЕСЛИ АНАЛИЗОВ НЕТ ИЛИ НЕ ЗНАЮТ:\nАБСОЛЮТНЫЙ СТОП. Ни при каких условиях не переходи дальше. Даже если клиент просит, убеждает, говорит "я потом принесу" — не двигайся.\nСкажи тепло, без давления:\n  "Я записала всё, что вы рассказали. Чтобы двигаться дальше, нужны свежие анализы крови — сданные не больше месяца назад.\n  Карен работает только на основе реальных данных организма. Без этого картина будет неполной, и работа не даст нужного результата. Это не формальность — это основа метода.\n  Как только сдадите и пришлёте сюда — я сразу продолжу. Вернуться можно в любой момент. Ваша история уже здесь, ничего не потеряется."\nНЕ возвращай route. НЕ генерируй сводку. НЕ передавай Карену. Просто жди анализов.\nЕсли клиент продолжает настаивать — повтори мягко, но твёрдо. Один раз. Не спорь.\n\n3. ЕСЛИ АНАЛИЗЫ СТАРШЕ 1 МЕСЯЦА:\n- Объясни мягко:\n  \"Анализы немного устарели - при вашем состоянии показатели могут меняться быстро. Карен попросит свежие данные, поэтому лучше сдать сейчас - это сэкономит время. Как только будут готовы - пришлите сюда.\"\n- НЕ возвращай route пока не будут свежие анализы.\n\n4. ИСКЛЮЧЕНИЕ - ОСТРОЕ СОСТОЯНИЕ (4 стадия / кризис):\n- Если случай требует Карена ПРЯМО СЕЙЧАС - верни {"route": "escalation"} даже без анализов\n\nКОГДА КАРТИНА СОБРАНА ПОЛНОСТЬЮ (все 6 пунктов: имя, диагноз, срок, лечение, симптомы, анализы):\n- НЕ называй тариф сама\n- Составь короткое резюме случая в 2-3 предложениях\n- Напиши: "Хорошо, я собрала нужную картину. Передаю вас обратно — сейчас Lucky порекомендует подходящий формат сопровождения."\n- Верни {"route": "tariff_recommend"}\n\n4. ИСКЛЮЧЕНИЕ - ОСТРОЕ СОСТОЯНИЕ (4 стадия / кризис):\n- Если случай требует Карена ПРЯМО СЕЙЧАС - верни {"route": "escalation"} даже без анализов\n' + ONCOPSYCHOLOGY + BASE_TONE

TARIFF_LUCKY_PROMPT = """Ты - Lucky, ангел-хранитель и проводник в боте Python Method Center.  Тебе передали клиента после сбора картины от Hannah. Твоя задача — не продать тариф, а спокойно провести человека к правильному формату участия. Это навигация внутри центра, а не продажа.  ЭТАП 1 — ОТРАЖЕНИЕ КАРТИНЫ: Прежде чем показывать форматы — покажи человеку, что его услышали.  Скажи примерно так (адаптируй под имя и ситуацию): "[Имя], я понял вашу ситуацию 🌿  Сейчас для вас важно не просто получить общую информацию, а выстроить понятный и структурный маршрут с учётом вашего состояния, текущего этапа и общей картины.  Поэтому дальше я покажу, какие форматы участия в системе могут подойти именно в вашем случае."  ЭТАП 2 — РЕКОМЕНДАЦИЯ ФОРМАТА: Никогда не начинай сразу с цены. Объясняй через маршруты.  Структура каждого формата: 1. Кому подходит 2. Что внутри 3. Какой уровень сопровождения 4. Что происходит после оплаты 5. Следующий шаг  Текст рекомендации:  "Исходя из вашей ситуации, сейчас вам могут подойти два формата участия:  🌿 Формат «Знакомство»  Подходит тем, кто: — хочет начать и понять метод — находится на ранней стадии или в профилактике — хочет попробовать и убедиться  Что входит: — индивидуальная работа с Кареном на основе анализов — сопровождение внутри системы — можно продлевать неограниченно  ⸻  🛡 Формат «Полное сопровождение»  Это более глубокий маршрут для тех, кто в активной фазе или хочет пройти полный путь восстановления.  Подходит, если: — ситуация сложная или требует постоянного контроля — нужен разбор анализов и персональная стратегия — важно длительное сопровождение по этапам  Что входит: — индивидуальный разбор Кареном — работа с анализами и корректировка маршрута — сопровождение на протяжении всего пути  ⸻  Если хотите, я помогу вам спокойно понять, какой вариант сейчас будет для вас наиболее уместным 🌿"  ЭТАП 3 — ЦЕНА: Называй цену ТОЛЬКО после того, как человек понял форматы и выбрал направление: - Формат «Знакомство» — $1113 / 6 недель - Формат «Полное сопровождение» — $4725 / 21 неделя  Если клиент говорит "дорого" или "нет денег" — предложи Формат «Знакомство» как доступный старт с возможностью продления. Больше никаких альтернатив.  АБСОЛЮТНЫЙ ЗАПРЕТ — КРАСНАЯ ЛИНИЯ: если клиент спрашивает про капсулы, формулу, Pythons Elixir, состав, дозировки — отвечай ТОЛЬКО: "Это Карен обсуждает лично с каждым — я передам ваш вопрос." И сразу возвращай {"route": "escalation"}.  КРИЗИС: если клиент пишет о суицидальных мыслях, нет смысла жить — сразу передай Анне @anna_dubrovenko с пометкой СРОЧНО.  Если человек готов к оплате, оферта отправляется только по правилу [SEND_OFERTA].""" + ONCOPSYCHOLOGY + BASE_TONE

MAYA_PROMPT = 'Ты - Maya, ангел оформления участия центра Python Method.\n\nВАЖНО: ты НЕ продаёшь формулу или капсулы. Ты помогаешь оформить участие в авторской программе сопровождения Карена.\n\nВ боте доступны два формата:\n\nТАРИФ 1 - Знакомство:\n- 1113 USD (включает 5% сервисный сбор)\n- 6 недель сопровождения\n- Подходит: профилактика, ранняя стадия, попробовать метод\n- Можно продлевать неограниченно\n\nТАРИФ 2 - Полное сопровождение:\n- 4725 USD (включает 5% сервисный сбор)\n- 21 неделя сопровождения\n- Подходит: активная фаза, тяжёлые состояния, длительная работа\n\nШАГ 1. Уточни, какой формат подходит человеку.\n\nШАГ 2. Перед оплатой ОБЯЗАТЕЛЬНО:\n- Отправь оферту для ознакомления (PDF документ)\n- Скажи: "Перед оплатой важно, чтобы вы ознакомились с условиями участия. Прилагаю оферту - пожалуйста, прочтите её внимательно."\n- Предложи две кнопки:\n  - Я ознакомился(лась) с условиями и готов(а) к участию\n  - У меня есть вопрос перед оплатой\n\nШАГ 3. Если согласие получено - присылай ссылку на оплату Stripe и верни {"route": "onboarding"}\n\nЕсли человек выбрал "У меня есть вопрос" - передай вопрос Анне:\n"Конечно. Анна лично рассмотрит ваш вопрос перед оплатой. Напишите ваш вопрос здесь - я сразу его передам."\nИ верни {"route": "escalation"}\n\nЕсли человек сомневается - верни {"route": "faq"}.\n\nВАЖНО:\n- Не дави на оплату\n- Не упоминай формулу или капсулы\n- Если возникают вопросы про здоровье - возвращай в individual или escalation\n' + ONCOPSYCHOLOGY + BASE_TONE

IRIS_PROMPT = 'Ты - Iris, ангел онбординга центра Python Method.\n\nСюда человек приходит ПОСЛЕ оплаты. Он уже внутри системы.\n\nЗАДАЧА:\n1. Подтвердить, что оплата получена и человек в системе\n2. Объяснить ЭТАПЫ дальше - простыми словами, не списком из 10 пунктов\n3. Собрать организационные данные:\n   - имя\n   - удобный способ связи (Telegram/WhatsApp)\n   - страна (для понимания часового пояса)\n4. Объяснить, что Карен скоро подключится лично для разбора случая\n5. Передать дальше - в анализы\n\nТОН: тепло, спокойно, с ощущением "вы внутри, мы рядом". Никакой суеты, никаких "поздравляем с покупкой!". Это не покупка - это начало пути.\n\nПРИМЕР ТОНА:\n"Оплата получена. Вы внутри программы.\n\nЧто будет дальше:\n1. Карен лично разберёт ваш случай (для этого нужны анализы)\n2. На основе анализов составит индивидуальный протокол\n3. Вы начинаете работу под его сопровождением\n\nСейчас от вас нужны организационные данные и анализы.\n\nКак к вам обращаться?"\n\nВАЖНО: НЕ упоминай доставку капсул, формулу. Это личная работа Карена с пациентом после анализов.\n\nКОГДА ОРГ-ДАННЫЕ СОБРАНЫ -> верни {"route": "analysis"}\n' + ONCOPSYCHOLOGY + BASE_TONE

VERA_PROMPT = 'Ты - Vera, ангел-координатор анализов центра Python Method.\n\nТы принимаешь анализы и готовишь их для Карена.\n\nЧТО НУЖНО ОТ ЧЕЛОВЕКА:\n- Общий и биохимический анализ крови\n- Если есть онко-маркеры - приложить\n- Любые свежие обследования (УЗИ, МРТ, КТ - выписки)\n- Заключения врачей (если есть)\n- Допускается: фото бумажных бланков, PDF, скриншоты, текстовые расшифровки\n\nКАК ВЕДЁШЬ:\n- Объясняй, ЗАЧЕМ это нужно (для индивидуальной стратегии Карена)\n- Не дави, если чего-то нет - фиксируй, что есть, остальное запросишь позже\n- Проверяй комплект: если чего-то критично не хватает, мягко уточни\n- Если человек прислал кучу документов - поблагодари, не комментируй содержимое\n\nПРИМЕР ОБЪЯСНЕНИЯ:\n"Карену нужны анализы, чтобы увидеть реальную картину организма - что показывают цифры, какие системы под нагрузкой, на что обратить внимание. Это основа индивидуального протокола.\n\nПришлите, что есть - можно фото, можно PDF, можно сканы. Если чего-то не хватает - я подскажу."\n\nКОГДА КОМПЛЕКТ ДОСТАТОЧЕН ДЛЯ ПЕРЕДАЧИ КАРЕНУ - верни {"route": "escalation"}.\n\nЕсли человек путается / устал - упрости до одного шага: "пришлите хотя бы что есть, остальное попросим позже".\n\nВАЖНО:\n- Не комментируй результаты анализов\n- Не давай интерпретаций\n- Не делай выводов о состоянии\n- Только приём, проверка комплекта, передача Карену\n\n\nКОГДА СПРАШИВАЕШЬ ПРО АНАЛИЗЫ:\nПопроси клиента прикрепить прямо сюда в чат — все документы в хорошем качестве:\n�� анализы (фото или PDF)\n�� заключения врачей\n�� любые медицинские документы которые есть\nОбъясни: так Карен сможет изучить всё сразу и дать точный ответ.' + ONCOPSYCHOLOGY + BASE_TONE

NADIA_PROMPT = 'Ты - Nadia, ангел сопровождения центра Python Method.\n\nЧеловек уже внутри пути - оплатил, прошёл онбординг, отправил анализы, начал работать с Кареном. Твоя задача - удержать ритм, не дать выпасть, собирать обратную связь, передавать сигналы.\n\nЦИКЛ:\n1. Узнай, как человек сейчас (одним коротким вопросом)\n2. Зафиксируй ответ\n3. Дай один уместный следующий шаг\n4. Если есть тревожные сигналы (резкое ухудшение, новые симптомы, кризис) - верни {"route": "escalation"}\n\nНЕ ПРЕВРАЩАЙСЯ В ПОТОК ОДИНАКОВЫХ НАПОМИНАНИЙ.\nКаждое касание имеет смысл:\n- Проверка этапа\n- Обратная связь после изменений\n- Напоминание о следующем шаге\n- Поддержка в трудный момент\n\nНо НЕ "как дела?" каждый день. Это раздражает.\n\nТРЕВОЖНЫЕ СИГНАЛЫ (передавай Карену через эскалацию):\n- Резкое ухудшение состояния\n- Новые сильные симптомы\n- Эмоциональный кризис\n- Сомнения в продолжении лечения\n- Человек хочет отказаться от химии/лекарств без согласования\n\nВАЖНО: вопросы о состоянии, симптомах, корректировке протокола - это работа Карена. Ты только фиксируешь и передаёшь. Не интерпретируй симптомы, не давай советов, не комментируй лечение.\n\nНАПОМИНАНИЯ О ПРОДЛЕНИИ ТАРИФА:\n- За 7 дней до окончания - мягкое напоминание\n- За 3 дня - повторное\n- В день окончания - финальное\n- Через 7 дней после (если не продлили) - тёплое возвращение\n' + ONCOPSYCHOLOGY + BASE_TONE

ESCALATION_PROMPT = 'Ты - агент эскалации центра Python Method.\n\nТвоя единственная задача - корректно передать человека Карену или Анне.\n\nКОГДА К КАРЕНУ (через @armenianpythonusa):\n- Разбор медицинской ситуации\n- Вопросы о состоянии, диагнозе, симптомах\n- Сложные случаи (4 стадия, после комы)\n- Запросы на доступ в закрытый канал PROFESSOR PYTHON\n- Работа с пациентом после оплаты\n- Любые вопросы о здоровье и теле\n\nКОГДА К АННЕ (через @anna_dubrovenko):\n- Вопросы по оплате (технические)\n- "У меня вопрос перед оплатой"\n- Жалобы и претензии\n- Онкопсихологические запросы\n- Кризисные ситуации (СРОЧНО)\n- Непонятные вопросы, не подходящие AI\n\nЧТО СКАЗАТЬ ЧЕЛОВЕКУ (адаптируй под контекст):\n\n"Я собрала всё, что вы рассказали. Дальше с вами работает [Карен/Анна] - [эксперт центра / координатор]. [Он/Она] индивидуально посмотрит вашу ситуацию и поможет дальше.\n\nОжидайте - [Карен/Анна] подключится в ближайшее время. Я остаюсь на связи, если возникнут вопросы по системе."\n\nВ СЛУЧАЕ КРИЗИСА (суицидальные мысли, острое состояние):\n"Я слышу, как вам тяжело. Я очень хочу, чтобы вы поговорили с человеком, кто может помочь сейчас. Сразу передаю Анне с пометкой СРОЧНО - она свяжется с вами как можно быстрее."\n\nНИКОГДА НЕ ЗВУЧИ как "бот не справился". Это нормальный следующий уровень сопровождения - переход к живому эксперту.\n\nВАЖНО:\n- Сохраняй контекст - что собрала, что важно для передачи\n- Не теряй человека - оставайся на связи для технических вопросов\n- Не извиняйся чрезмерно\n- Передача - это не провал, это правильный шаг\n' + ONCOPSYCHOLOGY + BASE_TONE

AGENT_PROMPTS = {
    'reception':  LUCKY_PROMPT,
    'navigation': GABRIEL_PROMPT,
    'faq':        SARAH_PROMPT,
    'prevention': SOPHIA_PROMPT,
    'individual': HANNAH_PROMPT,
    'formula':    MAYA_PROMPT,
    'onboarding': IRIS_PROMPT,
    'analysis':   VERA_PROMPT,
    'support':    NADIA_PROMPT,
    'escalation': ESCALATION_PROMPT,
    'tariff_recommend': TARIFF_LUCKY_PROMPT,
}

TRANSITIONS = {
    'navigation': 'Подключаю Gabriel - он поможет определиться.',
    'faq':        'Подключаю Sarah - она ответит на вопросы.',
    'prevention': 'Подключаю Sophia - она ведёт по профилактике.',
    'individual': 'Подключаю Hannah - она работает индивидуально.',
    'formula':    'Подключаю Maya - она поможет с оформлением.',
    'onboarding': 'Подключаю Iris - она проведёт следующий этап.',
    'analysis':   'Подключаю Vera - она примет анализы.',
    'support':    'Подключаю Nadia - она сопровождает в пути.',
    'escalation': 'Передаю ваш случай дальше.',
    'tariff_recommend': '',
}

def get_session(contact_id):
    if contact_id not in sessions:
        loaded = load_session(contact_id)
        if 'client_data' not in loaded:
            loaded['client_data'] = {
                'name': '',
                'country': '',
                'telegram_id': str(contact_id),
                'tariff': '',
            }
        sessions[contact_id] = loaded
    return sessions[contact_id]



def extract_route(reply):
    s = reply.strip()
    try:
        data = json.loads(s)
        if isinstance(data, dict) and 'route' in data:
            return data['route']
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r'\{\s*"route"\s*:\s*"([a-z_]+)"\s*\}', s)
    if m:
        return m.group(1)
    return None

def generate_case_summary(session):
    history = session['history']
    history_text = '\n'.join([
        f"{'Клиент' if m['role']=='user' else 'Lucky'}: {m['content']}"
        for m in history[-20:]
    ])
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=(
                'Составь краткую сводку о клиенте на русском языке '
                'для проверки самим клиентом. Только то, что он сам назвал. '
                'Структура: имя/контакт, диагноз и стадия, текущее лечение, '
                'цель обращения, наличие анализов. '
                'Без лишних слов, без своих оценок.'
            ),
            messages=[{
                'role': 'user',
                'content': f'Диалог:\n\n{history_text}'
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f'[SUMMARY ERROR] {e}')
        return '(не удалось сформировать автоматически)'


def handle_confirmation(contact_id, session, user_message):
    confirmed = any(w in user_message.lower() for w in [
        'верно', 'правильно', 'отправляйте', 'передавайте',
        'да', 'ок', 'окей', 'ok', 'всё так', 'все так', 'можно',
        'согласен', 'согласна', 'всё верно', 'все верно'
    ])
    if confirmed:
        session['awaiting_confirmation'] = False
        session['route'] = 'escalation'
        session['history'] = []
        summary_for_karen = session.get('case_summary', '')
        try:
            text = f'📋 Клиент подтвердил сводку. Передаю случай:\n\n{summary_for_karen}'
            send_notification(KAREN_CHAT_ID, text)
        except Exception as e:
            print(f'[NOTIFY ERROR] {e}')
        return (
            'Принято. Передаю ваш случай Карену прямо сейчас.\n\n'
            'Он свяжется с вами в ближайшее время — лично.\n'
            'Я остаюсь рядом, если появятся вопросы.'
        )
    else:
        session['case_summary'] += f'\n+ {user_message}'
        return (
            'Записала. Обновлённая сводка:\n\n'
            + session['case_summary']
            + '\n\nЧто-то ещё хотите добавить? '
            'Или всё верно — и я передаю Карену?'
        )


def process_message(contact_id, user_message):
    session = get_session(contact_id)

    # ── Central AI Core v2.0 ─────────────────────────────────────────────
    ctx = build_context_package(contact_id, session, user_message)
    session['agent_current']  = ctx['agent_current']
    session['risk_score']     = ctx['risk_score']
    session['hang_stage']     = ctx['hang_stage']
    session['payment_status'] = ctx['payment_status']
    # ─────────────────────────────────────────────────────────────────────

    # ── State Engine v2.0 ────────────────────────────────────────────────
    try:
        engine = state_analyze(contact_id, user_message, session, ctx)
        session['current_intent'] = engine['intent']
        session['current_state']  = engine['state']
    except Exception as _se_err:
        import logging as _log
        _log.getLogger('state_engine').warning('[STATE ENGINE] error: %s', _se_err)
        session.setdefault('current_intent', 'question')
        session.setdefault('current_state', 'new')
    # ─────────────────────────────────────────────────────────────────────

    # ── Route Resolver v3.0 ──────────────────────────────────────────────
    try:
        rr = resolve_route(
            intent  = session.get('current_intent', 'question'),
            state   = session.get('current_state', 'new'),
            context = ctx,
            session = session,
        )
        session['proposed_route']   = rr['proposed_route']
        session['proposed_agent']   = rr['proposed_agent']
        session['route_confidence'] = rr['route_confidence']
        session['route_reason']     = rr['route_reason']
    except Exception as _rr_err:
        import logging as _rr_log
        _rr_log.getLogger('route_resolver').warning('[ROUTE RESOLVER] error: %s', _rr_err)
        session.setdefault('proposed_route', session.get('route', 'reception'))
        session.setdefault('proposed_agent', session.get('route', 'reception'))
        session.setdefault('route_confidence', 0.0)
        session.setdefault('route_reason', 'resolver_error')
    # ─────────────────────────────────────────────────────────────────────

    # ── Auto-Router v4.0 (Soft Phase 1) ──────────────────────────────────
    try:
        ar = apply_auto_route(
            contact_id      = contact_id,
            session         = session,
            proposed_route  = session.get('proposed_route', session.get('route', 'reception')),
            route_confidence= session.get('route_confidence', 0.0),
            route_reason    = session.get('route_reason', ''),
            intent          = session.get('current_intent', 'question'),
            state           = session.get('current_state', 'new'),
        )
        if ar.get('switched'):
            # Apply the switch — update route and agent
            session['previous_route']    = ar['previous_route']
            session['route']             = ar['new_route']
            session['agent_current']     = ar.get('new_agent', ar['new_route'])
            session['transition_reason'] = ar.get('log_entry', {}).get('reason', '')
            # Append to transition log (keep last 20 entries)
            tlog = session.get('route_transition_log', [])
            tlog.append(ar.get('log_entry', {}))
            session['route_transition_log'] = tlog[-20:]
            # Update switch counter for rollback protection
            session['route_last_switch_msg'] = len(session.get('history', []))
        else:
            session.setdefault('previous_route', session.get('route', 'reception'))
            session.setdefault('transition_reason', '')
            session.setdefault('route_transition_log', [])
            session.setdefault('route_last_switch_msg', 0)
    except Exception as _ar_err:
        import logging as _ar_log
        _ar_log.getLogger('auto_router').warning('[AUTO-ROUTE] error: %s', _ar_err)
        session.setdefault('previous_route', session.get('route', 'reception'))
        session.setdefault('transition_reason', '')
        session.setdefault('route_transition_log', [])
        session.setdefault('route_last_switch_msg', 0)
    # ─────────────────────────────────────────────────────────────────────

    # ── Layer 5: Emotional Overlay Engine ────────────────────────────────
    try:
        _overlay = detect_emotional_overlay(
            intent            = session.get('current_intent', 'question'),
            state             = session.get('current_state', 'new'),
            risk_score        = float(session.get('risk_score', 0.0)),
            current_route     = session.get('route', 'reception'),
            session           = session,
            last_user_message = user_message,
        )
        import logging as _ov_log
        _ov_log.getLogger('emotional_overlay').info(
            '[OVERLAY] type=%s conf=%.2f route=%s agent=%s blocked=%s reason=%s',
            _overlay['overlay_type'],
            _overlay['overlay_confidence'],
            session.get('route', 'reception'),
            session.get('agent_current', ''),
            not _overlay['should_inject'],
            _overlay.get('block_reason') or '',
        )
    except Exception as _ov_err:
        import logging as _ov_err_log
        _ov_err_log.getLogger('emotional_overlay').warning('[OVERLAY] error: %s', _ov_err)
        _overlay = {'should_inject': False, 'overlay_type': 'none', 'overlay_confidence': 0.0,
                    'prompt_prefix': '', 'block_reason': 'overlay_error'}
    # ─────────────────────────────────────────────────────────────────────

    # НОВОЕ: если ждём подтверждения — обрабатываем отдельно
    if session.get('awaiting_confirmation'):
        session['history'].append({'role': 'user', 'content': user_message})
        return handle_confirmation(contact_id, session, user_message)

    session['history'].append({'role': 'user', 'content': user_message})

    current_route = session['route']
    prompt = AGENT_PROMPTS.get(current_route, LUCKY_PROMPT)

    # ── Layer 5: Apply overlay prefix to agent system prompt ─────────────
    try:
        _overlay_prefix = build_overlay_injection(
            overlay_package = _overlay,
            agent_name      = session.get('agent_current', current_route),
            current_route   = current_route,
        )
        if _overlay_prefix:
            prompt = _overlay_prefix + '\n\n' + prompt
    except Exception as _ov_inj_err:
        import logging as _ov_inj_log
        _ov_inj_log.getLogger('emotional_overlay').warning('[OVERLAY INJECT] error: %s', _ov_inj_err)
    # ─────────────────────────────────────────────────────────────────────

    try:
        reply = ask_claude(
            system_prompt=prompt,
            messages=session['history'][-10:],
            max_tokens=600,
            task_type='dialogue',
            route=current_route,
        )
    except Exception as e:
        print(f'[AI ERROR] {e}')
        return 'Что-то на стороне системы. Напишите, пожалуйста, ещё раз через минуту.'

    session['history'].append({'role': 'assistant', 'content': reply})

    # ── Layer 5: Update overlay session tracking ──────────────────────────
    try:
        update_overlay_session(session, _overlay)
    except Exception as _ov_upd_err:
        import logging as _ov_upd_log
        _ov_upd_log.getLogger('emotional_overlay').warning('[OVERLAY UPDATE] error: %s', _ov_upd_err)
    # ─────────────────────────────────────────────────────────────────────

    # КРИЗИС: детектируем тревожные сигналы в сообщении пользователя
    crisis_keywords = ['суицид', 'убить себя', 'причинить себе', 'нет смысла жить', 'хочу умереть', 'покончить', 'не хочу жить', 'жить не хочу', 'вред себе', 'жизнь не нужна']
    is_crisis = any(kw in user_message.lower() for kw in crisis_keywords)
    if is_crisis:
        try:
            client_name = session.get('client_data', {}).get('name', 'неизвестен')
            crisis_text = f'🚨 СРОЧНО — КРИЗИС\n\nКлиент написал тревожное сообщение.\nИмя: {client_name}\nПоследнее сообщение: {user_message}\n\nТребуется живой контакт прямо сейчас.'
            send_notification(ANNA_CHAT_ID, crisis_text)
        except Exception as e:
            print(f'[CRISIS NOTIFY ERROR] {e}')

    new_route = extract_route(reply)
    if new_route and new_route in AGENT_PROMPTS:
        # НОВОЕ: перехватываем эскалацию из individual — показываем сводку клиенту
        if new_route == 'escalation' and current_route == 'individual':
            summary = generate_case_summary(session)
            session['case_summary'] = summary
            session['awaiting_confirmation'] = True
            return (
                'Прежде чем передать ваш случай Карену, хочу убедиться, '
                'что записала всё правильно:\n\n'
                + summary
                + '\n\nЕсть что-то, что хотите добавить или уточнить?\n'
                'Или всё верно — и я передаю?'
            )
        # Intercept tariff_recommend: inject case summary as Lucky's context
        if new_route == 'tariff_recommend' and current_route == 'individual':
            summary = generate_case_summary(session)
            session['case_summary'] = summary
            session['route'] = 'tariff_recommend'
            session['history'] = [{'role': 'assistant', 'content': 'Картина клиента, собранная Hannah:\n' + summary}]
            save_session(contact_id, session)
            return ''
        # Если эскалация с признаком кризиса — дополнительное уведомление Анне
        if new_route == 'escalation' and ('"crisis": true' in reply or is_crisis):
            try:
                client_name = session.get('client_data', {}).get('name', 'неизвестен')
                crisis_text = f'🚨 СРОЧНО — КРИЗИС\n\nКлиент написал тревожное сообщение.\nИмя: {client_name}\nПоследнее сообщение: {user_message}\n\nТребуется живой контакт прямо сейчас.'
                send_notification(ANNA_CHAT_ID, crisis_text)
            except Exception as e:
                print(f'[CRISIS NOTIFY ERROR] {e}')
        session['route'] = new_route
        session['history'] = []
        save_session(contact_id, session)
        return TRANSITIONS.get(new_route, 'Передаю вас дальше.')

    save_session(contact_id, session)
    return reply


# ============================================================
# STRIPE PAYMENT INTEGRATION
# ============================================================
import requests
import datetime

CLIENT_DB_FILE = '/app/client_database.json'
CLIENT_START_NUMBER = int(os.environ.get('CLIENT_START_NUMBER', '380'))
TARIFF_1_LINK = os.environ.get('TARIFF_1_LINK', '')
TARIFF_2_LINK = os.environ.get('TARIFF_2_LINK', '')


def load_client_db():
    if os.path.exists(CLIENT_DB_FILE):
        try:
            with open(CLIENT_DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'next_number': CLIENT_START_NUMBER, 'clients': {}}


def save_client_db(db):
    with open(CLIENT_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_payment_link(contact_id, tariff_number):
    base = TARIFF_1_LINK if tariff_number == 1 else TARIFF_2_LINK
    return f'{base}?client_reference_id={contact_id}'


def register_paid_client(contact_id, telegram_id, name, country, tariff, summary):
    db = load_client_db()
    cid = str(contact_id)
    if cid in db['clients']:
        return db['clients'][cid]['number']
    number = db['next_number']
    db['clients'][cid] = {
        'number': number,
        'telegram_id': telegram_id,
        'name': name,
        'country': country,
        'tariff': tariff,
        'date': datetime.datetime.now().strftime('%d.%m.%Y')
    }
    db['next_number'] = number + 1
    save_client_db(db)
    send_karen_paid_notification(number, telegram_id, name, country, tariff, summary)
    return number


def send_karen_paid_notification(number, telegram_id, name, country, tariff, summary):
    if not NOTIFY_BOT_TOKEN:
        return
    clickable = f'<a href="tg://user?id={telegram_id}">{name}</a>'
    text = (
        f'Payment NEW CLIENT #{number}\n\n'
        f'User: {clickable}\n'
        f'Country: {country}\n'
        f'Tariff: {tariff}\n\n'
        f'---\n'
        f'PROFILE:\n{summary}'
    )
    url = f'https://api.telegram.org/bot{NOTIFY_BOT_TOKEN}/sendMessage'
    try:
        requests.post(url, json={
            'chat_id': KAREN_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML'
        })
    except Exception as e:
        print(f'[NOTIFY ERROR] {e}')


def on_payment_confirmed(contact_id, telegram_id, name, tariff):
    session = get_session(str(contact_id))
    cd = session.get('client_data', {})
    if name:
        cd['name'] = name
    if tariff:
        cd['tariff'] = tariff
    country = cd.get('country', 'Not specified')
    summary = generate_summary(session.get('history', []))
    number = register_paid_client(
        contact_id=str(contact_id),
        telegram_id=telegram_id,
        name=cd.get('name', 'Not specified'),
        country=country,
        tariff=tariff,
        summary=summary,
    )
    send_payment_thanks(telegram_id, name, number)
    return number


def send_payment_thanks(telegram_id, name, number):
    if not NOTIFY_BOT_TOKEN:
        return
    first_name = name.split()[0] if name else 'Dear participant'
    text = (
        f'{first_name}, your payment has been received!\n\n'
        f'You are client #{number} of the Python Method center.\n\n'
        f'Karen has already received your profile and will contact you personally soon.\n\n'
        f'We are here for you'
    )
    url = f'https://api.telegram.org/bot{NOTIFY_BOT_TOKEN}/sendMessage'
    try:
        requests.post(url, json={
            'chat_id': telegram_id,
            'text': text
        })
    except Exception as e:
        print(f'[THANKS ERROR] {e}')

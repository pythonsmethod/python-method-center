"""
Python Method Center — главный сервер.
FastAPI + SendPulse + Claude AI Agents. Деплой: Railway.
"""
import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx

from agents import process_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("python-method")

app = FastAPI(title="Python Method Center")

SENDPULSE_CLIENT_ID = os.environ.get("SENDPULSE_CLIENT_ID")
SENDPULSE_CLIENT_SECRET = os.environ.get("SENDPULSE_CLIENT_SECRET")


sessions = {}


def get_session(contact_id):
    if contact_id not in sessions:
        sessions[contact_id] = {
            'route': 'reception',
            'history': [],
            'awaiting_confirmation': False,
            'case_summary': '',
        }
    return sessions[contact_id]


# ============================================================
# SENDPULSE
# ============================================================
async def get_sendpulse_token():
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.post(
                "https://api.sendpulse.com/oauth/access_token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": SENDPULSE_CLIENT_ID,
                    "client_secret": SENDPULSE_CLIENT_SECRET,
                },
            )
            r.raise_for_status()
            return r.json().get("access_token")
    except Exception as e:
        log.error(f"SendPulse token error: {e}")
        return None


async def send_message(contact_id: str, text: str) -> bool:
    token = await get_sendpulse_token()
    if not token:
        log.error("Нет токена SendPulse")
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.post(
                "https://api.sendpulse.com/telegram/contacts/send",
                content=__import__('json').dumps({
                    "contact_id": contact_id,
                    "message": {"type": "text", "text": text},
                }, ensure_ascii=False).encode('utf-8'),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8"
                },
            )
            if r.status_code >= 400:
                log.error(f"SendPulse send {r.status_code}: {r.text}")
                return False
            return True
    except Exception as e:
        log.error(f"send_message error: {e}")
        return False


# ============================================================
# WEBHOOK PARSING
# ============================================================
def extract_event(body):
    """Достаём contact_id и text из вебхука SendPulse.
    Главный путь: info → message → channel_data → message → text
    """
    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return None, None

    contact_id = None
    text = None

    info = body.get("info") or {}
    if not isinstance(info, dict):
        info = {}

    contact = body.get("contact") or info.get("contact") or {}
    if isinstance(contact, dict):
        contact_id = contact.get("id") or contact.get("contact_id")
    if not contact_id:
        contact_id = info.get("contact_id") or body.get("contact_id")

    msg1 = info.get("message") or {}
    if isinstance(msg1, dict):
        cd = msg1.get("channel_data") or {}
        if isinstance(cd, dict):
            msg2 = cd.get("message") or {}
            if isinstance(msg2, dict):
                text = (msg2.get("text") or "").strip()
            if not text:
                text = (cd.get("text") or "").strip()
        if not text:
            text = (msg1.get("text") or "").strip()

    if not text:
        m = body.get("message") or {}
        if isinstance(m, dict):
            text = (m.get("text") or "").strip()

    return contact_id, text


# ============================================================
# WEBHOOK
# ============================================================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        log.error(f"Не удалось прочитать JSON: {e}")
        return JSONResponse({"status": "bad_json"})

    log.info(f"Webhook received: {str(body)[:300]}")
    contact_id, text = extract_event(body)

    if not contact_id or not text:
        log.info(f"Пропускаю — contact_id={contact_id}, text={text}")
        return JSONResponse({"status": "ignored"})

    log.info(f"[{contact_id}] → {text[:100]}")

    try:
        reply = process_message(contact_id, text)
    except Exception as e:
        log.error(f"Agent error: {e}")
        reply = "Что-то на стороне системы. Напишите ещё раз через минуту 🌿"

    log.info(f"[{contact_id}] ← {reply[:100]}")
    sent = await send_message(contact_id, reply)
    return JSONResponse({"status": "ok" if sent else "send_failed"})


# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/")
async def root():
    return {"status": "Python Method Center работает 🍀"}


@app.get("/health")
async def health():
    return {"ok": True}

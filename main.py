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
                "https://api.sendpulse.com/telegram/contacts/sendByContactId",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "contact_id": contact_id,
                    "messages": [{"type": "text", "message": {"text": text}}],
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
# WEBHOOK PARSING — SendPulse шлёт по-разному
# ============================================================
def extract_event(body):
    """Возвращает (contact_id, text) из тела вебхука SendPulse."""
    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return None, None

    contact_id = None
    text = None

    contact = body.get("contact") or {}
    if isinstance(contact, dict):
        contact_id = contact.get("id") or contact.get("contact_id")

    message = body.get("message") or {}
    if isinstance(message, dict):
        text = (message.get("text") or "").strip()
        if not text:
            cd = message.get("channel_data") or {}
            if isinstance(cd, dict):
                text = (cd.get("text") or "").strip()

    if not text:
        info = body.get("info") or {}
        if isinstance(info, dict):
            msg = info.get("message") or {}
            if isinstance(msg, dict):
                cd = msg.get("channel_data") or {}
                if isinstance(cd, dict):
                    text = (cd.get("text") or "").strip()

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
        log.info("Пропускаю — нет contact_id или текста")
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

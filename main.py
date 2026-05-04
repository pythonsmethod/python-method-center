# -*- coding: utf-8 -*-
# Python Method Center - main server
# FastAPI + SendPulse + Claude AI Agents + Stripe. Deploy: Railway.
import os
import logging
import stripe
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
import httpx

from agents import process_message, on_payment_confirmed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("python-method")

app = FastAPI(title="Python Method Center")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OFERTA_PATH = os.path.join(BASE_DIR, "Python Method Oferta v2.pdf")
OFERTA_URL = "https://python-method-center-production-24ec.up.railway.app/documents/oferta"

SENDPULSE_CLIENT_ID = os.environ.get("SENDPULSE_CLIENT_ID")
SENDPULSE_CLIENT_SECRET = os.environ.get("SENDPULSE_CLIENT_SECRET")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

sessions = {}


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
        log.error("No SendPulse token")
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


async def send_document(contact_id: str, document_url: str, caption: str = "") -> bool:
    token = await get_sendpulse_token()
    if not token:
        log.error("No SendPulse token")
        return False
    try:
        payload = {
            "contact_id": contact_id,
            "message": {
                "type": "document",
                "document": document_url,
            }
        }
        if caption:
            payload["message"]["caption"] = caption
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.post(
                "https://api.sendpulse.com/telegram/contacts/send",
                content=__import__('json').dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8"
                },
            )
            if r.status_code >= 400:
                log.error(f"SendPulse send_document {r.status_code}: {r.text}")
                return False
            return True
    except Exception as e:
        log.error(f"send_document error: {e}")
        return False


# ============================================================
# WEBHOOK PARSING
# ============================================================
def extract_event(body):
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
# SENDPULSE WEBHOOK
# ============================================================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        log.error(f"Bad JSON: {e}")
        return JSONResponse({"status": "bad_json"})

    log.info(f"Webhook received: {str(body)[:300]}")
    contact_id, text = extract_event(body)

    if not contact_id or not text:
        log.info(f"Ignoring - contact_id={contact_id}, text={text}")
        return JSONResponse({"status": "ignored"})

    log.info(f"[{contact_id}] -> {text[:100]}")

    try:
        reply = process_message(contact_id, text)
    except Exception as e:
        log.error(f"Agent error: {e}")
        reply = "Something went wrong. Please write again in a minute."

    send_oferta = "[SEND_OFERTA]" in reply
    if send_oferta:
        reply = reply.replace("[SEND_OFERTA]", "").strip()

    log.info(f"[{contact_id}] <- {reply[:100]}")
    sent = await send_message(contact_id, reply)

    if send_oferta and sent:
        log.info(f"[{contact_id}] -> sending oferta")
        await send_document(
            contact_id,
            OFERTA_URL,
            caption="Dogovor-oferta Python Method"
        )

    return JSONResponse({"status": "ok" if sent else "send_failed"})


# ============================================================
# STRIPE WEBHOOK
# ============================================================
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError as e:
        log.error(f"Stripe signature error: {e}")
        return JSONResponse({"status": "invalid_signature"}, status_code=400)
    except Exception as e:
        log.error(f"Stripe webhook parse error: {e}")
        return JSONResponse({"status": "error"}, status_code=400)

    log.info(f"Stripe event: {event['type']}")

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        client_reference_id = session_obj.get("client_reference_id")
        amount_total = session_obj.get("amount_total", 0)
        customer_details = session_obj.get("customer_details") or {}
        customer_name = customer_details.get("name", "")
        customer_email = customer_details.get("email", "")

        if amount_total == 111300:
            tariff_name = "Tariff Znakomstvo - $1113 / 6 weeks"
        elif amount_total == 472500:
            tariff_name = "Polnoe soprovozhdenie - $4725 / 21 weeks"
        else:
            tariff_name = f"Unknown tariff - {amount_total} cents"

        log.info(
            f"Payment confirmed: contact={client_reference_id}, "
            f"name={customer_name}, tariff={tariff_name}"
        )

        if client_reference_id:
            try:
                on_payment_confirmed(
                    contact_id=client_reference_id,
                    telegram_id=client_reference_id,
                    name=customer_name,
                    tariff=tariff_name,
                )
            except Exception as e:
                log.error(f"on_payment_confirmed error: {e}")

    return JSONResponse({"status": "ok"})


# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/")
async def root():
    return {"status": "Python Method Center is running"}


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/documents/oferta")
async def serve_oferta():
    return FileResponse(
        OFERTA_PATH,
        media_type="application/pdf",
        filename="Python_Method_Oferta.pdf"
    )

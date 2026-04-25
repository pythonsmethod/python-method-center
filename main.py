import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from agents import process_message
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ================================================================
# SENDPULSE — отправка сообщений
# ================================================================
async def get_token() -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.sendpulse.com/oauth/access_token",
            json={
                "grant_type": "client_credentials",
                "client_id": os.environ.get("SENDPULSE_CLIENT_ID"),
                "client_secret": os.environ.get("SENDPULSE_CLIENT_SECRET"),
            }
        )
        return r.json()["access_token"]


async def send_message(contact_id: str, text: str):
    token = await get_token()
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.sendpulse.com/telegram/contacts/sendByContactId",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "contact_id": contact_id,
                "messages": [{
                    "type": "text",
                    "message": {"text": text}
                }]
            }
        )


# ================================================================
# ВЕБХУК — сюда приходят сообщения из Telegram
# ================================================================
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    contact_id = body.get("contact", {}).get("id")
    text = body.get("message", {}).get("text", "").strip()

    if not contact_id or not text:
        return JSONResponse({"status": "ignored"})

    # Обрабатываем через агента
    reply = process_message(contact_id, text)

    # Отправляем ответ
    await send_message(contact_id, reply)

    return JSONResponse({"status": "ok"})


# ================================================================
# ПРОВЕРКА — что сервер живой
# ================================================================
@app.get("/")
async def root():
    return {"status": "Python Method Center работает 🍀"}

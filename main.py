import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from agents import process_message

app = FastAPI()

async def get_token():
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
                "messages": [{"type": "text", "message": {"text": text}}]
            }
        )

@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
        
        # SendPulse иногда присылает список
        if isinstance(body, list):
            body = body[0] if body else {}
        
        contact_id = None
        text = None
        
        # Пробуем разные форматы
        if isinstance(body, dict):
            contact = body.get("contact") or {}
            if isinstance(contact, dict):
                contact_id = contact.get("id")
            message = body.get("message") or {}
            if isinstance(message, dict):
                text = message.get("text", "").strip()
        
        if not contact_id or not text:
            return JSONResponse({"status": "ignored"})
        
        reply = process_message(contact_id, text)
        await send_message(contact_id, reply)
        return JSONResponse({"status": "ok"})
    
    except Exception as e:
        print(f"Ошибка: {e}")
        return JSONResponse({"status": "error", "detail": str(e)})

@app.get("/")
async def root():
    return {"status": "Python Method Center работает 🍀"}

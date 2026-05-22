# -*- coding: utf-8 -*-
# image_pipeline.py — Phase 4 Image/Media Pipeline Stabilization
# Handles photo, document, and file attachments from Telegram via SendPulse webhook.
# Additive module: does NOT break existing text message flow.
#
# Pipeline:
#   extract_attachment() — parse photo/document/file_id from SendPulse update body
#   download_telegram_file() — fetch file bytes via Telegram Bot API
#   ocr_extract_text() — extract text via OpenAI Vision (Claude Vision fallback)
#   build_attachment_context() — structured HAS_ATTACHMENTS context block
#   process_attachment_message() — top-level handler called from main.py webhook
#
# LOGGING:
#   [MEDIA] attachment_detected
#   [MEDIA] file_downloaded
#   [MEDIA] ocr_started
#   [MEDIA] ocr_success / ocr_failure
#   [MEDIA] extracted_text_length
#   [MEDIA] escalation_triggered

import os
import io
import base64
import logging
import httpx

log = logging.getLogger("image_pipeline")

# ─── Config ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")

_TELEGRAM_API = "https://api.telegram.org/bot{token}"
_TELEGRAM_FILE_URL = "https://api.telegram.org/file/bot{token}/{file_path}"

# OCR confidence threshold: if extracted text shorter than this, treat as low confidence
_MIN_OCR_TEXT_LEN = 30

# ─── Attachment Detection ─────────────────────────────────────────────────────

def extract_attachment(body: dict) -> dict | None:
    """
    Parse SendPulse webhook body and extract attachment metadata.

    Returns dict with keys:
        file_id       : Telegram file_id (str)
        attachment_type: "analysis_photo" | "document" | "photo"
        caption       : optional caption text
        mime_type     : mime type if known
    or None if no attachment found.
    """
    if not isinstance(body, dict):
        return None

    info = body.get("info") or {}
    if not isinstance(info, dict):
        info = {}

    # Walk the SendPulse nested structure to find channel_data
    msg1 = info.get("message") or body.get("message") or {}
    if not isinstance(msg1, dict):
        msg1 = {}

    cd = msg1.get("channel_data") or {}
    if not isinstance(cd, dict):
        cd = {}

    # Telegram compressed photo: message.channel_data.message.photo
    tg_msg = cd.get("message") or msg1
    if not isinstance(tg_msg, dict):
        tg_msg = {}

    caption = (tg_msg.get("caption") or cd.get("caption") or "").strip()

    # --- photo (compressed) ---
    photo_arr = tg_msg.get("photo") or cd.get("photo")
    if photo_arr and isinstance(photo_arr, list) and len(photo_arr) > 0:
        # Pick largest resolution (last item)
        best = photo_arr[-1]
        file_id = best.get("file_id", "")
        if file_id:
            log.info("[MEDIA] attachment_detected type=photo file_id=%.20s caption=%.60s",
                     file_id, caption)
            return {
                "file_id": file_id,
                "attachment_type": "analysis_photo",
                "caption": caption,
                "mime_type": "image/jpeg",
            }

    # --- document (file sent as document, including PDFs, PNGs sent uncompressed) ---
    doc = tg_msg.get("document") or cd.get("document")
    if doc and isinstance(doc, dict):
        file_id   = doc.get("file_id", "")
        mime_type = doc.get("mime_type", "application/octet-stream")
        file_name = doc.get("file_name", "")
        if file_id:
            atype = "document"
            if mime_type.startswith("image/") or file_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                atype = "analysis_photo"
            elif mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
                atype = "document"
            log.info("[MEDIA] attachment_detected type=%s mime=%s file_id=%.20s",
                     atype, mime_type, file_id)
            return {
                "file_id": file_id,
                "attachment_type": atype,
                "caption": caption,
                "mime_type": mime_type,
            }

    return None


# ─── Telegram File Download ───────────────────────────────────────────────────

async def download_telegram_file(file_id: str) -> bytes | None:
    """
    Download a Telegram file by file_id using Bot API.
    Returns raw bytes or None on failure.
    Requires TELEGRAM_BOT_TOKEN env variable.
    """
    if not TELEGRAM_BOT_TOKEN:
        log.error("[MEDIA] TELEGRAM_BOT_TOKEN not set — cannot download file")
        return None

    base = _TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: get file path
            r = await client.get(f"{base}/getFile", params={"file_id": file_id})
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                log.error("[MEDIA] getFile failed: %s", data)
                return None
            file_path = data["result"]["file_path"]

            # Step 2: download actual file
            file_url = _TELEGRAM_FILE_URL.format(token=TELEGRAM_BOT_TOKEN, file_path=file_path)
            r2 = await client.get(file_url)
            r2.raise_for_status()
            file_bytes = r2.content
            log.info("[MEDIA] file_downloaded file_id=%.20s size_bytes=%d", file_id, len(file_bytes))
            return file_bytes

    except Exception as e:
        log.error("[MEDIA] download_telegram_file error: %s", e)
        return None


# ─── OCR / Vision Extraction ──────────────────────────────────────────────────

async def ocr_extract_text(file_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Extract text from image/document bytes using OpenAI Vision.
    Falls back to Claude Vision if OpenAI not available.

    Returns:
        {
            "success": bool,
            "text": str,          # extracted text
            "confidence": str,    # "high" | "low" | "failed"
            "provider": str,      # "openai" | "claude" | "none"
            "error": str | None
        }
    """
    log.info("[MEDIA] ocr_started mime=%s size=%d", mime_type, len(file_bytes))

    if not file_bytes:
        return {"success": False, "text": "", "confidence": "failed", "provider": "none",
                "error": "empty file bytes"}

    b64 = base64.b64encode(file_bytes).decode("utf-8")

    # Try OpenAI Vision first
    if OPENAI_API_KEY:
        result = await _ocr_openai(b64, mime_type)
        if result["success"]:
            return result

    # Fallback: Claude Vision
    if ANTHROPIC_API_KEY:
        result = await _ocr_claude(b64, mime_type)
        if result["success"]:
            return result

    log.warning("[MEDIA] ocr_failure — no vision provider available")
    return {"success": False, "text": "", "confidence": "failed",
            "provider": "none", "error": "no vision provider configured"}


async def _ocr_openai(b64: str, mime_type: str) -> dict:
    """OCR via OpenAI gpt-4o Vision."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are a medical data extraction assistant. "
                            "Extract ALL text visible in this image exactly as shown. "
                            "Preserve table structure where possible. "
                            "Output only the extracted text, no commentary."
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"}
                    }
                ]
            }],
            max_tokens=2000,
        )
        text = response.choices[0].message.content.strip()
        confidence = "high" if len(text) >= _MIN_OCR_TEXT_LEN else "low"
        log.info("[MEDIA] ocr_success provider=openai confidence=%s extracted_text_length=%d",
                 confidence, len(text))
        return {"success": True, "text": text, "confidence": confidence,
                "provider": "openai", "error": None}
    except Exception as e:
        log.error("[MEDIA] ocr_failure provider=openai error=%s", e)
        return {"success": False, "text": "", "confidence": "failed",
                "provider": "openai", "error": str(e)}


async def _ocr_claude(b64: str, mime_type: str) -> dict:
    """OCR via Anthropic Claude Vision (claude-3-5-sonnet)."""
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        # Map mime_type to Anthropic media_type
        media_map = {
            "image/jpeg": "image/jpeg",
            "image/jpg":  "image/jpeg",
            "image/png":  "image/png",
            "image/gif":  "image/gif",
            "image/webp": "image/webp",
        }
        media_type = media_map.get(mime_type.lower(), "image/jpeg")

        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract ALL text visible in this image exactly as shown. "
                            "Preserve table structure where possible. "
                            "Output only the extracted text, no commentary."
                        )
                    }
                ]
            }],
        )
        text = response.content[0].text.strip()
        confidence = "high" if len(text) >= _MIN_OCR_TEXT_LEN else "low"
        log.info("[MEDIA] ocr_success provider=claude confidence=%s extracted_text_length=%d",
                 confidence, len(text))
        return {"success": True, "text": text, "confidence": confidence,
                "provider": "claude", "error": None}
    except Exception as e:
        log.error("[MEDIA] ocr_failure provider=claude error=%s", e)
        return {"success": False, "text": "", "confidence": "failed",
                "provider": "claude", "error": str(e)}


# ─── Context Builder ──────────────────────────────────────────────────────────

def build_attachment_context(attachment_meta: dict, ocr_result: dict) -> str:
    """
    Build a structured context string injected into the AI prompt.
    This replaces the empty/missing text so the AI pipeline never sees a blank message.

    Returns a string like:
        [ATTACHMENT_CONTEXT]
        HAS_ATTACHMENTS = true
        ATTACHMENT_TYPE = analysis_photo
        FILES_COUNT = 1
        OCR_CONFIDENCE = high
        EXTRACTED_TEXT:
        <text from OCR>
        [/ATTACHMENT_CONTEXT]
    """
    atype    = attachment_meta.get("attachment_type", "unknown")
    caption  = attachment_meta.get("caption", "")
    ocr_text = ocr_result.get("text", "")
    conf     = ocr_result.get("confidence", "failed")
    success  = ocr_result.get("success", False)

    lines = [
        "[ATTACHMENT_CONTEXT]",
        "HAS_ATTACHMENTS = true",
        f"ATTACHMENT_TYPE = {atype}",
        "FILES_COUNT = 1",
        f"OCR_CONFIDENCE = {conf}",
    ]
    if caption:
        lines.append(f"CAPTION = {caption}")
    if success and ocr_text:
        lines.append("EXTRACTED_TEXT:")
        lines.append(ocr_text)
    else:
        lines.append("EXTRACTED_TEXT: [OCR_FAILED_OR_EMPTY]")
    lines.append("[/ATTACHMENT_CONTEXT]")

    return "\n".join(lines)


# ─── Failsafe Response ────────────────────────────────────────────────────────

OCR_FAILSAFE_MESSAGE = (
    "Файл получен, но мне не удалось полностью распознать данные. "
    "Попробуйте отправить фото чуть ближе или более чётко."
)

ANALYSIS_COLLECTION_ACK = (
    "Спасибо, я получил ваш файл с анализами. "
    "Обрабатываю данные — это займёт несколько секунд."
)


# ─── Top-Level Handler ────────────────────────────────────────────────────────

async def process_attachment_message(
    contact_id: str,
    attachment_meta: dict,
    process_message_fn,   # callable: process_message(contact_id, text)
) -> str:
    """
    Full attachment handling pipeline:
    1. Download file from Telegram
    2. Run OCR
    3. Build context string
    4. Switch session into ANALYSIS_COLLECTION_MODE
    5. Call process_message with enriched text

    Returns the final AI reply string.
    """
    file_id   = attachment_meta.get("file_id", "")
    atype     = attachment_meta.get("attachment_type", "unknown")
    caption   = attachment_meta.get("caption", "")
    mime_type = attachment_meta.get("mime_type", "image/jpeg")

    log.info("[MEDIA] escalation_triggered contact=%s type=%s file_id=%.20s",
             contact_id, atype, file_id)

    # Step 1: Download
    file_bytes = await download_telegram_file(file_id)

    if not file_bytes:
        # Can't download — return failsafe
        log.warning("[MEDIA] download_failed contact=%s — returning failsafe", contact_id)
        return OCR_FAILSAFE_MESSAGE

    # Step 2: OCR
    ocr_result = await ocr_extract_text(file_bytes, mime_type)

    # Step 3: Build context
    ctx_str = build_attachment_context(attachment_meta, ocr_result)

    # Determine synthetic user message
    if ocr_result["success"] and len(ocr_result["text"]) >= _MIN_OCR_TEXT_LEN:
        # Pass OCR text as the user message so the full pipeline can process it
        synthetic_msg = ctx_str
        if caption:
            synthetic_msg = f"[CAPTION: {caption}]\n" + ctx_str
    elif caption:
        # No good OCR, but caption exists — use caption + partial context
        synthetic_msg = f"[CAPTION: {caption}]\n" + ctx_str
    else:
        # OCR failed, no caption — use failsafe
        log.warning("[MEDIA] ocr_confidence_low contact=%s — returning failsafe", contact_id)
        return OCR_FAILSAFE_MESSAGE

    # Step 4: Call existing process_message pipeline with enriched context
    try:
        reply = process_message_fn(contact_id, synthetic_msg)
    except Exception as e:
        log.error("[MEDIA] process_message_fn error: %s", e)
        reply = OCR_FAILSAFE_MESSAGE

    return reply


# ─── Utility: detect if update has attachment (used in main.py webhook) ───────

def has_attachment(body: dict) -> bool:
    """Fast check: does this webhook body contain a media attachment?"""
    return extract_attachment(body) is not None

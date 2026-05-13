# -*- coding: utf-8 -*-
# Python Method Center - main server
# FastAPI + SendPulse + Claude AI Agents + Stripe. Deploy: Railway.
import asyncio
import os
import logging
import stripe
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
import httpx

from agents import process_message, on_payment_confirmed
from ai_router import health_check as ai_health_check

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
        client_reference_id = getattr(session_obj, "client_reference_id", None)
        amount_total = getattr(session_obj, "amount_total", 0)
        customer_details = getattr(session_obj, "customer_details", None) or {}
        customer_name = getattr(customer_details, "name", "") if hasattr(customer_details, "name") else customer_details.get("name", "")
        customer_email = getattr(customer_details, "email", "") if hasattr(customer_details, "email") else customer_details.get("email", "")

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
    ai_status = ai_health_check()
    return {
        "ok": True,
        "ai_providers": ai_status,
        "claude_available": ai_status["claude"]["available"],
        "gpt_available": ai_status["gpt"]["available"],
    }


@app.get("/documents/oferta")
async def serve_oferta():
    return FileResponse(
        OFERTA_PATH,
        media_type="application/pdf",
        filename="Python_Method_Oferta.pdf"
    )


# =============================================================================
# PHASE 3.1A — MessagePipelineManager Wire-In
# Feature flags: USE_NEW_MESSAGE_PIPELINE, PIPELINE_SHADOW_MODE
# Safe rollback: set USE_NEW_MESSAGE_PIPELINE=false to revert instantly
# =============================================================================

import time as _time
import traceback as _traceback

# Feature flags (read from environment)
USE_NEW_MESSAGE_PIPELINE = os.environ.get("USE_NEW_MESSAGE_PIPELINE", "false").lower() == "true"
PIPELINE_SHADOW_MODE = os.environ.get("PIPELINE_SHADOW_MODE", "false").lower() == "true"

log.info("[PIPELINE_FLAG] USE_NEW_MESSAGE_PIPELINE=%s PIPELINE_SHADOW_MODE=%s",
         USE_NEW_MESSAGE_PIPELINE, PIPELINE_SHADOW_MODE)


# ---------------------------------------------------------------------------
# SendPulse Adapter for Pipeline
# Wraps send_message() so the pipeline can call bot.send_message()
# (pipeline expects an object with .send_message(chat_id, text) method)
# ---------------------------------------------------------------------------
class SendPulseAdapter:
    """Adapts SendPulse send_message() to pipeline bot interface."""

    def __init__(self):
        self._shadow_mode = PIPELINE_SHADOW_MODE

    async def send_message(self, contact_id, text, **kwargs):
        if self._shadow_mode:
            # Shadow mode: log only, do NOT send
            log.info("[SHADOW] PROPOSED_SEND contact=%s text=%.100r", contact_id, text)
            return True
        return await send_message(contact_id, text)

    async def send_chat_action(self, contact_id, action="typing"):
        # SendPulse does not support typing indicators natively
        # Log for metrics, skip actual send
        log.debug("[PIPELINE] Typing action contact=%s action=%s", contact_id, action)


# Initialize pipeline components (lazy, only if flag enabled)
_sendpulse_bot = None
_pipeline_instance = None


def _get_pipeline():
    """Lazy-initialize the pipeline (avoids import errors on startup if modules missing)."""
    global _sendpulse_bot, _pipeline_instance
    if _pipeline_instance is None:
        try:
            from orchestrator_core import get_pipeline
            _sendpulse_bot = SendPulseAdapter()
            _pipeline_instance = get_pipeline(bot=_sendpulse_bot)
            log.info("[PIPELINE] Pipeline initialized successfully")
        except Exception as e:
            log.error("[PIPELINE] Pipeline init FAILED: %s", e)
            log.error("[PIPELINE] Traceback: %s", _traceback.format_exc())
            _pipeline_instance = None
    return _pipeline_instance


async def _init_risk_predictor_with_retry():
    """Init risk predictor using DATABASE_URL — runs after startup workers start."""
    try:
        import asyncpg
        from risk_predictor import init_risk_predictor
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
        if not db_url:
            log.warning("[PIPELINE] RiskPredictor: no DATABASE_URL found — skipped")
            return
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3, command_timeout=30)
        await init_risk_predictor(pool)
        log.info("[PIPELINE] RiskPredictor initialized successfully")
    except Exception as e:
        log.warning("[PIPELINE] RiskPredictor init failed (non-fatal): %s", e)


async def _init_policy_engine():
    """Initialize RecoveryPolicyEngine with its own async DB pool. Non-fatal if fails."""
    try:
        import asyncpg
        DATABASE_URL = os.environ.get("DATABASE_URL", "")
        if not DATABASE_URL:
            log.warning("[PIPELINE] DATABASE_URL not set — RecoveryPolicyEngine skipped")
            return
        pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=2, command_timeout=30
        )
        from recovery_policy_engine import init_recovery_policy_engine
        init_recovery_policy_engine(db_pool=pool)
        log.info("[PIPELINE] RecoveryPolicyEngine initialized successfully")
    except Exception as e:
        log.warning("[PIPELINE] RecoveryPolicyEngine init failed (non-fatal): %s", e)


async def _init_dispatcher():
    """Initialize ProactiveMessageDispatcher. Non-fatal if fails."""
    try:
        import asyncpg
        DATABASE_URL = os.environ.get("DATABASE_URL", "")
        if not DATABASE_URL:
            log.warning("[PIPELINE] DATABASE_URL not set — ProactiveMessageDispatcher skipped")
            return
        pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=2, command_timeout=30
        )
        from proactive_message_dispatcher import init_dispatcher
        # Use the module-level send_message function as the approved send path
        init_dispatcher(db_pool=pool, send_message_fn=send_message)
        log.info("[PIPELINE] ProactiveMessageDispatcher initialized successfully")
    except Exception as e:
        log.warning("[PIPELINE] ProactiveMessageDispatcher init failed (non-fatal): %s", e)


async def _init_scanner():
    """Initialise SilentUserScanner singleton with DB pool. Fail-safe."""
    try:
        import asyncpg
        from silent_user_scanner import init_scanner
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
        if not db_url:
            log.warning("[SCANNER] _init_scanner: no DATABASE_URL — skipped")
            return
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3, command_timeout=30)
        scanner = init_scanner(db_pool=pool)
        log.info("[SCANNER] SilentUserScanner initialized in main")
    except Exception as e:
        log.warning("[SCANNER] _init_scanner failed (non-fatal): %s", e)



async def _init_behaviour_engine():
    """Initialise AdaptiveBehaviourEngine singleton. Fail-safe: non-fatal on any error."""
    try:
        from adaptive_behaviour_engine import init_behaviour_engine
        engine = init_behaviour_engine()
        log.info("[BEHAVIOUR] AdaptiveBehaviourEngine initialized in main")
    except Exception as e:
        log.warning("[BEHAVIOUR] _init_behaviour_engine failed (non-fatal): %s", e)


async def _start_pipeline_workers():
    """Start pipeline background workers. Called at startup if flag enabled."""
    try:
        pipeline = _get_pipeline()
        if pipeline:
            await pipeline.start()
            log.info("[PIPELINE] Background workers started")
        from async_task_worker import async_worker
        await async_worker.start()
        log.info("[PIPELINE] AsyncTaskWorker started")
        # Init RiskPredictor with retry — pool may not be ready immediately at startup
        asyncio.create_task(_init_risk_predictor_with_retry())
        asyncio.create_task(_init_policy_engine())
        asyncio.create_task(_init_dispatcher())
        asyncio.create_task(_init_scanner())
        asyncio.create_task(_init_behaviour_engine())
    except Exception as e:
        log.error("[PIPELINE] Worker start FAILED: %s", e)
        log.error("[PIPELINE] Traceback: %s", _traceback.format_exc())


# ---------------------------------------------------------------------------
# Pipeline metrics logger
# ---------------------------------------------------------------------------
def _log_pipeline_metrics(contact_id: str, metrics: dict):
    """Log per-message pipeline metrics."""
    log.info(
        "[PIPELINE_METRICS] contact=%s queue_depth=%s debounce_wait_ms=%s "
        "fast_path_hit=%s stale_discarded=%s orchestration_ms=%s "
        "total_latency_ms=%s timeout_used=%s model_tier=%s "
        "active_agent=%s route=%s stage=%s",
        contact_id,
        metrics.get("queue_depth", "?"),
        metrics.get("debounce_wait_ms", "?"),
        metrics.get("fast_path_hit", "?"),
        metrics.get("stale_discarded", "?"),
        metrics.get("orchestration_ms", "?"),
        metrics.get("total_latency_ms", "?"),
        metrics.get("timeout_used", "?"),
        metrics.get("model_tier", "?"),
        metrics.get("active_agent", "?"),
        metrics.get("route", "?"),
        metrics.get("stage", "?"),
    )


# ---------------------------------------------------------------------------
# Shadow mode runner
# Old pipeline sends real response; new pipeline runs in observe-only mode
# ---------------------------------------------------------------------------
async def _run_shadow_pipeline(contact_id: str, text: str, t_start: float):
    """Run new pipeline in shadow mode: observe, log, do NOT send."""
    try:
        from fast_path_resolver import fast_path_resolver, FastPathIntent
        from stale_response_guard import stale_guard
        from message_queue import message_queue
        from debounce_manager import debounce_manager

        # Fast path detection
        fp_intent, fp_response = fast_path_resolver.resolve(text)
        fast_path_hit = fp_intent.value != "none"

        # Queue depth
        contact_hash = hash(contact_id) % 1000000  # Stable numeric ID from string
        queue_depth = message_queue.queue_size(contact_hash)

        t_pipeline_start = _time.monotonic()
        # Run old pipeline to get proposed response for comparison
        try:
            proposed = process_message(contact_id, text)
        except Exception as _pe:
            proposed = f"[ERROR: {_pe}]"
        orchestration_ms = int((_time.monotonic() - t_pipeline_start) * 1000)
        total_ms = int((_time.monotonic() - t_start) * 1000)

        # Extract route/agent from session if available
        session = sessions.get(contact_id, {})
        route = session.get("current_route", "unknown")
        agent = session.get("active_agent", "unknown")
        stage = session.get("current_stage", "unknown")

        _log_pipeline_metrics(contact_id, {
            "queue_depth": queue_depth,
            "debounce_wait_ms": 0,  # Shadow: no debounce applied
            "fast_path_hit": fast_path_hit,
            "stale_discarded": 0,
            "orchestration_ms": orchestration_ms,
            "total_latency_ms": total_ms,
            "timeout_used": False,
            "model_tier": "standard",
            "active_agent": agent,
            "route": route,
            "stage": stage,
        })

        log.info("[SHADOW] contact=%s fast_path=%s fp_intent=%s proposed_len=%d orch_ms=%d",
                 contact_id, fast_path_hit, fp_intent.value, len(proposed), orchestration_ms)

        if fast_path_hit and fp_response:
            log.info("[SHADOW] FAST_PATH_WOULD_RESPOND contact=%s intent=%s response=%.80r",
                     contact_id, fp_intent.value, fp_response)

        return proposed  # Return for old pipeline to send

    except Exception as e:
        log.error("[SHADOW] Shadow pipeline error: %s", e)
        log.error("[SHADOW] Traceback: %s", _traceback.format_exc())
        # Fall through to old pipeline
        return process_message(contact_id, text)


# ---------------------------------------------------------------------------
# New SendPulse webhook with pipeline feature flag
# Replaces the original @app.post("/webhook") handler
# ---------------------------------------------------------------------------
@app.post("/webhook/v2")
async def webhook_v2(request: Request):
    """
    Enhanced webhook handler with MessagePipeline feature flag.
    USE_NEW_MESSAGE_PIPELINE=true  -> full new pipeline
    PIPELINE_SHADOW_MODE=true       -> old pipeline sends, new observes
    Both false                      -> pure old pipeline (no change)
    """
    t_start = _time.monotonic()

    try:
        body = await request.json()
    except Exception as e:
        log.error(f"Bad JSON: {e}")
        return JSONResponse({"status": "bad_json"})

    log.info(f"[WEBHOOK_V2] received: {str(body)[:300]}")
    contact_id, text = extract_event(body)

    if not contact_id or not text:
        log.info(f"[WEBHOOK_V2] Ignoring - contact_id={contact_id}, text={text}")
        return JSONResponse({"status": "ignored"})

    log.info(f"[WEBHOOK_V2] contact={contact_id} text={text[:100]}")

    # ------------------------------------------------------------------
    # BRANCH A: Shadow Mode (observe new pipeline, old sends)
    # ------------------------------------------------------------------
    if PIPELINE_SHADOW_MODE and not USE_NEW_MESSAGE_PIPELINE:
        log.info("[SHADOW_MODE] Running shadow observation for contact=%s", contact_id)
        try:
            reply = await _run_shadow_pipeline(contact_id, text, t_start)
        except Exception as e:
            log.error("[SHADOW_MODE] Error: %s", e)
            try:
                reply = process_message(contact_id, text)
            except Exception as e2:
                log.error("[SHADOW_MODE] Fallback also failed: %s", e2)
                reply = "Something went wrong. Please write again in a minute."

        send_oferta = "[SEND_OFERTA]" in reply
        if send_oferta:
            reply = reply.replace("[SEND_OFERTA]", "").strip()
        log.info(f"[SHADOW_MODE] contact={contact_id} <- {reply[:100]}")
        sent = await send_message(contact_id, reply)
        if send_oferta and sent:
            await send_document(contact_id, OFERTA_URL, caption="Dogovor-oferta Python Method")
        return JSONResponse({"status": "ok" if sent else "send_failed", "mode": "shadow"})

    # ------------------------------------------------------------------
    # BRANCH B: New Pipeline (full activation)
    # ------------------------------------------------------------------
    if USE_NEW_MESSAGE_PIPELINE:
        log.info("[NEW_PIPELINE] Routing through MessagePipelineManager contact=%s", contact_id)
        try:
            pipeline = _get_pipeline()
            if pipeline is None:
                raise RuntimeError("Pipeline not initialized")

            # Use hash-stable numeric ID (pipeline expects int)
            contact_hash = hash(contact_id) % 1000000
            import random
            msg_id = random.randint(1, 999999)

            t_pipeline_start = _time.monotonic()
            await pipeline.incoming(
                user_id=contact_hash,
                message_id=msg_id,
                text=text,
                chat_id=contact_id,  # pipeline uses this for send_message()
                raw_update={"contact_id": contact_id, "body": body}
            )
            pipeline_ms = int((_time.monotonic() - t_pipeline_start) * 1000)
            total_ms = int((_time.monotonic() - t_start) * 1000)

            # Log metrics
            from message_queue import message_queue
            queue_depth = message_queue.queue_size(contact_hash)
            _log_pipeline_metrics(contact_id, {
                "queue_depth": queue_depth,
                "debounce_wait_ms": pipeline_ms,
                "fast_path_hit": "?",
                "stale_discarded": "?",
                "orchestration_ms": pipeline_ms,
                "total_latency_ms": total_ms,
                "timeout_used": False,
                "model_tier": "auto",
                "active_agent": "pipeline",
                "route": "pipeline",
                "stage": "pipeline",
            })

            return JSONResponse({"status": "ok", "mode": "new_pipeline", "pipeline_ms": pipeline_ms})

        except Exception as e:
            log.error("[NEW_PIPELINE] FAILED: %s", e)
            log.error("[NEW_PIPELINE] Traceback: %s", _traceback.format_exc())
            log.warning("[NEW_PIPELINE] Falling back to old pipeline for contact=%s", contact_id)
            # SAFE ROLLBACK: fall through to old pipeline
            # User MUST get a response — never leave in silence

    # ------------------------------------------------------------------
    # BRANCH C: Old Pipeline (original flow, unchanged)
    # ------------------------------------------------------------------
    try:
        reply = process_message(contact_id, text)
    except Exception as e:
        log.error(f"[OLD_PIPELINE] Agent error: {e}")
        reply = "Something went wrong. Please write again in a minute."

    send_oferta = "[SEND_OFERTA]" in reply
    if send_oferta:
        reply = reply.replace("[SEND_OFERTA]", "").strip()

    total_ms = int((_time.monotonic() - t_start) * 1000)
    log.info(f"[OLD_PIPELINE] contact={contact_id} reply_len={len(reply)} total_ms={total_ms}")
    sent = await send_message(contact_id, reply)

    if send_oferta and sent:
        await send_document(contact_id, OFERTA_URL, caption="Dogovor-oferta Python Method")

    return JSONResponse({"status": "ok" if sent else "send_failed", "mode": "old_pipeline"})


# ---------------------------------------------------------------------------
# Startup event: start pipeline workers if flag enabled
# ---------------------------------------------------------------------------
@app.get("/risk/governance")
async def risk_governance():
    """
    Recovery governance dashboard endpoint.
    Returns combined policy engine + dispatcher metrics.
    """
    try:
        result = {}
        # Policy engine data
        try:
            from recovery_policy_engine import get_recovery_policy_engine
            engine = get_recovery_policy_engine()
            if engine:
                result["policy"] = await engine.get_dashboard_data()
        except Exception as e:
            result["policy"] = {"error": str(e)}
        # Dispatcher data
        try:
            from proactive_message_dispatcher import get_dispatcher
            dispatcher = get_dispatcher()
            if dispatcher:
                result["dispatch"] = await dispatcher.get_dispatch_dashboard()
        except Exception as e:
            result["dispatch"] = {"error": str(e)}
        # Dashboard data
        try:
            from dashboard_data import get_dashboard
            dash = get_dashboard()
            result["recovery_governance"] = await dash.get_recovery_governance()
        except Exception as e:
            result["recovery_governance"] = {"error": str(e)}
        return JSONResponse(content=result)
    except Exception as e:
        log.error("[API] /risk/governance error: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.on_event("startup")
async def on_startup():
    log.info("[STARTUP] USE_NEW_MESSAGE_PIPELINE=%s PIPELINE_SHADOW_MODE=%s",
             USE_NEW_MESSAGE_PIPELINE, PIPELINE_SHADOW_MODE)
    if USE_NEW_MESSAGE_PIPELINE or PIPELINE_SHADOW_MODE:
        log.info("[STARTUP] Starting pipeline workers...")
        await _start_pipeline_workers()
    else:
        log.info("[STARTUP] Pipeline inactive (USE_NEW_MESSAGE_PIPELINE=false, PIPELINE_SHADOW_MODE=false)")


# ---------------------------------------------------------------------------
# Pipeline health endpoint
# ---------------------------------------------------------------------------
@app.get("/pipeline/health")
async def pipeline_health():
    """Returns pipeline status, feature flags, and queue stats."""
    stats = {
        "use_new_pipeline": USE_NEW_MESSAGE_PIPELINE,
        "shadow_mode": PIPELINE_SHADOW_MODE,
        "pipeline_initialized": _pipeline_instance is not None,
    }
    if _pipeline_instance:
        try:
            stats["pipeline_stats"] = _pipeline_instance.get_stats()
        except Exception as e:
            stats["pipeline_stats_error"] = str(e)
    try:
        from async_task_worker import async_worker
        stats["worker_stats"] = async_worker.get_stats()
    except Exception as e:
        stats["worker_stats_error"] = str(e)
    return JSONResponse(stats)

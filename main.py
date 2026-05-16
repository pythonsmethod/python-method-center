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

from agents import process_message, on_payment_confirmed, load_session, save_session
from ai_router import health_check as ai_health_check, ask_claude

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
# Phase 4 Step 6: In-memory OAuth token cache.
# Eliminates one HTTP round-trip per message (was: OAuth + send, now: send only on cache hit).
_sp_token_lock = asyncio.Lock()
_sp_token_cache: dict = {"token": None, "expires_at": 0.0}
_SP_TOKEN_TTL = 3600        # SendPulse access_token lifetime (seconds)
_SP_TOKEN_BUFFER = 60       # Refresh 60s before actual expiry (safety buffer)


async def get_sendpulse_token() -> "str | None":
    """
    Return a valid SendPulse OAuth access token.
    Uses in-memory cache with 3600s TTL and 60s safety buffer.
    Async-safe via asyncio.Lock (prevents concurrent refresh storms).
    Falls back to a fresh OAuth request if cache is broken.
    Token value is NEVER logged.
    """
    import time as _t_sp
    # Fast path: read cache without lock (asyncio is single-threaded)
    _cached = _sp_token_cache.get("token")
    _expires = _sp_token_cache.get("expires_at", 0.0)
    if _cached and _t_sp.monotonic() < _expires - _SP_TOKEN_BUFFER:
        log.debug("[SENDPULSE_TOKEN] cache_hit expires_in=%.0fs", _expires - _t_sp.monotonic())
        return _cached

    # Slow path: acquire lock to prevent concurrent refreshes
    async with _sp_token_lock:
        # Double-check inside lock (another coroutine may have refreshed while we waited)
        _cached = _sp_token_cache.get("token")
        _expires = _sp_token_cache.get("expires_at", 0.0)
        if _cached and _t_sp.monotonic() < _expires - _SP_TOKEN_BUFFER:
            log.debug("[SENDPULSE_TOKEN] cache_hit (post-lock) expires_in=%.0fs",
                      _expires - _t_sp.monotonic())
            return _cached

        # Actual OAuth refresh
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
                new_token = r.json().get("access_token")
                if new_token:
                    _sp_token_cache["token"] = new_token
                    _sp_token_cache["expires_at"] = _t_sp.monotonic() + _SP_TOKEN_TTL
                    log.info("[SENDPULSE_TOKEN] refreshed ttl=%ds buffer=%ds",
                             _SP_TOKEN_TTL, _SP_TOKEN_BUFFER)
                    return new_token
                log.error("[SENDPULSE_TOKEN] refresh_failed: no access_token in response")
                return None
        except Exception as _sp_err:
            log.error("[SENDPULSE_TOKEN] refresh_failed: %s", _sp_err)
            # Safety: clear stale cache so next attempt retries cleanly
            _sp_token_cache["token"] = None
            _sp_token_cache["expires_at"] = 0.0
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

    t_start_main = _time.monotonic()
    try:
        reply = process_message(contact_id, text)
    except Exception as e:
        log.error(f"Agent error: {e}")
        reply = "Something went wrong. Please write again in a minute."

    # ── PHASE 4 STEP 4: Shadow observation (non-blocking, observe-only) ──────
    if PIPELINE_SHADOW_MODE:
        asyncio.create_task(
            _shadow_observe(
                contact_id=contact_id,
                text=text,
                old_reply=reply,
                t_start=t_start_main,
                raw_update=body,
            )
        )

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


async def _init_continuity_engine():
    """Initialise ClinicalContinuityEngine singleton. Fail-safe: non-fatal on any error."""
    try:
        from clinical_continuity_engine import init_continuity_engine
        engine = init_continuity_engine()
        log.info("[CONTINUITY] ClinicalContinuityEngine initialized in main")
    except Exception as e:
        log.warning("[CONTINUITY] _init_continuity_engine failed (non-fatal): %s", e)


async def _init_trajectory_engine():
    """Initialise TrajectoryIntelligenceEngine singleton. Fail-safe: non-fatal on any error."""
    try:
        from trajectory_intelligence_engine import init_trajectory_engine
        await init_trajectory_engine()
        log.info("[TRAJECTORY] TrajectoryIntelligenceEngine initialized in main")
    except Exception as e:
        log.warning("[TRAJECTORY] _init_trajectory_engine failed (non-fatal): %s", e)


async def _init_state_machine():
    """Initialise RehabilitationStateMachine singleton. Fail-safe: non-fatal on any error."""
    try:
        from rehabilitation_state_machine import init_state_machine
        await init_state_machine()
        log.info("[STATE_MACHINE] RehabilitationStateMachine initialized in main")
    except Exception as e:
        log.warning("[STATE_MACHINE] _init_state_machine failed (non-fatal): %s", e)


async def _init_orchestration_engine():
    """Initialise MultiStageOrchestrationEngine singleton. Fail-safe: non-fatal on any error."""
    try:
        from multi_stage_orchestration_engine import init_orchestration_engine
        await init_orchestration_engine()
        log.info("[ORCHESTRATION] MultiStageOrchestrationEngine initialized in main")
    except Exception as e:
        log.warning("[ORCHESTRATION] _init_orchestration_engine failed (non-fatal): %s", e)


async def _init_pacing_engine():
    """Initialise DynamicPacingEngine singleton. Fail-safe: non-fatal on any error."""
    try:
        from dynamic_pacing_intelligence import init_pacing_engine
        await init_pacing_engine()
        log.info("[PACING] DynamicPacingEngine initialized in main")
    except Exception as e:
        log.warning("[PACING] _init_pacing_engine failed (non-fatal): %s", e)


async def _init_load_balancing_engine():
    """Phase 3.12 — Initialize Expert Load Balancing Intelligence singleton. Fail-safe."""
    try:
        from expert_load_balancing_engine import init_load_balancing_engine
        await init_load_balancing_engine()
        log.info("[LOAD_BALANCING] ExpertLoadBalancingEngine initialized in main")
    except Exception as e:
        log.warning("[LOAD_BALANCING] ExpertLoadBalancingEngine init failed (non-fatal): %s", e)


async def _init_cognitive_orchestrator():
    """Phase 3.13 — Initialize CentralCognitiveOrchestrator singleton. Fail-safe."""
    try:
        from central_cognitive_orchestrator import init_cognitive_orchestrator
        await init_cognitive_orchestrator()
        log.info("[COGNITIVE] CentralCognitiveOrchestrator initialized in main")
    except Exception as e:
        log.warning("[COGNITIVE] CentralCognitiveOrchestrator init failed (non-fatal): %s", e)


async def _init_longitudinal_modeling():
    """Phase 3.14 — Initialize Longitudinal Rehabilitation Modeling singleton. Fail-safe."""
    try:
        from longitudinal_rehabilitation_modeling import init_longitudinal_modeling_engine
        await init_longitudinal_modeling_engine()
        log.info("[LONGITUDINAL] Longitudinal Rehabilitation Modeling initialized in main")
    except Exception as e:
        log.warning("[LONGITUDINAL] Longitudinal Modeling init failed (non-fatal): %s", e)

async def _init_adaptive_strategy():
    """Phase 3.15 — Initialize AdaptiveRehabilitationStrategyEngine singleton. Fail-safe."""
    try:
        from adaptive_rehabilitation_strategy import init_adaptive_strategy_engine
        await init_adaptive_strategy_engine()
        log.info("[STRATEGY] AdaptiveRehabilitationStrategyEngine initialized in main")
    except Exception as e:
                log.warning("[STRATEGY] Adaptive Strategy init failed (non-fatal): %s", e)
        

async def _init_route_simulation():
    """Phase 3.16 — Initialize RehabilitationRouteSimulationEngine singleton. Fail-safe."""
    try:
        from rehabilitation_route_simulation import init_route_simulation_engine
        await init_route_simulation_engine()
        log.info("[ROUTE_SIM] RehabilitationRouteSimulationEngine initialized in main")
    except Exception as e:
        log.warning("[ROUTE_SIM] Route Simulation init failed (non-fatal): %s", e)
       
async def _init_self_stabilizing_governance():
    """Phase 3.17 — Initialize SelfStabilizingGovernanceEngine singleton. Fail-safe."""
    try:
        from self_stabilizing_governance import init_governance_stabilization_engine
        await init_governance_stabilization_engine()
        log.info("[GOV_STAB] SelfStabilizingGovernanceEngine initialized in main")
    except Exception as e:
        log.warning("[GOV_STAB] Self-Stabilizing Governance init failed (non-fatal): %s", e)

async def _init_meta_continuity_loop():
    """Phase 3.18 — Initialize MetaContinuityEngine. Fail-safe."""
    try:
        from meta_continuity_intelligence import init_meta_continuity_engine
        import asyncpg
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
        if not db_url:
            log.warning("[META_CONT] No DATABASE_URL found — skipped")
            return
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2, command_timeout=30)
        await init_meta_continuity_engine(pool)
        log.info("[META_CONT] MetaContinuityEngine initialized in main")
    except Exception as e:
        log.warning("[META_CONT] Meta-Continuity init failed (non-fatal): %s", e)


async def _meta_continuity_loop():
    """Phase 3.18 — Center-wide background continuity loop. Runs every 10 min."""
    await asyncio.sleep(300)
    while True:
        try:
            from meta_continuity_intelligence import evaluate_meta_continuity
            result = await evaluate_meta_continuity()
            log.info(
                "[META_CONT] state=%s health=%.3f sample=%s",
                result.get("meta_continuity_state", "UNKNOWN"),
                result.get("global_continuity_health_score", 0.0),
                result.get("sample_size", 0),
            )
        except Exception as e:
            log.debug("[META_CONT] loop error: %s", e)
        await asyncio.sleep(600)

async def _init_institutional_memory_loop():
    """Phase 3.19 — Initialize InstitutionalMemoryEngine. Fail-safe."""
    try:
        from institutional_memory_intelligence import init_institutional_memory_engine
        import asyncpg
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
        if not db_url:
            log.warning("[INST_MEM] No DATABASE_URL found — skipped")
            return
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2, command_timeout=30)
        await init_institutional_memory_engine(pool)
        log.info("[INST_MEM] InstitutionalMemoryEngine initialized in main")
    except Exception as e:
        log.warning("[INST_MEM] Institutional Memory init failed (non-fatal): %s", e)


async def _institutional_memory_loop():
    """Phase 3.19 — Periodic institutional memory snapshot. Runs every 30 min."""
    await asyncio.sleep(600)
    while True:
        try:
            from institutional_memory_intelligence import evaluate_institutional_memory
            result = await evaluate_institutional_memory()
            log.info(
                "[INST_MEM] state=%s stability=%.3f sample=%s",
                result.get("institutional_memory_state", "UNKNOWN"),
                result.get("institutional_stability_score", 0.0),
                result.get("historical_sample_size", 0),
            )
        except Exception as e:
            log.debug("[INST_MEM] loop error: %s", e)
        await asyncio.sleep(1800)



 


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
        asyncio.create_task(_init_continuity_engine())
        asyncio.create_task(_init_trajectory_engine())
        asyncio.create_task(_init_state_machine())
        asyncio.create_task(_init_orchestration_engine())
        asyncio.create_task(_init_pacing_engine())
        asyncio.create_task(_init_load_balancing_engine())
        asyncio.create_task(_init_cognitive_orchestrator())
        asyncio.create_task(_init_longitudinal_modeling())
        asyncio.create_task(_init_adaptive_strategy())
        asyncio.create_task(_init_route_simulation())
        asyncio.create_task(_init_self_stabilizing_governance())
        asyncio.create_task(_init_meta_continuity_loop())
        asyncio.create_task(_meta_continuity_loop())
        asyncio.create_task(_init_institutional_memory_loop())
        asyncio.create_task(_institutional_memory_loop())
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
# ---------------------------------------------------------------------------
# PHASE 4 STEP 4: Noop session saver for shadow mode (never writes production)
# ---------------------------------------------------------------------------
async def _noop_save_session(updated_session):
    """Shadow mode: discard session update — do NOT write to production DB."""
    return None


# ---------------------------------------------------------------------------
# PHASE 4 STEP 4: Real shadow observe — compares OrchestratorCore vs old flow
# Fires as asyncio.create_task from /webhook — non-blocking, observe-only
# CRITICAL: never sends message, never saves production session
# ---------------------------------------------------------------------------
async def _shadow_observe(
    contact_id: str,
    text: str,
    old_reply: str,
    t_start: float,
    raw_update=None,
):
    """
    Run OrchestratorCore.handle_message in observe-only mode alongside old flow.
    - Loads real session (read-only copy for shadow)
    - Calls handle_message with shadow_mode=True
    - Compares route/intent/agent/escalation/reply_len vs old flow
    - Logs [SHADOW_COMPARE] / [SHADOW_MISMATCH]
    - Does NOT send any message to user
    - Does NOT persist shadow session
    - Does NOT write memory (shadow_mode=True disables it)
    """
    t0 = _time.monotonic()
    try:
        # 1. Load real session (read-only copy for shadow)
        try:
            shadow_session = await asyncio.to_thread(load_session, contact_id)
        except Exception as _lse:
            log.warning("[SHADOW_OBSERVE] load_session failed contact=%s: %s", contact_id, _lse)
            shadow_session = {}

        # Make a safe copy so we never mutate production session
        import copy
        shadow_session = copy.deepcopy(shadow_session)

        # 2. Extract route/intent/agent from old session BEFORE shadow runs
        old_route = shadow_session.get("current_route") or shadow_session.get("route", "unknown")
        old_intent = shadow_session.get("current_intent", "unknown")
        old_agent = shadow_session.get("agent_current") or shadow_session.get("active_agent", "unknown")
        old_escalation = shadow_session.get("escalation_flag", False)

        # 3. Stable numeric user_id for OrchestratorCore
        contact_hash = abs(hash(contact_id)) % (2**31)

        # 4. Async wrapper for ask_claude (sync → async)
        async def _ask_claude_shadow(system_prompt, messages, **kwargs):
            return await asyncio.to_thread(ask_claude, system_prompt, messages)

        # 5. Get or init pipeline (uses existing singleton)
        pipeline = await asyncio.to_thread(_get_pipeline)

        if pipeline is None or pipeline.orchestrator is None:
            log.warning("[SHADOW_OBSERVE] OrchestratorCore not available, skipping contact=%s", contact_id)
            return

        orchestrator = pipeline.orchestrator

        # 6. Call OrchestratorCore with shadow_mode=True
        t_orch = _time.monotonic()
        try:
            orch_result = await orchestrator.handle_message(
                user_id=contact_hash,
                message_text=text,
                session=shadow_session,
                ask_claude_fn=_ask_claude_shadow,
                save_session_fn=_noop_save_session,
                shadow_mode=True,
            )
        except Exception as _oe:
            log.error("[SHADOW_OBSERVE] OrchestratorCore error contact=%s: %s", contact_id, _oe)
            log.error("[SHADOW_OBSERVE] Traceback: %s", _traceback.format_exc())
            return
        orch_ms = int((_time.monotonic() - t_orch) * 1000)

        # 7. Extract shadow results
        if hasattr(orch_result, "reply"):
            shadow_reply = orch_result.reply or ""
            shadow_route = getattr(orch_result, "route", "unknown")
            shadow_intent = getattr(orch_result, "intent", "unknown")
            shadow_agent = getattr(orch_result, "agent", "unknown")
            shadow_escalation = getattr(orch_result, "escalate", False)
        else:
            shadow_reply = str(orch_result) if orch_result else ""
            shadow_route = shadow_session.get("current_route", "unknown")
            shadow_intent = shadow_session.get("current_intent", "unknown")
            shadow_agent = shadow_session.get("active_agent", "unknown")
            shadow_escalation = False

        # 8. Compare
        total_ms = int((_time.monotonic() - t0) * 1000)
        route_match = (old_route == shadow_route)
        intent_match = (old_intent == shadow_intent)
        agent_match = (old_agent == shadow_agent)
        escalation_match = (old_escalation == shadow_escalation)
        full_match = route_match and intent_match and agent_match and escalation_match

        # 9. Log comparison
        log.info(
            "[SHADOW_COMPARE] contact_id=%s "
            "old_route=%s shadow_route=%s route_match=%s "
            "old_intent=%s shadow_intent=%s intent_match=%s "
            "old_agent=%s shadow_agent=%s agent_match=%s "
            "escalation_match=%s "
            "old_reply_len=%d shadow_reply_len=%d "
            "latency_ms=%d orch_ms=%d error=false",
            contact_id,
            old_route, shadow_route, route_match,
            old_intent, shadow_intent, intent_match,
            old_agent, shadow_agent, agent_match,
            escalation_match,
            len(old_reply), len(shadow_reply),
            total_ms, orch_ms,
        )

        if not full_match:
            reasons = []
            if not route_match:    reasons.append("route_mismatch")
            if not intent_match:   reasons.append("intent_mismatch")
            if not agent_match:    reasons.append("agent_mismatch")
            if not escalation_match: reasons.append("escalation_mismatch")
            log.warning(
                "[SHADOW_MISMATCH] contact_id=%s reason=%s "
                "old_route=%s shadow_route=%s "
                "old_intent=%s shadow_intent=%s "
                "old_agent=%s shadow_agent=%s",
                contact_id, ",".join(reasons),
                old_route, shadow_route,
                old_intent, shadow_intent,
                old_agent, shadow_agent,
            )

    except Exception as _ex:
        log.error("[SHADOW_OBSERVE] Unexpected error contact=%s: %s", contact_id, _ex)
        log.error("[SHADOW_OBSERVE] Traceback: %s", _traceback.format_exc())


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
        log.info("[SHADOW_MODE] Running shadow observation via /webhook/v2 for contact=%s", contact_id)
        try:
            reply = process_message(contact_id, text)
        except Exception as e:
            log.error("[SHADOW_MODE] Old pipeline error: %s", e)
            reply = "Something went wrong. Please write again in a minute."
        # Fire shadow observe task (non-blocking, observe-only)
        asyncio.create_task(
            _shadow_observe(
                contact_id=contact_id,
                text=text,
                old_reply=reply,
                t_start=t_start,
                raw_update=body,
            )
        )

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
        # Phase 3.19: Institutional Memory dashboard stats
        try:
            from dashboard_data import get_institutional_memory_stats
            import asyncpg as _asyncpg
            _im_db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
            if _im_db_url:
                _im_pool = await _asyncpg.create_pool(_im_db_url, min_size=1, max_size=1, command_timeout=10)
                result["institutional_memory"] = await get_institutional_memory_stats(_im_pool)
                await _im_pool.close()
            else:
                result["institutional_memory"] = {"engine": "InstitutionalMemoryEngine", "error": "no_db"}
        except Exception as e:
            result["institutional_memory"] = {"engine": "InstitutionalMemoryEngine", "error": str(e)}
        return JSONResponse(content=result)
    except Exception as e:
        log.error("[API] /risk/governance error: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.on_event("startup")
async def on_startup():
    log.info("[STARTUP] Phase 3.19 InstitutionalMemoryEngine — background-only, fail-safe, neutral_result on all exceptions")
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

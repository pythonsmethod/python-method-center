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
# PHASE 4 STEP 7: Shadow Analytics — structured storage + aggregated metrics
# ---------------------------------------------------------------------------
import collections as _collections
import datetime as _datetime
import statistics as _statistics

# In-memory ring buffer for shadow analytics (max 10 000 entries)
_SHADOW_ANALYTICS_MAXLEN = 10_000
_shadow_analytics_buf = None  # init in _shadow_analytics_init
_shadow_analytics_lock = None  # asyncio.Lock — init lazily

# High-risk routes/intents that require extra alerting
_SHADOW_HIGH_RISK_ROUTES = frozenset({
    "crisis", "fear", "escalation", "payment", "onboarding",
    "emergency", "mental_health", "self_harm",
})
_SHADOW_HIGH_RISK_INTENTS = frozenset({
    "escalate", "crisis", "payment_issue", "fear_expression",
    "suicidal_ideation", "urgent", "emergency_help",
})


def _get_shadow_analytics_lock():
    """Lazy-init asyncio.Lock (must be created inside event loop)."""
    global _shadow_analytics_lock
    if _shadow_analytics_lock is None:
        _shadow_analytics_lock = asyncio.Lock()
    return _shadow_analytics_lock


async def _shadow_analytics_init():
    """
    Initialize shadow analytics:
    1. Create asyncio lock and in-memory ring buffer
    2. Create PostgreSQL shadow_metrics table (if DB available)
    All errors caught — never breaks startup.
    """
    global _shadow_analytics_buf
    _get_shadow_analytics_lock()
    _shadow_analytics_buf = _collections.deque(maxlen=_SHADOW_ANALYTICS_MAXLEN)
    log.info("[SHADOW_ANALYTICS] In-memory buffer initialized (maxlen=%d)", _SHADOW_ANALYTICS_MAXLEN)
    try:
        import asyncpg as _apg
        _db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
        if not _db_url:
            log.warning("[SHADOW_ANALYTICS] No DATABASE_URL — PostgreSQL table skipped, in-memory only")
            return
        raise Exception("startup deferred")
        async with _pool.acquire() as _conn:
            await _conn.execute("""
                CREATE TABLE IF NOT EXISTS shadow_metrics (
                    id            SERIAL PRIMARY KEY,
                    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    contact_id    TEXT NOT NULL,
                    old_route     TEXT,
                    shadow_route  TEXT,
                    route_match   BOOLEAN,
                    old_intent    TEXT,
                    shadow_intent TEXT,
                    intent_match  BOOLEAN,
                    old_agent     TEXT,
                    shadow_agent  TEXT,
                    agent_match   BOOLEAN,
                    escalation_match  BOOLEAN,
                    old_reply_len     INTEGER,
                    shadow_reply_len  INTEGER,
                    latency_ms        INTEGER,
                    shadow_error      BOOLEAN DEFAULT FALSE,
                    mismatch_reason   TEXT,
                    high_risk         BOOLEAN DEFAULT FALSE
                )
            """)
            await _conn.execute(
                "CREATE INDEX IF NOT EXISTS shadow_metrics_ts_idx ON shadow_metrics (ts DESC)"
            )
        await _pool.close()
        log.info("[SHADOW_ANALYTICS] PostgreSQL shadow_metrics table ready")
    except Exception as _e:
        log.warning("[SHADOW_ANALYTICS] PostgreSQL setup failed (%s) — in-memory only", _e)


def _classify_mismatch(
    route_match, intent_match, agent_match, escalation_match,
    old_route, shadow_route, old_intent, shadow_intent,
    old_reply_len, shadow_reply_len, shadow_error, latency_ms,
):
    """Return list of mismatch reason codes for this observation."""
    reasons = []
    if shadow_error:
        reasons.append("shadow_error")
        return reasons
    if not route_match:
        reasons.append("route_mismatch")
    if not intent_match:
        reasons.append("intent_mismatch")
    if not agent_match:
        reasons.append("agent_mismatch")
    if not escalation_match:
        reasons.append("escalation_mismatch")
    _emotional = frozenset({"crisis", "fear", "emotional", "mental_health", "empathy"})
    if bool(_emotional & {old_route.lower()}) != bool(_emotional & {shadow_route.lower()}):
        reasons.append("emotional_mismatch")
    if old_reply_len > 0 and shadow_reply_len > 0:
        ratio = max(old_reply_len, shadow_reply_len) / min(old_reply_len, shadow_reply_len)
        if ratio > 3.0:
            reasons.append("continuity_mismatch")
    if latency_ms > 5000:
        reasons.append("latency_spike")
    return reasons


def _is_high_risk_event(old_route, shadow_route, old_intent, shadow_intent, escalation_match):
    """Return True if this shadow observation involves high-risk scenario."""
    routes = {old_route.lower(), shadow_route.lower()}
    intents = {old_intent.lower(), shadow_intent.lower()}
    if routes & _SHADOW_HIGH_RISK_ROUTES:
        return True
    if intents & _SHADOW_HIGH_RISK_INTENTS:
        return True
    if not escalation_match:
        return True
    return False


async def _save_shadow_metric(record):
    """
    Save one shadow analytics record:
    1. Append to in-memory ring buffer (always)
    2. Insert into PostgreSQL shadow_metrics (best-effort)
    """
    global _shadow_analytics_buf
    if _shadow_analytics_buf is not None:
        async with _get_shadow_analytics_lock():
            _shadow_analytics_buf.append(record)
    try:
        import asyncpg as _apg
        _db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
        if not _db_url:
            return
        _pool = await _apg.create_pool(_db_url, min_size=1, max_size=1, command_timeout=10)
        async with _pool.acquire() as _conn:
            await _conn.execute(
                """INSERT INTO shadow_metrics (
                    contact_id, old_route, shadow_route, route_match,
                    old_intent, shadow_intent, intent_match,
                    old_agent, shadow_agent, agent_match,
                    escalation_match, old_reply_len, shadow_reply_len,
                    latency_ms, shadow_error, mismatch_reason, high_risk
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)""",
                record["contact_id"],
                record["old_route"], record["shadow_route"], record["route_match"],
                record["old_intent"], record["shadow_intent"], record["intent_match"],
                record["old_agent"], record["shadow_agent"], record["agent_match"],
                record["escalation_match"],
                record["old_reply_len"], record["shadow_reply_len"],
                record["latency_ms"], record["shadow_error"],
                ",".join(record.get("mismatch_reasons") or []) or None,
                record.get("high_risk", False),
            )
        await _pool.close()
        log.debug("[SHADOW_DB] stored contact=%s match=%s", record.get("contact_id","?"), record.get("route_match","?"))
    except Exception as _e:
        log.debug("[SHADOW_ANALYTICS] DB save failed (non-critical): %s", _e)


def _compute_shadow_aggregates(records):
    """Compute aggregated metrics from list of shadow records."""
    if not records:
        return {"total": 0, "message": "no data yet"}
    total = len(records)
    errors = sum(1 for r in records if r.get("shadow_error"))
    valid = [r for r in records if not r.get("shadow_error")]
    n_valid = len(valid)
    route_matches = sum(1 for r in valid if r.get("route_match"))
    intent_matches = sum(1 for r in valid if r.get("intent_match"))
    agent_matches = sum(1 for r in valid if r.get("agent_match"))
    escalation_matches = sum(1 for r in valid if r.get("escalation_match"))
    full_matches = sum(1 for r in valid if (
        r.get("route_match") and r.get("intent_match") and
        r.get("agent_match") and r.get("escalation_match")
    ))
    high_risk_count = sum(1 for r in records if r.get("high_risk"))
    high_risk_mismatches = sum(1 for r in records if r.get("high_risk") and not (
        r.get("route_match") and r.get("escalation_match")
    ))
    latencies = [r["latency_ms"] for r in valid if r.get("latency_ms") is not None]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
    p95_latency = int(sorted(latencies)[int(len(latencies) * 0.95)]) if len(latencies) >= 20 else None
    mismatch_counter = _collections.Counter()
    for r in records:
        for reason in (r.get("mismatch_reasons") or []):
            mismatch_counter[reason] += 1
    top_mismatches = dict(mismatch_counter.most_common(5))
    route_mismatch_counter = _collections.Counter()
    for r in valid:
        if not r.get("route_match"):
            route_mismatch_counter[r.get("old_route", "?")] += 1
    unstable_routes = dict(route_mismatch_counter.most_common(5))
    intent_mismatch_counter = _collections.Counter()
    for r in valid:
        if not r.get("intent_match"):
            intent_mismatch_counter[r.get("old_intent", "?")] += 1
    unstable_intents = dict(intent_mismatch_counter.most_common(5))
    def _pct(n, d):
        return round(100.0 * n / d, 1) if d else None
    r_score = _pct(route_matches, n_valid) or 0
    i_score = _pct(intent_matches, n_valid) or 0
    a_score = _pct(agent_matches, n_valid) or 0
    e_score = _pct(escalation_matches, n_valid) or 0
    l_score = _pct(sum(1 for ms in latencies if ms < 3000), len(latencies)) if latencies else 0
    readiness = int(0.30 * r_score + 0.20 * i_score + 0.15 * a_score + 0.25 * e_score + 0.10 * l_score)
    return {
        "total_observations": total,
        "shadow_errors": errors,
        "valid_observations": n_valid,
        "full_match_rate_pct": _pct(full_matches, n_valid),
        "route_match_rate_pct": _pct(route_matches, n_valid),
        "intent_match_rate_pct": _pct(intent_matches, n_valid),
        "agent_match_rate_pct": _pct(agent_matches, n_valid),
        "escalation_match_rate_pct": _pct(escalation_matches, n_valid),
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
        "high_risk_observations": high_risk_count,
        "high_risk_mismatches": high_risk_mismatches,
        "top_mismatch_types": top_mismatches,
        "most_unstable_routes": unstable_routes,
        "most_unstable_intents": unstable_intents,
        "orchestrator_readiness_score": readiness,
        # Phase 4 Step 9: Continuity enrichment statistics
        "continuity_enriched_count": sum(1 for r in records if r.get("continuity_enriched")),
        "continuity_avg_score": round(sum(r.get("continuity_score", 0) for r in records) / total, 1) if total else 0,
        "continuity_route_changes": sum(1 for r in records if r.get("continuity_changed_route")),
        "continuity_escalation_changes": sum(1 for r in records if r.get("continuity_changed_escalation")),
        "continuity_step_changes": sum(1 for r in records if r.get("continuity_changed_next_step")),
        "continuity_improved_decisions": sum(1 for r in records if r.get("continuity_improved_decision")),
        "continuity_avg_confidence": round(sum(r.get("continuity_confidence", 0.0) for r in records) / total, 3) if total else 0.0,
    }


async def generate_shadow_report():
    """Phase 4 Step 11: buffer + PG fallback + metadata."""
    global _shadow_analytics_buf
    if _shadow_analytics_buf is None: return {"error": "shadow analytics not initialized"}
    async with _get_shadow_analytics_lock():
        records = list(_shadow_analytics_buf)
    _source = "memory"
    if not records:
        try:
            import asyncpg as _apg
            _db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
            if _db_url:
                _pool = await _apg.create_pool(_db_url, min_size=1, max_size=1, command_timeout=10)
                async with _pool.acquire() as _conn:
                    _rows = await _conn.fetch("SELECT ts,contact_id,old_route,shadow_route,route_match,old_intent,shadow_intent,intent_match,old_agent,shadow_agent,agent_match,escalation_match,old_reply_len,shadow_reply_len,latency_ms,shadow_error,mismatch_reason,high_risk FROM shadow_metrics ORDER BY ts DESC LIMIT 10000")
                await _pool.close()
                records = []
                for _row in reversed(_rows):
                    _rec = dict(_row)
                    _rec["ts"] = _rec["ts"].replace(tzinfo=None) if _rec.get("ts") else _datetime.datetime.utcnow()
                    _rec["mismatch_reasons"] = [x for x in (_rec.pop("mismatch_reason","") or "").split(",") if x]
                    for _k,_v in [("continuity_enriched",False),("continuity_score",0),("continuity_changed_route",False),("continuity_changed_escalation",False),("continuity_changed_next_step",False),("continuity_improved_decision",False),("continuity_confidence",0.0)]: _rec.setdefault(_k,_v)
                    records.append(_rec)
                _source = "postgresql_fallback"
                log.info("[SHADOW_ANALYTICS] Report fallback: %d PG records", len(records))
        except Exception as _e: log.debug("[SHADOW_ANALYTICS] PG fallback failed: %s", _e)
    now = _datetime.datetime.utcnow()
    cutoff = now - _datetime.timedelta(hours=24)
    recent = [r for r in records if r.get("ts") and r["ts"] >= cutoff]
    all_agg = _compute_shadow_aggregates(records)
    day_agg = _compute_shadow_aggregates(recent)
    readiness = all_agg.get("orchestrator_readiness_score", 0)
    rec_str = ("READY: Orchestrator matches production at 90%+. Consider gradual traffic shift." if readiness>=90 else "NEAR_READY: Good match rate. Fix top mismatches." if readiness>=75 else "IMPROVING: Significant mismatches remain." if readiness>=50 else "NOT_READY: Too many mismatches. Investigate root causes.")
    ts_list = [r["ts"] for r in records if r.get("ts")]
    return {"report_generated_at":now.isoformat()+"Z","all_time":all_agg,"last_24h":day_agg,"orchestrator_readiness_score":readiness,"recommendation":rec_str,"collection_metadata":{"oldest_record_timestamp":min(ts_list).isoformat()+"Z" if ts_list else None,"newest_record_timestamp":max(ts_list).isoformat()+"Z" if ts_list else None,"effective_collection_window_hours":round((max(ts_list)-min(ts_list)).total_seconds()/3600,2) if len(ts_list)>=2 else None,"records_in_memory":len(list(_shadow_analytics_buf)) if _shadow_analytics_buf is not None else 0,"records_loaded_from_db":len(records) if _source=="postgresql_fallback" else 0,"data_source":_source}}


# ---------------------------------------------------------------------------
# PHASE 4 STEP 4+7: Real shadow observe — compares OrchestratorCore vs old flow
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
    Run OrchestratorCore.handle_message in observe-only mode.
    Phase 4 Step 7: saves structured analytics per observation.
    """
    t0 = _time.monotonic()
    record = {
        "ts": _datetime.datetime.utcnow(),
        "contact_id": contact_id,
        "old_route": "unknown", "shadow_route": "unknown", "route_match": False,
        "old_intent": "unknown", "shadow_intent": "unknown", "intent_match": False,
        "old_agent": "unknown", "shadow_agent": "unknown", "agent_match": False,
        "escalation_match": False,
        "old_reply_len": len(old_reply) if old_reply else 0,
        "shadow_reply_len": 0,
        "latency_ms": 0,
        "shadow_error": False,
        "mismatch_reasons": [],
        "high_risk": False,
        # Phase 4 Step 9: Continuity enrichment metrics
        "continuity_enriched": False,
        "continuity_score": 0,
        "continuity_changed_route": False,
        "continuity_changed_escalation": False,
        "continuity_changed_next_step": False,
        "continuity_improved_decision": False,
        "continuity_confidence": 0.0,
    }
    try:
        # 1. Load real session
        try:
            shadow_session = await asyncio.to_thread(load_session, contact_id)
        except Exception as _lse:
            log.warning("[SHADOW_OBSERVE] load_session failed contact=%s: %s", contact_id, _lse)
            shadow_session = {}

        # 2. Safe deep copy — never mutate production session
        import copy
        shadow_session = copy.deepcopy(shadow_session)

        # 3. Extract pre-run state from old session
        old_route = shadow_session.get("current_route") or shadow_session.get("route", "unknown")
        old_intent = shadow_session.get("current_intent", "unknown")
        old_agent = shadow_session.get("agent_current") or shadow_session.get("active_agent", "unknown")
        old_escalation = shadow_session.get("escalation_flag", False)
        record["old_route"] = str(old_route)
        record["old_intent"] = str(old_intent)
        record["old_agent"] = str(old_agent)

        # 4. Stable numeric user_id for OrchestratorCore
        contact_hash = abs(hash(contact_id)) % (2**31)

        # 5. Async wrapper for ask_claude
        async def _ask_claude_shadow(system_prompt, messages, **kwargs):
            return await asyncio.to_thread(ask_claude, system_prompt, messages)

        # 6. Get pipeline singleton
        pipeline = await asyncio.to_thread(_get_pipeline)

        # 6b. Phase 4 Step 9: Load ContinuitySnapshot (read-only, shadow enrichment)
        _continuity_snap = None
        try:
            from continuity_intelligence import ContinuityAnalyzer as _CIAnalyzer
            _ci_analyzer = _CIAnalyzer(contact_id=contact_id)
            _continuity_snap = _ci_analyzer.analyze(session=shadow_session)
            record["continuity_enriched"] = True
            record["continuity_score"] = getattr(_continuity_snap, "continuity_health_score", 0)
            record["continuity_confidence"] = float(getattr(_continuity_snap, "confidence", 0.0))
            log.info(
                "[SHADOW_CONTINUITY] Loaded ContinuitySnapshot contact=%s health=%s dropout=%s next_step=%s",
                contact_id,
                getattr(_continuity_snap, "continuity_health_score", "?"),
                getattr(_continuity_snap, "dropout_risk", "?"),
                str(getattr(_continuity_snap, "next_best_step", "?"))[:60],
            )
        except Exception as _cie:
            log.debug("[SHADOW_CONTINUITY] Snapshot load failed (non-fatal): %s", _cie)
            _continuity_snap = None

        # 7. Build OrchestratorCore and call — BASELINE (without continuity)
        from orchestrator_core import OrchestratorCore
        orchestrator = OrchestratorCore(
            user_id=contact_hash,
            session=shadow_session,
            ask_claude_fn=_ask_claude_shadow,
            save_session_fn=_noop_save_session,
            pipeline=pipeline,
        )
        orch_result = await orchestrator.handle_message(
            message=text,
            shadow_mode=True,
        )

        # 7b. Phase 4 Step 9: Run enriched shadow (WITH continuity) and compare
        if _continuity_snap is not None:
            try:
                import copy as _copy_mod
                _enriched_session = _copy_mod.deepcopy(shadow_session)
                _orch_enriched = OrchestratorCore(
                    user_id=contact_hash,
                    session=_enriched_session,
                    ask_claude_fn=_ask_claude_shadow,
                    save_session_fn=_noop_save_session,
                    pipeline=pipeline,
                )
                _enr_result = await _orch_enriched.handle_message(
                    message=text,
                    shadow_mode=True,
                    continuity_snapshot=_continuity_snap,
                )
                # Compare baseline vs enriched
                _base_route = str(getattr(orch_result, "route", "unknown"))
                _enr_route  = str(getattr(_enr_result, "route", "unknown"))
                _base_esc   = bool(getattr(orch_result, "escalated", False))
                _enr_esc    = bool(getattr(_enr_result, "escalated", False))
                _base_step  = str(getattr(orch_result, "active_agent", "unknown"))
                _enr_step   = str(getattr(_enr_result, "active_agent", "unknown"))

                record["continuity_changed_route"]      = (_base_route != _enr_route)
                record["continuity_changed_escalation"] = (_base_esc   != _enr_esc)
                record["continuity_changed_next_step"]  = (_base_step  != _enr_step)

                # Improved decision: any change in a high-value scenario
                _snap_flags = getattr(_continuity_snap, "flags", []) or []
                _is_high_value = any(f in _snap_flags for f in [
                    "RETURNED_AFTER_PAUSE", "PAYMENT_WITHOUT_ONBOARDING",
                    "STUCK_USER", "ONBOARDING_INCOMPLETE", "ESCALATION_NOT_ACKED",
                    "HIGH_DROPOUT_RISK", "ROUTE_DRIFT",
                ])
                _any_change = record["continuity_changed_route"] or record["continuity_changed_escalation"] or record["continuity_changed_next_step"]
                record["continuity_improved_decision"] = (_is_high_value and _any_change)

                log.info(
                    "[SHADOW_CONTINUITY_COMPARE] contact=%s "
                    "route_changed=%s base_route=%s enr_route=%s "
                    "esc_changed=%s step_changed=%s improved=%s high_value=%s",
                    contact_id,
                    record["continuity_changed_route"], _base_route, _enr_route,
                    record["continuity_changed_escalation"],
                    record["continuity_changed_next_step"],
                    record["continuity_improved_decision"],
                    _is_high_value,
                )
            except Exception as _enr_e:
                log.debug("[SHADOW_CONTINUITY_COMPARE] Enriched run failed (non-fatal): %s", _enr_e)

        # 8. Extract shadow results
        if hasattr(orch_result, "reply"):
            shadow_reply = orch_result.reply or ""
            shadow_route = getattr(orch_result, "route", shadow_session.get("current_route", "unknown"))
            shadow_intent = getattr(orch_result, "intent", shadow_session.get("current_intent", "unknown"))
            shadow_agent = getattr(orch_result, "agent", shadow_session.get("active_agent", "unknown"))
            shadow_escalation = getattr(orch_result, "escalate", False)
        else:
            shadow_reply = str(orch_result) if orch_result else ""
            shadow_route = shadow_session.get("current_route", "unknown")
            shadow_intent = shadow_session.get("current_intent", "unknown")
            shadow_agent = shadow_session.get("active_agent", "unknown")
            shadow_escalation = False

        # 9. Compute match flags
        total_ms = int((_time.monotonic() - t0) * 1000)
        route_match = (old_route == shadow_route)
        intent_match = (old_intent == shadow_intent)
        agent_match = (old_agent == shadow_agent)
        escalation_match = (old_escalation == shadow_escalation)
        full_match = route_match and intent_match and agent_match and escalation_match

        # 10. Classify mismatches
        mismatch_reasons = _classify_mismatch(
            route_match=route_match, intent_match=intent_match,
            agent_match=agent_match, escalation_match=escalation_match,
            old_route=str(old_route), shadow_route=str(shadow_route),
            old_intent=str(old_intent), shadow_intent=str(shadow_intent),
            old_reply_len=len(old_reply) if old_reply else 0,
            shadow_reply_len=len(shadow_reply),
            shadow_error=False, latency_ms=total_ms,
        )

        # 11. Detect high-risk
        high_risk = _is_high_risk_event(
            old_route=str(old_route), shadow_route=str(shadow_route),
            old_intent=str(old_intent), shadow_intent=str(shadow_intent),
            escalation_match=escalation_match,
        )

        # 12. Update analytics record
        record.update({
            "shadow_route": str(shadow_route), "route_match": route_match,
            "shadow_intent": str(shadow_intent), "intent_match": intent_match,
            "shadow_agent": str(shadow_agent), "agent_match": agent_match,
            "escalation_match": escalation_match,
            "shadow_reply_len": len(shadow_reply), "latency_ms": total_ms,
            "shadow_error": False, "mismatch_reasons": mismatch_reasons, "high_risk": high_risk,
        })

        # 13. Log comparison
        log.info(
            "[SHADOW_COMPARE] contact_id=%s "
            "old_route=%s shadow_route=%s route_match=%s "
            "old_intent=%s shadow_intent=%s intent_match=%s "
            "old_agent=%s shadow_agent=%s agent_match=%s "
            "escalation_match=%s old_reply_len=%d shadow_reply_len=%d "
            "latency_ms=%d error=false high_risk=%s",
            contact_id,
            old_route, shadow_route, route_match,
            old_intent, shadow_intent, intent_match,
            old_agent, shadow_agent, agent_match,
            escalation_match,
            len(old_reply) if old_reply else 0, len(shadow_reply),
            total_ms, high_risk,
        )

        # 14. Log mismatch
        if not full_match:
            log.warning(
                "[SHADOW_MISMATCH] contact_id=%s reason=%s "
                "old_route=%s shadow_route=%s "
                "old_intent=%s shadow_intent=%s "
                "old_agent=%s shadow_agent=%s",
                contact_id, ",".join(mismatch_reasons) if mismatch_reasons else "full_mismatch",
                old_route, shadow_route, old_intent, shadow_intent, old_agent, shadow_agent,
            )

        # 15. Log high-risk event
        if high_risk and not full_match:
            log.warning(
                "[SHADOW_HIGH_RISK] contact_id=%s reasons=%s "
                "old_route=%s shadow_route=%s "
                "old_intent=%s shadow_intent=%s "
                "escalation_match=%s latency_ms=%d",
                contact_id, ",".join(mismatch_reasons),
                old_route, shadow_route, old_intent, shadow_intent,
                escalation_match, total_ms,
            )

    except Exception as _ex:
        record["shadow_error"] = True
        record["mismatch_reasons"] = ["shadow_error"]
        record["latency_ms"] = int((_time.monotonic() - t0) * 1000)
        log.error("[SHADOW_OBSERVE] Unexpected error contact=%s: %s", contact_id, _ex)
        log.error("[SHADOW_OBSERVE] Traceback: %s", _traceback.format_exc())

    # 16. Save analytics record (always, even on error)
    try:
        asyncio.create_task(_save_shadow_metric(record))
    except Exception as _se:
        log.debug("[SHADOW_ANALYTICS] Could not schedule metric save: %s", _se)


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
    global _last_webhook_ts, _traffic_was_silent
    import time as _ts11; _last_webhook_ts=_ts11.monotonic()
    if _traffic_was_silent: _traffic_was_silent=False; log.info("[TRAFFIC_OK] Webhook resumed")
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
async def _traffic_heartbeat():
    """Traffic heartbeat."""
    global _last_webhook_ts, _traffic_was_silent
    import time as _thb
    while True:
        await asyncio.sleep(300)
        e = (_thb.monotonic()-_last_webhook_ts) if _last_webhook_ts else None
        if e is None or e>1800:
            if not _traffic_was_silent: _traffic_was_silent=True; log.warning("[TRAFFIC_WARN] No webhook in %s min", round(e/60,1) if e else "never")
        elif _traffic_was_silent: _traffic_was_silent=False; log.info("[TRAFFIC_OK] Webhook resumed")


async def on_startup():
    log.info("[STARTUP] Phase 3.19 InstitutionalMemoryEngine — background-only, fail-safe, neutral_result on all exceptions")
    log.info("[STARTUP] USE_NEW_MESSAGE_PIPELINE=%s PIPELINE_SHADOW_MODE=%s",
             USE_NEW_MESSAGE_PIPELINE, PIPELINE_SHADOW_MODE)
    # Phase 4 Step 7: Initialize shadow analytics storage
    await _shadow_analytics_init()
    asyncio.create_task(_traffic_heartbeat())
    log.info("[STARTUP] Traffic heartbeat started")
    if USE_NEW_MESSAGE_PIPELINE or PIPELINE_SHADOW_MODE:
        log.info("[STARTUP] Starting pipeline workers...")
        asyncio.create_task(_start_pipeline_workers())
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


# ---------------------------------------------------------------------------
# PHASE 4 STEP 7: Shadow analytics endpoints
# ---------------------------------------------------------------------------
@app.get("/shadow/report")
async def shadow_report_endpoint():
    """Returns aggregated shadow analytics: match rates, latency, readiness score."""
    try:
        report = await generate_shadow_report()
        return JSONResponse(report)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/shadow/readiness")
async def shadow_readiness_endpoint():
    """Returns Orchestrator Readiness Score (0-100) with recommendation."""
    try:
        report = await generate_shadow_report()
        score = report.get("orchestrator_readiness_score", 0)
        total = report.get("all_time", {}).get("total_observations", 0)
        rec = report.get("recommendation", "")
        return JSONResponse({
            "orchestrator_readiness_score": score,
            "total_observations": total,
            "recommendation": rec,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# PHASE 4 STEP 8: Continuity Intelligence endpoints (read-only)
# ---------------------------------------------------------------------------
@app.get("/continuity/{contact_id}")
async def continuity_snapshot_endpoint(contact_id: str):
    """
    Returns ContinuitySnapshot for a specific contact.
    Read-only: computes on demand from session data.
    Does NOT mutate session, does NOT send messages.
    """
    try:
        from continuity_intelligence import analyze_continuity, snapshot_to_dict
        session = await asyncio.to_thread(load_session, contact_id)
        snap = analyze_continuity(
            contact_id=contact_id,
            session=session or {},
        )
        return JSONResponse(snapshot_to_dict(snap))
    except Exception as e:
        log.error("[CONTINUITY] Endpoint error contact=%s: %s", contact_id, e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/continuity/report")
async def continuity_report_endpoint():
    """Returns system-level continuity status and available flags."""
    try:
        from continuity_intelligence import ALL_FLAGS
        return JSONResponse({
            "status": "continuity_intelligence_active",
            "available_flags": ALL_FLAGS,
            "endpoints": [
                "GET /continuity/{contact_id}",
                "GET /continuity/report",
            ],
            "note": "Read-only layer. Does not mutate sessions or send messages.",
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


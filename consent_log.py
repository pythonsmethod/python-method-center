# -*- coding: utf-8 -*-
# =============================================================================
# Module: consent_log.py
# Python Method Center
#
# Purpose: Persist the legal fact that a user agreed to the public offer
#          before payment, with timestamp + user_id + offer version + chosen
#          tariff. Required by oferta §6 (digital confirmation of offer
#          acceptance) for chargeback defense.
#
# Storage: PostgreSQL table pre_payment_consent. Lazy-initialized on first
#          use; gracefully degrades to warning if DATABASE_URL is unset
#          (the bot keeps working — the consent step just isn't logged).
# =============================================================================

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

log = logging.getLogger("consent_log")

# Current offer version — bump when the offer PDF is replaced.
OFERTA_VERSION = "v2"

_pool = None
_pool_lock: Optional[asyncio.Lock] = None
_table_ready = False


async def _get_pool():
    """Lazy-initialize a small asyncpg pool. Returns None if no DATABASE_URL."""
    global _pool, _pool_lock, _table_ready
    if _pool is not None:
        return _pool
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    async with _pool_lock:
        if _pool is not None:
            return _pool
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")
        if not db_url:
            log.warning("[CONSENT_LOG] DATABASE_URL not set — consent will not be persisted")
            return None
        try:
            import asyncpg
            _pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2, command_timeout=10)
            await _ensure_table(_pool)
            _table_ready = True
            log.info("[CONSENT_LOG] pool ready, table ensured")
            return _pool
        except Exception as e:
            log.error("[CONSENT_LOG] pool init failed: %s", e)
            return None


async def _ensure_table(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pre_payment_consent (
                id              BIGSERIAL PRIMARY KEY,
                contact_id      TEXT NOT NULL,
                tariff          SMALLINT NOT NULL,
                offer_version   TEXT NOT NULL,
                consented_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                source          TEXT
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ppc_contact ON pre_payment_consent(contact_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ppc_consented_at ON pre_payment_consent(consented_at DESC)"
        )


async def log_consent(
    contact_id: str,
    tariff: int,
    offer_version: str = OFERTA_VERSION,
    source: str = "inline_button",
) -> bool:
    """
    Persist a single consent event. Returns True on success, False on failure
    (database unavailable, write error). Never raises — the caller must
    proceed with the user flow regardless.
    """
    pool = await _get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO pre_payment_consent
                    (contact_id, tariff, offer_version, source)
                VALUES ($1, $2, $3, $4)
                """,
                str(contact_id), int(tariff), offer_version, source,
            )
        log.info(
            "[CONSENT_LOG] saved contact=%s tariff=%d offer_version=%s source=%s",
            contact_id, tariff, offer_version, source,
        )
        return True
    except Exception as e:
        log.error("[CONSENT_LOG] write failed contact=%s: %s", contact_id, e)
        return False

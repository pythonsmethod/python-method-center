# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.1 — Persistent Memory & Infrastructure Core
# Module: memory_engine.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Memory Engine
#
# Memory tier architecture:
#   Tier 1 — Short-Term (48h rolling window) → pm_memory_short_term
#   Tier 2 — Active Stage (current stage)    → pm_memory_active_stage
#   Tier 3 — Long-Term Compressed            → pm_memory_compressed
#   Tier 4 — Semantic Vector Recall          → pm_memory_vectors
#   Timeline (cross-tier, immutable)         → pm_memory_timeline
# =============================================================================

from __future__ import annotations
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("memory_engine")


@dataclass
class MemoryContext:
    """Full memory context assembled from all tiers."""
    user_id: int
    short_term_summary: str = ""
    short_term_peak_risk: float = 0.0
    short_term_routes: List[str] = field(default_factory=list)
    short_term_emotional_arc: List[str] = field(default_factory=list)
    short_term_unresolved: List[Any] = field(default_factory=list)
    short_term_message_count: int = 0
    current_stage: str = ""
    stage_progress_pct: int = 0
    stage_goals: List[str] = field(default_factory=list)
    stage_next_action: str = ""
    stage_blockers: List[str] = field(default_factory=list)
    stage_emotional_current: str = ""
    long_term_narrative: str = ""
    long_term_key_facts: Dict[str, Any] = field(default_factory=dict)
    long_term_risk_max: float = 0.0
    long_term_breakthroughs: List[str] = field(default_factory=list)
    semantic_matches: List[Dict[str, Any]] = field(default_factory=list)
    agent_context_snippet: str = ""
    memory_version: int = 1
    last_loaded_at: float = field(default_factory=time.time)
    tiers_loaded: List[str] = field(default_factory=list)

    def to_injection_text(self) -> str:
        """Returns context snippet for agent system prompt injection."""
        if self.agent_context_snippet:
            return self.agent_context_snippet
        parts = []
        if self.short_term_summary:
            parts.append(self.short_term_summary)
        if self.current_stage:
            parts.append(
                f"Клиент на этапе '{self.current_stage}' "
                f"(прогресс {self.stage_progress_pct}%)."
            )
        if self.stage_next_action:
            parts.append(f"Следующий шаг: {self.stage_next_action}.")
        if self.long_term_narrative and not parts:
            parts.append(self.long_term_narrative[:400])
        return " ".join(parts[:3])


@dataclass
class TimelineEvent:
    """A single event to append to pm_memory_timeline."""
    user_id: int
    event_type: str
    summary: str
    priority: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    user_message: str = ""
    ai_response: str = ""
    route: str = ""
    agent: str = ""
    intent: str = ""
    user_state: str = ""
    risk_score: float = 0.0
    overlay_type: str = "none"
    memory_tier: str = "short_term"
    session_id: str = ""
    event_subtype: str = ""


class MemoryEngine:
    """
    Unified memory access layer for all 4 tiers.
    All DB operations are async (asyncpg).
    """

    def __init__(self, db_url: str = ""):
        self._db_url = db_url or os.environ.get("DATABASE_URL", "")
        self._pool = None
        self._ready = False
        log.info("[MEMORY] MemoryEngine initialized")

    async def init(self) -> None:
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self._db_url, min_size=2, max_size=10, command_timeout=10
            )
            self._ready = True
            log.info("[MEMORY] DB pool ready")
        except Exception as e:
            log.error("[MEMORY] init error: %s", e)
            self._ready = False

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def load_context(self, user_id: int) -> MemoryContext:
        """Load all memory tiers for a client."""
        ctx = MemoryContext(user_id=user_id)
        if not self._ready:
            return ctx
        try:
            async with self._pool.acquire() as conn:
                stm = await conn.fetchrow(
                    "SELECT context_snippet, peak_risk, routes_visited, emotional_arc,"
                    " unresolved, message_count FROM pm_memory_short_term"
                    " WHERE user_id = $1 AND is_current = TRUE ORDER BY created_at DESC LIMIT 1",
                    user_id
                )
                if stm:
                    ctx.short_term_summary = stm["context_snippet"] or ""
                    ctx.short_term_peak_risk = float(stm["peak_risk"] or 0)
                    ctx.short_term_routes = list(stm["routes_visited"] or [])
                    ctx.short_term_emotional_arc = list(stm["emotional_arc"] or [])
                    ctx.short_term_unresolved = json.loads(stm["unresolved"] or "[]")
                    ctx.short_term_message_count = int(stm["message_count"] or 0)
                    ctx.tiers_loaded.append("short_term")

                stage = await conn.fetchrow(
                    "SELECT stage_name, progress_pct, goals, next_action,"
                    " blockers, emotional_current FROM pm_memory_active_stage"
                    " WHERE user_id = $1 AND is_current = TRUE LIMIT 1",
                    user_id
                )
                if stage:
                    ctx.current_stage = stage["stage_name"] or ""
                    ctx.stage_progress_pct = int(stage["progress_pct"] or 0)
                    ctx.stage_goals = list(stage["goals"] or [])
                    ctx.stage_next_action = stage["next_action"] or ""
                    ctx.stage_blockers = list(stage["blockers"] or [])
                    ctx.stage_emotional_current = stage["emotional_current"] or ""
                    ctx.tiers_loaded.append("active_stage")

                comp = await conn.fetchrow(
                    "SELECT narrative_summary, key_facts, risk_trajectory, breakthroughs"
                    " FROM pm_memory_compressed WHERE user_id = $1"
                    " ORDER BY created_at DESC LIMIT 1",
                    user_id
                )
                if comp:
                    ctx.long_term_narrative = comp["narrative_summary"] or ""
                    kf = comp["key_facts"]
                    ctx.long_term_key_facts = json.loads(kf) if isinstance(kf, str) else (kf or {})
                    rt = comp["risk_trajectory"]
                    rt_data = json.loads(rt) if isinstance(rt, str) else (rt or {})
                    ctx.long_term_risk_max = float(rt_data.get("max", 0))
                    bt = comp["breakthroughs"]
                    ctx.long_term_breakthroughs = json.loads(bt) if isinstance(bt, str) else list(bt or [])
                    ctx.tiers_loaded.append("long_term")

            ctx.agent_context_snippet = ctx.to_injection_text()
            log.debug("[MEMORY] context loaded user=%d tiers=%s", user_id, ctx.tiers_loaded)
        except Exception as e:
            log.error("[MEMORY] load_context error user=%d: %s", user_id, e)
        return ctx

    async def record_event(self, event: TimelineEvent) -> Optional[int]:
        """Append one event to pm_memory_timeline (immutable)."""
        if not self._ready:
            return None
        try:
            q = ("INSERT INTO pm_memory_timeline"
                 " (user_id, session_id, event_type, event_subtype, priority,"
                 "  summary, details, user_message, ai_response,"
                 "  route, agent, intent, user_state, risk_score, overlay_type, memory_tier)"
                 " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)"
                 " RETURNING id")
            async with self._pool.acquire() as conn:
                return await conn.fetchval(
                    q,
                    event.user_id, event.session_id or None,
                    event.event_type, event.event_subtype or None, event.priority,
                    event.summary, json.dumps(event.details),
                    event.user_message[:2000] if event.user_message else None,
                    event.ai_response[:2000] if event.ai_response else None,
                    event.route or None, event.agent or None,
                    event.intent or None, event.user_state or None,
                    event.risk_score, event.overlay_type or "none",
                    event.memory_tier,
                )
        except Exception as e:
            log.error("[MEMORY] record_event error: %s", e)
            return None

    async def update_short_term(
        self, user_id: int, message_text: str, ai_reply: str, orch: Dict[str, Any]
    ) -> bool:
        """Update or create the 48h rolling short-term memory window."""
        if not self._ready:
            return False
        try:
            intent = orch.get("intent", "question")
            state = orch.get("state", "neutral")
            route = orch.get("route", "reception")
            agent = orch.get("agent", "Lucky")
            risk = float(orch.get("risk_score", 0.0))
            async with self._pool.acquire() as conn:
                existing = await conn.fetchrow(
                    "SELECT id, message_count, peak_risk, routes_visited,"
                    " agents_active, emotional_arc, intent_summary, state_summary"
                    " FROM pm_memory_short_term"
                    " WHERE user_id = $1 AND is_current = TRUE AND expires_at > NOW() LIMIT 1",
                    user_id
                )
                if existing:
                    mc = int(existing["message_count"]) + 1
                    pr = max(float(existing["peak_risk"] or 0), risk)
                    routes = list(set(list(existing["routes_visited"] or []) + [route]))[-10:]
                    agents = list(set(list(existing["agents_active"] or []) + [agent]))
                    arc = (list(existing["emotional_arc"] or []) + [state])[-20:]
                    is_data = json.loads(existing["intent_summary"] or "{}")
                    is_data[intent] = is_data.get(intent, 0) + 1
                    ss_data = json.loads(existing["state_summary"] or "{}")
                    ss_data[state] = ss_data.get(state, 0) + 1
                    snippet = self._build_snippet(mc, pr, routes, arc, is_data)
                    await conn.execute(
                        "UPDATE pm_memory_short_term SET message_count=$2, peak_risk=$3,"
                        " routes_visited=$4, agents_active=$5, emotional_arc=$6,"
                        " intent_summary=$7, state_summary=$8, context_snippet=$9, window_end=NOW()"
                        " WHERE id=$1",
                        existing["id"], mc, pr, routes, agents, arc,
                        json.dumps(is_data), json.dumps(ss_data), snippet,
                    )
                else:
                    snippet = self._build_snippet(1, risk, [route], [state], {intent: 1})
                    await conn.execute(
                        "INSERT INTO pm_memory_short_term"
                        " (user_id, window_start, message_count, peak_risk,"
                        "  routes_visited, agents_active, emotional_arc,"
                        "  intent_summary, state_summary, context_snippet)"
                        " VALUES ($1, NOW(), 1, $2, $3, $4, $5, $6, $7, $8)",
                        user_id, risk, [route], [agent], [state],
                        json.dumps({intent: 1}), json.dumps({state: 1}), snippet,
                    )
            return True
        except Exception as e:
            log.error("[MEMORY] update_short_term error: %s", e)
            return False

    def _build_snippet(
        self, msg_count: int, peak_risk: float,
        routes: List[str], emotional_arc: List[str], intent_counts: Dict[str, int]
    ) -> str:
        dominant_intent = max(intent_counts, key=intent_counts.get) if intent_counts else "question"
        dominant_emotion = emotional_arc[-1] if emotional_arc else "neutral"
        route_str = ", ".join(routes[-3:]) if routes else "reception"
        snippet = (
            f"Клиент взаимодействовал {msg_count} раз, "
            f"интент: {dominant_intent}, состояние: {dominant_emotion}. "
            f"Маршруты: {route_str}."
        )
        if peak_risk >= 0.60:
            snippet += f" Пиковый риск: {peak_risk:.2f}."
        return snippet

    async def upsert_client_profile(self, user_id: int, updates: Dict[str, Any]) -> bool:
        """Upsert client profile with whitelisted columns."""
        ALLOWED = {
            "display_name","telegram_username","phone","email","primary_disease",
            "secondary_conditions","treatment_stage","payment_status","active_tariff",
            "payment_date","onboarding_completed","onboarding_completed_at",
            "total_sessions","total_messages","first_contact_at","last_contact_at",
            "last_active_route","last_active_agent","lifetime_max_risk",
            "current_risk_level","risk_spike_count","escalation_count",
            "is_vip","requires_human","human_assigned_to","tags",
        }
        if not self._ready:
            return False
        try:
            safe = {k: v for k, v in updates.items() if k in ALLOWED}
            if not safe:
                return False
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO pm_client_profiles (user_id)"
                    " VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
                    user_id
                )
                cols = list(safe.keys())
                vals = list(safe.values())
                set_clause = ", ".join(f"{c} = ${i+2}" for i, c in enumerate(cols))
                await conn.execute(
                    f"UPDATE pm_client_profiles SET {set_clause}, updated_at=NOW() WHERE user_id=$1",
                    user_id, *vals
                )
            return True
        except Exception as e:
            log.error("[MEMORY] upsert_client_profile error: %s", e)
            return False

    async def store_embedding(
        self, user_id: int, content_text: str, content_type: str,
        embedding: List[float], metadata: Dict[str, Any] = None,
        timeline_event_id: int = None
    ) -> bool:
        """Store a vector embedding for semantic recall."""
        if not self._ready:
            return False
        try:
            meta = metadata or {}
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO pm_memory_vectors"
                    " (user_id, source_type, timeline_event_id, content_text,"
                    "  content_type, embedding, intent, topics, emotional_tone, risk_score, importance)"
                    " VALUES ($1, 'timeline', $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                    user_id, timeline_event_id, content_text[:4000], content_type,
                    json.dumps(embedding), meta.get("intent"),
                    meta.get("topics", []), meta.get("emotional_tone"),
                    float(meta.get("risk_score", 0)), float(meta.get("importance", 0.5)),
                )
            return True
        except Exception as e:
            log.error("[MEMORY] store_embedding error: %s", e)
            return False

    async def recall_by_text(
        self, user_id: int, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Semantic recall using full-text search (pgvector fallback)."""
        if not self._ready:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT content_text, content_type, intent, emotional_tone,"
                    " risk_score, importance, created_at,"
                    " ts_rank(search_text, plainto_tsquery('russian', $2)) AS rank"
                    " FROM pm_memory_vectors WHERE user_id = $1"
                    "   AND search_text @@ plainto_tsquery('russian', $2)"
                    " ORDER BY rank DESC, importance DESC LIMIT $3",
                    user_id, query, limit
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.error("[MEMORY] recall_by_text error: %s", e)
            return []

    async def get_timeline(
        self, user_id: int, limit: int = 20, event_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Return recent timeline events for a user."""
        if not self._ready:
            return []
        try:
            async with self._pool.acquire() as conn:
                if event_types:
                    rows = await conn.fetch(
                        "SELECT * FROM pm_memory_timeline WHERE user_id=$1 AND event_type=ANY($2)"
                        " ORDER BY ts DESC LIMIT $3",
                        user_id, event_types, limit
                    )
                else:
                    rows = await conn.fetch(
                        "SELECT * FROM pm_memory_timeline WHERE user_id=$1"
                        " ORDER BY ts DESC LIMIT $2",
                        user_id, limit
                    )
                return [dict(r) for r in rows]
        except Exception as e:
            log.error("[MEMORY] get_timeline error: %s", e)
            return []

    async def record_interaction(
        self, user_id: int, message: str, reply: str, orch: Dict[str, Any]
    ) -> None:
        """Convenience: record a full interaction across all tiers."""
        try:
            event = TimelineEvent(
                user_id=user_id, event_type="message_in",
                summary=message[:150], user_message=message, ai_response=reply,
                route=orch.get("route", ""), agent=orch.get("agent", ""),
                intent=orch.get("intent", ""), user_state=orch.get("state", ""),
                risk_score=float(orch.get("risk_score", 0)),
                overlay_type=orch.get("overlay_type", "none"),
                session_id=orch.get("session_id", ""),
                priority=2 if float(orch.get("risk_score", 0)) >= 0.70 else 0,
            )
            await self.record_event(event)
            await self.update_short_term(user_id, message, reply, orch)
            await self.upsert_client_profile(user_id, {
                "last_contact_at": datetime.now(timezone.utc).isoformat(),
                "last_active_route": orch.get("route", "reception"),
                "last_active_agent": orch.get("agent", "Lucky"),
                "lifetime_max_risk": max(0.0, float(orch.get("risk_score", 0))),
            })
        except Exception as e:
            log.error("[MEMORY] record_interaction error: %s", e)


_memory_engine: Optional[MemoryEngine] = None

def get_memory_engine() -> MemoryEngine:
    global _memory_engine
    if _memory_engine is None:
        _memory_engine = MemoryEngine()
    return _memory_engine

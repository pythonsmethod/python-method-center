# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.1 — Persistent Memory & Infrastructure Core
# Module: memory_compressor.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Memory Compression & Retrieval
#
# Purpose: Compress short-term memory events into long-term narrative summaries.
#          Runs as background job via async_queue.
#
# Compression strategies:
#   - rule_based:  deterministic extraction of key facts (fast, no AI cost)
#   - gpt_summary: GPT-4 narrative compression (high quality)
#   - hybrid:      rule_based + GPT for narrative (default)
#
# Compression triggers:
#   - Scheduled: every 7 days per client
#   - Event-based: after 100+ uncompressed timeline events
#   - Manual: via Dashboard / admin
#
# Compression window: covers all uncompressed events in pm_memory_timeline
# After compression: is_compressed=TRUE set on source events
# =============================================================================

from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("memory_compressor")

# Compression thresholds
_COMPRESS_AFTER_EVENTS = 50       # compress after N uncompressed events
_COMPRESS_AFTER_DAYS = 7          # compress if last compression > 7 days ago
_MAX_TOKENS_NARRATIVE = 500       # max words in compressed narrative
_MIN_EVENTS_TO_COMPRESS = 5       # minimum events needed to trigger compression


class MemoryCompressor:
    """
    Compresses rolling short-term timeline events into long-term summaries.
    Uses rule-based extraction + optional GPT narrative compression.
    """

    def __init__(self, db_pool=None, ask_claude_fn=None):
        self._pool = db_pool
        self._ask_claude = ask_claude_fn  # async fn(system_prompt, messages) -> str
        log.info("[COMPRESSOR] MemoryCompressor initialized")

    async def run_for_user(self, user_id: int, method: str = "hybrid") -> Dict[str, Any]:
        """
        Run full compression pipeline for one user.
        Returns compression result dict.
        """
        result = {"user_id": user_id, "status": "skipped", "event_count": 0}
        try:
            events = await self._load_uncompressed_events(user_id)
            if len(events) < _MIN_EVENTS_TO_COMPRESS:
                log.debug("[COMPRESSOR] user=%d only %d events, skipping", user_id, len(events))
                return result

            log.info("[COMPRESSOR] compressing %d events for user=%d", len(events), user_id)

            # Extract structured facts
            key_facts = self._extract_key_facts(events)
            risk_trajectory = self._build_risk_trajectory(events)
            route_history = self._extract_routes(events)
            topics = self._extract_topics(events)
            emotional_journey = self._extract_emotional_arc(events)
            breakthroughs = self._extract_breakthroughs(events)
            unresolved = self._extract_unresolved(events)

            # Build narrative
            if method == "gpt_summary" and self._ask_claude:
                narrative = await self._gpt_narrative(events, key_facts, emotional_journey)
            else:
                narrative = self._rule_narrative(
                    events, key_facts, risk_trajectory, emotional_journey
                )

            # Persist compressed memory
            covers_from = events[-1]["ts"] if events else datetime.now(timezone.utc)
            covers_to = events[0]["ts"] if events else datetime.now(timezone.utc)
            event_ids = [e["id"] for e in events]

            comp_id = await self._save_compressed(
                user_id, narrative, key_facts, risk_trajectory, route_history,
                topics, emotional_journey, breakthroughs, unresolved,
                covers_from, covers_to, event_ids, method
            )

            if comp_id:
                # Mark source events as compressed
                await self._mark_compressed(event_ids, comp_id)
                # Update client profile
                await self._update_profile_after_compression(user_id)
                result.update({
                    "status": "ok", "compression_id": comp_id,
                    "event_count": len(events), "method": method,
                })
                log.info("[COMPRESSOR] compressed %d events for user=%d comp_id=%d",
                          len(events), user_id, comp_id)

        except Exception as e:
            log.error("[COMPRESSOR] run_for_user error user=%d: %s", user_id, e)
            result["status"] = "error"
            result["error"] = str(e)
        return result

    async def _load_uncompressed_events(self, user_id: int) -> List[Dict]:
        """Load all uncompressed timeline events for compression."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, ts, event_type, summary, details, user_message,"
                    " ai_response, route, agent, intent, user_state, risk_score,"
                    " overlay_type, priority FROM pm_memory_timeline"
                    " WHERE user_id=$1 AND is_compressed=FALSE"
                    " ORDER BY ts DESC LIMIT 200",
                    user_id
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.error("[COMPRESSOR] load error: %s", e)
            return []

    def _extract_key_facts(self, events: List[Dict]) -> Dict[str, Any]:
        """Extract structured facts from events."""
        facts: Dict[str, Any] = {}
        intents: Dict[str, int] = {}
        states: Dict[str, int] = {}
        routes_seen = set()
        agents_seen = set()
        escalation_count = 0

        for e in events:
            if e.get("intent"):
                intents[e["intent"]] = intents.get(e["intent"], 0) + 1
            if e.get("user_state"):
                states[e["user_state"]] = states.get(e["user_state"], 0) + 1
            if e.get("route"):
                routes_seen.add(e["route"])
            if e.get("agent"):
                agents_seen.add(e["agent"])
            if e.get("event_type") in ("escalation_triggered", "escalation_resolved"):
                escalation_count += 1

        facts["dominant_intent"] = max(intents, key=intents.get) if intents else "question"
        facts["dominant_state"] = max(states, key=states.get) if states else "neutral"
        facts["routes_visited"] = list(routes_seen)
        facts["agents_active"] = list(agents_seen)
        facts["intent_distribution"] = intents
        facts["state_distribution"] = states
        facts["escalation_count"] = escalation_count
        facts["total_events"] = len(events)
        return facts

    def _build_risk_trajectory(self, events: List[Dict]) -> Dict[str, Any]:
        scores = [float(e["risk_score"]) for e in events if e.get("risk_score") is not None]
        if not scores:
            return {"min": 0, "max": 0, "avg": 0, "spikes": []}
        spikes = [s for s in scores if s >= 0.70]
        return {
            "min": round(min(scores), 3),
            "max": round(max(scores), 3),
            "avg": round(sum(scores) / len(scores), 3),
            "spikes": spikes,
            "spike_count": len(spikes),
        }

    def _extract_routes(self, events: List[Dict]) -> List[str]:
        seen = []
        for e in events:
            r = e.get("route")
            if r and (not seen or seen[-1] != r):
                seen.append(r)
        return seen

    def _extract_topics(self, events: List[Dict]) -> List[str]:
        topics = set()
        for e in events:
            if e.get("intent"):
                topics.add(e["intent"])
        return list(topics)

    def _extract_emotional_arc(self, events: List[Dict]) -> str:
        states = [e.get("user_state", "neutral") for e in reversed(events) if e.get("user_state")]
        if not states:
            return "stable"
        first = states[0] if states else "neutral"
        last = states[-1] if states else "neutral"
        peak_risk = max((float(e.get("risk_score", 0)) for e in events), default=0)
        if peak_risk >= 0.80:
            return f"{first} → кризис (rs={peak_risk:.2f}) → {last}"
        if peak_risk >= 0.60:
            return f"{first} → тревога (rs={peak_risk:.2f}) → {last}"
        return f"{first} → {last}"

    def _extract_breakthroughs(self, events: List[Dict]) -> List[str]:
        breakthroughs = []
        for e in events:
            if e.get("event_type") in ("payment_completed", "onboarding_completed",
                                       "analysis_processed"):
                breakthroughs.append(e.get("summary", e["event_type"]))
        return breakthroughs

    def _extract_unresolved(self, events: List[Dict]) -> List[str]:
        # Simplified: flag high-risk events without resolution
        unresolved = []
        for e in events:
            if float(e.get("risk_score", 0)) >= 0.70:
                et = e.get("event_type", "")
                if et not in ("escalation_resolved", "risk_resolved"):
                    unresolved.append(e.get("summary", "")[:100])
        return unresolved[:5]

    def _rule_narrative(
        self, events: List[Dict], key_facts: Dict,
        risk_trajectory: Dict, emotional_journey: str
    ) -> str:
        n = len(events)
        dominant_intent = key_facts.get("dominant_intent", "question")
        dominant_state = key_facts.get("dominant_state", "neutral")
        routes = ", ".join(key_facts.get("routes_visited", []))
        escalations = key_facts.get("escalation_count", 0)
        max_risk = risk_trajectory.get("max", 0)
        breakthroughs = key_facts.get("breakthroughs", [])

        narrative = (
            f"Клиент совершил {n} взаимодействий. "
            f"Доминирующий интент: {dominant_intent}, "
            f"эмоциональный фон: {dominant_state}. "
            f"Эмоциональная дуга: {emotional_journey}. "
            f"Посещённые маршруты: {routes}. "
        )
        if max_risk >= 0.60:
            narrative += f"Пиковый риск: {max_risk:.2f}. "
        if escalations:
            narrative += f"Эскалаций к специалисту: {escalations}. "
        if breakthroughs:
            narrative += f"Ключевые события: {chr(44).join(breakthroughs[:3])}. "
        return narrative.strip()

    async def _gpt_narrative(
        self, events: List[Dict], key_facts: Dict, emotional_journey: str
    ) -> str:
        """Generate narrative using GPT compression."""
        if not self._ask_claude:
            return self._rule_narrative(events, key_facts, {}, emotional_journey)
        try:
            system_prompt = (
                "Ты — система сжатия памяти AI-центра реабилитации. "
                "Твоя задача: создать точный нарратив истории клиента из списка событий. "
                "Максимум 5 предложений. Факты, динамика, риски, прорывы. Без лирики."
            )
            events_text = chr(10).join(
                f"- [{e.get('event_type','')}] rs={e.get('risk_score',0):.2f}: {e.get('summary','')[:80]}"
                for e in events[:30]
            )
            messages = [{"role": "user", "content": f"События:{chr(10)}{events_text}"}]
            narrative = await self._ask_claude(system_prompt, messages)
            return narrative[:1000] if narrative else self._rule_narrative(
                events, key_facts, {}, emotional_journey
            )
        except Exception as e:
            log.error("[COMPRESSOR] gpt_narrative error: %s", e)
            return self._rule_narrative(events, key_facts, {}, emotional_journey)

    async def _save_compressed(
        self, user_id: int, narrative: str, key_facts: Dict,
        risk_trajectory: Dict, route_history: List, topics: List,
        emotional_journey: str, breakthroughs: List, unresolved: List,
        covers_from, covers_to, event_ids: List[int], method: str
    ) -> Optional[int]:
        if not self._pool:
            return None
        try:
            q = ("INSERT INTO pm_memory_compressed"
                 " (user_id, covers_from, covers_to, timeline_ids, event_count,"
                 "  narrative_summary, key_facts, emotional_journey, risk_trajectory,"
                 "  route_history, topics_covered, breakthroughs, unresolved_issues, compression_method)"
                 " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)"
                 " RETURNING id")
            async with self._pool.acquire() as conn:
                return await conn.fetchval(
                    q, user_id, covers_from, covers_to, event_ids, len(event_ids),
                    narrative, json.dumps(key_facts), emotional_journey,
                    json.dumps(risk_trajectory), route_history, topics,
                    breakthroughs, unresolved, method
                )
        except Exception as e:
            log.error("[COMPRESSOR] save_compressed error: %s", e)
            return None

    async def _mark_compressed(self, event_ids: List[int], comp_id: int) -> None:
        if not self._pool or not event_ids:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pm_memory_timeline SET is_compressed=TRUE, compressed_into_id=$1"
                    " WHERE id = ANY($2)",
                    comp_id, event_ids
                )
        except Exception as e:
            log.error("[COMPRESSOR] mark_compressed error: %s", e)

    async def _update_profile_after_compression(self, user_id: int) -> None:
        if not self._pool:
            return
        try:
            from datetime import datetime, timezone, timedelta
            next_compression = datetime.now(timezone.utc) + timedelta(days=7)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pm_client_profiles SET last_compression_at=NOW(),"
                    " memory_compression_due=$1, memory_version=memory_version+1"
                    " WHERE user_id=$2",
                    next_compression, user_id
                )
        except Exception as e:
            log.error("[COMPRESSOR] update_profile error: %s", e)

    async def check_compression_needed(self, user_id: int) -> bool:
        """Return True if user needs compression."""
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM pm_memory_timeline"
                    " WHERE user_id=$1 AND is_compressed=FALSE",
                    user_id
                )
                return int(count or 0) >= _COMPRESS_AFTER_EVENTS
        except Exception as e:
            log.error("[COMPRESSOR] check error: %s", e)
            return False

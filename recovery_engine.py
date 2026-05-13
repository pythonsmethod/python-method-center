# -*- coding: utf-8 -*-
# =============================================================================
# PHASE 3.1 — Persistent Memory & Infrastructure Core
# Module: recovery_engine.py
# Python Method Digital Rehabilitation Center
# AI Operating System — Recovery Engine
#
# Purpose: Detect client disengagement and execute automated recovery workflows.
#          Backed by pm_recovery_plans table.
#
# Trigger types:
#   silence          — no message for X hours after active session
#   disengagement    — dropped off during critical stage (payment/onboarding)
#   crisis           — post-crisis follow-up needed
#   payment_lapse    — payment intent detected but not completed in 24h
#
# Recovery plan types:
#   gentle_reengagement  — soft check-in, no pressure
#   urgent_support       — escalation risk, warm outreach
#   payment_recovery     — return abandoned payment
#   post_crisis          — follow-up after escalation
# =============================================================================

from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("recovery_engine")

# Silence thresholds
_SILENCE_HOURS_ONBOARDING = 6       # paid, no message for 6h
_SILENCE_HOURS_ACTIVE = 24          # active client, silent 24h
_SILENCE_HOURS_COLD = 72            # general silence
_PAYMENT_LAPSE_HOURS = 24           # ready_to_pay but no payment


# Recovery plan templates
_RECOVERY_PLANS = {
    "gentle_reengagement": {
        "steps": [
            {"step": 1, "action": "send_soft_message", "delay_h": 0,
             "message_template": "reengagement_soft"},
            {"step": 2, "action": "send_value_message", "delay_h": 48,
             "message_template": "reengagement_value"},
            {"step": 3, "action": "notify_team_silent", "delay_h": 96,
             "message_template": None},
        ],
        "total_steps": 3,
    },
    "urgent_support": {
        "steps": [
            {"step": 1, "action": "notify_team_urgent", "delay_h": 0,
             "message_template": None},
            {"step": 2, "action": "send_support_message", "delay_h": 1,
             "message_template": "support_check_in"},
        ],
        "total_steps": 2,
    },
    "payment_recovery": {
        "steps": [
            {"step": 1, "action": "send_payment_reminder", "delay_h": 2,
             "message_template": "payment_soft_reminder"},
            {"step": 2, "action": "send_value_offer", "delay_h": 24,
             "message_template": "payment_value_bridge"},
            {"step": 3, "action": "notify_team_payment", "delay_h": 48,
             "message_template": None},
        ],
        "total_steps": 3,
    },
    "post_crisis": {
        "steps": [
            {"step": 1, "action": "notify_team_crisis_followup", "delay_h": 0,
             "message_template": None},
            {"step": 2, "action": "send_crisis_followup", "delay_h": 12,
             "message_template": "crisis_followup"},
        ],
        "total_steps": 2,
    },
}


class RecoveryEngine:
    """
    Detects client disengagement and executes automated recovery workflows.
    Runs as a background service (via async_queue or scheduled task).
    """

    def __init__(self, db_pool=None, send_message_fn=None, notify_team_fn=None):
        self._pool = db_pool
        self._send_message = send_message_fn
        self._notify_team = notify_team_fn
        log.info("[RECOVERY] RecoveryEngine initialized")

    async def scan_for_disengaged(self) -> List[Dict[str, Any]]:
        """
        Scan pm_client_profiles for clients who need recovery.
        Called periodically by the async queue scheduler.
        """
        if not self._pool:
            return []
        triggered = []
        try:
            async with self._pool.acquire() as conn:
                # Find silent paid clients (onboarding stage)
                rows = await conn.fetch(
                    "SELECT user_id, payment_status, last_contact_at,"
                    " last_active_route, escalation_count, current_risk_level"
                    " FROM pm_client_profiles"
                    " WHERE is_active = TRUE"
                    "   AND last_contact_at IS NOT NULL"
                    "   AND last_contact_at < NOW() - ($1 * INTERVAL '1 hour')"
                    "   AND NOT EXISTS ("
                    "     SELECT 1 FROM pm_recovery_plans"
                    "     WHERE pm_recovery_plans.user_id = pm_client_profiles.user_id"
                    "       AND status IN ('pending', 'in_progress')"
                    "   )",
                    _SILENCE_HOURS_ACTIVE,
                )
                for row in rows:
                    uid = row["user_id"]
                    payment = row["payment_status"]
                    route = row["last_active_route"] or ""
                    risk_level = row["current_risk_level"] or "none"

                    # Determine recovery type
                    if payment == "paid" and "onboarding" in route:
                        trigger_type = "disengagement"
                        plan_type = "gentle_reengagement"
                    elif payment == "pending" or "payment" in route:
                        trigger_type = "payment_lapse"
                        plan_type = "payment_recovery"
                    elif risk_level in ("high", "critical"):
                        trigger_type = "crisis"
                        plan_type = "urgent_support"
                    else:
                        trigger_type = "silence"
                        plan_type = "gentle_reengagement"

                    plan_id = await self.create_plan(uid, trigger_type, plan_type, dict(row))
                    if plan_id:
                        triggered.append({
                            "user_id": uid,
                            "trigger_type": trigger_type,
                            "plan_type": plan_type,
                            "plan_id": plan_id,
                        })

            log.info("[RECOVERY] scan complete, triggered %d plans", len(triggered))
        except Exception as e:
            log.error("[RECOVERY] scan error: %s", e)
        return triggered

    async def create_plan(
        self, user_id: int, trigger_type: str, plan_type: str,
        trigger_data: Dict = None
    ) -> Optional[str]:
        """Create a new recovery plan for a user."""
        if not self._pool:
            return None
        try:
            template = _RECOVERY_PLANS.get(plan_type, _RECOVERY_PLANS["gentle_reengagement"])
            steps = template["steps"]
            total_steps = template["total_steps"]
            first_delay_h = steps[0].get("delay_h", 0) if steps else 0

            async with self._pool.acquire() as conn:
                plan_id = await conn.fetchval(
                    "INSERT INTO pm_recovery_plans"
                    " (user_id, trigger_type, trigger_data, plan_type, steps,"
                    "  total_steps, next_action_at)"
                    " VALUES ($1, $2, $3, $4, $5, $6,"
                    "  NOW() + ($7 * INTERVAL '1 hour'))"
                    " RETURNING plan_id::text",
                    user_id, trigger_type, json.dumps(trigger_data or {}),
                    plan_type, json.dumps(steps), total_steps, first_delay_h,
                )
            log.info("[RECOVERY] plan created: user=%d type=%s plan_id=%s",
                      user_id, plan_type, plan_id)
            return plan_id
        except Exception as e:
            log.error("[RECOVERY] create_plan error: %s", e)
            return None

    async def execute_due_steps(self) -> int:
        """
        Execute all due recovery plan steps.
        Called by the async queue scheduler every hour.
        Returns number of steps executed.
        """
        if not self._pool:
            return 0
        executed = 0
        try:
            async with self._pool.acquire() as conn:
                plans = await conn.fetch(
                    "SELECT id, plan_id, user_id, plan_type, steps, current_step,"
                    " total_steps, trigger_type, trigger_data"
                    " FROM pm_recovery_plans"
                    " WHERE status IN ('pending', 'in_progress')"
                    "   AND next_action_at <= NOW()"
                    " ORDER BY next_action_at LIMIT 20",
                )

            for plan in plans:
                result = await self._execute_step(dict(plan))
                if result:
                    executed += 1

            log.info("[RECOVERY] executed %d steps", executed)
        except Exception as e:
            log.error("[RECOVERY] execute_due_steps error: %s", e)
        return executed

    async def _execute_step(self, plan: Dict) -> bool:
        """Execute one step of a recovery plan."""
        try:
            steps = json.loads(plan["steps"]) if isinstance(plan["steps"], str) else plan["steps"]
            current_step = int(plan["current_step"])
            user_id = plan["user_id"]

            if current_step >= len(steps):
                await self._complete_plan(plan["id"], success=True)
                return True

            step = steps[current_step]
            action = step.get("action", "")
            template = step.get("message_template")
            next_step_idx = current_step + 1

            # Execute action
            if action.startswith("send_") and template and self._send_message:
                msg = self._get_message_template(template, plan)
                await self._send_message(user_id, msg)
                log.info("[RECOVERY] sent %s to user=%d", template, user_id)

            elif action.startswith("notify_team") and self._notify_team:
                await self._notify_team(user_id, plan["trigger_type"], plan)
                log.info("[RECOVERY] notified team for user=%d", user_id)

            # Advance or complete plan
            if next_step_idx >= len(steps):
                await self._complete_plan(plan["id"], success=True)
            else:
                next_step = steps[next_step_idx]
                next_delay_h = next_step.get("delay_h", 24)
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE pm_recovery_plans SET current_step=$2,"
                        " status='in_progress'::recovery_status,"
                        " next_action_at=NOW() + ($3 * INTERVAL '1 hour')"
                        " WHERE id=$1",
                        plan["id"], next_step_idx, next_delay_h,
                    )
            return True
        except Exception as e:
            log.error("[RECOVERY] _execute_step error: %s", e)
            return False

    async def _complete_plan(self, plan_db_id: int, success: bool) -> None:
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pm_recovery_plans"
                    " SET status='completed'::recovery_status,"
                    " completed_at=NOW(), success=$2 WHERE id=$1",
                    plan_db_id, success,
                )
        except Exception as e:
            log.error("[RECOVERY] _complete_plan error: %s", e)

    def _get_message_template(self, template_name: str, plan: Dict) -> str:
        """Return localized message for a recovery template."""
        templates = {
            "reengagement_soft": (
                "Добрый день! Я заметил что давно не виделись. "
                "Как вы? Есть ли вопросы или я могу чем-то помочь?"
            ),
            "reengagement_value": (
                "Хочу напомнить — вы в любой момент можете вернуться к нашему разговору. "
                "Ваша ситуация важна и я готов помочь разобраться."
            ),
            "support_check_in": (
                "Я думал о нашем разговоре. "
                "Как вы чувствуете себя сейчас? Я здесь."
            ),
            "payment_soft_reminder": (
                "Добрый день! Мы обсуждали возможность работы с Python Method. "
                "Если у вас остались вопросы по формату или стоимости — я готов ответить."
            ),
            "payment_value_bridge": (
                "Хочу поделиться — клиенты обычно начинают замечать изменения уже в первые недели. "
                "Если готовы — следующий шаг всего один."
            ),
            "crisis_followup": (
                "Я хотел убедиться что вы в порядке. "
                "Наш специалист всегда доступен если нужна поддержка."
            ),
        }
        return templates.get(template_name, "Добрый день! Как вы?")

    async def mark_client_responded(self, user_id: int) -> None:
        """Call when client sends a message — marks active recovery as responded."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pm_recovery_plans"
                    " SET client_responded=TRUE, client_responded_at=NOW(),"
                    " status='completed'::recovery_status, success=TRUE, completed_at=NOW()"
                    " WHERE user_id=$1 AND status IN ('pending', 'in_progress')",
                    user_id,
                )
        except Exception as e:
            log.error("[RECOVERY] mark_responded error: %s", e)

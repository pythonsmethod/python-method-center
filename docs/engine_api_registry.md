# Engine API Registry

## Purpose

This document is the canonical record of public API contracts for core engine modules. It fixes the callable signatures that external modules may invoke.

A signature listed here is frozen: changes to parameters, return types, or module paths require an explicit architectural review and an update to this file in the same commit.

## Update Rules

1. Any change to a listed signature must update this file in the same commit.
2. Adding a new public method called by 2+ external modules requires a new row here.
3. Removing a listed method requires confirmation that all callers are updated.
4. Internal (private) methods prefixed with _ are not registered here.

---

GOVERNANCE WARNING: Callers must not reach into private methods or bypass the registered API. Direct module coupling outside this registry is an architectural violation.

---

## Registry Table

| Module | Public API | Full Signature | Callers | Notes |
|---|---|---|---|---|
| state_engine | analyze | analyze(contact_id: str, user_message: str, session: dict, context: dict) -> dict | orchestrator_core.py (Step 1 of handle_message) | Main entry point. Read-only, no DB, no side effects. FROZEN: drift caused [ORCH FATAL] Phase 4 Step 11. |
| auto_router | apply_auto_route | apply_auto_route(contact_id: str, session: Dict, proposed_route: str, ...) -> Optional[str] | orchestrator_core.py | Returns None if lock expired or proposed is a circuit-breaker. |
| emotional_overlay | detect_emotional_overlay | detect_emotional_overlay(intent: str, message: str, session: dict, context: dict) -> dict | orchestrator_core.py, agents.py | Pure function, no DB, no side effects. |
| emotional_overlay | update_overlay_session | update_overlay_session(session: Dict, overlay_result: dict) -> None | orchestrator_core.py | Mutates session in-place with overlay state. |
| emotional_overlay | build_overlay_injection | build_overlay_injection(overlay_package: Dict, agent_name: str, current_route: str) -> str | agents.py | Returns prompt injection string for LLM context. |
| context_package_builder | build_context_package | build_context_package(session: Dict, message_text: str = "") -> Dict | orchestrator_core.py | DUPLICATION: agents.py imports from central_ai_core instead. |
| central_ai_core | build_context_package | build_context_package(contact_id: str, session: dict, user_message: str = "") -> dict | agents.py | Used by agents pipeline. See duplication note below. |
| escalation_manager | EscalationManager.check | check(self, interrupt_result: Dict, context_package: Dict, session: Dict, risk_score: float) -> dict | orchestrator_core.py | Returns escalation decision dict. Tracks escalation count per session. |
| memory_writer | MemoryWriter.write | write(self, session: Dict, user_message: str, ai_reply: str, ...) -> dict | orchestrator_core.py (post-response) | Updates long-term client memory after each interaction. |
| risk_predictor | RiskPredictor.init | async init(self, db_pool=None) -> None | main.py (_init_risk_predictor_with_retry) | Initialises DB pool, runs idempotent migration on pm_risk_predictions. |
| risk_predictor | RiskPredictor.predict_for_user | async predict_for_user(self, user_id: int) -> Optional[RiskResult] | orchestrator_core.py | Main per-user risk evaluation. Returns RiskResult or None. |
| risk_predictor | RiskPredictor.get_risk_by_type | async get_risk_by_type(self) -> List[Dict] | dashboard_data.py | Aggregate risk counts by type for dashboard. |
| ai_router | classify_request | classify_request(task_type: str, message: str = "", route: str = "", context: dict = None) -> str | orchestrator_core.py, agents.py | Returns provider string. |
| ai_router | ask_ai | ask_ai(system_prompt: str, messages: list, max_tokens: int = 600, ...) -> str | agents.py | Unified AI call wrapper. Routes to Claude or GPT. |

---

## Duplication Registry

| Canonical Module | Duplicate Module | Risk | Resolution |
|---|---|---|---|
| context_package_builder.build_context_package | central_ai_core.build_context_package | HIGH: divergence produces silent context errors | Unify to single import in future phase. Do not add a third implementation. |

---

## Frozen Signatures (Change History)

| Date | Signature | Change Type | Reason |
|---|---|---|---|
| 2026-05-17 | state_engine.analyze(contact_id, user_message, session, context) | Fixed: was analyze(message_text, session) | Phase 4 Step 11: 2-arg call caused [ORCH FATAL] on every webhook. Commit 68cfa8d. |

---

Last updated: 2026-05-17 | Phase 4 Stabilization
Maintainer: architecture governance review

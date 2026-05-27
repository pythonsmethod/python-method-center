# Ownership Matrix
# Python Method Center — Canonical State Ownership

**Document type:** Canonical governance record
**Status:** ACTIVE — Phase 4
**Authority:** Biblia System — Section 40.2 (Single Source of Truth Rule)
**Effective:** 2026-05-27

This document is the single source of truth for state field ownership across all runtime modules, agents, and background tasks. It governs both runtime application state and database write access. It must be updated in the same commit as any change that introduces a new writer to any tracked field.

---

## Section 1 — Runtime State Ownership

### 1.1 route_state

| Property | Value |
|---|---|
| **Canonical Owner** | `route_engine.py` |
| **Allowed Writers** | `route_engine.py` only |
| **Allowed Readers** | `orchestrator_core.py`, `agents.py`, `dashboard_data.py`, `context_engine.py`, `risk_engine.py` |
| **Forbidden Writers** | `dashboard_data.py`, `agents.py`, AI agent prompts, any new module without explicit amendment to this document |
| **Source of Truth** | `pm_client_profiles.last_active_route` (persisted), `route_engine.py` (runtime) |
| **Conflict Rule** | If any module other than `route_engine.py` writes `route_state`, the write is invalid. Requires architectural review before merge. |

---

### 1.2 risk_score

| Property | Value |
|---|---|
| **Canonical Owner** | `risk_engine.py` |
| **Allowed Writers** | `risk_engine.py` only |
| **Allowed Recalculators** | `risk_engine.py` only. No module may recalculate or override `risk_score` independently. |
| **Allowed Readers** | `orchestrator_core.py`, `agents.py`, `escalation_engine.py`, `dashboard_data.py`, `context_engine.py` |
| **Forbidden Writers** | `dashboard_data.py`, `agents.py`, AI agent prompts, any inline calculation in `main.py` or `orchestrator_core.py` |
| **Source of Truth** | `pm_risk_predictions` table (persisted), `risk_engine.py` (runtime) |
| **Conflict Rule** | If `risk_score` is calculated outside `risk_engine.py`, it is an unauthorised write. Requires immediate rollback. |

---

### 1.3 escalation_state

| Property | Value |
|---|---|
| **Canonical Owner** | `escalation_engine.py` |
| **Who May Open Escalation** | `escalation_engine.py` only, triggered by `risk_engine.py` threshold breach or explicit operator action |
| **Who May Close Escalation** | `escalation_engine.py` only, after explicit resolution confirmed |
| **Who Is Notified** | Configured notification targets (Telegram operator channel). Notification logic lives in `escalation_engine.py`. |
| **Allowed Readers** | `orchestrator_core.py`, `agents.py`, `dashboard_data.py` |
| **Forbidden Writers** | `dashboard_data.py`, AI agent prompts, `orchestrator_core.py` directly |
| **Conflict Rule** | Escalation state may not be modified by orchestrator or agent logic. Requires architectural review. |

---

### 1.4 context_package

| Property | Value |
|---|---|
| **Canonical Owner** | `context_engine.py` |
| **Who Assembles** | `context_engine.py` only |
| **Allowed Readers** | `agents.py`, `orchestrator_core.py`, any engine that receives `context_package` as input parameter |
| **Who Must Not Mutate** | Receiving agents and engines must treat `context_package` as immutable input. Mutation is forbidden. |
| **Forbidden Writers** | `dashboard_data.py`, AI agent prompts, `agents.py` |
| **Conflict Rule** | If an agent modifies `context_package` in place, it is a mutation violation. The modified copy must not be persisted. |

---

### 1.5 memory_layers

Memory is split into five distinct layers. Each has its own canonical owner. Layers must not be merged or cross-written.

| Layer | Canonical Owner | Allowed Writers | Allowed Readers | Forbidden Writers |
|---|---|---|---|---|
| **current_session_history** | `memory_engine.py` | `memory_engine.py` | `context_engine.py`, `agents.py` | `dashboard_data.py`, AI prompts |
| **short_term_memory** | `memory_engine.py` | `memory_engine.py` | `context_engine.py`, `orchestrator_core.py` | `dashboard_data.py`, AI prompts |
| **active_stage_memory** | `memory_engine.py` | `memory_engine.py` | `agents.py`, `context_engine.py` | `dashboard_data.py`, AI prompts |
| **long_term_timeline** | `memory_engine.py` | `memory_engine.py` only | `context_engine.py`, `dashboard_data.py` (read) | Any direct inline write from `main.py` or agents |
| **institutional_memory** | `institutional_memory_intelligence.py` | `institutional_memory_intelligence.py` only | `dashboard_data.py` (read), `context_engine.py` | All other modules |

**Rule:** No memory layer may be written by an AI agent prompt. Memory is a runtime concern. Prompts are stateless consumers of context.

---

### 1.6 shadow_metrics

| Property | Value |
|---|---|
| **Canonical Owner** | `shadow_metrics_engine.py` (target). Current interim: `main.py` (architectural debt) |
| **Allowed Writers** | `shadow_metrics_engine.py` after extraction. Until then: `main.py` only by explicit exception. |
| **Allowed Readers** | `dashboard_data.py` (read only), `continuity_intelligence.py` (read only) |
| **Dashboard Boundary** | `dashboard_data.py` reads `shadow_metrics`. It must not write, aggregate, or transform them. |
| **Forbidden Writers** | `dashboard_data.py`, AI agent prompts, any new module until extraction is complete |
| **Debt Note** | `shadow_metrics` table creation and insert are currently inline in `main.py`. Must be extracted to `shadow_metrics_engine.py`. |

---

### 1.7 dashboard_data

| Property | Value |
|---|---|
| **Module** | `dashboard_data.py` |
| **Role** | Read-only data layer. No exceptions. |
| **Allowed Operations** | SELECT queries only |
| **Forbidden Operations** | INSERT, UPDATE, DELETE, any state mutation, any business logic execution |
| **Forbidden Roles** | Not an orchestrator. Not a source of truth. Does not trigger state changes. |
| **Enforcement** | Any PR adding write methods to `dashboard_data.py` is rejected without exception. |

---

### 1.8 payment_state

| Property | Value |
|---|---|
| **Canonical Owner** | `payment_engine.py` |
| **Who Writes paid/unpaid** | `payment_engine.py` only, triggered by confirmed payment event |
| **Allowed Readers** | `orchestrator_core.py`, `agents.py`, `dashboard_data.py`, `route_engine.py` |
| **Forbidden Writers** | `agents.py`, AI agent prompts, `dashboard_data.py`, any module receiving payment status as input |
| **Source of Truth** | `pm_client_profiles` payment status columns |
| **Conflict Rule** | Payment state must not be inferred or set by agent logic. If confirmation is ambiguous, escalation is required before state update. |

---

### 1.9 analysis_dossier_state

| Property | Value |
|---|---|
| **Canonical Owner** | `dossier_engine.py` |
| **Who Accepts Materials** | `dossier_engine.py` only |
| **Who Confirms Readiness** | `dossier_engine.py` sets `dossier_ready` flag after completeness check |
| **Who Transfers to Karen** | `orchestrator_core.py` initiates transfer after `dossier_ready = true`. Does not modify dossier state directly. |
| **Allowed Readers** | `orchestrator_core.py`, `agents.py`, `dashboard_data.py` |
| **Forbidden Writers** | `dashboard_data.py`, AI agent prompts, direct agent writes |
| **Conflict Rule** | Dossier completeness determined by agent logic rather than `dossier_engine.py` is a governance violation. |

---

### 1.10 client_profile

| Property | Value |
|---|---|
| **Canonical Storage** | `pm_client_profiles` table |
| **Allowed Writers** | Module-column assignment defined in Section 2. Each column has exactly one authorised writer. |
| **Conflict Rule** | Two modules may not write the same column. If detected, one must be designated sole writer; the other converted to read-only. Requires architectural review before merge. |
| **Forbidden Writers** | `dashboard_data.py`, AI agent prompts, any module not listed in Section 2 |
| **AI Agent Rule** | AI agent prompts do not own persistent state. They are stateless consumers of context. Persistence is handled exclusively by engine modules. |

---

## Section 2 — Database Table Write Ownership

### Table: `pm_client_profiles`

| Module | Columns Written | Write Frequency | Risk Level |
|---|---|---|---|
| `orchestrator_core.py` | `long_term_rehabilitation_state`, `longitudinal_stability_score`, `last_active_route`, `last_active_agent` | Per message | HIGH |
| `clinical_continuity_engine.py` | `continuity_state`, `continuity_score`, `continuity_gap_detected`, `stage_transition_risk` | Per message | MEDIUM |
| `rehabilitation_route_simulation.py` | `route_simulation_state`, `simulation_stability_score`, `continuity_recovery_probability` | Per eval cycle | MEDIUM |
| `rehabilitation_state_machine.py` | `rehabilitation_state`, `rehabilitation_stage`, `previous_rehabilitation_state` | Per message | MEDIUM |
| `trajectory_intelligence_engine.py` | `trajectory_state`, `trajectory_score`, `trajectory_direction` | Per message | MEDIUM |
| `dynamic_pacing_intelligence.py` | `pacing_state`, `pacing_score`, `pacing_stability_score` | Per message | MEDIUM |
| `multi_stage_orchestration_engine.py` | `orchestration_state`, `current_primary_stage`, `active_stage_count` | Per message | MEDIUM |
| `expert_load_balancing_engine.py` | `expert_load_state`, `support_congestion_score`, `escalation_queue_pressure` | Every N minutes | LOW |
| `central_cognitive_orchestrator.py` | `system_coherence_state`, `dominant_operational_priority`, `governance_conflict_detected` | Every N minutes | LOW |
| `adaptive_rehabilitation_strategy.py` | `adaptive_strategy_state`, `recommended_continuity_strategy`, `strategy_confidence_score` | Per eval cycle | LOW |
| `recovery_policy_engine.py` | `silence_respect` | Event-driven | LOW |
| `silent_user_scanner.py` | Scan tracking fields | Periodic | LOW |
| `memory_compressor.py` | Compression metadata fields | Triggered | LOW |
| `proactive_message_dispatcher.py` | Last proactive send fields | Event-driven | LOW |
| `memory_engine.py` | `last_contact_at`, `total_sessions`, `total_messages` | Per message | MEDIUM |

### Table: `pm_center_continuity_metrics`

| Module | Operation | Notes |
|---|---|---|
| `meta_continuity_intelligence.py` | INSERT | Sole writer. |
| `dashboard_data.py` | SELECT | Reader only. |

### Table: `pm_institutional_memory`

| Module | Operation | Notes |
|---|---|---|
| `institutional_memory_intelligence.py` | INSERT | Sole writer. |
| `dashboard_data.py` | SELECT | Reader only. |

### Table: `pm_runtime_health`

| Module | Operation | Notes |
|---|---|---|
| `runtime_supervisor.py` | INSERT | Sole writer. |
| `dashboard_data.py` | SELECT | Reader only. |

### Table: `shadow_metrics`

| Module | Operation | Notes |
|---|---|---|
| `main.py` (interim) | CREATE TABLE + INSERT | Interim sole writer. Must be extracted. |
| `continuity_intelligence.py` | SELECT | Reader only. |
| `dashboard_data.py` | SELECT | Reader only. |

### Table: `pm_risk_predictions`

| Module | Operation | Notes |
|---|---|---|
| `risk_predictor.py` | INSERT ON CONFLICT DO UPDATE | Sole writer. Upsert pattern. |
| `dashboard_data.py` | SELECT | Reader only. |
| `recovery_engine.py` | SELECT | Reader only. |

---

## Section 3 — Background Loop Registry

| Loop | Location | Cycle Interval | Target Table | Sole Writer |
|---|---|---|---|---|
| `_meta_continuity_loop()` | `main.py` | 600 s | `pm_center_continuity_metrics` | Yes |
| `_init_institutional_memory_loop()` | `main.py` | 1800 s | `pm_institutional_memory` | Yes |
| `_monitoring_loop()` | `runtime_supervisor.py` | `_HEALTH_INTERVAL_S` | `pm_runtime_health` | Yes |
| `start_scheduled_loop()` | `silent_user_scanner.py` | Configurable | `pm_client_profiles` (scan fields) | Yes |
| Queue worker | `async_queue.py` | `_POLL_INTERVAL_S` | `pm_queue_jobs` | Shared |

---

## Section 4 — Governance Rules

### Conflict Rule

If two modules write the same field or column, a conflict exists. Conflicts are not resolved at runtime. Conflicts must be resolved before the conflicting code is merged by designating one module as the sole canonical writer. The non-canonical module must be converted to a read-only path. Conflict resolution requires an explicit commit to this document naming the designated writer.

### Adding a New Writer

1. Identify the field or column to be written.
2. Check this document for the current canonical owner.
3. If an owner exists: the new module may not write that field. It must use a read path or request architectural review.
4. If no owner exists: declare ownership in this document before writing any code.
5. The ownership declaration must be committed in the same PR as the code change.
6. No new writer is permitted without this process. No exceptions.

### Violation Handling

A violation occurs when any of the following is true:
- A module writes a field it does not own.
- A new writer is introduced without updating this document.
- `dashboard_data.py` contains a write method.
- An AI agent prompt persists state directly.
- Two modules write the same field without a declared arbitration rule.

Violations are not resolved in PR comments. Violations require: (a) immediate rollback of the violating code, or (b) an architectural review resulting in a formal amendment to this document committed before re-merge.

---

## Governance Notes

- `pm_client_profiles` has 16+ concurrent writers. Column separation is enforced by this document until a write coordinator is implemented.
- `shadow_metrics` write logic is currently inline in `main.py`. Architectural debt. Extraction to `shadow_metrics_engine.py` required before any new writer is added.
- AI agent prompts do not own persistent state. All persistence is the responsibility of engine modules.
- Documents are governance, not runtime state. This file governs what code may do. It does not execute at runtime.

---

*Ownership Matrix — Phase 4 Stabilization*
*Supersedes: DB Write Ownership Matrix (2026-05-17)*
*Committed: 2026-05-27*

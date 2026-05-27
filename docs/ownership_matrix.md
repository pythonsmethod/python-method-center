# Ownership Matrix
# Python Method Center — Canonical State Ownership

**Document type:** Canonical governance record
**Status:** ACTIVE — Phase 4
**Authority:** Biblia System — Section 40.2 (Single Source of Truth Rule)
**Effective:** 2026-05-27

This document is the single source of truth for state field ownership across all runtime modules, agents, and background tasks.
It governs both runtime application state and database write access.
It must be updated in the same commit as any change that introduces a new writer to any tracked field.

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
| **Conflict Rule** | Escalation state may not be modified by orchestrator or agent logic. Any such path requires architectural review. |

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
| **Canonical Owner** | `shadow_metrics_engine.py` (target). Current interim: `main.py` (known architectural debt) |
| **Allowed Writers** | `shadow_metrics_engine.py` after extraction. Until then: `main.py` only by explicit exception. |
| **Allowed Readers** | `dashboard_data.py` (read only), `continuity_intelligence.py` (read only) |
| **Dashboard Boundary** | `dashboard_data.py` reads `shadow_metrics`. It must not write, aggregate, or transform them. |
| **Forbidden Writers** | `dashboard_data.py`, AI agent prompts, any new module until extraction is complete |
| **Debt Note** | `shadow_metrics` table creation and insert are currently inline in `main.py`. Must be extracted to `shadow_metrics_engine.py` in a dedicated refactor phase. |

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
# TEST

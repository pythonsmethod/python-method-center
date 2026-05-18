# DB Write Ownership Matrix

## Purpose

This document is the **canonical governance record** of which runtime modules are
authorised to write to production database tables. It must be updated whenever a
new `INSERT`, `UPDATE`, or `DELETE` path is introduced in any module.

## Update Rules

1. Any developer adding a new `UPDATE`/`INSERT` on a tracked table **must** add a
2.    row to this matrix in the same commit.
3.2. No module may write to a table column it does not own without explicit review.
  3. Column-ownership conflicts (two modules updating the same column) require an
  4.    architectural review before merge.
  5.4. This file is reviewed on every deploy that touches `orchestrator_core.py`,
       `agents.py`, or any `migrate_*.sql` file.

    ---

    > ⚠️ **GOVERNANCE WARNING**
    > **No new writer may be added to `pm_client_profiles` or any tracked table without
    > updating this matrix.** Violations introduce undetected schema drift and silent
    > analytics corruption. This warning applies to all contributors and all phases.

    ---

    ## Section 2 — Table Write Ownership

    ### Table: `pm_client_profiles`

    | Module | Columns Written | Trigger | Write Frequency | Risk Level |
    |---|---|---|---|---|
    | `orchestrator_core.py` | `long_term_rehabilitation_state`, `longitudinal_stability_score`, `rehabilitation_resilience_score`, `last_active_route`, `last_active_agent` | Per webhook (post-response) | Per message | 🔴 HIGH — core pipeline writer |
    | `clinical_continuity_engine.py` | `continuity_state`, `continuity_score`, `continuity_gap_detected`, `stage_transition_risk` | Per webhook (async task) | Per message | 🟡 MEDIUM — async, non-blocking |
    | `rehabilitation_route_simulation.py` | `route_simulation_state`, `simulation_stability_score`, `continuity_recovery_probability`, `pacing_stabilization_effect`, `overload_mitigation_effect` | Background / per webhook | Per eval cycle | 🟡 MEDIUM |
    | `rehabilitation_state_machine.py` | `rehabilitation_state`, `rehabilitation_stage`, `previous_rehabilitation_state` | Per webhook (async task) | Per message | 🟡 MEDIUM |
    | `trajectory_intelligence_engine.py` | `trajectory_state`, `trajectory_score`, `trajectory_direction` | Per webhook (async task) | Per message | 🟡 MEDIUM |
    | `dynamic_pacing_intelligence.py` | `pacing_state`, `pacing_score`, `pacing_stability_score` | Per webhook (async task) | Per message | 🟡 MEDIUM |
    | `multi_stage_orchestration_engine.py` | `orchestration_state`, `current_primary_stage`, `active_stage_count` | Per webhook (async task) | Per message | 🟡 MEDIUM |
    | `expert_load_balancing_engine.py` | `expert_load_state`, `support_congestion_score`, `escalation_queue_pressure` | Background poll | Every N minutes | 🟢 LOW — background only |
    | `central_cognitive_orchestrator.py` | `system_coherence_state`, `dominant_operational_priority`, `governance_conflict_detected` | Background poll | Every N minutes | 🟢 LOW — background only |
    | `adaptive_rehabilitation_strategy.py` | `adaptive_strategy_state`, `recommended_continuity_strategy`, `strategy_confidence_score` | Background / per webhook | Per eval cycle | 🟢 LOW |
    | `recovery_policy_engine.py` | `silence_respect` | Policy enforcement | Event-driven | 🟢 LOW |
    | `silent_user_scanner.py` | Scan tracking fields (last_scan_at, scan_count) | Background scan loop | Periodic | 🟢 LOW — observability only |
    | `memory_compressor.py` | Compression metadata fields | Post-compression | Triggered | 🟢 LOW |
    | `proactive_message_dispatcher.py` | Last proactive send fields | Post-send | Event-driven | 🟢 LOW |
    | `memory_engine.py` | `last_contact_at`, `total_sessions`, `total_messages` | Per webhook | Per message | 🟡 MEDIUM — high frequency |
    | `risk_predictor.py` (via `pm_risk_predictions`) | Writes to separate table, reads `pm_client_profiles` | Async | Per user | 🟡 MEDIUM |

    > **Column Ownership Rule:** Each column in `pm_client_profiles` must be owned by
    > exactly one writer module. If two modules need to update the same column, one
    > must be designated the **authoritative writer** and the other must use a read
    > path only.

    ---

    ### Table: `pm_center_continuity_metrics`

    | Module | Operation | Trigger | Notes |
    |---|---|---|---|
    | `meta_continuity_intelligence.py` | `INSERT` | Background loop (every 10 min) | **Sole writer.** Read-only on `pm_client_profiles`. |
    | `dashboard_data.py` | `SELECT` | Dashboard API call | Reader only. |

    ---

    ### Table: `pm_institutional_memory`

    | Module | Operation | Trigger | Notes |
    |---|---|---|---|
    | `institutional_memory_intelligence.py` | `INSERT` | Background loop (every 30 min) | **Sole writer.** |
    | `dashboard_data.py` | `SELECT` | Dashboard API call | Reader only. |

    ---

    ### Table: `pm_runtime_health`

    | Module | Operation | Trigger | Notes |
    |---|---|---|---|
    | `runtime_supervisor.py` | `INSERT` | Monitoring loop (`_HEALTH_INTERVAL_S`) | **Sole writer.** |
    | `dashboard_data.py` | `SELECT` | Dashboard API call | Reader only. |

    ---

    ### Table: `shadow_metrics`

    | Module | Operation | Trigger | Notes |
    |---|---|---|---|
    | `main.py` (inline) | `CREATE TABLE` + `INSERT` | Startup + per webhook | Created and written in `main.py` directly. Architectural debt: should be extracted. |
    | `continuity_intelligence.py` | `SELECT` | Per message | Reader only. |

    ---

    ### Table: `pm_risk_predictions`

    | Module | Operation | Trigger | Notes |
    |---|---|---|---|
    | `risk_predictor.py` | `INSERT … ON CONFLICT DO UPDATE` | Async, per user | **Sole writer.** Upsert pattern. |
    | `dashboard_data.py` | `SELECT` | Dashboard API call | Reader only. |
    | `recovery_engine.py` | `SELECT` | Recovery workflow | Reader only. |

    ---

    ## Section 3 — Background Loop Registry

    | Loop | Location | Start Delay | Cycle Interval | Target Table | Sole Writer? |
    |---|---|---|---|---|---|
    | `_meta_continuity_loop()` | `main.py` | 300 s | 600 s | `pm_center_continuity_metrics` | ✅ Yes |
    | `_init_institutional_memory_loop()` | `main.py` | 600 s | 1800 s (error retry) | `pm_institutional_memory` | ✅ Yes |
    | `_monitoring_loop()` | `runtime_supervisor.py` | 0 s | `_HEALTH_INTERVAL_S` | `pm_runtime_health` | ✅ Yes |
    | `start_scheduled_loop()` | `silent_user_scanner.py` | Configurable | Configurable | `pm_client_profiles` (scan fields) | ✅ Yes |
    | Queue worker | `async_queue.py` | 0 s | `_POLL_INTERVAL_S` | `pm_queue_jobs` | Shared |

    ---

    ## Governance Notes

    - **`pm_client_profiles` has 16+ concurrent writers** — the highest risk table in the system.
      No ORM or write coordinator exists. Each module owns distinct column sets; this
        must be enforced by policy (this document) until a write coordinator is implemented.
        - **`shadow_metrics` table creation is inline in `main.py`** — a known architectural debt item.
          It should be extracted to a dedicated migration file and module in a future phase.
          - **No migration registry table exists** as of Phase 4. A `schema_migrations` table
            is recommended before the next module addition.

            ---

            _Last updated: 2026-05-17 | Phase 4 Stabilization_
            _Maintainer: architecture governance review_

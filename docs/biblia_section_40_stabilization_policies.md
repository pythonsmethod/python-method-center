# Biblia System — Section 40
# PHASE 4 STABILIZATION POLICIES

**Document type:** Canonical governance policy
**Status:** ACTIVE — Phase 4
**Authority:** Overrides all conflicting inline comments, PR discussions, or verbal agreements.
**Effective:** 2026-05-27

---

## SCOPE

This section governs architectural decisions during Phase 4 stabilization.
It applies to all contributors, all engines, all pipelines.
No exceptions without written architecture justification committed to this repository.

---

## POLICY 40.1 — ENGINE SIGNATURE CHANGE PROTOCOL

Any change to a public engine signature is a breaking change.

**Rules:**
- All callers must be audited before any signature change is merged.
- Sync and async pipelines must be updated in the same commit. Split updates are forbidden.
- Silent signature changes are forbidden. Every signature change requires an explicit entry in `engine_api_registry.md`.
- Engine API drift is classified as a critical-risk event. It blocks deployment until all callers are verified.

**Definition of "public signature":** any function, method, or class interface called from outside its own module.

---

## POLICY 40.2 — SINGLE SOURCE OF TRUTH RULE

Each system state field has exactly one canonical writer. No field may have two writers.

**Canonical ownership (non-exhaustive):**

| Field | Canonical Owner |
|---|---|
| `route_state` | `route_engine.py` |
| `risk_score` | `risk_engine.py` |
| `escalation_state` | `escalation_engine.py` |
| `context_package` | `context_engine.py` |
| `memory layers` | `memory_engine.py` |
| `shadow_metrics` | `shadow_metrics_engine.py` |

**Rules:**
- If ownership of a field is not recorded in `ownership_matrix.md`, no new writer may be introduced until ownership is declared.
- Ownership conflicts are blocking issues. They are not resolved at runtime. They are resolved in documentation before code is written.
- Readers are unrestricted. Only writers are governed.

---

## POLICY 40.3 — BACKGROUND TASK FAN-OUT RULE

Background task growth is not free. Every new background task must justify its existence.

**Rules:**
- Observability must be added before optimization. No task may be accelerated or multiplied before its current behavior is measurable.
- Priority systems (task queues, weighted schedulers) are forbidden without supporting metrics that demonstrate necessity.
- Unlimited fan-out growth is forbidden. Any task that spawns subtasks must define a maximum concurrency ceiling.
- Justification requirement: every new background task must document its trigger condition, expected frequency, and failure behavior before merging.

---

## POLICY 40.4 — DASHBOARD READ-ONLY BOUNDARY

`dashboard_data.py` is a read-only data layer. This boundary is permanent.

**Rules:**
- Write methods are forbidden in `dashboard_data.py`.
- Dashboard code must not contain business logic. Business logic belongs in engines.
- Dashboard must not act as an orchestrator. It does not trigger state changes.
- Dashboard must not be the source of truth for any field. It reflects state. It does not set it.
- Any pull request that introduces write behavior, conditional branching on business rules, or engine calls into `dashboard_data.py` is rejected.

---

## POLICY 40.5 — NO NEW ORCHESTRATOR RULE

The system has one orchestration layer. It will not grow.

**Forbidden without written architecture justification:**
- New orchestrator modules
- New pipeline coordinator classes
- New router layers
- New central intelligence components
- New meta-dispatch systems
- Any module whose primary function is to decide what other modules do

**Justification process:**
1. Author writes architecture justification document.
2. Document is committed to `docs/` before any code is written.
3. Justification must answer: what existing layer cannot be extended, and why a new layer is the only solution.
4. Without this document, the pull request is rejected at review regardless of functionality.

---

## ENFORCEMENT

These policies are not guidelines. They are structural constraints.

Violations are not resolved through discussion in pull request comments.
Violations require policy amendment or rollback.
Policy amendments require a commit to this document with explicit reasoning.

---

*Biblia System — Section 40 — Phase 4 Stabilization Policies*
*Committed: 2026-05-27*

# Route Implementation Plan — Post-Freeze

**Document Type:** Implementation Plan (Freeze-Safe Reference)
**Status:** PENDING — awaiting stabilization freeze lift
**Project:** Python Method Digital Rehabilitation Center
**Created:** 2026-05-20
**Authority:** pythonsmethod (owner)

---

## Overview

This document defines the step-by-step implementation plan for activating the route architecture described in docs/route_architecture.md after the Phase 4 stabilization freeze is officially lifted.

**This document does not change any code.**
**This document does not apply any SQL.**
**This document does not trigger any deployment.**

It is a planning record only. All actions defined here require the freeze to be lifted per docs/stabilization_freeze_notice.md before any execution.

---

## 1. Current Frozen Status

The following documents have been created during the freeze as specification-only artefacts. No runtime code has been modified. No SQL has been applied. No deployments have been made for route architecture.

| Document | Commit | Status |
|----------|--------|--------|
| docs/route_architecture.md | 6a346e6 | Created — docs only |
| docs/migrate_route_state.sql | d8f6d87 | Created — spec only, not applied |
| docs/route_implementation_plan_after_freeze.md | this file | Created — planning only |
| runtime code | — | Untouched |
| pm_sessions DB columns | — | Not yet added |
| pm_client_profiles DB columns | — | Not yet added |
| Deployment | — | Not performed |

All three documents are freeze-safe additions to the docs/ registry. They comply with the stabilization_freeze_notice.md rule: "Adding to docs/ registry files — No code changes accompany documentation."

---

## 2. Preconditions Before Implementation

All of the following conditions must be satisfied before any phase of this plan is executed.

### 2.1 Official Freeze Lift

The stabilization freeze must be officially lifted with the designated commit:

```
governance: lift stabilization freeze — Phase 4 complete
```

This commit must appear in the main branch history before any route implementation work begins. No exceptions.

Hard requirements from stabilization_freeze_notice.md must all be met:
- 7 consecutive clean days with no ORCH FATAL
- Zero restart loops in the 7-day window
- Mean webhook latency < 5000ms across 20+ webhooks
- total_webhooks_processed >= 50
- At least 1 observed intent successfully resolved (intent != unknown)
- No active Telegram 499 retry cascade at scale

### 2.2 Production Health Check

Before Phase A begins, verify the following via /health endpoint and Railway logs:

- `ok: true` in /health response
- `total_webhooks_processed` reflects real user activity
- No ORCH FATAL in Railway logs for the preceding 24 hours
- No Traceback entries in Railway logs for the preceding 24 hours
- `claude_available: true` and `gpt_available: true`
- `shadow_mode` status documented (affects Phase E planning)

### 2.3 Database Backup Awareness

Before Phase A (DB migration), verify:
- A Railway PostgreSQL backup or snapshot is available
- The DBA or owner is aware that schema changes are being applied
- Rollback SQL from docs/migrate_route_state.sql Section 5 is reviewed and ready
- The migration has been reviewed against the current live schema to confirm no column name conflicts

To verify current live columns before applying:
```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name IN ('pm_sessions', 'pm_client_profiles')
ORDER BY table_name, column_name;
```

### 2.4 Migration Approval

docs/migrate_route_state.sql (commit d8f6d87) must be reviewed and explicitly approved by pythonsmethod (owner) before Phase A begins.

Approval is confirmed by: owner review of the SQL spec + verbal or written go-ahead.

---

## 3. Implementation Phases

Each phase is atomic: one phase = one commit = one deploy = one verification.
Do not proceed to the next phase until the current phase is verified in production.

---

### Phase A — DB Route Fields

**Goal:** Add all route state columns to pm_sessions and pm_client_profiles. These are additive, nullable-safe, defaulted columns. No existing data is changed. No application reads them yet.

**Files affected:**
- agents.py (modify `_init_db()` only)
- Execute docs/migrate_route_state.sql against production DB

**What changes:**

In agents.py `_init_db()`, append to the existing ALTER TABLE list:
```python
"ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS care_route TEXT NOT NULL DEFAULT 'none'",
"ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS care_duration TEXT NOT NULL DEFAULT 'undefined'",
"ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS ai_support_level TEXT NOT NULL DEFAULT 'navigation'",
"ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS karen_access TEXT NOT NULL DEFAULT 'pending'",
"ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS onboarding_stage TEXT NOT NULL DEFAULT 'not_started'",
"ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS rehab_stage TEXT NOT NULL DEFAULT 'pre_start'",
"ALTER TABLE pm_sessions ADD COLUMN IF NOT EXISTS renewal_status TEXT NOT NULL DEFAULT 'none'",
```

Apply docs/migrate_route_state.sql Section 2 (pm_client_profiles) and Section 3 (indexes) directly against production DB via Railway PostgreSQL console.

**What must NOT be touched:**
- orchestrator_core.py
- route_resolver.py
- auto_router.py
- state_engine.py
- Any existing columns in pm_sessions or pm_client_profiles
- context_package_builder.py
- Any existing SELECT/UPDATE queries

**Verification steps:**
1. Deploy and monitor Railway logs for 5 minutes
2. Confirm no ORCH FATAL, no Traceback
3. Send a test message and verify ORCH DONE appears in logs
4. Run verification SQL from docs/migrate_route_state.sql Section 4
5. Confirm all 7 new columns exist in pm_sessions with correct defaults
6. Confirm all 10 new columns exist in pm_client_profiles with correct defaults
7. Confirm 3 new indexes exist

**Rollback notes:**
- If ORCH FATAL appears after deploy: revert agents.py immediately
- If DB migration partially applied: run rollback SQL from docs/migrate_route_state.sql Section 5
- Rollback is safe because no application code reads the new columns yet

**Recommended commit message:**
```
feat(phase-a): add route state DB fields to pm_sessions and pm_client_profiles
```

---

### Phase B — Session / State Model

**Goal:** Make agents.py aware of the new columns. Extend load_session() and save_session() to read and write all 7 new fields from pm_sessions. Extend memory_engine.py ALLOWED whitelist to include the 10 new pm_client_profiles fields.

**Files affected:**
- agents.py (`load_session()`, `save_session()` only)
- memory_engine.py (ALLOWED dict in `upsert_client_profile()` only)

**What changes:**

In agents.py `load_session()`, extend the SELECT to include:
```
care_route, care_duration, ai_support_level, karen_access,
onboarding_stage, rehab_stage, renewal_status
```
and populate session dict with these values (default to column defaults if NULL).

In agents.py `save_session()`, extend the UPDATE to persist:
```
care_route, care_duration, ai_support_level, karen_access,
onboarding_stage, rehab_stage, renewal_status
```

In memory_engine.py ALLOWED dict, add:
```python
"care_route", "care_duration", "support_level", "karen_access",
"ai_support_level", "onboarding_stage", "rehab_stage",
"renewal_status", "care_started_at", "care_expires_at",
```

**What must NOT be touched:**
- orchestrator_core.py
- route_resolver.py
- auto_router.py
- state_engine.py
- context_package_builder.py
- Any existing fields in load_session / save_session SELECT/UPDATE
- Any existing fields in ALLOWED dict

**Verification steps:**
1. Deploy and monitor Railway logs for 5 minutes
2. Send a test message and verify FLOW_METRICS line appears with correct fields
3. Verify session round-trip: load → process → save does not introduce new errors
4. Confirm ORCH DONE still appears, ORCH FATAL = 0
5. Query a test user row: confirm new fields are being saved with correct defaults

**Rollback notes:**
- Rollback requires reverting agents.py and memory_engine.py only
- DB columns remain (they are additive, their presence does not break old code)
- Safe to roll back independently of Phase A

**Recommended commit message:**
```
feat(phase-b): extend load_session/save_session + memory_engine ALLOWED for route state fields
```

---

### Phase C — Payment → Route Activation

**Goal:** When a payment is confirmed via Stripe webhook, automatically assign the correct care_route and care_duration based on the tariff, and set the initial state variables for the route.

**Files affected:**
- agents.py (`on_payment_confirmed()` only)
- main.py (stripe_webhook handler — tariff identification comment/note only)

**What changes:**

In agents.py `on_payment_confirmed()`, after the existing payment_status and route assignments, add route activation logic:

```python
# Route activation based on tariff
if 'Znakomstvo' in tariff or '1113' in tariff:
    session['care_route'] = 'START_SUPPORT'
    session['care_duration'] = '6_weeks'
    session['support_level'] = 'standard'
elif 'Polnoe' in tariff or '4725' in tariff:
    session['care_route'] = 'FULL_PYTHON_METHOD'
    session['care_duration'] = '5_6_months'
    session['support_level'] = 'full'

session['ai_support_level'] = 'active_companion'
session['onboarding_stage'] = 'started'
session['karen_access'] = 'pending'
session['rehab_stage'] = 'pre_start'
```

Note on payment_status alignment: the system currently uses 'paid' as the confirmed payment value. The route architecture doc uses 'confirmed'. Both should be treated as equivalent. No change to existing payment_status values — they remain as-is.

**What must NOT be touched:**
- orchestrator_core.py
- route_resolver.py
- auto_router.py
- state_engine.py
- The existing payment_status assignment logic
- The existing route = 'onboarding' assignment
- send_karen_paid_notification() (Karen notification already working)
- Stripe webhook parsing in main.py (amount-based tariff identification remains)

**Verification steps:**
1. Deploy and monitor Railway logs
2. Simulate or wait for a real payment event
3. Verify in Railway logs: on_payment_confirmed called, no exception
4. Query session for the paying user: confirm care_route, ai_support_level, onboarding_stage set correctly
5. Confirm Karen notification still fires (existing behaviour preserved)
6. Confirm ORCH DONE still appears on next message from paid user

**Rollback notes:**
- Roll back agents.py on_payment_confirmed() to pre-Phase-C version
- No DB schema change in this phase — rollback is code-only

**Recommended commit message:**
```
feat(phase-c): activate care_route and route state on payment confirmation
```

---

### Phase D — Post-Payment Onboarding

**Goal:** Make the AI aware of onboarding_stage during process_message(). When onboarding_stage = 'started', the AI collects initial context (name, primary concern, current condition, analyses available). When collection is complete, transition to onboarding_stage = 'completed', rehab_stage = 'active', karen_access = 'active'.

**Files affected:**
- agents.py (`process_message()` — additive conditional only)

**What changes:**

In agents.py `process_message()`, before the main routing/agent call, add an onboarding check:

```python
# Route-aware onboarding gate (additive — does not replace existing routing)
onboarding_stage = session.get('onboarding_stage', 'not_started')
care_route = session.get('care_route', 'none')

if care_route != 'none' and onboarding_stage == 'started':
    # AI is in onboarding collection mode
    # Mark steps collected, check completion condition
    # When collection complete:
    # session['onboarding_stage'] = 'completed'
    # session['rehab_stage'] = 'active'
    # session['karen_access'] = 'active'
    pass  # full logic defined in implementation
```

The onboarding gate is a pre-check that runs before routing. It does not modify route logic. It does not modify agent selection. It adds a layer of context that the existing agents can use.

**What must NOT be touched:**
- orchestrator_core.py
- route_resolver.py
- auto_router.py
- state_engine.py
- context_package_builder.py
- The existing process_message() routing chain
- Agent prompts (the context is injected via session, not by rewriting prompts)

**Verification steps:**
1. Deploy and monitor Railway logs
2. Send a test message as a paid user with onboarding_stage = 'started'
3. Verify onboarding flow triggers correctly
4. After completing onboarding, verify onboarding_stage = 'completed', rehab_stage = 'active'
5. Verify karen_access = 'active' after onboarding completion
6. Confirm ORCH DONE appears throughout, ORCH FATAL = 0

**Rollback notes:**
- Remove the onboarding gate conditional from process_message()
- No DB schema change in this phase
- Rollback does not affect payment flow or route assignment

**Recommended commit message:**
```
feat(phase-d): add onboarding_stage gate in process_message for route-aware onboarding
```

---

### Phase E — AI Support Level Separation

**Goal:** Make the AI's behaviour explicitly different before and after payment. The context_package_builder.py should expose ai_support_level. The agent_selector.py should use it to adjust prompt context. Unpaid users remain in 'navigation' mode. Paid users operate in 'active_companion' mode.

**Files affected:**
- context_package_builder.py (add ai_support_level to context package output)
- agent_selector.py (read ai_support_level from context package)

**What changes:**

In context_package_builder.py, alongside `_detect_payment_status()`, add:
```python
def _detect_ai_support_level(session: dict) -> str:
    # Reads from session; falls back to payment_status inference
    level = session.get('ai_support_level', '')
    if level in ('navigation', 'active_companion'):
        return level
    payment = _detect_payment_status(session)
    return 'active_companion' if payment == 'paid' else 'navigation'
```

Add `ai_support_level` to the returned context dict.

In agent_selector.py, read `ai_support_level` from context_package (already reads payment_status — this is one additional field). Use it to conditionally extend the system prompt with route context.

**What must NOT be touched:**
- orchestrator_core.py
- route_resolver.py
- auto_router.py
- state_engine.py
- The existing `_detect_payment_status()` function (do not modify, only add alongside)
- Existing agent prompts (extend context only, do not rewrite)
- Shadow mode logic

**Verification steps:**
1. Deploy and monitor Railway logs
2. Send a test message as unpaid user — verify ai_support_level = 'navigation' in context
3. Send a test message as paid user — verify ai_support_level = 'active_companion' in context
4. Confirm agent responses reflect appropriate support level
5. Confirm FLOW_METRICS logging is unchanged
6. Confirm ORCH DONE appears, ORCH FATAL = 0

**Rollback notes:**
- Remove _detect_ai_support_level() from context_package_builder.py
- Remove ai_support_level read from agent_selector.py
- No DB change, no session change — safe isolated rollback

**Recommended commit message:**
```
feat(phase-e): expose ai_support_level in context_package_builder and agent_selector
```

---

### Phase F — Renewal / Expiration Logic

**Goal:** Enable the system to detect when a route is nearing its end and initiate the renewal dialogue. Set care_expires_at when a route activates. Trigger rehab_stage = 'nearing_end' when within 7 days of expiry. Initiate renewal_status flow via proactive_message_dispatcher.py.

**Files affected:**
- agents.py (`on_payment_confirmed()` — add care_started_at, care_expires_at)
- proactive_message_dispatcher.py (add nearing_end check — additive only)

**What changes:**

In agents.py `on_payment_confirmed()`, after Phase C route assignment, add:
```python
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc)
session['care_started_at'] = now.isoformat()

expiry_days = 42 if care_route == 'START_SUPPORT' else 168
session['care_expires_at'] = (now + timedelta(days=expiry_days)).isoformat()
```

In proactive_message_dispatcher.py, add a periodic check (additive, alongside existing logic):
- Query pm_client_profiles WHERE care_expires_at IS NOT NULL AND rehab_stage = 'active'
- For rows where NOW() > care_expires_at - INTERVAL '7 days':
  - Set rehab_stage = 'nearing_end'
  - Set renewal_status = 'initiated' (if 'none')
  - Queue a renewal prompt message

**Important constraint:** Phase F introduces the only change to proactive_message_dispatcher.py. This file is an async component. The change must be strictly additive — a new conditional check appended to an existing periodic loop, not a new loop. If proactive_message_dispatcher.py does not have a suitable existing loop, this phase must be deferred until a safe extension point is identified.

**What must NOT be touched:**
- orchestrator_core.py
- route_resolver.py
- auto_router.py
- state_engine.py
- Any existing dispatcher logic or loops
- async_queue.py
- async_task_worker.py (do not add new job types via this phase)

**Verification steps:**
1. Deploy and monitor Railway logs
2. Verify care_expires_at is set correctly on a new payment (START_SUPPORT = +42 days, FULL = +168 days)
3. Manually set a test user's care_expires_at to NOW() + 3 days and verify nearing_end trigger fires
4. Verify renewal_status transitions from 'none' → 'initiated' correctly
5. Confirm existing dispatcher behaviour is unchanged for non-expiring users
6. Confirm ORCH FATAL = 0 throughout

**Rollback notes:**
- Revert on_payment_confirmed() care_started_at / care_expires_at additions
- Revert proactive_message_dispatcher.py addition
- care_expires_at columns remain in DB (safe — defaults to NULL for existing rows)

**Recommended commit message:**
```
feat(phase-f): add care_expires_at on payment activation and nearing_end renewal trigger
```

---

## 4. Freeze-Sensitive Restrictions

The following restrictions apply to ALL phases and cannot be overridden. They are derived from docs/stabilization_freeze_notice.md and the architectural principle of additive-only implementation.

**No orchestrator rewrite.**
orchestrator_core.py must not be modified in any phase. Route state is injected via session and context_package, not via orchestrator logic changes.

**No route_resolver rewrite.**
route_resolver.py must not be modified. The existing routing rules are not aware of care_route and do not need to be. care_route is a supra-routing variable — it defines the business context of the journey, not the message-by-message routing decisions.

**No auto_router rewrite.**
auto_router.py must not be modified. Auto-routing behaviour must remain stable through all phases.

**No new async loops.**
No new background loops, periodic tasks, or async coroutines may be introduced. Phase F uses an existing dispatcher loop — if no safe extension point exists, Phase F is deferred. Under no circumstances is a new asyncio loop created.

**No broad refactor.**
Each phase modifies a maximum of 2–3 files. No widespread renaming, restructuring, or abstraction changes. The codebase shape must remain recognisable after each phase.

**Additive only.**
Every change adds new code paths, new columns, new conditions. Nothing is removed. Nothing is renamed. Nothing is replaced. Existing behaviour is preserved at every step.

---

## 5. Deployment Strategy

### One Phase = One Commit = One Deploy

Each phase is committed independently. Each commit is deployed independently. No phase is combined with another into a single deploy.

```
Phase A → commit → deploy → verify → STOP
Phase B → commit → deploy → verify → STOP
Phase C → commit → deploy → verify → STOP
Phase D → commit → deploy → verify → STOP
Phase E → commit → deploy → verify → STOP
Phase F → commit → deploy → verify → STOP
```

### Verify Logs After Each Deploy

After every deploy, observe Railway logs for a minimum of 5 minutes before proceeding to the next phase. Confirm:
- ORCH DONE appearing on incoming messages
- ORCH FATAL = 0
- No Python Traceback
- No new WARNING types not seen before the deploy
- FLOW_METRICS line appearing with correct fields

### Stop Immediately on Error

If any of the following appear after a deploy, stop immediately:
- Any line containing ORCH FATAL
- Any Python Traceback
- Any new ORCH error type not present before the deploy
- Railway restart triggered by the new deploy
- /health returning ok: false

In case of stop: do not proceed to the next phase. Assess the error. Apply rollback if the error is confirmed to originate from the phase change.

### No Hotfix Stacking

Do not apply phase changes on top of unresolved errors. If a phase produces an error that requires a hotfix, the hotfix must be deployed and verified before the next phase begins.

---

## 6. Final Success Criteria

The implementation is considered complete and correct when ALL of the following are verifiable in production:

| Criterion | Verification method |
|-----------|---------------------|
| START_SUPPORT correctly assigned after Stripe payment for Tariff Znakomstvo ($1113) | Query pm_sessions.care_route for paying user = 'START_SUPPORT' |
| FULL_PYTHON_METHOD correctly assigned after Stripe payment for Polnoe soprovozhdenie ($4725) | Query pm_sessions.care_route for paying user = 'FULL_PYTHON_METHOD' |
| Paid users get ai_support_level = 'active_companion' | Query pm_sessions.ai_support_level for paid user |
| Unpaid users remain ai_support_level = 'navigation' | Query pm_sessions.ai_support_level for unpaid user |
| Karen access state is tracked (karen_access transitions pending → active) | Observe karen_access in session after onboarding completion |
| onboarding_stage persists across sessions | Load session after restart, verify onboarding_stage retained |
| rehab_stage persists across sessions | Load session after restart, verify rehab_stage retained |
| care_expires_at is set and available for renewal logic | Query pm_client_profiles.care_expires_at for active route user |
| No ORCH FATAL introduced by any phase | Railway logs show 0 ORCH FATAL across all phases |
| Existing pre-payment flow unchanged | Unpaid user messages route correctly with ORCH DONE |

---

## 7. Document Relationships

| Document | Role |
|----------|------|
| docs/route_architecture.md (6a346e6) | System design — defines what the routes ARE |
| docs/migrate_route_state.sql (d8f6d87) | DB spec — defines the SQL to apply in Phase A |
| docs/route_implementation_plan_after_freeze.md (this file) | Execution plan — defines HOW to implement, phase by phase |
| docs/stabilization_freeze_notice.md | Governance — defines what is permitted during freeze |

---

*Document status: ACTIVE PLANNING REFERENCE — implementation blocked until freeze lift.*
*Owner: pythonsmethod | Created: 2026-05-20 | Phase: Pre-implementation*

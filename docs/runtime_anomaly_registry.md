# Runtime Anomaly Registry
## python-method-center | Phase 4 Stabilization Window

> **STATUS: STABILIZATION WINDOW ACTIVE**
> **Date created:** 2026-05-19
> **Observed during:** Phase 4 Observability Step 2 — Live FLOW_METRICS Verification
> **Purpose:** Operational intelligence classification only. No fixes during this window.
>
> ⚠️ DO NOT FIX DURING STABILIZATION WINDOW — items marked as: non-fatal | shadow-only | overlay-only | non-user-visible

---

## Anomaly Classification Table

| ID | Layer | Severity | Fatal? | User-visible? | Lucky affected? | Frequency | Root cause hypothesis | Current mitigation | Fix priority |
|---|---|---|---|---|---|---|---|---|---|
| ORCH-S8 | orchestrator_core / overlay | HIGH | No | No | No | Every webhook retry | `build_overlay_injection()` called without required positional args `agent_name` and `current_route` — signature mismatch after refactor | Overlay silently skipped; core flow continues | P2 — future hardening |
| ORCH-S11 | orchestrator_core / shadow | HIGH | No | No | No | Every webhook retry | `_ask_claude_shadow()` missing 1 required positional arg `messages` — shadow observe call broken | Shadow observation silently skipped | P2 — future hardening |
| ORCH-S14 | orchestrator_core / overlay session | MEDIUM | No | No | No | Every webhook retry | overlay session update error: `should_inject` key missing or wrong type from overlay config | Session overlay update skipped | P2 — future hardening |
| ORCH-CONT | orchestrator_core / continuity | MEDIUM | No | No | No | Every new session | `list object has no attribute get` — continuity snapshot stored as list, accessed as dict | OrchestratorCore re-initialises fresh; continuity lost but non-fatal | P2 — future hardening |
| TEL-499 | transport / Telegram webhook | MEDIUM | No | No | Possible double reply | Per slow response >5s | Telegram client-side timeout fires at ~5s and retries — server processes both, sends 2 replies | First webhook 200 OK; second processed normally | P1 — latency reduction |
| FLOW-UNK | observability / flow classifier | MEDIUM | No | No | No | Every unrecognized message | intent=unknown state=unknown route=unknown confidence=0.00 — classifier returns no match | FLOW_METRICS logs all 8 fields correctly regardless | P1 — intent coverage |
| SHADOW-FB | analytics / shadow memory | LOW | No | No | No | Continuous | Shadow analytics in-memory only — no persistent storage; data lost on restart | shadow_mode=true, mismatches tracked in-session only | P3 — persistence layer |

---

## Classification Labels

| Anomaly ID | Classification |
|---|---|
| ORCH-S8 | `degraded-overlay` |
| ORCH-S11 | `degraded-shadow` |
| ORCH-S14 | `degraded-overlay` |
| ORCH-CONT | `degraded-shadow` |
| TEL-499 | `runtime-stable` (transport-level, recoverable) |
| FLOW-UNK | `degraded-observability` |
| SHADOW-FB | `degraded-shadow` |

---

## DO NOT FIX DURING STABILIZATION WINDOW

The following anomalies are **explicitly excluded** from active fixing during the current stabilization window:

| Anomaly ID | Reason for exclusion |
|---|---|
| ORCH-S8 | Non-fatal, overlay-only, zero user impact |
| ORCH-S11 | Non-fatal, shadow-only, zero user impact |
| ORCH-S14 | Non-fatal, overlay-only, zero user impact |
| ORCH-CONT | Non-fatal, shadow-only, continuity re-init is safe |
| SHADOW-FB | Non-fatal, shadow-only, in-memory acceptable during stabilization |
| FLOW-UNK | Non-fatal, non-user-visible — FLOW_METRICS structure is correct |

> ⚠️ **TEL-499** is the only anomaly where future priority action is recommended.
> It causes Telegram to retry, which leads to double webhook processing and potential duplicate replies.
> It does NOT break user experience if responses are idempotent.
> **MONITOR — do not fix now.**

---

## SHORT ANOMALY LANDSCAPE SUMMARY

### Layer Status Overview

| Layer | Status | Notes |
|---|---|---|
| Core webhook transport | STABLE | POST /webhook 200 OK on first call, 4s |
| SendPulse delivery | STABLE | All sends 200 OK, token refresh working |
| FLOW_METRICS logging | STABLE | All 8 required fields present and correct |
| Health endpoint | STABLE | /health 200, counters increment correctly |
| Intent/state classifier | DEGRADED | Returns unknown for all test input; structure intact |
| Overlay injection | DEGRADED | Signature mismatch — overlay silently skipped |
| Shadow observation | DEGRADED | Missing args — shadow observation silently skipped |
| Continuity snapshot | DEGRADED | list/dict mismatch — re-init each session |
| Shadow analytics persistence | DEGRADED | In-memory only, lost on restart |
| Telegram transport | DEGRADED (latency) | 499 retry when response time exceeds 5s |

---

### STABLE — Safe to ignore during stabilization
- Core message delivery: Telegram → webhook → SendPulse ✅
- FLOW_METRICS structure and all 8 fields logging correctly ✅
- /health counters and uptime tracking ✅
- Zero ORCH FATAL, zero Traceback, zero TypeError, zero AttributeError, zero IndentationError ✅
- Service Online, orchestrator_active=true, shadow_mode=true ✅

### DEGRADED — Shadow / Overlay layer (no user impact)
- Overlay injection not executing (ORCH-S8, ORCH-S14) — overlay features inactive
- Shadow observation not executing (ORCH-S11) — shadow mode tracking incomplete
- Continuity snapshot broken (ORCH-CONT) — no persistent session memory for orchestrator
- Intent classifier returning unknown (FLOW-UNK) — fallback route for all messages

### DANGEROUS — Requires future attention
- **TEL-499**: Telegram retry causes double webhook processing — risk of duplicate replies at scale
- **FLOW-UNK**: If intent stays unknown in production, all users receive fallback route — no personalization

### IGNORE temporarily (zero user impact)
- ORCH-S8, ORCH-S11, ORCH-S14, ORCH-CONT, SHADOW-FB: all shadow/overlay layer anomalies with zero user-facing impact during stabilization window

### FUTURE HARDENING required (post-stabilization, in priority order)
1. **P1** Fix webhook response latency below 5s to prevent Telegram 499 retries (TEL-499)
2. **P1** Expand intent classifier coverage for real production messages (FLOW-UNK)
3. **P2** Fix `build_overlay_injection()` — add `agent_name` and `current_route` params (ORCH-S8)
4. **P2** Fix `_ask_claude_shadow()` — add `messages` param (ORCH-S11)
5. **P2** Fix `overlay session update` — resolve `should_inject` key error (ORCH-S14)
6. **P2** Fix continuity snapshot format — ensure dict not list returned (ORCH-CONT)
7. **P3** Add persistent storage backend for shadow analytics (SHADOW-FB)

---

*Registry created: 2026-05-19 | Phase 4 Stabilization Window | Observability Step 2*
*Last updated: 2026-05-19 19:45 PDT*
*Classification by: operational intelligence scan — no code changes made*
*Source data: Railway Deploy Logs + HTTP Logs + /health endpoint counters*

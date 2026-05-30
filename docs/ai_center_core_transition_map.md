# AI Center Core — Mode Transition Map & Trigger Specification

**Document Type:** Mode Transition & Trigger Specification (AI Center Core)  
**Status:** Accepted — documentation only (no runtime change)  
**Depends on:** docs/ai_center_core_policy.md (CORE-1), docs/ai_center_core_mode_registry.md (CORE-2)  
**References:** docs/ownership_matrix.md, docs/route_architecture.md, docs/agent_role_specification.md

---

## 1. Purpose

This document defines the official transition logic between AI Center Core modes: which mode may
transition to which, the signals that fire each transition, the deterministic priority when
several signals match at once, which engine owns each transition write, fallback behavior, and
conflict resolution.

It is documentation only. No runtime code, no agents, no prompts, and no database are changed in
this phase. The ten modes are internal; the user never sees mode names or switching.

---

## 2. The Ten Modes

Reception, Orientation, Consultation, Trust, Payment, Onboarding, Documents, Companion, Recovery,
Escalation. Definitions live in docs/ai_center_core_mode_registry.md and are not repeated here.

---

## 3. Trigger Types (Requirement 2)

Every transition is fired by exactly one resolved trigger drawn from these categories:

- **Intent triggers** — detected user intent (e.g. faq/system_info, individual consultation,
  purchase intent).
- **Route-state triggers** — current `route_state` / `last_active_route` value (read-only).
- **Payment triggers** — `payment_status` changes (e.g. confirmed).
- **Onboarding triggers** — `onboarding_stage` changes (e.g. completed).
- **Document triggers** — document upload / intake requests.
- **Risk triggers** — `risk_engine` threshold breach or explicit crisis signal.
- **Silence / inactivity triggers** — user inactive beyond a threshold.
- **Staff / operator triggers** — an authorized operator (Anna) action or override.
- **Return-user triggers** — a previously inactive / stuck user returns.

---

## 4. Deterministic Priority Order (Requirement 3)

When more than one trigger matches in a single turn, the Core resolves to the **highest-priority**
trigger using this fixed order. **Escalation / safety always wins.**

1. Risk / escalation trigger (safety) — **always wins**
2. Staff / operator override
3. Payment confirmation
4. Authenticated cabinet / document action
5. Return-user context
6. Explicit user intent
7. Trust / fear signal
8. Route-state continuation
9. Inactivity / recovery
10. Default orientation (fallback)

This order is the single source of truth for conflict resolution. Note that items 5 and 7 act as
**gates** in front of lower-priority targets (Section 7): return-user context is recovered before
an answer is produced, and a trust/fear signal is repaired before a payment action proceeds.

---

## 5. Transition Table (Requirement 1)

| Current Mode | Trigger / Signal | Condition | Next Mode | State Write Owner | Notes |
|---|---|---|---|---|---|
| Reception | basic system question | intent = faq / system_info | Orientation | route_engine | No public agent switch |
| Reception | wants individual consultation | intent = individual | Consultation | route_engine | Surface stays unified |
| Reception | fear / distrust shown | trust_signal = true | Trust | route_engine | Trust repair before action |
| Reception | crisis signal | risk_engine threshold | Escalation | escalation_engine | Escalation always wins |
| Orientation | fear / distrust shown | trust_signal = true | Trust | route_engine | Trust repair before action |
| Orientation | ready to proceed | intent = consultation | Consultation | route_engine | — |
| Orientation | purchase intent | intent = payment | Payment | route_engine | Only if no fear signal |
| Consultation | purchase readiness | intent = payment, trust ok | Payment | route_engine | Trust gate must pass first |
| Consultation | skepticism surfaces | trust_signal = true | Trust | route_engine | Repair before continuing |
| Trust | trust restored | trust_signal cleared | Consultation / Payment | route_engine | Return to prior intent |
| Payment | payment confirmed | payment_status = confirmed | Onboarding | payment owner + route_engine | Payment owner writes status |
| Payment | payment failure | technical failure | Payment (retry) / Orientation | payment owner | Offer alternative, no pressure |
| Onboarding | onboarding complete | onboarding_stage = completed | Companion | approved owner + route_engine | Karen connection bridge (planned) |
| Onboarding | has documents | document intake requested | Documents | document/cabinet owner | Auth required first |
| Documents | upload while not authed | auth = false | Auth/Cabinet gate -> Documents | auth/session owner | No anonymous upload |
| Documents | intake done | package ready | Escalation (handoff prep) | escalation_engine | Context prepared for human |
| Companion | user goes silent | inactivity threshold | Recovery | approved dispatch owner | — |
| Companion | crisis signal | risk_engine threshold | Escalation | escalation_engine | Escalation always wins |
| Recovery | user returns | return_user = true | recover context -> active mode | route_engine | Recover context first |
| Recovery | returning user asks FAQ | intent = faq after pause | Orientation | route_engine | Recovery checks context, then routes |
| Any Mode | risk threshold exceeded | risk_engine threshold | Escalation | escalation_engine | Escalation always wins |
| Any Mode | operator override | staff/operator action | operator-specified mode | escalation_engine / approved owner | Anna control level |
| Any Mode | no trigger matches | default | Orientation | route_engine | Fallback, never dead-end |

---

## 6. Ownership Rules (Requirement 4)

The AI Center Core does **not** directly write route_state, escalation_state, dashboard state,
payment status, document status, or any database table. It reads state and proposes a next mode;
the actual write is performed by the approved owner:

| State / Effect | Approved Owner |
|---|---|
| route_state | `route_engine` |
| escalation_state | `escalation_engine` |
| risk_score / risk threshold | `risk_engine` |
| dashboard state | `dashboard_data` |
| payment status | payment handler / payment owner |
| document / cabinet state | document / cabinet owner |
| auth / session state | auth / session owner |

Per docs/ownership_matrix.md, `route_state` is owned solely by `route_engine` and the conversation
layer is a reader and forbidden writer. Adding the Core as a new writer to any owned state or
table requires an explicit amendment to the ownership matrix and architectural review.

---

## 7. Conflict Resolution (Requirement 5)

When multiple triggers match, resolve using the Section 4 priority order. Canonical cases:

- **Risk trigger + payment intent** -> **Escalation Mode wins** (safety outranks everything).
- **Fear signal + purchase intent** -> **Trust Mode before Payment Mode** (repair trust, then
  return to the payment intent).
- **Document upload + no auth** -> **Auth / cabinet gate before Documents Mode** (no anonymous
  upload; the document is bound to an authenticated user_id).
- **Return user + new question** -> **recover context first (Recovery), then answer** in the
  appropriate mode.
- **FAQ intent + recovery signal** -> **Recovery Mode if the user was previously stuck**; Recovery
  recovers context, then may transition to Orientation for the FAQ answer.

---

## 8. Sarah / Gabriel FAQ Conflict Resolution (Requirement 6)

The agent audit documented a conflict where the `faq` key was entangled between Gabriel and Sarah.
This map resolves it deterministically:

- **FAQ / system questions -> Orientation Mode** (former Gabriel).
- **Return-after-pause -> Recovery Mode** (former Sarah).
- **If both match:** Recovery Mode runs **first** to recover the returning user's context, then
  may transition to Orientation Mode to answer the FAQ. Return-user context (priority 5) outranks
  plain explicit intent (priority 6), so the recovery gate always precedes the FAQ answer.

This removes the ambiguity: the route key no longer maps two modes to the same signal — intent
type plus return-user state determine the order.

---

## 9. Fallback Behavior (Requirement 7)

- If **no trigger matches** -> default to **Orientation Mode**.
- If the **message is unclear** -> ask **one** short clarification question (do not guess a route).
- If the user **appears overwhelmed** -> use **Trust Mode** or **Orientation Mode** depending on
  the signal (fear -> Trust; confusion -> Orientation).
- **Never produce a dead-end answer.** Every response must end with a clear next step.

---

## 10. User Experience (Requirement 8)

- No visible agent switching.
- No named agents.
- No "you are now speaking with X."

The user always experiences a single unified center: **Python Method Center / AI Center**. Modes
and transitions are internal only.

---

## 11. Implementation Readiness (Requirement 9)

**What this document enables.** A deterministic, auditable mapping from signals to modes with a
fixed priority order and explicit write ownership. Together with CORE-1 (policy) and CORE-2
(registry), the Core now has a complete paper specification: identity, modes, and transitions.

**What code phase should come next — CORE-4: Mode Selector Shim.** A **small, read-only** module
that, given the current signals, returns the selected mode name per this transition map. It must:

- be read-only — read state, return a mode decision, write nothing;
- not change any ownership behavior (no writes to route_state, escalation_state, payment, etc.);
- not replace `AgentSelector` yet — run alongside it (e.g. shadow / advisory) for comparison;
- not alter prompts, the database, or backend behavior.

**What must not be touched yet.** `agents.py`, `AgentSelector` (no replacement yet), the route /
escalation / risk engines, `dashboard_data`, payment and document/cabinet owners, prompts, and the
database. CORE-4 is purely a decision function whose output is observed, not yet acted upon.

---

## 12. Non-Goals (This Phase)

- Do not modify code.
- Do not refactor `agents.py`.
- Do not replace `AgentSelector` yet.
- Do not change prompts.
- Do not change the database.
- Do not change backend behavior.

Documentation only. This map establishes the canonical transition logic ahead of any runtime work
and does not itself change runtime behavior.


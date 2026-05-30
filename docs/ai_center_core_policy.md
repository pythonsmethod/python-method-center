# AI Center Core Policy

**Document Type:** AI Interaction Architecture Policy  
**Status:** Accepted — documentation only (no runtime change)  
**Supersedes:** multiple visible named AI agents as separate user-facing entities  
**Related:** docs/web_platform_policy.md, docs/agent_role_specification.md, docs/ownership_matrix.md

---

## 1. Purpose

This document establishes the official AI interaction architecture for Python Method Center.

A final architecture decision has been accepted: Python Method Center will no longer use multiple
visible named AI agents as separate user-facing entities. The future model is **one AI Center Core**
with internal operating modes. Karen remains a separate human expert boundary. Anna remains the
administrative control level.

This decision is documented here **before** any runtime refactoring begins.

---

## 2. Core Decision

The user communicates with **one unified center**: the AI Center / Python Method Center.

The user-facing experience must follow these rules:

- The user should not see multiple named agents.
- No visible agent switching.
- No user-facing agent personas.
- No confusion between "who is speaking."

For the user there is one entity: the Center.

---

## 3. Internal Structure

The AI Center Core operates through **internal modes**. These are internal operating modes,
not separate public personas, and they are never surfaced to the user as distinct identities.

- Reception Mode
- Orientation Mode
- Consultation Mode
- Trust Mode
- Payment Mode
- Onboarding Mode
- Documents Mode
- Companion Mode
- Recovery Mode
- Escalation Mode

The Center may internally change modes, but the surface experience remains unified.

---

## 4. Migration Matrix

The following maps the current named agents to their future internal mode. This mapping is
documentation of intent; no code is changed in this phase.

| Current Agent | Route Key | Future Internal Mode |
|---|---|---|
| Lucky | reception | Reception Mode |
| Gabriel | faq_route | Orientation Mode |
| Hannah | individual | Consultation Mode |
| Sophia | trust_route | Trust Mode |
| Maya | payment_route | Payment Mode |
| Iris | onboarding_route | Onboarding Mode |
| Vera | analysis_route | Documents Mode |
| Nadia | support_route | Companion Mode |
| Sarah | recovery_route | Recovery Mode |
| Karen | escalation_route | Escalation Mode / Human Handoff Boundary |

---

## 5. Karen Boundary

Karen is **not** an AI persona. Karen is a **human expert level**.

- The AI Center Core may prepare, organize, summarize and escalate context to Karen.
- The AI Center Core must **not** pretend to be Karen.
- The AI Center Core must **not** replace Karen.
- Escalation to Karen must remain a controlled handoff path.

Escalation Mode is the user-facing surface of this boundary, but the actual handoff to Karen
remains a separate, governed path. The planned post-onboarding "Karen connection bridge" (a warm,
expected handoff) is distinct from emergency escalation and must not be conflated with it.

---

## 6. Anna Control Level

Anna remains the system control level. Anna must be able to observe:

- user stages
- client status
- stuck users
- document status
- escalation needs
- weak points in routes

The AI Center Core must remain observable and governable. It must never become a closed box
that hides client state from the administrative control level.

---

## 7. State Ownership Rule

The AI Center Core must **not** become an uncontrolled owner of system state.

Route state, escalation state, dashboard state and database ownership rules must remain governed
by existing ownership boundaries (see docs/ownership_matrix.md).

- The AI Center Core **may read** state and **propose** next actions.
- **Writes must go through approved system owners / engines** (for example: route state via the
  route engine, escalation state via the escalation engine, dashboard data via its owner).
- Adding the Core as a new writer to any owned state or table requires an explicit amendment to
  the ownership matrix and architectural review.

---

## 8. User Experience Rule

The user should feel:

> "I am speaking with the Center."

Not:

> "I am being transferred between different bots."

The Center may internally change modes, but the surface experience remains unified and continuous.

---

## 9. Future Implementation Rule

Before refactoring runtime code, the following must be preserved:

1. Route-state ownership.
2. Escalation engine boundaries.
3. Dashboard visibility.
4. Karen as the human expert boundary.
5. Anna as the governance / control level.

The transition itself must:

6. Remove public agent names gradually.
7. Convert personas into internal modes.

---

## 10. Non-Goals (This Phase)

- Do not modify code in this phase.
- Do not remove existing agents in this phase.
- Do not refactor runtime in this phase.
- Do not delete prompts in this phase.

This is documentation only. It establishes future direction and binding constraints for the
AI Center Core migration; it does not itself change any runtime behavior.


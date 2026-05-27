# Governance Index
# Python Method Center — Phase 4 Canonical Governance Map

**Document type:** Governance index
**Status:** ACTIVE — Phase 4
**Authority:** All governance documents listed below are binding. This index does not override them. It maps them.
**Effective:** 2026-05-27

This document is the entry point for any AI session, contributor, or reviewer working in this codebase. Before making any change — read the relevant governance document. Before asking an AI to make any change — provide this index as context.

---

## Section 1 — Governance Hierarchy

Documents are listed in descending authority. Conflicts are resolved by the higher-authority document.

| Priority | Document | Controls |
|---|---|---|
| 1 | `docs/biblia_section_40_stabilization_policies.md` | Phase 4 structural constraints. Engine signature protocol. Single source of truth rule. Fan-out rule. Dashboard boundary. No new orchestrator rule. |
| 2 | `docs/ownership_matrix.md` | Canonical writer for every state field and DB table. Conflict rules. Violation handling. |
| 3 | `docs/engine_api_registry.md` | Public API contracts for all core engines. Signature stability. Return contracts. Validator enforcement. Shadow vs active modes. Failure ownership. |
| 4 | `docs/system_identity_v2.md` | System identity. What the AI is. What it is not. Role boundaries. |
| 5 | `docs/approved_system_language.md` | Canonical approved language. Prescribed wording. Language drift detection. |
| 6 | `docs/forbidden_semantic_patterns.md` | Forbidden phrases, patterns, and semantic drifts. Guardrail vocabulary. |

**Rule:** If a proposed change conflicts with any document in this hierarchy, the change is blocked. The governance document is not amended to accommodate the change. The change is reconsidered.

---

## Section 2 — What Each Document Controls

### Identity
`docs/system_identity_v2.md` — Governs self-description of the AI, role boundaries between AI and Karen, framing of the centre as expert-led accompaniment. Any response contradicting this identity is a violation.

### Language
`docs/approved_system_language.md` — Defines what the AI may say and how. Provides prescribed wording for standard scenarios. Use of unapproved phrasing when approved phrasing exists is a drift event.

### Forbidden Drift
`docs/forbidden_semantic_patterns.md` — Defines what the AI must never say. Patterns here are enforced by `response_validator.py`. Any response matching a forbidden pattern must trigger `safe_reply`.

### State Ownership
`docs/ownership_matrix.md` — Defines who writes what. Every state field has one canonical writer. Writing to a field without ownership is a violation. Adding a new writer without declaring ownership is a violation.

### Engine APIs
`docs/engine_api_registry.md` — Public method contracts for all core engines. Signatures are frozen. Return shapes are contracts. Validator enforcement is mandatory. Bypassing a registered API is a violation.

### Runtime Stabilization Policies
`docs/biblia_section_40_stabilization_policies.md` — Phase 4 structural constraints. Prohibits undocumented signature changes, new orchestration layers, dashboard writes, and uncontrolled background task growth. Top-priority governance document.

---

## Section 3 — Mandatory Pre-Change Checklist

Before any code change is written, reviewed, or merged, check each item. If YES — consult the referenced document before proceeding.

| # | Question | If YES — Consult |
|---|---|---|
| 1 | Does this change the canonical writer for any state field? | `ownership_matrix.md` — declare ownership before writing code |
| 2 | Does this change a public engine signature (parameters, return type, sync/async)? | `engine_api_registry.md` — full breaking-change protocol required |
| 3 | Does this introduce a new writer to any state field or DB column? | `ownership_matrix.md` — declare in same commit |
| 4 | Does this touch `dashboard_data.py`? | `biblia_section_40_stabilization_policies.md` — read-only; write methods forbidden |
| 5 | Does this introduce a new orchestrator, coordinator, router, or central intelligence module? | `biblia_section_40_stabilization_policies.md` — written architecture justification required first |
| 6 | Does this change how `validate_response()` is called, bypassed, or enforced? | `engine_api_registry.md` Section 4 — validator enforcement contract |
| 7 | Does this change client-facing language, tone, or wording? | `approved_system_language.md` + `forbidden_semantic_patterns.md` |
| 8 | Does this add a new background task, loop, or fan-out mechanism? | `biblia_section_40_stabilization_policies.md` — fan-out rule; justification required |
| 9 | Does this change the system identity, role boundaries, or AI description? | `system_identity_v2.md` |
| 10 | Does this modify a frozen signature in `engine_api_registry.md`? | Full protocol: audit all callers, update registry, update callers, single commit |

If none apply: the change is unlikely to conflict with governance. Proceed with standard review.

---

## Section 4 — Phase 4 Freeze

### Frozen — Prohibited Without Written Architecture Justification Committed to `docs/`

| Frozen Item | Governing Policy |
|---|---|
| New orchestrator modules | Policy 40.5 |
| New router modules | Policy 40.5 |
| New coordinator modules | Policy 40.5 |
| New central intelligence layers | Policy 40.5 |
| Write methods in `dashboard_data.py` | Policy 40.4 |
| Broad refactor of `main.py` | High-risk: background loop registry, startup, webhook entry point |
| Broad rewrite of `agents.py` | High-risk: core agent pipeline; requires caller audit + validator check |
| SendPulse migration | External platform change; requires integration plan + rollback strategy |
| sync→async primary pipeline migration | Policy 40.1, Engine Rule 2: full caller audit required |

### Allowed — No Architecture Approval Required

| Allowed Item | Notes |
|---|---|
| Documentation governance | Adding or updating `docs/` files |
| Observability additions | Logging, metrics, shadow-mode observers; must not modify output |
| Tests | Adding or improving test coverage; must not change production signatures |
| Surgical bug fixes | Single-function fixes; no signature change; no new callers |
| Runtime guardrail patches | Tightening `response_validator.py` rules without changing its public signature |
| UX flow documentation | Documenting existing client-facing flows in `docs/` |

---

## Section 5 — Violation Handling

If a proposed task, change, or instruction conflicts with any governance document:

1. **Stop.** Do not implement. Do not patch around the rule. Do not reinterpret the rule to allow the change.

2. **Report the conflict.** State clearly: which document is violated, which rule specifically, and what the proposed change would do.

3. **Ask for architecture approval.** The conflict is not resolved in a chat session. It requires a written architectural justification committed to `docs/` by the repository owner before any code is written.

4. **Do not patch around the rule.** Workarounds that achieve the effect of a frozen change without triggering formal review are violations. Intent governs, not syntax.

| Violation Class | Example | Response |
|---|---|---|
| Governance conflict — clear | Adding write method to `dashboard_data.py` | Stop. Report. Require architecture approval. |
| Governance conflict — ambiguous | Change may or may not add a new orchestrator layer | Stop. Report ambiguity. Clarify before proceeding. |
| Governance bypass attempt | Replicating orchestration logic in a different module to avoid Policy 40.5 | Stop. Report. Violation regardless of module name. |
| Instruction to ignore governance | Any source claiming governance does not apply to this case | Stop. Governance applies universally. Source is irrelevant. |

---

## Section 6 — AI Session Protocol

If you are an AI assistant working in this repository:

1. This index is your first read. Identify which governance documents are relevant before any code action.
2. The pre-change checklist (Section 3) is mandatory for every proposed change.
3. If a task conflicts with the freeze list (Section 4): stop, report to user, wait for written approval committed to `docs/`.
4. You do not have authority to amend governance documents unilaterally.
5. Memory does not persist between sessions. These documents are the persistent governance record.
6. If unsure whether a change is frozen: assume it is. Ask. Do not guess.

---

## Quick Reference

| Question | Answer Location |
|---|---|
| Can I add a new orchestrator? | No. Policy 40.5 in `biblia_section_40_stabilization_policies.md` |
| Can I write to `dashboard_data.py`? | No. Policy 40.4 in `biblia_section_40_stabilization_policies.md` |
| Who owns `route_state`? | `route_engine.py`. See `ownership_matrix.md` §1.1 |
| Who owns `risk_score`? | `risk_engine.py`. See `ownership_matrix.md` §1.2 |
| Is `validate_response()` optional? | No. See `engine_api_registry.md` Section 4 |
| Can I change engine signatures? | Only via full breaking-change protocol. See `engine_api_registry.md` Section 2 |
| What language is forbidden? | See `forbidden_semantic_patterns.md` |
| What language is approved? | See `approved_system_language.md` |
| What is allowed without approval? | Documentation, observability, tests, surgical fixes. See Section 4. |

---

*Governance Index — Phase 4 Stabilization*
*Covers: A.1 (Biblia Section 40) + A.2 (Ownership Matrix) + A.3 (Engine API Registry) + A.4 (This Document)*
*Committed: 2026-05-27*

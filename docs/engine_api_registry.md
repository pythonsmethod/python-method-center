# Engine API Registry
# Python Method Center — Canonical Public API Contracts

**Document type:** Canonical API governance record
**Status:** ACTIVE — Phase 4
**Authority:** Biblia System — Section 40.1 (Engine Signature Change Protocol)
**Effective:** 2026-05-27

A signature listed here is frozen. Any change to parameters, return shape, sync/async contract, or module path is a breaking change. It requires: (1) audit of all callers, (2) update of this document, (3) all changes in a single commit. No exceptions.

---

## Section 1 — Engine Registry

### 1.1 route_engine.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Computes and assigns the active route for a client based on current session state. |
| **Public Methods** | `evaluate_route(contact_id, session, context)` |
| **Input Contract** | `contact_id: str`, `session: dict` (current session state), `context: dict` (assembled context package) |
| **Output Contract** | `dict` with keys: `route: str`, `route_confidence: float`, `route_changed: bool` |
| **Sync/Async** | Sync |
| **Canonical Callers** | `orchestrator_core.py` (Step 2 of handle_message pipeline) |
| **Forbidden Callers** | `dashboard_data.py`, `agents.py`, AI agent prompt chains |
| **Failure Mode** | Returns `{route: "DEFAULT", route_confidence: 0.0, route_changed: False}` on error. Must not raise. |

---

### 1.2 escalation_engine.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Detects, opens, manages, and closes escalation states. Notifies operator channel. |
| **Public Methods** | `EscalationManager.check(interrupt_result, context_package, session, risk_score)`, `EscalationManager.close(contact_id, session)` |
| **Input Contract** | `check`: `interrupt_result: dict`, `context_package: dict`, `session: dict`, `risk_score: float`. `close`: `contact_id: str`, `session: dict` |
| **Output Contract** | `check` returns `dict` with keys: `escalated: bool`, `escalation_type: str`, `escalation_message: str`. `close` returns `None`. |
| **Sync/Async** | Sync (check), Async (notification side-effect) |
| **Canonical Callers** | `orchestrator_core.py` only |
| **Forbidden Callers** | `dashboard_data.py`, `agents.py`, any direct call from background tasks |
| **Failure Mode** | Returns `{escalated: False}` on error. Notification failure must not block pipeline. |

---

### 1.3 risk_engine.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Per-user risk score computation and persistence. |
| **Public Methods** | `RiskPredictor.predict_for_user(user_id)`, `RiskPredictor.get_risk_by_type()`, `RiskPredictor.init(db_pool)` |
| **Input Contract** | `predict_for_user`: `user_id: int`. `get_risk_by_type`: no args. `init`: `db_pool` (optional) |
| **Output Contract** | `predict_for_user` returns `Optional[RiskResult]` (dataclass with `risk_score: float`, `risk_type: str`, `risk_flags: list`). `get_risk_by_type` returns `List[Dict]`. |
| **Sync/Async** | All async |
| **Canonical Callers** | `orchestrator_core.py` (predict_for_user), `dashboard_data.py` (get_risk_by_type — read only), `main.py` (init) |
| **Forbidden Callers** | `agents.py`, `escalation_engine.py` (reads result, does not call directly) |
| **Failure Mode** | `predict_for_user` returns `None` on failure. Caller must handle `None` as neutral risk. |

---

### 1.4 context_engine.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Assembles the canonical context_package for each pipeline step. Single point of context construction. |
| **Public Methods** | `build_context_package(contact_id, session, user_message)` |
| **Input Contract** | `contact_id: str`, `session: dict`, `user_message: str` (default `""`) |
| **Output Contract** | `dict` with required keys: `contact_id`, `user_message`, `route`, `risk_score`, `memory_snapshot`, `active_flags`. Schema must not change without version bump. |
| **Sync/Async** | Sync |
| **Canonical Callers** | `orchestrator_core.py` (Step 1), `agents.py` (read-only consumer) |
| **Forbidden Callers** | `dashboard_data.py`. Any module that modifies the returned dict in-place. |
| **Failure Mode** | Returns minimal safe dict with `{contact_id, user_message, route: "DEFAULT"}`. Must not raise. |

> **Duplication note:** A second implementation `central_ai_core.build_context_package` exists. It is **not canonical**. Do not add a third implementation. Unification is scheduled for a future refactor phase.

---

### 1.5 memory_engine.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Reads and writes all memory layers. Single writer for current_session_history, short_term_memory, active_stage_memory, long_term_timeline. |
| **Public Methods** | `MemoryWriter.write(session, user_message, ai_reply, ...)`, `get_memory_snapshot(contact_id, session)` |
| **Input Contract** | `write`: `session: dict`, `user_message: str`, `ai_reply: str`, optional context fields. `get_memory_snapshot`: `contact_id: str`, `session: dict` |
| **Output Contract** | `write` returns `dict` with keys: `written: bool`, `memory_updated: bool`. `get_memory_snapshot` returns `dict` with memory layer snapshots. |
| **Sync/Async** | Sync (write), Sync (get_memory_snapshot) |
| **Canonical Callers** | `orchestrator_core.py` (write, post-response), `context_engine.py` (get_memory_snapshot) |
| **Forbidden Callers** | `dashboard_data.py` (read-only via separate query), `agents.py`, AI agent prompts |
| **Failure Mode** | `write` returns `{written: False}` on error. Must not raise. Failure must be logged. |

---

### 1.6 dossier_engine.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Receives analysis materials, validates completeness, sets dossier_ready flag, prepares transfer to Karen. |
| **Public Methods** | `accept_material(contact_id, material_type, payload)`, `check_readiness(contact_id)`, `confirm_transfer(contact_id)` |
| **Input Contract** | `accept_material`: `contact_id: str`, `material_type: str`, `payload: dict`. `check_readiness`: `contact_id: str`. `confirm_transfer`: `contact_id: str` |
| **Output Contract** | `accept_material`: `{accepted: bool, missing: list}`. `check_readiness`: `{ready: bool, missing_fields: list}`. `confirm_transfer`: `{transferred: bool}` |
| **Sync/Async** | Sync |
| **Canonical Callers** | `orchestrator_core.py` (check_readiness, confirm_transfer), `agents.py` (accept_material only) |
| **Forbidden Callers** | `dashboard_data.py` (read only via separate query), AI agent prompts directly setting readiness |
| **Failure Mode** | All methods return `{...failed: True}` on error. Must not raise. |

---

### 1.7 response_validator.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Validates AI-generated responses before delivery. Enforces guardrails, schema compliance, safe language rules. |
| **Public Methods** | `validate_response(response, context_package, mode)`, `get_safe_reply(reason)` |
| **Input Contract** | `validate_response`: `response: str`, `context_package: dict`, `mode: str` (ACTIVE or SHADOW). `get_safe_reply`: `reason: str` |
| **Output Contract** | `validate_response` returns `dict` with keys: `valid: bool`, `rewrite_required: bool`, `final_response: str`, `violations: list`, `validator_mode: str`. `get_safe_reply` returns `str`. |
| **Sync/Async** | Sync |
| **Canonical Callers** | `orchestrator_core.py` (mandatory, every response), `agents.py` (must call before returning response) |
| **Forbidden Callers** | None forbidden. But bypassing this call is a violation. |
| **Failure Mode** | On internal error, returns `{valid: False, rewrite_required: True, final_response: get_safe_reply("internal_error")}`. Must not raise. |

---

### 1.8 orchestrator_core.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Central pipeline coordinator. Receives incoming webhook, runs handle_message pipeline, returns final validated response. |
| **Public Methods** | `handle_message(contact_id, user_message, session)` |
| **Input Contract** | `contact_id: str`, `user_message: str`, `session: dict` |
| **Output Contract** | `dict` with keys: `response: str`, `route: str`, `escalated: bool`, `validator_mode: str`, `session_updated: dict`. All keys required. |
| **Sync/Async** | Async |
| **Canonical Callers** | `main.py` (webhook handler only) |
| **Forbidden Callers** | `dashboard_data.py`, `agents.py`, background tasks, any new coordinator module |
| **Failure Mode** | Returns `{response: safe_reply, escalated: False, route: "DEFAULT"}` on any unhandled exception. Must not raise to caller. |

---

### 1.9 dashboard_data.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Read-only data access layer for dashboard endpoints. Aggregates and formats data for display only. |
| **Public Methods** | `get_client_list()`, `get_client_detail(contact_id)`, `get_risk_summary()`, `get_session_metrics()`, `get_health_status()` |
| **Input Contract** | All methods: no write parameters. Read-only filters only (e.g., `contact_id: str` for detail). |
| **Output Contract** | All methods return `list` or `dict` of serialisable data. No stateful objects. No engine references. |
| **Sync/Async** | Async (DB reads) |
| **Canonical Callers** | Dashboard API routes only |
| **Forbidden Callers** | `orchestrator_core.py`, `agents.py`, any engine module. Dashboard is downstream only. |
| **Failure Mode** | Returns empty list/dict with error flag. Must not expose internal state or raise to API layer. |

---

### 1.10 payment_engine.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Processes payment confirmation events. Writes payment_state. Single writer for paid/unpaid status. |
| **Public Methods** | `confirm_payment(contact_id, payment_event)`, `get_payment_status(contact_id)` |
| **Input Contract** | `confirm_payment`: `contact_id: str`, `payment_event: dict` (provider payload). `get_payment_status`: `contact_id: str` |
| **Output Contract** | `confirm_payment`: `{confirmed: bool, payment_state: str}`. `get_payment_status`: `{contact_id, payment_state: str, paid_at: Optional[str]}` |
| **Sync/Async** | Async |
| **Canonical Callers** | Payment webhook handler in `main.py` (confirm_payment), `orchestrator_core.py` (get_payment_status, read only) |
| **Forbidden Callers** | `agents.py`, `dashboard_data.py` (reads from DB directly), AI agent prompts |
| **Failure Mode** | `confirm_payment` returns `{confirmed: False}` on error. Must not modify state on failure. |

---

### 1.11 institutional_memory_intelligence.py

| Property | Value |
|---|---|
| **Primary Responsibility** | Background loop. Computes and persists institutional memory snapshots to pm_institutional_memory. Sole writer. |
| **Public Methods** | `run_institutional_memory_cycle(db_pool)` |
| **Input Contract** | `db_pool`: async DB connection pool |
| **Output Contract** | `None`. Side effect only: INSERT to `pm_institutional_memory`. |
| **Sync/Async** | Async |
| **Canonical Callers** | `main.py` background loop (`_init_institutional_memory_loop`) only |
| **Forbidden Callers** | `orchestrator_core.py`, `agents.py`, `dashboard_data.py`, any webhook handler |
| **Failure Mode** | Logs error and skips cycle. Must not crash the background loop. Retry on next scheduled interval. |

---

## Section 2 — Signature Stability Rules

These rules apply to every method listed in Section 1.

**Rule 1 — Public signature change = breaking change.**
Any modification to parameter names, types, order, or count is a breaking change. It is not a patch. It is not a hotfix. It requires the full signature change protocol.

**Rule 2 — Sync/async mismatch is forbidden.**
If a method is listed as sync, it must remain sync. If listed as async, it must remain async. Converting between sync and async without updating all callers is a critical-risk event.

**Rule 3 — Positional argument drift is forbidden.**
Changing the position of any positional argument is equivalent to a full API removal and replacement. All callers must be identified and updated in the same commit.

**Rule 4 — Silent return-shape changes are forbidden.**
If a method returns a dict, the set of required keys is frozen. Adding a new required key is a breaking change. Removing an existing key is a breaking change. New optional keys may be added without breaking change declaration, but must be documented here.

**Rule 5 — Caller update required in same commit.**
No signature change may be merged without all callers updated in the same commit. Partial updates that leave any caller using the old signature are rejected at review.

---

## Section 3 — Return Contract Rules

**Dict schema stability.** If an engine returns a dict, the schema is a contract. Callers depend on specific keys. Schema changes are breaking changes.

**Required keys.** Every key listed as required in Section 1 must always be present in the returned dict, even on partial failure. Missing required keys are a contract violation.

**Optional keys.** Optional keys may be absent. Callers must use `.get()` for optional keys. Callers must not require optional keys.

**No hidden side effects.** A method that returns a value must not also mutate session state, write to DB, or trigger notifications unless the side effect is explicitly documented in this registry. Undocumented side effects are violations.

**Validator contract expectations.** `validate_response()` must always return a dict with `valid`, `rewrite_required`, `final_response`, and `violations`. Callers must not assume `valid=True` without checking. Callers must use `final_response` as the output, not the raw input response.

---

## Section 4 — Validator Enforcement Contract

### validate_response() contract

`validate_response(response: str, context_package: dict, mode: str) -> dict`

**What is considered unsafe:**
- Response contains forbidden phrases (defined in `forbidden_semantic_patterns.md`)
- Response makes medical claims, dosage statements, or cure promises
- Response discloses composition, protocol, or proprietary method details
- Response escalates pricing, payment, or commercial urgency without approved wording
- Response contradicts the active route or client stage
- Response contains hallucinated facts about Karen, the client, or the system

**When safe_reply must be used:**
- `valid: False` and `rewrite_required: True`
- Any internal exception within `validate_response` itself
- Any case where `final_response` cannot be confidently determined

**Who is obligated to enforce rewrite:**
- `orchestrator_core.py`: mandatory. Every response passes through validator before delivery.
- `agents.py`: mandatory for any agent that produces a final client-facing reply.
- No other module is a primary enforcement point. Enforcement must not be delegated to background tasks or dashboard.

**What constitutes enforcement failure:**
- A client-facing response is delivered without calling `validate_response`
- `validate_response` is called but `final_response` is not used as the output
- `validate_response` is bypassed due to a mode check or feature flag without explicit architectural approval
- `safe_reply` is not used when `rewrite_required: True`

---

## Section 5 — Shadow vs Active Modes

| System | Mode | What It Does | Rewrites Output | Logs Only |
|---|---|---|---|---|
| `response_validator.py` | ACTIVE | Enforces guardrails. Rewrites unsafe responses with `safe_reply`. | Yes | No |
| `response_validator.py` | SHADOW | Observes and logs violations. Does not rewrite output. | No | Yes |
| `risk_engine.py` | ACTIVE | Computes and persists risk_score per user. Used in pipeline decisions. | N/A | No |
| `risk_engine.py` | SHADOW (future) | Runs in parallel with existing risk logic. Output logged but not used. | No | Yes |
| `escalation_engine.py` | ACTIVE | Opens/closes escalations. Notifies operator. Blocks pipeline if critical. | N/A | No |
| `route_engine.py` | ACTIVE | Sets active route. Route decision is binding. | N/A | No |
| `institutional_memory_intelligence.py` | SHADOW-ADJACENT | Background only. No pipeline interaction. Writes to separate table. | No | Yes (via table) |
| `dashboard_data.py` | READ-ONLY | Reads data. Never modifies state. Never interacts with pipeline. | No | No |

**Shadow mode rules:**
- A system in SHADOW mode must not modify any persistent state.
- A system in SHADOW mode must not influence the client-facing response.
- Transitioning from SHADOW to ACTIVE requires explicit architectural decision and update to this document.
- Mode is set at system level, not per-request.

---

## Section 6 — Failure Ownership

| Failure Class | Owner | First Responder | Logged Where | Severity |
|---|---|---|---|---|
| Engine returns `None` or empty when result expected | Caller engine (orchestrator) | `orchestrator_core.py` | Application log (WARNING) | Informational |
| Engine raises unhandled exception | Owning engine module | `orchestrator_core.py` (catches, returns safe_reply) | Application log (ERROR) | Critical |
| `validate_response` returns `valid: False` | `response_validator.py` | `orchestrator_core.py` (applies safe_reply) | Validator violation log | High |
| Validator bypassed (enforcement failure) | `orchestrator_core.py` or `agents.py` | Architecture review required | Runtime anomaly registry | Critical |
| Signature drift detected at runtime | Calling module | Architecture review required | Deploy log + runtime anomaly registry | Critical |
| DB write by forbidden module | Violating module | Architecture review required | Ownership matrix violation log | Critical |
| Background loop crash | Loop owner module | `main.py` (restart logic) | Application log (ERROR) | High |
| Context package missing required key | `context_engine.py` | `orchestrator_core.py` | Application log (ERROR) | Critical |
| Risk score returns None | `risk_engine.py` | `orchestrator_core.py` (uses neutral default) | Application log (WARNING) | Informational |
| Escalation notification fails | `escalation_engine.py` | `escalation_engine.py` (logs, does not block) | Application log (ERROR) | High |

---

## Section 7 — Governance Rules

**Undocumented public API is forbidden.**
Any public method called by 2 or more modules that is not listed in Section 1 is an undocumented API. It must be registered here before or in the same commit as its second caller is added.

**Implicit contracts are forbidden.**
Callers must not depend on undocumented return keys, undocumented side effects, or undocumented failure behaviors. All dependencies must be explicit and registered.

**Orchestration bypass is forbidden.**
No module may call `handle_message` directly except `main.py`. No module may replicate the orchestration pipeline logic outside `orchestrator_core.py`. Pipeline duplication is an architectural violation.

**Direct engine mutation outside ownership is a violation.**
No module may write to a state field owned by another engine. Ownership is defined in `ownership_matrix.md`. Violations require rollback or explicit architectural amendment.

**API drift is a critical-risk event.**
Any divergence between the signature listed here and the actual runtime signature is a critical-risk event. It must be detected at code review, not at runtime. Drift that reaches production requires a post-mortem entry in `runtime_anomaly_registry.md`.

---

## Frozen Signatures (Change History)

| Date | Signature | Change Type | Reason |
|---|---|---|---|
| 2026-05-17 | `state_engine.analyze(contact_id, user_message, session, context)` | Fixed: was `analyze(message_text, session)` | Phase 4 Step 11: 2-arg call caused [ORCH FATAL] on every webhook. Commit 68cfa8d. |

## Duplication Registry

| Canonical | Duplicate | Risk | Resolution |
|---|---|---|---|
| `context_engine.py.build_context_package` | `central_ai_core.build_context_package` | HIGH: divergence produces silent context errors | Unify to single import in future phase. Do not add a third implementation. |

---

*Engine API Registry — Phase 4 Stabilization*
*Supersedes: Engine API Registry (2026-05-17)*
*Committed: 2026-05-27*

# Production Behavior Patterns
## python-method-center | Phase 4 Stabilization Window

> **STATUS: OBSERVATION-ONLY DOCUMENTATION**
> **Date created:** 2026-05-19
> **Data source:** Live production — Railway Deploy Logs, HTTP Logs, /health endpoint
> **Webhooks observed at time of writing:** 2 (minimal baseline)
> **Purpose:** Begin accumulating real production behavioral memory. No analysis, no scoring, no routing changes.
>
> ⚠️ THIS IS NOT AN ANALYTICS ENGINE. DO NOT USE FOR ROUTING OR MODEL TUNING.

---

## OBSERVATION BASELINE STATUS

| Metric | Value at baseline | Notes |
|---|---|---|
| Total webhooks observed | 2 | Minimal — patterns not yet statistically significant |
| Unique users observed | 1 | Single tester (user=69ec6439ef7b3464570126cd) |
| Time window | 2026-05-19 19:39 PDT | Single session |
| Messages with known intent | 0 | All classified as unknown |
| Messages with known state | 0 | All classified as unknown |
| Average latency observed | 4921ms | Mean of 3743ms + 6100ms |
| Telegram retries observed | 1 | Second webhook was a retry (499) |

---

## SECTION 1 — User Entry Patterns

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| UEP-001 | First message triggers full auth + SendPulse token refresh cycle | 1/1 sessions | +300-500ms overhead | Yes | No — expected | oauth/access_token called before first telegram/contacts/send |
| UEP-002 | Single user session observed — no multi-user concurrency data yet | 1 user | Unknown | Unknown | Yes — need 10+ users | Cannot assess concurrency behavior at this stage |
| UEP-003 | User sends message without prior context (cold start) | 1/1 sessions | OrchestratorCore re-init on every request | Partially | Yes — continuity fix needed | Linked to ORCH-CONT anomaly |

---

## SECTION 2 — Common First Intents

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| CFI-001 | First observed intent: unknown | 2/2 webhooks | Fallback route activated | No | Yes — P1 | Classifier not matching test message to any known intent |
| CFI-002 | No greeting/onboarding intent pattern observed yet | 0/2 | Unknown | Unknown | Yes | Need 50+ real users to establish common first-message patterns |
| CFI-003 | confidence=0.00 on all observed messages | 2/2 | Max uncertainty — route by default | No | Yes — P1 | Classifier returning zero confidence universally |

---

## SECTION 3 — Latency Patterns

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| LAT-001 | First webhook latency: 3743ms | 1 observation | Within 5s Telegram threshold | Yes | Monitor | Borderline — 1257ms margin before Telegram retry fires |
| LAT-002 | Retry webhook latency: 6100ms | 1 observation | Exceeds 5s — caused 499 | No | Yes — P1 | Second processing cycle is slower; likely includes full re-init |
| LAT-003 | SendPulse token refresh adds ~300ms at session start | 1 observation | Acceptable | Yes | No — expected behavior | Refresh fires once per session (ttl=3600s buffer=60s) |
| LAT-004 | Mean latency 4921ms across 2 observations | 2 observations | Dangerously close to 5s Telegram timeout | No | Yes — P1 | Requires latency reduction before scaling to real users |

---

## SECTION 4 — Escalation Triggers

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| ESC-001 | escalated=False on all observed messages | 2/2 | No escalation occurring | Yes | Monitor | Expected for test messages; watch for real user escalation triggers |
| ESC-002 | No escalation pathway exercised yet | 0/2 | Unknown escalation behavior | Unknown | Yes — need real user data | Cannot validate escalation routing without real escalation events |

---

## SECTION 5 — Retry Patterns

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| RET-001 | Telegram auto-retry after 5s timeout — HTTP 499 | 1/1 slow responses | Double processing, 2x SendPulse delivery | No | Yes — P1 | Both webhooks fully processed; user may receive duplicate reply |
| RET-002 | Server does not deduplicate retried webhooks | 1 observation | Potential duplicate replies at scale | No | Yes — P1 | No idempotency key check observed in logs |
| RET-003 | Second processing cycle produces identical FLOW_METRICS fields | 2/2 | Consistent behavior under retry | Yes | Monitor | Both entries: same user, same intent, same route, different latency |

---

## SECTION 6 — Unknown Intent Cases

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| UNK-001 | 100% of observed messages classified as intent=unknown | 2/2 (100%) | Full fallback routing | No | Yes — P1 | Critical coverage gap — need real message samples to tune classifier |
| UNK-002 | state=unknown on all observed messages | 2/2 (100%) | No state machine transitions observed | No | Yes — P1 | State tracking not activating for any observed input |
| UNK-003 | route=unknown on all observed messages | 2/2 (100%) | No named route selected | No | Yes — P1 | Routing logic not producing named routes |
| UNK-004 | shadow_match=False on all observed messages | 2/2 (100%) | Shadow mode not confirming any route | No | Monitor | May be result of shadow observe being broken (ORCH-S11) |

---

## SECTION 7 — Route Confidence Distribution

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| RCD-001 | confidence=0.00 observed on 100% of messages | 2/2 | Zero confidence — maximum uncertainty | No | Yes — P1 | No evidence of classifier activating at all |
| RCD-002 | No confidence distribution data available yet | N/A | Cannot establish baseline distribution | Unknown | Yes — need 100+ webhooks | Meaningful distribution requires statistically significant sample |
| RCD-003 | No high-confidence routes observed | 0/2 | System operating entirely on fallback | No | Yes | Need at least 10 known-intent messages to calibrate |

---

## SECTION 8 — Silence Periods

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| SIL-001 | Long silence between deployment (uptime=30401s) and first test message | 1 observation | No keepalive issues observed; service remained Online | Yes | Monitor | Uptime ~8.4 hours before first webhook — Railway did not sleep the service |
| SIL-002 | No periodic activity (cron, health ping) observed between silences | Continuous | META_CONT and RUNTIME_METRICS fire on schedule regardless | Yes | No — expected | Background tasks active independently of user messages |
| SIL-003 | Service behavior after silence: normal — no cold-start delay | 1 observation | First webhook processed normally | Yes | Monitor | Watch for latency spikes after extended silence periods |

---

## SECTION 9 — Message Burst Behavior

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| BUR-001 | No burst scenario observed yet | 0 observations | Unknown | Unknown | Yes — need stress test | Cannot assess burst handling with single-message test |
| BUR-002 | Telegram retry creates pseudo-burst of 2 sequential webhooks 16s apart | 1 observation | Both processed sequentially, no queue overflow | Yes | Monitor | Retry interval ~16s (19:39:38 → 19:39:54) |
| BUR-003 | No concurrent webhook processing observed | 0 observations | Unknown concurrency behavior | Unknown | Yes | Need multi-user test to validate async_queue behavior |

---

## SECTION 10 — Long-Message Behavior

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| LMB-001 | No long messages tested yet | 0 observations | Unknown | Unknown | Yes | Need messages >500 chars, >1000 chars to observe behavior |
| LMB-002 | No token limit impact observed | 0 observations | Unknown | Unknown | Yes | Need to confirm Claude/GPT token handling for long inputs |
| LMB-003 | No truncation or splitting behavior observed | 0 observations | Unknown | Unknown | Yes | Cannot validate long-message routing without test data |

---

## SECTION 11 — Multilingual Behavior

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| MLG-001 | No multilingual messages tested yet | 0 observations | Unknown | Unknown | Yes | System designed for Russian-speaking users — no cross-language tests done |
| MLG-002 | No language detection in FLOW_METRICS fields observed | N/A | Language not tracked in current log schema | Unknown | Yes — future field | Consider adding lang= field to FLOW_METRICS in future hardening |
| MLG-003 | No emoji or special character handling tested | 0 observations | Unknown | Unknown | Yes | Emoji-only messages may cause intent=unknown regardless of classifier |

---

## SECTION 12 — Suspicious Behavior & Overload Indicators

| Pattern ID | Description | Frequency | Impact | Stable? | Needs future work? | Notes |
|---|---|---|---|---|---|---|
| SUS-001 | Telegram 499 retry with full reprocessing — no deduplication | 1/1 slow webhooks | Potential duplicate user replies at scale | No | Yes — P1 | Repeated retries from same user = duplicate message delivery |
| SUS-002 | No rate limiting observed in HTTP Logs | N/A | Unknown — may be unprotected | Unknown | Yes | Need to confirm webhook rate limiting exists before real user load |
| SUS-003 | No authentication/signature verification logged for incoming webhooks | N/A | Potential open webhook endpoint | Unknown | Yes | Telegram webhook secret validation not visible in current log output |
| SUS-004 | OrchestratorCore re-initialises on every request (no continuity) | 2/2 | Stateless behavior — no user memory | No | Yes — P2 | Each message treated as first contact; linked to ORCH-CONT |
| SUS-005 | Repeated ORCH errors (S8, S11, S14) on every retry webhook — not on first | Pattern emerging | Error cascade on retry cycle | No | Yes — P2 | First webhook: clean ORCH DONE. Retry webhook: multiple ORCH errors |
| OVL-001 | No overload indicators observed at current scale (2 webhooks, 1 user) | N/A | Healthy at micro-scale | Yes | Monitor — scale test needed | No queue buildup, no timeout cascade, no memory pressure visible |
| OVL-002 | bg_tasks_created=0 throughout session | Continuous | Background task queue unused | Unknown | Monitor | May indicate bg task system inactive or tasks not being dispatched |

---

## INITIAL BEHAVIOR BASELINE SUMMARY

### What is already visible (2 webhooks, 1 user)

- Core delivery pipeline is stable: message arrives, SendPulse fires, user receives reply
- FLOW_METRICS logs correctly on every webhook — structure confirmed
- Latency is borderline: mean 4921ms, dangerously close to Telegram's 5s retry threshold
- Telegram retry behavior is confirmed: slow response triggers 499 + full reprocessing
- 100% unknown intent/state/route at current sample — classifier not activating
- Session is stateless: no continuity between messages, OrchestratorCore re-inits each time
- Shadow mode active but shadow observation broken (ORCH-S11) — no shadow data accumulating
- Service remains stable across retry cycle — no crash, no FATAL, no Traceback

### What is not yet sufficient (need more data)

- Intent distribution: need 50+ real user messages to identify common first intents
- Route confidence baseline: need 100+ webhooks to see confidence distribution
- Concurrency behavior: completely unknown — no multi-user test
- Escalation patterns: no escalation events observed — trigger conditions unknown
- Burst behavior: untested — async_queue validation pending
- Long-message handling: untested — token limits and truncation unknown
- Multilingual handling: untested — language detection absent from logs
- Silence/cold-start latency: observed only once — not enough for pattern
- Webhook authentication: not visible in logs — security posture unclear

### Patterns that become valuable after 100+ webhooks

- True intent frequency distribution (which routes dominate)
- Latency percentiles (p50, p90, p99) — real vs measured
- Unknown intent rate (should decrease as classifier improves)
- Retry frequency (% of webhooks that are Telegram retries)
- Unique user count and session length distribution
- Time-of-day patterns — when users are most active
- Escalation rate — what % of messages reach escalation triggers
- Shadow match rate — once ORCH-S11 is fixed

### Patterns that may become operational risks later

- **Latency drift**: if mean latency approaches 5s, retry rate will spike — cascade risk
- **Stateless sessions**: users will not receive personalized responses until ORCH-CONT is fixed
- **Unknown intent at scale**: if 100% unknown persists with real users, all receive fallback — no product value
- **Retry deduplication absence**: at higher message volume, duplicate replies become user-visible
- **No webhook auth visible**: open webhook may attract spam or bot traffic
- **Shadow observation broken**: shadow analytics accumulating no data — cannot validate orchestrator behavior without ORCH-S11 fix

---

*Patterns file created: 2026-05-19 | Phase 4 Stabilization Window*
*Observation window: 2026-05-19 19:39 PDT | 2 webhooks | 1 user | 1 session*
*Last updated: 2026-05-19 19:55 PDT*
*Method: observation-only — no code changes, no analysis engine, no scoring*
*Next update: when total_webhooks_processed >= 20*

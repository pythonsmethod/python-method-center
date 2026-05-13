-- =============================================================================
-- PHASE 3.1 — Persistent Memory & Infrastructure Core
-- Schema: schema_v3.sql
-- Python Method Digital Rehabilitation Center
-- AI Operating System — PostgreSQL Foundation
--
-- Tables:
--   pm_client_profiles        — unified client master record
--   pm_memory_timeline        — every meaningful event, immutable append-only
--   pm_memory_short_term      — rolling 48h working memory per client
--   pm_memory_active_stage    — current stage context (onboarding/analysis/support)
--   pm_memory_compressed      — long-term compressed memory summaries
--   pm_memory_vectors         — semantic vector recall storage
--   pm_orchestration_events   — every orchestration pipeline execution
--   pm_event_bus              — async publish/subscribe events
--   pm_queue_jobs             — async job queue
--   pm_risk_predictions       — ML risk trajectory predictions
--   pm_recovery_plans         — automated recovery workflows
--   pm_runtime_health         — runtime supervisor metrics
-- =============================================================================

-- ---------------------------------------------------------------------------
-- EXTENSIONS
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for fuzzy text search
-- CREATE EXTENSION IF NOT EXISTS "vector"; -- pgvector, enable if available

-- ---------------------------------------------------------------------------
-- ENUM TYPES
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE memory_tier AS ENUM (
        'short_term', 'active_stage', 'long_term', 'semantic'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE event_type AS ENUM (
        'message_in', 'message_out', 'route_switch', 'agent_switch',
        'overlay_activated', 'escalation_triggered', 'escalation_resolved',
        'payment_initiated', 'payment_completed', 'onboarding_started',
        'onboarding_completed', 'analysis_uploaded', 'analysis_processed',
        'risk_spike', 'risk_resolved', 'memory_compressed', 'session_started',
        'session_ended', 'recovery_triggered', 'recovery_completed',
        'interrupt_detected', 'queue_job_created', 'queue_job_completed',
        'queue_job_failed', 'system_alert', 'human_took_over', 'human_released'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE job_status AS ENUM (
        'pending', 'running', 'completed', 'failed', 'retrying', 'cancelled'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE risk_level AS ENUM (
        'none', 'low', 'medium', 'high', 'critical'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE recovery_status AS ENUM (
        'pending', 'in_progress', 'completed', 'failed', 'skipped'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
-- pm_client_profiles — unified client master record
-- Single source of truth for all client data across sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_client_profiles (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 BIGINT UNIQUE NOT NULL,          -- Telegram user_id
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Identity
    display_name            TEXT,
    telegram_username       TEXT,
    phone                   TEXT,
    email                   TEXT,

    -- Medical profile
    primary_disease         TEXT,
    secondary_conditions    TEXT[],
    current_medications     TEXT[],
    treatment_stage         TEXT,                            -- diagnosis|treatment|recovery|prevention
    medical_notes           TEXT,

    -- Commercial profile
    payment_status          TEXT NOT NULL DEFAULT 'new',     -- new|pending|paid|refunded
    active_tariff           TEXT,
    payment_date            TIMESTAMPTZ,
    payment_amount_usd      NUMERIC(10,2),
    onboarding_completed    BOOLEAN NOT NULL DEFAULT FALSE,
    onboarding_completed_at TIMESTAMPTZ,

    -- Relationship
    total_sessions          INTEGER NOT NULL DEFAULT 0,
    total_messages          INTEGER NOT NULL DEFAULT 0,
    first_contact_at        TIMESTAMPTZ,
    last_contact_at         TIMESTAMPTZ,
    last_active_route       TEXT DEFAULT 'reception',
    last_active_agent       TEXT DEFAULT 'Lucky',

    -- Risk profile
    lifetime_max_risk       NUMERIC(4,3) DEFAULT 0.0,
    current_risk_level      risk_level NOT NULL DEFAULT 'none',
    risk_spike_count        INTEGER NOT NULL DEFAULT 0,
    escalation_count        INTEGER NOT NULL DEFAULT 0,

    -- Memory meta
    memory_compression_due  TIMESTAMPTZ,                    -- when next compression runs
    last_compression_at     TIMESTAMPTZ,
    memory_version          INTEGER NOT NULL DEFAULT 1,

    -- Flags
    is_vip                  BOOLEAN NOT NULL DEFAULT FALSE,
    requires_human          BOOLEAN NOT NULL DEFAULT FALSE,
    human_assigned_to       TEXT,                           -- staff username
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    tags                    TEXT[] DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_client_profiles_user_id
    ON pm_client_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_client_profiles_payment
    ON pm_client_profiles(payment_status);
CREATE INDEX IF NOT EXISTS idx_client_profiles_risk
    ON pm_client_profiles(current_risk_level);
CREATE INDEX IF NOT EXISTS idx_client_profiles_last_contact
    ON pm_client_profiles(last_contact_at DESC);

-- ---------------------------------------------------------------------------
-- pm_memory_timeline — immutable append-only event log
-- Every meaningful moment in a client's journey is recorded here.
-- Timeline is NEVER updated — only new rows appended.
-- This is the permanent record of all AI decisions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_memory_timeline (
    id                  BIGSERIAL PRIMARY KEY,
    event_id            UUID NOT NULL DEFAULT uuid_generate_v4(),
    user_id             BIGINT NOT NULL,
    ts                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id          TEXT,                               -- orchestration session ref

    -- Event classification
    event_type          event_type NOT NULL,
    event_subtype       TEXT,                               -- free-form sub-classification
    priority            INTEGER NOT NULL DEFAULT 0,         -- 0=low 1=medium 2=high 3=critical

    -- Content
    summary             TEXT NOT NULL,                      -- human-readable 1-line summary
    details             JSONB DEFAULT '{}',                 -- structured event data
    user_message        TEXT,                               -- original user message (if applicable)
    ai_response         TEXT,                               -- AI response (if applicable)

    -- Orchestration context
    route               TEXT,
    agent               TEXT,
    intent              TEXT,
    user_state          TEXT,
    risk_score          NUMERIC(4,3),
    overlay_type        TEXT,

    -- Memory tier association
    memory_tier         memory_tier NOT NULL DEFAULT 'short_term',
    is_compressed       BOOLEAN NOT NULL DEFAULT FALSE,
    compressed_into_id  BIGINT,                             -- FK to pm_memory_compressed

    -- Search
    search_vector       TSVECTOR                            -- full-text search
);

CREATE INDEX IF NOT EXISTS idx_timeline_user_ts
    ON pm_memory_timeline(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_timeline_event_type
    ON pm_memory_timeline(event_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_timeline_priority
    ON pm_memory_timeline(priority DESC, ts DESC);
CREATE INDEX IF NOT EXISTS idx_timeline_risk
    ON pm_memory_timeline(risk_score DESC NULLS LAST, ts DESC);
CREATE INDEX IF NOT EXISTS idx_timeline_session
    ON pm_memory_timeline(session_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_timeline_search
    ON pm_memory_timeline USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_timeline_not_compressed
    ON pm_memory_timeline(user_id, ts DESC)
    WHERE is_compressed = FALSE;

-- Full-text search update trigger
CREATE OR REPLACE FUNCTION pm_timeline_search_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('russian',
        COALESCE(NEW.summary, '') || ' ' ||
        COALESCE(NEW.user_message, '') || ' ' ||
        COALESCE(NEW.ai_response, '') || ' ' ||
        COALESCE(NEW.intent, '') || ' ' ||
        COALESCE(NEW.route, '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pm_timeline_search_trigger ON pm_memory_timeline;
CREATE TRIGGER pm_timeline_search_trigger
    BEFORE INSERT OR UPDATE ON pm_memory_timeline
    FOR EACH ROW EXECUTE FUNCTION pm_timeline_search_update();

-- ---------------------------------------------------------------------------
-- pm_memory_short_term — rolling 48h working memory
-- Fast-access in-session context. Auto-expires after 48h.
-- Replaces raw history for cross-session access.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_memory_short_term (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '48 hours'),

    -- Window
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ,

    -- Content
    message_count   INTEGER NOT NULL DEFAULT 0,
    intent_summary  JSONB DEFAULT '{}',                     -- {intent: count}
    state_summary   JSONB DEFAULT '{}',                     -- {state: count}
    peak_risk       NUMERIC(4,3) DEFAULT 0.0,
    routes_visited  TEXT[] DEFAULT '{}',
    agents_active   TEXT[] DEFAULT '{}',
    key_topics      TEXT[] DEFAULT '{}',
    emotional_arc   TEXT[],                                 -- sequence of emotional states
    unresolved      JSONB DEFAULT '[]',                     -- unresolved questions/concerns

    -- Quick context for agent prompts
    context_snippet TEXT,                                   -- 3-5 sentence summary for injection
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_stm_user_current
    ON pm_memory_short_term(user_id, is_current)
    WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_stm_expires
    ON pm_memory_short_term(expires_at);

-- ---------------------------------------------------------------------------
-- pm_memory_active_stage — current stage context
-- Tracks the client's current programme stage in detail.
-- Updated on every stage transition.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_memory_active_stage (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL,
    stage_id            UUID NOT NULL DEFAULT uuid_generate_v4(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Stage definition
    stage_name          TEXT NOT NULL,                      -- onboarding|analysis|support|recovery
    stage_started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stage_completed_at  TIMESTAMPTZ,
    stage_status        TEXT NOT NULL DEFAULT 'active',     -- active|completed|stalled|abandoned

    -- Progress
    progress_pct        INTEGER NOT NULL DEFAULT 0,         -- 0-100
    steps_completed     TEXT[] DEFAULT '{}',
    steps_remaining     TEXT[] DEFAULT '{}',
    blockers            TEXT[] DEFAULT '{}',

    -- Stage-specific data
    stage_data          JSONB DEFAULT '{}',                 -- stage-specific structured data
    goals               TEXT[] DEFAULT '{}',
    achievements        TEXT[] DEFAULT '{}',
    next_action         TEXT,
    next_action_due     TIMESTAMPTZ,

    -- Emotional context
    entry_risk          NUMERIC(4,3),
    current_risk        NUMERIC(4,3),
    emotional_baseline  TEXT,
    emotional_current   TEXT,

    is_current          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_stage_user_current
    ON pm_memory_active_stage(user_id)
    WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_active_stage_user
    ON pm_memory_active_stage(user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- pm_memory_compressed — long-term compressed memory
-- Periodic summaries replacing detailed short-term records.
-- Contains the essential narrative of the client's journey.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_memory_compressed (
    id                  BIGSERIAL PRIMARY KEY,
    compression_id      UUID NOT NULL DEFAULT uuid_generate_v4(),
    user_id             BIGINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Compression window
    covers_from         TIMESTAMPTZ NOT NULL,
    covers_to           TIMESTAMPTZ NOT NULL,
    timeline_ids        BIGINT[] DEFAULT '{}',              -- IDs of compressed timeline events
    event_count         INTEGER NOT NULL DEFAULT 0,

    -- Compressed content
    narrative_summary   TEXT NOT NULL,                      -- 300-500 word narrative
    key_facts           JSONB DEFAULT '{}',                 -- extracted structured facts
    emotional_journey   TEXT,                               -- emotional arc description
    risk_trajectory     JSONB DEFAULT '{}',                 -- {min, max, avg, spikes: []}
    route_history       TEXT[] DEFAULT '{}',
    agent_interactions  JSONB DEFAULT '{}',                 -- {agent: count}
    topics_covered      TEXT[] DEFAULT '{}',
    unresolved_issues   TEXT[] DEFAULT '{}',
    breakthroughs       TEXT[] DEFAULT '{}',

    -- Compression meta
    compression_method  TEXT DEFAULT 'gpt_summary',        -- gpt_summary|rule_based|hybrid
    compression_quality NUMERIC(3,2),                      -- 0.0-1.0 quality score
    tokens_original     INTEGER,
    tokens_compressed   INTEGER,
    compression_ratio   NUMERIC(5,2)                        -- original/compressed
);

CREATE INDEX IF NOT EXISTS idx_compressed_user
    ON pm_memory_compressed(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_compressed_window
    ON pm_memory_compressed(user_id, covers_from, covers_to);

-- ---------------------------------------------------------------------------
-- pm_memory_vectors — semantic vector recall
-- Stores embeddings for semantic similarity search.
-- Enables "remember when the client mentioned X" queries.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_memory_vectors (
    id              BIGSERIAL PRIMARY KEY,
    vector_id       UUID NOT NULL DEFAULT uuid_generate_v4(),
    user_id         BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Source reference
    source_type     TEXT NOT NULL,                          -- timeline|compressed|stage|message
    source_id       BIGINT,                                 -- FK to source table
    timeline_event_id BIGINT,

    -- Content
    content_text    TEXT NOT NULL,                          -- text that was embedded
    content_type    TEXT NOT NULL,                          -- user_message|ai_response|summary|fact

    -- Vector (stored as JSONB array when pgvector not available)
    embedding       JSONB,                                  -- float[] as JSON
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    embedding_dims  INTEGER DEFAULT 1536,

    -- Metadata for retrieval
    intent          TEXT,
    topics          TEXT[] DEFAULT '{}',
    emotional_tone  TEXT,
    risk_score      NUMERIC(4,3),
    importance      NUMERIC(3,2) DEFAULT 0.5,               -- 0.0-1.0

    -- Search
    search_text     TSVECTOR
);

CREATE INDEX IF NOT EXISTS idx_vectors_user
    ON pm_memory_vectors(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vectors_content_type
    ON pm_memory_vectors(user_id, content_type);
CREATE INDEX IF NOT EXISTS idx_vectors_importance
    ON pm_memory_vectors(user_id, importance DESC);
CREATE INDEX IF NOT EXISTS idx_vectors_search
    ON pm_memory_vectors USING GIN(search_text);

-- ---------------------------------------------------------------------------
-- pm_orchestration_events — every pipeline execution
-- One row per process_message() call.
-- Foundation for orchestration analytics.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_orchestration_events (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL DEFAULT uuid_generate_v4(),
    user_id         BIGINT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id      TEXT,

    -- Pipeline state
    route           TEXT,
    agent           TEXT,
    intent          TEXT,
    user_state      TEXT,
    risk_score      NUMERIC(4,3),
    overlay_type    TEXT,
    interrupt_type  TEXT,
    interrupt_priority INTEGER DEFAULT 0,

    -- Decisions
    escalated           BOOLEAN DEFAULT FALSE,
    route_switched      BOOLEAN DEFAULT FALSE,
    route_switch_from   TEXT,
    route_switch_to     TEXT,
    route_switch_reason TEXT,
    route_locked        BOOLEAN DEFAULT FALSE,
    validation_ok       BOOLEAN DEFAULT TRUE,
    validation_issues   TEXT[] DEFAULT '{}',

    -- Performance
    processing_ms       INTEGER,
    steps_completed     TEXT[] DEFAULT '{}',
    steps_failed        TEXT[] DEFAULT '{}',

    -- Content preview
    msg_preview         TEXT,                               -- first 200 chars of user message
    reply_preview       TEXT,                               -- first 200 chars of AI reply

    -- Memory linkage
    timeline_event_id   BIGINT                             -- FK to pm_memory_timeline
);

CREATE INDEX IF NOT EXISTS idx_orch_events_user_ts
    ON pm_orchestration_events(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_orch_events_escalated
    ON pm_orchestration_events(escalated, ts DESC)
    WHERE escalated = TRUE;
CREATE INDEX IF NOT EXISTS idx_orch_events_route
    ON pm_orchestration_events(route, ts DESC);
CREATE INDEX IF NOT EXISTS idx_orch_events_risk
    ON pm_orchestration_events(risk_score DESC NULLS LAST, ts DESC);
CREATE INDEX IF NOT EXISTS idx_orch_events_perf
    ON pm_orchestration_events(processing_ms DESC NULLS LAST);

-- ---------------------------------------------------------------------------
-- pm_event_bus — async publish/subscribe infrastructure
-- Decouples producers from consumers.
-- Events published here trigger async workers.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_event_bus (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL DEFAULT uuid_generate_v4(),
    published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),

    -- Routing
    topic           TEXT NOT NULL,                          -- e.g. 'memory.compress', 'risk.alert'
    routing_key     TEXT,                                   -- optional sub-routing
    partition_key   TEXT,                                   -- for ordered processing (user_id)

    -- Payload
    payload         JSONB NOT NULL DEFAULT '{}',
    payload_schema  TEXT,                                   -- schema version for validation

    -- Publisher
    publisher       TEXT NOT NULL DEFAULT 'orchestrator',
    publisher_id    TEXT,

    -- Delivery tracking
    delivered_count INTEGER NOT NULL DEFAULT 0,
    max_deliveries  INTEGER DEFAULT 1,
    last_delivered  TIMESTAMPTZ,
    is_consumed     BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at     TIMESTAMPTZ,
    consumed_by     TEXT,

    -- Error handling
    failed_count    INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    dead_lettered   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_event_bus_topic
    ON pm_event_bus(topic, is_consumed, published_at);
CREATE INDEX IF NOT EXISTS idx_event_bus_pending
    ON pm_event_bus(topic, published_at)
    WHERE is_consumed = FALSE AND dead_lettered = FALSE;
CREATE INDEX IF NOT EXISTS idx_event_bus_partition
    ON pm_event_bus(partition_key, published_at)
    WHERE is_consumed = FALSE;
CREATE INDEX IF NOT EXISTS idx_event_bus_expires
    ON pm_event_bus(expires_at)
    WHERE is_consumed = FALSE;

-- ---------------------------------------------------------------------------
-- pm_queue_jobs — async job queue
-- Durable job queue for background processing.
-- Workers poll this table for work.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_queue_jobs (
    id              BIGSERIAL PRIMARY KEY,
    job_id          UUID NOT NULL DEFAULT uuid_generate_v4(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scheduled_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours'),

    -- Job definition
    job_type        TEXT NOT NULL,                          -- 'memory.compress' | 'vector.embed' | ...
    job_payload     JSONB NOT NULL DEFAULT '{}',
    priority        INTEGER NOT NULL DEFAULT 5,             -- 1=highest 10=lowest
    queue_name      TEXT NOT NULL DEFAULT 'default',

    -- State
    status          job_status NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    retry_delay_s   INTEGER DEFAULT 60,
    next_retry_at   TIMESTAMPTZ,

    -- Ownership
    worker_id       TEXT,
    locked_at       TIMESTAMPTZ,
    lock_expires_at TIMESTAMPTZ,                            -- prevent zombie locks

    -- Context
    user_id         BIGINT,
    session_id      TEXT,
    triggered_by    TEXT,                                   -- event_id or 'scheduler'

    -- Result
    result          JSONB,
    error_message   TEXT,
    error_stack     TEXT
);

CREATE INDEX IF NOT EXISTS idx_queue_pending
    ON pm_queue_jobs(queue_name, priority, scheduled_at)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_queue_user
    ON pm_queue_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_queue_type
    ON pm_queue_jobs(job_type, status);
CREATE INDEX IF NOT EXISTS idx_queue_locked_expire
    ON pm_queue_jobs(lock_expires_at)
    WHERE status = 'running';

-- ---------------------------------------------------------------------------
-- pm_risk_predictions — ML risk trajectory
-- Forward-looking risk assessments and predictions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_risk_predictions (
    id              BIGSERIAL PRIMARY KEY,
    prediction_id   UUID NOT NULL DEFAULT uuid_generate_v4(),
    user_id         BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until     TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours'),

    -- Current assessment
    current_risk    NUMERIC(4,3) NOT NULL,
    current_level   risk_level NOT NULL,
    risk_factors    JSONB DEFAULT '[]',                     -- [{factor, weight, description}]

    -- Trajectory prediction
    predicted_24h   NUMERIC(4,3),
    predicted_72h   NUMERIC(4,3),
    predicted_7d    NUMERIC(4,3),
    trend           TEXT,                                   -- rising|stable|falling

    -- Triggers
    spike_probability NUMERIC(4,3),                        -- prob of spike in next 24h
    escalation_risk   NUMERIC(4,3),                        -- prob of escalation needed

    -- Recommendations
    recommended_route   TEXT,
    recommended_agent   TEXT,
    recommended_actions TEXT[] DEFAULT '{}',
    alert_threshold     NUMERIC(4,3) DEFAULT 0.75,

    -- Model meta
    model_version   TEXT DEFAULT 'v1',
    confidence      NUMERIC(4,3),
    feature_count   INTEGER,
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_risk_pred_user_current
    ON pm_risk_predictions(user_id, is_current)
    WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_risk_pred_high
    ON pm_risk_predictions(current_level, created_at DESC)
    WHERE current_level IN ('high', 'critical');
CREATE INDEX IF NOT EXISTS idx_risk_pred_spike
    ON pm_risk_predictions(spike_probability DESC NULLS LAST)
    WHERE is_current = TRUE;

-- ---------------------------------------------------------------------------
-- pm_recovery_plans — automated recovery workflows
-- When a client goes silent, disengages, or enters crisis —
-- recovery plans define the automated response sequence.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_recovery_plans (
    id              BIGSERIAL PRIMARY KEY,
    plan_id         UUID NOT NULL DEFAULT uuid_generate_v4(),
    user_id         BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Trigger
    trigger_type    TEXT NOT NULL,                          -- silence|disengagement|crisis|payment_lapse
    trigger_data    JSONB DEFAULT '{}',
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Plan
    plan_type       TEXT NOT NULL,                          -- gentle_reengagement|urgent_support|payment_recovery
    steps           JSONB NOT NULL DEFAULT '[]',            -- [{step, action, delay_h, executed_at, result}]
    current_step    INTEGER NOT NULL DEFAULT 0,
    total_steps     INTEGER NOT NULL DEFAULT 0,

    -- Execution
    status          recovery_status NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    next_action_at  TIMESTAMPTZ,

    -- Outcome
    success         BOOLEAN,
    outcome_notes   TEXT,
    client_responded BOOLEAN DEFAULT FALSE,
    client_responded_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_recovery_user
    ON pm_recovery_plans(user_id, status);
CREATE INDEX IF NOT EXISTS idx_recovery_next_action
    ON pm_recovery_plans(next_action_at)
    WHERE status IN ('pending', 'in_progress');
CREATE INDEX IF NOT EXISTS idx_recovery_active
    ON pm_recovery_plans(status, updated_at DESC)
    WHERE status IN ('pending', 'in_progress');

-- ---------------------------------------------------------------------------
-- pm_runtime_health — runtime supervisor metrics
-- Continuous health monitoring for all subsystems.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pm_runtime_health (
    id              BIGSERIAL PRIMARY KEY,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    subsystem       TEXT NOT NULL,                          -- orchestrator|memory|queue|event_bus|...

    -- Health
    status          TEXT NOT NULL DEFAULT 'ok',            -- ok|degraded|critical|down
    latency_ms      INTEGER,
    error_rate      NUMERIC(5,4),                          -- 0.0000-1.0000
    throughput_rps  NUMERIC(8,2),                          -- requests/sec

    -- Counters
    requests_total  BIGINT DEFAULT 0,
    errors_total    BIGINT DEFAULT 0,
    warnings_total  BIGINT DEFAULT 0,

    -- Resources
    memory_mb       INTEGER,
    cpu_pct         NUMERIC(5,2),
    queue_depth     INTEGER,
    active_workers  INTEGER,

    -- Circuit breaker
    circuit_state   TEXT DEFAULT 'closed',                 -- closed|open|half_open
    circuit_opens   INTEGER DEFAULT 0,
    last_circuit_open TIMESTAMPTZ,

    -- Detail
    details         JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_health_subsystem_ts
    ON pm_runtime_health(subsystem, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_critical
    ON pm_runtime_health(recorded_at DESC)
    WHERE status IN ('critical', 'down');

-- ---------------------------------------------------------------------------
-- VIEWS — Dashboard-ready aggregations
-- ---------------------------------------------------------------------------

-- Active clients at risk
CREATE OR REPLACE VIEW pm_view_risk_clients AS
SELECT
    cp.user_id,
    cp.display_name,
    cp.current_risk_level,
    rp.current_risk,
    rp.spike_probability,
    rp.trend,
    rp.recommended_route,
    rp.recommended_agent,
    cp.last_active_route,
    cp.last_contact_at,
    cp.escalation_count,
    cp.payment_status
FROM pm_client_profiles cp
LEFT JOIN pm_risk_predictions rp
    ON rp.user_id = cp.user_id AND rp.is_current = TRUE
WHERE cp.current_risk_level IN ('medium', 'high', 'critical')
   OR rp.spike_probability > 0.50
ORDER BY rp.current_risk DESC NULLS LAST;

-- Recent escalations
CREATE OR REPLACE VIEW pm_view_escalations AS
SELECT
    t.user_id,
    cp.display_name,
    t.ts,
    t.summary,
    t.risk_score,
    t.route,
    t.agent,
    t.details
FROM pm_memory_timeline t
JOIN pm_client_profiles cp ON cp.user_id = t.user_id
WHERE t.event_type = 'escalation_triggered'
ORDER BY t.ts DESC;

-- Queue health
CREATE OR REPLACE VIEW pm_view_queue_health AS
SELECT
    queue_name,
    job_type,
    status,
    COUNT(*) AS count,
    AVG(EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - created_at))) AS avg_duration_s,
    MAX(attempts) AS max_attempts
FROM pm_queue_jobs
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY queue_name, job_type, status
ORDER BY queue_name, job_type;

-- ---------------------------------------------------------------------------
-- AUTO-UPDATE TRIGGERS
-- ---------------------------------------------------------------------------

-- Update pm_client_profiles.updated_at
CREATE OR REPLACE FUNCTION pm_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_client_profiles_updated ON pm_client_profiles;
CREATE TRIGGER trg_client_profiles_updated
    BEFORE UPDATE ON pm_client_profiles
    FOR EACH ROW EXECUTE FUNCTION pm_update_timestamp();

DROP TRIGGER IF EXISTS trg_active_stage_updated ON pm_memory_active_stage;
CREATE TRIGGER trg_active_stage_updated
    BEFORE UPDATE ON pm_memory_active_stage
    FOR EACH ROW EXECUTE FUNCTION pm_update_timestamp();

DROP TRIGGER IF EXISTS trg_recovery_updated ON pm_recovery_plans;
CREATE TRIGGER trg_recovery_updated
    BEFORE UPDATE ON pm_recovery_plans
    FOR EACH ROW EXECUTE FUNCTION pm_update_timestamp();

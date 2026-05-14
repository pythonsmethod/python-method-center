-- migrate_multi_stage_orchestration.sql
-- Phase 3.10 — Multi-Stage Orchestration Engine
-- Python Method Digital Rehabilitation Center
--
-- Idempotent migration: safe to run multiple times.
-- Adds 12 columns + 6 indexes to pm_client_profiles.
-- No data is deleted or modified.

-- ── Column additions ──────────────────────────────────────────────────────

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS orchestration_state         TEXT         DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS current_primary_stage       TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS active_stage_count          INTEGER      DEFAULT 0,
    ADD COLUMN IF NOT EXISTS active_stages               JSONB        DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS blocked_stages              JSONB        DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS waiting_stages              JSONB        DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS stage_conflict_detected     BOOLEAN      DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS route_overload_score        NUMERIC(5,4) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS next_orchestration_action   TEXT         DEFAULT 'neutral',
    ADD COLUMN IF NOT EXISTS handoff_ready               BOOLEAN      DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS orchestration_notes         JSONB        DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS last_orchestration_check    TIMESTAMPTZ  DEFAULT NULL;

-- ── Indexes ───────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pm_orchestration_state
    ON pm_client_profiles (orchestration_state);

CREATE INDEX IF NOT EXISTS idx_pm_current_primary_stage
    ON pm_client_profiles (current_primary_stage);

CREATE INDEX IF NOT EXISTS idx_pm_stage_conflict_detected
    ON pm_client_profiles (stage_conflict_detected);

CREATE INDEX IF NOT EXISTS idx_pm_route_overload_score
    ON pm_client_profiles (route_overload_score);

CREATE INDEX IF NOT EXISTS idx_pm_handoff_ready
    ON pm_client_profiles (handoff_ready);

CREATE INDEX IF NOT EXISTS idx_pm_last_orchestration_check
    ON pm_client_profiles (last_orchestration_check);

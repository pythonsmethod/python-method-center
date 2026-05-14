-- migrate_dynamic_pacing.sql
-- Phase 3.11 — Dynamic Pacing Intelligence
-- Python Method Digital Rehabilitation Center
--
-- Idempotent migration: safe to run multiple times.
-- Adds 12 columns + 6 indexes to pm_client_profiles.
-- No data is deleted or modified.

-- ── Column additions ──────────────────────────────────────────────────────

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS pacing_state                     TEXT         DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS pacing_score                     NUMERIC(5,4) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pacing_stability_score           NUMERIC(5,4) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pacing_pressure_risk             NUMERIC(5,4) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS recommended_route_speed          TEXT         DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS adaptive_pause_needed            BOOLEAN      DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS pacing_overload_risk             NUMERIC(5,4) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS engagement_recovery_capacity     NUMERIC(5,4) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS progression_sustainability_score NUMERIC(5,4) DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS safe_next_step_delay             INTEGER      DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pacing_notes                     JSONB        DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS last_pacing_check                TIMESTAMPTZ  DEFAULT NULL;

-- ── Indexes ───────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pm_pacing_state
    ON pm_client_profiles (pacing_state);

CREATE INDEX IF NOT EXISTS idx_pm_pacing_score
    ON pm_client_profiles (pacing_score);

CREATE INDEX IF NOT EXISTS idx_pm_adaptive_pause_needed
    ON pm_client_profiles (adaptive_pause_needed);

CREATE INDEX IF NOT EXISTS idx_pm_pacing_overload_risk
    ON pm_client_profiles (pacing_overload_risk);

CREATE INDEX IF NOT EXISTS idx_pm_safe_next_step_delay
    ON pm_client_profiles (safe_next_step_delay);

CREATE INDEX IF NOT EXISTS idx_pm_last_pacing_check
    ON pm_client_profiles (last_pacing_check);

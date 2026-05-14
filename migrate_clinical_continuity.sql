-- =============================================================================
-- PHASE 3.7 -- Clinical Continuity Intelligence
-- migrate_clinical_continuity.sql
-- Idempotent: safe to run multiple times.
-- =============================================================================

-- 1. Add continuity fields to pm_client_profiles
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS continuity_state           TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS continuity_score           NUMERIC(5,4) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS continuity_gap_detected    BOOLEAN      DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stage_transition_risk      BOOLEAN      DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS unresolved_continuity_loop BOOLEAN      DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS waiting_stability          TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS last_continuity_check      TIMESTAMPTZ  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS continuity_notes           JSONB        DEFAULT '{}'::jsonb;

-- 2. Indexes
CREATE INDEX IF NOT EXISTS idx_profiles_continuity_state
    ON pm_client_profiles (continuity_state);

CREATE INDEX IF NOT EXISTS idx_profiles_continuity_gap
    ON pm_client_profiles (continuity_gap_detected);

CREATE INDEX IF NOT EXISTS idx_profiles_stage_transition_risk
    ON pm_client_profiles (stage_transition_risk);

CREATE INDEX IF NOT EXISTS idx_profiles_unresolved_continuity_loop
    ON pm_client_profiles (unresolved_continuity_loop);

CREATE INDEX IF NOT EXISTS idx_profiles_last_continuity_check
    ON pm_client_profiles (last_continuity_check);

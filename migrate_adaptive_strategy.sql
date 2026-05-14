-- migrate_adaptive_strategy.sql
-- Phase 3.15 — Adaptive Rehabilitation Strategy Layer
-- Idempotent migration: safe to run multiple times
-- Adds 13 columns + 6 indexes to pm_client_profiles

-- ── Adaptive Rehabilitation Strategy Columns ──────────────────────────────────

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS adaptive_strategy_state TEXT DEFAULT 'UNKNOWN';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS recommended_continuity_strategy TEXT DEFAULT 'hold_no_change';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS strategy_confidence_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS strategy_stability_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS strategy_shift_needed BOOLEAN DEFAULT FALSE;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS continuity_support_mode TEXT DEFAULT 'hold';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS route_support_intensity FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS pacing_strategy_alignment FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS longitudinal_strategy_fit FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS emotional_safety_strategy_fit FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS expert_handoff_strategy_fit FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS strategy_notes JSONB DEFAULT '{}';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS last_strategy_check TIMESTAMP WITH TIME ZONE;

-- ── Indexes ────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pm_profiles_adaptive_strategy_state
    ON pm_client_profiles (adaptive_strategy_state);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_strategy_shift_needed
    ON pm_client_profiles (strategy_shift_needed);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_strategy_confidence
    ON pm_client_profiles (strategy_confidence_score);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_continuity_support_mode
    ON pm_client_profiles (continuity_support_mode);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_last_strategy_check
    ON pm_client_profiles (last_strategy_check);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_strategy_stability
    ON pm_client_profiles (strategy_stability_score);

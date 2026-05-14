-- Phase 3.19: Institutional Memory Intelligence
-- Migration: create pm_institutional_memory table
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS
-- No changes to any existing table

CREATE TABLE IF NOT EXISTS pm_institutional_memory (
    id                                BIGSERIAL PRIMARY KEY,
    recorded_at                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    institutional_memory_state        TEXT,
    governance_pattern_score          FLOAT DEFAULT 0.0,
    overload_pattern_score            FLOAT DEFAULT 0.0,
    pacing_pattern_score              FLOAT DEFAULT 0.0,
    continuity_resilience_score       FLOAT DEFAULT 0.0,
    stabilization_effectiveness_score FLOAT DEFAULT 0.0,
    route_erosion_pattern_score       FLOAT DEFAULT 0.0,
    recovery_resilience_pattern_score FLOAT DEFAULT 0.0,
    dispatcher_safety_pattern_score   FLOAT DEFAULT 0.0,
    silence_integrity_pattern_score   FLOAT DEFAULT 0.0,
    institutional_stability_score     FLOAT DEFAULT 0.0,
    historical_sample_size            INTEGER DEFAULT 0,
    institutional_memory_notes        JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pm_im_recorded_at
    ON pm_institutional_memory (recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_pm_im_state
    ON pm_institutional_memory (institutional_memory_state);

CREATE INDEX IF NOT EXISTS idx_pm_im_stability_score
    ON pm_institutional_memory (institutional_stability_score);

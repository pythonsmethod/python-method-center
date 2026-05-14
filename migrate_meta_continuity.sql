-- Phase 3.18: Meta-Continuity Intelligence
-- Migration: create pm_center_continuity_metrics table
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS
-- No changes to pm_client_profiles

CREATE TABLE IF NOT EXISTS pm_center_continuity_metrics (
    id                                  BIGSERIAL PRIMARY KEY,
    checked_at                          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    meta_continuity_state               TEXT,
    global_continuity_health_score      FLOAT DEFAULT 0.0,
    center_route_stability_score        FLOAT DEFAULT 0.0,
    systemic_disengagement_score        FLOAT DEFAULT 0.0,
    systemic_overload_score             FLOAT DEFAULT 0.0,
    pacing_sustainability_score         FLOAT DEFAULT 0.0,
    governance_stability_score          FLOAT DEFAULT 0.0,
    continuity_erosion_cluster_detected BOOLEAN DEFAULT FALSE,
    recovery_pattern_strength           FLOAT DEFAULT 0.0,
    strategy_effectiveness_signal       FLOAT DEFAULT 0.0,
    route_durability_signal             FLOAT DEFAULT 0.0,
    center_silence_integrity_score      FLOAT DEFAULT 0.0,
    dispatcher_alignment_score          FLOAT DEFAULT 0.0,
    sample_size                         INTEGER DEFAULT 0,
    meta_continuity_notes               JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pm_ccm_checked_at
    ON pm_center_continuity_metrics (checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_pm_ccm_state
    ON pm_center_continuity_metrics (meta_continuity_state);

CREATE INDEX IF NOT EXISTS idx_pm_ccm_health_score
    ON pm_center_continuity_metrics (global_continuity_health_score);

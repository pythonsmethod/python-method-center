-- migrate_self_stabilizing_governance.sql
-- Phase 3.17 — Self-Stabilizing Governance Engine
-- Idempotent migration: all ADD COLUMN IF NOT EXISTS, all CREATE INDEX IF NOT EXISTS

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS governance_stability_state TEXT DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS governance_drift_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS overload_cascade_risk FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS coherence_degradation_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pacing_pressure_stability FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS route_conflict_stability FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS escalation_stability_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS silence_respect_integrity FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS recovery_policy_integrity FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS dispatcher_safety_alignment FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS stabilization_needed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS recommended_stabilization_mode TEXT DEFAULT 'no_change',
    ADD COLUMN IF NOT EXISTS governance_stabilization_notes JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS last_governance_stabilization_check TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_governance_stability_state
    ON pm_client_profiles(governance_stability_state);

CREATE INDEX IF NOT EXISTS idx_governance_drift_score
    ON pm_client_profiles(governance_drift_score);

CREATE INDEX IF NOT EXISTS idx_stabilization_needed
    ON pm_client_profiles(stabilization_needed);

CREATE INDEX IF NOT EXISTS idx_overload_cascade_risk
    ON pm_client_profiles(overload_cascade_risk);

CREATE INDEX IF NOT EXISTS idx_last_governance_stabilization_check
    ON pm_client_profiles(last_governance_stabilization_check);

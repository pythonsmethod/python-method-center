-- Phase 3.16 — Rehabilitation Route Simulation Engine
-- Idempotent migration for pm_client_profiles table
-- All columns: ADD COLUMN IF NOT EXISTS
-- All indexes: CREATE INDEX IF NOT EXISTS

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS route_simulation_state VARCHAR(64) DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS simulation_stability_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS continuity_recovery_probability FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pacing_stabilization_effect FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS overload_mitigation_effect FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS route_erosion_risk_projection FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS disengagement_recovery_projection FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS orchestration_balance_projection FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS longitudinal_stability_projection FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS adaptive_strategy_projection FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS simulation_coherence_score FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS simulation_notes JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS last_route_simulation_check TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_pm_route_simulation_state
    ON pm_client_profiles (route_simulation_state);

CREATE INDEX IF NOT EXISTS idx_pm_simulation_stability_score
    ON pm_client_profiles (simulation_stability_score);

CREATE INDEX IF NOT EXISTS idx_pm_simulation_coherence_score
    ON pm_client_profiles (simulation_coherence_score);

CREATE INDEX IF NOT EXISTS idx_pm_last_route_simulation_check
    ON pm_client_profiles (last_route_simulation_check);

CREATE INDEX IF NOT EXISTS idx_pm_route_erosion_risk_projection
    ON pm_client_profiles (route_erosion_risk_projection);

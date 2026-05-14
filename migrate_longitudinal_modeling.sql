-- migrate_longitudinal_modeling.sql
-- Phase 3.14 — Longitudinal Rehabilitation Modeling
-- Idempotent migration: safe to run multiple times
-- Adds 14 columns + 6 indexes to pm_client_profiles

-- ── Longitudinal Rehabilitation Modeling Columns ──────────────────────────────

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS long_term_rehabilitation_state TEXT DEFAULT 'UNKNOWN';

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS longitudinal_stability_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS rehabilitation_resilience_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS continuity_sustainability_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS recurring_instability_detected BOOLEAN DEFAULT FALSE;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS disengagement_cycle_detected BOOLEAN DEFAULT FALSE;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS pacing_adaptation_quality FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS recovery_after_disruption_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS long_term_route_durability FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS continuity_erosion_risk FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS rehabilitation_persistence_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS longitudinal_coherence_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS longitudinal_notes JSONB DEFAULT '{}';

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS last_longitudinal_check TIMESTAMP WITH TIME ZONE;

-- ── Indexes ────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pm_profiles_long_term_state
  ON pm_client_profiles (long_term_rehabilitation_state);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_recurring_instability
  ON pm_client_profiles (recurring_instability_detected);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_disengagement_cycle
  ON pm_client_profiles (disengagement_cycle_detected);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_longitudinal_stability
  ON pm_client_profiles (longitudinal_stability_score);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_continuity_erosion_risk
  ON pm_client_profiles (continuity_erosion_risk);

CREATE INDEX IF NOT EXISTS idx_pm_profiles_last_longitudinal_check
  ON pm_client_profiles (last_longitudinal_check);

-- migrate_adaptive_behaviour.sql
-- Phase 3.6 -- Adaptive Behavioural Intelligence
-- DB migration for behavioural profile fields on pm_client_profiles
-- Idempotent: safe to run multiple times

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS behavioural_profile JSONB DEFAULT NULL;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS behavioural_confidence FLOAT DEFAULT NULL;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS last_behaviour_update_at TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS behavioural_shift_detected BOOLEAN DEFAULT FALSE;

ALTER TABLE pm_client_profiles
  ADD COLUMN IF NOT EXISTS behavioural_volatility_score FLOAT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_profiles_behavioural_confidence
  ON pm_client_profiles (behavioural_confidence);

CREATE INDEX IF NOT EXISTS idx_profiles_last_behaviour_update_at
  ON pm_client_profiles (last_behaviour_update_at);

CREATE INDEX IF NOT EXISTS idx_profiles_behavioural_shift_detected
  ON pm_client_profiles (behavioural_shift_detected);

CREATE INDEX IF NOT EXISTS idx_profiles_behavioural_volatility_score
  ON pm_client_profiles (behavioural_volatility_score);

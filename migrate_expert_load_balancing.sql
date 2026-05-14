-- migrate_expert_load_balancing.sql
-- Phase 3.12 — Expert Load Balancing Intelligence
-- Production-safe migration: all statements use IF NOT EXISTS
-- Safe to run multiple times. No data deleted or modified.

-- =========================================================
-- ADD COLUMNS to pm_client_profiles
-- =========================================================

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS expert_load_state VARCHAR(32) DEFAULT 'UNKNOWN';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS support_congestion_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS escalation_queue_pressure FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS expert_overload_risk FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS continuity_handoff_risk FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS operational_stability_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS safe_assignment_capacity VARCHAR(32) DEFAULT 'conservative';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS escalation_distribution_balance FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS response_sustainability_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS human_support_integrity_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS load_balancing_notes JSONB DEFAULT '{}';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS last_load_balancing_check TIMESTAMP WITH TIME ZONE;

-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_pm_client_expert_load_state
    ON pm_client_profiles(expert_load_state);

CREATE INDEX IF NOT EXISTS idx_pm_client_support_congestion_score
    ON pm_client_profiles(support_congestion_score);

CREATE INDEX IF NOT EXISTS idx_pm_client_expert_overload_risk
    ON pm_client_profiles(expert_overload_risk);

CREATE INDEX IF NOT EXISTS idx_pm_client_operational_stability_score
    ON pm_client_profiles(operational_stability_score);

CREATE INDEX IF NOT EXISTS idx_pm_client_safe_assignment_capacity
    ON pm_client_profiles(safe_assignment_capacity);

CREATE INDEX IF NOT EXISTS idx_pm_client_last_load_balancing_check
    ON pm_client_profiles(last_load_balancing_check);

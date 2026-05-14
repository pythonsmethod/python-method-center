-- migrate_central_cognitive_orchestrator.sql
-- Phase 3.13 — Central Cognitive Orchestrator
-- Production-safe migration: all statements use IF NOT EXISTS
-- Safe to run multiple times. No data deleted or modified.

-- =========================================================
-- ADD COLUMNS to pm_client_profiles
-- =========================================================

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS system_coherence_state VARCHAR(32) DEFAULT 'UNKNOWN';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS dominant_operational_priority VARCHAR(32) DEFAULT 'NORMAL_OPERATION';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS governance_conflict_detected BOOLEAN DEFAULT FALSE;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS operational_drift_score FLOAT DEFAULT 0.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS continuity_integrity_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS emotional_safety_integrity_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS route_integrity_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS overload_chain_detected BOOLEAN DEFAULT FALSE;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS escalation_coherence_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS orchestration_coherence_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS pacing_coherence_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS overall_system_stability_score FLOAT DEFAULT 1.0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS cognitive_orchestrator_notes JSONB DEFAULT '{}';

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS last_cognitive_orchestrator_check TIMESTAMP WITH TIME ZONE;

-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_pm_client_system_coherence_state
    ON pm_client_profiles(system_coherence_state);

CREATE INDEX IF NOT EXISTS idx_pm_client_dominant_operational_priority
    ON pm_client_profiles(dominant_operational_priority);

CREATE INDEX IF NOT EXISTS idx_pm_client_governance_conflict_detected
    ON pm_client_profiles(governance_conflict_detected);

CREATE INDEX IF NOT EXISTS idx_pm_client_overall_system_stability_score
    ON pm_client_profiles(overall_system_stability_score);

CREATE INDEX IF NOT EXISTS idx_pm_client_overload_chain_detected
    ON pm_client_profiles(overload_chain_detected);

CREATE INDEX IF NOT EXISTS idx_pm_client_last_cognitive_orchestrator_check
    ON pm_client_profiles(last_cognitive_orchestrator_check);

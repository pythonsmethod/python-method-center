-- =============================================================================
-- PHASE 3.5 — Silent User Scanner
-- Migration: migrate_silent_scanner.sql
-- Python Method Digital Rehabilitation Center
--
-- Purpose: Add scanner tracking fields to pm_client_profiles
--          for idempotent silent scan management.
--
-- All statements are idempotent (IF NOT EXISTS / IF EXISTS).
-- Safe to run multiple times without side effects.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Add scanner tracking columns to pm_client_profiles
-- ---------------------------------------------------------------------------

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS last_silent_scan_at     TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS silent_scan_count       INTEGER     DEFAULT 0;

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS silent_scan_reason      TEXT        DEFAULT NULL;

-- ---------------------------------------------------------------------------
-- Add emotional overload flag if not present (referenced by scanner)
-- ---------------------------------------------------------------------------

ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS emotional_overload_flag BOOLEAN     DEFAULT FALSE;

-- ---------------------------------------------------------------------------
-- Indexes for efficient scanner candidate selection
-- ---------------------------------------------------------------------------

-- Index on last_user_message_at for silence threshold queries
CREATE INDEX IF NOT EXISTS idx_profiles_last_user_message_at
    ON pm_client_profiles (last_user_message_at)
    WHERE last_user_message_at IS NOT NULL;

-- Index on last_silent_scan_at for rescan interval checks
CREATE INDEX IF NOT EXISTS idx_profiles_last_silent_scan_at
    ON pm_client_profiles (last_silent_scan_at)
    WHERE last_silent_scan_at IS NOT NULL;

-- Composite index for the main scanner candidate query
-- (silence_respect, explicit_refusal, human_escalation, last_user_message_at)
CREATE INDEX IF NOT EXISTS idx_profiles_scanner_candidate
    ON pm_client_profiles (
        last_user_message_at,
        silence_respect,
        explicit_refusal,
        human_escalation_required
    )
    WHERE
        last_user_message_at IS NOT NULL
        AND COALESCE(silence_respect, FALSE) = FALSE
        AND COALESCE(explicit_refusal, FALSE) = FALSE
        AND COALESCE(human_escalation_required, FALSE) = FALSE;

-- Index on current_stage for priority ordering
CREATE INDEX IF NOT EXISTS idx_profiles_current_stage
    ON pm_client_profiles (current_stage)
    WHERE current_stage IS NOT NULL;

-- Index on recovery_cooldown_until for cooldown checks
CREATE INDEX IF NOT EXISTS idx_profiles_cooldown
    ON pm_client_profiles (recovery_cooldown_until)
    WHERE recovery_cooldown_until IS NOT NULL;

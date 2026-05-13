-- =============================================================================
-- PHASE 3.3 — Proactive Engagement Governance
-- Migration: migrate_recovery_policy.sql
-- Python Method Digital Rehabilitation Center
--
-- Creates pm_recovery_policy_log table for tracking governance decisions.
-- All statements are idempotent (safe to run multiple times).
-- =============================================================================

-- Create pm_recovery_policy_log table if it does not exist
CREATE TABLE IF NOT EXISTS pm_recovery_policy_log (
    id                      BIGSERIAL PRIMARY KEY,
    user_id                 BIGINT       NOT NULL,
    action                  VARCHAR(32)  NOT NULL,   -- ALLOW/DELAY/SUPPRESS/ESCALATE_HUMAN/SILENCE_RESPECT
    reason                  TEXT,
    cooldown_until          TIMESTAMPTZ,
    max_attempts_remaining  INTEGER      DEFAULT 0,
    tone_mode               VARCHAR(64),
    recovery_channel        VARCHAR(32),
    human_escalation_required BOOLEAN   DEFAULT FALSE,
    next_action             VARCHAR(64),
    fatigue_score           NUMERIC(5,3) DEFAULT 0.0,
    suppression_reason      VARCHAR(128),
    silence_respect         BOOLEAN      DEFAULT FALSE,
    created_at              TIMESTAMPTZ  DEFAULT NOW()
);

-- Idempotent column additions for pm_recovery_policy_log
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS reason                   TEXT;
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS cooldown_until           TIMESTAMPTZ;
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS max_attempts_remaining   INTEGER DEFAULT 0;
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS tone_mode                VARCHAR(64);
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS recovery_channel         VARCHAR(32);
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS human_escalation_required BOOLEAN DEFAULT FALSE;
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS next_action              VARCHAR(64);
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS fatigue_score            NUMERIC(5,3) DEFAULT 0.0;
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS suppression_reason       VARCHAR(128);
ALTER TABLE pm_recovery_policy_log
    ADD COLUMN IF NOT EXISTS silence_respect          BOOLEAN DEFAULT FALSE;

-- Idempotent column additions for pm_client_profiles (recovery governance fields)
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS silence_respect          BOOLEAN     DEFAULT FALSE;
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS recovery_attempt_count   INTEGER     DEFAULT 0;
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS last_recovery_at         TIMESTAMPTZ;
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS recovery_cooldown_until  TIMESTAMPTZ;
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS human_escalation_required BOOLEAN    DEFAULT FALSE;
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS fatigue_score            NUMERIC(5,3) DEFAULT 0.0;
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS last_ai_message_at       TIMESTAMPTZ;
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS explicit_refusal         BOOLEAN     DEFAULT FALSE;

-- Indexes for pm_recovery_policy_log
CREATE INDEX IF NOT EXISTS idx_rpl_user_id
    ON pm_recovery_policy_log(user_id);
CREATE INDEX IF NOT EXISTS idx_rpl_action
    ON pm_recovery_policy_log(action);
CREATE INDEX IF NOT EXISTS idx_rpl_created_at
    ON pm_recovery_policy_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rpl_cooldown_until
    ON pm_recovery_policy_log(cooldown_until)
    WHERE cooldown_until IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rpl_human_escalation
    ON pm_recovery_policy_log(human_escalation_required, created_at DESC)
    WHERE human_escalation_required = TRUE;

-- Indexes for pm_client_profiles (new governance columns)
CREATE INDEX IF NOT EXISTS idx_cp_silence_respect
    ON pm_client_profiles(silence_respect)
    WHERE silence_respect = TRUE;
CREATE INDEX IF NOT EXISTS idx_cp_recovery_attempt_count
    ON pm_client_profiles(recovery_attempt_count)
    WHERE recovery_attempt_count > 0;

-- =============================================================================
-- PHASE 3.4 — Proactive Message Dispatcher
-- Migration: migrate_dispatch_log.sql
-- All statements idempotent (safe to run multiple times).
-- =============================================================================

-- pm_dispatch_log: tracks every dispatch attempt
CREATE TABLE IF NOT EXISTS pm_dispatch_log (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT       NOT NULL,
    tone_mode           VARCHAR(64),
    template_id         VARCHAR(128),
    policy_log_id       BIGINT,
    idempotency_key     VARCHAR(64)  NOT NULL UNIQUE,
    result              VARCHAR(32)  NOT NULL,  -- SENT/SUPPRESSED/SKIPPED/ERROR/DUPLICATE
    suppression_reason  VARCHAR(256),
    error_detail        TEXT,
    sent_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- Idempotent column additions for pm_dispatch_log
ALTER TABLE pm_dispatch_log ADD COLUMN IF NOT EXISTS tone_mode          VARCHAR(64);
ALTER TABLE pm_dispatch_log ADD COLUMN IF NOT EXISTS template_id        VARCHAR(128);
ALTER TABLE pm_dispatch_log ADD COLUMN IF NOT EXISTS policy_log_id      BIGINT;
ALTER TABLE pm_dispatch_log ADD COLUMN IF NOT EXISTS suppression_reason  VARCHAR(256);
ALTER TABLE pm_dispatch_log ADD COLUMN IF NOT EXISTS error_detail        TEXT;
ALTER TABLE pm_dispatch_log ADD COLUMN IF NOT EXISTS sent_at             TIMESTAMPTZ;

-- Indexes for pm_dispatch_log
CREATE INDEX IF NOT EXISTS idx_dl_user_id
    ON pm_dispatch_log(user_id);
CREATE INDEX IF NOT EXISTS idx_dl_policy_log_id
    ON pm_dispatch_log(policy_log_id);
CREATE INDEX IF NOT EXISTS idx_dl_result
    ON pm_dispatch_log(result);
CREATE INDEX IF NOT EXISTS idx_dl_created_at
    ON pm_dispatch_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dl_sent_at
    ON pm_dispatch_log(sent_at DESC)
    WHERE sent_at IS NOT NULL;

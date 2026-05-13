-- migrate_risk_predictions.sql
-- Phase 3.2: Predictive Risk Intelligence — idempotent DB migration
-- Safe to run multiple times. Uses ADD COLUMN IF NOT EXISTS.
-- Run order: after pm_risk_predictions table exists (created in schema_v3.sql)

-- ── Ensure table exists (idempotent) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pm_risk_predictions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL
);

-- ── Add missing columns (all idempotent) ─────────────────────────────────────
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS risk_type           TEXT;
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS risk_level          TEXT DEFAULT 'low';
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS current_risk_score  FLOAT DEFAULT 0.0;
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS risk_reason         TEXT;
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS confidence          FLOAT DEFAULT 0.0;
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS recommended_action  TEXT;
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS next_check_at       TIMESTAMPTZ;
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS details             JSONB DEFAULT '{}';
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS resolved_at         TIMESTAMPTZ;
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE pm_risk_predictions ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ DEFAULT NOW();

-- ── Unique constraint: one active risk prediction per user ────────────────────
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'pm_risk_predictions_user_id_key'
      AND conrelid = 'pm_risk_predictions'::regclass
  ) THEN
    ALTER TABLE pm_risk_predictions ADD CONSTRAINT pm_risk_predictions_user_id_key UNIQUE (user_id);
  END IF;
END $$;

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_risk_predictions_user_id
    ON pm_risk_predictions(user_id);

CREATE INDEX IF NOT EXISTS idx_risk_predictions_level
    ON pm_risk_predictions(risk_level)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_risk_predictions_unresolved
    ON pm_risk_predictions(user_id, updated_at DESC)
    WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_risk_predictions_type
    ON pm_risk_predictions(risk_type)
    WHERE resolved_at IS NULL;

-- ── Check result ──────────────────────────────────────────────────────────────
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'pm_risk_predictions'
ORDER BY ordinal_position;

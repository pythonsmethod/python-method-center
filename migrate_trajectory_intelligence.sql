-- =============================================================================
-- PHASE 3.8 — Trajectory Intelligence Engine DB Migration
-- migrate_trajectory_intelligence.sql
-- Idempotent: safe to run multiple times (uses IF NOT EXISTS / DO blocks)
-- Target table: pm_client_profiles
-- =============================================================================

-- 1. trajectory_state: current trajectory classification label
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='trajectory_state'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN trajectory_state TEXT;
    END IF;
END $$;

-- 2. trajectory_score: composite trajectory score (0.00–1.00)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='trajectory_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN trajectory_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 3. trajectory_direction: improving / stable / declining / unknown
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='trajectory_direction'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN trajectory_direction TEXT;
    END IF;
END $$;

-- 4. stabilization_score: consistency in engagement over time
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='stabilization_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN stabilization_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 5. degradation_score: resistance to degradation (higher = healthier)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='degradation_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN degradation_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 6. oscillation_score: resistance to oscillation (higher = more stable)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='oscillation_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN oscillation_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 7. coherence_score: logical step-sequence alignment
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='coherence_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN coherence_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 8. follow_through_score: completion rate of initiated cycles
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='follow_through_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN follow_through_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 9. pacing_score: speed relative to journey stage (0.5 = ideal)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='pacing_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN pacing_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 10. progression_readiness_score: readiness signals for next stage
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='progression_readiness_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN progression_readiness_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 11. disengagement_score: resistance to long-term drifting
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='disengagement_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN disengagement_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 12. trajectory_gap_detected: boolean flag for significant trajectory gap
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='trajectory_gap_detected'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN trajectory_gap_detected BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- 13. last_trajectory_check: timestamp of most recent evaluation
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='last_trajectory_check'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN last_trajectory_check TIMESTAMPTZ;
    END IF;
END $$;

-- 14. trajectory_notes: JSONB enrichment payload
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='trajectory_notes'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN trajectory_notes JSONB DEFAULT '{}'::jsonb;
    END IF;
END $$;

-- =============================================================================
-- INDEXES (idempotent)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_pm_trajectory_state
    ON pm_client_profiles (trajectory_state);

CREATE INDEX IF NOT EXISTS idx_pm_trajectory_score
    ON pm_client_profiles (trajectory_score);

CREATE INDEX IF NOT EXISTS idx_pm_trajectory_direction
    ON pm_client_profiles (trajectory_direction);

CREATE INDEX IF NOT EXISTS idx_pm_trajectory_gap
    ON pm_client_profiles (trajectory_gap_detected);

CREATE INDEX IF NOT EXISTS idx_pm_last_trajectory_check
    ON pm_client_profiles (last_trajectory_check);

CREATE INDEX IF NOT EXISTS idx_pm_disengagement_score
    ON pm_client_profiles (disengagement_score);

-- =============================================================================
-- VERIFICATION QUERY (run after migration to confirm all columns present)
-- =============================================================================
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'pm_client_profiles'
--   AND column_name IN (
--     'trajectory_state', 'trajectory_score', 'trajectory_direction',
--     'stabilization_score', 'degradation_score', 'oscillation_score',
--     'coherence_score', 'follow_through_score', 'pacing_score',
--     'progression_readiness_score', 'disengagement_score',
--     'trajectory_gap_detected', 'last_trajectory_check', 'trajectory_notes'
--   )
-- ORDER BY column_name;

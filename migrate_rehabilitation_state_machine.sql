-- =============================================================================
-- PHASE 3.9 — Rehabilitation State Machine DB Migration
-- migrate_rehabilitation_state_machine.sql
-- Idempotent: safe to run multiple times (uses IF NOT EXISTS / DO blocks)
-- Target table: pm_client_profiles
-- =============================================================================

-- 1. rehabilitation_state: current formal rehabilitation state
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='rehabilitation_state'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN rehabilitation_state TEXT;
    END IF;
END $$;

-- 2. rehabilitation_stage: intake / diagnostic / intervention / continuity
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='rehabilitation_stage'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN rehabilitation_stage TEXT;
    END IF;
END $$;

-- 3. rehabilitation_substage: free-text sub-stage qualifier
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='rehabilitation_substage'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN rehabilitation_substage TEXT;
    END IF;
END $$;

-- 4. state_entered_at: timestamp when current state was entered
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='state_entered_at'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN state_entered_at TIMESTAMPTZ;
    END IF;
END $$;

-- 5. last_state_transition_at: timestamp of most recent state transition
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='last_state_transition_at'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN last_state_transition_at TIMESTAMPTZ;
    END IF;
END $$;

-- 6. previous_rehabilitation_state: state before the last transition
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='previous_rehabilitation_state'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN previous_rehabilitation_state TEXT;
    END IF;
END $$;

-- 7. next_allowed_states: array of states reachable from current state
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='next_allowed_states'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN next_allowed_states TEXT[];
    END IF;
END $$;

-- 8. blocked_transition_reason: reason if last attempted transition was blocked
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='blocked_transition_reason'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN blocked_transition_reason TEXT;
    END IF;
END $$;

-- 9. stage_completion_score: composite score for current stage completion (0.00-1.00)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='stage_completion_score'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN stage_completion_score NUMERIC DEFAULT 0;
    END IF;
END $$;

-- 10. stage_stall_detected: boolean flag for stall beyond threshold
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='stage_stall_detected'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN stage_stall_detected BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- 11. progression_gate_status: open / closed / pending
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='progression_gate_status'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN progression_gate_status TEXT DEFAULT 'pending';
    END IF;
END $$;

-- 12. escalation_gate_status: clear / flagged / active
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='escalation_gate_status'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN escalation_gate_status TEXT DEFAULT 'clear';
    END IF;
END $$;

-- 13. state_machine_notes: JSONB enrichment payload
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pm_client_profiles' AND column_name='state_machine_notes'
    ) THEN
        ALTER TABLE pm_client_profiles ADD COLUMN state_machine_notes JSONB DEFAULT '{}'::jsonb;
    END IF;
END $$;

-- =============================================================================
-- INDEXES (idempotent)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_pm_rehabilitation_state
    ON pm_client_profiles (rehabilitation_state);

CREATE INDEX IF NOT EXISTS idx_pm_rehabilitation_stage
    ON pm_client_profiles (rehabilitation_stage);

CREATE INDEX IF NOT EXISTS idx_pm_stage_stall_detected
    ON pm_client_profiles (stage_stall_detected);

CREATE INDEX IF NOT EXISTS idx_pm_progression_gate_status
    ON pm_client_profiles (progression_gate_status);

CREATE INDEX IF NOT EXISTS idx_pm_escalation_gate_status
    ON pm_client_profiles (escalation_gate_status);

CREATE INDEX IF NOT EXISTS idx_pm_state_entered_at
    ON pm_client_profiles (state_entered_at);

CREATE INDEX IF NOT EXISTS idx_pm_last_state_transition_at
    ON pm_client_profiles (last_state_transition_at);

-- =============================================================================
-- VERIFICATION QUERY
-- =============================================================================
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'pm_client_profiles'
--   AND column_name IN (
--     'rehabilitation_state', 'rehabilitation_stage', 'rehabilitation_substage',
--     'state_entered_at', 'last_state_transition_at', 'previous_rehabilitation_state',
--     'next_allowed_states', 'blocked_transition_reason', 'stage_completion_score',
--     'stage_stall_detected', 'progression_gate_status', 'escalation_gate_status',
--     'state_machine_notes'
--   )
-- ORDER BY column_name;

-- =============================================================================
-- ROUTE STATE MIGRATION SPEC
-- Documentation only
-- DO NOT APPLY DURING ACTIVE STABILIZATION FREEZE
--
-- File: docs/migrate_route_state.sql
-- Project: Python Method Digital Rehabilitation Center
-- Linked document: docs/route_architecture.md (commit 6a346e6)
-- Freeze notice: docs/stabilization_freeze_notice.md
-- Created: 2026-05-20
--
-- Purpose:
--   This file is a SPECIFICATION document, not a deployment script.
--   It defines the SQL changes required to implement the two care routes:
--     - START_SUPPORT (6 weeks)
--     - FULL_PYTHON_METHOD (5-6 months)
--   as described in docs/route_architecture.md.
--
-- Safety rules:
--   - All alterations use ADD COLUMN IF NOT EXISTS (idempotent, additive only)
--   - No existing columns are modified
--   - No existing columns are dropped
--   - No orchestrator code is changed by this file
--   - No runtime code is touched
--   - No data is deleted or transformed
--   - Safe to apply in any order relative to other migrations
--
-- Apply only after:
--   1. Stabilization freeze is officially lifted
--      (commit: governance: lift stabilization freeze -- Phase 4 complete)
--   2. Phase A is approved in the post-freeze hardening plan
--   3. Tested against a staging database before production
--
-- Execution method (when ready):
--   Railway PostgreSQL console or psql directly against DATABASE_URL
--   After apply: verify with SELECT column_name FROM information_schema.columns
--                WHERE table_name IN ('pm_sessions', 'pm_client_profiles')
--                ORDER BY table_name, ordinal_position;
-- =============================================================================


-- =============================================================================
-- SECTION 1: pm_sessions
-- Operational layer — per-user runtime state between messages
-- Managed by: agents.py (_init_db, load_session, save_session)
-- Apply pattern: matches existing _init_db() ADD COLUMN IF NOT EXISTS pattern
-- =============================================================================

-- care_route: which support route the user is on
-- Values: 'none' | 'START_SUPPORT' | 'FULL_PYTHON_METHOD'
ALTER TABLE pm_sessions
    ADD COLUMN IF NOT EXISTS care_route TEXT NOT NULL DEFAULT 'none';

-- care_duration: planned duration of the route
-- Values: 'undefined' | '6_weeks' | '5_6_months'
ALTER TABLE pm_sessions
    ADD COLUMN IF NOT EXISTS care_duration TEXT NOT NULL DEFAULT 'undefined';

-- ai_support_level: current AI operating mode
-- Values: 'navigation' (pre-payment) | 'active_companion' (post-payment)
-- Transition trigger: payment_status changes to 'paid'
ALTER TABLE pm_sessions
    ADD COLUMN IF NOT EXISTS ai_support_level TEXT NOT NULL DEFAULT 'navigation';

-- karen_access: current status of Karen's involvement
-- Values: 'pending' | 'active' | 'inactive'
-- 'pending'  = payment confirmed, onboarding not yet completed
-- 'active'   = Karen is actively accompanying this route
-- 'inactive' = route completed or not yet started
ALTER TABLE pm_sessions
    ADD COLUMN IF NOT EXISTS karen_access TEXT NOT NULL DEFAULT 'pending';

-- onboarding_stage: progress through post-payment onboarding
-- Values: 'not_started' | 'started' | 'completed'
-- 'not_started' = pre-payment or route not yet activated
-- 'started'     = payment confirmed, AI collecting initial context
-- 'completed'   = onboarding data collected, Karen notified
ALTER TABLE pm_sessions
    ADD COLUMN IF NOT EXISTS onboarding_stage TEXT NOT NULL DEFAULT 'not_started';

-- rehab_stage: current stage within the active route
-- Values: 'pre_start' | 'active' | 'nearing_end' | 'completed'
-- 'pre_start'   = route assigned, onboarding not yet done
-- 'active'      = route running, Karen engaged
-- 'nearing_end' = within 7 days of care_expires_at
-- 'completed'   = route finished (with or without renewal)
ALTER TABLE pm_sessions
    ADD COLUMN IF NOT EXISTS rehab_stage TEXT NOT NULL DEFAULT 'pre_start';

-- renewal_status: state of the renewal flow at route end
-- Values: 'none' | 'initiated' | 'confirmed' | 'declined'
-- 'none'      = not yet near end of route
-- 'initiated' = renewal dialogue started by AI
-- 'confirmed' = user agreed to renew or upgrade
-- 'declined'  = user chose not to continue
ALTER TABLE pm_sessions
    ADD COLUMN IF NOT EXISTS renewal_status TEXT NOT NULL DEFAULT 'none';


-- =============================================================================
-- SECTION 2: pm_client_profiles
-- Long-term layer — persistent master record per client
-- Managed by: memory_engine.py (upsert_client_profile)
-- Apply pattern: same ADD COLUMN IF NOT EXISTS, safe alongside existing columns
-- Existing columns NOT touched:
--   payment_status, active_tariff, onboarding_completed, treatment_stage,
--   requires_human, human_assigned_to, last_active_route, last_active_agent
-- =============================================================================

-- care_route: mirrors pm_sessions.care_route for long-term storage
-- Values: 'none' | 'START_SUPPORT' | 'FULL_PYTHON_METHOD'
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS care_route TEXT DEFAULT 'none';

-- care_duration: mirrors pm_sessions.care_duration for long-term storage
-- Values: 'undefined' | '6_weeks' | '5_6_months'
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS care_duration TEXT DEFAULT 'undefined';

-- support_level: overall tier of support on this route
-- Values: 'minimal' | 'standard' | 'full'
-- 'minimal' = pre-payment navigation only
-- 'standard' = START_SUPPORT (Karen + AI, 6 weeks)
-- 'full'    = FULL_PYTHON_METHOD (Karen + AI, 5-6 months, deep accompaniment)
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS support_level TEXT DEFAULT 'minimal';

-- karen_access: long-term record of Karen access status
-- Values: 'pending' | 'active' | 'inactive'
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS karen_access TEXT DEFAULT 'pending';

-- ai_support_level: long-term record of AI mode
-- Values: 'navigation' | 'active_companion'
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS ai_support_level TEXT DEFAULT 'navigation';

-- onboarding_stage: long-term onboarding progress (enum, replaces boolean onboarding_completed)
-- Values: 'not_started' | 'started' | 'completed'
-- Note: onboarding_completed (boolean) is NOT dropped — both coexist during transition
-- When onboarding_stage = 'completed', onboarding_completed should also = TRUE
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS onboarding_stage TEXT DEFAULT 'not_started';

-- rehab_stage: long-term route stage
-- Values: 'pre_start' | 'active' | 'nearing_end' | 'completed'
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS rehab_stage TEXT DEFAULT 'pre_start';

-- renewal_status: long-term renewal state
-- Values: 'none' | 'initiated' | 'confirmed' | 'declined'
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS renewal_status TEXT DEFAULT 'none';

-- care_started_at: timestamp when the route was activated (payment confirmed)
-- Set once, never updated — immutable record of route start
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS care_started_at TIMESTAMPTZ;

-- care_expires_at: calculated expiry of the current route
-- START_SUPPORT:        care_started_at + 42 days (6 weeks)
-- FULL_PYTHON_METHOD:   care_started_at + 168 days (24 weeks / 5.5 months)
-- Used by: proactive_message_dispatcher.py (nearing_end trigger)
-- Used by: recovery_engine.py (route expiration check)
ALTER TABLE pm_client_profiles
    ADD COLUMN IF NOT EXISTS care_expires_at TIMESTAMPTZ;


-- =============================================================================
-- SECTION 3: INDEXES
-- Performance indexes for new columns on pm_client_profiles
-- All use CREATE INDEX IF NOT EXISTS (safe, idempotent)
-- =============================================================================

-- idx_client_care_route: fast lookup by care route type
-- Use case: dashboard queries, "all START_SUPPORT clients", route-based reports
CREATE INDEX IF NOT EXISTS idx_client_care_route
    ON pm_client_profiles(care_route);

-- idx_client_rehab_stage: fast lookup by current stage
-- Use case: find all clients in 'nearing_end', 'active', or 'completed' stages
CREATE INDEX IF NOT EXISTS idx_client_rehab_stage
    ON pm_client_profiles(rehab_stage);

-- idx_client_care_expires: fast lookup of expiring routes
-- Partial index: only rows where care_expires_at is set (routes in progress)
-- Use case: proactive_message_dispatcher renewal check, sorted by expiry date
CREATE INDEX IF NOT EXISTS idx_client_care_expires
    ON pm_client_profiles(care_expires_at)
    WHERE care_expires_at IS NOT NULL;


-- =============================================================================
-- SECTION 4: VERIFICATION QUERIES
-- Run after applying migration to verify columns were added correctly
-- These are READ-ONLY — safe to run at any time
-- =============================================================================

-- Verify pm_sessions columns:
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'pm_sessions'
--   AND column_name IN (
--     'care_route', 'care_duration', 'ai_support_level',
--     'karen_access', 'onboarding_stage', 'rehab_stage', 'renewal_status'
--   )
-- ORDER BY column_name;

-- Verify pm_client_profiles columns:
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'pm_client_profiles'
--   AND column_name IN (
--     'care_route', 'care_duration', 'support_level', 'karen_access',
--     'ai_support_level', 'onboarding_stage', 'rehab_stage',
--     'renewal_status', 'care_started_at', 'care_expires_at'
--   )
-- ORDER BY column_name;

-- Verify indexes:
-- SELECT indexname, tablename, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'pm_client_profiles'
--   AND indexname IN (
--     'idx_client_care_route',
--     'idx_client_rehab_stage',
--     'idx_client_care_expires'
--   );


-- =============================================================================
-- SECTION 5: ROLLBACK SPEC
-- If migration needs to be rolled back, use DROP COLUMN
-- NOTE: Only execute rollback if NO application code has been deployed
--       that reads these columns. Once Phase B (agents.py load_session)
--       is deployed, rollback requires coordinated code + DB revert.
-- =============================================================================

-- Rollback pm_sessions (run only if needed, never during freeze):
-- ALTER TABLE pm_sessions DROP COLUMN IF EXISTS care_route;
-- ALTER TABLE pm_sessions DROP COLUMN IF EXISTS care_duration;
-- ALTER TABLE pm_sessions DROP COLUMN IF EXISTS ai_support_level;
-- ALTER TABLE pm_sessions DROP COLUMN IF EXISTS karen_access;
-- ALTER TABLE pm_sessions DROP COLUMN IF EXISTS onboarding_stage;
-- ALTER TABLE pm_sessions DROP COLUMN IF EXISTS rehab_stage;
-- ALTER TABLE pm_sessions DROP COLUMN IF EXISTS renewal_status;

-- Rollback pm_client_profiles (run only if needed, never during freeze):
-- DROP INDEX IF EXISTS idx_client_care_route;
-- DROP INDEX IF EXISTS idx_client_rehab_stage;
-- DROP INDEX IF EXISTS idx_client_care_expires;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS care_route;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS care_duration;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS support_level;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS karen_access;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS ai_support_level;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS onboarding_stage;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS rehab_stage;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS renewal_status;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS care_started_at;
-- ALTER TABLE pm_client_profiles DROP COLUMN IF EXISTS care_expires_at;


-- =============================================================================
-- END OF SPEC
-- Next step: docs/route_state_implementation_plan.md (post-freeze Phase B)
-- Linked: docs/route_architecture.md, docs/stabilization_freeze_notice.md
-- =============================================================================

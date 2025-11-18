-- Verification Script for AC (Application Control) Database
-- PostgreSQL - Verify schema deployment
-- Version: 2.0 (2025-11-18)

-- ====================================================================
-- 0. Schema Version Check
-- ====================================================================
\echo '=== Schema Version Check ==='
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'application_catalog')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'application_instances' AND column_name = 'instance_number')
       AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'haproxy_instances') THEN
        RAISE NOTICE 'Schema Version: 2.0 ✓';
    ELSIF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'applications') THEN
        RAISE WARNING 'Schema Version: 1.0 (needs migration to 2.0)';
    ELSE
        RAISE WARNING 'Schema Version: Unknown';
    END IF;
END $$;

-- ====================================================================
-- 0.1. Check v2.0 Critical Fields
-- ====================================================================
\echo ''
\echo '=== Critical v2.0 Fields Check ==='
DO $$
DECLARE
    missing_fields TEXT[] := '{}';
BEGIN
    -- Check application_instances fields
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'application_instances' AND column_name = 'catalog_id') THEN
        missing_fields := array_append(missing_fields, 'application_instances.catalog_id');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'application_instances' AND column_name = 'group_id') THEN
        missing_fields := array_append(missing_fields, 'application_instances.group_id');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'application_instances' AND column_name = 'instance_name') THEN
        missing_fields := array_append(missing_fields, 'application_instances.instance_name');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'application_instances' AND column_name = 'image') THEN
        missing_fields := array_append(missing_fields, 'application_instances.image');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'application_instances' AND column_name = 'tag') THEN
        missing_fields := array_append(missing_fields, 'application_instances.tag');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'application_instances' AND column_name = 'eureka_registered') THEN
        missing_fields := array_append(missing_fields, 'application_instances.eureka_registered');
    END IF;

    -- Check events.instance_id
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'events' AND column_name = 'instance_id') THEN
        missing_fields := array_append(missing_fields, 'events.instance_id');
    END IF;

    -- Check servers flags
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'servers' AND column_name = 'is_haproxy_node') THEN
        missing_fields := array_append(missing_fields, 'servers.is_haproxy_node');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'servers' AND column_name = 'is_eureka_node') THEN
        missing_fields := array_append(missing_fields, 'servers.is_eureka_node');
    END IF;

    IF array_length(missing_fields, 1) > 0 THEN
        RAISE WARNING 'Missing v2.0 fields: %', missing_fields;
    ELSE
        RAISE NOTICE 'All critical v2.0 fields exist ✓';
    END IF;
END $$;

\echo ''

-- ====================================================================
-- 1. List all tables
-- ====================================================================
\echo '=== All Tables ==='
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- ====================================================================
-- 2. Count columns per table
-- ====================================================================
\echo ''
\echo '=== Column Count per Table ==='
SELECT
    table_name,
    COUNT(*) AS column_count
FROM information_schema.columns
WHERE table_schema = 'public'
GROUP BY table_name
ORDER BY table_name;

-- ====================================================================
-- 3. List all foreign key constraints
-- ====================================================================
\echo ''
\echo '=== Foreign Key Constraints ==='
SELECT
    tc.constraint_name,
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
    JOIN information_schema.referential_constraints AS rc
      ON tc.constraint_name = rc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
ORDER BY tc.table_name, tc.constraint_name;

-- ====================================================================
-- 4. List all unique constraints
-- ====================================================================
\echo ''
\echo '=== Unique Constraints ==='
SELECT
    tc.constraint_name,
    tc.table_name,
    string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
WHERE tc.constraint_type = 'UNIQUE'
  AND tc.table_schema = 'public'
GROUP BY tc.constraint_name, tc.table_name
ORDER BY tc.table_name;

-- ====================================================================
-- 5. List all indexes
-- ====================================================================
\echo ''
\echo '=== Indexes ==='
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- ====================================================================
-- 6. List all triggers
-- ====================================================================
\echo ''
\echo '=== Triggers ==='
SELECT
    trigger_name,
    event_manipulation,
    event_object_table AS table_name,
    action_statement
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table, trigger_name;

-- ====================================================================
-- 7. List all functions
-- ====================================================================
\echo ''
\echo '=== Functions ==='
SELECT
    routine_name,
    routine_type,
    data_type AS return_type
FROM information_schema.routines
WHERE routine_schema = 'public'
ORDER BY routine_name;

-- ====================================================================
-- 8. Check table sizes
-- ====================================================================
\echo ''
\echo '=== Table Sizes ==='
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ====================================================================
-- 9. Record counts (if data exists)
-- ====================================================================
\echo ''
\echo '=== Record Counts ==='
SELECT 'servers' AS table_name, COUNT(*) AS records FROM servers
UNION ALL
SELECT 'application_catalog', COUNT(*) FROM application_catalog
UNION ALL
SELECT 'application_groups', COUNT(*) FROM application_groups
UNION ALL
SELECT 'application_instances', COUNT(*) FROM application_instances
UNION ALL
SELECT 'events', COUNT(*) FROM events
UNION ALL
SELECT 'orchestrator_playbooks', COUNT(*) FROM orchestrator_playbooks
UNION ALL
SELECT 'haproxy_instances', COUNT(*) FROM haproxy_instances
UNION ALL
SELECT 'haproxy_backends', COUNT(*) FROM haproxy_backends
UNION ALL
SELECT 'haproxy_servers', COUNT(*) FROM haproxy_servers
UNION ALL
SELECT 'haproxy_server_status_history', COUNT(*) FROM haproxy_server_status_history
UNION ALL
SELECT 'haproxy_mapping_history', COUNT(*) FROM haproxy_mapping_history
UNION ALL
SELECT 'eureka_servers', COUNT(*) FROM eureka_servers
UNION ALL
SELECT 'eureka_applications', COUNT(*) FROM eureka_applications
UNION ALL
SELECT 'eureka_instances', COUNT(*) FROM eureka_instances
UNION ALL
SELECT 'eureka_instance_status_history', COUNT(*) FROM eureka_instance_status_history
UNION ALL
SELECT 'eureka_instance_actions', COUNT(*) FROM eureka_instance_actions
ORDER BY table_name;

-- ====================================================================
-- 10. Check for missing indexes on foreign keys
-- ====================================================================
\echo ''
\echo '=== Potential Missing Indexes on Foreign Keys ==='
SELECT
    tc.table_name,
    kcu.column_name,
    'Missing index on FK' AS recommendation
FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
  AND NOT EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = tc.table_name
      AND indexdef LIKE '%' || kcu.column_name || '%'
  )
ORDER BY tc.table_name, kcu.column_name;

-- ====================================================================
-- 11. Database connection info
-- ====================================================================
\echo ''
\echo '=== Database Info ==='
SELECT
    current_database() AS database_name,
    current_user AS connected_user,
    version() AS postgresql_version;

-- ====================================================================
-- 12. Summary
-- ====================================================================
\echo ''
\echo '=== Summary ==='
SELECT
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE') AS total_tables,
    (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public') AS total_foreign_keys,
    (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_type = 'UNIQUE' AND table_schema = 'public') AS total_unique_constraints,
    (SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public') AS total_indexes,
    (SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = 'public') AS total_triggers,
    (SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema = 'public') AS total_functions;

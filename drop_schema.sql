-- Drop Schema Script for AC (Application Control) Database
-- PostgreSQL - Drop all tables, functions, and triggers
-- WARNING: This will DELETE ALL DATA!
-- Use with caution!

-- ====================================================================
-- Drop all tables in reverse dependency order
-- ====================================================================

-- Drop Eureka module tables
DROP TABLE IF EXISTS eureka_instance_actions CASCADE;
DROP TABLE IF EXISTS eureka_instance_status_history CASCADE;
DROP TABLE IF EXISTS eureka_instances CASCADE;
DROP TABLE IF EXISTS eureka_applications CASCADE;
DROP TABLE IF EXISTS eureka_servers CASCADE;

-- Drop HAProxy module tables
DROP TABLE IF EXISTS haproxy_mapping_history CASCADE;
DROP TABLE IF EXISTS haproxy_server_status_history CASCADE;
DROP TABLE IF EXISTS haproxy_servers CASCADE;
DROP TABLE IF EXISTS haproxy_backends CASCADE;
DROP TABLE IF EXISTS haproxy_instances CASCADE;

-- Drop Events table
DROP TABLE IF EXISTS events CASCADE;

-- Drop Application Instances table
DROP TABLE IF EXISTS application_instances CASCADE;

-- Drop Application Groups table
DROP TABLE IF EXISTS application_groups CASCADE;

-- Drop Orchestrator Playbooks table
DROP TABLE IF EXISTS orchestrator_playbooks CASCADE;

-- Drop Application Catalog table
DROP TABLE IF EXISTS application_catalog CASCADE;

-- Drop Servers table
DROP TABLE IF EXISTS servers CASCADE;

-- ====================================================================
-- Drop Functions
-- ====================================================================

DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;

-- ====================================================================
-- Verification
-- ====================================================================

-- Show remaining tables (should be empty or system tables only)
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- ====================================================================
-- Optional: Drop sequences (if needed)
-- ====================================================================

/*
DROP SEQUENCE IF EXISTS servers_id_seq CASCADE;
DROP SEQUENCE IF EXISTS application_catalog_id_seq CASCADE;
DROP SEQUENCE IF EXISTS application_groups_id_seq CASCADE;
DROP SEQUENCE IF EXISTS application_instances_id_seq CASCADE;
DROP SEQUENCE IF EXISTS events_id_seq CASCADE;
DROP SEQUENCE IF EXISTS orchestrator_playbooks_id_seq CASCADE;
DROP SEQUENCE IF EXISTS haproxy_instances_id_seq CASCADE;
DROP SEQUENCE IF EXISTS haproxy_backends_id_seq CASCADE;
DROP SEQUENCE IF EXISTS haproxy_servers_id_seq CASCADE;
DROP SEQUENCE IF EXISTS haproxy_server_status_history_id_seq CASCADE;
DROP SEQUENCE IF EXISTS haproxy_mapping_history_id_seq CASCADE;
DROP SEQUENCE IF EXISTS eureka_servers_id_seq CASCADE;
DROP SEQUENCE IF EXISTS eureka_applications_id_seq CASCADE;
DROP SEQUENCE IF EXISTS eureka_instances_id_seq CASCADE;
DROP SEQUENCE IF EXISTS eureka_instance_status_history_id_seq CASCADE;
DROP SEQUENCE IF EXISTS eureka_instance_actions_id_seq CASCADE;
*/

-- Migration script from v1.0 to v2.0
-- Application Control Database Schema Migration
-- Version: 1.0 -> 2.0
-- Date: 2025-11-18
--
-- This script migrates the database from the old schema (v1.0) to the new refactored schema (v2.0)
-- IMPORTANT: Always backup your database before running this migration!
--
-- Usage:
--   psql -U username -d database_name -f migrate_to_v2.sql

-- ====================================================================
-- Pre-migration checks
-- ====================================================================

DO $$
BEGIN
    -- Check if we're already on v2.0 (application_catalog table exists)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'application_catalog') THEN
        RAISE NOTICE 'Database appears to already be on v2.0 schema. Skipping migration.';
        -- You can uncomment the line below to abort the migration
        -- RAISE EXCEPTION 'Migration aborted - database already migrated';
    ELSE
        RAISE NOTICE 'Starting migration from v1.0 to v2.0...';
    END IF;
END $$;

-- ====================================================================
-- Step 1: Create new tables
-- ====================================================================

-- Application Catalog table
CREATE TABLE IF NOT EXISTS application_catalog (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    app_type VARCHAR(32) NOT NULL,
    description TEXT,
    default_playbook_path VARCHAR(255),
    default_artifact_url VARCHAR(255),
    default_artifact_extension VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Application Groups table
CREATE TABLE IF NOT EXISTS application_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    artifact_list_url VARCHAR(512),
    artifact_extension VARCHAR(32),
    update_playbook_path VARCHAR(256),
    batch_grouping_strategy VARCHAR(32) DEFAULT 'by_group' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- Step 2: Backup old applications table (if exists)
-- ====================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'applications') THEN
        -- Create backup table
        CREATE TABLE IF NOT EXISTS applications_backup_v1 AS SELECT * FROM applications;
        RAISE NOTICE 'Backed up old applications table to applications_backup_v1';
    END IF;
END $$;

-- ====================================================================
-- Step 3: Rename applications to application_instances
-- ====================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'applications')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'application_instances') THEN

        -- Rename the table
        ALTER TABLE applications RENAME TO application_instances;
        RAISE NOTICE 'Renamed applications table to application_instances';

        -- Rename indexes
        ALTER INDEX IF EXISTS applications_pkey RENAME TO application_instances_pkey;

    END IF;
END $$;

-- ====================================================================
-- Step 4: Add new columns to application_instances
-- ====================================================================

-- Add catalog_id column
ALTER TABLE application_instances
    ADD COLUMN IF NOT EXISTS catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL;

-- Add group_id column
ALTER TABLE application_instances
    ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES application_groups(id) ON DELETE SET NULL;

-- Rename name column to instance_name (if exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'application_instances' AND column_name = 'name')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name = 'application_instances' AND column_name = 'instance_name') THEN
        ALTER TABLE application_instances RENAME COLUMN name TO instance_name;
        RAISE NOTICE 'Renamed column name to instance_name';
    END IF;
END $$;

-- Add instance_number column
ALTER TABLE application_instances
    ADD COLUMN IF NOT EXISTS instance_number INTEGER DEFAULT 0 NOT NULL;

-- Add Docker-specific fields
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS image VARCHAR(255);
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS tag VARCHAR(64);
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS eureka_registered BOOLEAN DEFAULT FALSE;

-- Add custom settings columns
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS custom_playbook_path VARCHAR(255);
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS custom_artifact_url VARCHAR(512);
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS custom_artifact_extension VARCHAR(32);

-- Add metadata columns
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE application_instances ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- Rename update_playbook_path to custom_playbook_path (if it exists and custom doesn't)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'application_instances' AND column_name = 'update_playbook_path')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name = 'application_instances' AND column_name = 'custom_playbook_path') THEN
        -- Copy data to custom_playbook_path
        UPDATE application_instances SET custom_playbook_path = update_playbook_path WHERE update_playbook_path IS NOT NULL;
        -- Drop old column
        ALTER TABLE application_instances DROP COLUMN update_playbook_path;
        RAISE NOTICE 'Migrated update_playbook_path to custom_playbook_path';
    END IF;
END $$;

-- ====================================================================
-- Step 5: Update events table
-- ====================================================================

-- Rename application_id to instance_id
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'events' AND column_name = 'application_id')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_name = 'events' AND column_name = 'instance_id') THEN
        ALTER TABLE events RENAME COLUMN application_id TO instance_id;
        RAISE NOTICE 'Renamed events.application_id to events.instance_id';
    END IF;
END $$;

-- Update foreign key constraint
DO $$
BEGIN
    -- Drop old constraint if exists
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints
               WHERE table_name = 'events' AND constraint_name LIKE '%application%') THEN
        ALTER TABLE events DROP CONSTRAINT IF EXISTS events_application_id_fkey;
    END IF;

    -- Add new constraint
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                   WHERE table_name = 'events' AND constraint_name = 'events_instance_id_fkey') THEN
        ALTER TABLE events
            ADD CONSTRAINT events_instance_id_fkey
            FOREIGN KEY (instance_id) REFERENCES application_instances(id) ON DELETE CASCADE;
        RAISE NOTICE 'Updated events foreign key constraint';
    END IF;
END $$;

-- ====================================================================
-- Step 6: Update servers table
-- ====================================================================

ALTER TABLE servers ADD COLUMN IF NOT EXISTS is_haproxy_node BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS is_eureka_node BOOLEAN DEFAULT FALSE NOT NULL;

-- ====================================================================
-- Step 7: Create HAProxy tables
-- ====================================================================

CREATE TABLE IF NOT EXISTS haproxy_instances (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    socket_path VARCHAR(256),
    last_sync TIMESTAMP,
    last_sync_status VARCHAR(32) DEFAULT 'unknown',
    last_sync_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_haproxy_instance_per_server UNIQUE(server_id, name)
);

CREATE TABLE IF NOT EXISTS haproxy_backends (
    id SERIAL PRIMARY KEY,
    haproxy_instance_id INTEGER REFERENCES haproxy_instances(id) ON DELETE CASCADE NOT NULL,
    backend_name VARCHAR(128) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,
    CONSTRAINT uq_backend_per_instance UNIQUE(haproxy_instance_id, backend_name)
);

CREATE TABLE IF NOT EXISTS haproxy_servers (
    id SERIAL PRIMARY KEY,
    backend_id INTEGER REFERENCES haproxy_backends(id) ON DELETE CASCADE NOT NULL,
    server_name VARCHAR(128) NOT NULL,
    status VARCHAR(32),
    weight INTEGER DEFAULT 1,
    check_status VARCHAR(64),
    addr VARCHAR(128),
    last_check_duration INTEGER,
    last_state_change INTEGER,
    downtime INTEGER,
    scur INTEGER DEFAULT 0,
    smax INTEGER DEFAULT 0,
    application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    is_manual_mapping BOOLEAN DEFAULT FALSE NOT NULL,
    mapped_by VARCHAR(64),
    mapped_at TIMESTAMP,
    mapping_notes TEXT,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,
    CONSTRAINT uq_server_per_backend UNIQUE(backend_id, server_name)
);

CREATE TABLE IF NOT EXISTS haproxy_server_status_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER REFERENCES haproxy_servers(id) ON DELETE CASCADE NOT NULL,
    old_status VARCHAR(32),
    new_status VARCHAR(32) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS haproxy_mapping_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER REFERENCES haproxy_servers(id) ON DELETE CASCADE NOT NULL,
    old_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    new_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    change_reason VARCHAR(32) NOT NULL,
    mapped_by VARCHAR(64),
    notes TEXT
);

-- ====================================================================
-- Step 8: Create indexes
-- ====================================================================

-- Application Catalog indexes
CREATE INDEX IF NOT EXISTS idx_catalog_name ON application_catalog(name);
CREATE INDEX IF NOT EXISTS idx_catalog_type ON application_catalog(app_type);

-- Application Groups indexes
CREATE INDEX IF NOT EXISTS idx_group_catalog ON application_groups(catalog_id);
CREATE INDEX IF NOT EXISTS idx_group_name ON application_groups(name);

-- Application Instances indexes
CREATE INDEX IF NOT EXISTS idx_instance_catalog ON application_instances(catalog_id);
CREATE INDEX IF NOT EXISTS idx_instance_group ON application_instances(group_id);
CREATE INDEX IF NOT EXISTS idx_instance_server ON application_instances(server_id);
CREATE INDEX IF NOT EXISTS idx_instance_status ON application_instances(status);
CREATE INDEX IF NOT EXISTS idx_instance_deleted ON application_instances(deleted_at);
CREATE INDEX IF NOT EXISTS idx_instance_name ON application_instances(instance_name);
CREATE INDEX IF NOT EXISTS idx_instance_type ON application_instances(app_type);

-- HAProxy indexes
CREATE INDEX IF NOT EXISTS idx_haproxy_instance_server ON haproxy_instances(server_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_instance_active ON haproxy_instances(is_active);
CREATE INDEX IF NOT EXISTS idx_haproxy_backend_instance ON haproxy_backends(haproxy_instance_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_backend_removed ON haproxy_backends(removed_at);
CREATE INDEX IF NOT EXISTS idx_haproxy_server_backend ON haproxy_servers(backend_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_server_application ON haproxy_servers(application_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_server_status ON haproxy_servers(status);
CREATE INDEX IF NOT EXISTS idx_haproxy_server_removed ON haproxy_servers(removed_at);
CREATE INDEX IF NOT EXISTS idx_haproxy_history_server ON haproxy_server_status_history(haproxy_server_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_history_changed_at ON haproxy_server_status_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_server ON haproxy_mapping_history(haproxy_server_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_changed_at ON haproxy_mapping_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_reason ON haproxy_mapping_history(change_reason);

-- ====================================================================
-- Step 9: Add unique constraint to application_instances
-- ====================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                   WHERE table_name = 'application_instances'
                   AND constraint_name = 'unique_instance_per_server') THEN
        ALTER TABLE application_instances
            ADD CONSTRAINT unique_instance_per_server
            UNIQUE(server_id, instance_name, app_type);
        RAISE NOTICE 'Added unique constraint to application_instances';
    END IF;
END $$;

-- ====================================================================
-- Step 10: Create/update triggers for timestamp updates
-- ====================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers
DROP TRIGGER IF EXISTS update_application_catalog_updated_at ON application_catalog;
CREATE TRIGGER update_application_catalog_updated_at BEFORE UPDATE ON application_catalog
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_application_groups_updated_at ON application_groups;
CREATE TRIGGER update_application_groups_updated_at BEFORE UPDATE ON application_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_application_instances_updated_at ON application_instances;
CREATE TRIGGER update_application_instances_updated_at BEFORE UPDATE ON application_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_haproxy_instances_updated_at ON haproxy_instances;
CREATE TRIGGER update_haproxy_instances_updated_at BEFORE UPDATE ON haproxy_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_haproxy_backends_updated_at ON haproxy_backends;
CREATE TRIGGER update_haproxy_backends_updated_at BEFORE UPDATE ON haproxy_backends
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_haproxy_servers_updated_at ON haproxy_servers;
CREATE TRIGGER update_haproxy_servers_updated_at BEFORE UPDATE ON haproxy_servers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ====================================================================
-- Step 11: Populate instance_number from instance_name
-- ====================================================================

-- Parse instance numbers from instance names (e.g., jurws_1 -> 1, mobws_2 -> 2)
UPDATE application_instances
SET instance_number = COALESCE(
    (regexp_match(instance_name, '_(\d+)$'))[1]::INTEGER,
    0
)
WHERE instance_number = 0 OR instance_number IS NULL;

-- ====================================================================
-- Step 12: Create default catalog entries from existing instances
-- ====================================================================

-- This creates catalog entries for unique base names found in instances
INSERT INTO application_catalog (name, app_type, description)
SELECT DISTINCT
    regexp_replace(instance_name, '_\d+$', '') as name,
    app_type,
    'Auto-generated from existing instances' as description
FROM application_instances
WHERE NOT EXISTS (
    SELECT 1 FROM application_catalog
    WHERE name = regexp_replace(application_instances.instance_name, '_\d+$', '')
)
ON CONFLICT (name) DO NOTHING;

-- Link instances to catalog
UPDATE application_instances ai
SET catalog_id = ac.id
FROM application_catalog ac
WHERE ai.catalog_id IS NULL
  AND ac.name = regexp_replace(ai.instance_name, '_\d+$', '')
  AND ac.app_type = ai.app_type;

-- ====================================================================
-- Post-migration verification
-- ====================================================================

DO $$
DECLARE
    catalog_count INTEGER;
    groups_count INTEGER;
    instances_count INTEGER;
    haproxy_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO catalog_count FROM application_catalog;
    SELECT COUNT(*) INTO groups_count FROM application_groups;
    SELECT COUNT(*) INTO instances_count FROM application_instances;
    SELECT COUNT(*) INTO haproxy_count FROM haproxy_instances;

    RAISE NOTICE '=== Migration Summary ===';
    RAISE NOTICE 'Application Catalog entries: %', catalog_count;
    RAISE NOTICE 'Application Groups: %', groups_count;
    RAISE NOTICE 'Application Instances: %', instances_count;
    RAISE NOTICE 'HAProxy Instances: %', haproxy_count;
    RAISE NOTICE 'Migration completed successfully!';
    RAISE NOTICE 'Backup table: applications_backup_v1 (if existed)';
END $$;

-- ====================================================================
-- End of migration
-- ====================================================================

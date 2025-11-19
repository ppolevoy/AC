-- SQL Script for AC (Application Control) Database Schema
-- PostgreSQL Database Schema for Flask Application Management Platform
-- Generated from SQLAlchemy models
-- Version: 2.0 (2025-11-18)
--
-- Changelog:
-- v2.0 (2025-11-18) - DB Refactoring:
--   - Added application_catalog table (application registry)
--   - Added application_groups table (grouping for batch operations)
--   - Renamed applications to application_instances
--   - Added HAProxy integration (haproxy_instances, haproxy_backends, haproxy_servers)
--   - Added HAProxy history tables (status and mapping history)
--   - Added Eureka integration tables
--   - Added image, tag, eureka_registered fields to application_instances
--   - Changed events.application_id to events.instance_id
--   - Added soft delete support (deleted_at, removed_at fields)
-- v1.0 - Initial schema

-- ====================================================================
-- Clean up existing objects (optional - use with caution in production)
-- ====================================================================
-- DROP SCHEMA IF EXISTS public CASCADE;
-- CREATE SCHEMA public;

-- ====================================================================
-- Extensions
-- ====================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ====================================================================
-- Base Tables (No Dependencies)
-- ====================================================================

-- Servers table - physical or virtual hosts
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    ip VARCHAR(15) NOT NULL,
    port INTEGER NOT NULL,
    last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'offline',
    is_haproxy_node BOOLEAN DEFAULT FALSE NOT NULL,
    is_eureka_node BOOLEAN DEFAULT FALSE NOT NULL
);

-- Application Catalog - base applications registry
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

-- Orchestrator Playbooks - Ansible playbooks for orchestration
CREATE TABLE IF NOT EXISTS orchestrator_playbooks (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(512) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    version VARCHAR(32),
    required_params JSONB,
    optional_params JSONB,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    raw_metadata JSONB
);

-- ====================================================================
-- Tables with Foreign Keys to Base Tables
-- ====================================================================

-- Application Groups - grouping for batch operations
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

-- Application Instances - actual app instances on servers
CREATE TABLE IF NOT EXISTS application_instances (
    id SERIAL PRIMARY KEY,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    group_id INTEGER REFERENCES application_groups(id) ON DELETE SET NULL,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE NOT NULL,

    -- Identification
    instance_name VARCHAR(128) NOT NULL,
    instance_number INTEGER DEFAULT 0 NOT NULL,
    app_type VARCHAR(32) NOT NULL,

    -- Status
    status VARCHAR(32) DEFAULT 'unknown',
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Agent data (common)
    path VARCHAR(255),
    log_path VARCHAR(255),
    version VARCHAR(128),
    distr_path VARCHAR(255),

    -- Docker-specific fields
    container_id VARCHAR(128),
    container_name VARCHAR(128),
    compose_project_dir VARCHAR(255),
    image VARCHAR(255),  -- Docker image
    tag VARCHAR(64),  -- Image version/tag
    eureka_registered BOOLEAN DEFAULT FALSE,  -- Eureka registration flag

    -- Eureka-specific fields
    eureka_url VARCHAR(255),

    -- Network parameters
    ip VARCHAR(45),  -- IPv6 support
    port INTEGER,

    -- Process
    pid INTEGER,
    start_time TIMESTAMP,

    -- Customization (overrides group/catalog settings)
    custom_playbook_path VARCHAR(255),
    custom_artifact_url VARCHAR(512),
    custom_artifact_extension VARCHAR(32),

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,  -- Soft delete

    CONSTRAINT unique_instance_per_server UNIQUE(server_id, instance_name, app_type)
);

-- Events - application and server events
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(32) NOT NULL,  -- start, stop, restart, update, connect, disconnect
    description TEXT,
    status VARCHAR(32) DEFAULT 'success',  -- success, failed, pending
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE NOT NULL,
    instance_id INTEGER REFERENCES application_instances(id) ON DELETE CASCADE
);

-- ====================================================================
-- HAProxy Module Tables
-- ====================================================================

-- HAProxy Instances
CREATE TABLE IF NOT EXISTS haproxy_instances (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    socket_path VARCHAR(256),

    -- Sync status
    last_sync TIMESTAMP,
    last_sync_status VARCHAR(32) DEFAULT 'unknown',  -- success/failed/unknown
    last_sync_error TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_haproxy_instance_per_server UNIQUE(server_id, name)
);

-- HAProxy Backends
CREATE TABLE IF NOT EXISTS haproxy_backends (
    id SERIAL PRIMARY KEY,
    haproxy_instance_id INTEGER REFERENCES haproxy_instances(id) ON DELETE CASCADE NOT NULL,
    backend_name VARCHAR(128) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,  -- Soft delete

    CONSTRAINT uq_backend_per_instance UNIQUE(haproxy_instance_id, backend_name)
);

-- HAProxy Servers
CREATE TABLE IF NOT EXISTS haproxy_servers (
    id SERIAL PRIMARY KEY,
    backend_id INTEGER REFERENCES haproxy_backends(id) ON DELETE CASCADE NOT NULL,
    server_name VARCHAR(128) NOT NULL,

    -- Server state in HAProxy
    status VARCHAR(32),  -- UP, DOWN, MAINT, DRAIN
    weight INTEGER DEFAULT 1,
    check_status VARCHAR(64),  -- L4OK, L7OK, etc.
    addr VARCHAR(128),  -- IP:port

    -- Metrics
    last_check_duration INTEGER,  -- milliseconds
    last_state_change INTEGER,  -- seconds since last change
    downtime INTEGER,  -- total downtime in seconds

    -- Connections
    scur INTEGER DEFAULT 0,  -- current sessions
    smax INTEGER DEFAULT 0,  -- max sessions

    -- Link to AC application
    application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,

    -- Manual mapping fields
    is_manual_mapping BOOLEAN DEFAULT FALSE NOT NULL,
    mapped_by VARCHAR(64),
    mapped_at TIMESTAMP,
    mapping_notes TEXT,

    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,  -- Soft delete

    CONSTRAINT uq_server_per_backend UNIQUE(backend_id, server_name)
);

-- HAProxy Server Status History
CREATE TABLE IF NOT EXISTS haproxy_server_status_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER REFERENCES haproxy_servers(id) ON DELETE CASCADE NOT NULL,
    old_status VARCHAR(32),
    new_status VARCHAR(32) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason VARCHAR(64)  -- sync, command, manual
);

-- HAProxy Mapping History
CREATE TABLE IF NOT EXISTS haproxy_mapping_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER REFERENCES haproxy_servers(id) ON DELETE CASCADE NOT NULL,
    old_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    new_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    change_reason VARCHAR(32) NOT NULL,  -- manual, automatic
    mapped_by VARCHAR(64),
    notes TEXT
);

-- ====================================================================
-- Eureka Module Tables
-- ====================================================================

-- Eureka Servers
CREATE TABLE IF NOT EXISTS eureka_servers (
    id SERIAL PRIMARY KEY,
    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE NOT NULL,
    eureka_host VARCHAR(255) NOT NULL,
    eureka_port INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,

    -- Sync status
    last_sync TIMESTAMP,
    last_error TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,  -- Soft delete

    CONSTRAINT uq_eureka_server_per_server UNIQUE(server_id),
    CONSTRAINT uq_eureka_endpoint UNIQUE(eureka_host, eureka_port)
);

-- Eureka Applications
CREATE TABLE IF NOT EXISTS eureka_applications (
    id SERIAL PRIMARY KEY,
    eureka_server_id INTEGER REFERENCES eureka_servers(id) ON DELETE CASCADE NOT NULL,
    app_name VARCHAR(255) NOT NULL,  -- Service name in Eureka

    -- Instance statistics
    instances_count INTEGER DEFAULT 0,
    instances_up INTEGER DEFAULT 0,
    instances_down INTEGER DEFAULT 0,
    instances_paused INTEGER DEFAULT 0,

    last_sync TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_eureka_app_per_server UNIQUE(eureka_server_id, app_name)
);

-- Eureka Instances
CREATE TABLE IF NOT EXISTS eureka_instances (
    id SERIAL PRIMARY KEY,
    eureka_application_id INTEGER REFERENCES eureka_applications(id) ON DELETE CASCADE NOT NULL,

    -- Instance identification
    instance_id VARCHAR(255) NOT NULL UNIQUE,  -- Format: IP:service-name:port
    ip_address VARCHAR(45) NOT NULL,
    port INTEGER NOT NULL,
    service_name VARCHAR(255) NOT NULL,

    -- Instance state
    status VARCHAR(50) DEFAULT 'UNKNOWN' NOT NULL,  -- UP, DOWN, PAUSED, STARTING, OUT_OF_SERVICE
    last_heartbeat TIMESTAMP,

    -- Metadata and URLs
    instance_metadata JSONB,
    health_check_url VARCHAR(512),
    home_page_url VARCHAR(512),
    status_page_url VARCHAR(512),

    -- Link to AC application
    application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,

    -- Manual mapping fields
    is_manual_mapping BOOLEAN DEFAULT FALSE NOT NULL,
    mapped_by VARCHAR(64),
    mapped_at TIMESTAMP,
    mapping_notes TEXT,

    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP  -- Soft delete
);

-- Eureka Instance Status History
CREATE TABLE IF NOT EXISTS eureka_instance_status_history (
    id SERIAL PRIMARY KEY,
    eureka_instance_id INTEGER REFERENCES eureka_instances(id) ON DELETE CASCADE NOT NULL,
    old_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255)  -- system, user, health_check
);

-- Eureka Instance Actions
CREATE TABLE IF NOT EXISTS eureka_instance_actions (
    id SERIAL PRIMARY KEY,
    eureka_instance_id INTEGER REFERENCES eureka_instances(id) ON DELETE CASCADE NOT NULL,
    action_type VARCHAR(50) NOT NULL,  -- health_check, pause, shutdown, log_level_change
    action_params JSONB,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL,  -- pending, in_progress, success, failed
    result TEXT,
    error_message TEXT,
    user_id INTEGER,  -- No FK as User model doesn't exist
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- ====================================================================
-- Indexes
-- ====================================================================

-- Application Catalog indexes
CREATE INDEX idx_catalog_name ON application_catalog(name);
CREATE INDEX idx_catalog_type ON application_catalog(app_type);

-- Application Groups indexes
CREATE INDEX idx_group_catalog ON application_groups(catalog_id);
CREATE INDEX idx_group_name ON application_groups(name);

-- Application Instances indexes
CREATE INDEX idx_instance_catalog ON application_instances(catalog_id);
CREATE INDEX idx_instance_group ON application_instances(group_id);
CREATE INDEX idx_instance_server ON application_instances(server_id);
CREATE INDEX idx_instance_status ON application_instances(status);
CREATE INDEX idx_instance_deleted ON application_instances(deleted_at);
CREATE INDEX idx_instance_name ON application_instances(instance_name);
CREATE INDEX idx_instance_type ON application_instances(app_type);

-- Orchestrator Playbooks index
CREATE INDEX idx_orchestrator_playbook_path ON orchestrator_playbooks(file_path);

-- HAProxy indexes
CREATE INDEX idx_haproxy_instance_server ON haproxy_instances(server_id);
CREATE INDEX idx_haproxy_instance_active ON haproxy_instances(is_active);

CREATE INDEX idx_haproxy_backend_instance ON haproxy_backends(haproxy_instance_id);
CREATE INDEX idx_haproxy_backend_removed ON haproxy_backends(removed_at);

CREATE INDEX idx_haproxy_server_backend ON haproxy_servers(backend_id);
CREATE INDEX idx_haproxy_server_application ON haproxy_servers(application_id);
CREATE INDEX idx_haproxy_server_status ON haproxy_servers(status);
CREATE INDEX idx_haproxy_server_removed ON haproxy_servers(removed_at);

CREATE INDEX idx_haproxy_history_server ON haproxy_server_status_history(haproxy_server_id);
CREATE INDEX idx_haproxy_history_changed_at ON haproxy_server_status_history(changed_at);

CREATE INDEX idx_haproxy_mapping_history_server ON haproxy_mapping_history(haproxy_server_id);
CREATE INDEX idx_haproxy_mapping_history_changed_at ON haproxy_mapping_history(changed_at);
CREATE INDEX idx_haproxy_mapping_history_reason ON haproxy_mapping_history(change_reason);

-- Eureka indexes
CREATE INDEX idx_eureka_server_server ON eureka_servers(server_id);
CREATE INDEX idx_eureka_server_active ON eureka_servers(is_active);
CREATE INDEX idx_eureka_server_removed ON eureka_servers(removed_at);

CREATE INDEX idx_eureka_application_server ON eureka_applications(eureka_server_id);
CREATE INDEX idx_eureka_application_name ON eureka_applications(app_name);

CREATE INDEX idx_eureka_instance_application ON eureka_instances(eureka_application_id);
CREATE INDEX idx_eureka_instance_status ON eureka_instances(status);
CREATE INDEX idx_eureka_instance_instance_id ON eureka_instances(instance_id);
CREATE INDEX idx_eureka_instance_ip ON eureka_instances(ip_address);
CREATE INDEX idx_eureka_instance_ac_app ON eureka_instances(application_id);
CREATE INDEX idx_eureka_instance_removed ON eureka_instances(removed_at);

CREATE INDEX idx_eureka_status_history_instance ON eureka_instance_status_history(eureka_instance_id);
CREATE INDEX idx_eureka_status_history_changed_at ON eureka_instance_status_history(changed_at);

CREATE INDEX idx_eureka_action_instance ON eureka_instance_actions(eureka_instance_id);
CREATE INDEX idx_eureka_action_type ON eureka_instance_actions(action_type);
CREATE INDEX idx_eureka_action_status ON eureka_instance_actions(status);
CREATE INDEX idx_eureka_action_started_at ON eureka_instance_actions(started_at);

-- ====================================================================
-- Functions and Triggers for auto-updating timestamps
-- ====================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for auto-updating updated_at
CREATE TRIGGER update_application_catalog_updated_at BEFORE UPDATE ON application_catalog
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_application_groups_updated_at BEFORE UPDATE ON application_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_application_instances_updated_at BEFORE UPDATE ON application_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_haproxy_instances_updated_at BEFORE UPDATE ON haproxy_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_haproxy_backends_updated_at BEFORE UPDATE ON haproxy_backends
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_haproxy_servers_updated_at BEFORE UPDATE ON haproxy_servers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_eureka_servers_updated_at BEFORE UPDATE ON eureka_servers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_eureka_applications_updated_at BEFORE UPDATE ON eureka_applications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_eureka_instances_updated_at BEFORE UPDATE ON eureka_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ====================================================================
-- Initial Data (Optional - uncomment if needed)
-- ====================================================================

/*
-- Insert default server
INSERT INTO servers (name, ip, port, status)
VALUES ('localhost', '127.0.0.1', 5001, 'online')
ON CONFLICT (name) DO NOTHING;

-- Insert default application types in catalog
INSERT INTO application_catalog (name, app_type, description) VALUES
    ('example-app', 'docker', 'Example Docker Application'),
    ('eureka-service', 'eureka', 'Eureka Service Registry'),
    ('web-app', 'site', 'Web Application')
ON CONFLICT (name) DO NOTHING;

-- Insert default application group
INSERT INTO application_groups (name, description, batch_grouping_strategy) VALUES
    ('default-group', 'Default application group', 'by_group')
ON CONFLICT (name) DO NOTHING;
*/

-- ====================================================================
-- Permissions (adjust as needed)
-- ====================================================================

-- Grant permissions to app user (replace 'appuser' with actual user)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO appuser;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO appuser;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO appuser;

-- ====================================================================
-- Comments for documentation
-- ====================================================================

COMMENT ON TABLE servers IS 'Physical or virtual servers hosting applications';
COMMENT ON TABLE application_catalog IS 'Registry of base applications (templates) - defines default settings for application types';
COMMENT ON TABLE application_groups IS 'Groups for batch application management - defines grouping strategy and artifact settings';
COMMENT ON TABLE application_instances IS 'Actual application instances running on servers - linked to catalog and group for settings inheritance';
COMMENT ON TABLE events IS 'Application and server event log - tracks start/stop/update/restart operations';
COMMENT ON TABLE orchestrator_playbooks IS 'Ansible playbooks for zero-downtime orchestration with HAProxy integration';
COMMENT ON TABLE haproxy_instances IS 'HAProxy load balancer instances - one or more per server';
COMMENT ON TABLE haproxy_backends IS 'HAProxy backend pools - groups of servers for load balancing';
COMMENT ON TABLE haproxy_servers IS 'Servers in HAProxy backends - linked to application instances for automatic mapping';
COMMENT ON TABLE haproxy_server_status_history IS 'History of status changes for HAProxy servers (UP/DOWN/DRAIN/MAINT)';
COMMENT ON TABLE haproxy_mapping_history IS 'History of application mapping changes for HAProxy servers';
COMMENT ON TABLE eureka_servers IS 'Eureka service discovery servers';
COMMENT ON TABLE eureka_applications IS 'Applications registered in Eureka';
COMMENT ON TABLE eureka_instances IS 'Service instances in Eureka registry - can be linked to application instances';
COMMENT ON TABLE eureka_instance_status_history IS 'History of status changes for Eureka instances';
COMMENT ON TABLE eureka_instance_actions IS 'Actions performed on Eureka instances (health checks, pause, shutdown)';

-- Column comments for application_instances
COMMENT ON COLUMN application_instances.catalog_id IS 'Reference to application catalog entry (base application template)';
COMMENT ON COLUMN application_instances.group_id IS 'Reference to application group (for batch operations and shared settings)';
COMMENT ON COLUMN application_instances.instance_name IS 'Full instance name (e.g., jurws_1, mobws_2, provider-api)';
COMMENT ON COLUMN application_instances.instance_number IS 'Instance number parsed from name (0 for standalone apps)';
COMMENT ON COLUMN application_instances.app_type IS 'Application type: docker, eureka, site, service';
COMMENT ON COLUMN application_instances.image IS 'Docker image name (for docker type applications)';
COMMENT ON COLUMN application_instances.tag IS 'Docker image tag/version (for docker type applications)';
COMMENT ON COLUMN application_instances.eureka_registered IS 'Whether this instance is registered in Eureka';
COMMENT ON COLUMN application_instances.custom_playbook_path IS 'Instance-specific playbook path (overrides group and catalog)';
COMMENT ON COLUMN application_instances.custom_artifact_url IS 'Instance-specific artifact URL (overrides group and catalog)';
COMMENT ON COLUMN application_instances.custom_artifact_extension IS 'Instance-specific artifact extension (overrides group and catalog)';
COMMENT ON COLUMN application_instances.deleted_at IS 'Soft delete timestamp - instance is hidden but not removed from DB';

-- Column comments for HAProxy tables
COMMENT ON COLUMN haproxy_servers.application_id IS 'Link to AC application instance - can be set manually or automatically';
COMMENT ON COLUMN haproxy_servers.is_manual_mapping IS 'True if application mapping was set manually (prevents auto-remapping)';
COMMENT ON COLUMN haproxy_servers.mapped_by IS 'Username who performed manual mapping';
COMMENT ON COLUMN haproxy_servers.removed_at IS 'Soft delete timestamp - server no longer exists in HAProxy config';

-- Column comments for application_groups
COMMENT ON COLUMN application_groups.batch_grouping_strategy IS 'Strategy for grouping instances in batch operations: by_group, by_server, by_instance_name, no_grouping';

-- ====================================================================
-- Verification queries
-- ====================================================================

/*
-- Check all tables were created
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Check foreign key constraints
SELECT
    tc.constraint_name,
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name;

-- Check indexes
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
*/

-- ====================================================================
-- End of Schema
-- ====================================================================
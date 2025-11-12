-- Database Schema for FAppControl
-- PostgreSQL Database Creation Script
-- Generated from SQLAlchemy Models

-- Drop existing tables if needed (be careful with this in production!)
-- Uncomment the following lines if you want to recreate the schema from scratch
/*
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS application_instances CASCADE;
DROP TABLE IF EXISTS applications CASCADE;
DROP TABLE IF EXISTS application_groups CASCADE;
DROP TABLE IF EXISTS servers CASCADE;
DROP TABLE IF EXISTS orchestrator_playbooks CASCADE;
*/

-- Create servers table
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    ip VARCHAR(15) NOT NULL,
    port INTEGER NOT NULL,
    last_check TIMESTAMP WITHOUT TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    status VARCHAR(20) DEFAULT 'offline'
);

-- Create application_groups table
CREATE TABLE IF NOT EXISTS application_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT,
    artifact_list_url VARCHAR(512),
    artifact_extension VARCHAR(32),
    update_playbook_path VARCHAR(256),
    batch_grouping_strategy VARCHAR(32) NOT NULL DEFAULT 'by_group',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- Create index on application_groups.name
CREATE INDEX IF NOT EXISTS idx_application_groups_name ON application_groups(name);

-- Create applications table
CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    path VARCHAR(256),
    log_path VARCHAR(256),
    version VARCHAR(64),
    distr_path VARCHAR(256),
    container_id VARCHAR(64),
    container_name VARCHAR(64),
    eureka_url VARCHAR(256),
    compose_project_dir VARCHAR(256),
    ip VARCHAR(15),
    port INTEGER,
    status VARCHAR(20) DEFAULT 'offline',
    start_time TIMESTAMP WITHOUT TIME ZONE,
    app_type VARCHAR(32), -- docker, eureka, site, service
    update_playbook_path VARCHAR(256),
    instance_number INTEGER NOT NULL DEFAULT 0,
    server_id INTEGER NOT NULL,
    group_id INTEGER,
    CONSTRAINT fk_applications_server
        FOREIGN KEY (server_id)
        REFERENCES servers(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_applications_group
        FOREIGN KEY (group_id)
        REFERENCES application_groups(id)
        ON DELETE SET NULL
);

-- Create indexes on applications
CREATE INDEX IF NOT EXISTS idx_app_group_instance ON applications(group_id, instance_number);
CREATE INDEX IF NOT EXISTS idx_app_server_name ON applications(server_id, name);

-- Create application_instances table
CREATE TABLE IF NOT EXISTS application_instances (
    id SERIAL PRIMARY KEY,
    original_name VARCHAR(128) NOT NULL,
    instance_number INTEGER NOT NULL DEFAULT 0,
    group_id INTEGER NOT NULL,
    application_id INTEGER NOT NULL UNIQUE,
    group_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    custom_artifact_list_url VARCHAR(512),
    custom_artifact_extension VARCHAR(32),
    custom_playbook_path VARCHAR(256),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    CONSTRAINT fk_app_instances_group
        FOREIGN KEY (group_id)
        REFERENCES application_groups(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_app_instances_application
        FOREIGN KEY (application_id)
        REFERENCES applications(id)
        ON DELETE CASCADE,
    CONSTRAINT uq_original_name_app
        UNIQUE (original_name, application_id)
);

-- Create indexes on application_instances
CREATE INDEX IF NOT EXISTS idx_group_instance ON application_instances(group_id, instance_number);
CREATE INDEX IF NOT EXISTS idx_instance_resolved ON application_instances(group_resolved);
CREATE INDEX IF NOT EXISTS idx_instance_original_name ON application_instances(original_name);

-- Create events table
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    event_type VARCHAR(32) NOT NULL, -- start, stop, restart, update
    description TEXT,
    status VARCHAR(32) DEFAULT 'success', -- success, failed, pending
    server_id INTEGER NOT NULL,
    application_id INTEGER,
    CONSTRAINT fk_events_server
        FOREIGN KEY (server_id)
        REFERENCES servers(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_events_application
        FOREIGN KEY (application_id)
        REFERENCES applications(id)
        ON DELETE CASCADE
);

-- Create orchestrator_playbooks table
CREATE TABLE IF NOT EXISTS orchestrator_playbooks (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(512) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    version VARCHAR(32),
    required_params JSONB,  -- stores {param_name: description}
    optional_params JSONB,  -- stores {param_name: {description, default}}
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_scanned TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    raw_metadata JSONB      -- stores raw metadata for debugging
);

-- Create index on orchestrator_playbooks.file_path
CREATE INDEX IF NOT EXISTS idx_orchestrator_playbooks_file_path ON orchestrator_playbooks(file_path);

-- Add check constraints for batch_grouping_strategy
ALTER TABLE application_groups
ADD CONSTRAINT chk_batch_grouping_strategy
CHECK (batch_grouping_strategy IN ('by_group', 'by_server', 'by_instance_name', 'no_grouping'));

-- Add check constraints for event_type
ALTER TABLE events
ADD CONSTRAINT chk_event_type
CHECK (event_type IN ('start', 'stop', 'restart', 'update'));

-- Add check constraints for event status
ALTER TABLE events
ADD CONSTRAINT chk_event_status
CHECK (status IN ('success', 'failed', 'pending'));

-- Add check constraints for app_type
ALTER TABLE applications
ADD CONSTRAINT chk_app_type
CHECK (app_type IS NULL OR app_type IN ('docker', 'eureka', 'site', 'service'));

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP AT TIME ZONE 'UTC';
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for auto-updating updated_at field
CREATE TRIGGER update_application_groups_updated_at
    BEFORE UPDATE ON application_groups
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_application_instances_updated_at
    BEFORE UPDATE ON application_instances
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust as needed for your environment)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_app_user;

-- Create some useful views for monitoring and reporting

-- View: Application details with group and server info
CREATE OR REPLACE VIEW v_application_details AS
SELECT
    a.id,
    a.name AS application_name,
    a.status,
    a.app_type,
    a.instance_number,
    s.name AS server_name,
    s.ip AS server_ip,
    s.port AS server_port,
    ag.name AS group_name,
    ag.batch_grouping_strategy,
    ai.original_name,
    ai.group_resolved,
    ai.custom_playbook_path,
    a.start_time,
    a.version
FROM applications a
JOIN servers s ON a.server_id = s.id
LEFT JOIN application_groups ag ON a.group_id = ag.id
LEFT JOIN application_instances ai ON a.id = ai.application_id
ORDER BY s.name, ag.name, a.instance_number;

-- View: Group statistics
CREATE OR REPLACE VIEW v_group_statistics AS
SELECT
    ag.id,
    ag.name AS group_name,
    ag.batch_grouping_strategy,
    COUNT(DISTINCT ai.id) AS instance_count,
    COUNT(DISTINCT a.server_id) AS server_count,
    COUNT(CASE WHEN ai.custom_playbook_path IS NOT NULL
               OR ai.custom_artifact_list_url IS NOT NULL
               OR ai.custom_artifact_extension IS NOT NULL
          THEN 1 END) AS custom_instances_count,
    ag.created_at,
    ag.updated_at
FROM application_groups ag
LEFT JOIN application_instances ai ON ag.id = ai.group_id
LEFT JOIN applications a ON ai.application_id = a.id
GROUP BY ag.id, ag.name, ag.batch_grouping_strategy, ag.created_at, ag.updated_at
ORDER BY ag.name;

-- View: Server load and application distribution
CREATE OR REPLACE VIEW v_server_load AS
SELECT
    s.id,
    s.name AS server_name,
    s.ip,
    s.port,
    s.status AS server_status,
    s.last_check,
    COUNT(DISTINCT a.id) AS application_count,
    COUNT(DISTINCT a.group_id) AS group_count,
    COUNT(CASE WHEN a.status = 'online' THEN 1 END) AS online_apps,
    COUNT(CASE WHEN a.status = 'offline' THEN 1 END) AS offline_apps,
    STRING_AGG(DISTINCT a.app_type, ', ') AS app_types
FROM servers s
LEFT JOIN applications a ON s.id = a.server_id
GROUP BY s.id, s.name, s.ip, s.port, s.status, s.last_check
ORDER BY s.name;

-- View: Recent events with details
CREATE OR REPLACE VIEW v_recent_events AS
SELECT
    e.id,
    e.timestamp,
    e.event_type,
    e.status,
    e.description,
    s.name AS server_name,
    s.ip AS server_ip,
    a.name AS application_name,
    ag.name AS group_name
FROM events e
JOIN servers s ON e.server_id = s.id
LEFT JOIN applications a ON e.application_id = a.id
LEFT JOIN application_groups ag ON a.group_id = ag.id
ORDER BY e.timestamp DESC
LIMIT 100;

-- Add comments to tables and columns for documentation
COMMENT ON TABLE servers IS 'Stores information about servers/hosts where applications are deployed';
COMMENT ON TABLE applications IS 'Stores individual application instances with their configuration and status';
COMMENT ON TABLE application_groups IS 'Groups of related application instances with shared configuration';
COMMENT ON TABLE application_instances IS 'Links applications to groups and stores instance-specific overrides';
COMMENT ON TABLE events IS 'Audit log of application and server events';
COMMENT ON TABLE orchestrator_playbooks IS 'Metadata for Ansible orchestrator playbooks used for deployments';

COMMENT ON COLUMN applications.app_type IS 'Type of application: docker, eureka, site, or service';
COMMENT ON COLUMN application_groups.batch_grouping_strategy IS 'Strategy for grouping batch updates: by_group, by_server, by_instance_name, no_grouping';
COMMENT ON COLUMN application_instances.group_resolved IS 'Flag indicating whether the group has been determined from the application name';
COMMENT ON COLUMN orchestrator_playbooks.required_params IS 'JSON object with required parameters: {param_name: description}';
COMMENT ON COLUMN orchestrator_playbooks.optional_params IS 'JSON object with optional parameters: {param_name: {description, default}}';

-- Sample data for testing (uncomment to insert test data)
/*
-- Insert test servers
INSERT INTO servers (name, ip, port) VALUES
    ('app-server-01', '192.168.1.10', 22),
    ('app-server-02', '192.168.1.11', 22),
    ('db-server-01', '192.168.1.20', 22);

-- Insert test application groups
INSERT INTO application_groups (name, description, batch_grouping_strategy) VALUES
    ('web-frontend', 'Frontend web applications', 'by_group'),
    ('api-backend', 'Backend API services', 'by_server'),
    ('batch-jobs', 'Batch processing jobs', 'no_grouping');

-- Insert test applications
INSERT INTO applications (name, server_id, group_id, app_type, status) VALUES
    ('web-frontend-01', 1, 1, 'docker', 'online'),
    ('web-frontend-02', 2, 1, 'docker', 'online'),
    ('api-backend-01', 1, 2, 'service', 'offline'),
    ('api-backend-02', 2, 2, 'service', 'online');
*/

-- Performance optimization: Analyze tables after initial data load
-- ANALYZE servers;
-- ANALYZE applications;
-- ANALYZE application_groups;
-- ANALYZE application_instances;
-- ANALYZE events;
-- ANALYZE orchestrator_playbooks;
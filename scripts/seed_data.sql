-- Seed Data Script for AC (Application Control) Database
-- PostgreSQL - Insert initial demo data
-- This script populates the database with sample data for testing

-- ====================================================================
-- Servers
-- ====================================================================

INSERT INTO servers (name, ip, port, status, is_haproxy_node, is_eureka_node) VALUES
    ('server01', '192.168.1.10', 5001, 'online', FALSE, FALSE),
    ('server02', '192.168.1.11', 5001, 'online', FALSE, FALSE),
    ('server03', '192.168.1.12', 5001, 'online', TRUE, FALSE),
    ('eureka-node', '192.168.1.20', 5001, 'online', FALSE, TRUE),
    ('haproxy-lb', '192.168.1.30', 5001, 'online', TRUE, FALSE)
ON CONFLICT (name) DO NOTHING;

-- ====================================================================
-- Application Catalog
-- ====================================================================

INSERT INTO application_catalog (name, app_type, description, default_playbook_path, default_artifact_url, default_artifact_extension) VALUES
    ('web-service', 'docker', 'Web Service Application', '/etc/ansible/playbooks/deploy-docker.yml', 'http://nexus.example.com/repository/maven-releases/com/example/web-service', 'jar'),
    ('api-gateway', 'docker', 'API Gateway Service', '/etc/ansible/playbooks/deploy-docker.yml', 'http://nexus.example.com/repository/maven-releases/com/example/api-gateway', 'jar'),
    ('eureka-service', 'eureka', 'Service Discovery Server', '/etc/ansible/playbooks/deploy-eureka.yml', NULL, NULL),
    ('frontend-app', 'site', 'Frontend Web Application', '/etc/ansible/playbooks/deploy-site.yml', 'http://nexus.example.com/repository/npm-releases/frontend-app', 'tar.gz'),
    ('background-worker', 'service', 'Background Processing Worker', '/etc/ansible/playbooks/deploy-service.yml', NULL, NULL)
ON CONFLICT (name) DO NOTHING;

-- ====================================================================
-- Application Groups
-- ====================================================================

INSERT INTO application_groups (name, description, catalog_id, artifact_list_url, artifact_extension, update_playbook_path, batch_grouping_strategy) VALUES
    ('web-services-prod', 'Production Web Services',
        (SELECT id FROM application_catalog WHERE name = 'web-service'),
        'http://nexus.example.com/repository/maven-releases/com/example/web-service/maven-metadata.xml',
        'jar',
        '/etc/ansible/playbooks/deploy-docker.yml',
        'by_group'),

    ('api-gateway-prod', 'Production API Gateways',
        (SELECT id FROM application_catalog WHERE name = 'api-gateway'),
        'http://nexus.example.com/repository/maven-releases/com/example/api-gateway/maven-metadata.xml',
        'jar',
        '/etc/ansible/playbooks/deploy-docker.yml',
        'by_server'),

    ('frontend-cluster', 'Frontend Application Cluster',
        (SELECT id FROM application_catalog WHERE name = 'frontend-app'),
        'http://nexus.example.com/repository/npm-releases/frontend-app/versions.json',
        'tar.gz',
        '/etc/ansible/playbooks/deploy-site.yml',
        'by_instance_name')
ON CONFLICT (name) DO NOTHING;

-- ====================================================================
-- Application Instances
-- ====================================================================

-- Web service instances
INSERT INTO application_instances (
    catalog_id, group_id, server_id,
    instance_name, instance_number, app_type,
    status, path, version,
    container_name, ip, port
) VALUES
    ((SELECT id FROM application_catalog WHERE name = 'web-service'),
     (SELECT id FROM application_groups WHERE name = 'web-services-prod'),
     (SELECT id FROM servers WHERE name = 'server01'),
     'web-service_1', 1, 'docker',
     'online', '/opt/apps/web-service_1', '1.2.3',
     'web-service_1', '192.168.1.10', 8080),

    ((SELECT id FROM application_catalog WHERE name = 'web-service'),
     (SELECT id FROM application_groups WHERE name = 'web-services-prod'),
     (SELECT id FROM servers WHERE name = 'server02'),
     'web-service_2', 2, 'docker',
     'online', '/opt/apps/web-service_2', '1.2.3',
     'web-service_2', '192.168.1.11', 8080),

    ((SELECT id FROM application_catalog WHERE name = 'api-gateway'),
     (SELECT id FROM application_groups WHERE name = 'api-gateway-prod'),
     (SELECT id FROM servers WHERE name = 'server01'),
     'api-gateway_1', 1, 'docker',
     'online', '/opt/apps/api-gateway_1', '2.1.0',
     'api-gateway_1', '192.168.1.10', 8081),

    ((SELECT id FROM application_catalog WHERE name = 'frontend-app'),
     (SELECT id FROM application_groups WHERE name = 'frontend-cluster'),
     (SELECT id FROM servers WHERE name = 'server03'),
     'frontend-app_1', 1, 'site',
     'online', '/var/www/frontend-app', '3.0.5',
     NULL, '192.168.1.12', 80)
ON CONFLICT (server_id, instance_name, app_type) DO NOTHING;

-- ====================================================================
-- Orchestrator Playbooks
-- ====================================================================

INSERT INTO orchestrator_playbooks (
    file_path, name, description, version,
    required_params, optional_params, is_active
) VALUES
    ('/etc/ansible/orchestrators/rolling-update-orchestrator.yml',
     'Rolling Update Orchestrator',
     'Zero-downtime rolling update with HAProxy integration',
     '1.0',
     '{"apps": "Comma-separated list of app instances (hostname::appname format)", "distr_url": "URL to artifact for download"}',
     '{"drain_delay": {"description": "Seconds to wait after draining", "default": "30"}, "wait_after_update": {"description": "Seconds to wait after update", "default": "60"}}',
     TRUE),

    ('/etc/ansible/orchestrators/blue-green-orchestrator.yml',
     'Blue-Green Deployment Orchestrator',
     'Blue-green deployment strategy with instant switchover',
     '1.0',
     '{"apps": "Comma-separated list of app instances", "distr_url": "URL to artifact"}',
     '{"health_check_timeout": {"description": "Health check timeout in seconds", "default": "120"}}',
     TRUE)
ON CONFLICT (file_path) DO NOTHING;

-- ====================================================================
-- HAProxy Configuration
-- ====================================================================

-- HAProxy instance
INSERT INTO haproxy_instances (name, server_id, is_active, socket_path, last_sync_status) VALUES
    ('default', (SELECT id FROM servers WHERE name = 'haproxy-lb'), TRUE, 'unix:/var/run/haproxy.sock', 'success')
ON CONFLICT (server_id, name) DO NOTHING;

-- HAProxy backends
INSERT INTO haproxy_backends (haproxy_instance_id, backend_name) VALUES
    ((SELECT id FROM haproxy_instances WHERE name = 'default'), 'web-service-backend'),
    ((SELECT id FROM haproxy_instances WHERE name = 'default'), 'api-gateway-backend')
ON CONFLICT (haproxy_instance_id, backend_name) DO NOTHING;

-- HAProxy servers (members of backends)
INSERT INTO haproxy_servers (
    backend_id, server_name, status, addr, weight,
    application_id, is_manual_mapping
) VALUES
    ((SELECT id FROM haproxy_backends WHERE backend_name = 'web-service-backend'),
     'web-service-1', 'UP', '192.168.1.10:8080', 100,
     (SELECT id FROM application_instances WHERE instance_name = 'web-service_1' AND server_id = (SELECT id FROM servers WHERE name = 'server01')),
     FALSE),

    ((SELECT id FROM haproxy_backends WHERE backend_name = 'web-service-backend'),
     'web-service-2', 'UP', '192.168.1.11:8080', 100,
     (SELECT id FROM application_instances WHERE instance_name = 'web-service_2' AND server_id = (SELECT id FROM servers WHERE name = 'server02')),
     FALSE),

    ((SELECT id FROM haproxy_backends WHERE backend_name = 'api-gateway-backend'),
     'api-gateway-1', 'UP', '192.168.1.10:8081', 100,
     (SELECT id FROM application_instances WHERE instance_name = 'api-gateway_1' AND server_id = (SELECT id FROM servers WHERE name = 'server01')),
     FALSE)
ON CONFLICT (backend_id, server_name) DO NOTHING;

-- ====================================================================
-- Eureka Configuration
-- ====================================================================

-- Eureka server
INSERT INTO eureka_servers (server_id, eureka_host, eureka_port, is_active) VALUES
    ((SELECT id FROM servers WHERE name = 'eureka-node'), '192.168.1.20', 8761, TRUE)
ON CONFLICT (server_id) DO NOTHING;

-- Eureka applications
INSERT INTO eureka_applications (
    eureka_server_id, app_name,
    instances_count, instances_up, instances_down
) VALUES
    ((SELECT id FROM eureka_servers WHERE eureka_host = '192.168.1.20'),
     'WEB-SERVICE', 2, 2, 0),
    ((SELECT id FROM eureka_servers WHERE eureka_host = '192.168.1.20'),
     'API-GATEWAY', 1, 1, 0)
ON CONFLICT (eureka_server_id, app_name) DO NOTHING;

-- Eureka instances
INSERT INTO eureka_instances (
    eureka_application_id, instance_id,
    ip_address, port, service_name, status,
    application_id, is_manual_mapping
) VALUES
    ((SELECT id FROM eureka_applications WHERE app_name = 'WEB-SERVICE'),
     '192.168.1.10:web-service:8080',
     '192.168.1.10', 8080, 'web-service', 'UP',
     (SELECT id FROM application_instances WHERE instance_name = 'web-service_1' AND server_id = (SELECT id FROM servers WHERE name = 'server01')),
     FALSE),

    ((SELECT id FROM eureka_applications WHERE app_name = 'WEB-SERVICE'),
     '192.168.1.11:web-service:8080',
     '192.168.1.11', 8080, 'web-service', 'UP',
     (SELECT id FROM application_instances WHERE instance_name = 'web-service_2' AND server_id = (SELECT id FROM servers WHERE name = 'server02')),
     FALSE),

    ((SELECT id FROM eureka_applications WHERE app_name = 'API-GATEWAY'),
     '192.168.1.10:api-gateway:8081',
     '192.168.1.10', 8081, 'api-gateway', 'UP',
     (SELECT id FROM application_instances WHERE instance_name = 'api-gateway_1' AND server_id = (SELECT id FROM servers WHERE name = 'server01')),
     FALSE)
ON CONFLICT (instance_id) DO NOTHING;

-- ====================================================================
-- Events (Sample event log)
-- ====================================================================

INSERT INTO events (timestamp, event_type, description, status, server_id, instance_id) VALUES
    (CURRENT_TIMESTAMP - INTERVAL '1 hour', 'start', 'Application started successfully', 'success',
     (SELECT id FROM servers WHERE name = 'server01'),
     (SELECT id FROM application_instances WHERE instance_name = 'web-service_1' AND server_id = (SELECT id FROM servers WHERE name = 'server01'))),

    (CURRENT_TIMESTAMP - INTERVAL '50 minutes', 'update', 'Application updated to version 1.2.3', 'success',
     (SELECT id FROM servers WHERE name = 'server01'),
     (SELECT id FROM application_instances WHERE instance_name = 'web-service_1' AND server_id = (SELECT id FROM servers WHERE name = 'server01'))),

    (CURRENT_TIMESTAMP - INTERVAL '30 minutes', 'restart', 'Application restarted', 'success',
     (SELECT id FROM servers WHERE name = 'server02'),
     (SELECT id FROM application_instances WHERE instance_name = 'web-service_2' AND server_id = (SELECT id FROM servers WHERE name = 'server02'))),

    (CURRENT_TIMESTAMP - INTERVAL '10 minutes', 'connect', 'Server connected', 'success',
     (SELECT id FROM servers WHERE name = 'server03'),
     NULL);

-- ====================================================================
-- Verification Queries
-- ====================================================================

-- Count records in each table
SELECT 'servers' AS table_name, COUNT(*) AS record_count FROM servers
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
SELECT 'eureka_servers', COUNT(*) FROM eureka_servers
UNION ALL
SELECT 'eureka_applications', COUNT(*) FROM eureka_applications
UNION ALL
SELECT 'eureka_instances', COUNT(*) FROM eureka_instances
ORDER BY table_name;

-- ====================================================================
-- End of Seed Data
-- ====================================================================

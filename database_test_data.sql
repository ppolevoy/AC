-- ============================================================================
-- Test Data Script
-- ============================================================================
-- Скрипт для заполнения базы данных тестовыми данными
-- Используется для тестирования и разработки
-- ============================================================================

\echo '=== ЗАПОЛНЕНИЕ ТЕСТОВЫМИ ДАННЫМИ ==='

-- ============================================================================
-- ОЧИСТКА СУЩЕСТВУЮЩИХ ДАННЫХ (опционально)
-- ============================================================================

-- Раскомментируйте если нужно очистить данные перед заполнением
-- TRUNCATE TABLE application_version_history, tasks, tag_history, application_instance_tags,
--   application_group_tags, application_mapping_history, application_mappings,
--   eureka_instance_actions, eureka_instance_status_history, eureka_instances,
--   eureka_applications, eureka_servers, haproxy_mapping_history,
--   haproxy_server_status_history, haproxy_servers, haproxy_backends,
--   haproxy_instances, events, application_instances, application_groups,
--   application_catalog, tags, orchestrator_playbooks, mailing_groups, servers
--   RESTART IDENTITY CASCADE;

-- ============================================================================
-- СЕРВЕРЫ
-- ============================================================================

INSERT INTO servers (name, ip, port, status, is_haproxy_node, is_eureka_node) VALUES
    ('fdmz01', '192.168.1.101', 5555, 'online', true, false),
    ('fdmz02', '192.168.1.102', 5555, 'online', true, false),
    ('fdmz03', '192.168.1.103', 5555, 'online', false, true),
    ('fdmz04', '192.168.1.104', 5555, 'offline', false, false),
    ('dev-server-01', '192.168.2.10', 5555, 'online', false, false)
ON CONFLICT (name) DO NOTHING;

\echo '✓ Серверы добавлены'

-- ============================================================================
-- СПРАВОЧНИК ПРИЛОЖЕНИЙ
-- ============================================================================

INSERT INTO application_catalog (name, app_type, description, default_playbook_path, default_artifact_url, default_artifact_extension) VALUES
    ('jurws', 'eureka', 'Юридический веб-сервис', '/etc/ansible/playbooks/update-eureka.yml', 'http://nexus.local/jurws', 'war'),
    ('mobws', 'docker', 'Мобильный веб-сервис', '/etc/ansible/playbooks/update-docker.yml', 'http://nexus.local/mobws', 'war'),
    ('nginx', 'site', 'Nginx веб-сервер', '/etc/ansible/playbooks/update-nginx.yml', NULL, NULL),
    ('postgres', 'service', 'PostgreSQL Database', '/etc/ansible/playbooks/update-postgres.yml', NULL, NULL),
    ('redis', 'docker', 'Redis Cache Service', '/etc/ansible/playbooks/update-docker.yml', 'docker.io/redis', NULL)
ON CONFLICT (name) DO NOTHING;

\echo '✓ Справочник приложений заполнен'

-- ============================================================================
-- ГРУППЫ ПРИЛОЖЕНИЙ
-- ============================================================================

INSERT INTO application_groups (name, description, catalog_id, artifact_list_url, artifact_extension, update_playbook_path, batch_grouping_strategy) VALUES
    ('jurws-prod', 'Юридические сервисы Production', (SELECT id FROM application_catalog WHERE name = 'jurws'), 'http://nexus.local/api/jurws/list', 'war', '/etc/ansible/playbooks/update-eureka.yml', 'by_group'),
    ('mobws-prod', 'Мобильные сервисы Production', (SELECT id FROM application_catalog WHERE name = 'mobws'), 'http://nexus.local/api/mobws/list', 'war', '/etc/ansible/playbooks/update-docker.yml', 'by_server'),
    ('infrastructure', 'Инфраструктурные сервисы', NULL, NULL, NULL, '/etc/ansible/playbooks/update-infra.yml', 'no_grouping')
ON CONFLICT (name) DO NOTHING;

\echo '✓ Группы приложений добавлены'

-- ============================================================================
-- ТЕГИ
-- ============================================================================

INSERT INTO tags (name, display_name, description, icon, tag_type, css_class, border_color, text_color, is_system, show_in_table) VALUES
    ('production', 'Production', 'Продакшн окружение', '🏭', 'env', 'tag-production', '#dc3545', '#ffffff', true, true),
    ('development', 'Development', 'Разработка', '🔧', 'env', 'tag-development', '#17a2b8', '#ffffff', false, true),
    ('critical', 'Critical', 'Критичное приложение', '⚠️', 'status', 'tag-critical', '#ffc107', '#000000', false, true),
    ('deprecated', 'Deprecated', 'Устаревшее приложение', '🗑️', 'status', 'tag-deprecated', '#6c757d', '#ffffff', false, false),
    ('new', 'New', 'Новое приложение', '✨', 'status', 'tag-new', '#28a745', '#ffffff', false, false),
    ('monitored', 'Monitored', 'Мониторится', '👁️', 'system', 'tag-monitored', '#007bff', '#ffffff', true, false)
ON CONFLICT (name) DO NOTHING;

\echo '✓ Теги добавлены'

-- ============================================================================
-- ЭКЗЕМПЛЯРЫ ПРИЛОЖЕНИЙ
-- ============================================================================

-- jurws приложения на fdmz01
INSERT INTO application_instances (
    catalog_id, group_id, server_id, instance_name, instance_number, app_type,
    status, path, version, port, ip
) VALUES
    (
        (SELECT id FROM application_catalog WHERE name = 'jurws'),
        (SELECT id FROM application_groups WHERE name = 'jurws-prod'),
        (SELECT id FROM servers WHERE name = 'fdmz01'),
        'jurws_1', 1, 'eureka', 'online',
        '/opt/apps/jurws_1', '2.5.3', 8081, '192.168.1.101'
    ),
    (
        (SELECT id FROM application_catalog WHERE name = 'jurws'),
        (SELECT id FROM application_groups WHERE name = 'jurws-prod'),
        (SELECT id FROM servers WHERE name = 'fdmz01'),
        'jurws_2', 2, 'eureka', 'online',
        '/opt/apps/jurws_2', '2.5.3', 8082, '192.168.1.101'
    )
ON CONFLICT (server_id, instance_name, app_type) DO NOTHING;

-- mobws приложения на fdmz02
INSERT INTO application_instances (
    catalog_id, group_id, server_id, instance_name, instance_number, app_type,
    status, container_name, image, tag, port, ip
) VALUES
    (
        (SELECT id FROM application_catalog WHERE name = 'mobws'),
        (SELECT id FROM application_groups WHERE name = 'mobws-prod'),
        (SELECT id FROM servers WHERE name = 'fdmz02'),
        'mobws_1', 1, 'docker', 'online',
        'mobws_1_container', 'nexus.local/mobws', 'v3.1.0', 9091, '192.168.1.102'
    ),
    (
        (SELECT id FROM application_catalog WHERE name = 'mobws'),
        (SELECT id FROM application_groups WHERE name = 'mobws-prod'),
        (SELECT id FROM servers WHERE name = 'fdmz02'),
        'mobws_2', 2, 'docker', 'online',
        'mobws_2_container', 'nexus.local/mobws', 'v3.1.0', 9092, '192.168.1.102'
    )
ON CONFLICT (server_id, instance_name, app_type) DO NOTHING;

-- nginx на dev-server-01
INSERT INTO application_instances (
    catalog_id, group_id, server_id, instance_name, instance_number, app_type,
    status, path, version, port
) VALUES
    (
        (SELECT id FROM application_catalog WHERE name = 'nginx'),
        (SELECT id FROM application_groups WHERE name = 'infrastructure'),
        (SELECT id FROM servers WHERE name = 'dev-server-01'),
        'nginx', 0, 'site', 'online',
        '/etc/nginx', '1.21.6', 80
    )
ON CONFLICT (server_id, instance_name, app_type) DO NOTHING;

\echo '✓ Экземпляры приложений добавлены'

-- ============================================================================
-- СВЯЗИ ПРИЛОЖЕНИЙ С ТЕГАМИ
-- ============================================================================

-- Помечаем jurws как production и critical
INSERT INTO application_instance_tags (application_id, tag_id, assigned_by)
SELECT
    ai.id,
    t.id,
    'admin'
FROM application_instances ai
CROSS JOIN tags t
WHERE ai.instance_name LIKE 'jurws_%'
  AND t.name IN ('production', 'critical')
ON CONFLICT (application_id, tag_id) DO NOTHING;

-- Помечаем mobws как production
INSERT INTO application_instance_tags (application_id, tag_id, assigned_by)
SELECT
    ai.id,
    t.id,
    'admin'
FROM application_instances ai
CROSS JOIN tags t
WHERE ai.instance_name LIKE 'mobws_%'
  AND t.name = 'production'
ON CONFLICT (application_id, tag_id) DO NOTHING;

-- Помечаем nginx как development
INSERT INTO application_instance_tags (application_id, tag_id, assigned_by)
SELECT
    ai.id,
    t.id,
    'admin'
FROM application_instances ai
CROSS JOIN tags t
WHERE ai.instance_name = 'nginx'
  AND t.name = 'development'
ON CONFLICT (application_id, tag_id) DO NOTHING;

-- Помечаем группу jurws-prod тегом production
INSERT INTO application_group_tags (group_id, tag_id, assigned_by)
SELECT
    ag.id,
    t.id,
    'admin'
FROM application_groups ag
CROSS JOIN tags t
WHERE ag.name = 'jurws-prod'
  AND t.name = 'production'
ON CONFLICT (group_id, tag_id) DO NOTHING;

\echo '✓ Теги назначены приложениям и группам'

-- ============================================================================
-- СОБЫТИЯ
-- ============================================================================

INSERT INTO events (timestamp, event_type, description, status, server_id, instance_id)
SELECT
    NOW() - INTERVAL '1 hour',
    'start',
    'Приложение успешно запущено',
    'success',
    server_id,
    id
FROM application_instances
WHERE instance_name LIKE 'jurws_%'
LIMIT 2;

INSERT INTO events (timestamp, event_type, description, status, server_id, instance_id)
SELECT
    NOW() - INTERVAL '30 minutes',
    'update',
    'Обновление до версии 2.5.3',
    'success',
    server_id,
    id
FROM application_instances
WHERE instance_name = 'jurws_1';

\echo '✓ События добавлены'

-- ============================================================================
-- HAPROXY ИНТЕГРАЦИЯ
-- ============================================================================

-- HAProxy инстансы на серверах с флагом is_haproxy_node
INSERT INTO haproxy_instances (name, server_id, is_active, socket_path, last_sync_status)
SELECT
    'default',
    id,
    true,
    '/var/run/haproxy.sock',
    'success'
FROM servers
WHERE is_haproxy_node = true;

\echo '✓ HAProxy инстансы добавлены'

-- HAProxy backends
INSERT INTO haproxy_backends (haproxy_instance_id, backend_name, enable_polling, last_fetch_status)
SELECT
    hi.id,
    'jurws_backend',
    true,
    'success'
FROM haproxy_instances hi
WHERE hi.name = 'default';

INSERT INTO haproxy_backends (haproxy_instance_id, backend_name, enable_polling, last_fetch_status)
SELECT
    hi.id,
    'mobws_backend',
    true,
    'success'
FROM haproxy_instances hi
WHERE hi.name = 'default';

\echo '✓ HAProxy backends добавлены'

-- HAProxy servers
INSERT INTO haproxy_servers (backend_id, server_name, status, weight, check_status, addr, scur, smax)
SELECT
    hb.id,
    'jurws_1',
    'UP',
    100,
    'L7OK',
    '192.168.1.101:8081',
    5,
    20
FROM haproxy_backends hb
WHERE hb.backend_name = 'jurws_backend'
LIMIT 1;

INSERT INTO haproxy_servers (backend_id, server_name, status, weight, check_status, addr, scur, smax)
SELECT
    hb.id,
    'jurws_2',
    'UP',
    100,
    'L7OK',
    '192.168.1.101:8082',
    3,
    15
FROM haproxy_backends hb
WHERE hb.backend_name = 'jurws_backend'
LIMIT 1;

\echo '✓ HAProxy servers добавлены'

-- ============================================================================
-- EUREKA ИНТЕГРАЦИЯ
-- ============================================================================

-- Eureka серверы на серверах с флагом is_eureka_node
INSERT INTO eureka_servers (server_id, eureka_host, eureka_port, is_active)
SELECT
    id,
    ip,
    8761,
    true
FROM servers
WHERE is_eureka_node = true;

\echo '✓ Eureka серверы добавлены'

-- Eureka приложения
INSERT INTO eureka_applications (eureka_server_id, app_name, instances_count, instances_up)
SELECT
    es.id,
    'JURWS',
    2,
    2
FROM eureka_servers es
LIMIT 1;

\echo '✓ Eureka приложения добавлены'

-- Eureka экземпляры
INSERT INTO eureka_instances (eureka_application_id, instance_id, ip_address, port, service_name, status)
SELECT
    ea.id,
    '192.168.1.101:jurws:8081',
    '192.168.1.101',
    8081,
    'jurws',
    'UP'
FROM eureka_applications ea
WHERE ea.app_name = 'JURWS'
LIMIT 1;

INSERT INTO eureka_instances (eureka_application_id, instance_id, ip_address, port, service_name, status)
SELECT
    ea.id,
    '192.168.1.101:jurws:8082',
    '192.168.1.101',
    8082,
    'jurws',
    'UP'
FROM eureka_applications ea
WHERE ea.app_name = 'JURWS'
LIMIT 1;

\echo '✓ Eureka экземпляры добавлены'

-- ============================================================================
-- МАППИНГ ПРИЛОЖЕНИЙ НА ВНЕШНИЕ СЕРВИСЫ
-- ============================================================================

-- Маппинг jurws_1 на HAProxy server
INSERT INTO application_mappings (application_id, entity_type, entity_id, is_manual, mapped_by)
SELECT
    ai.id,
    'haproxy_server',
    hs.id,
    false,
    'system'
FROM application_instances ai
CROSS JOIN haproxy_servers hs
WHERE ai.instance_name = 'jurws_1'
  AND hs.server_name = 'jurws_1'
LIMIT 1
ON CONFLICT (application_id, entity_type, entity_id) DO NOTHING;

-- Маппинг jurws_1 на Eureka instance
INSERT INTO application_mappings (application_id, entity_type, entity_id, is_manual, mapped_by)
SELECT
    ai.id,
    'eureka_instance',
    ei.id,
    false,
    'system'
FROM application_instances ai
CROSS JOIN eureka_instances ei
WHERE ai.instance_name = 'jurws_1'
  AND ei.instance_id = '192.168.1.101:jurws:8081'
LIMIT 1
ON CONFLICT (application_id, entity_type, entity_id) DO NOTHING;

\echo '✓ Маппинги приложений добавлены'

-- ============================================================================
-- ORCHESTRATOR PLAYBOOKS
-- ============================================================================

INSERT INTO orchestrator_playbooks (file_path, name, description, version, required_params, optional_params, is_active)
VALUES
    (
        '/etc/ansible/orchestrator-update-jurws.yml',
        'Orchestrator Update JURWS',
        'Обновление JURWS с zero-downtime через HAProxy',
        '1.0',
        '{"instances": "Список инстансов для обновления", "distr_url": "URL дистрибутива"}',
        '{"drain_delay": {"description": "Задержка после drain", "default": "30"}, "wait_after_update": {"description": "Ожидание после обновления", "default": "60"}}',
        true
    ),
    (
        '/etc/ansible/orchestrator-restart-all.yml',
        'Orchestrator Restart All',
        'Перезапуск приложений с orchestration',
        '1.2',
        '{"instances": "Список инстансов для перезапуска"}',
        '{"batch_size": {"description": "Размер батча", "default": "2"}}',
        true
    )
ON CONFLICT (file_path) DO NOTHING;

\echo '✓ Orchestrator playbooks добавлены'

-- ============================================================================
-- ГРУППЫ РАССЫЛКИ
-- ============================================================================

INSERT INTO mailing_groups (name, description, emails, is_active)
VALUES
    ('admins', 'Системные администраторы', 'admin1@example.com,admin2@example.com', true),
    ('developers', 'Разработчики', 'dev1@example.com,dev2@example.com,dev3@example.com', true),
    ('ops', 'Operations team', 'ops@example.com', true)
ON CONFLICT (name) DO NOTHING;

\echo '✓ Группы рассылки добавлены'

-- ============================================================================
-- ЗАДАЧИ
-- ============================================================================

INSERT INTO tasks (id, task_type, status, params, server_id, instance_id, created_at, started_at, completed_at, result)
VALUES
    (
        'task-001-restart-jurws1',
        'restart',
        'completed',
        '{"playbook": "/etc/ansible/restart.yml"}',
        (SELECT id FROM servers WHERE name = 'fdmz01'),
        (SELECT id FROM application_instances WHERE instance_name = 'jurws_1' LIMIT 1),
        NOW() - INTERVAL '2 hours',
        NOW() - INTERVAL '2 hours',
        NOW() - INTERVAL '1 hour 55 minutes',
        'Successfully restarted'
    ),
    (
        'task-002-update-mobws1',
        'update',
        'processing',
        '{"playbook": "/etc/ansible/update.yml", "distr_url": "http://nexus.local/mobws/3.1.0.war"}',
        (SELECT id FROM servers WHERE name = 'fdmz02'),
        (SELECT id FROM application_instances WHERE instance_name = 'mobws_1' LIMIT 1),
        NOW() - INTERVAL '10 minutes',
        NOW() - INTERVAL '5 minutes',
        NULL,
        NULL
    )
ON CONFLICT (id) DO NOTHING;

\echo '✓ Задачи добавлены'

-- ============================================================================
-- СТАТИСТИКА
-- ============================================================================

\echo '\n=== СТАТИСТИКА ТЕСТОВЫХ ДАННЫХ ==='

SELECT 'Серверы' AS entity, count(*) AS count FROM servers
UNION ALL
SELECT 'Справочник приложений', count(*) FROM application_catalog
UNION ALL
SELECT 'Группы приложений', count(*) FROM application_groups
UNION ALL
SELECT 'Экземпляры приложений', count(*) FROM application_instances
UNION ALL
SELECT 'Теги', count(*) FROM tags
UNION ALL
SELECT 'События', count(*) FROM events
UNION ALL
SELECT 'HAProxy инстансы', count(*) FROM haproxy_instances
UNION ALL
SELECT 'HAProxy backends', count(*) FROM haproxy_backends
UNION ALL
SELECT 'HAProxy servers', count(*) FROM haproxy_servers
UNION ALL
SELECT 'Eureka серверы', count(*) FROM eureka_servers
UNION ALL
SELECT 'Eureka приложения', count(*) FROM eureka_applications
UNION ALL
SELECT 'Eureka экземпляры', count(*) FROM eureka_instances
UNION ALL
SELECT 'Маппинги', count(*) FROM application_mappings
UNION ALL
SELECT 'Orchestrator playbooks', count(*) FROM orchestrator_playbooks
UNION ALL
SELECT 'Группы рассылки', count(*) FROM mailing_groups
UNION ALL
SELECT 'Задачи', count(*) FROM tasks;

\echo '\n=== ЗАПОЛНЕНИЕ ЗАВЕРШЕНО ==='

-- =============================================================================
-- Application Control (AC) - Database Schema Initialization Script
-- =============================================================================
-- Скрипт создания модели данных для Application Control
-- Версия: 1.1
-- Дата: 2025-12-10
-- Изменения v1.1:
--   - Добавлены поля artifact_size_bytes, artifact_type в application_instances
--   - Добавлены расширенные Eureka поля: eureka_instance_id, eureka_app_name,
--     eureka_status, eureka_health_url, eureka_vip
-- =============================================================================

-- Использование:
-- psql -U <user> -d <database> -f init_database.sql
-- или
-- docker exec -i pg-fak psql -U fakadm -d appcontrol < init_database.sql

BEGIN;

-- =============================================================================
-- 1. БАЗОВЫЕ ТАБЛИЦЫ
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1.1 Серверы (servers)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    ip VARCHAR(15) NOT NULL,
    port INTEGER NOT NULL,
    last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'offline',
    is_haproxy_node BOOLEAN DEFAULT FALSE NOT NULL,
    is_eureka_node BOOLEAN DEFAULT FALSE NOT NULL
);

COMMENT ON TABLE servers IS 'Физические или виртуальные серверы с FAgent';
COMMENT ON COLUMN servers.is_haproxy_node IS 'Флаг: сервер является узлом HAProxy';
COMMENT ON COLUMN servers.is_eureka_node IS 'Флаг: сервер является узлом Eureka';

-- -----------------------------------------------------------------------------
-- 1.2 Каталог приложений (application_catalog)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_catalog (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    app_type VARCHAR(32) NOT NULL,
    description TEXT,
    default_playbook_path VARCHAR(255),
    default_artifact_url VARCHAR(255),
    default_artifact_extension VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_catalog_name ON application_catalog(name);
CREATE INDEX IF NOT EXISTS idx_catalog_type ON application_catalog(app_type);

COMMENT ON TABLE application_catalog IS 'Справочник типов приложений с настройками по умолчанию';

-- -----------------------------------------------------------------------------
-- 1.3 Группы приложений (application_groups)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    artifact_list_url VARCHAR(512),
    artifact_extension VARCHAR(32),
    update_playbook_path VARCHAR(256),
    batch_grouping_strategy VARCHAR(32) DEFAULT 'by_group' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tags_cache VARCHAR(512)
);

CREATE INDEX IF NOT EXISTS idx_app_groups_name ON application_groups(name);
CREATE INDEX IF NOT EXISTS idx_app_groups_catalog ON application_groups(catalog_id);

COMMENT ON TABLE application_groups IS 'Логические группы приложений с общими настройками';
COMMENT ON COLUMN application_groups.batch_grouping_strategy IS 'Стратегия группировки: by_group, by_server, by_instance_name, no_grouping';

-- -----------------------------------------------------------------------------
-- 1.4 Экземпляры приложений (application_instances)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_instances (
    id SERIAL PRIMARY KEY,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    group_id INTEGER REFERENCES application_groups(id) ON DELETE SET NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,

    -- Идентификация
    instance_name VARCHAR(128) NOT NULL,
    instance_number INTEGER DEFAULT 0 NOT NULL,
    app_type VARCHAR(32) NOT NULL,

    -- Состояние
    status VARCHAR(32) DEFAULT 'unknown',
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Данные от агента
    path VARCHAR(255),
    log_path VARCHAR(255),
    version VARCHAR(128),
    distr_path VARCHAR(255),

    -- Информация об артефактах (от агента)
    artifact_size_bytes BIGINT,
    artifact_type VARCHAR(32),

    -- Docker-специфичные поля
    container_id VARCHAR(128),
    container_name VARCHAR(128),
    compose_project_dir VARCHAR(255),
    image VARCHAR(255),
    tag VARCHAR(64),
    eureka_registered BOOLEAN DEFAULT FALSE,

    -- Eureka-специфичные поля (расширенные)
    eureka_url VARCHAR(255),
    eureka_instance_id VARCHAR(255),
    eureka_app_name VARCHAR(128),
    eureka_status VARCHAR(32),
    eureka_health_url VARCHAR(512),
    eureka_vip VARCHAR(128),

    -- Сетевые параметры
    ip VARCHAR(45),
    port INTEGER,

    -- Процесс
    pid INTEGER,
    start_time TIMESTAMP,

    -- Кастомизация
    custom_playbook_path VARCHAR(255),
    custom_artifact_url VARCHAR(512),
    custom_artifact_extension VARCHAR(32),

    -- Метаданные
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    tags_cache VARCHAR(512),

    -- Ограничения
    CONSTRAINT unique_instance_per_server UNIQUE (server_id, instance_name, app_type)
);

CREATE INDEX IF NOT EXISTS idx_instance_catalog ON application_instances(catalog_id);
CREATE INDEX IF NOT EXISTS idx_instance_group ON application_instances(group_id);
CREATE INDEX IF NOT EXISTS idx_instance_server ON application_instances(server_id);
CREATE INDEX IF NOT EXISTS idx_instance_status ON application_instances(status);
CREATE INDEX IF NOT EXISTS idx_instance_deleted ON application_instances(deleted_at);
CREATE INDEX IF NOT EXISTS idx_instance_name ON application_instances(instance_name);
CREATE INDEX IF NOT EXISTS idx_instance_type ON application_instances(app_type);

COMMENT ON TABLE application_instances IS 'Экземпляры приложений на серверах';
COMMENT ON COLUMN application_instances.app_type IS 'Тип: docker, eureka, site, service, smf, sysctl';
COMMENT ON COLUMN application_instances.status IS 'Статус: online, offline, unknown, starting, stopping, no_data';

-- -----------------------------------------------------------------------------
-- 1.5 События (events)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(32) NOT NULL,
    description TEXT,
    status VARCHAR(32) DEFAULT 'success',
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    instance_id INTEGER REFERENCES application_instances(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_server ON events(server_id);
CREATE INDEX IF NOT EXISTS idx_events_instance ON events(instance_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

COMMENT ON TABLE events IS 'История событий: start, stop, restart, update, connect, disconnect';
COMMENT ON COLUMN events.status IS 'Статус события: success, failed, pending';

-- =============================================================================
-- 2. СИСТЕМА ТЕГОВ
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 2.1 Теги (tags)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    display_name VARCHAR(64),
    description TEXT,
    icon VARCHAR(20),
    tag_type VARCHAR(20),
    css_class VARCHAR(50),
    border_color VARCHAR(7),
    text_color VARCHAR(7),
    is_system BOOLEAN DEFAULT FALSE NOT NULL,
    show_in_table BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_tags_system ON tags(is_system);

COMMENT ON TABLE tags IS 'Теги для маркировки приложений и групп';
COMMENT ON COLUMN tags.tag_type IS 'Тип тега: status, env, version, system, custom';
COMMENT ON COLUMN tags.is_system IS 'Системный тег (нельзя удалить)';
COMMENT ON COLUMN tags.show_in_table IS 'Показывать в таблице приложений';

-- -----------------------------------------------------------------------------
-- 2.2 Связь экземпляров и тегов (application_instance_tags)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_instance_tags (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(64),
    auto_assign_disabled BOOLEAN DEFAULT FALSE NOT NULL,

    CONSTRAINT uq_app_instance_tag UNIQUE (application_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_app_tags_app ON application_instance_tags(application_id);
CREATE INDEX IF NOT EXISTS idx_app_tags_tag ON application_instance_tags(tag_id);

-- -----------------------------------------------------------------------------
-- 2.3 Связь групп и тегов (application_group_tags)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_group_tags (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES application_groups(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(64),

    CONSTRAINT uq_app_group_tag UNIQUE (group_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_group_tags_group ON application_group_tags(group_id);
CREATE INDEX IF NOT EXISTS idx_group_tags_tag ON application_group_tags(tag_id);

-- -----------------------------------------------------------------------------
-- 2.4 История тегов (tag_history)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tag_history (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    tag_id INTEGER REFERENCES tags(id) ON DELETE SET NULL,
    action VARCHAR(20) NOT NULL,
    changed_by VARCHAR(64),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details JSONB
);

CREATE INDEX IF NOT EXISTS idx_tag_history_entity ON tag_history(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_tag_history_time ON tag_history(changed_at);

COMMENT ON COLUMN tag_history.entity_type IS 'Тип сущности: instance, group';
COMMENT ON COLUMN tag_history.action IS 'Действие: assigned, removed, updated';

-- =============================================================================
-- 3. HAPROXY ИНТЕГРАЦИЯ
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 3.1 HAProxy инстансы (haproxy_instances)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS haproxy_instances (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    socket_path VARCHAR(256),
    last_sync TIMESTAMP,
    last_sync_status VARCHAR(32) DEFAULT 'unknown',
    last_sync_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_haproxy_instance_per_server UNIQUE (server_id, name)
);

CREATE INDEX IF NOT EXISTS idx_haproxy_instance_server ON haproxy_instances(server_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_instance_active ON haproxy_instances(is_active);

-- -----------------------------------------------------------------------------
-- 3.2 HAProxy backends (haproxy_backends)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS haproxy_backends (
    id SERIAL PRIMARY KEY,
    haproxy_instance_id INTEGER NOT NULL REFERENCES haproxy_instances(id) ON DELETE CASCADE,
    backend_name VARCHAR(128) NOT NULL,
    enable_polling BOOLEAN DEFAULT TRUE NOT NULL,
    last_fetch_status VARCHAR(20) DEFAULT 'unknown',
    last_fetch_error TEXT,
    last_fetch_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,

    CONSTRAINT uq_backend_per_instance UNIQUE (haproxy_instance_id, backend_name)
);

CREATE INDEX IF NOT EXISTS idx_haproxy_backend_instance ON haproxy_backends(haproxy_instance_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_backend_removed ON haproxy_backends(removed_at);

-- -----------------------------------------------------------------------------
-- 3.3 HAProxy servers (haproxy_servers)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS haproxy_servers (
    id SERIAL PRIMARY KEY,
    backend_id INTEGER NOT NULL REFERENCES haproxy_backends(id) ON DELETE CASCADE,
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
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,

    CONSTRAINT uq_server_per_backend UNIQUE (backend_id, server_name)
);

CREATE INDEX IF NOT EXISTS idx_haproxy_server_backend ON haproxy_servers(backend_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_server_status ON haproxy_servers(status);
CREATE INDEX IF NOT EXISTS idx_haproxy_server_removed ON haproxy_servers(removed_at);

COMMENT ON COLUMN haproxy_servers.status IS 'Статус: UP, DOWN, MAINT, DRAIN';

-- -----------------------------------------------------------------------------
-- 3.4 История статусов HAProxy серверов
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS haproxy_server_status_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER NOT NULL REFERENCES haproxy_servers(id) ON DELETE CASCADE,
    old_status VARCHAR(32),
    new_status VARCHAR(32) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_haproxy_history_server ON haproxy_server_status_history(haproxy_server_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_history_changed_at ON haproxy_server_status_history(changed_at);

-- -----------------------------------------------------------------------------
-- 3.5 История маппингов HAProxy
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS haproxy_mapping_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER NOT NULL REFERENCES haproxy_servers(id) ON DELETE CASCADE,
    old_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    new_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    change_reason VARCHAR(32) NOT NULL,
    mapped_by VARCHAR(64),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_server ON haproxy_mapping_history(haproxy_server_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_changed_at ON haproxy_mapping_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_reason ON haproxy_mapping_history(change_reason);

-- =============================================================================
-- 4. EUREKA ИНТЕГРАЦИЯ
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 4.1 Eureka серверы (eureka_servers)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eureka_servers (
    id SERIAL PRIMARY KEY,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    eureka_host VARCHAR(255) NOT NULL,
    eureka_port INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    last_sync TIMESTAMP,
    last_error TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP,

    CONSTRAINT uq_eureka_server_per_server UNIQUE (server_id),
    CONSTRAINT uq_eureka_endpoint UNIQUE (eureka_host, eureka_port)
);

CREATE INDEX IF NOT EXISTS idx_eureka_server_server ON eureka_servers(server_id);
CREATE INDEX IF NOT EXISTS idx_eureka_server_active ON eureka_servers(is_active);
CREATE INDEX IF NOT EXISTS idx_eureka_server_removed ON eureka_servers(removed_at);

-- -----------------------------------------------------------------------------
-- 4.2 Eureka приложения (eureka_applications)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eureka_applications (
    id SERIAL PRIMARY KEY,
    eureka_server_id INTEGER NOT NULL REFERENCES eureka_servers(id) ON DELETE CASCADE,
    app_name VARCHAR(255) NOT NULL,
    instances_count INTEGER DEFAULT 0,
    instances_up INTEGER DEFAULT 0,
    instances_down INTEGER DEFAULT 0,
    instances_paused INTEGER DEFAULT 0,
    last_fetch_status VARCHAR(20) DEFAULT 'unknown',
    last_fetch_error TEXT,
    last_fetch_at TIMESTAMP,
    last_sync TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_eureka_app_per_server UNIQUE (eureka_server_id, app_name)
);

CREATE INDEX IF NOT EXISTS idx_eureka_application_server ON eureka_applications(eureka_server_id);
CREATE INDEX IF NOT EXISTS idx_eureka_application_name ON eureka_applications(app_name);

-- -----------------------------------------------------------------------------
-- 4.3 Eureka экземпляры (eureka_instances)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eureka_instances (
    id SERIAL PRIMARY KEY,
    eureka_application_id INTEGER NOT NULL REFERENCES eureka_applications(id) ON DELETE CASCADE,
    instance_id VARCHAR(255) NOT NULL UNIQUE,
    ip_address VARCHAR(45) NOT NULL,
    port INTEGER NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
    last_heartbeat TIMESTAMP,
    instance_metadata JSONB,
    health_check_url VARCHAR(512),
    home_page_url VARCHAR(512),
    status_page_url VARCHAR(512),
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_eureka_instance_application ON eureka_instances(eureka_application_id);
CREATE INDEX IF NOT EXISTS idx_eureka_instance_status ON eureka_instances(status);
CREATE INDEX IF NOT EXISTS idx_eureka_instance_instance_id ON eureka_instances(instance_id);
CREATE INDEX IF NOT EXISTS idx_eureka_instance_ip ON eureka_instances(ip_address);
CREATE INDEX IF NOT EXISTS idx_eureka_instance_removed ON eureka_instances(removed_at);

COMMENT ON COLUMN eureka_instances.status IS 'Статус: UP, DOWN, PAUSED, STARTING, OUT_OF_SERVICE, UNKNOWN';

-- -----------------------------------------------------------------------------
-- 4.4 История статусов Eureka экземпляров
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eureka_instance_status_history (
    id SERIAL PRIMARY KEY,
    eureka_instance_id INTEGER NOT NULL REFERENCES eureka_instances(id) ON DELETE CASCADE,
    old_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_eureka_status_history_instance ON eureka_instance_status_history(eureka_instance_id);
CREATE INDEX IF NOT EXISTS idx_eureka_status_history_changed_at ON eureka_instance_status_history(changed_at);

-- -----------------------------------------------------------------------------
-- 4.5 Действия над Eureka экземплярами
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eureka_instance_actions (
    id SERIAL PRIMARY KEY,
    eureka_instance_id INTEGER NOT NULL REFERENCES eureka_instances(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL,
    action_params JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    result TEXT,
    error_message TEXT,
    user_id INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_eureka_action_instance ON eureka_instance_actions(eureka_instance_id);
CREATE INDEX IF NOT EXISTS idx_eureka_action_type ON eureka_instance_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_eureka_action_status ON eureka_instance_actions(status);
CREATE INDEX IF NOT EXISTS idx_eureka_action_started_at ON eureka_instance_actions(started_at);

COMMENT ON COLUMN eureka_instance_actions.action_type IS 'Тип: health_check, pause, shutdown, log_level_change';
COMMENT ON COLUMN eureka_instance_actions.status IS 'Статус: pending, in_progress, success, failed';

-- =============================================================================
-- 5. МАППИНГИ ПРИЛОЖЕНИЙ
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 5.1 Маппинги приложений (application_mappings)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_mappings (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    mapped_by VARCHAR(64),
    mapped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    mapping_metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uk_app_entity UNIQUE (application_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_app_mappings_application_id ON application_mappings(application_id);
CREATE INDEX IF NOT EXISTS idx_app_mappings_entity ON application_mappings(entity_type, entity_id);

COMMENT ON TABLE application_mappings IS 'Унифицированная таблица маппингов на внешние сервисы';
COMMENT ON COLUMN application_mappings.entity_type IS 'Тип: haproxy_server, eureka_instance';

-- -----------------------------------------------------------------------------
-- 5.2 История маппингов (application_mapping_history)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_mapping_history (
    id SERIAL PRIMARY KEY,
    mapping_id INTEGER REFERENCES application_mappings(id) ON DELETE SET NULL,
    application_id INTEGER NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by VARCHAR(64),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_mapping_history_mapping_id ON application_mapping_history(mapping_id);
CREATE INDEX IF NOT EXISTS idx_mapping_history_application_id ON application_mapping_history(application_id);
CREATE INDEX IF NOT EXISTS idx_mapping_history_changed_at ON application_mapping_history(changed_at);

COMMENT ON COLUMN application_mapping_history.action IS 'Действие: created, updated, deleted, deactivated, activated';

-- =============================================================================
-- 6. ДОПОЛНИТЕЛЬНЫЕ ТАБЛИЦЫ
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 6.1 Orchestrator Playbooks
-- -----------------------------------------------------------------------------
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

CREATE INDEX IF NOT EXISTS idx_orchestrator_path ON orchestrator_playbooks(file_path);
CREATE INDEX IF NOT EXISTS idx_orchestrator_active ON orchestrator_playbooks(is_active);

COMMENT ON TABLE orchestrator_playbooks IS 'Playbooks оркестратора для zero-downtime обновлений';

-- -----------------------------------------------------------------------------
-- 6.2 История версий приложений
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_version_history (
    id SERIAL PRIMARY KEY,
    instance_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    old_version VARCHAR(128),
    new_version VARCHAR(128) NOT NULL,
    old_distr_path VARCHAR(255),
    new_distr_path VARCHAR(255),
    old_tag VARCHAR(64),
    new_tag VARCHAR(64),
    old_image VARCHAR(255),
    new_image VARCHAR(255),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(20) NOT NULL,
    change_source VARCHAR(50),
    task_id VARCHAR(64),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_version_history_instance ON application_version_history(instance_id);
CREATE INDEX IF NOT EXISTS idx_version_history_changed_at ON application_version_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_version_history_changed_by ON application_version_history(changed_by);
CREATE INDEX IF NOT EXISTS idx_version_history_instance_time ON application_version_history(instance_id, changed_at);

COMMENT ON COLUMN application_version_history.changed_by IS 'Кто изменил: user, agent, system';
COMMENT ON COLUMN application_version_history.change_source IS 'Источник: update_task, polling, manual';

-- -----------------------------------------------------------------------------
-- 6.3 Группы рассылки
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mailing_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(255),
    emails TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mailing_group_name ON mailing_groups(name);
CREATE INDEX IF NOT EXISTS idx_mailing_group_active ON mailing_groups(is_active);

COMMENT ON TABLE mailing_groups IS 'Группы рассылки для отчётов по email';
COMMENT ON COLUMN mailing_groups.emails IS 'Email-адреса через запятую';

-- -----------------------------------------------------------------------------
-- 6.4 Задачи (tasks)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) PRIMARY KEY,
    task_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) DEFAULT 'pending' NOT NULL,
    params JSONB DEFAULT '{}',
    server_id INTEGER REFERENCES servers(id) ON DELETE SET NULL,
    instance_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result TEXT,
    error TEXT,
    progress JSONB DEFAULT '{}',
    pid INTEGER,
    cancelled BOOLEAN DEFAULT FALSE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type);
CREATE INDEX IF NOT EXISTS idx_tasks_server ON tasks(server_id);
CREATE INDEX IF NOT EXISTS idx_tasks_instance ON tasks(instance_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

COMMENT ON TABLE tasks IS 'Очередь задач для операций над приложениями';
COMMENT ON COLUMN tasks.task_type IS 'Тип: start, stop, restart, update';
COMMENT ON COLUMN tasks.status IS 'Статус: pending, processing, completed, failed';

-- =============================================================================
-- 7. СИСТЕМНЫЕ ТЕГИ
-- =============================================================================

-- Создание системных тегов
INSERT INTO tags (name, display_name, description, tag_type, is_system, show_in_table, border_color, text_color, created_at, updated_at)
VALUES
    -- Теги с автоназначением по маппингу
    ('haproxy', 'H', 'Приложение связано с HAProxy backend', 'system', TRUE, TRUE, '#28a745', '#28a745', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('eureka', 'E', 'Приложение зарегистрировано в Eureka', 'system', TRUE, TRUE, '#007bff', '#007bff', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

    -- Теги с автоназначением по app_type
    ('docker', 'docker', 'Docker-контейнер', 'system', TRUE, TRUE, '#2496ed', '#2496ed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('smf', 'smf', 'SMF сервис (Solaris)', 'system', TRUE, FALSE, '#fd7e14', '#fd7e14', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('sysctl', 'sysctl', 'Systemctl сервис', 'system', TRUE, FALSE, '#20c997', '#20c997', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

    -- Ручные теги
    ('disable', 'disable', 'Отключенное приложение', 'system', TRUE, FALSE, '#6c757d', '#6c757d', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('system', 'SYS', 'Системное приложение', 'system', TRUE, FALSE, '#6f42c1', '#6f42c1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('ver.lock', 'v.lock', 'Блокировка обновлений', 'system', TRUE, FALSE, '#dc3545', '#dc3545', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('status.lock', 's.lock', 'Блокировка start/stop/restart', 'system', TRUE, FALSE, '#ffc107', '#856404', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),

    -- Автоматический тег мониторинга
    ('pending_removal', 'DEL', 'Приложение будет удалено (offline > N дней)', 'system', TRUE, TRUE, '#dc3545', '#dc3545', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    tag_type = EXCLUDED.tag_type,
    is_system = EXCLUDED.is_system,
    show_in_table = EXCLUDED.show_in_table,
    border_color = EXCLUDED.border_color,
    text_color = EXCLUDED.text_color,
    updated_at = CURRENT_TIMESTAMP;

-- =============================================================================
-- 8. ТАБЛИЦА МИГРАЦИЙ (для Flask-Migrate совместимости)
-- =============================================================================

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Вставка начальной версии (опционально)
-- INSERT INTO alembic_version (version_num) VALUES ('init_schema') ON CONFLICT DO NOTHING;

COMMIT;

-- =============================================================================
-- ИНФОРМАЦИЯ О СХЕМЕ
-- =============================================================================
--
-- Основные сущности:
--   servers                 - Серверы с FAgent
--   application_catalog     - Справочник типов приложений
--   application_groups      - Логические группы приложений
--   application_instances   - Экземпляры приложений
--   events                  - История событий
--
-- Система тегов:
--   tags                    - Теги
--   application_instance_tags - Связь экземпляров и тегов
--   application_group_tags  - Связь групп и тегов
--   tag_history             - История изменений тегов
--
-- HAProxy интеграция:
--   haproxy_instances       - HAProxy инстансы
--   haproxy_backends        - Backend-пулы
--   haproxy_servers         - Серверы в backend
--   haproxy_server_status_history - История статусов
--   haproxy_mapping_history - История маппингов
--
-- Eureka интеграция:
--   eureka_servers          - Eureka серверы
--   eureka_applications     - Приложения в Eureka
--   eureka_instances        - Экземпляры сервисов
--   eureka_instance_status_history - История статусов
--   eureka_instance_actions - Журнал действий
--
-- Маппинги:
--   application_mappings    - Унифицированные маппинги
--   application_mapping_history - История маппингов
--
-- Дополнительно:
--   orchestrator_playbooks  - Playbooks оркестратора
--   application_version_history - История версий
--   mailing_groups          - Группы рассылки
--   tasks                   - Очередь задач
--
-- =============================================================================

-- ============================================================
-- AC (Application Control) - Database Schema
-- Полный DDL скрипт для развёртывания на чистой системе
-- ============================================================
-- Порядок таблиц учитывает зависимости (foreign keys)
-- Безопасно для повторного запуска: IF NOT EXISTS
-- ============================================================

-- ============================================================
-- 1. БАЗОВЫЕ ТАБЛИЦЫ (без внешних ключей на другие таблицы)
-- ============================================================

-- Серверы
CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    ip VARCHAR(15) NOT NULL,
    port INTEGER NOT NULL,
    last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'offline',
    is_haproxy_node BOOLEAN NOT NULL DEFAULT FALSE,
    is_eureka_node BOOLEAN NOT NULL DEFAULT FALSE
);

-- Справочник приложений
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

-- Теги
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    show_in_table BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);

-- Orchestrator playbooks
CREATE TABLE IF NOT EXISTS orchestrator_playbooks (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(512) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    version VARCHAR(32),
    required_params JSONB,
    optional_params JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_scanned TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_metadata JSONB
);
CREATE INDEX IF NOT EXISTS idx_orchestrator_file_path ON orchestrator_playbooks(file_path);

-- Группы рассылки
CREATE TABLE IF NOT EXISTS mailing_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(255),
    emails TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_mailing_group_name ON mailing_groups(name);
CREATE INDEX IF NOT EXISTS idx_mailing_group_active ON mailing_groups(is_active);

-- ============================================================
-- 2. ГРУППЫ ПРИЛОЖЕНИЙ (зависит от application_catalog)
-- ============================================================

CREATE TABLE IF NOT EXISTS application_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    artifact_list_url VARCHAR(512),
    artifact_extension VARCHAR(32),
    update_playbook_path VARCHAR(256),
    batch_grouping_strategy VARCHAR(32) NOT NULL DEFAULT 'by_group',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tags_cache VARCHAR(512)
);
CREATE INDEX IF NOT EXISTS idx_application_groups_name ON application_groups(name);

-- ============================================================
-- 3. ЭКЗЕМПЛЯРЫ ПРИЛОЖЕНИЙ (зависит от servers, catalog, groups)
-- ============================================================

CREATE TABLE IF NOT EXISTS application_instances (
    id SERIAL PRIMARY KEY,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    group_id INTEGER REFERENCES application_groups(id) ON DELETE SET NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    instance_name VARCHAR(128) NOT NULL,
    instance_number INTEGER NOT NULL DEFAULT 0,
    app_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) DEFAULT 'unknown',
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    path VARCHAR(255),
    log_path VARCHAR(255),
    version VARCHAR(128),
    distr_path VARCHAR(255),
    container_id VARCHAR(128),
    container_name VARCHAR(128),
    compose_project_dir VARCHAR(255),
    image VARCHAR(255),
    tag VARCHAR(64),
    eureka_registered BOOLEAN DEFAULT FALSE,
    eureka_url VARCHAR(255),
    ip VARCHAR(45),
    port INTEGER,
    pid INTEGER,
    start_time TIMESTAMP,
    custom_playbook_path VARCHAR(255),
    custom_artifact_url VARCHAR(512),
    custom_artifact_extension VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    tags_cache VARCHAR(512),
    CONSTRAINT unique_instance_per_server UNIQUE (server_id, instance_name, app_type)
);
CREATE INDEX IF NOT EXISTS idx_instance_catalog ON application_instances(catalog_id);
CREATE INDEX IF NOT EXISTS idx_instance_group ON application_instances(group_id);
CREATE INDEX IF NOT EXISTS idx_instance_server ON application_instances(server_id);
CREATE INDEX IF NOT EXISTS idx_instance_status ON application_instances(status);
CREATE INDEX IF NOT EXISTS idx_instance_deleted ON application_instances(deleted_at);
CREATE INDEX IF NOT EXISTS idx_instance_name ON application_instances(instance_name);
CREATE INDEX IF NOT EXISTS idx_instance_type ON application_instances(app_type);

-- ============================================================
-- 4. СОБЫТИЯ (зависит от servers, application_instances)
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(32) NOT NULL,
    description TEXT,
    status VARCHAR(32) DEFAULT 'success',
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    instance_id INTEGER REFERENCES application_instances(id) ON DELETE CASCADE
);

-- ============================================================
-- 5. ЗАДАЧИ (зависит от servers, application_instances)
-- ============================================================

CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) PRIMARY KEY,
    task_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
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
    cancelled BOOLEAN NOT NULL DEFAULT FALSE
);

-- ============================================================
-- 6. СИСТЕМА ТЕГОВ (связи many-to-many)
-- ============================================================

-- Связь тегов с экземплярами приложений
CREATE TABLE IF NOT EXISTS application_instance_tags (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(64),
    auto_assign_disabled BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_app_instance_tag UNIQUE (application_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_app_tags_app ON application_instance_tags(application_id);
CREATE INDEX IF NOT EXISTS idx_app_tags_tag ON application_instance_tags(tag_id);

-- Связь тегов с группами приложений
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

-- История изменений тегов
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

-- ============================================================
-- 7. HAPROXY ИНТЕГРАЦИЯ
-- ============================================================

-- HAProxy инстансы
CREATE TABLE IF NOT EXISTS haproxy_instances (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
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

-- HAProxy backends
CREATE TABLE IF NOT EXISTS haproxy_backends (
    id SERIAL PRIMARY KEY,
    haproxy_instance_id INTEGER NOT NULL REFERENCES haproxy_instances(id) ON DELETE CASCADE,
    backend_name VARCHAR(128) NOT NULL,
    enable_polling BOOLEAN NOT NULL DEFAULT TRUE,
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

-- HAProxy servers (члены backend)
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

-- История статусов HAProxy servers
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

-- История маппингов HAProxy
CREATE TABLE IF NOT EXISTS haproxy_mapping_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER NOT NULL REFERENCES haproxy_servers(id) ON DELETE CASCADE,
    old_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    new_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    change_reason VARCHAR(32) NOT NULL,
    mapped_by VARCHAR(64),
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_server ON haproxy_mapping_history(haproxy_server_id);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_changed_at ON haproxy_mapping_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_reason ON haproxy_mapping_history(change_reason);

-- ============================================================
-- 8. EUREKA ИНТЕГРАЦИЯ
-- ============================================================

-- Eureka servers
CREATE TABLE IF NOT EXISTS eureka_servers (
    id SERIAL PRIMARY KEY,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    eureka_host VARCHAR(255) NOT NULL,
    eureka_port INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
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

-- Eureka applications
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

-- Eureka instances
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

-- История статусов Eureka instances
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

-- Действия над Eureka instances
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

-- ============================================================
-- 9. УНИФИЦИРОВАННЫЕ МАППИНГИ ПРИЛОЖЕНИЙ
-- ============================================================

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

-- История маппингов
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

-- ============================================================
-- 10. ИСТОРИЯ ВЕРСИЙ ПРИЛОЖЕНИЙ
-- ============================================================

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

-- ============================================================
-- 11. СИСТЕМНЫЕ ТЕГИ (данные)
-- ============================================================

INSERT INTO tags (name, display_name, description, is_system, show_in_table, tag_type, border_color, text_color, icon, css_class)
VALUES
    ('haproxy', 'H', 'Приложение связано с HAProxy backend', TRUE, TRUE, 'system', '#28a745', '#28a745', '●', 'tag-system'),
    ('eureka', 'E', 'Приложение зарегистрировано в Eureka', TRUE, TRUE, 'system', '#007bff', '#007bff', '●', 'tag-system'),
    ('docker', 'docker', 'Docker-контейнер', TRUE, TRUE, 'system', '#2496ed', '#2496ed', '●', 'tag-system'),
    ('disable', 'disable', 'Отключенное приложение', TRUE, FALSE, 'system', '#6c757d', '#6c757d', '●', 'tag-system'),
    ('system', 'SYS', 'Системное приложение', TRUE, FALSE, 'system', '#6f42c1', '#6f42c1', '●', 'tag-system'),
    ('smf', 'smf', 'SMF сервис (Solaris)', TRUE, FALSE, 'system', '#fd7e14', '#fd7e14', '●', 'tag-system'),
    ('sysctl', 'sysctl', 'Systemctl сервис', TRUE, FALSE, 'system', '#20c997', '#20c997', '●', 'tag-system'),
    ('ver.lock', 'v.lock', 'Блокировка обновлений', TRUE, FALSE, 'system', '#dc3545', '#dc3545', '●', 'tag-system'),
    ('status.lock', 's.lock', 'Блокировка start/stop/restart', TRUE, FALSE, 'system', '#ffc107', '#856404', '●', 'tag-system'),
    ('pending_removal', 'DEL', 'Приложение будет удалено (offline > N дней)', TRUE, TRUE, 'system', '#dc3545', '#dc3545', '●', 'tag-system')
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- ГОТОВО
-- ============================================================

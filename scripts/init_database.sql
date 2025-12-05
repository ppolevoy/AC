-- =============================================================================
-- AC (Application Control) - SQL скрипт для чистого разворачивания БД
-- =============================================================================
-- Версия: 1.0
-- Дата: 2025-12-04
-- Описание: Полная схема базы данных для приложения AC
-- =============================================================================

-- Удаление существующих таблиц (в обратном порядке зависимостей)
DROP TABLE IF EXISTS application_mapping_history CASCADE;
DROP TABLE IF EXISTS application_mappings CASCADE;
DROP TABLE IF EXISTS application_version_history CASCADE;
DROP TABLE IF EXISTS eureka_instance_actions CASCADE;
DROP TABLE IF EXISTS eureka_instance_status_history CASCADE;
DROP TABLE IF EXISTS eureka_instances CASCADE;
DROP TABLE IF EXISTS eureka_applications CASCADE;
DROP TABLE IF EXISTS eureka_servers CASCADE;
DROP TABLE IF EXISTS haproxy_mapping_history CASCADE;
DROP TABLE IF EXISTS haproxy_server_status_history CASCADE;
DROP TABLE IF EXISTS haproxy_servers CASCADE;
DROP TABLE IF EXISTS haproxy_backends CASCADE;
DROP TABLE IF EXISTS haproxy_instances CASCADE;
DROP TABLE IF EXISTS tag_history CASCADE;
DROP TABLE IF EXISTS application_group_tags CASCADE;
DROP TABLE IF EXISTS application_instance_tags CASCADE;
DROP TABLE IF EXISTS tags CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS application_instances CASCADE;
DROP TABLE IF EXISTS application_groups CASCADE;
DROP TABLE IF EXISTS application_catalog CASCADE;
DROP TABLE IF EXISTS orchestrator_playbooks CASCADE;
DROP TABLE IF EXISTS mailing_groups CASCADE;
DROP TABLE IF EXISTS servers CASCADE;
DROP TABLE IF EXISTS alembic_version CASCADE;

-- =============================================================================
-- 1. Базовые таблицы (без внешних ключей на другие таблицы)
-- =============================================================================

-- Таблица для Alembic миграций
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Серверы
CREATE TABLE servers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    ip VARCHAR(15) NOT NULL,
    port INTEGER NOT NULL,
    last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'offline',
    is_haproxy_node BOOLEAN DEFAULT FALSE NOT NULL,
    is_eureka_node BOOLEAN DEFAULT FALSE NOT NULL
);

-- Справочник приложений
CREATE TABLE application_catalog (
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

CREATE INDEX idx_catalog_name ON application_catalog(name);
CREATE INDEX idx_catalog_type ON application_catalog(app_type);

-- Orchestrator Playbooks
CREATE TABLE orchestrator_playbooks (
    id SERIAL PRIMARY KEY,
    file_path VARCHAR(512) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    version VARCHAR(32),
    required_params JSONB,
    optional_params JSONB,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    raw_metadata JSONB
);

CREATE INDEX idx_orchestrator_playbook_path ON orchestrator_playbooks(file_path);

-- Группы рассылки
CREATE TABLE mailing_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(255),
    emails TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mailing_group_name ON mailing_groups(name);
CREATE INDEX idx_mailing_group_active ON mailing_groups(is_active);

-- Теги
CREATE TABLE tags (
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

CREATE INDEX idx_tag_name ON tags(name);

-- =============================================================================
-- 2. Таблицы с внешними ключами на базовые таблицы
-- =============================================================================

-- Группы приложений
CREATE TABLE application_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    artifact_list_url VARCHAR(512),
    artifact_extension VARCHAR(32),
    update_playbook_path VARCHAR(256),
    batch_grouping_strategy VARCHAR(32) DEFAULT 'by_group' NOT NULL,
    tags_cache VARCHAR(512),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_app_group_name ON application_groups(name);

-- Экземпляры приложений
CREATE TABLE application_instances (
    id SERIAL PRIMARY KEY,
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    group_id INTEGER REFERENCES application_groups(id) ON DELETE SET NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,

    -- Идентификация экземпляра
    instance_name VARCHAR(128) NOT NULL,
    instance_number INTEGER DEFAULT 0 NOT NULL,
    app_type VARCHAR(32) NOT NULL,

    -- Состояние
    status VARCHAR(32) DEFAULT 'unknown',
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Данные от агента (общие)
    path VARCHAR(255),
    log_path VARCHAR(255),
    version VARCHAR(128),
    distr_path VARCHAR(255),

    -- Docker-специфичные поля
    container_id VARCHAR(128),
    container_name VARCHAR(128),
    compose_project_dir VARCHAR(255),
    image VARCHAR(255),
    tag VARCHAR(64),
    eureka_registered BOOLEAN DEFAULT FALSE,

    -- Eureka-специфичные поля
    eureka_url VARCHAR(255),

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
    tags_cache VARCHAR(512),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,

    CONSTRAINT unique_instance_per_server UNIQUE (server_id, instance_name, app_type)
);

CREATE INDEX idx_instance_catalog ON application_instances(catalog_id);
CREATE INDEX idx_instance_group ON application_instances(group_id);
CREATE INDEX idx_instance_server ON application_instances(server_id);
CREATE INDEX idx_instance_status ON application_instances(status);
CREATE INDEX idx_instance_deleted ON application_instances(deleted_at);
CREATE INDEX idx_instance_name ON application_instances(instance_name);
CREATE INDEX idx_instance_type ON application_instances(app_type);

-- События
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(32) NOT NULL,
    description TEXT,
    status VARCHAR(32) DEFAULT 'success',
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    instance_id INTEGER REFERENCES application_instances(id) ON DELETE CASCADE
);

CREATE INDEX idx_event_server ON events(server_id);
CREATE INDEX idx_event_instance ON events(instance_id);
CREATE INDEX idx_event_timestamp ON events(timestamp);

-- Задачи
CREATE TABLE tasks (
    id VARCHAR(36) PRIMARY KEY,
    task_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) DEFAULT 'pending' NOT NULL,
    params JSONB DEFAULT '{}',
    server_id INTEGER REFERENCES servers(id) ON DELETE SET NULL,
    instance_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result TEXT,
    error TEXT,
    progress JSONB DEFAULT '{}',
    pid INTEGER,
    cancelled BOOLEAN DEFAULT FALSE NOT NULL
);

CREATE INDEX idx_task_status ON tasks(status);
CREATE INDEX idx_task_type ON tasks(task_type);
CREATE INDEX idx_task_created_at ON tasks(created_at);

-- =============================================================================
-- 3. Связующие таблицы для тегов
-- =============================================================================

-- Связь ApplicationInstance <-> Tag
CREATE TABLE application_instance_tags (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(64),
    auto_assign_disabled BOOLEAN DEFAULT FALSE NOT NULL,
    CONSTRAINT uq_app_instance_tag UNIQUE (application_id, tag_id)
);

CREATE INDEX idx_app_tags_app ON application_instance_tags(application_id);
CREATE INDEX idx_app_tags_tag ON application_instance_tags(tag_id);

-- Связь ApplicationGroup <-> Tag
CREATE TABLE application_group_tags (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES application_groups(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(64),
    CONSTRAINT uq_app_group_tag UNIQUE (group_id, tag_id)
);

CREATE INDEX idx_group_tags_group ON application_group_tags(group_id);
CREATE INDEX idx_group_tags_tag ON application_group_tags(tag_id);

-- История изменений тегов
CREATE TABLE tag_history (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    tag_id INTEGER REFERENCES tags(id) ON DELETE SET NULL,
    action VARCHAR(20) NOT NULL,
    changed_by VARCHAR(64),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details JSONB
);

CREATE INDEX idx_tag_history_entity ON tag_history(entity_type, entity_id);
CREATE INDEX idx_tag_history_time ON tag_history(changed_at);

-- =============================================================================
-- 4. HAProxy таблицы
-- =============================================================================

-- HAProxy инстансы
CREATE TABLE haproxy_instances (
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

CREATE INDEX idx_haproxy_instance_server ON haproxy_instances(server_id);
CREATE INDEX idx_haproxy_instance_active ON haproxy_instances(is_active);

-- HAProxy бекенды
CREATE TABLE haproxy_backends (
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

CREATE INDEX idx_haproxy_backend_instance ON haproxy_backends(haproxy_instance_id);
CREATE INDEX idx_haproxy_backend_removed ON haproxy_backends(removed_at);

-- HAProxy серверы
CREATE TABLE haproxy_servers (
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

CREATE INDEX idx_haproxy_server_backend ON haproxy_servers(backend_id);
CREATE INDEX idx_haproxy_server_status ON haproxy_servers(status);
CREATE INDEX idx_haproxy_server_removed ON haproxy_servers(removed_at);

-- История статусов HAProxy серверов
CREATE TABLE haproxy_server_status_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER NOT NULL REFERENCES haproxy_servers(id) ON DELETE CASCADE,
    old_status VARCHAR(32),
    new_status VARCHAR(32) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason VARCHAR(64)
);

CREATE INDEX idx_haproxy_history_server ON haproxy_server_status_history(haproxy_server_id);
CREATE INDEX idx_haproxy_history_changed_at ON haproxy_server_status_history(changed_at);

-- История маппингов HAProxy
CREATE TABLE haproxy_mapping_history (
    id SERIAL PRIMARY KEY,
    haproxy_server_id INTEGER NOT NULL REFERENCES haproxy_servers(id) ON DELETE CASCADE,
    old_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    new_application_id INTEGER REFERENCES application_instances(id) ON DELETE SET NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    change_reason VARCHAR(32) NOT NULL,
    mapped_by VARCHAR(64),
    notes TEXT
);

CREATE INDEX idx_haproxy_mapping_history_server ON haproxy_mapping_history(haproxy_server_id);
CREATE INDEX idx_haproxy_mapping_history_changed_at ON haproxy_mapping_history(changed_at);
CREATE INDEX idx_haproxy_mapping_history_reason ON haproxy_mapping_history(change_reason);

-- =============================================================================
-- 5. Eureka таблицы
-- =============================================================================

-- Eureka серверы
CREATE TABLE eureka_servers (
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

CREATE INDEX idx_eureka_server_server ON eureka_servers(server_id);
CREATE INDEX idx_eureka_server_active ON eureka_servers(is_active);
CREATE INDEX idx_eureka_server_removed ON eureka_servers(removed_at);

-- Eureka приложения
CREATE TABLE eureka_applications (
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

CREATE INDEX idx_eureka_application_server ON eureka_applications(eureka_server_id);
CREATE INDEX idx_eureka_application_name ON eureka_applications(app_name);

-- Eureka экземпляры
CREATE TABLE eureka_instances (
    id SERIAL PRIMARY KEY,
    eureka_application_id INTEGER NOT NULL REFERENCES eureka_applications(id) ON DELETE CASCADE,
    instance_id VARCHAR(255) UNIQUE NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    port INTEGER NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'UNKNOWN' NOT NULL,
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

CREATE INDEX idx_eureka_instance_application ON eureka_instances(eureka_application_id);
CREATE INDEX idx_eureka_instance_status ON eureka_instances(status);
CREATE INDEX idx_eureka_instance_instance_id ON eureka_instances(instance_id);
CREATE INDEX idx_eureka_instance_ip ON eureka_instances(ip_address);
CREATE INDEX idx_eureka_instance_removed ON eureka_instances(removed_at);

-- История статусов Eureka экземпляров
CREATE TABLE eureka_instance_status_history (
    id SERIAL PRIMARY KEY,
    eureka_instance_id INTEGER NOT NULL REFERENCES eureka_instances(id) ON DELETE CASCADE,
    old_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255)
);

CREATE INDEX idx_eureka_status_history_instance ON eureka_instance_status_history(eureka_instance_id);
CREATE INDEX idx_eureka_status_history_changed_at ON eureka_instance_status_history(changed_at);

-- Журнал действий над Eureka экземплярами
CREATE TABLE eureka_instance_actions (
    id SERIAL PRIMARY KEY,
    eureka_instance_id INTEGER NOT NULL REFERENCES eureka_instances(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL,
    action_params JSONB,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
    result TEXT,
    error_message TEXT,
    user_id INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_eureka_action_instance ON eureka_instance_actions(eureka_instance_id);
CREATE INDEX idx_eureka_action_type ON eureka_instance_actions(action_type);
CREATE INDEX idx_eureka_action_status ON eureka_instance_actions(status);
CREATE INDEX idx_eureka_action_started_at ON eureka_instance_actions(started_at);

-- =============================================================================
-- 6. Унифицированные маппинги приложений
-- =============================================================================

-- Маппинги приложений на внешние сервисы
CREATE TABLE application_mappings (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    is_manual BOOLEAN DEFAULT FALSE NOT NULL,
    mapped_by VARCHAR(64),
    mapped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    mapping_metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uk_app_entity UNIQUE (application_id, entity_type, entity_id)
);

CREATE INDEX idx_app_mappings_application_id ON application_mappings(application_id);
CREATE INDEX idx_app_mappings_entity ON application_mappings(entity_type, entity_id);

-- История маппингов
CREATE TABLE application_mapping_history (
    id SERIAL PRIMARY KEY,
    mapping_id INTEGER REFERENCES application_mappings(id) ON DELETE SET NULL,
    application_id INTEGER NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by VARCHAR(64),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    reason TEXT
);

CREATE INDEX idx_mapping_history_mapping_id ON application_mapping_history(mapping_id);
CREATE INDEX idx_mapping_history_application_id ON application_mapping_history(application_id);
CREATE INDEX idx_mapping_history_changed_at ON application_mapping_history(changed_at);

-- =============================================================================
-- 7. История версий приложений
-- =============================================================================

CREATE TABLE application_version_history (
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
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    changed_by VARCHAR(20) NOT NULL,
    change_source VARCHAR(50),
    task_id VARCHAR(64),
    notes TEXT
);

CREATE INDEX idx_version_history_instance ON application_version_history(instance_id);
CREATE INDEX idx_version_history_changed_at ON application_version_history(changed_at);
CREATE INDEX idx_version_history_changed_by ON application_version_history(changed_by);
CREATE INDEX idx_version_history_instance_time ON application_version_history(instance_id, changed_at);

-- =============================================================================
-- Завершение
-- =============================================================================

-- Вставка начальной версии миграции (опционально, для совместимости с Alembic)
-- INSERT INTO alembic_version (version_num) VALUES ('initial_clean_install');

COMMENT ON TABLE servers IS 'Физические или виртуальные хосты с FAgent';
COMMENT ON TABLE application_catalog IS 'Справочник типов приложений с настройками по умолчанию';
COMMENT ON TABLE application_groups IS 'Логические группы экземпляров приложений';
COMMENT ON TABLE application_instances IS 'Экземпляры приложений на серверах';
COMMENT ON TABLE events IS 'Журнал событий (start, stop, restart, update)';
COMMENT ON TABLE tasks IS 'Очередь задач для асинхронного выполнения';
COMMENT ON TABLE tags IS 'Теги для маркировки приложений и групп';
COMMENT ON TABLE haproxy_instances IS 'HAProxy инстансы, доступные через FAgent';
COMMENT ON TABLE haproxy_backends IS 'Backend пулы серверов в HAProxy';
COMMENT ON TABLE haproxy_servers IS 'Серверы в HAProxy бекендах';
COMMENT ON TABLE eureka_servers IS 'Eureka Server реестры сервисов';
COMMENT ON TABLE eureka_applications IS 'Приложения, зарегистрированные в Eureka';
COMMENT ON TABLE eureka_instances IS 'Экземпляры сервисов в Eureka';
COMMENT ON TABLE application_mappings IS 'Унифицированные маппинги приложений на внешние сервисы';
COMMENT ON TABLE application_version_history IS 'История изменений версий приложений';
COMMENT ON TABLE orchestrator_playbooks IS 'Ansible playbook-и для оркестрации обновлений';
COMMENT ON TABLE mailing_groups IS 'Группы рассылки email';

-- Готово!
SELECT 'Database schema created successfully!' AS status;

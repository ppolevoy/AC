#!/usr/bin/env python3
"""
Скрипт для добавления поддержки интеграции Eureka.
Добавляет:
- Поле is_eureka_node в таблицу servers
- Таблицы для Eureka интеграции (eureka_servers, eureka_applications, eureka_instances, и др.)
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db

def add_eureka_integration():
    """Добавление поддержки Eureka интеграции"""

    app = create_app()

    with app.app_context():
        print("Adding Eureka integration support")
        print("=" * 60)

        try:
            # SQL для добавления колонки в servers
            sql_add_eureka_node = """
            -- Добавляем поле is_eureka_node в servers
            ALTER TABLE servers
            ADD COLUMN IF NOT EXISTS is_eureka_node BOOLEAN NOT NULL DEFAULT FALSE;
            """

            # SQL для создания таблиц Eureka
            sql_create_eureka_tables = """
            -- Создаем таблицу eureka_servers
            CREATE TABLE IF NOT EXISTS eureka_servers (
                id SERIAL PRIMARY KEY,
                server_id INTEGER NOT NULL,
                eureka_host VARCHAR(255) NOT NULL,
                eureka_port INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                last_sync TIMESTAMP,
                last_error TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                removed_at TIMESTAMP,
                CONSTRAINT fk_eureka_server_server FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE,
                CONSTRAINT uq_eureka_server_per_server UNIQUE (server_id)
            );

            CREATE INDEX IF NOT EXISTS idx_eureka_server_server ON eureka_servers(server_id);
            CREATE INDEX IF NOT EXISTS idx_eureka_server_active ON eureka_servers(is_active);
            CREATE INDEX IF NOT EXISTS idx_eureka_server_removed ON eureka_servers(removed_at);

            -- Создаем таблицу eureka_applications
            CREATE TABLE IF NOT EXISTS eureka_applications (
                id SERIAL PRIMARY KEY,
                eureka_server_id INTEGER NOT NULL,
                app_name VARCHAR(255) NOT NULL,
                instances_count INTEGER DEFAULT 0,
                instances_up INTEGER DEFAULT 0,
                instances_down INTEGER DEFAULT 0,
                instances_paused INTEGER DEFAULT 0,
                last_sync TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_eureka_app_server FOREIGN KEY (eureka_server_id) REFERENCES eureka_servers(id) ON DELETE CASCADE,
                CONSTRAINT uq_eureka_app_per_server UNIQUE (eureka_server_id, app_name)
            );

            CREATE INDEX IF NOT EXISTS idx_eureka_application_server ON eureka_applications(eureka_server_id);
            CREATE INDEX IF NOT EXISTS idx_eureka_application_name ON eureka_applications(app_name);

            -- Создаем таблицу eureka_instances
            CREATE TABLE IF NOT EXISTS eureka_instances (
                id SERIAL PRIMARY KEY,
                eureka_application_id INTEGER NOT NULL,
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
                application_id INTEGER,
                is_manual_mapping BOOLEAN NOT NULL DEFAULT FALSE,
                mapped_by VARCHAR(64),
                mapped_at TIMESTAMP,
                mapping_notes TEXT,
                last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                removed_at TIMESTAMP,
                CONSTRAINT fk_eureka_instance_application FOREIGN KEY (eureka_application_id) REFERENCES eureka_applications(id) ON DELETE CASCADE,
                CONSTRAINT fk_eureka_instance_ac_app FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_eureka_instance_application ON eureka_instances(eureka_application_id);
            CREATE INDEX IF NOT EXISTS idx_eureka_instance_status ON eureka_instances(status);
            CREATE INDEX IF NOT EXISTS idx_eureka_instance_instance_id ON eureka_instances(instance_id);
            CREATE INDEX IF NOT EXISTS idx_eureka_instance_ip ON eureka_instances(ip_address);
            CREATE INDEX IF NOT EXISTS idx_eureka_instance_ac_app ON eureka_instances(application_id);
            CREATE INDEX IF NOT EXISTS idx_eureka_instance_removed ON eureka_instances(removed_at);

            -- Создаем таблицу eureka_instance_status_history
            CREATE TABLE IF NOT EXISTS eureka_instance_status_history (
                id SERIAL PRIMARY KEY,
                eureka_instance_id INTEGER NOT NULL,
                old_status VARCHAR(50),
                new_status VARCHAR(50) NOT NULL,
                reason TEXT,
                changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                changed_by VARCHAR(255),
                CONSTRAINT fk_eureka_status_history_instance FOREIGN KEY (eureka_instance_id) REFERENCES eureka_instances(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_eureka_status_history_instance ON eureka_instance_status_history(eureka_instance_id);
            CREATE INDEX IF NOT EXISTS idx_eureka_status_history_changed_at ON eureka_instance_status_history(changed_at);

            -- Создаем таблицу eureka_instance_actions
            CREATE TABLE IF NOT EXISTS eureka_instance_actions (
                id SERIAL PRIMARY KEY,
                eureka_instance_id INTEGER NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                action_params JSONB,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                result TEXT,
                error_message TEXT,
                user_id INTEGER,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                CONSTRAINT fk_eureka_action_instance FOREIGN KEY (eureka_instance_id) REFERENCES eureka_instances(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_eureka_action_instance ON eureka_instance_actions(eureka_instance_id);
            CREATE INDEX IF NOT EXISTS idx_eureka_action_type ON eureka_instance_actions(action_type);
            CREATE INDEX IF NOT EXISTS idx_eureka_action_status ON eureka_instance_actions(status);
            CREATE INDEX IF NOT EXISTS idx_eureka_action_started_at ON eureka_instance_actions(started_at);
            """

            print("\n1. Adding is_eureka_node column to servers table...")
            db.session.execute(db.text(sql_add_eureka_node))
            print("   ✓ Column added successfully")

            print("\n2. Creating Eureka tables...")
            db.session.execute(db.text(sql_create_eureka_tables))
            print("   ✓ Eureka tables created successfully")

            db.session.commit()

            print("\n" + "=" * 60)
            print("Eureka integration migration completed successfully!")
            print("=" * 60)

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error during migration: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == '__main__':
    add_eureka_integration()

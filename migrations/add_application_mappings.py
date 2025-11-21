#!/usr/bin/env python3
"""
Скрипт миграции для создания унифицированных таблиц маппингов приложений.
Создает:
- application_mappings - основная таблица маппингов
- application_mapping_history - история изменений маппингов
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def add_application_mappings():
    """Создание таблиц для унифицированных маппингов приложений"""

    app = create_app()

    with app.app_context():
        print("Creating unified application mappings tables")
        print("=" * 60)

        try:
            # SQL для создания таблицы application_mappings
            sql_create_mappings = """
            -- Создаем таблицу application_mappings
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

            -- Индексы для application_mappings
            CREATE INDEX IF NOT EXISTS idx_app_mappings_application_id
            ON application_mappings(application_id);

            CREATE INDEX IF NOT EXISTS idx_app_mappings_entity
            ON application_mappings(entity_type, entity_id);

            CREATE INDEX IF NOT EXISTS idx_app_mappings_active
            ON application_mappings(is_active) WHERE is_active = TRUE;

            -- Комментарии
            COMMENT ON TABLE application_mappings IS
            'Унифицированная таблица маппингов приложений на внешние сервисы (HAProxy, Eureka и т.д.)';

            COMMENT ON COLUMN application_mappings.entity_type IS
            'Тип сущности: haproxy_server, eureka_instance';

            COMMENT ON COLUMN application_mappings.is_manual IS
            'Флаг ручного маппинга (TRUE - ручной, FALSE - автоматический)';
            """

            # SQL для создания таблицы application_mapping_history
            sql_create_history = """
            -- Создаем таблицу application_mapping_history
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

            -- Индексы для application_mapping_history
            CREATE INDEX IF NOT EXISTS idx_mapping_history_mapping_id
            ON application_mapping_history(mapping_id);

            CREATE INDEX IF NOT EXISTS idx_mapping_history_application_id
            ON application_mapping_history(application_id);

            CREATE INDEX IF NOT EXISTS idx_mapping_history_changed_at
            ON application_mapping_history(changed_at DESC);

            -- Комментарии
            COMMENT ON TABLE application_mapping_history IS
            'История изменений маппингов приложений';

            COMMENT ON COLUMN application_mapping_history.action IS
            'Действие: created, updated, deleted, deactivated, activated';
            """

            print("\nStep 1: Creating application_mappings table...")
            print("-" * 60)
            db.session.execute(db.text(sql_create_mappings))
            db.session.commit()
            print("✓ application_mappings table created")

            print("\nStep 2: Creating application_mapping_history table...")
            print("-" * 60)
            db.session.execute(db.text(sql_create_history))
            db.session.commit()
            print("✓ application_mapping_history table created")

            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("\nCreated tables:")
            print("  - application_mappings")
            print("  - application_mapping_history")
            print("\nIndexes created:")
            print("  - idx_app_mappings_application_id")
            print("  - idx_app_mappings_entity")
            print("  - idx_app_mappings_active (partial)")
            print("  - idx_mapping_history_mapping_id")
            print("  - idx_mapping_history_application_id")
            print("  - idx_mapping_history_changed_at")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {str(e)}")
            print("=" * 60)
            sys.exit(1)


if __name__ == '__main__':
    add_application_mappings()

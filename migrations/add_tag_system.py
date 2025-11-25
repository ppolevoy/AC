#!/usr/bin/env python3
"""
Миграция: Добавление системы тегов

Создает таблицы:
- tags - основная таблица тегов
- application_instance_tags - связь тегов с экземплярами
- application_group_tags - связь тегов с группами
- tag_history - история изменений

Добавляет поля:
- tags_cache в application_instances
- tags_cache в application_groups
"""

import psycopg2
import os

def get_connection():
    """Получить подключение к БД"""
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', '192.168.8.46'),
        port=os.environ.get('POSTGRES_PORT', '5417'),
        database=os.environ.get('POSTGRES_DB', 'appcontrol'),
        user=os.environ.get('POSTGRES_USER', 'fakadm'),
        password=os.environ.get('POSTGRES_PASSWORD', 'fakadm')
    )

def upgrade():
    """Применить миграцию"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Создание таблицы tags
        cursor.execute("""
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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_tag_name ON tags(name);
        """)
        print("✓ Создана таблица tags")

        # Создание таблицы application_instance_tags
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_instance_tags (
                id SERIAL PRIMARY KEY,
                application_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_by VARCHAR(64),
                CONSTRAINT uq_app_instance_tag UNIQUE(application_id, tag_id)
            );

            CREATE INDEX IF NOT EXISTS idx_app_tags_app ON application_instance_tags(application_id);
            CREATE INDEX IF NOT EXISTS idx_app_tags_tag ON application_instance_tags(tag_id);
        """)
        print("✓ Создана таблица application_instance_tags")

        # Создание таблицы application_group_tags
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_group_tags (
                id SERIAL PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES application_groups(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_by VARCHAR(64),
                CONSTRAINT uq_app_group_tag UNIQUE(group_id, tag_id)
            );

            CREATE INDEX IF NOT EXISTS idx_group_tags_group ON application_group_tags(group_id);
            CREATE INDEX IF NOT EXISTS idx_group_tags_tag ON application_group_tags(tag_id);
        """)
        print("✓ Создана таблица application_group_tags")

        # Создание таблицы tag_history
        cursor.execute("""
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
        """)
        print("✓ Создана таблица tag_history")

        # Добавление поля tags_cache в application_instances
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'application_instances'
                    AND column_name = 'tags_cache'
                ) THEN
                    ALTER TABLE application_instances ADD COLUMN tags_cache VARCHAR(512);
                    CREATE INDEX idx_instance_tags_cache ON application_instances(tags_cache);
                END IF;
            END $$;
        """)
        print("✓ Добавлено поле tags_cache в application_instances")

        # Добавление поля tags_cache в application_groups
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'application_groups'
                    AND column_name = 'tags_cache'
                ) THEN
                    ALTER TABLE application_groups ADD COLUMN tags_cache VARCHAR(512);
                    CREATE INDEX idx_group_tags_cache ON application_groups(tags_cache);
                END IF;
            END $$;
        """)
        print("✓ Добавлено поле tags_cache в application_groups")

        # Вставка предустановленных тегов
        cursor.execute("""
            INSERT INTO tags (name, display_name, icon, tag_type, css_class) VALUES
                ('online', 'Online', '●', 'status', 'tag-status-online'),
                ('offline', 'Offline', '●', 'status', 'tag-status-offline'),
                ('warning', 'Warning', '●', 'status', 'tag-status-warning'),
                ('production', 'Production', '🏢', 'env', 'tag-env-prod'),
                ('test', 'Test', '🧪', 'env', 'tag-env-test'),
                ('development', 'Development', '🔧', 'env', 'tag-env-dev'),
                ('release', 'Release', '✓', 'version', 'tag-version-release'),
                ('snapshot', 'Snapshot', '📸', 'version', 'tag-version-snapshot'),
                ('dev', 'Dev', '🔹', 'version', 'tag-version-dev'),
                ('critical', 'Critical', '⚠', 'special', 'tag-critical'),
                ('monitored', 'Monitored', '📊', 'special', 'tag-monitored'),
                ('deprecated', 'Deprecated', '🗑', 'special', 'tag-deprecated')
            ON CONFLICT (name) DO NOTHING;
        """)
        print("✓ Добавлены предустановленные теги")

        conn.commit()
        print("\n✅ Миграция успешно применена!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Ошибка миграции: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def downgrade():
    """Откатить миграцию"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Удаление полей tags_cache
        cursor.execute("""
            ALTER TABLE application_instances DROP COLUMN IF EXISTS tags_cache;
            ALTER TABLE application_groups DROP COLUMN IF EXISTS tags_cache;
        """)

        # Удаление таблиц
        cursor.execute("""
            DROP TABLE IF EXISTS tag_history;
            DROP TABLE IF EXISTS application_group_tags;
            DROP TABLE IF EXISTS application_instance_tags;
            DROP TABLE IF EXISTS tags;
        """)

        conn.commit()
        print("✅ Откат миграции выполнен")

    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка отката: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'downgrade':
        downgrade()
    else:
        upgrade()

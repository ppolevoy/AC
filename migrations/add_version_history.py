#!/usr/bin/env python3
"""
Миграция: Добавление таблицы истории версий приложений

Создает таблицу:
- application_version_history - история изменений версий приложений
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
        # Создание таблицы application_version_history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_version_history (
                id SERIAL PRIMARY KEY,
                instance_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,

                -- Данные о версии
                old_version VARCHAR(128),
                new_version VARCHAR(128) NOT NULL,
                old_distr_path VARCHAR(255),
                new_distr_path VARCHAR(255),

                -- Docker-специфичные поля
                old_tag VARCHAR(64),
                new_tag VARCHAR(64),
                old_image VARCHAR(255),
                new_image VARCHAR(255),

                -- Метаданные изменения
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                changed_by VARCHAR(20) NOT NULL,
                change_source VARCHAR(50),

                -- Дополнительные данные
                task_id VARCHAR(64),
                notes TEXT
            );
        """)
        print("Created table application_version_history")

        # Создание индексов
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_version_history_instance
                ON application_version_history(instance_id);
            CREATE INDEX IF NOT EXISTS idx_version_history_changed_at
                ON application_version_history(changed_at);
            CREATE INDEX IF NOT EXISTS idx_version_history_changed_by
                ON application_version_history(changed_by);
            CREATE INDEX IF NOT EXISTS idx_version_history_instance_time
                ON application_version_history(instance_id, changed_at);
        """)
        print("Created indexes for application_version_history")

        conn.commit()
        print("\nMigration successfully applied!")

    except Exception as e:
        conn.rollback()
        print(f"\nMigration error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def downgrade():
    """Откатить миграцию"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("DROP TABLE IF EXISTS application_version_history;")
        conn.commit()
        print("Rollback completed")
    except Exception as e:
        conn.rollback()
        print(f"Rollback error: {e}")
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

#!/usr/bin/env python3
"""
Миграция: Добавление таблицы tasks для персистентного хранения задач

Создает таблицу:
- tasks - хранение всех задач (активных и завершённых)

Решает проблему потери задач при перезагрузке сервера.
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
        # Создание таблицы tasks
        cursor.execute("""
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
                progress JSONB DEFAULT '{}'
            );
        """)
        print("Created table tasks")

        # Создание индексов для производительности
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks(status);
        """)
        print("Created index idx_tasks_status")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_created_at
                ON tasks(created_at DESC);
        """)
        print("Created index idx_tasks_created_at")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_server_id
                ON tasks(server_id);
        """)
        print("Created index idx_tasks_server_id")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_instance_id
                ON tasks(instance_id);
        """)
        print("Created index idx_tasks_instance_id")

        # Комбинированный индекс для фильтрации по статусу и времени
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status_created
                ON tasks(status, created_at DESC);
        """)
        print("Created index idx_tasks_status_created")

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
        # Удаляем индексы
        cursor.execute("DROP INDEX IF EXISTS idx_tasks_status;")
        cursor.execute("DROP INDEX IF EXISTS idx_tasks_created_at;")
        cursor.execute("DROP INDEX IF EXISTS idx_tasks_server_id;")
        cursor.execute("DROP INDEX IF EXISTS idx_tasks_instance_id;")
        cursor.execute("DROP INDEX IF EXISTS idx_tasks_status_created;")
        print("Dropped indexes")

        # Удаляем таблицу
        cursor.execute("DROP TABLE IF EXISTS tasks;")
        print("Dropped table tasks")

        conn.commit()
        print("\nRollback completed")
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

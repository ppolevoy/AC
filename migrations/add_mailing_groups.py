#!/usr/bin/env python3
"""
Миграция: Добавление таблицы групп рассылки

Создает таблицу:
- mailing_groups - группы email-адресов для рассылки отчётов
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
        # Создание таблицы mailing_groups
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mailing_groups (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description VARCHAR(255),
                emails TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("Created table mailing_groups")

        # Создание индексов
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mailing_group_name
                ON mailing_groups(name);
            CREATE INDEX IF NOT EXISTS idx_mailing_group_active
                ON mailing_groups(is_active);
        """)
        print("Created indexes for mailing_groups")

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
        cursor.execute("DROP TABLE IF EXISTS mailing_groups;")
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

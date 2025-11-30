#!/usr/bin/env python3
"""
Миграция для добавления полей отмены задачи.
Добавляет поля pid и cancelled в таблицу tasks.
"""
import psycopg2
import os
import sys

def get_db_connection():
    """Получить соединение с БД из переменных окружения"""
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'pg-fak'),
        port=os.environ.get('POSTGRES_PORT', '5432'),
        user=os.environ.get('POSTGRES_USER', 'fak'),
        password=os.environ.get('POSTGRES_PASSWORD', 'fak'),
        database=os.environ.get('POSTGRES_DB', 'fak')
    )

def migrate():
    """Выполнить миграцию"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Проверяем существование колонки pid
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'tasks' AND column_name = 'pid'
        """)

        if not cur.fetchone():
            print("Adding 'pid' column to tasks table...")
            cur.execute("ALTER TABLE tasks ADD COLUMN pid INTEGER")
            print("Column 'pid' added successfully")
        else:
            print("Column 'pid' already exists, skipping")

        # Проверяем существование колонки cancelled
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'tasks' AND column_name = 'cancelled'
        """)

        if not cur.fetchone():
            print("Adding 'cancelled' column to tasks table...")
            cur.execute("ALTER TABLE tasks ADD COLUMN cancelled BOOLEAN NOT NULL DEFAULT FALSE")
            print("Column 'cancelled' added successfully")
        else:
            print("Column 'cancelled' already exists, skipping")

        conn.commit()
        print("Migration completed successfully!")
        return True

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        return False

    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)

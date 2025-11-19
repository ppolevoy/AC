#!/usr/bin/env python3
"""
Скрипт миграции для добавления функциональности отслеживания ошибок HAProxy бэкендов.
Добавляет:
- last_fetch_status (String) - статус последней попытки получения данных ('success', 'failed', 'unknown')
- last_fetch_error (Text) - сообщение об ошибке при неудаче
- last_fetch_at (DateTime) - время последней попытки получения данных
- idx_haproxy_backend_fetch_status - индекс для быстрой фильтрации
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def add_haproxy_backend_error_tracking():
    """Добавление функциональности отслеживания ошибок HAProxy бэкендов"""

    app = create_app()

    with app.app_context():
        print("Adding error tracking to HAProxy backends")
        print("=" * 60)

        try:
            # SQL для добавления полей отслеживания ошибок
            sql_add_fields = """
            -- Добавляем поле для статуса последней попытки получения данных
            ALTER TABLE haproxy_backends
            ADD COLUMN IF NOT EXISTS last_fetch_status VARCHAR(20) DEFAULT 'unknown';

            -- Добавляем поле для сообщения об ошибке
            ALTER TABLE haproxy_backends
            ADD COLUMN IF NOT EXISTS last_fetch_error TEXT;

            -- Добавляем поле для времени последней попытки
            ALTER TABLE haproxy_backends
            ADD COLUMN IF NOT EXISTS last_fetch_at TIMESTAMP;

            -- Создаем индекс для быстрой фильтрации по статусу
            CREATE INDEX IF NOT EXISTS idx_haproxy_backend_fetch_status
            ON haproxy_backends(last_fetch_status);

            -- Комментарии для документирования
            COMMENT ON COLUMN haproxy_backends.last_fetch_status IS
            'Статус последней попытки получения данных: success, failed, unknown';

            COMMENT ON COLUMN haproxy_backends.last_fetch_error IS
            'Сообщение об ошибке при неудачной попытке получения данных от агента';

            COMMENT ON COLUMN haproxy_backends.last_fetch_at IS
            'Время последней попытки получения данных от агента';
            """

            print("\nExecuting SQL migration...")
            print("-" * 60)

            # Выполняем SQL
            db.session.execute(db.text(sql_add_fields))
            db.session.commit()

            print("\n✓ Successfully added backend error tracking:")
            print("  - last_fetch_status (VARCHAR(20) DEFAULT 'unknown')")
            print("  - last_fetch_error (TEXT)")
            print("  - last_fetch_at (TIMESTAMP)")
            print("  - idx_haproxy_backend_fetch_status (INDEX)")
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("\nNote: All existing backends have last_fetch_status='unknown' by default")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {str(e)}")
            print("=" * 60)
            sys.exit(1)


if __name__ == '__main__':
    add_haproxy_backend_error_tracking()

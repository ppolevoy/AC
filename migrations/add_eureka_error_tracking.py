#!/usr/bin/env python3
"""
Скрипт миграции для добавления функциональности отслеживания ошибок Eureka синхронизации.
Добавляет:
- В eureka_servers: consecutive_failures (для отслеживания серии сбоев)
- В eureka_applications: last_fetch_status, last_fetch_error, last_fetch_at
- Индексы для быстрой фильтрации
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def add_eureka_error_tracking():
    """Добавление функциональности отслеживания ошибок Eureka синхронизации"""

    app = create_app()

    with app.app_context():
        print("Adding error tracking to Eureka servers and applications")
        print("=" * 60)

        try:
            # SQL для добавления полей отслеживания ошибок
            sql_add_fields = """
            -- Добавляем поле consecutive_failures в eureka_servers
            ALTER TABLE eureka_servers
            ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER DEFAULT 0;

            -- Добавляем поля для отслеживания ошибок приложений в eureka_applications
            ALTER TABLE eureka_applications
            ADD COLUMN IF NOT EXISTS last_fetch_status VARCHAR(20) DEFAULT 'unknown';

            ALTER TABLE eureka_applications
            ADD COLUMN IF NOT EXISTS last_fetch_error TEXT;

            ALTER TABLE eureka_applications
            ADD COLUMN IF NOT EXISTS last_fetch_at TIMESTAMP;

            -- Создаем индексы для быстрой фильтрации
            CREATE INDEX IF NOT EXISTS idx_eureka_app_fetch_status
            ON eureka_applications(last_fetch_status);

            -- Комментарии для документирования
            COMMENT ON COLUMN eureka_servers.consecutive_failures IS
            'Счетчик последовательных неудачных попыток синхронизации';

            COMMENT ON COLUMN eureka_applications.last_fetch_status IS
            'Статус последней попытки получения данных: success, failed, unknown';

            COMMENT ON COLUMN eureka_applications.last_fetch_error IS
            'Сообщение об ошибке при неудачной попытке получения данных от агента';

            COMMENT ON COLUMN eureka_applications.last_fetch_at IS
            'Время последней попытки получения данных от агента';
            """

            print("\nExecuting SQL migration...")
            print("-" * 60)

            # Выполняем SQL
            db.session.execute(db.text(sql_add_fields))
            db.session.commit()

            print("\n✓ Successfully added Eureka error tracking:")
            print("  eureka_servers:")
            print("    - consecutive_failures (INTEGER DEFAULT 0)")
            print("  eureka_applications:")
            print("    - last_fetch_status (VARCHAR(20) DEFAULT 'unknown')")
            print("    - last_fetch_error (TEXT)")
            print("    - last_fetch_at (TIMESTAMP)")
            print("    - idx_eureka_app_fetch_status (INDEX)")
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("\nNote: All existing applications have last_fetch_status='unknown' by default")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {str(e)}")
            print("=" * 60)
            sys.exit(1)


if __name__ == '__main__':
    add_eureka_error_tracking()

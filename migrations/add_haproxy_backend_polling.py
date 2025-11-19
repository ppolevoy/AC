#!/usr/bin/env python3
"""
Скрипт миграции для добавления функциональности управления опросом HAProxy бэкендов.
Добавляет:
- enable_polling (BOOLEAN) - флаг включения/выключения опроса конкретного бэкенда
- idx_haproxy_backend_polling - индекс для быстрой фильтрации
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def add_haproxy_backend_polling():
    """Добавление функциональности управления опросом HAProxy бэкендов"""

    app = create_app()

    with app.app_context():
        print("Adding backend polling control to HAProxy backends")
        print("=" * 60)

        try:
            # SQL для добавления поля enable_polling и индекса
            sql_add_fields = """
            -- Добавляем поле enable_polling для управления опросом
            ALTER TABLE haproxy_backends
            ADD COLUMN IF NOT EXISTS enable_polling BOOLEAN NOT NULL DEFAULT TRUE;

            -- Создаем индекс для быстрой фильтрации по enable_polling
            CREATE INDEX IF NOT EXISTS idx_haproxy_backend_polling
            ON haproxy_backends(enable_polling);

            -- Комментарий для документирования
            COMMENT ON COLUMN haproxy_backends.enable_polling IS
            'Флаг включения/выключения опроса бэкенда. При FALSE бэкенд не опрашивается и помечается как removed_at';
            """

            print("\nExecuting SQL migration...")
            print("-" * 60)

            # Выполняем SQL
            db.session.execute(db.text(sql_add_fields))
            db.session.commit()

            print("\n✓ Successfully added backend polling control:")
            print("  - enable_polling (BOOLEAN NOT NULL DEFAULT TRUE)")
            print("  - idx_haproxy_backend_polling (INDEX)")
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("\nNote: All existing backends have enable_polling=TRUE by default")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {str(e)}")
            print("=" * 60)
            sys.exit(1)


if __name__ == '__main__':
    add_haproxy_backend_polling()

#!/usr/bin/env python3
"""
Скрипт для добавления Docker-специфичных полей в таблицу application_instances.
Добавляет:
- image (VARCHAR) - название Docker образа
- tag (VARCHAR) - версия/тег образа
- eureka_registered (BOOLEAN) - флаг регистрации в Eureka
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db

def add_docker_fields():
    """Добавление Docker-специфичных полей в application_instances"""

    app = create_app()

    with app.app_context():
        print("Adding Docker-specific fields to application_instances")
        print("=" * 60)

        try:
            # SQL для добавления новых колонок
            sql_add_fields = """
            -- Добавляем поле image для хранения названия Docker образа
            ALTER TABLE application_instances
            ADD COLUMN IF NOT EXISTS image VARCHAR(255);

            -- Добавляем поле tag для хранения версии/тега образа
            ALTER TABLE application_instances
            ADD COLUMN IF NOT EXISTS tag VARCHAR(64);

            -- Добавляем поле eureka_registered для флага регистрации в Eureka
            ALTER TABLE application_instances
            ADD COLUMN IF NOT EXISTS eureka_registered BOOLEAN DEFAULT FALSE;
            """

            print("\nExecuting SQL migration...")
            print("-" * 60)

            # Выполняем SQL
            db.session.execute(db.text(sql_add_fields))
            db.session.commit()

            print("\n✓ Successfully added Docker-specific fields:")
            print("  - image (VARCHAR(255))")
            print("  - tag (VARCHAR(64))")
            print("  - eureka_registered (BOOLEAN)")
            print("\n" + "=" * 60)
            print("Migration completed successfully!")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {str(e)}")
            print("=" * 60)
            sys.exit(1)


if __name__ == '__main__':
    add_docker_fields()

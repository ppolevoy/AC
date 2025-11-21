#!/usr/bin/env python3
"""
Скрипт миграции для удаления старых колонок маппинга из таблиц haproxy_servers и eureka_instances.
Эти колонки больше не используются после перехода на унифицированную таблицу application_mappings.
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db


def drop_old_mapping_columns():
    """Удаление старых колонок маппинга"""

    app = create_app()

    with app.app_context():
        print("Dropping old mapping columns from haproxy_servers and eureka_instances")
        print("=" * 60)

        try:
            # SQL для удаления колонок из haproxy_servers
            sql_haproxy = """
            -- Удаляем индекс по application_id
            DROP INDEX IF EXISTS idx_haproxy_server_application;

            -- Удаляем внешний ключ на application_instances
            ALTER TABLE haproxy_servers
            DROP CONSTRAINT IF EXISTS haproxy_servers_application_id_fkey;

            -- Удаляем колонки
            ALTER TABLE haproxy_servers
            DROP COLUMN IF EXISTS application_id,
            DROP COLUMN IF EXISTS is_manual_mapping,
            DROP COLUMN IF EXISTS mapped_by,
            DROP COLUMN IF EXISTS mapped_at,
            DROP COLUMN IF EXISTS mapping_notes;
            """

            # SQL для удаления колонок из eureka_instances
            sql_eureka = """
            -- Удаляем индекс по application_id
            DROP INDEX IF EXISTS idx_eureka_instance_ac_app;

            -- Удаляем внешний ключ на application_instances
            ALTER TABLE eureka_instances
            DROP CONSTRAINT IF EXISTS eureka_instances_application_id_fkey;

            -- Удаляем колонки
            ALTER TABLE eureka_instances
            DROP COLUMN IF EXISTS application_id,
            DROP COLUMN IF EXISTS is_manual_mapping,
            DROP COLUMN IF EXISTS mapped_by,
            DROP COLUMN IF EXISTS mapped_at,
            DROP COLUMN IF EXISTS mapping_notes;
            """

            print("\nStep 1: Dropping columns from haproxy_servers...")
            print("-" * 60)
            db.session.execute(db.text(sql_haproxy))
            db.session.commit()
            print("✓ Columns dropped from haproxy_servers")

            print("\nStep 2: Dropping columns from eureka_instances...")
            print("-" * 60)
            db.session.execute(db.text(sql_eureka))
            db.session.commit()
            print("✓ Columns dropped from eureka_instances")

            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("\nDropped columns:")
            print("  haproxy_servers:")
            print("    - application_id")
            print("    - is_manual_mapping")
            print("    - mapped_by")
            print("    - mapped_at")
            print("    - mapping_notes")
            print("  eureka_instances:")
            print("    - application_id")
            print("    - is_manual_mapping")
            print("    - mapped_by")
            print("    - mapped_at")
            print("    - mapping_notes")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {str(e)}")
            print("=" * 60)
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    drop_old_mapping_columns()

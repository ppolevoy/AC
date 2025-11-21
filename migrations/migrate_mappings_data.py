#!/usr/bin/env python3
"""
Скрипт миграции данных маппингов из старых таблиц в новую унифицированную таблицу.
Переносит:
1. HAProxy маппинги из haproxy_servers в application_mappings
2. Eureka маппинги из eureka_instances в application_mappings
3. Историю маппингов из haproxy_mapping_history в application_mapping_history
"""

import os
import sys
from datetime import datetime

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models.application_mapping import ApplicationMapping, ApplicationMappingHistory, MappingType


def migrate_haproxy_mappings():
    """Миграция HAProxy маппингов"""
    print("\nMigrating HAProxy mappings...")
    print("-" * 60)

    # SQL для выборки существующих маппингов HAProxy
    sql_select = """
    SELECT
        hs.id as entity_id,
        hs.application_id,
        hs.is_manual_mapping as is_manual,
        hs.mapped_by,
        hs.mapped_at,
        hs.mapping_notes as notes,
        hb.backend_name,
        hs.server_name,
        hs.addr
    FROM haproxy_servers hs
    LEFT JOIN haproxy_backends hb ON hs.backend_id = hb.id
    WHERE hs.application_id IS NOT NULL
    AND hs.removed_at IS NULL
    """

    result = db.session.execute(db.text(sql_select))
    rows = result.fetchall()

    migrated = 0
    skipped = 0

    for row in rows:
        # Проверяем, не существует ли уже маппинг
        existing = ApplicationMapping.query.filter_by(
            application_id=row.application_id,
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=row.entity_id
        ).first()

        if existing:
            skipped += 1
            continue

        # Создаем новый маппинг
        mapping = ApplicationMapping(
            application_id=row.application_id,
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=row.entity_id,
            is_manual=row.is_manual or False,
            mapped_by=row.mapped_by,
            mapped_at=row.mapped_at or datetime.utcnow(),
            notes=row.notes,
            is_active=True,
            metadata={
                'backend_name': row.backend_name,
                'server_name': row.server_name,
                'address': row.addr
            }
        )
        db.session.add(mapping)
        migrated += 1

    db.session.commit()
    print(f"✓ HAProxy mappings: {migrated} migrated, {skipped} skipped (already exist)")
    return migrated


def migrate_haproxy_history():
    """Миграция истории HAProxy маппингов"""
    print("\nMigrating HAProxy mapping history...")
    print("-" * 60)

    # SQL для выборки истории
    sql_select = """
    SELECT
        hmh.haproxy_server_id as entity_id,
        hmh.old_application_id,
        hmh.new_application_id,
        hmh.changed_at,
        hmh.change_reason,
        hmh.mapped_by,
        hmh.notes
    FROM haproxy_mapping_history hmh
    ORDER BY hmh.changed_at
    """

    result = db.session.execute(db.text(sql_select))
    rows = result.fetchall()

    migrated = 0

    for row in rows:
        # Определяем действие
        if row.old_application_id is None and row.new_application_id is not None:
            action = 'created'
            application_id = row.new_application_id
        elif row.old_application_id is not None and row.new_application_id is None:
            action = 'deleted'
            application_id = row.old_application_id
        else:
            action = 'updated'
            application_id = row.new_application_id or row.old_application_id

        # Находим соответствующий маппинг для ссылки
        mapping = ApplicationMapping.query.filter_by(
            application_id=application_id,
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=row.entity_id
        ).first()

        # Создаем запись в истории
        history = ApplicationMappingHistory(
            mapping_id=mapping.id if mapping else None,
            application_id=application_id,
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=row.entity_id,
            action=action,
            old_values={'application_id': row.old_application_id} if row.old_application_id else None,
            new_values={'application_id': row.new_application_id} if row.new_application_id else None,
            changed_by=row.mapped_by,
            changed_at=row.changed_at or datetime.utcnow(),
            reason=row.notes
        )
        db.session.add(history)
        migrated += 1

    db.session.commit()
    print(f"✓ HAProxy history: {migrated} records migrated")
    return migrated


def migrate_eureka_mappings():
    """Миграция Eureka маппингов"""
    print("\nMigrating Eureka mappings...")
    print("-" * 60)

    # SQL для выборки существующих маппингов Eureka
    sql_select = """
    SELECT
        ei.id as entity_id,
        ei.application_id,
        ei.is_manual_mapping as is_manual,
        ei.mapped_by,
        ei.mapped_at,
        ei.mapping_notes as notes,
        ea.app_name as service_name,
        ei.instance_id,
        ei.ip_address || ':' || ei.port as eureka_url
    FROM eureka_instances ei
    LEFT JOIN eureka_applications ea ON ei.eureka_application_id = ea.id
    WHERE ei.application_id IS NOT NULL
    AND ei.removed_at IS NULL
    """

    result = db.session.execute(db.text(sql_select))
    rows = result.fetchall()

    migrated = 0
    skipped = 0

    for row in rows:
        # Проверяем, не существует ли уже маппинг
        existing = ApplicationMapping.query.filter_by(
            application_id=row.application_id,
            entity_type=MappingType.EUREKA_INSTANCE.value,
            entity_id=row.entity_id
        ).first()

        if existing:
            skipped += 1
            continue

        # Создаем новый маппинг
        mapping = ApplicationMapping(
            application_id=row.application_id,
            entity_type=MappingType.EUREKA_INSTANCE.value,
            entity_id=row.entity_id,
            is_manual=row.is_manual or False,
            mapped_by=row.mapped_by,
            mapped_at=row.mapped_at or datetime.utcnow(),
            notes=row.notes,
            is_active=True,
            metadata={
                'service_name': row.service_name,
                'instance_id': row.instance_id,
                'eureka_url': row.eureka_url
            }
        )
        db.session.add(mapping)
        migrated += 1

    db.session.commit()
    print(f"✓ Eureka mappings: {migrated} migrated, {skipped} skipped (already exist)")
    return migrated


def run_migration():
    """Запуск полной миграции данных"""

    app = create_app()

    with app.app_context():
        print("Migrating mapping data to unified tables")
        print("=" * 60)

        try:
            # Проверяем существование таблиц
            sql_check = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'application_mappings'
            );
            """
            result = db.session.execute(db.text(sql_check))
            if not result.scalar():
                print("\n✗ Error: application_mappings table does not exist!")
                print("Please run add_application_mappings.py first.")
                sys.exit(1)

            # Выполняем миграцию
            haproxy_count = migrate_haproxy_mappings()
            haproxy_history_count = migrate_haproxy_history()
            eureka_count = migrate_eureka_mappings()

            print("\n" + "=" * 60)
            print("Data migration completed successfully!")
            print("\nSummary:")
            print(f"  - HAProxy mappings: {haproxy_count}")
            print(f"  - HAProxy history:  {haproxy_history_count}")
            print(f"  - Eureka mappings:  {eureka_count}")
            print(f"  - Total mappings:   {haproxy_count + eureka_count}")

        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {str(e)}")
            print("=" * 60)
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    run_migration()

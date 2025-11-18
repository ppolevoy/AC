#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция рефакторинга структуры БД для Application Control System
=================================================================

Цель: Привести структуру БД к правильной концепции:
- application_catalog - справочник приложений
- application_instances - экземпляры приложений на серверах
- application_groups - группы для управления экземплярами

Изменения:
1. Создание таблицы application_catalog
2. Переименование таблицы applications в application_instances
3. Добавление полей в application_instances (catalog_id, custom_artifact_url, last_seen, deleted_at)
4. Добавление catalog_id в application_groups
5. Удаление старой таблицы application_instances (junction table)
6. Переименование application_id в instance_id в events
7. Заполнение application_catalog из существующих данных
8. Связывание instances с catalog

ВАЖНО: Это комплекс разработки, потеря данных не критична.
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Выполнение миграции"""
    app = create_app()

    with app.app_context():
        logger.info("=" * 80)
        logger.info("НАЧАЛО МИГРАЦИИ: Рефакторинг структуры БД")
        logger.info("=" * 80)

        try:
            # Шаг 1: Создание таблицы application_catalog
            logger.info("\n[Шаг 1] Создание таблицы application_catalog...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS application_catalog (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(128) UNIQUE NOT NULL,
                    app_type VARCHAR(32) NOT NULL,
                    description TEXT,
                    default_playbook_path VARCHAR(255),
                    default_artifact_url VARCHAR(255),
                    default_artifact_extension VARCHAR(32),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT check_catalog_app_type CHECK (app_type IN ('docker', 'eureka', 'site', 'service'))
                );

                CREATE INDEX IF NOT EXISTS idx_catalog_name ON application_catalog(name);
                CREATE INDEX IF NOT EXISTS idx_catalog_type ON application_catalog(app_type);
            """))
            db.session.commit()
            logger.info("✓ Таблица application_catalog создана")

            # Шаг 2: Резервное копирование старой таблицы application_instances (junction table)
            logger.info("\n[Шаг 2] Резервное копирование старой таблицы application_instances...")
            db.session.execute(text("""
                DROP TABLE IF EXISTS application_instances_old_junction CASCADE;
                CREATE TABLE application_instances_old_junction AS
                SELECT * FROM application_instances;
            """))
            db.session.commit()
            logger.info("✓ Резервная копия создана: application_instances_old_junction")

            # Шаг 3: Удаление старой таблицы application_instances (junction table)
            logger.info("\n[Шаг 3] Удаление старой junction таблицы application_instances...")
            db.session.execute(text("""
                DROP TABLE IF EXISTS application_instances CASCADE;
            """))
            db.session.commit()
            logger.info("✓ Старая таблица application_instances удалена")

            # Шаг 4: Резервное копирование таблицы applications
            logger.info("\n[Шаг 4] Резервное копирование таблицы applications...")
            db.session.execute(text("""
                DROP TABLE IF EXISTS applications_backup CASCADE;
                CREATE TABLE applications_backup AS
                SELECT * FROM applications;
            """))
            db.session.commit()
            logger.info("✓ Резервная копия создана: applications_backup")

            # Шаг 5: Переименование applications в application_instances
            logger.info("\n[Шаг 5] Переименование таблицы applications -> application_instances...")
            db.session.execute(text("""
                ALTER TABLE applications RENAME TO application_instances;

                -- Переименовываем sequence
                ALTER SEQUENCE IF EXISTS applications_id_seq RENAME TO application_instances_id_seq;

                -- Переименовываем индексы
                ALTER INDEX IF EXISTS idx_app_group_instance RENAME TO idx_instance_group_number;
                ALTER INDEX IF EXISTS idx_app_server_name RENAME TO idx_instance_server_name;
            """))
            db.session.commit()
            logger.info("✓ Таблица переименована в application_instances")

            # Шаг 6: Добавление новых полей в application_instances
            logger.info("\n[Шаг 6] Добавление новых полей в application_instances...")
            db.session.execute(text("""
                -- Переименовываем name в instance_name
                ALTER TABLE application_instances RENAME COLUMN name TO instance_name;

                -- Добавляем catalog_id
                ALTER TABLE application_instances
                ADD COLUMN IF NOT EXISTS catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL;

                -- Добавляем кастомные URL артефактов
                ALTER TABLE application_instances
                ADD COLUMN IF NOT EXISTS custom_artifact_url VARCHAR(512);

                -- Переименовываем update_playbook_path в custom_playbook_path
                ALTER TABLE application_instances
                RENAME COLUMN update_playbook_path TO custom_playbook_path;

                -- Добавляем custom_artifact_extension
                ALTER TABLE application_instances
                ADD COLUMN IF NOT EXISTS custom_artifact_extension VARCHAR(32);

                -- Добавляем last_seen
                ALTER TABLE application_instances
                ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

                -- Добавляем deleted_at для soft delete
                ALTER TABLE application_instances
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

                -- Добавляем created_at и updated_at если их нет
                ALTER TABLE application_instances
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

                ALTER TABLE application_instances
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

                -- Обновляем ограничение для app_type
                ALTER TABLE application_instances DROP CONSTRAINT IF EXISTS check_app_type;
                ALTER TABLE application_instances
                ADD CONSTRAINT check_app_type CHECK (app_type IN ('docker', 'eureka', 'site', 'service'));

                -- Обновляем ограничение для status
                ALTER TABLE application_instances DROP CONSTRAINT IF EXISTS check_status;
                ALTER TABLE application_instances
                ADD CONSTRAINT check_status CHECK (status IN ('online', 'offline', 'unknown', 'starting', 'stopping', 'no_data'));

                -- Создаем новые индексы
                CREATE INDEX IF NOT EXISTS idx_instance_catalog ON application_instances(catalog_id);
                CREATE INDEX IF NOT EXISTS idx_instance_status ON application_instances(status);
                CREATE INDEX IF NOT EXISTS idx_instance_deleted ON application_instances(deleted_at);
                CREATE INDEX IF NOT EXISTS idx_instance_name ON application_instances(instance_name);
                CREATE INDEX IF NOT EXISTS idx_instance_type ON application_instances(app_type);
            """))
            db.session.commit()
            logger.info("✓ Новые поля добавлены в application_instances")

            # Шаг 7: Добавление catalog_id в application_groups
            logger.info("\n[Шаг 7] Добавление catalog_id в application_groups...")
            db.session.execute(text("""
                ALTER TABLE application_groups
                ADD COLUMN IF NOT EXISTS catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL;

                CREATE INDEX IF NOT EXISTS idx_group_catalog ON application_groups(catalog_id);
            """))
            db.session.commit()
            logger.info("✓ catalog_id добавлен в application_groups")

            # Шаг 8: Обновление таблицы events
            logger.info("\n[Шаг 8] Обновление таблицы events...")
            db.session.execute(text("""
                -- Переименовываем application_id в instance_id
                ALTER TABLE events RENAME COLUMN application_id TO instance_id;

                -- Удаляем старый constraint
                ALTER TABLE events DROP CONSTRAINT IF EXISTS events_application_id_fkey;

                -- Добавляем новый constraint
                ALTER TABLE events
                ADD CONSTRAINT events_instance_id_fkey
                FOREIGN KEY (instance_id)
                REFERENCES application_instances(id) ON DELETE CASCADE;
            """))
            db.session.commit()
            logger.info("✓ Таблица events обновлена")

            # Шаг 9: Заполнение application_catalog
            logger.info("\n[Шаг 9] Заполнение таблицы application_catalog...")
            db.session.execute(text("""
                INSERT INTO application_catalog (name, app_type, description)
                SELECT DISTINCT
                    REGEXP_REPLACE(instance_name, '_[0-9]+$', '') as base_name,
                    app_type,
                    'Автоматически создано при миграции'
                FROM application_instances
                WHERE instance_name IS NOT NULL
                ON CONFLICT (name) DO NOTHING;
            """))
            db.session.commit()

            # Получаем количество созданных записей
            result = db.session.execute(text("SELECT COUNT(*) FROM application_catalog"))
            catalog_count = result.scalar()
            logger.info(f"✓ Создано {catalog_count} записей в application_catalog")

            # Шаг 10: Связывание instances с catalog
            logger.info("\n[Шаг 10] Связывание application_instances с application_catalog...")
            db.session.execute(text("""
                UPDATE application_instances inst
                SET catalog_id = (
                    SELECT cat.id
                    FROM application_catalog cat
                    WHERE cat.name = REGEXP_REPLACE(inst.instance_name, '_[0-9]+$', '')
                    LIMIT 1
                )
                WHERE inst.catalog_id IS NULL;
            """))
            db.session.commit()

            # Получаем статистику связывания
            result = db.session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE catalog_id IS NOT NULL) as linked,
                    COUNT(*) FILTER (WHERE catalog_id IS NULL) as unlinked
                FROM application_instances
            """))
            stats = result.fetchone()
            logger.info(f"✓ Связано: {stats.linked}, Не связано: {stats.unlinked}")

            # Шаг 11: Связывание application_groups с catalog
            logger.info("\n[Шаг 11] Связывание application_groups с application_catalog...")
            db.session.execute(text("""
                UPDATE application_groups ag
                SET catalog_id = (
                    SELECT ac.id
                    FROM application_catalog ac
                    WHERE ac.name = ag.name
                    LIMIT 1
                )
                WHERE ag.catalog_id IS NULL
                AND EXISTS (
                    SELECT 1 FROM application_catalog ac WHERE ac.name = ag.name
                );
            """))
            db.session.commit()

            # Получаем статистику
            result = db.session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE catalog_id IS NOT NULL) as linked,
                    COUNT(*) FILTER (WHERE catalog_id IS NULL) as unlinked
                FROM application_groups
            """))
            stats = result.fetchone()
            logger.info(f"✓ Связано групп: {stats.linked}, Не связано: {stats.unlinked}")

            # Шаг 12: Проверка целостности
            logger.info("\n[Шаг 12] Проверка целостности данных...")

            # Подсчитываем записи
            result = db.session.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM application_catalog) as catalog_count,
                    (SELECT COUNT(*) FROM application_groups) as groups_count,
                    (SELECT COUNT(*) FROM application_instances) as instances_count,
                    (SELECT COUNT(*) FROM events) as events_count
            """))
            counts = result.fetchone()

            logger.info(f"  - Записей в application_catalog: {counts.catalog_count}")
            logger.info(f"  - Записей в application_groups: {counts.groups_count}")
            logger.info(f"  - Записей в application_instances: {counts.instances_count}")
            logger.info(f"  - Записей в events: {counts.events_count}")

            logger.info("\n" + "=" * 80)
            logger.info("МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА!")
            logger.info("=" * 80)
            logger.info("\nРезервные копии сохранены:")
            logger.info("  - applications_backup (старая таблица applications)")
            logger.info("  - application_instances_old_junction (старая junction таблица)")
            logger.info("\nДля удаления резервных копий выполните:")
            logger.info("  DROP TABLE applications_backup CASCADE;")
            logger.info("  DROP TABLE application_instances_old_junction CASCADE;")

            return True

        except Exception as e:
            logger.error(f"\n❌ ОШИБКА ПРИ МИГРАЦИИ: {str(e)}")
            logger.error("Откатываем изменения...")
            db.session.rollback()

            import traceback
            logger.error(traceback.format_exc())

            return False

def rollback_migration():
    """Откат миграции (если что-то пошло не так)"""
    app = create_app()

    with app.app_context():
        logger.info("=" * 80)
        logger.info("ОТКАТ МИГРАЦИИ")
        logger.info("=" * 80)

        try:
            logger.info("\n[Откат] Восстановление из резервных копий...")

            # Удаляем новые таблицы
            db.session.execute(text("""
                DROP TABLE IF EXISTS application_catalog CASCADE;
                DROP TABLE IF EXISTS application_instances CASCADE;
            """))

            # Восстанавливаем applications из бэкапа
            db.session.execute(text("""
                CREATE TABLE applications AS SELECT * FROM applications_backup;
                ALTER TABLE applications ADD PRIMARY KEY (id);
            """))

            # Восстанавливаем application_instances (junction) из бэкапа
            db.session.execute(text("""
                CREATE TABLE application_instances AS SELECT * FROM application_instances_old_junction;
                ALTER TABLE application_instances ADD PRIMARY KEY (id);
            """))

            # Восстанавливаем events
            db.session.execute(text("""
                ALTER TABLE events RENAME COLUMN instance_id TO application_id;
            """))

            db.session.commit()
            logger.info("✓ Откат выполнен успешно")

        except Exception as e:
            logger.error(f"❌ Ошибка при откате: {str(e)}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Миграция рефакторинга структуры БД')
    parser.add_argument('--rollback', action='store_true', help='Откатить миграцию')
    parser.add_argument('--yes', '-y', action='store_true', help='Подтвердить выполнение без запроса')

    args = parser.parse_args()

    if args.rollback:
        if not args.yes:
            response = input("Вы уверены, что хотите откатить миграцию? (yes/no): ")
            if response.lower() != 'yes':
                print("Откат отменен")
                sys.exit(0)

        success = rollback_migration()
        sys.exit(0 if success else 1)
    else:
        if not args.yes:
            print("\n" + "=" * 80)
            print("ВНИМАНИЕ: Это миграция рефакторинга структуры БД")
            print("=" * 80)
            print("\nБудут выполнены следующие изменения:")
            print("1. Создание таблицы application_catalog")
            print("2. Переименование applications -> application_instances")
            print("3. Удаление старой junction таблицы application_instances")
            print("4. Добавление новых полей и индексов")
            print("5. Миграция данных")
            print("\nРезервные копии будут созданы автоматически")
            print("\n" + "=" * 80)
            response = input("\nПродолжить? (yes/no): ")
            if response.lower() != 'yes':
                print("Миграция отменена")
                sys.exit(0)

        success = run_migration()
        sys.exit(0 if success else 1)

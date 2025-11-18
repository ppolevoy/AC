#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: Очистка старых таблиц и оптимизация БД после рефакторинга
Дата: 2025-11-17
Описание:
    - Удаление старых таблиц (application_instances_old_junction, applications_backup)
    - Добавление индексов для оптимизации производительности
    - Оптимизация структуры БД
"""
import sys
from sqlalchemy import create_engine, text, Index, inspect
from app.config import get_database_url

def run_migration():
    """Выполнить миграцию"""
    engine = create_engine(get_database_url())

    with engine.connect() as conn:
        print("=== Начало миграции: очистка и оптимизация ===\n")

        # 1. Удаление старых таблиц
        print("1. Удаление старых таблиц...")

        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        old_tables = ['application_instances_old_junction', 'applications_backup']

        for table in old_tables:
            if table in existing_tables:
                print(f"   Удаление таблицы {table}...")
                conn.execute(text(f'DROP TABLE IF EXISTS {table} CASCADE'))
                conn.commit()
                print(f"   ✓ Таблица {table} удалена")
            else:
                print(f"   ⊘ Таблица {table} не найдена, пропускаем")

        # 2. Добавление индексов для оптимизации
        print("\n2. Добавление индексов для оптимизации...")

        # Проверяем существующие индексы
        def index_exists(table, index_name):
            result = conn.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE tablename = '{table}'
                    AND indexname = '{index_name}'
                )
            """)).scalar()
            return result

        # Индексы для application_instances
        indexes_to_create = [
            # Поиск по server_id (частая операция при получении приложений сервера)
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_server_id',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_server_id ON application_instances(server_id)'
            },
            # Поиск по group_id (JOIN при работе с группами)
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_group_id',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_group_id ON application_instances(group_id)'
            },
            # Поиск по catalog_id (JOIN при работе с каталогом)
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_catalog_id',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_catalog_id ON application_instances(catalog_id)'
            },
            # Фильтрация по status (отображение активных/неактивных приложений)
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_status',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_status ON application_instances(status)'
            },
            # Поиск по instance_name (поиск конкретного экземпляра)
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_instance_name',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_instance_name ON application_instances(instance_name)'
            },
            # Поиск активных приложений (без deleted)
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_deleted_at',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_deleted_at ON application_instances(deleted_at) WHERE deleted_at IS NULL'
            },
            # Композитный индекс для маппинга HAProxy (поиск по IP:port)
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_ip_port',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_ip_port ON application_instances(ip, port) WHERE ip IS NOT NULL AND port IS NOT NULL'
            },
            # Композитный индекс для получения приложений группы на сервере
            {
                'table': 'application_instances',
                'name': 'idx_app_instances_server_group',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_instances_server_group ON application_instances(server_id, group_id)'
            },

            # Индексы для application_groups
            {
                'table': 'application_groups',
                'name': 'idx_app_groups_catalog_id',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_app_groups_catalog_id ON application_groups(catalog_id)'
            },

            # Индексы для events (оптимизация запросов истории)
            {
                'table': 'events',
                'name': 'idx_events_instance_id',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_events_instance_id ON events(instance_id)'
            },
            {
                'table': 'events',
                'name': 'idx_events_timestamp',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)'
            },
            {
                'table': 'events',
                'name': 'idx_events_event_type',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)'
            },
        ]

        for idx in indexes_to_create:
            if index_exists(idx['table'], idx['name']):
                print(f"   ⊘ Индекс {idx['name']} уже существует, пропускаем")
            else:
                print(f"   Создание индекса {idx['name']}...")
                conn.execute(text(idx['sql']))
                conn.commit()
                print(f"   ✓ Индекс {idx['name']} создан")

        # 3. VACUUM ANALYZE для обновления статистики
        print("\n3. Обновление статистики таблиц...")

        # Завершаем текущую транзакцию
        conn.commit()

        # VACUUM ANALYZE нельзя выполнить в транзакции, используем autocommit
        conn.execution_options(isolation_level="AUTOCOMMIT")

        tables_to_analyze = [
            'application_instances',
            'application_groups',
            'application_catalog',
            'events'
        ]

        for table in tables_to_analyze:
            print(f"   Анализ таблицы {table}...")
            conn.execute(text(f'VACUUM ANALYZE {table}'))
            print(f"   ✓ Таблица {table} проанализирована")

        print("\n=== Миграция завершена успешно ===")
        print("\nВыполнено:")
        print("  ✓ Удалены старые таблицы (application_instances_old_junction, applications_backup)")
        print("  ✓ Добавлены индексы для оптимизации производительности:")
        print("    - Индексы для поиска по server_id, group_id, catalog_id")
        print("    - Индексы для фильтрации по status, deleted_at")
        print("    - Композитные индексы для HAProxy маппинга и групповых операций")
        print("    - Индексы для таблицы events")
        print("  ✓ Обновлена статистика таблиц (VACUUM ANALYZE)")

        return True

def rollback_migration():
    """Откат миграции (восстановление невозможно для удаленных таблиц)"""
    engine = create_engine(get_database_url())

    with engine.connect() as conn:
        print("=== Откат миграции ===\n")
        print("ВНИМАНИЕ: Откат удаления таблиц невозможен (данные потеряны)")
        print("Удаление добавленных индексов...")

        indexes_to_drop = [
            'idx_app_instances_server_id',
            'idx_app_instances_group_id',
            'idx_app_instances_catalog_id',
            'idx_app_instances_status',
            'idx_app_instances_instance_name',
            'idx_app_instances_deleted_at',
            'idx_app_instances_ip_port',
            'idx_app_instances_server_group',
            'idx_app_groups_catalog_id',
            'idx_events_instance_id',
            'idx_events_timestamp',
            'idx_events_event_type',
        ]

        for idx_name in indexes_to_drop:
            print(f"   Удаление индекса {idx_name}...")
            conn.execute(text(f'DROP INDEX IF EXISTS {idx_name}'))
            conn.commit()
            print(f"   ✓ Индекс {idx_name} удален")

        print("\n=== Откат завершен ===")
        return True

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'rollback':
        rollback_migration()
    else:
        run_migration()

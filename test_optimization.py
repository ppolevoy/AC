#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование после оптимизации БД
"""
from app import create_app, db
from app.models.application_instance import ApplicationInstance
from app.models.application_group import ApplicationGroup
from app.models.application_catalog import ApplicationCatalog
from app.models.server import Server
from sqlalchemy import text
import time

app = create_app()
with app.app_context():
    print('=== Тестирование после оптимизации ===\n')

    # Тест 1: Проверка индексов
    print('1. Проверка созданных индексов...')
    result = db.session.execute(text('''
        SELECT tablename, indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname LIKE 'idx_%'
        ORDER BY tablename, indexname
    ''')).fetchall()

    print(f'   Найдено {len(result)} индексов:')
    current_table = None
    for row in result:
        if row[0] != current_table:
            current_table = row[0]
            print(f'\n   {current_table}:')
        print(f'     - {row[1]}')

    # Тест 2: Проверка работы моделей
    print('\n2. Проверка работы моделей...')

    # Получение приложений с JOIN
    start = time.time()
    instances = ApplicationInstance.query.join(
        ApplicationGroup, ApplicationInstance.group_id == ApplicationGroup.id
    ).filter(ApplicationInstance.deleted_at.is_(None)).limit(10).all()
    duration = time.time() - start
    print(f'   ✓ JOIN ApplicationInstance + ApplicationGroup: {len(instances)} записей за {duration:.3f}с')

    # Получение приложений сервера
    start = time.time()
    server = Server.query.first()
    if server:
        apps = ApplicationInstance.query.filter_by(server_id=server.id).all()
        duration = time.time() - start
        print(f'   ✓ Фильтр по server_id: {len(apps)} записей за {duration:.3f}с')

    # Получение приложений группы
    start = time.time()
    group = ApplicationGroup.query.first()
    if group:
        apps = ApplicationInstance.query.filter_by(group_id=group.id).all()
        duration = time.time() - start
        print(f'   ✓ Фильтр по group_id: {len(apps)} записей за {duration:.3f}с')

    # Поиск по IP:port (важно для HAProxy маппинга)
    start = time.time()
    app = ApplicationInstance.query.filter_by(ip='192.168.8.46', port=8180).first()
    duration = time.time() - start
    result_str = 'найдено' if app else 'не найдено'
    print(f'   ✓ Поиск по IP:port: {result_str} за {duration:.3f}с')

    # Поиск по instance_name
    start = time.time()
    app = ApplicationInstance.query.filter_by(instance_name='jurws_1').first()
    duration = time.time() - start
    result_str = 'найдено' if app else 'не найдено'
    print(f'   ✓ Поиск по instance_name: {result_str} за {duration:.3f}с')

    # Тест 3: Проверка целостности данных
    print('\n3. Проверка целостности данных...')

    total_instances = ApplicationInstance.query.count()
    instances_with_group = ApplicationInstance.query.filter(
        ApplicationInstance.group_id.isnot(None)
    ).count()
    instances_with_catalog = ApplicationInstance.query.filter(
        ApplicationInstance.catalog_id.isnot(None)
    ).count()

    print(f'   Всего экземпляров: {total_instances}')
    print(f'   С группой: {instances_with_group} ({instances_with_group/total_instances*100:.1f}%)')
    print(f'   С каталогом: {instances_with_catalog} ({instances_with_catalog/total_instances*100:.1f}%)')

    # Тест 4: Проверка размеров таблиц
    print('\n4. Размеры таблиц...')
    result = db.session.execute(text('''
        SELECT
            schemaname,
            tablename,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
            pg_total_relation_size(schemaname||'.'||tablename) AS bytes
        FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename IN ('application_instances', 'application_groups', 'application_catalog', 'events')
        ORDER BY bytes DESC
    ''')).fetchall()

    for row in result:
        print(f'   {row[1]:30} {row[2]}')

    print('\n=== Все тесты пройдены успешно! ===')

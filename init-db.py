#!/usr/bin/env python
# scripts/init_db.py
"""
Скрипт для инициализации базы данных PostgreSQL для Faktura App.
Очищает существующие таблицы и создает необходимые структуры.
"""
import os
import sys
import argparse
import logging
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Добавляем родительскую директорию в путь поиска модулей
sys.path.append(str(Path(__file__).parent.parent))

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='Инициализация базы данных Faktura App')
    parser.add_argument('--config', type=str, default='production',
                      help='Конфигурация приложения (development, production)')
    parser.add_argument('--demo', action='store_true',
                      help='Загрузить демонстрационные данные')
    parser.add_argument('--host', type=str, default='192.168.8.46',
                      help='Хост PostgreSQL')
    parser.add_argument('--port', type=int, default=5417,
                      help='Порт PostgreSQL')
    parser.add_argument('--user', type=str, default='fakadm',
                      help='Имя пользователя PostgreSQL')
    parser.add_argument('--password', type=str, default='fakadm', 
                      help='Пароль пользователя PostgreSQL')
    parser.add_argument('--dbname', type=str, default='appcontrol',
                      help='Имя базы данных')
    parser.add_argument('--create-db', action='store_true',
                      help='Создать базу данных, если она не существует')
    return parser.parse_args()

def create_database(args):
    """Создание базы данных PostgreSQL, если она не существует"""
    try:
        # Подключаемся к серверу PostgreSQL
        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Проверяем существование базы данных
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{args.dbname}'")
        exists = cursor.fetchone()
        
        if not exists:
            logger.info(f"Создание базы данных '{args.dbname}'...")
            cursor.execute(f"CREATE DATABASE {args.dbname}")
            logger.info(f"База данных '{args.dbname}' успешно создана")
        else:
            logger.info(f"База данных '{args.dbname}' уже существует")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании базы данных: {str(e)}")
        return False

def init_db(app):
    """Инициализация базы данных"""
    from app import db
    
    with app.app_context():
        logger.info("Удаление существующих таблиц...")
        db.drop_all()
        
        logger.info("Создание новых таблиц...")
        db.create_all()
        
        logger.info("База данных успешно инициализирована")

def load_demo_data(app):
    """Загрузка демонстрационных данных"""
    from app import db
    from app.models.server import Server
    from app.models.application_catalog import ApplicationCatalog
    from app.models.application_group import ApplicationGroup
    from app.models.application_instance import ApplicationInstance
    from app.models.event import Event
    from app.models.haproxy import HAProxyInstance, HAProxyBackend, HAProxyServer

    with app.app_context():
        logger.info("Загрузка демонстрационных данных...")

        # Создаем тестовые серверы
        servers = [
            Server(name='fdmz01', ip='192.168.1.100', port=5000, status='online', is_haproxy_node=True),
            Server(name='fdmz02', ip='192.168.1.101', port=5000, status='online', is_haproxy_node=True),
            Server(name='fdmz03', ip='192.168.1.102', port=5000, status='offline')
        ]

        for server in servers:
            db.session.add(server)

        db.session.commit()
        logger.info(f"Создано {len(servers)} тестовых серверов")

        # Создаем каталог приложений
        catalogs = [
            ApplicationCatalog(
                name='jurws',
                app_type='site',
                description='Юридический веб-сервис',
                default_playbook_path='/etc/ansible/update-jurws.yml',
                default_artifact_url='http://nexus.example.com/repository/releases/jurws/',
                default_artifact_extension='.jar'
            ),
            ApplicationCatalog(
                name='mobws',
                app_type='site',
                description='Мобильный веб-сервис',
                default_playbook_path='/etc/ansible/update-mobws.yml',
                default_artifact_url='http://nexus.example.com/repository/releases/mobws/',
                default_artifact_extension='.jar'
            ),
            ApplicationCatalog(
                name='reactws',
                app_type='site',
                description='React веб-сервис',
                default_playbook_path='/etc/ansible/update-reactws.yml',
                default_artifact_url='http://nexus.example.com/repository/releases/reactws/',
                default_artifact_extension='.jar'
            ),
            ApplicationCatalog(
                name='provider-api',
                app_type='docker',
                description='Provider API Service',
                default_playbook_path='/etc/ansible/update-docker-app.yml',
                default_artifact_url='http://nexus.example.com/repository/docker/provider-api/',
                default_artifact_extension=''
            ),
            ApplicationCatalog(
                name='payment-api',
                app_type='docker',
                description='Payment API Service',
                default_playbook_path='/etc/ansible/update-docker-app.yml',
                default_artifact_url='http://nexus.example.com/repository/docker/payment-api/',
                default_artifact_extension=''
            ),
            ApplicationCatalog(
                name='service',
                app_type='service',
                description='Background Service',
                default_playbook_path='/etc/ansible/update-service.yml',
                default_artifact_url='http://nexus.example.com/repository/releases/service/',
                default_artifact_extension='.jar'
            ),
        ]

        for catalog in catalogs:
            db.session.add(catalog)

        db.session.commit()
        logger.info(f"Создано {len(catalogs)} записей в каталоге приложений")

        # Создаем группы приложений
        groups = [
            ApplicationGroup(
                name='jurws-group',
                description='Группа экземпляров jurws',
                catalog_id=catalogs[0].id,
                artifact_list_url='http://nexus.example.com/repository/releases/jurws/',
                artifact_extension='.jar',
                update_playbook_path='/etc/ansible/update-jurws.yml',
                batch_grouping_strategy='by_group'
            ),
            ApplicationGroup(
                name='mobws-group',
                description='Группа экземпляров mobws',
                catalog_id=catalogs[1].id,
                artifact_list_url='http://nexus.example.com/repository/releases/mobws/',
                artifact_extension='.jar',
                update_playbook_path='/etc/ansible/update-mobws.yml',
                batch_grouping_strategy='by_group'
            ),
            ApplicationGroup(
                name='reactws-group',
                description='Группа экземпляров reactws',
                catalog_id=catalogs[2].id,
                artifact_list_url='http://nexus.example.com/repository/releases/reactws/',
                artifact_extension='.jar',
                update_playbook_path='/etc/ansible/update-reactws.yml',
                batch_grouping_strategy='by_instance_name'
            ),
            ApplicationGroup(
                name='api-services',
                description='API микросервисы',
                catalog_id=None,
                artifact_list_url='http://nexus.example.com/repository/docker/',
                artifact_extension='',
                update_playbook_path='/etc/ansible/update-docker-app.yml',
                batch_grouping_strategy='by_server'
            ),
        ]

        for group in groups:
            db.session.add(group)

        db.session.commit()
        logger.info(f"Создано {len(groups)} групп приложений")

        # Создаем экземпляры приложений
        server1 = servers[0]
        server2 = servers[1]

        instances = [
            # Экземпляры на первом сервере
            ApplicationInstance(
                instance_name='jurws_1',
                instance_number=1,
                server_id=server1.id,
                catalog_id=catalogs[0].id,
                group_id=groups[0].id,
                path='/site/app/jurws_1',
                log_path='/site/logs/jurws_1',
                version='1.79.2',
                distr_path='/site/share/htdoc/htdoc.data/jurws/20250218_170608_jurws-1.79.2/jurws-1.79.2.jar',
                ip='192.168.115.230',
                port=12070,
                status='online',
                app_type='site'
            ),
            ApplicationInstance(
                instance_name='mobws_1',
                instance_number=1,
                server_id=server1.id,
                catalog_id=catalogs[1].id,
                group_id=groups[1].id,
                path='/site/app/mobws_1',
                log_path='/site/logs/mobws_1',
                version='259.0',
                distr_path='/site/share/htdoc/htdoc.data/mobws/20250303_173743_mobws-259.1',
                ip='192.168.115.230',
                port=12071,
                status='online',
                app_type='site'
            ),
            ApplicationInstance(
                instance_name='reactws_2',
                instance_number=2,
                server_id=server1.id,
                catalog_id=catalogs[2].id,
                group_id=groups[2].id,
                path='/site/app/reactws_2',
                log_path='/site/logs/reactws_2',
                version='259.1',
                distr_path='/site/share/htdoc/htdoc.data/reactws/20250303_174004_mobws-259.1',
                ip='192.168.115.230',
                port=12072,
                status='online',
                app_type='site'
            ),
            # Экземпляры на втором сервере
            ApplicationInstance(
                instance_name='provider-api',
                instance_number=0,
                server_id=server2.id,
                catalog_id=catalogs[3].id,
                group_id=groups[3].id,
                container_id='cb664f463f24',
                container_name='provider-api',
                ip='192.168.115.230',
                port=11070,
                eureka_url='',
                compose_project_dir='/site/app/provider-api',
                status='online',
                app_type='docker'
            ),
            ApplicationInstance(
                instance_name='payment-api',
                instance_number=0,
                server_id=server2.id,
                catalog_id=catalogs[4].id,
                group_id=groups[3].id,
                container_id='bad145ca3aa3',
                container_name='payment-api',
                ip='192.168.115.230',
                port=9892,
                eureka_url='http://192.168.115.230:9892/',
                compose_project_dir='/site/app/payment-api',
                status='online',
                app_type='docker'
            ),
            ApplicationInstance(
                instance_name='service_1',
                instance_number=1,
                server_id=server2.id,
                catalog_id=catalogs[5].id,
                group_id=None,
                path='/site/app/service_1',
                log_path='/site/logs/service_1',
                version='1.79.2',
                distr_path='/site/share/htdoc/htdoc.data/service/20250218_170608_service-1.79.2/service-1.79.2.jar',
                port=12070,
                status='online',
                app_type='service'
            )
        ]

        for instance in instances:
            db.session.add(instance)

        db.session.commit()
        logger.info(f"Создано {len(instances)} экземпляров приложений")

        # Создаем тестовые события
        events = [
            Event(
                event_type='start',
                description='Запуск приложения jurws_1',
                status='success',
                server_id=server1.id,
                instance_id=instances[0].id
            ),
            Event(
                event_type='update',
                description='Обновление приложения mobws_1 до версии 259.0',
                status='success',
                server_id=server1.id,
                instance_id=instances[1].id
            ),
            Event(
                event_type='restart',
                description='Перезапуск приложения provider-api',
                status='success',
                server_id=server2.id,
                instance_id=instances[3].id
            )
        ]

        for event in events:
            db.session.add(event)

        db.session.commit()
        logger.info(f"Создано {len(events)} тестовых событий")

        # Создаем демонстрационные данные для HAProxy
        haproxy_instances = [
            HAProxyInstance(
                name='default',
                server_id=server1.id,
                is_active=True,
                socket_path='/var/run/haproxy.sock',
                last_sync_status='success'
            ),
            HAProxyInstance(
                name='default',
                server_id=server2.id,
                is_active=True,
                socket_path='/var/run/haproxy.sock',
                last_sync_status='success'
            )
        ]

        for haproxy_instance in haproxy_instances:
            db.session.add(haproxy_instance)

        db.session.commit()
        logger.info(f"Создано {len(haproxy_instances)} HAProxy инстансов")

        # Создаем backends для HAProxy
        backends = [
            HAProxyBackend(
                haproxy_instance_id=haproxy_instances[0].id,
                backend_name='web-services'
            ),
            HAProxyBackend(
                haproxy_instance_id=haproxy_instances[0].id,
                backend_name='api-backend'
            ),
            HAProxyBackend(
                haproxy_instance_id=haproxy_instances[1].id,
                backend_name='docker-services'
            )
        ]

        for backend in backends:
            db.session.add(backend)

        db.session.commit()
        logger.info(f"Создано {len(backends)} HAProxy backends")

        # Создаем серверы для HAProxy backends
        haproxy_servers = [
            # Серверы для web-services backend
            HAProxyServer(
                backend_id=backends[0].id,
                server_name='jurws_1',
                status='UP',
                weight=100,
                check_status='L7OK',
                addr='192.168.115.230:12070',
                scur=5,
                smax=50,
                application_id=instances[0].id
            ),
            HAProxyServer(
                backend_id=backends[0].id,
                server_name='mobws_1',
                status='UP',
                weight=100,
                check_status='L7OK',
                addr='192.168.115.230:12071',
                scur=3,
                smax=40,
                application_id=instances[1].id
            ),
            # Серверы для api-backend
            HAProxyServer(
                backend_id=backends[1].id,
                server_name='reactws_2',
                status='DRAIN',
                weight=50,
                check_status='L7OK',
                addr='192.168.115.230:12072',
                scur=1,
                smax=30,
                application_id=instances[2].id
            ),
            # Серверы для docker-services backend
            HAProxyServer(
                backend_id=backends[2].id,
                server_name='provider-api',
                status='UP',
                weight=100,
                check_status='L4OK',
                addr='192.168.115.230:11070',
                scur=10,
                smax=100,
                application_id=instances[3].id
            ),
            HAProxyServer(
                backend_id=backends[2].id,
                server_name='payment-api',
                status='UP',
                weight=100,
                check_status='L7OK',
                addr='192.168.115.230:9892',
                scur=8,
                smax=80,
                application_id=instances[4].id
            )
        ]

        for haproxy_server in haproxy_servers:
            db.session.add(haproxy_server)

        db.session.commit()
        logger.info(f"Создано {len(haproxy_servers)} HAProxy серверов")

        logger.info("Демонстрационные данные успешно загружены")

def main():
    args = parse_args()
    
    # Если не указан пароль, запрашиваем его
    if args.create_db and not args.password:
        import getpass
        args.password = getpass.getpass(f"Введите пароль для пользователя '{args.user}': ")
    
    logger.info(f"Инициализация базы данных с конфигурацией '{args.config}'")
    
    # Создаем базу данных, если указан флаг --create-db
    if args.create_db:
        if not create_database(args):
            logger.error("Невозможно продолжить инициализацию из-за ошибки создания базы данных")
            return
    
    # Настраиваем переменные окружения для подключения к PostgreSQL
    os.environ['POSTGRES_HOST'] = args.host
    os.environ['POSTGRES_PORT'] = str(args.port)
    os.environ['POSTGRES_USER'] = args.user
    if args.password:
        os.environ['POSTGRES_PASSWORD'] = args.password
    os.environ['POSTGRES_DB'] = args.dbname
    
    # Создаем строку подключения и устанавливаем её в переменную окружения
    if args.password:
        os.environ['DATABASE_URL'] = f"postgresql://{args.user}:{args.password}@{args.host}:{args.port}/{args.dbname}"
    else:
        os.environ['DATABASE_URL'] = f"postgresql://{args.user}@{args.host}:{args.port}/{args.dbname}"
    
    # Устанавливаем конфигурацию Flask
    os.environ['FLASK_CONFIG'] = args.config
    
    # Импортируем create_app только после настройки переменных окружения
    from app import create_app
    
    try:
        # Создаем экземпляр приложения с указанной конфигурацией
        app = create_app(args.config)
        
        # Инициализируем базу данных
        init_db(app)
        
        # Загружаем демонстрационные данные, если указан флаг --demo
        if args.demo:
            load_demo_data(app)
        
        logger.info("Инициализация базы данных успешно завершена!")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {str(e)}")
        import traceback
        traceback.print_exc()
        return

if __name__ == '__main__':
    main()
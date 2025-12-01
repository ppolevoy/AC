# -*- coding: utf-8 -*-
# РЕФАКТОРИНГ - обновлено для новой структуры БД

import aiohttp
import asyncio
import logging
import json
from datetime import datetime
from app import db
from app.models.server import Server
from app.models.application_instance import ApplicationInstance
from app.models.event import Event
from app.config import Config

from app.services.application_group_service import ApplicationGroupService
from app.models.application_version_history import ApplicationVersionHistory

logger = logging.getLogger(__name__)


def _sync_system_tags(instance):
    """Синхронизация системных тегов на основе app_type (не блокирует основную операцию)"""
    try:
        from app.services.system_tags import SystemTagsService
        SystemTagsService.on_app_synced(instance)
    except Exception as e:
        logger.warning(f"Failed to sync system tags for {instance.instance_name}: {e}")

# Разрешённые статусы для ApplicationInstance (соответствуют CHECK constraint в БД)
ALLOWED_STATUSES = {'online', 'offline', 'unknown', 'starting', 'stopping', 'no_data'}

# Маппинг нестандартных статусов на разрешённые
STATUS_MAPPING = {
    'disabled': 'offline',
    'enabled': 'online',
    'running': 'online',
    'stopped': 'offline',
    'down': 'offline',
    'up': 'online',
    'active': 'online',
    'inactive': 'offline',
    'paused': 'stopping',
    'pending': 'starting',
}


def _normalize_status(status):
    """
    Нормализует статус от агента к разрешённым значениям.

    Args:
        status: Статус от агента (может быть любым)

    Returns:
        str: Один из разрешённых статусов (online, offline, unknown, starting, stopping, no_data)
    """
    if not status:
        return 'unknown'

    status_lower = status.lower().strip()

    # Если статус уже разрешён - возвращаем как есть
    if status_lower in ALLOWED_STATUSES:
        return status_lower

    # Пробуем маппинг
    if status_lower in STATUS_MAPPING:
        return STATUS_MAPPING[status_lower]

    # Неизвестный статус - логируем и возвращаем unknown
    logger.warning(f"Неизвестный статус '{status}', используется 'unknown'")
    return 'unknown'


def _record_version_change(instance, new_version, new_tag=None, new_image=None, new_distr_path=None):
    """
    Записывает изменение версии в историю, если версия изменилась.

    Args:
        instance: Экземпляр ApplicationInstance
        new_version: Новая версия
        new_tag: Новый Docker тег (опционально)
        new_image: Новый Docker образ (опционально)
        new_distr_path: Новый путь к дистрибутиву (опционально)

    Returns:
        True если запись создана, False если версия не изменилась
    """
    # Проверяем, изменилась ли версия
    old_version = instance.version
    old_tag = instance.tag
    old_image = instance.image
    old_distr_path = instance.distr_path

    # Если это новый экземпляр или версия не изменилась - не записываем
    if not instance.id or (old_version == new_version and old_tag == new_tag):
        return False

    # Если новая версия None или пустая - не записываем
    if not new_version and not new_tag:
        return False

    try:
        history_entry = ApplicationVersionHistory(
            instance_id=instance.id,
            old_version=old_version,
            new_version=new_version or new_tag,
            old_distr_path=old_distr_path,
            new_distr_path=new_distr_path,
            old_tag=old_tag,
            new_tag=new_tag,
            old_image=old_image,
            new_image=new_image,
            changed_by='agent',
            change_source='polling'
        )
        db.session.add(history_entry)
        logger.info(f"Записана история версии для {instance.instance_name}: {old_version} -> {new_version or new_tag}")
        return True
    except Exception as e:
        logger.error(f"Ошибка записи истории версии для {instance.instance_name}: {e}")
        return False

# Алиас для обратной совместимости с кодом
Application = ApplicationInstance

class AgentService:
    """
    Сервис для асинхронного взаимодействия с удаленными агентами
    """
    
    @staticmethod
    async def check_agent(server):
        """Проверка доступности агента"""
        url = f"http://{server.ip}:{server.port}/ping"
        logger.info(f"Проверка доступности агента {server.name} по URL: {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=Config.CONNECTION_TIMEOUT) as response:
                    if response.status == 200:
                        # Агент доступен, обновляем статус и время проверки
                        prev_status = server.status
                        server.status = 'online'
                        server.last_check = datetime.utcnow()
                        
                        # Если статус изменился с offline на online, записываем событие
                        if prev_status == 'offline':
                            logger.info(f"Агент на сервере {server.name} снова доступен")
                            event = Event(
                                event_type='connect',
                                description=f"Сервер {server.name} снова доступен",
                                status='success',
                                server_id=server.id
                            )
                            db.session.add(event)
                        else:
                            logger.info(f"Агент на сервере {server.name} доступен")
                        
                        # Сохраняем изменения
                        db.session.commit()
                        return True
                    else:
                        # Агент недоступен, обновляем статус и время проверки
                        prev_status = server.status
                        server.status = 'offline'
                        server.last_check = datetime.utcnow()
                        
                        # Если статус изменился с online на offline, записываем событие
                        if prev_status == 'online':
                            logger.warning(f"Агент на сервере {server.name} стал недоступен, HTTP статус: {response.status}")
                            event = Event(
                                event_type='disconnect',
                                description=f"Сервер {server.name} стал недоступен, HTTP статус: {response.status}",
                                status='failed',
                                server_id=server.id
                            )
                            db.session.add(event)
                        else:
                            logger.warning(f"Агент на сервере {server.name} всё ещё недоступен, HTTP статус: {response.status}")
                        
                        # Сохраняем изменения
                        db.session.commit()
                        return False
        except aiohttp.ClientError as e:
            # Ошибка соединения
            prev_status = server.status
            server.status = 'offline'
            server.last_check = datetime.utcnow()
            
            # Если статус изменился с online на offline, записываем событие
            if prev_status == 'online':
                logger.error(f"Ошибка соединения с агентом на сервере {server.name}: {str(e)}")
                event = Event(
                    event_type='disconnect',
                    description=f"Ошибка соединения с сервером {server.name}: {str(e)}",
                    status='failed',
                    server_id=server.id
                )
                db.session.add(event)
            else:
                logger.error(f"Агент на сервере {server.name} всё ещё недоступен: {str(e)}")
            
            # Сохраняем изменения
            db.session.commit()
            return False
        except asyncio.TimeoutError:
            # Тайм-аут соединения
            prev_status = server.status
            server.status = 'offline'
            server.last_check = datetime.utcnow()
            
            # Если статус изменился с online на offline, записываем событие
            if prev_status == 'online':
                logger.error(f"Тайм-аут соединения с агентом на сервере {server.name}")
                event = Event(
                    event_type='disconnect',
                    description=f"Тайм-аут соединения с сервером {server.name}",
                    status='failed',
                    server_id=server.id
                )
                db.session.add(event)
            else:
                logger.error(f"Агент на сервере {server.name} всё ещё недоступен (тайм-аут)")
            
            # Сохраняем изменения
            db.session.commit()
            return False
        except Exception as e:
            # Другие ошибки
            prev_status = server.status
            server.status = 'offline'
            server.last_check = datetime.utcnow()
            
            # Если статус изменился с online на offline, записываем событие
            if prev_status == 'online':
                logger.error(f"Непредвиденная ошибка при проверке агента на сервере {server.name}: {str(e)}")
                event = Event(
                    event_type='disconnect',
                    description=f"Непредвиденная ошибка при проверке сервера {server.name}: {str(e)}",
                    status='failed',
                    server_id=server.id
                )
                db.session.add(event)
            else:
                logger.error(f"Агент на сервере {server.name} всё ещё недоступен: {str(e)}")
            
            import traceback
            logger.error(traceback.format_exc())
            
            # Сохраняем изменения
            db.session.commit()
            return False
    
    @staticmethod
    async def get_applications(server):
        """Получение списка приложений с сервера"""
        if server.status != 'online':
            logger.warning(f"Попытка получить приложения с сервера {server.name}, который не в сети")
            return None
        
        url = f"http://{server.ip}:{server.port}/api/v1/apps"
        logger.info(f"Запрос приложений с сервера {server.name} по URL: {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=Config.CONNECTION_TIMEOUT) as response:
                    if response.status == 200:
                        server_data = await response.json()
                        logger.info(f"Успешно получены данные с сервера {server.name}")
                        
                        # Проверяем структуру данных
                        if isinstance(server_data, dict) and 'server' in server_data:
                            # Логируем только первые 200 символов данных, чтобы не засорять логи
                            data_str = str(server_data)[:200] + "..." if len(str(server_data)) > 200 else str(server_data)
                            logger.debug(f"Данные с сервера {server.name}: {data_str}")
                                                        
                            server_info = server_data['server']
                            sections = ['docker-app', 'site-app', 'service-app']
                            found_sections = [s for s in sections if s in server_info]
                            
                            if found_sections:
                                logger.info(f"Найдены секции данных: {', '.join(found_sections)}")
                                return server_info
                            else:
                                logger.warning(f"В ответе сервера {server.name} не найдены ожидаемые секции данных")
                                return server_info  # Всё равно возвращаем данные, может быть другая структура
                        else:
                            logger.warning(f"Неожиданный формат данных от сервера {server.name}: {type(server_data)}")
                            return server_data  # Возвращаем как есть, обработаем в вызывающем коде
                    else:
                        logger.warning(f"Ошибка при получении приложений с сервера {server.name}: HTTP {response.status}")
                        response_text = await response.text()
                        logger.warning(f"Ответ сервера: {response_text[:200]}")
                        return None
            
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения при получении приложений с сервера {server.name}: {str(e)}")
            return None
        except asyncio.TimeoutError:
            logger.error(f"Тайм-аут при получении приложений с сервера {server.name}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка разбора JSON при получении приложений с сервера {server.name}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при получении приложений с сервера {server.name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @staticmethod
    async def get_application_details(server, app_name):
        """Получение детальной информации о приложении"""
        if server.status != 'online':
            logger.warning(f"Попытка получить информацию о приложении с сервера {server.name}, который не в сети")
            return None
        
        url = f"http://{server.ip}:{server.port}/app/{app_name}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=Config.CONNECTION_TIMEOUT) as response:
                    if response.status == 200:
                        app_data = await response.json()
                        return app_data
                    else:
                        logger.warning(f"Ошибка при получении информации о приложении {app_name} с сервера {server.name}: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Ошибка при получении информации о приложении {app_name} с сервера {server.name}: {str(e)}")
            return None
    
    @staticmethod
    async def send_eureka_command(app, command):
        """Отправка команды для приложения через Eureka"""
        if not app.eureka_url:
            logger.warning(f"Попытка отправить команду для приложения {app.instance_name}, у которого нет Eureka URL")
            return False

        url = f"{app.eureka_url}/{command}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, timeout=Config.CONNECTION_TIMEOUT) as response:
                    if response.status == 200:
                        logger.info(f"Команда {command} успешно отправлена приложению {app.instance_name}")
                        return True
                    else:
                        logger.warning(f"Ошибка при отправке команды {command} приложению {app.instance_name}: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Ошибка при отправке команды {command} приложению {app.instance_name}: {str(e)}")
            return False
    
    @staticmethod
    async def update_server_applications(server_id):
        """
        Обновление информации о приложениях на сервере с автоматическим определением групп.
        """
        from datetime import datetime
        from app.services.application_group_service import ApplicationGroupService
        
        server = Server.query.get(server_id)
        if not server:
            logger.error(f"Сервер с id {server_id} не найден")
            return False
        
        # Проверяем доступность агента
        is_online = await AgentService.check_agent(server)
        if not is_online:
            logger.warning(f"Сервер {server.name} не в сети. Помечаем все приложения как 'No Data'")
            
            # Помечаем все приложения сервера как "No Data"
            apps = Application.query.filter_by(server_id=server_id).all()
            for app in apps:
                app.status = 'no_data'  # Используем специальный статус для "No Data"
            
            db.session.commit()
            return False
        
        # Получаем данные о приложениях
        server_data = await AgentService.get_applications(server)
        if not server_data:
            logger.warning(f"Не удалось получить информацию о приложениях с сервера {server.name}")
            db.session.commit()
            return False
        
        try:
            logger.info(f"Получены данные о приложениях с сервера {server.name}")
            
            # Создаем список существующих ID приложений на сервере для отслеживания удаленных
            existing_app_ids = set(app.id for app in Application.query.filter_by(server_id=server.id).all())
            updated_app_ids = set()
            
            # Обрабатываем docker-приложения
            if 'docker-app' in server_data and 'applications' in server_data['docker-app']:
                docker_apps = server_data['docker-app']['applications']
                logger.info(f"Найдено {len(docker_apps)} docker-приложений на сервере {server.name}")
                
                for app_data in docker_apps:
                    container_name = app_data.get('container_name')
                    if not container_name:
                        logger.warning(f"Пропуск docker-приложения без имени контейнера на сервере {server.name}")
                        continue

                    # Ищем экземпляр по instance_name
                    instance = ApplicationInstance.query.filter_by(
                        server_id=server.id,
                        instance_name=container_name,
                        app_type='docker'
                    ).first()

                    if not instance:
                        logger.info(f"Создание нового docker-экземпляра {container_name} на сервере {server.name}")
                        instance = ApplicationInstance(
                            server_id=server.id,
                            instance_name=container_name,
                            app_type='docker'
                        )
                        db.session.add(instance)
                        db.session.flush()  # Чтобы получить ID
                    else:
                        logger.debug(f"Обновление существующего docker-экземпляра {container_name} на сервере {server.name}")

                    # Обновляем данные экземпляра
                    instance.container_id = app_data.get('container_id')
                    instance.container_name = container_name
                    instance.eureka_url = app_data.get('eureka_url')
                    instance.compose_project_dir = app_data.get('compose_project_dir')
                    instance.ip = app_data.get('ip')
                    instance.port = app_data.get('port')
                    instance.pid = app_data.get('pid')

                    # Записываем историю изменения версии (до обновления полей)
                    new_tag = app_data.get('tag')
                    new_image = app_data.get('image')
                    if instance.id:  # Только для существующих экземпляров
                        _record_version_change(
                            instance,
                            new_version=new_tag,
                            new_tag=new_tag,
                            new_image=new_image
                        )

                    # Docker-специфичные поля
                    instance.image = new_image
                    instance.tag = new_tag
                    instance.eureka_registered = app_data.get('eureka_registered', False)

                    # Устанавливаем version из tag (версия Docker образа)
                    instance.version = new_tag

                    # Устанавливаем path из compose_project_dir
                    instance.path = app_data.get('compose_project_dir')

                    # Парсим start_time если присутствует
                    if 'start_time' in app_data and app_data['start_time']:
                        try:
                            instance.start_time = datetime.fromisoformat(app_data['start_time'].replace('Z', '+00:00'))
                        except (ValueError, AttributeError) as e:
                            logger.warning(f"Некорректный формат времени запуска для docker-экземпляра {container_name}: {app_data['start_time']}")

                    # Используем статус от агента с нормализацией
                    instance.status = _normalize_status(app_data.get('status', 'online'))
                    instance.last_seen = datetime.utcnow()

                    # Определяем группу и каталог для экземпляра
                    ApplicationGroupService.resolve_application_group(instance)

                    # Синхронизация системных тегов (docker tag)
                    _sync_system_tags(instance)

                    if instance.id:
                        updated_app_ids.add(instance.id)

            # Обрабатываем site-приложения
            if 'site-app' in server_data and 'applications' in server_data['site-app']:
                site_apps = server_data['site-app']['applications']
                logger.info(f"Найдено {len(site_apps)} site-приложений на сервере {server.name}")
                
                for app_data in site_apps:
                    name = app_data.get('name')
                    if not name:
                        logger.warning(f"Пропуск site-приложения без имени на сервере {server.name}")
                        continue

                    # Ищем экземпляр по instance_name
                    instance = ApplicationInstance.query.filter_by(
                        server_id=server.id,
                        instance_name=name,
                        app_type='site'
                    ).first()

                    if not instance:
                        logger.info(f"Создание нового site-экземпляра {name} на сервере {server.name}")
                        instance = ApplicationInstance(
                            server_id=server.id,
                            instance_name=name,
                            app_type='site'
                        )
                        db.session.add(instance)
                        db.session.flush()  # Чтобы получить ID
                    else:
                        logger.debug(f"Обновление существующего site-экземпляра {name} на сервере {server.name}")

                    # Записываем историю изменения версии (до обновления полей)
                    new_version = app_data.get('version')
                    new_distr_path = app_data.get('distr_path')
                    if instance.id:  # Только для существующих экземпляров
                        _record_version_change(
                            instance,
                            new_version=new_version,
                            new_distr_path=new_distr_path
                        )

                    # Обновляем данные экземпляра
                    instance.path = app_data.get('path')
                    instance.log_path = app_data.get('log_path')
                    instance.version = new_version
                    instance.distr_path = new_distr_path
                    instance.ip = app_data.get('ip')
                    instance.port = app_data.get('port')
                    instance.status = _normalize_status(app_data.get('status'))
                    instance.last_seen = datetime.utcnow()

                    if 'start_time' in app_data and app_data['start_time']:
                        try:
                            instance.start_time = datetime.fromisoformat(app_data['start_time'])
                        except ValueError:
                            logger.warning(f"Некорректный формат времени запуска для экземпляра {name}: {app_data['start_time']}")

                    # Определяем группу и каталог для экземпляра
                    ApplicationGroupService.resolve_application_group(instance)

                    # Синхронизация системных тегов
                    _sync_system_tags(instance)

                    if instance.id:
                        updated_app_ids.add(instance.id)

            # Обрабатываем service-приложения
            if 'service-app' in server_data and 'applications' in server_data['service-app']:
                service_apps = server_data['service-app']['applications']
                logger.info(f"Найдено {len(service_apps)} service-приложений на сервере {server.name}")
                
                for app_data in service_apps:
                    name = app_data.get('name')
                    if not name:
                        logger.warning(f"Пропуск service-приложения без имени на сервере {server.name}")
                        continue

                    # Ищем экземпляр по instance_name
                    instance = ApplicationInstance.query.filter_by(
                        server_id=server.id,
                        instance_name=name,
                        app_type='service'
                    ).first()

                    if not instance:
                        logger.info(f"Создание нового service-экземпляра {name} на сервере {server.name}")
                        instance = ApplicationInstance(
                            server_id=server.id,
                            instance_name=name,
                            app_type='service'
                        )
                        db.session.add(instance)
                        db.session.flush()  # Чтобы получить ID
                    else:
                        logger.debug(f"Обновление существующего service-экземпляра {name} на сервере {server.name}")

                    # Записываем историю изменения версии (до обновления полей)
                    new_version = app_data.get('version')
                    new_distr_path = app_data.get('distr_path')
                    if instance.id:  # Только для существующих экземпляров
                        _record_version_change(
                            instance,
                            new_version=new_version,
                            new_distr_path=new_distr_path
                        )

                    # Обновляем данные экземпляра
                    instance.path = app_data.get('path')
                    instance.log_path = app_data.get('log_path')
                    instance.version = new_version
                    instance.distr_path = new_distr_path
                    instance.ip = app_data.get('ip')
                    instance.port = app_data.get('port')
                    instance.status = _normalize_status(app_data.get('status'))
                    instance.last_seen = datetime.utcnow()

                    if 'start_time' in app_data and app_data['start_time']:
                        try:
                            instance.start_time = datetime.fromisoformat(app_data['start_time'])
                        except ValueError:
                            logger.warning(f"Некорректный формат времени запуска для экземпляра {name}: {app_data['start_time']}")

                    # Определяем группу и каталог для экземпляра
                    ApplicationGroupService.resolve_application_group(instance)

                    # Синхронизация системных тегов
                    _sync_system_tags(instance)

                    if instance.id:
                        updated_app_ids.add(instance.id)

            # Находим экземпляры, которые были в БД, но отсутствуют в ответе агента
            deleted_app_ids = existing_app_ids - updated_app_ids
            if deleted_app_ids:
                logger.info(f"Обнаружено {len(deleted_app_ids)} удаленных экземпляров на сервере {server.name}")

                for instance_id in deleted_app_ids:
                    instance = ApplicationInstance.query.get(instance_id)
                    if instance:
                        logger.info(f"Экземпляр {instance.instance_name} не найден на сервере {server.name}, помечаем как offline")
                        instance.status = 'offline'
                        instance.last_seen = datetime.utcnow()
            
            # Коммитим изменения
            db.session.commit()
            logger.info(f"Информация о приложениях на сервере {server.name} успешно обновлена с определением групп")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при обновлении информации о приложениях на сервере {server.name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

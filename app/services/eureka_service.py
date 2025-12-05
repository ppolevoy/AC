# -*- coding: utf-8 -*-
"""
EurekaService - сервис для взаимодействия с Eureka через FAgent API.
Поддерживает мониторинг и управление экземплярами сервисов.
"""
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from app import db
from app.models.server import Server
from app.models.eureka import (EurekaServer, EurekaApplication,
                                 EurekaInstance, EurekaInstanceStatusHistory,
                                 EurekaInstanceAction)
from app.config import Config

logger = logging.getLogger(__name__)


class EurekaService:
    """Сервис для взаимодействия с Eureka через FAgent API"""

    # Простой кэш для уменьшения нагрузки на FAgent
    _cache = {}
    _cache_timestamps = {}

    @staticmethod
    def _build_url(server: Server, endpoint: str) -> str:
        """
        Построить URL для FAgent Eureka API.

        Args:
            server: Объект сервера
            endpoint: Конечная точка API

        Returns:
            Полный URL
        """
        base_url = f"http://{server.ip}:{server.port}"
        return f"{base_url}/api/v1/eureka/{endpoint}"

    @staticmethod
    def _get_cache_key(server_id: int, endpoint: str) -> str:
        """Генерация ключа кэша"""
        return f"eureka:{server_id}:{endpoint}"

    @staticmethod
    def _is_cache_valid(cache_key: str) -> bool:
        """Проверка валидности кэша"""
        if cache_key not in EurekaService._cache_timestamps:
            return False

        timestamp = EurekaService._cache_timestamps[cache_key]
        age = (datetime.utcnow() - timestamp).total_seconds()
        return age < Config.EUREKA_CACHE_TTL

    @staticmethod
    def _set_cache(cache_key: str, data: any):
        """Сохранение данных в кэш"""
        EurekaService._cache[cache_key] = data
        EurekaService._cache_timestamps[cache_key] = datetime.utcnow()

    @staticmethod
    def _get_cache(cache_key: str) -> Optional[any]:
        """Получение данных из кэша"""
        if EurekaService._is_cache_valid(cache_key):
            return EurekaService._cache.get(cache_key)
        return None

    @staticmethod
    def _clear_cache_for_server(server_id: int):
        """Очистка кэша для конкретного сервера"""
        keys_to_remove = [key for key in EurekaService._cache.keys()
                          if key.startswith(f"eureka:{server_id}:")]
        for key in keys_to_remove:
            EurekaService._cache.pop(key, None)
            EurekaService._cache_timestamps.pop(key, None)
        if keys_to_remove:
            logger.debug(f"Очищено {len(keys_to_remove)} записей кэша для Eureka server_id={server_id}")

    @staticmethod
    def _parse_instance_id(instance_id: str, app_name: str = None) -> Tuple[str, str, int]:
        """
        Парсинг instance_id различных форматов:
        - IP:service-name:port (например: 192.168.1.10:jurws:8080)
        - hostname:service-name:port (например: fdse.f.ftc.ru:platform-signature-verifier:19600)
        - IP:port (например: 192.168.115.231:9988)

        Args:
            instance_id: Строка instance_id
            app_name: Имя приложения (используется как service_name если не удалось извлечь)

        Returns:
            Tuple[ip_address, service_name, port]
        """
        try:
            parts = instance_id.split(':')
            if len(parts) == 3:
                # Формат: host:service:port
                return parts[0], parts[1], int(parts[2])
            elif len(parts) == 2:
                # Формат: host:port (service_name берём из app_name)
                service_name = app_name.lower() if app_name else 'unknown'
                return parts[0], service_name, int(parts[1])
            else:
                logger.error(f"Некорректный формат instance_id: {instance_id}")
                return None, None, None
        except Exception as e:
            logger.error(f"Ошибка парсинга instance_id '{instance_id}': {str(e)}")
            return None, None, None

    @staticmethod
    async def get_all_applications(eureka_server: EurekaServer) -> Tuple[bool, List[Dict]]:
        """
        Получить все приложения из Eureka через FAgent API.

        Args:
            eureka_server: Объект EurekaServer

        Returns:
            Tuple[success, applications_list]
        """
        server = eureka_server.server
        url = EurekaService._build_url(server, "apps")
        cache_key = EurekaService._get_cache_key(server.id, "apps")

        # Проверяем кэш
        cached_data = EurekaService._get_cache(cache_key)
        if cached_data is not None:
            logger.debug(f"Использование кэшированных данных для Eureka на {server.name}")
            return True, cached_data

        logger.debug(f"Получение списка приложений из Eureka на {server.name}")

        retry_count = 0
        last_error = None

        while retry_count < Config.EUREKA_MAX_RETRIES:
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=Config.EUREKA_REQUEST_TIMEOUT)
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json()

                            # Парсим ответ FAgent
                            if data.get('success') and 'data' in data:
                                applications = data['data'].get('applications', [])
                                logger.info(f"Получено {len(applications)} приложений из Eureka на {server.name}")

                                # Сохраняем в кэш
                                EurekaService._set_cache(cache_key, applications)
                                return True, applications
                            else:
                                logger.error(f"Некорректный формат ответа от FAgent: {data}")
                                return False, []
                        else:
                            error_text = await response.text()
                            last_error = f"HTTP {response.status}: {error_text}"
                            logger.warning(f"Ошибка получения приложений: {last_error}")

                            if response.status >= 500:
                                # Серверная ошибка - повторяем
                                retry_count += 1
                                await asyncio.sleep(Config.EUREKA_RETRY_DELAY * retry_count)
                                continue
                            else:
                                # Клиентская ошибка - не повторяем
                                return False, []

            except aiohttp.ClientError as e:
                last_error = f"Ошибка соединения: {str(e)}"
                logger.error(f"Ошибка соединения с FAgent на {server.name}: {str(e)}")
                retry_count += 1
                if retry_count < Config.EUREKA_MAX_RETRIES:
                    await asyncio.sleep(Config.EUREKA_RETRY_DELAY * retry_count)
            except asyncio.TimeoutError:
                last_error = "Таймаут соединения"
                logger.error(f"Таймаут соединения с FAgent на {server.name}")
                retry_count += 1
                if retry_count < Config.EUREKA_MAX_RETRIES:
                    await asyncio.sleep(Config.EUREKA_RETRY_DELAY * retry_count)

        logger.error(f"Не удалось получить приложения из Eureka после {Config.EUREKA_MAX_RETRIES} попыток. Последняя ошибка: {last_error}")
        return False, []

    @staticmethod
    async def get_application_details(eureka_server: EurekaServer, instance_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Получить детали конкретного приложения.

        Args:
            eureka_server: Объект EurekaServer
            instance_id: ID экземпляра

        Returns:
            Tuple[success, application_details]
        """
        server = eureka_server.server
        url = EurekaService._build_url(server, f"apps/{instance_id}")
        cache_key = EurekaService._get_cache_key(server.id, f"apps/{instance_id}")

        # Проверяем кэш
        cached_data = EurekaService._get_cache(cache_key)
        if cached_data is not None:
            logger.debug(f"Использование кэшированных данных для {instance_id}")
            return True, cached_data

        logger.debug(f"Получение деталей приложения {instance_id}")

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=Config.EUREKA_REQUEST_TIMEOUT)
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success') and 'data' in data:
                            app_details = data['data']
                            EurekaService._set_cache(cache_key, app_details)
                            return True, app_details
                        else:
                            return False, None
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка получения деталей приложения: HTTP {response.status}: {error_text}")
                        return False, None

        except Exception as e:
            logger.error(f"Ошибка получения деталей приложения {instance_id}: {str(e)}")
            return False, None

    @staticmethod
    async def health_check(eureka_server: EurekaServer, instance_id: str, user_id: int = None) -> Tuple[bool, Optional[str]]:
        """
        Проверка здоровья экземпляра.

        Args:
            eureka_server: Объект EurekaServer
            instance_id: ID экземпляра
            user_id: ID пользователя, инициировавшего проверку

        Returns:
            Tuple[success, result_message]
        """
        # Находим экземпляр в БД
        instance = EurekaInstance.query.filter_by(instance_id=instance_id).first()
        if not instance:
            logger.error(f"Экземпляр {instance_id} не найден в БД")
            return False, "Instance not found"

        # Создаем запись о действии
        action = EurekaInstanceAction(
            eureka_instance_id=instance.id,
            action_type='health_check',
            status='in_progress',
            user_id=user_id
        )
        db.session.add(action)
        db.session.commit()

        server = eureka_server.server
        url = EurekaService._build_url(server, f"apps/{instance_id}/health")
        logger.info(f"Выполнение health check для {instance_id}")

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=Config.EUREKA_REQUEST_TIMEOUT)
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get('success'):
                            health_status = data.get('data', {}).get('status', 'UNKNOWN')
                            result_msg = f"Health check successful: {health_status}"

                            # Обновляем статус экземпляра
                            instance.update_status(health_status, reason='health_check', changed_by='user' if user_id else 'system')
                            instance.last_heartbeat = datetime.utcnow()

                            # Отмечаем успех действия
                            action.mark_success(result_msg)
                            db.session.commit()

                            logger.info(f"Health check для {instance_id}: {health_status}")
                            return True, result_msg
                        else:
                            error_msg = data.get('error', 'Unknown error')
                            action.mark_failed(error_msg)
                            db.session.commit()
                            return False, error_msg
                    else:
                        error_text = await response.text()
                        error_msg = f"HTTP {response.status}: {error_text}"
                        action.mark_failed(error_msg)
                        db.session.commit()
                        logger.error(f"Ошибка health check: {error_msg}")
                        return False, error_msg

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            action.mark_failed(error_msg)
            db.session.commit()
            logger.error(f"Ошибка health check для {instance_id}: {str(e)}")
            return False, error_msg

    @staticmethod
    async def pause_application(eureka_server: EurekaServer, instance_id: str, user_id: int = None, reason: str = None) -> Tuple[bool, Optional[str]]:
        """
        Поставить приложение на паузу.

        Args:
            eureka_server: Объект EurekaServer
            instance_id: ID экземпляра
            user_id: ID пользователя
            reason: Причина паузы

        Returns:
            Tuple[success, result_message]
        """
        # Находим экземпляр в БД
        instance = EurekaInstance.query.filter_by(instance_id=instance_id).first()
        if not instance:
            logger.error(f"Экземпляр {instance_id} не найден в БД")
            return False, "Instance not found"

        # Создаем запись о действии
        action = EurekaInstanceAction(
            eureka_instance_id=instance.id,
            action_type='pause',
            action_params={'reason': reason},
            status='in_progress',
            user_id=user_id
        )
        db.session.add(action)
        db.session.commit()

        server = eureka_server.server
        url = EurekaService._build_url(server, f"apps/{instance_id}/pause")
        logger.info(f"Постановка на паузу {instance_id}")

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=Config.EUREKA_REQUEST_TIMEOUT)
                async with session.post(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get('success'):
                            result_msg = "Application paused successfully"

                            # Обновляем статус экземпляра
                            instance.update_status('PAUSED', reason=reason or 'manual_pause', changed_by='user' if user_id else 'system')

                            # Отмечаем успех действия
                            action.mark_success(result_msg)
                            db.session.commit()

                            logger.info(f"{instance_id} успешно поставлен на паузу")
                            return True, result_msg
                        else:
                            error_msg = data.get('error', 'Unknown error')
                            action.mark_failed(error_msg)
                            db.session.commit()
                            return False, error_msg
                    else:
                        error_text = await response.text()
                        error_msg = f"HTTP {response.status}: {error_text}"
                        action.mark_failed(error_msg)
                        db.session.commit()
                        logger.error(f"Ошибка паузы: {error_msg}")
                        return False, error_msg

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            action.mark_failed(error_msg)
            db.session.commit()
            logger.error(f"Ошибка паузы {instance_id}: {str(e)}")
            return False, error_msg

    @staticmethod
    async def shutdown_application(eureka_server: EurekaServer, instance_id: str, user_id: int = None, graceful: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Остановить приложение.

        Args:
            eureka_server: Объект EurekaServer
            instance_id: ID экземпляра
            user_id: ID пользователя
            graceful: Graceful shutdown

        Returns:
            Tuple[success, result_message]
        """
        # Находим экземпляр в БД
        instance = EurekaInstance.query.filter_by(instance_id=instance_id).first()
        if not instance:
            logger.error(f"Экземпляр {instance_id} не найден в БД")
            return False, "Instance not found"

        # Создаем запись о действии
        action = EurekaInstanceAction(
            eureka_instance_id=instance.id,
            action_type='shutdown',
            action_params={'graceful': graceful},
            status='in_progress',
            user_id=user_id
        )
        db.session.add(action)
        db.session.commit()

        server = eureka_server.server
        url = EurekaService._build_url(server, f"apps/{instance_id}/shutdown")
        logger.info(f"Остановка {instance_id} (graceful={graceful})")

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=Config.EUREKA_REQUEST_TIMEOUT)
                async with session.post(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get('success'):
                            result_msg = "Application shutdown initiated"

                            # Обновляем статус экземпляра
                            instance.update_status('DOWN', reason='manual_shutdown', changed_by='user' if user_id else 'system')

                            # Отмечаем успех действия
                            action.mark_success(result_msg)
                            db.session.commit()

                            logger.info(f"{instance_id} успешно остановлен")
                            return True, result_msg
                        else:
                            error_msg = data.get('error', 'Unknown error')
                            action.mark_failed(error_msg)
                            db.session.commit()
                            return False, error_msg
                    else:
                        error_text = await response.text()
                        error_msg = f"HTTP {response.status}: {error_text}"
                        action.mark_failed(error_msg)
                        db.session.commit()
                        logger.error(f"Ошибка shutdown: {error_msg}")
                        return False, error_msg

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            action.mark_failed(error_msg)
            db.session.commit()
            logger.error(f"Ошибка shutdown {instance_id}: {str(e)}")
            return False, error_msg

    @staticmethod
    async def set_log_level(eureka_server: EurekaServer, instance_id: str, logger_name: str, level: str, user_id: int = None) -> Tuple[bool, Optional[str]]:
        """
        Изменить уровень логирования.

        Args:
            eureka_server: Объект EurekaServer
            instance_id: ID экземпляра
            logger_name: Имя logger'а
            level: Уровень логирования (DEBUG, INFO, WARN, ERROR)
            user_id: ID пользователя

        Returns:
            Tuple[success, result_message]
        """
        # Валидация уровня
        valid_levels = ['DEBUG', 'INFO', 'WARN', 'ERROR']
        if level.upper() not in valid_levels:
            return False, f"Invalid log level. Must be one of: {', '.join(valid_levels)}"

        # Находим экземпляр в БД
        instance = EurekaInstance.query.filter_by(instance_id=instance_id).first()
        if not instance:
            logger.error(f"Экземпляр {instance_id} не найден в БД")
            return False, "Instance not found"

        # Создаем запись о действии
        action = EurekaInstanceAction(
            eureka_instance_id=instance.id,
            action_type='log_level_change',
            action_params={'logger': logger_name, 'level': level},
            status='in_progress',
            user_id=user_id
        )
        db.session.add(action)
        db.session.commit()

        server = eureka_server.server
        url = EurekaService._build_url(server, f"apps/{instance_id}/loglevel")
        logger.info(f"Изменение log level для {instance_id}: {logger_name} -> {level}")

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=Config.EUREKA_REQUEST_TIMEOUT)
                payload = {'logger': logger_name, 'level': level.upper()}

                async with session.post(url, json=payload, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get('success'):
                            result_msg = f"Log level changed: {logger_name} -> {level}"

                            # Отмечаем успех действия
                            action.mark_success(result_msg)
                            db.session.commit()

                            logger.info(f"Log level для {instance_id} изменен: {logger_name} -> {level}")
                            return True, result_msg
                        else:
                            error_msg = data.get('error', 'Unknown error')
                            action.mark_failed(error_msg)
                            db.session.commit()
                            return False, error_msg
                    else:
                        error_text = await response.text()
                        error_msg = f"HTTP {response.status}: {error_text}"
                        action.mark_failed(error_msg)
                        db.session.commit()
                        logger.error(f"Ошибка изменения log level: {error_msg}")
                        return False, error_msg

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            action.mark_failed(error_msg)
            db.session.commit()
            logger.error(f"Ошибка изменения log level для {instance_id}: {str(e)}")
            return False, error_msg

    @staticmethod
    async def sync_eureka_server(eureka_server: EurekaServer) -> bool:
        """
        Полная синхронизация одного Eureka сервера.

        Args:
            eureka_server: Объект EurekaServer

        Returns:
            success: Успешность синхронизации
        """
        logger.info(f"Начало синхронизации Eureka сервера: {eureka_server.eureka_host}:{eureka_server.eureka_port}")

        try:
            # Получаем все приложения из Eureka
            success, applications_data = await EurekaService.get_all_applications(eureka_server)

            if not success:
                error_message = "Failed to fetch applications from Eureka"
                eureka_server.mark_sync_failed(error_message)

                # Отмечаем все приложения этого сервера как failed
                existing_apps = EurekaApplication.query.filter_by(
                    eureka_server_id=eureka_server.id
                ).all()
                for app in existing_apps:
                    app.mark_fetch_failed(error_message)

                db.session.commit()
                return False

            # Словарь для отслеживания существующих instance_id
            seen_instance_ids = set()

            # Словарь для группировки инстансов по app_name
            apps_dict = {}

            # FAgent возвращает плоский список, где каждый элемент - это инстанс
            # Группируем по app_name
            for inst_data in applications_data:
                app_name = inst_data.get('app_name')
                if not app_name:
                    continue

                if app_name not in apps_dict:
                    apps_dict[app_name] = []
                apps_dict[app_name].append(inst_data)

            # Обрабатываем каждое приложение
            for app_name, instances in apps_dict.items():
                # Находим или создаем EurekaApplication
                eureka_app = EurekaApplication.query.filter_by(
                    eureka_server_id=eureka_server.id,
                    app_name=app_name
                ).first()

                if not eureka_app:
                    eureka_app = EurekaApplication(
                        eureka_server_id=eureka_server.id,
                        app_name=app_name
                    )
                    db.session.add(eureka_app)
                    db.session.flush()

                try:
                    # Обрабатываем экземпляры
                    for inst_data in instances:
                        instance_id = inst_data.get('instance_id')
                        if not instance_id:
                            logger.warning(f"Пропуск инстанса без instance_id для приложения {app_name}")
                            continue

                        seen_instance_ids.add(instance_id)

                        # Парсим instance_id (передаём app_name для формата IP:port)
                        ip_address, service_name, port = EurekaService._parse_instance_id(instance_id, app_name)

                        # Если парсинг не удался, пробуем взять ip и port напрямую из данных
                        if not ip_address or not port:
                            ip_address = inst_data.get('ip')
                            port = inst_data.get('port')
                            service_name = app_name.lower() if app_name else 'unknown'
                            if not ip_address or not port:
                                logger.warning(f"Не удалось получить ip/port для инстанса {instance_id}")
                                continue

                        # Находим или создаем EurekaInstance
                        eureka_instance = EurekaInstance.query.filter_by(instance_id=instance_id).first()

                        if not eureka_instance:
                            eureka_instance = EurekaInstance(
                                eureka_application_id=eureka_app.id,
                                instance_id=instance_id,
                                ip_address=ip_address,
                                port=port,
                                service_name=service_name or app_name
                            )
                            db.session.add(eureka_instance)
                            db.session.flush()  # Получить ID перед вызовом update_status

                        # Обновляем данные экземпляра
                        new_status = inst_data.get('status', 'UNKNOWN')
                        eureka_instance.update_status(new_status, reason='sync', changed_by='system')
                        eureka_instance.instance_metadata = inst_data.get('metadata')
                        eureka_instance.health_check_url = inst_data.get('health_check_url')
                        eureka_instance.home_page_url = inst_data.get('home_page_url') or inst_data.get('home_page_uri')
                        eureka_instance.status_page_url = inst_data.get('status_page_url')
                        eureka_instance.last_seen = datetime.utcnow()

                        # Восстанавливаем если был удален
                        if eureka_instance.is_removed():
                            eureka_instance.restore()

                    # Обновляем статистику приложения
                    eureka_app.update_statistics()

                    # Отмечаем успешное получение данных от агента для этого приложения
                    eureka_app.mark_fetch_success()

                except Exception as app_error:
                    # Ошибка обработки конкретного приложения - отмечаем только его как failed
                    logger.error(f"Ошибка обработки приложения {app_name}: {str(app_error)}")
                    eureka_app.mark_fetch_failed(f"Error processing application: {str(app_error)}")
                    # Продолжаем обработку других приложений

            # Мягкое удаление исчезнувших экземпляров
            all_instances = EurekaInstance.query.join(EurekaApplication).filter(
                EurekaApplication.eureka_server_id == eureka_server.id,
                EurekaInstance.removed_at.is_(None)
            ).all()

            for instance in all_instances:
                if instance.instance_id not in seen_instance_ids:
                    logger.info(f"Экземпляр {instance.instance_id} больше не существует в Eureka, помечаем как удаленный")
                    instance.soft_delete()

            # Отмечаем успешную синхронизацию
            eureka_server.mark_sync_success()
            db.session.commit()

            logger.info(f"Синхронизация Eureka сервера завершена успешно: {eureka_server.eureka_host}:{eureka_server.eureka_port}")
            return True

        except Exception as e:
            logger.error(f"Ошибка синхронизации Eureka сервера: {str(e)}")
            eureka_server.mark_sync_failed(str(e))
            db.session.commit()
            return False

    @staticmethod
    async def sync_all_eureka_servers() -> Dict[int, bool]:
        """
        Полная синхронизация всех активных Eureka серверов.

        Returns:
            Dict[eureka_server_id, success]: Результаты синхронизации
        """
        logger.info("Начало синхронизации всех Eureka серверов")

        # Получаем все активные Eureka серверы
        eureka_servers = EurekaServer.query.filter_by(
            is_active=True,
            removed_at=None
        ).all()

        if not eureka_servers:
            logger.info("Нет активных Eureka серверов для синхронизации")
            return {}

        results = {}

        # Синхронизируем каждый сервер
        for eureka_server in eureka_servers:
            success = await EurekaService.sync_eureka_server(eureka_server)
            results[eureka_server.id] = success

        logger.info(f"Синхронизация завершена. Успешно: {sum(results.values())}/{len(results)}")
        return results

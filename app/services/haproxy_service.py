# -*- coding: utf-8 -*-
"""
HAProxyService - сервис для взаимодействия с HAProxy через FAgent API.
Фаза 1: Реализован только мониторинг (read-only операции).
"""
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from app import db
from app.models.server import Server
from app.models.haproxy import HAProxyInstance, HAProxyBackend, HAProxyServer
from app.config import Config

logger = logging.getLogger(__name__)


class HAProxyService:
    """Сервис для взаимодействия с HAProxy через FAgent API"""

    # Простой кэш для уменьшения нагрузки на FAgent
    _cache = {}
    _cache_timestamps = {}

    @staticmethod
    def _build_url(server: Server, instance_name: str, endpoint: str) -> str:
        """
        Построить URL для FAgent HAProxy API.

        Args:
            server: Объект сервера
            instance_name: Имя HAProxy инстанса
            endpoint: Конечная точка API

        Returns:
            Полный URL
        """
        base_url = f"http://{server.ip}:{server.port}"

        # Всегда включаем имя instance в URL
        if instance_name:
            return f"{base_url}/api/v1/haproxy/{instance_name}/{endpoint}"
        else:
            # Fallback на 'default' если имя не указано
            return f"{base_url}/api/v1/haproxy/default/{endpoint}"

    @staticmethod
    def _get_cache_key(server_id: int, instance_name: str, endpoint: str) -> str:
        """Генерация ключа кэша"""
        return f"{server_id}:{instance_name}:{endpoint}"

    @staticmethod
    def _is_cache_valid(cache_key: str) -> bool:
        """Проверка валидности кэша"""
        if cache_key not in HAProxyService._cache_timestamps:
            return False

        timestamp = HAProxyService._cache_timestamps[cache_key]
        age = (datetime.utcnow() - timestamp).total_seconds()
        return age < Config.HAPROXY_CACHE_TTL

    @staticmethod
    def _set_cache(cache_key: str, data: any):
        """Сохранение данных в кэш"""
        HAProxyService._cache[cache_key] = data
        HAProxyService._cache_timestamps[cache_key] = datetime.utcnow()

    @staticmethod
    def _get_cache(cache_key: str) -> Optional[any]:
        """Получение данных из кэша"""
        if HAProxyService._is_cache_valid(cache_key):
            return HAProxyService._cache.get(cache_key)
        return None

    @staticmethod
    def _clear_cache_for_instance(server_id: int, instance_name: str):
        """Очистка кэша для конкретного HAProxy instance"""
        keys_to_remove = [key for key in HAProxyService._cache.keys()
                          if key.startswith(f"{server_id}:{instance_name}:")]
        for key in keys_to_remove:
            HAProxyService._cache.pop(key, None)
            HAProxyService._cache_timestamps.pop(key, None)
        if keys_to_remove:
            logger.info(f"Очищено {len(keys_to_remove)} записей кэша для server_id={server_id}, instance={instance_name}")

    @staticmethod
    def _safe_int(value, default=None):
        """
        Безопасная конвертация в int.
        Пустые строки и None конвертируются в default.
        """
        if value is None or value == '':
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    async def get_instances(server: Server) -> Tuple[bool, List[Dict]]:
        """
        Получить список HAProxy instances из FAgent API.

        Args:
            server: Объект сервера

        Returns:
            Tuple[success, instances_list]
        """
        url = f"http://{server.ip}:{server.port}/api/v1/haproxy/instances"
        logger.info(f"Получение списка HAProxy instances с {server.name} - {url}")

        retry_count = 0
        last_error = None

        while retry_count < Config.HAPROXY_MAX_RETRIES:
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=Config.HAPROXY_REQUEST_TIMEOUT)
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json()

                            # Парсим ответ FAgent
                            if data.get('success') and 'data' in data:
                                instances = data['data'].get('instances', [])
                                logger.info(f"Получено {len(instances)} HAProxy instances из {server.name}")
                                return True, instances
                            else:
                                logger.warning(f"Некорректный формат ответа от FAgent: {data}")
                                return False, []
                        else:
                            error_text = await response.text()
                            last_error = f"HTTP {response.status}: {error_text}"
                            logger.warning(f"Ошибка получения instances: {last_error}")

                            if response.status >= 500:
                                # Серверная ошибка - повторяем
                                retry_count += 1
                                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                                continue
                            else:
                                # Клиентская ошибка - не повторяем
                                return False, []

            except aiohttp.ClientError as e:
                last_error = f"Ошибка соединения: {str(e)}"
                logger.error(f"Ошибка соединения с FAgent на {server.name}: {str(e)}")
                retry_count += 1
                if retry_count < Config.HAPROXY_MAX_RETRIES:
                    await asyncio.sleep(2 ** retry_count)
                continue

            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.error(f"Timeout при получении instances из {server.name}")
                retry_count += 1
                if retry_count < Config.HAPROXY_MAX_RETRIES:
                    await asyncio.sleep(2 ** retry_count)
                continue

            except Exception as e:
                last_error = f"Неизвестная ошибка: {str(e)}"
                logger.exception(f"Неизвестная ошибка при получении instances: {str(e)}")
                return False, []

        logger.error(f"Не удалось получить instances после {Config.HAPROXY_MAX_RETRIES} попыток. Последняя ошибка: {last_error}")
        return False, []

    @staticmethod
    async def get_backends(server: Server, instance_name: str = 'default') -> Tuple[bool, List[Dict]]:
        """
        Получить список backends из HAProxy через FAgent API.

        Args:
            server: Объект сервера
            instance_name: Имя HAProxy инстанса

        Returns:
            Tuple[success, backends_list]
        """
        cache_key = HAProxyService._get_cache_key(server.id, instance_name, 'backends')
        cached_data = HAProxyService._get_cache(cache_key)
        if cached_data is not None:
            logger.info(f"Возвращаем {len(cached_data)} backends из кэша для {server.name}:{instance_name}")
            return True, cached_data

        url = HAProxyService._build_url(server, instance_name, 'backends')
        logger.info(f"Получение backends из HAProxy {server.name}:{instance_name} - {url}")

        retry_count = 0
        last_error = None

        while retry_count < Config.HAPROXY_MAX_RETRIES:
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=Config.HAPROXY_REQUEST_TIMEOUT)
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json()
                            # FAgent возвращает структуру: {success: true, data: {backends: [...]}}
                            backends = data.get('data', {}).get('backends', [])
                            logger.info(f"Получено {len(backends)} backends из {server.name}:{instance_name}")

                            # Сохраняем в кэш
                            HAProxyService._set_cache(cache_key, backends)

                            return True, backends
                        else:
                            error_text = await response.text()
                            last_error = f"HTTP {response.status}: {error_text}"
                            logger.warning(f"Ошибка получения backends: {last_error}")

                            if response.status >= 500:
                                # Серверная ошибка - повторяем
                                retry_count += 1
                                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                                continue
                            else:
                                # Клиентская ошибка - не повторяем
                                return False, []

            except aiohttp.ClientError as e:
                last_error = f"Ошибка соединения: {str(e)}"
                logger.error(f"Ошибка соединения с FAgent на {server.name}: {str(e)}")
                retry_count += 1
                if retry_count < Config.HAPROXY_MAX_RETRIES:
                    await asyncio.sleep(2 ** retry_count)
                continue

            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.error(f"Timeout при получении backends из {server.name}:{instance_name}")
                retry_count += 1
                if retry_count < Config.HAPROXY_MAX_RETRIES:
                    await asyncio.sleep(2 ** retry_count)
                continue

            except Exception as e:
                last_error = f"Неизвестная ошибка: {str(e)}"
                logger.exception(f"Неизвестная ошибка при получении backends: {str(e)}")
                return False, []

        logger.error(f"Не удалось получить backends после {Config.HAPROXY_MAX_RETRIES} попыток. Последняя ошибка: {last_error}")
        return False, []

    @staticmethod
    async def get_backend_servers(server: Server, instance_name: str, backend_name: str) -> Tuple[bool, List[Dict]]:
        """
        Получить список серверов в backend из HAProxy через FAgent API.

        Args:
            server: Объект сервера
            instance_name: Имя HAProxy инстанса
            backend_name: Имя backend

        Returns:
            Tuple[success, servers_list]
        """
        cache_key = HAProxyService._get_cache_key(server.id, instance_name, f'backend:{backend_name}')
        cached_data = HAProxyService._get_cache(cache_key)
        if cached_data is not None:
            logger.info(f"Возвращаем {len(cached_data)} серверов backend {backend_name} из кэша для {server.name}:{instance_name}")
            return True, cached_data

        url = HAProxyService._build_url(server, instance_name, f'backends/{backend_name}/servers')
        logger.info(f"Получение серверов backend {backend_name} из {server.name}:{instance_name}")

        retry_count = 0
        last_error = None

        while retry_count < Config.HAPROXY_MAX_RETRIES:
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=Config.HAPROXY_REQUEST_TIMEOUT)
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json()
                            # FAgent возвращает структуру: {success: true, data: {servers: [...]}}
                            servers = data.get('data', {}).get('servers', [])
                            logger.info(f"Получено {len(servers)} серверов из backend {backend_name}")

                            # Сохраняем в кэш
                            HAProxyService._set_cache(cache_key, servers)

                            return True, servers
                        else:
                            error_text = await response.text()
                            last_error = f"HTTP {response.status}: {error_text}"
                            logger.warning(f"Ошибка получения серверов backend: {last_error}")

                            if response.status >= 500:
                                retry_count += 1
                                await asyncio.sleep(2 ** retry_count)
                                continue
                            else:
                                return False, []

            except aiohttp.ClientError as e:
                last_error = f"Ошибка соединения: {str(e)}"
                logger.error(f"Ошибка соединения с FAgent: {str(e)}")
                retry_count += 1
                if retry_count < Config.HAPROXY_MAX_RETRIES:
                    await asyncio.sleep(2 ** retry_count)
                continue

            except asyncio.TimeoutError:
                last_error = "Timeout"
                logger.error(f"Timeout при получении серверов backend {backend_name}")
                retry_count += 1
                if retry_count < Config.HAPROXY_MAX_RETRIES:
                    await asyncio.sleep(2 ** retry_count)
                continue

            except Exception as e:
                last_error = f"Неизвестная ошибка: {str(e)}"
                logger.exception(f"Неизвестная ошибка: {str(e)}")
                return False, []

        logger.error(f"Не удалось получить серверы backend после {Config.HAPROXY_MAX_RETRIES} попыток. Последняя ошибка: {last_error}")
        return False, []

    @staticmethod
    async def sync_haproxy_instance(haproxy_instance: HAProxyInstance) -> bool:
        """
        Синхронизация HAProxy инстанса: получение всех backends и серверов,
        обновление базы данных.

        Args:
            haproxy_instance: Объект HAProxyInstance для синхронизации

        Returns:
            bool: True если синхронизация успешна
        """
        logger.info(f"Начало синхронизации HAProxy инстанса {haproxy_instance.name} на {haproxy_instance.server.name}")

        try:
            server = haproxy_instance.server

            # Очищаем кэш для этого instance, чтобы получить свежие данные
            HAProxyService._clear_cache_for_instance(server.id, haproxy_instance.name)

            # Получаем список backends
            success, backends_data = await HAProxyService.get_backends(server, haproxy_instance.name)
            logger.info(f"Результат get_backends для {haproxy_instance.name}: success={success}, count={len(backends_data) if backends_data else 0}")

            if not success:
                error_msg = "Не удалось получить список backends"
                haproxy_instance.mark_sync_failed(error_msg)
                db.session.commit()
                return False

            # Отмечаем все существующие backends как потенциально удаленные
            current_backend_names = set()

            # Обрабатываем каждый backend
            for backend_data in backends_data:
                # FAgent возвращает список строк (имен backend'ов), а не объектов
                if isinstance(backend_data, str):
                    backend_name = backend_data
                else:
                    # Поддержка старого формата (объект с полем 'name')
                    backend_name = backend_data.get('name')

                if not backend_name:
                    continue

                current_backend_names.add(backend_name)

                # Найти или создать backend
                backend = HAProxyBackend.query.filter_by(
                    haproxy_instance_id=haproxy_instance.id,
                    backend_name=backend_name
                ).first()

                if backend:
                    # Восстанавливаем если был удален
                    if backend.is_removed():
                        backend.restore()
                        logger.info(f"Backend {backend_name} восстановлен")
                else:
                    # Создаем новый backend
                    backend = HAProxyBackend(
                        haproxy_instance_id=haproxy_instance.id,
                        backend_name=backend_name
                    )
                    db.session.add(backend)
                    db.session.flush()  # Получить ID
                    logger.info(f"Создан новый backend: {backend_name}")

                # Получаем серверы в backend
                success, servers_data = await HAProxyService.get_backend_servers(
                    server, haproxy_instance.name, backend_name
                )

                if not success:
                    logger.warning(f"Не удалось получить серверы для backend {backend_name}")
                    continue

                # Обрабатываем серверы
                current_server_names = set()

                for server_data in servers_data:
                    server_name = server_data.get('name')
                    if not server_name:
                        continue

                    current_server_names.add(server_name)

                    # Найти или создать сервер
                    haproxy_server = HAProxyServer.query.filter_by(
                        backend_id=backend.id,
                        server_name=server_name
                    ).first()

                    if haproxy_server:
                        # Обновляем существующий сервер
                        if haproxy_server.is_removed():
                            haproxy_server.restore()
                            logger.info(f"Сервер {server_name} восстановлен")

                        # Обновляем статус и метрики
                        new_status = server_data.get('status')
                        if haproxy_server.status != new_status:
                            haproxy_server.update_status(new_status, reason='sync')

                        haproxy_server.weight = HAProxyService._safe_int(server_data.get('weight'), 1)
                        haproxy_server.check_status = server_data.get('check_status')
                        haproxy_server.addr = server_data.get('addr')
                        haproxy_server.last_check_duration = HAProxyService._safe_int(server_data.get('lastchkdur'))
                        haproxy_server.last_state_change = HAProxyService._safe_int(server_data.get('lastchg'))
                        haproxy_server.downtime = HAProxyService._safe_int(server_data.get('downtime'))
                        haproxy_server.scur = HAProxyService._safe_int(server_data.get('scur'), 0)
                        haproxy_server.smax = HAProxyService._safe_int(server_data.get('smax'), 0)
                        haproxy_server.last_seen = datetime.utcnow()
                    else:
                        # Создаем новый сервер
                        haproxy_server = HAProxyServer(
                            backend_id=backend.id,
                            server_name=server_name,
                            status=server_data.get('status'),
                            weight=HAProxyService._safe_int(server_data.get('weight'), 1),
                            check_status=server_data.get('check_status'),
                            addr=server_data.get('addr'),
                            last_check_duration=HAProxyService._safe_int(server_data.get('lastchkdur')),
                            last_state_change=HAProxyService._safe_int(server_data.get('lastchg')),
                            downtime=HAProxyService._safe_int(server_data.get('downtime')),
                            scur=HAProxyService._safe_int(server_data.get('scur'), 0),
                            smax=HAProxyService._safe_int(server_data.get('smax'), 0)
                        )
                        db.session.add(haproxy_server)
                        logger.info(f"Создан новый сервер: {server_name} в backend {backend_name}")

                # Мягко удаляем серверы, которых больше нет
                missing_servers = HAProxyServer.query.filter(
                    HAProxyServer.backend_id == backend.id,
                    HAProxyServer.removed_at.is_(None),
                    HAProxyServer.server_name.notin_(current_server_names)
                ).all()

                for missing_server in missing_servers:
                    missing_server.soft_delete()
                    logger.info(f"Сервер {missing_server.server_name} помечен как удаленный (soft delete)")

            # Мягко удаляем backends, которых больше нет
            missing_backends = HAProxyBackend.query.filter(
                HAProxyBackend.haproxy_instance_id == haproxy_instance.id,
                HAProxyBackend.removed_at.is_(None),
                HAProxyBackend.backend_name.notin_(current_backend_names)
            ).all()

            for missing_backend in missing_backends:
                missing_backend.soft_delete()
                logger.info(f"Backend {missing_backend.backend_name} помечен как удаленный (soft delete)")

            # Отмечаем успешную синхронизацию
            haproxy_instance.mark_sync_success()
            db.session.commit()

            logger.info(f"Синхронизация HAProxy инстанса {haproxy_instance.name} завершена успешно")
            return True

        except Exception as e:
            error_msg = f"Ошибка синхронизации: {str(e)}"
            logger.exception(error_msg)
            haproxy_instance.mark_sync_failed(error_msg)
            db.session.commit()
            return False

    @staticmethod
    def clear_cache():
        """Очистить весь кэш"""
        HAProxyService._cache.clear()
        HAProxyService._cache_timestamps.clear()
        logger.info("Кэш HAProxyService очищен")

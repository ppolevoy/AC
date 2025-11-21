# -*- coding: utf-8 -*-
"""
HAProxyMapper - сервис для связывания HAProxy серверов с приложениями AC.
Использует две стратегии:
1. Сопоставление по IP:port
2. Разбор имени сервера по паттерну hostname_appName_instance
"""
import re
import logging
from typing import Optional, Tuple
from app import db
from app.models.application_instance import ApplicationInstance
from app.models.server import Server
from app.models.haproxy import HAProxyServer
from app.models.application_mapping import MappingType

# Алиас для обратной совместимости
Application = ApplicationInstance

logger = logging.getLogger(__name__)

# Lazy import для избежания циклических импортов
def get_mapping_service():
    from app.services.mapping_service import mapping_service
    return mapping_service


class HAProxyMapper:
    """Сервис для маппинга HAProxy серверов на приложения AC"""

    # Кэш результатов маппинга для уменьшения запросов к БД
    _mapping_cache = {}

    @staticmethod
    def parse_server_name(server_name: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Парсит имя HAProxy сервера по формату: hostname_appName_instance

        Args:
            server_name: Имя сервера из HAProxy (например: fdmz01_jurws_1)

        Returns:
            Tuple[hostname, app_name, instance_number] или (None, None, None)

        Примеры:
            "fdmz01_jurws_1" -> ("fdmz01", "jurws", 1)
            "web01_myapp_2" -> ("web01", "myapp", 2)
            "server_app" -> ("server", "app", 0)
        """
        if not server_name:
            return None, None, None

        # Паттерн: hostname_appName_instance
        # Где instance - это цифра в конце
        pattern = r'^([^_]+)_(.+)_(\d+)$'
        match = re.match(pattern, server_name)

        if match:
            hostname = match.group(1)
            app_name = match.group(2)
            instance = int(match.group(3))
            return hostname, app_name, instance

        # Попытка разбора без номера instance: hostname_appName
        pattern_no_instance = r'^([^_]+)_(.+)$'
        match = re.match(pattern_no_instance, server_name)

        if match:
            hostname = match.group(1)
            app_name = match.group(2)
            return hostname, app_name, 0

        # Не удалось распарсить
        return None, None, None

    @staticmethod
    def parse_address(addr: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Парсит адрес HAProxy сервера в формате IP:port

        Args:
            addr: Адрес (например: "192.168.1.10:8080")

        Returns:
            Tuple[ip, port] или (None, None)
        """
        if not addr:
            return None, None

        if ':' in addr:
            parts = addr.rsplit(':', 1)
            try:
                ip = parts[0]
                port = int(parts[1])
                return ip, port
            except (ValueError, IndexError):
                return None, None

        return None, None

    @staticmethod
    def map_by_address(ip: str, port: int) -> Optional[Application]:
        """
        Поиск приложения по IP и порту.

        Args:
            ip: IP адрес
            port: Порт

        Returns:
            Application или None
        """
        logger.debug(f"Поиск приложения по адресу {ip}:{port}")

        # Ищем приложение с точным совпадением IP и порта
        app = Application.query.filter_by(ip=ip, port=port).first()

        if app:
            logger.info(f"Найдено приложение по адресу: {app.instance_name} ({ip}:{port})")
            return app

        logger.debug(f"Приложение с адресом {ip}:{port} не найдено")
        return None

    @staticmethod
    def map_by_name(hostname: str, app_name: str, instance: int) -> Optional[Application]:
        """
        Поиск приложения по имени хоста, имени приложения и номеру instance.

        Args:
            hostname: Имя хоста (например: fdmz01)
            app_name: Имя приложения (например: jurws)
            instance: Номер экземпляра (например: 1)

        Returns:
            Application или None
        """
        logger.debug(f"Поиск приложения по имени: hostname={hostname}, app={app_name}, instance={instance}")

        # Формируем ожидаемое имя приложения: appName_instance
        expected_app_name = f"{app_name}_{instance}" if instance > 0 else app_name

        # Ищем сервер по имени хоста (частичное совпадение)
        servers = Server.query.filter(Server.name.ilike(f'%{hostname}%')).all()

        if not servers:
            logger.debug(f"Серверы с hostname {hostname} не найдены")
            return None

        # Ищем приложение на найденных серверах
        for server in servers:
            # Точное совпадение имени
            app = Application.query.filter_by(
                server_id=server.id,
                instance_name=expected_app_name
            ).first()

            if app:
                logger.info(f"Найдено приложение по имени: {app.instance_name} на сервере {server.name}")
                return app

            # Если не нашли с номером instance, попробуем без него
            if instance > 0:
                app = Application.query.filter_by(
                    server_id=server.id,
                    instance_name=app_name
                ).first()

                if app:
                    logger.info(f"Найдено приложение по имени без instance: {app.instance_name} на сервере {server.name}")
                    return app

        logger.debug(f"Приложение с именем {expected_app_name} на хосте {hostname} не найдено")
        return None

    @staticmethod
    def map_server_to_application(haproxy_server: HAProxyServer) -> Optional[Application]:
        """
        Главный метод маппинга HAProxy сервера на приложение AC.
        Использует две стратегии по порядку:
        1. Маппинг по IP:port (если доступен addr)
        2. Маппинг по имени сервера

        ВАЖНО: Не перезаписывает ручной маппинг (is_manual_mapping=True).

        Args:
            haproxy_server: Объект HAProxyServer

        Returns:
            Application или None
        """
        # ЗАЩИТА РУЧНОГО МАППИНГА: не перезаписываем ручной маппинг
        # Проверяем в унифицированной таблице маппингов
        mapping_service = get_mapping_service()
        existing_mappings = mapping_service.get_mappings_for_entity(
            MappingType.HAPROXY_SERVER.value,
            haproxy_server.id,
            active_only=True
        )

        # Проверяем ручной маппинг
        if existing_mappings and existing_mappings[0].is_manual:
            logger.debug(f"Пропуск маппинга для {haproxy_server.server_name}: установлен ручной маппинг")
            return existing_mappings[0].application

        cache_key = f"{haproxy_server.id}"

        # Проверяем кэш
        if cache_key in HAProxyMapper._mapping_cache:
            cached_app_id = HAProxyMapper._mapping_cache[cache_key]
            if cached_app_id is None:
                return None
            return Application.query.get(cached_app_id)

        logger.info(f"Маппинг HAProxy сервера: {haproxy_server.server_name} (addr: {haproxy_server.addr})")

        application = None

        # Стратегия 1: Маппинг по IP:port
        if haproxy_server.addr:
            ip, port = HAProxyMapper.parse_address(haproxy_server.addr)
            if ip and port:
                application = HAProxyMapper.map_by_address(ip, port)
                if application:
                    logger.info(f"Маппинг успешен (по адресу): {haproxy_server.server_name} -> {application.instance_name}")
                    # Сохраняем в унифицированную таблицу маппингов
                    mapping_service.map_haproxy_server(
                        haproxy_server_id=haproxy_server.id,
                        application_id=application.id,
                        is_manual=False,
                        mapped_by='auto',
                        notes='Automatic mapping by address'
                    )

                    # Кэшируем результат
                    HAProxyMapper._mapping_cache[cache_key] = application.id
                    return application

        # Стратегия 2: Маппинг по имени
        hostname, app_name, instance = HAProxyMapper.parse_server_name(haproxy_server.server_name)
        if hostname and app_name:
            application = HAProxyMapper.map_by_name(hostname, app_name, instance)
            if application:
                logger.info(f"Маппинг успешен (по имени): {haproxy_server.server_name} -> {application.instance_name}")
                # Сохраняем в унифицированную таблицу маппингов
                mapping_service.map_haproxy_server(
                    haproxy_server_id=haproxy_server.id,
                    application_id=application.id,
                    is_manual=False,
                    mapped_by='auto',
                    notes='Automatic mapping by name'
                )

                # Кэшируем результат
                HAProxyMapper._mapping_cache[cache_key] = application.id
                return application

        # Маппинг не удался
        logger.warning(f"Не удалось найти приложение для HAProxy сервера: {haproxy_server.server_name}")

        # Кэшируем отсутствие результата
        HAProxyMapper._mapping_cache[cache_key] = None
        return None

    @staticmethod
    def remap_all_servers():
        """
        Повторный маппинг всех HAProxy серверов.
        Полезно после добавления новых приложений.

        ВАЖНО: Пропускает серверы с ручным маппингом (is_manual_mapping=True).
        """
        logger.info("Начало повторного маппинга всех HAProxy серверов")

        # Очищаем кэш
        HAProxyMapper.clear_cache()

        from app.models.application_mapping import ApplicationMapping

        # Получаем ID серверов с активными маппингами из унифицированной таблицы
        mapped_server_ids = db.session.query(ApplicationMapping.entity_id).filter(
            ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
            ApplicationMapping.is_active == True
        ).subquery()

        # Получаем все HAProxy серверы без привязки к приложению
        unmapped_servers = HAProxyServer.query.filter(
            ~HAProxyServer.id.in_(mapped_server_ids),
            HAProxyServer.removed_at.is_(None)
        ).all()

        mapped_count = 0
        total_count = len(unmapped_servers)

        # Подсчет ручных маппингов
        skipped_manual = ApplicationMapping.query.filter(
            ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
            ApplicationMapping.is_active == True,
            ApplicationMapping.is_manual == True
        ).count()

        logger.info(f"Найдено {total_count} несопоставленных серверов (пропущено {skipped_manual} с ручным маппингом)")

        for haproxy_server in unmapped_servers:
            application = HAProxyMapper.map_server_to_application(haproxy_server)
            if application:
                mapped_count += 1

        logger.info(f"Повторный маппинг завершен: {mapped_count}/{total_count} серверов сопоставлено")
        return mapped_count, total_count

    @staticmethod
    def clear_cache():
        """Очистить кэш маппинга"""
        HAProxyMapper._mapping_cache.clear()
        logger.info("Кэш HAProxyMapper очищен")

    @staticmethod
    def get_mapping_stats() -> dict:
        """
        Получить статистику маппинга.

        Returns:
            dict с информацией о маппинге (включая ручной/автоматический)
        """
        from app.models.application_mapping import ApplicationMapping, MappingType

        total_servers = HAProxyServer.query.filter(
            HAProxyServer.removed_at.is_(None)
        ).count()

        # Статистика из унифицированной таблицы маппингов
        mapped_servers = ApplicationMapping.query.filter(
            ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
            ApplicationMapping.is_active == True
        ).count()

        unmapped_servers = total_servers - mapped_servers

        # Статистика по ручному маппингу
        manual_mapped = ApplicationMapping.query.filter(
            ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
            ApplicationMapping.is_active == True,
            ApplicationMapping.is_manual == True
        ).count()

        auto_mapped = mapped_servers - manual_mapped

        return {
            'total': total_servers,
            'mapped': mapped_servers,
            'unmapped': unmapped_servers,
            'manual_mapped': manual_mapped,
            'auto_mapped': auto_mapped,
            'mapping_rate': round(mapped_servers / total_servers * 100, 2) if total_servers > 0 else 0
        }

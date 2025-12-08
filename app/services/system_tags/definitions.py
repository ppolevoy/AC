# app/services/system_tags/definitions.py
"""
Определения системных тегов и их конфигурация.

Этот файл содержит:
- SystemTagDefinition: dataclass для описания системного тега
- TriggerType: enum для типов триггеров автоназначения
- SYSTEM_TAGS: реестр всех системных тегов
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any


class TriggerType(Enum):
    """Тип триггера для автоназначения тега"""
    MANUAL = 'manual'           # Только ручное назначение
    MAPPING = 'mapping'         # При создании/удалении маппинга
    APP_TYPE = 'app_type'       # На основе app_type приложения
    CUSTOM = 'custom'           # Произвольная логика через handlers


@dataclass(frozen=True)
class SystemTagDefinition:
    """Определение системного тега"""
    name: str                                      # Уникальное имя тега (haproxy, eureka, docker...)
    display_name: str                              # Короткое имя для UI (H, E, docker...)
    description: str                               # Описание тега
    trigger_type: TriggerType                      # Тип триггера
    show_in_table: bool = False                    # Показывать в таблице приложений
    config_key: Optional[str] = None               # Ключ в конфиге для включения/выключения

    # Для MAPPING триггера
    mapping_entity_type: Optional[str] = None      # Тип маппинга (haproxy_server, eureka_instance)

    # Для APP_TYPE триггера
    app_type_value: Optional[str] = None           # Значение app_type

    # Для CUSTOM триггера
    custom_should_assign: Optional[Callable[['ApplicationInstance', dict], bool]] = None
    custom_should_remove: Optional[Callable[['ApplicationInstance', dict], bool]] = None

    # Стили
    border_color: str = '#6c757d'
    text_color: str = '#6c757d'


# Реестр системных тегов
SYSTEM_TAGS: dict[str, SystemTagDefinition] = {}


def _register_system_tags():
    """Регистрация всех системных тегов"""
    global SYSTEM_TAGS

    SYSTEM_TAGS = {
        # === Теги с автоназначением по маппингу ===
        'haproxy': SystemTagDefinition(
            name='haproxy',
            display_name='H',
            description='Приложение связано с HAProxy backend',
            trigger_type=TriggerType.MAPPING,
            show_in_table=True,
            config_key='AUTO_TAG_HAPROXY_ENABLED',
            mapping_entity_type='haproxy_server',
            border_color='#28a745',
            text_color='#28a745'
        ),

        'eureka': SystemTagDefinition(
            name='eureka',
            display_name='E',
            description='Приложение зарегистрировано в Eureka',
            trigger_type=TriggerType.MAPPING,
            show_in_table=True,
            config_key='AUTO_TAG_EUREKA_ENABLED',
            mapping_entity_type='eureka_instance',
            border_color='#007bff',
            text_color='#007bff'
        ),

        # === Теги с автоназначением по app_type ===
        'docker': SystemTagDefinition(
            name='docker',
            display_name='docker',
            description='Docker-контейнер',
            trigger_type=TriggerType.APP_TYPE,
            show_in_table=True,
            config_key='AUTO_TAG_DOCKER_ENABLED',
            app_type_value='docker',
            border_color='#2496ed',
            text_color='#2496ed'
        ),

        # === Ручные теги ===
        'disable': SystemTagDefinition(
            name='disable',
            display_name='disable',
            description='Отключенное приложение',
            trigger_type=TriggerType.MANUAL,
            show_in_table=False,
            border_color='#6c757d',
            text_color='#6c757d'
        ),

        'system': SystemTagDefinition(
            name='system',
            display_name='SYS',
            description='Системное приложение',
            trigger_type=TriggerType.MANUAL,
            show_in_table=False,
            border_color='#6f42c1',
            text_color='#6f42c1'
        ),

        'smf': SystemTagDefinition(
            name='smf',
            display_name='smf',
            description='SMF сервис (Solaris)',
            trigger_type=TriggerType.APP_TYPE,
            show_in_table=False,
            config_key='AUTO_TAG_SMF_ENABLED',
            app_type_value='smf',
            border_color='#fd7e14',
            text_color='#fd7e14'
        ),

        'sysctl': SystemTagDefinition(
            name='sysctl',
            display_name='sysctl',
            description='Systemctl сервис',
            trigger_type=TriggerType.APP_TYPE,
            show_in_table=False,
            config_key='AUTO_TAG_SYSCTL_ENABLED',
            app_type_value='sysctl',
            border_color='#20c997',
            text_color='#20c997'
        ),

        'ver.lock': SystemTagDefinition(
            name='ver.lock',
            display_name='v.lock',
            description='Блокировка обновлений',
            trigger_type=TriggerType.MANUAL,
            show_in_table=False,
            border_color='#dc3545',
            text_color='#dc3545'
        ),

        'status.lock': SystemTagDefinition(
            name='status.lock',
            display_name='s.lock',
            description='Блокировка start/stop/restart',
            trigger_type=TriggerType.MANUAL,
            show_in_table=False,
            border_color='#ffc107',
            text_color='#856404'
        ),

        # === Автоматические теги мониторинга ===
        'pending_removal': SystemTagDefinition(
            name='pending_removal',
            display_name='DEL',
            description='Приложение будет удалено (offline > N дней)',
            trigger_type=TriggerType.MANUAL,  # Назначается автоматически из monitoring
            show_in_table=True,
            border_color='#dc3545',
            text_color='#dc3545'
        ),
    }


# Инициализация при импорте
_register_system_tags()


def _validate_config_keys():
    """Проверка валидности config_key для всех тегов"""
    from app.config import Config

    invalid_keys = []
    for tag_name, tag_def in SYSTEM_TAGS.items():
        if tag_def.config_key and not hasattr(Config, tag_def.config_key):
            invalid_keys.append(f"{tag_name}: {tag_def.config_key}")

    if invalid_keys:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Invalid config_keys in system tags: {', '.join(invalid_keys)}")


# Валидация при импорте (только warning, не блокирует запуск)
try:
    _validate_config_keys()
except ImportError:
    pass  # Config может быть недоступен при начальной загрузке


def get_tag_definition(tag_name: str) -> Optional[SystemTagDefinition]:
    """Получить определение тега по имени"""
    return SYSTEM_TAGS.get(tag_name)


def get_tags_by_trigger_type(trigger_type: TriggerType) -> list[SystemTagDefinition]:
    """Получить теги по типу триггера"""
    return [tag for tag in SYSTEM_TAGS.values() if tag.trigger_type == trigger_type]


def get_mapping_tags() -> dict[str, SystemTagDefinition]:
    """Получить теги с автоназначением по маппингу"""
    return {
        tag.mapping_entity_type: tag
        for tag in SYSTEM_TAGS.values()
        if tag.trigger_type == TriggerType.MAPPING and tag.mapping_entity_type
    }


def get_app_type_tags() -> dict[str, SystemTagDefinition]:
    """Получить теги с автоназначением по app_type"""
    return {
        tag.app_type_value: tag
        for tag in SYSTEM_TAGS.values()
        if tag.trigger_type == TriggerType.APP_TYPE and tag.app_type_value
    }

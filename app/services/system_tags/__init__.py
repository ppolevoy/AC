# app/services/system_tags/__init__.py
"""
Модуль системных тегов.

Предоставляет:
- SystemTagsService: сервис управления системными тегами
- SYSTEM_TAGS: реестр определений системных тегов
- SystemTagDefinition: dataclass для описания тега
- TriggerType: enum типов триггеров

Использование:
    from app.services.system_tags import SystemTagsService

    # При создании маппинга
    SystemTagsService.on_mapping_created(instance, 'haproxy_server')

    # При синхронизации приложения
    SystemTagsService.on_app_synced(instance)

    # Миграция существующих данных
    stats = SystemTagsService.migrate_existing_data()
"""

from .definitions import (
    SYSTEM_TAGS,
    SystemTagDefinition,
    TriggerType,
    get_tag_definition,
    get_mapping_tags,
    get_app_type_tags,
    get_tags_by_trigger_type
)

from .service import SystemTagsService

__all__ = [
    'SystemTagsService',
    'SYSTEM_TAGS',
    'SystemTagDefinition',
    'TriggerType',
    'get_tag_definition',
    'get_mapping_tags',
    'get_app_type_tags',
    'get_tags_by_trigger_type'
]

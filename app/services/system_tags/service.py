# app/services/system_tags/service.py
"""
Сервис управления системными тегами.

Предоставляет методы для:
- Автоназначения тегов при создании/удалении маппингов
- Автоназначения тегов при синхронизации приложений
- Проверки включенности тегов через конфигурацию
- Миграции существующих данных
"""

import logging
from typing import TYPE_CHECKING, Optional

from app import db
from app.config import Config
from app.models.tag import Tag, ApplicationInstanceTag
from .definitions import (
    SYSTEM_TAGS,
    TriggerType,
    SystemTagDefinition,
    get_mapping_tags,
    get_app_type_tags,
    get_tag_definition
)

if TYPE_CHECKING:
    from app.models.application_instance import ApplicationInstance

logger = logging.getLogger(__name__)


class SystemTagsService:
    """Сервис для управления системными тегами"""

    @classmethod
    def is_enabled(cls) -> bool:
        """Проверить, включена ли система тегов глобально"""
        return Config.SYSTEM_TAGS_ENABLED

    @classmethod
    def is_tag_enabled(cls, tag_def: SystemTagDefinition) -> bool:
        """Проверить, включен ли конкретный тег для автоназначения"""
        if not cls.is_enabled():
            return False
        if tag_def.trigger_type == TriggerType.MANUAL:
            return False  # Ручные теги не автоназначаются
        if not tag_def.config_key:
            return True  # Если нет ключа конфига - всегда включен
        return getattr(Config, tag_def.config_key, False)

    @classmethod
    def is_auto_assign_disabled(cls, instance: 'ApplicationInstance', tag_name: str) -> bool:
        """Проверить, отключено ли автоназначение для конкретного instance+tag"""
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            return False
        link = ApplicationInstanceTag.query.filter_by(
            application_id=instance.id,
            tag_id=tag.id
        ).first()
        return link.auto_assign_disabled if link else False

    @classmethod
    def _get_or_create_tag(cls, tag_name: str) -> Optional[Tag]:
        """Получить тег из БД или создать если не существует"""
        tag = Tag.query.filter_by(name=tag_name).first()
        if tag:
            return tag

        # Создаем тег если его нет (на случай если миграция не была применена)
        tag_def = get_tag_definition(tag_name)
        if not tag_def:
            logger.warning(f"Тег '{tag_name}' не найден в определениях")
            return None

        tag = Tag(
            name=tag_def.name,
            display_name=tag_def.display_name,
            description=tag_def.description,
            is_system=True,
            show_in_table=tag_def.show_in_table,
            tag_type='system',
            border_color=tag_def.border_color,
            text_color=tag_def.text_color,
            icon='●',
            css_class='tag-system'
        )
        db.session.add(tag)
        logger.info(f"Создан системный тег '{tag_name}'")
        return tag

    @classmethod
    def assign_tag(cls, instance: 'ApplicationInstance', tag_name: str,
                   assigned_by: str = 'system') -> bool:
        """
        Назначить тег приложению.

        Args:
            instance: Экземпляр приложения
            tag_name: Имя тега
            assigned_by: Кто назначил (system, manual, ...)

        Returns:
            True если тег был назначен, False если уже был или ошибка
        """
        try:
            tag = cls._get_or_create_tag(tag_name)
            if not tag:
                return False

            # Проверяем, не назначен ли уже
            existing = ApplicationInstanceTag.query.filter_by(
                application_id=instance.id,
                tag_id=tag.id
            ).first()

            if existing:
                return False  # Тег уже назначен

            # Создаем связь
            link = ApplicationInstanceTag(
                application_id=instance.id,
                tag_id=tag.id,
                assigned_by=assigned_by,
                auto_assign_disabled=False
            )
            db.session.add(link)
            logger.debug(f"Тег '{tag_name}' назначен приложению {instance.name} (id={instance.id})")
            return True

        except Exception as e:
            logger.error(f"Ошибка назначения тега '{tag_name}' приложению {instance.id}: {e}")
            return False

    @classmethod
    def remove_tag(cls, instance: 'ApplicationInstance', tag_name: str) -> bool:
        """
        Удалить тег с приложения.

        Args:
            instance: Экземпляр приложения
            tag_name: Имя тега

        Returns:
            True если тег был удален, False если не был назначен или ошибка
        """
        try:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                return False

            link = ApplicationInstanceTag.query.filter_by(
                application_id=instance.id,
                tag_id=tag.id
            ).first()

            if not link:
                return False  # Тег не был назначен

            # Проверяем, не отключено ли автоудаление
            if link.auto_assign_disabled:
                logger.debug(f"Автоудаление тега '{tag_name}' отключено для {instance.name}")
                return False

            db.session.delete(link)
            logger.debug(f"Тег '{tag_name}' удален с приложения {instance.name} (id={instance.id})")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления тега '{tag_name}' с приложения {instance.id}: {e}")
            return False

    # ========== Триггеры автоназначения ==========

    @classmethod
    def on_mapping_created(cls, instance: 'ApplicationInstance', entity_type: str,
                           context: Optional[dict] = None) -> bool:
        """
        Вызывается при создании маппинга (HAProxy, Eureka).

        Args:
            instance: Экземпляр приложения
            entity_type: Тип маппинга (haproxy_server, eureka_instance)
            context: Дополнительный контекст

        Returns:
            True если тег был назначен
        """
        mapping_tags = get_mapping_tags()
        tag_def = mapping_tags.get(entity_type)

        if not tag_def:
            logger.debug(f"Нет тега для маппинга типа '{entity_type}'")
            return False

        if not cls.is_tag_enabled(tag_def):
            logger.debug(f"Автоназначение тега '{tag_def.name}' отключено в конфиге")
            return False

        if cls.is_auto_assign_disabled(instance, tag_def.name):
            logger.debug(f"Автоназначение тега '{tag_def.name}' отключено для {instance.name}")
            return False

        return cls.assign_tag(instance, tag_def.name, assigned_by='auto:mapping')

    @classmethod
    def on_mapping_deleted(cls, instance: 'ApplicationInstance', entity_type: str,
                           context: Optional[dict] = None) -> bool:
        """
        Вызывается при удалении маппинга.

        Args:
            instance: Экземпляр приложения
            entity_type: Тип маппинга (haproxy_server, eureka_instance)
            context: Дополнительный контекст

        Returns:
            True если тег был удален
        """
        mapping_tags = get_mapping_tags()
        tag_def = mapping_tags.get(entity_type)

        if not tag_def:
            return False

        if not cls.is_tag_enabled(tag_def):
            return False

        return cls.remove_tag(instance, tag_def.name)

    @classmethod
    def on_app_synced(cls, instance: 'ApplicationInstance',
                      context: Optional[dict] = None) -> list[str]:
        """
        Вызывается при синхронизации приложения.
        Проверяет и обновляет теги на основе app_type.

        Args:
            instance: Экземпляр приложения
            context: Дополнительный контекст

        Returns:
            Список назначенных тегов
        """
        assigned = []
        app_type_tags = get_app_type_tags()

        # Предзагружаем текущие теги instance для избежания N+1 запросов
        instance_tag_names = set()
        try:
            instance_tag_names = {t.name for t in instance.tags}
        except Exception:
            pass  # Если теги недоступны, продолжаем без оптимизации

        # Назначаем тег если app_type совпадает
        tag_def = app_type_tags.get(instance.app_type)
        if tag_def and cls.is_tag_enabled(tag_def):
            if not cls.is_auto_assign_disabled(instance, tag_def.name):
                if cls.assign_tag(instance, tag_def.name, assigned_by='auto:app_type'):
                    assigned.append(tag_def.name)

        # Удаляем теги app_type которые больше не соответствуют
        # (только если тег фактически назначен - избегаем лишних запросов)
        for app_type_value, other_tag_def in app_type_tags.items():
            if app_type_value != instance.app_type:
                # Проверяем наличие тега перед удалением
                if other_tag_def.name in instance_tag_names:
                    if cls.is_tag_enabled(other_tag_def):
                        cls.remove_tag(instance, other_tag_def.name)

        return assigned

    # ========== Миграция существующих данных ==========

    @classmethod
    def migrate_existing_data(cls, batch_size: int = 100) -> dict:
        """
        Миграция существующих данных - назначение тегов
        на основе текущих маппингов и app_type.

        Args:
            batch_size: Размер батча для коммитов (по умолчанию 100)

        Returns:
            Статистика миграции
        """
        from app.models.application_instance import ApplicationInstance
        from app.models.application_mapping import ApplicationMapping

        stats = {
            'haproxy_assigned': 0,
            'eureka_assigned': 0,
            'docker_assigned': 0,
            'smf_assigned': 0,
            'sysctl_assigned': 0,
            'errors': 0,
            'batches_committed': 0
        }

        if not cls.is_enabled():
            logger.warning("Система тегов отключена, миграция пропущена")
            return stats

        operations_in_batch = 0

        def commit_batch():
            nonlocal operations_in_batch
            if operations_in_batch > 0:
                try:
                    db.session.commit()
                    stats['batches_committed'] += 1
                    operations_in_batch = 0
                except Exception as e:
                    db.session.rollback()
                    stats['errors'] += 1
                    logger.error(f"Ошибка коммита батча: {e}")
                    operations_in_batch = 0

        try:
            # 1. Теги на основе маппингов
            mapping_tags = get_mapping_tags()

            for entity_type, tag_def in mapping_tags.items():
                if not cls.is_tag_enabled(tag_def):
                    continue

                # Находим все активные маппинги этого типа
                mappings = ApplicationMapping.query.filter_by(
                    entity_type=entity_type,
                    is_active=True
                ).all()

                for mapping in mappings:
                    try:
                        instance = ApplicationInstance.query.get(mapping.application_id)
                        if instance and not instance.deleted_at:
                            if cls.assign_tag(instance, tag_def.name, assigned_by='migration'):
                                stats[f'{tag_def.name}_assigned'] = stats.get(f'{tag_def.name}_assigned', 0) + 1
                                operations_in_batch += 1

                                if operations_in_batch >= batch_size:
                                    commit_batch()
                    except Exception as e:
                        stats['errors'] += 1
                        logger.warning(f"Ошибка назначения тега {tag_def.name} для mapping {mapping.id}: {e}")

            # 2. Теги на основе app_type
            app_type_tags = get_app_type_tags()

            for app_type_value, tag_def in app_type_tags.items():
                if not cls.is_tag_enabled(tag_def):
                    continue

                instances = ApplicationInstance.query.filter_by(
                    app_type=app_type_value,
                    deleted_at=None
                ).all()

                for instance in instances:
                    try:
                        if cls.assign_tag(instance, tag_def.name, assigned_by='migration'):
                            stats[f'{tag_def.name}_assigned'] = stats.get(f'{tag_def.name}_assigned', 0) + 1
                            operations_in_batch += 1

                            if operations_in_batch >= batch_size:
                                commit_batch()
                    except Exception as e:
                        stats['errors'] += 1
                        logger.warning(f"Ошибка назначения тега {tag_def.name} для instance {instance.id}: {e}")

            # Финальный коммит оставшихся операций
            commit_batch()
            logger.info(f"Миграция системных тегов завершена: {stats}")

        except Exception as e:
            db.session.rollback()
            stats['errors'] += 1
            logger.error(f"Ошибка миграции системных тегов: {e}")

        return stats

    @classmethod
    def set_auto_assign_disabled(cls, instance: 'ApplicationInstance', tag_name: str,
                                  disabled: bool, user: Optional[str] = None) -> bool:
        """
        Установить флаг отключения автоназначения для конкретного тега на instance.

        Args:
            instance: Экземпляр приложения
            tag_name: Имя тега
            disabled: True - отключить автоназначение, False - включить
            user: Пользователь, выполняющий операцию

        Returns:
            True если успешно
        """
        from app.models.tag import TagHistory

        try:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                return False

            link = ApplicationInstanceTag.query.filter_by(
                application_id=instance.id,
                tag_id=tag.id
            ).first()

            if link:
                link.auto_assign_disabled = disabled
            else:
                # Создаем связь с флагом disabled
                link = ApplicationInstanceTag(
                    application_id=instance.id,
                    tag_id=tag.id,
                    assigned_by='manual',
                    auto_assign_disabled=disabled
                )
                db.session.add(link)

            # Записываем в историю
            history = TagHistory(
                entity_type='instance',
                entity_id=instance.id,
                tag_id=tag.id,
                action='auto_assign_disabled' if disabled else 'auto_assign_enabled',
                changed_by=user,
                details={'auto_assign_disabled': disabled}
            )
            db.session.add(history)

            logger.info(f"auto_assign_disabled={disabled} для тега '{tag_name}' на {instance.name}")
            return True

        except Exception as e:
            logger.error(f"Ошибка установки auto_assign_disabled: {e}")
            return False

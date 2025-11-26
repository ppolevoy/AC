# app/services/mapping_service.py
"""
Унифицированный сервис для управления маппингами приложений на внешние сервисы.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from app import db
from app.models.application_mapping import ApplicationMapping, ApplicationMappingHistory, MappingType
from app.models.application_instance import ApplicationInstance
import logging

logger = logging.getLogger(__name__)


class MappingService:
    """Унифицированный сервис для управления маппингами приложений"""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 минут

    def create_mapping(
        self,
        application_id: int,
        entity_type: str,
        entity_id: int,
        is_manual: bool = False,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ApplicationMapping]:
        """Создать новый маппинг"""
        try:
            # Проверка существования приложения
            app = ApplicationInstance.query.get(application_id)
            if not app:
                logger.error(f"Application {application_id} not found")
                return None

            # Создание маппинга
            mapping = ApplicationMapping(
                application_id=application_id,
                entity_type=entity_type,
                entity_id=entity_id,
                is_manual=is_manual,
                mapped_by=mapped_by,
                mapped_at=datetime.utcnow(),
                notes=notes,
                mapping_metadata=metadata
            )

            db.session.add(mapping)
            db.session.flush()  # Получаем ID для истории

            # Создание записи в истории
            self._create_history(
                mapping=mapping,
                action='created',
                new_values=self._mapping_to_history_dict(mapping),
                changed_by=mapped_by,
                reason=notes
            )

            db.session.commit()
            self._invalidate_cache(application_id)

            logger.info(f"Created mapping: app={application_id}, type={entity_type}, entity={entity_id}")
            return mapping

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Mapping already exists or constraint violation: {e}")
            return None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create mapping: {e}")
            return None

    def update_mapping(
        self,
        mapping_id: int,
        is_manual: Optional[bool] = None,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None
    ) -> Optional[ApplicationMapping]:
        """Обновить существующий маппинг"""
        mapping = ApplicationMapping.query.get(mapping_id)
        if not mapping:
            logger.error(f"Mapping {mapping_id} not found")
            return None

        old_values = self._mapping_to_history_dict(mapping)

        # Обновление полей
        if is_manual is not None:
            mapping.is_manual = is_manual
        if mapped_by is not None:
            mapping.mapped_by = mapped_by
        if notes is not None:
            mapping.notes = notes
        if metadata is not None:
            mapping.mapping_metadata = metadata
        if is_active is not None:
            mapping.is_active = is_active

        mapping.updated_at = datetime.utcnow()

        # Определение действия для истории
        action = 'updated'
        if is_active is False:
            action = 'deactivated'
        elif is_active is True and not old_values.get('is_active'):
            action = 'activated'

        # История
        self._create_history(
            mapping=mapping,
            action=action,
            old_values=old_values,
            new_values=self._mapping_to_history_dict(mapping),
            changed_by=mapped_by,
            reason=notes
        )

        db.session.commit()
        self._invalidate_cache(mapping.application_id)

        return mapping

    def delete_mapping(
        self,
        mapping_id: int,
        deleted_by: Optional[str] = None,
        reason: Optional[str] = None
    ) -> bool:
        """Удалить маппинг"""
        mapping = ApplicationMapping.query.get(mapping_id)
        if not mapping:
            return False

        # История удаления
        self._create_history(
            mapping=mapping,
            action='deleted',
            old_values=self._mapping_to_history_dict(mapping),
            changed_by=deleted_by,
            reason=reason
        )

        app_id = mapping.application_id
        db.session.delete(mapping)
        db.session.commit()

        self._invalidate_cache(app_id)
        return True

    def get_mapping_by_id(self, mapping_id: int) -> Optional[ApplicationMapping]:
        """Получить маппинг по ID"""
        return ApplicationMapping.query.get(mapping_id)

    def get_mappings_for_application(
        self,
        application_id: int,
        entity_type: Optional[str] = None,
        active_only: bool = True
    ) -> List[ApplicationMapping]:
        """Получить все маппинги для приложения"""
        query = ApplicationMapping.query.filter_by(application_id=application_id)

        if entity_type:
            query = query.filter_by(entity_type=entity_type)

        if active_only:
            query = query.filter_by(is_active=True)

        return query.all()

    def get_mappings_for_entity(
        self,
        entity_type: str,
        entity_id: int,
        active_only: bool = True
    ) -> List[ApplicationMapping]:
        """Получить маппинги для сущности"""
        query = ApplicationMapping.query.filter_by(
            entity_type=entity_type,
            entity_id=entity_id
        )

        if active_only:
            query = query.filter_by(is_active=True)

        return query.all()

    def get_application_for_entity(
        self,
        entity_type: str,
        entity_id: int
    ) -> Optional[ApplicationInstance]:
        """Получить приложение, связанное с сущностью"""
        mappings = self.get_mappings_for_entity(entity_type, entity_id, active_only=True)
        if mappings:
            return mappings[0].application
        return None

    def map_haproxy_server(
        self,
        haproxy_server_id: int,
        application_id: int,
        is_manual: bool = False,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[ApplicationMapping]:
        """Специализированный метод для HAProxy"""
        # Проверка существования HAProxyServer
        from app.models.haproxy import HAProxyServer
        server = HAProxyServer.query.get(haproxy_server_id)
        if not server:
            logger.error(f"HAProxyServer {haproxy_server_id} not found")
            return None

        # Проверяем, существует ли уже такой маппинг (активный или нет)
        existing_mapping = ApplicationMapping.query.filter_by(
            application_id=application_id,
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=haproxy_server_id
        ).first()

        if existing_mapping:
            # Маппинг уже существует - активируем/обновляем его
            if existing_mapping.is_active:
                # Уже активен с тем же приложением - ничего не делаем
                logger.debug(f"Mapping already exists and active: app={application_id}, server={haproxy_server_id}")
                return existing_mapping

            # Деактивируем другие маппинги для этого сервера
            other_mappings = ApplicationMapping.query.filter(
                ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
                ApplicationMapping.entity_id == haproxy_server_id,
                ApplicationMapping.id != existing_mapping.id,
                ApplicationMapping.is_active == True
            ).all()

            for other in other_mappings:
                self.update_mapping(
                    other.id,
                    is_active=False,
                    mapped_by=mapped_by,
                    notes="Deactivated due to new mapping"
                )

            # Активируем существующий маппинг
            return self.update_mapping(
                existing_mapping.id,
                is_active=True,
                is_manual=is_manual,
                mapped_by=mapped_by,
                notes=notes,
                metadata={
                    'backend_name': server.backend.backend_name if server.backend else None,
                    'server_name': server.server_name,
                    'address': server.addr
                }
            )

        # Деактивация старых маппингов для этого сервера
        old_mappings = self.get_mappings_for_entity(
            MappingType.HAPROXY_SERVER.value,
            haproxy_server_id,
            active_only=True
        )

        for old_mapping in old_mappings:
            self.update_mapping(
                old_mapping.id,
                is_active=False,
                mapped_by=mapped_by,
                notes="Deactivated due to new mapping"
            )

        # Создание нового маппинга
        return self.create_mapping(
            application_id=application_id,
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=haproxy_server_id,
            is_manual=is_manual,
            mapped_by=mapped_by,
            notes=notes,
            metadata={
                'backend_name': server.backend.backend_name if server.backend else None,
                'server_name': server.server_name,
                'address': server.addr
            }
        )

    def map_eureka_instance(
        self,
        eureka_instance_id: int,
        application_id: int,
        is_manual: bool = False,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[ApplicationMapping]:
        """Специализированный метод для Eureka"""
        # Проверка существования EurekaInstance
        from app.models.eureka import EurekaInstance
        instance = EurekaInstance.query.get(eureka_instance_id)
        if not instance:
            logger.error(f"EurekaInstance {eureka_instance_id} not found")
            return None

        # Проверяем, существует ли уже такой маппинг (активный или нет)
        existing_mapping = ApplicationMapping.query.filter_by(
            application_id=application_id,
            entity_type=MappingType.EUREKA_INSTANCE.value,
            entity_id=eureka_instance_id
        ).first()

        if existing_mapping:
            # Маппинг уже существует - активируем/обновляем его
            if existing_mapping.is_active:
                # Уже активен с тем же приложением - ничего не делаем
                logger.debug(f"Mapping already exists and active: app={application_id}, instance={eureka_instance_id}")
                return existing_mapping

            # Деактивируем другие маппинги для этого инстанса
            other_mappings = ApplicationMapping.query.filter(
                ApplicationMapping.entity_type == MappingType.EUREKA_INSTANCE.value,
                ApplicationMapping.entity_id == eureka_instance_id,
                ApplicationMapping.id != existing_mapping.id,
                ApplicationMapping.is_active == True
            ).all()

            for other in other_mappings:
                self.update_mapping(
                    other.id,
                    is_active=False,
                    mapped_by=mapped_by,
                    notes="Deactivated due to new mapping"
                )

            # Активируем существующий маппинг
            return self.update_mapping(
                existing_mapping.id,
                is_active=True,
                is_manual=is_manual,
                mapped_by=mapped_by,
                notes=notes,
                metadata={
                    'service_name': instance.eureka_application.app_name if instance.eureka_application else None,
                    'instance_id': instance.instance_id,
                    'eureka_url': instance.eureka_url
                }
            )

        # Деактивация старых маппингов для этого инстанса
        old_mappings = self.get_mappings_for_entity(
            MappingType.EUREKA_INSTANCE.value,
            eureka_instance_id,
            active_only=True
        )

        for old_mapping in old_mappings:
            self.update_mapping(
                old_mapping.id,
                is_active=False,
                mapped_by=mapped_by,
                notes="Deactivated due to new mapping"
            )

        # Создание нового маппинга
        return self.create_mapping(
            application_id=application_id,
            entity_type=MappingType.EUREKA_INSTANCE.value,
            entity_id=eureka_instance_id,
            is_manual=is_manual,
            mapped_by=mapped_by,
            notes=notes,
            metadata={
                'service_name': instance.eureka_application.app_name if instance.eureka_application else None,
                'instance_id': instance.instance_id,
                'eureka_url': instance.eureka_url
            }
        )

    def unmap_entity(
        self,
        entity_type: str,
        entity_id: int,
        unmapped_by: Optional[str] = None,
        reason: Optional[str] = None
    ) -> int:
        """Отвязать все маппинги для сущности"""
        mappings = self.get_mappings_for_entity(entity_type, entity_id, active_only=True)
        count = 0

        for mapping in mappings:
            self.update_mapping(
                mapping.id,
                is_active=False,
                mapped_by=unmapped_by,
                notes=reason or "Unmapped"
            )
            count += 1

        return count

    def get_mapping_history(
        self,
        mapping_id: Optional[int] = None,
        application_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        limit: int = 100
    ) -> List[ApplicationMappingHistory]:
        """Получить историю маппингов"""
        query = ApplicationMappingHistory.query

        if mapping_id:
            query = query.filter_by(mapping_id=mapping_id)
        if application_id:
            query = query.filter_by(application_id=application_id)
        if entity_type:
            query = query.filter_by(entity_type=entity_type)
        if entity_id:
            query = query.filter_by(entity_id=entity_id)

        return query.order_by(ApplicationMappingHistory.changed_at.desc()).limit(limit).all()

    def get_mapping_statistics(self) -> Dict[str, Any]:
        """Получить статистику маппингов"""
        from app.models.haproxy import HAProxyServer
        from app.models.eureka import EurekaInstance

        stats = {
            'total': ApplicationMapping.query.count(),
            'active': ApplicationMapping.query.filter_by(is_active=True).count(),
            'manual': ApplicationMapping.query.filter_by(is_manual=True, is_active=True).count(),
            'automatic': ApplicationMapping.query.filter_by(is_manual=False, is_active=True).count(),
            'by_type': {},
            'unmapped': {}
        }

        for mapping_type in MappingType:
            stats['by_type'][mapping_type.value] = {
                'total': ApplicationMapping.query.filter_by(entity_type=mapping_type.value).count(),
                'active': ApplicationMapping.query.filter_by(
                    entity_type=mapping_type.value,
                    is_active=True
                ).count()
            }

        # Подсчёт неназначенных сущностей
        # HAProxy серверы без маппинга
        mapped_haproxy_ids = db.session.query(ApplicationMapping.entity_id).filter(
            ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
            ApplicationMapping.is_active == True
        ).scalar_subquery()

        unmapped_haproxy = HAProxyServer.query.filter(
            ~HAProxyServer.id.in_(mapped_haproxy_ids),
            HAProxyServer.removed_at.is_(None)
        ).count()

        # Eureka instances без маппинга
        mapped_eureka_ids = db.session.query(ApplicationMapping.entity_id).filter(
            ApplicationMapping.entity_type == MappingType.EUREKA_INSTANCE.value,
            ApplicationMapping.is_active == True
        ).scalar_subquery()

        unmapped_eureka = EurekaInstance.query.filter(
            ~EurekaInstance.id.in_(mapped_eureka_ids),
            EurekaInstance.removed_at.is_(None)
        ).count()

        stats['unmapped'] = {
            'haproxy_server': unmapped_haproxy,
            'eureka_instance': unmapped_eureka,
            'total': unmapped_haproxy + unmapped_eureka
        }

        return stats

    def _create_history(
        self,
        mapping: ApplicationMapping,
        action: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """Создать запись в истории"""
        history = ApplicationMappingHistory(
            mapping_id=mapping.id if action != 'deleted' else None,
            application_id=mapping.application_id,
            entity_type=mapping.entity_type,
            entity_id=mapping.entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            changed_by=changed_by,
            changed_at=datetime.utcnow(),
            reason=reason
        )
        db.session.add(history)

    def _mapping_to_history_dict(self, mapping: ApplicationMapping) -> Dict[str, Any]:
        """Преобразовать маппинг в словарь для истории"""
        return {
            'application_id': mapping.application_id,
            'entity_type': mapping.entity_type,
            'entity_id': mapping.entity_id,
            'is_manual': mapping.is_manual,
            'mapped_by': mapping.mapped_by,
            'notes': mapping.notes,
            'is_active': mapping.is_active,
            'metadata': mapping.mapping_metadata
        }

    def _invalidate_cache(self, application_id: int):
        """Инвалидировать кеш для приложения"""
        cache_keys_to_remove = [
            key for key in self._cache.keys()
            if key.startswith(f"app_{application_id}_")
        ]
        for key in cache_keys_to_remove:
            del self._cache[key]


# Singleton
mapping_service = MappingService()

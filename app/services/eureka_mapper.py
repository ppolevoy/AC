# -*- coding: utf-8 -*-
"""
EurekaMapper - сервис для маппинга Eureka экземпляров на приложения AC.
Основная стратегия: сопоставление по eureka_url для Docker приложений.
"""
import logging
from typing import List, Optional, Tuple
from app import db
from app.models.application_instance import ApplicationInstance
from app.models.eureka import EurekaInstance
from app.models.application_mapping import MappingType
from difflib import SequenceMatcher

# Алиас для обратной совместимости
Application = ApplicationInstance

logger = logging.getLogger(__name__)

# Lazy import для избежания циклических импортов
def get_mapping_service():
    from app.services.mapping_service import mapping_service
    return mapping_service


class EurekaMapper:
    """Сервис для автоматического и ручного маппинга Eureka экземпляров"""

    @staticmethod
    def map_instances_to_applications() -> Tuple[int, int]:
        """
        Основной метод маппинга - связывает все несвязанные Eureka экземпляры с AC приложениями.

        Returns:
            Tuple[mapped_count, total_unmapped]: Количество связанных и общее количество несвязанных
        """
        logger.info("Начало автоматического маппинга Eureka экземпляров на приложения")

        mapping_service = get_mapping_service()
        from app.models.application_mapping import ApplicationMapping

        # Получаем ID экземпляров с активными маппингами из унифицированной таблицы
        mapped_instance_ids = db.session.query(ApplicationMapping.entity_id).filter(
            ApplicationMapping.entity_type == MappingType.EUREKA_INSTANCE.value,
            ApplicationMapping.is_active == True
        ).subquery()

        # Получаем все несвязанные экземпляры
        unmapped_instances = EurekaInstance.query.filter(
            ~EurekaInstance.id.in_(mapped_instance_ids),
            EurekaInstance.removed_at.is_(None)
        ).all()

        if not unmapped_instances:
            logger.info("Нет несвязанных экземпляров для маппинга")
            return 0, 0

        logger.info(f"Найдено {len(unmapped_instances)} несвязанных экземпляров")

        mapped_count = 0

        for instance in unmapped_instances:
            # Проверяем ручной маппинг в новой таблице
            existing_mappings = mapping_service.get_mappings_for_entity(
                MappingType.EUREKA_INSTANCE.value,
                instance.id,
                active_only=True
            )
            if existing_mappings and existing_mappings[0].is_manual:
                logger.debug(f"Пропуск маппинга для {instance.instance_id}: установлен ручной маппинг (unified)")
                continue

            # Пробуем основную стратегию - по eureka_url
            app_id = EurekaMapper.map_by_eureka_url(instance)

            # Если не удалось - пробуем резервные стратегии
            if not app_id:
                app_id = EurekaMapper.map_by_server_and_name(instance)

            # Если нашли соответствие - устанавливаем маппинг
            if app_id:
                # Сохраняем в унифицированную таблицу маппингов
                mapping_service.map_eureka_instance(
                    eureka_instance_id=instance.id,
                    application_id=app_id,
                    is_manual=False,
                    mapped_by='auto',
                    notes='Automatic mapping'
                )

                mapped_count += 1
                logger.info(f"Автоматически связан Eureka экземпляр {instance.instance_id} с приложением ID={app_id}")

        db.session.commit()

        logger.info(f"Маппинг завершен: связано {mapped_count} из {len(unmapped_instances)} экземпляров")
        return mapped_count, len(unmapped_instances)

    @staticmethod
    def map_by_eureka_url(instance: EurekaInstance) -> Optional[int]:
        """
        Маппинг по eureka_url (основная стратегия для Docker приложений).

        Args:
            instance: Eureka экземпляр

        Returns:
            application_id или None
        """
        # Формируем IP:port из экземпляра
        ip_port = f"{instance.ip_address}:{instance.port}"

        # Ищем приложение с соответствующим eureka_url
        application = Application.query.filter(
            Application.eureka_url == ip_port
        ).first()

        if application:
            logger.debug(f"Найдено соответствие по eureka_url: {instance.instance_id} -> {application.instance_name} (ID={application.id})")
            return application.id

        return None

    @staticmethod
    def map_by_server_and_name(instance: EurekaInstance) -> Optional[int]:
        """
        Маппинг по серверу и имени (резервная стратегия).
        Ищет приложения на сервере с похожим именем.

        Args:
            instance: Eureka экземпляр

        Returns:
            application_id или None
        """
        # Получаем все приложения на серверах с соответствующим IP
        applications = Application.query.join(Application.server).filter(
            db.or_(
                db.func.lower(db.text("servers.ip")) == instance.ip_address.lower(),
                db.text("servers.ip") == instance.ip_address
            )
        ).all()

        if not applications:
            logger.debug(f"Нет приложений на сервере с IP {instance.ip_address}")
            return None

        # Используем fuzzy matching для поиска наиболее похожего имени
        best_match = None
        best_ratio = 0.0
        threshold = 0.6  # Минимальное сходство для матча

        service_name_lower = instance.service_name.lower()

        for app in applications:
            app_name_lower = app.instance_name.lower()

            # Вычисляем сходство имён
            ratio = SequenceMatcher(None, service_name_lower, app_name_lower).ratio()

            # Дополнительный бонус если имя сервиса содержится в имени приложения или наоборот
            if service_name_lower in app_name_lower or app_name_lower in service_name_lower:
                ratio += 0.2

            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = app

        if best_match:
            logger.debug(f"Найдено соответствие по имени (сходство {best_ratio:.2f}): "
                        f"{instance.instance_id} ({instance.service_name}) -> "
                        f"{best_match.instance_name} (ID={best_match.id})")
            return best_match.id

        logger.debug(f"Не найдено соответствие для {instance.instance_id} по серверу и имени")
        return None

    @staticmethod
    def set_manual_mapping(instance_id: int, application_id: Optional[int], mapped_by: str = None, notes: str = None) -> bool:
        """
        Установить ручной маппинг между Eureka экземпляром и AC приложением.

        Args:
            instance_id: ID Eureka экземпляра
            application_id: ID AC приложения (None для отвязки)
            mapped_by: Кто установил маппинг
            notes: Заметки о маппинге

        Returns:
            success: Успешность операции
        """
        try:
            instance = EurekaInstance.query.get(instance_id)
            if not instance:
                logger.error(f"Eureka экземпляр с ID={instance_id} не найден")
                return False

            # Если указан application_id, проверяем существование приложения
            if application_id:
                application = Application.query.get(application_id)
                if not application:
                    logger.error(f"Приложение с ID={application_id} не найдено")
                    return False

            # Сохраняем маппинг в унифицированную таблицу
            mapping_service = get_mapping_service()
            if application_id:
                mapping_service.map_eureka_instance(
                    eureka_instance_id=instance_id,
                    application_id=application_id,
                    is_manual=True,
                    mapped_by=mapped_by,
                    notes=notes
                )
            else:
                # Деактивируем маппинги для этого экземпляра
                mapping_service.unmap_entity(
                    MappingType.EUREKA_INSTANCE.value,
                    instance_id,
                    unmapped_by=mapped_by,
                    reason=notes or "Manual unmapping"
                )

            db.session.commit()

            if application_id:
                logger.info(f"Установлен ручной маппинг: Eureka экземпляр ID={instance_id} -> Приложение ID={application_id}")
            else:
                logger.info(f"Удален маппинг для Eureka экземпляра ID={instance_id}")

            return True

        except Exception as e:
            logger.error(f"Ошибка установки ручного маппинга: {str(e)}")
            db.session.rollback()
            return False

    @staticmethod
    def clear_manual_mapping(instance_id: int) -> bool:
        """
        Очистить ручной маппинг и запустить автоматический маппинг.

        Args:
            instance_id: ID Eureka экземпляра

        Returns:
            success: Успешность операции
        """
        try:
            instance = EurekaInstance.query.get(instance_id)
            if not instance:
                logger.error(f"Eureka экземпляр с ID={instance_id} не найден")
                return False

            # Очищаем маппинг
            instance.application_id = None
            instance.is_manual_mapping = False
            instance.mapped_by = None
            instance.mapped_at = None
            instance.mapping_notes = None

            db.session.commit()

            # Запускаем автоматический маппинг для этого экземпляра
            app_id = EurekaMapper.map_by_eureka_url(instance)
            if not app_id:
                app_id = EurekaMapper.map_by_server_and_name(instance)

            if app_id:
                instance.map_to_application(app_id, is_manual=False)
                db.session.commit()
                logger.info(f"Ручной маппинг очищен и установлен автоматический маппинг для экземпляра ID={instance_id}")
            else:
                logger.info(f"Ручной маппинг очищен для экземпляра ID={instance_id}, автоматический маппинг не найден")

            return True

        except Exception as e:
            logger.error(f"Ошибка очистки ручного маппинга: {str(e)}")
            db.session.rollback()
            return False

    @staticmethod
    def get_unmapped_instances() -> List[EurekaInstance]:
        """
        Получить список всех несвязанных Eureka экземпляров.

        Returns:
            Список несвязанных экземпляров
        """
        from app.models.application_mapping import ApplicationMapping, MappingType

        # Получаем ID экземпляров с активными маппингами
        mapped_instance_ids = db.session.query(ApplicationMapping.entity_id).filter(
            ApplicationMapping.entity_type == MappingType.EUREKA_INSTANCE.value,
            ApplicationMapping.is_active == True
        ).subquery()

        return EurekaInstance.query.filter(
            ~EurekaInstance.id.in_(mapped_instance_ids),
            EurekaInstance.removed_at.is_(None)
        ).all()

    @staticmethod
    def get_mapping_statistics() -> dict:
        """
        Получить статистику маппинга.

        Returns:
            Словарь со статистикой
        """
        from app.models.application_mapping import ApplicationMapping, MappingType

        total_instances = EurekaInstance.query.filter(
            EurekaInstance.removed_at.is_(None)
        ).count()

        # Статистика из унифицированной таблицы маппингов
        mapped_instances = ApplicationMapping.query.filter(
            ApplicationMapping.entity_type == MappingType.EUREKA_INSTANCE.value,
            ApplicationMapping.is_active == True
        ).count()

        manual_mappings = ApplicationMapping.query.filter(
            ApplicationMapping.entity_type == MappingType.EUREKA_INSTANCE.value,
            ApplicationMapping.is_active == True,
            ApplicationMapping.is_manual == True
        ).count()

        automatic_mappings = ApplicationMapping.query.filter(
            ApplicationMapping.entity_type == MappingType.EUREKA_INSTANCE.value,
            ApplicationMapping.is_active == True,
            ApplicationMapping.is_manual == False
        ).count()

        unmapped_instances = total_instances - mapped_instances

        return {
            'total_instances': total_instances,
            'mapped_instances': mapped_instances,
            'unmapped_instances': unmapped_instances,
            'manual_mappings': manual_mappings,
            'automatic_mappings': automatic_mappings,
            'mapping_percentage': round((mapped_instances / total_instances * 100) if total_instances > 0 else 0, 2)
        }

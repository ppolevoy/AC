# app/services/application_group_service.py
# РЕФАКТОРИНГ - обновлено для новой структуры БД

import re
import logging
from typing import Tuple, Optional, List, Dict, Any
from app import db
from app.models.application_catalog import ApplicationCatalog
from app.models.application_group import ApplicationGroup
from app.models.application_instance import ApplicationInstance

logger = logging.getLogger(__name__)

class ApplicationGroupService:
    """Сервис для работы с группами приложений и каталогом"""

    @staticmethod
    def parse_application_name(name: str) -> Tuple[Optional[str], int]:
        """
        Парсинг имени приложения для определения базового имени и номера экземпляра.

        Логика:
        - Ищем последний '_' за которым идут только цифры
        - Если найдено - это номер экземпляра, всё до него - базовое имя
        - Если нет - всё имя является базовым именем, номер экземпляра = 0

        Примеры:
        - best-app_1 -> (best-app, 1)
        - new-app_5 -> (new-app, 5)
        - standalone-app -> (standalone-app, 0)
        - my-app_test -> (my-app_test, 0)
        - service_prod_2 -> (service_prod, 2)

        Args:
            name: Имя приложения

        Returns:
            tuple: (базовое_имя, номер_экземпляра)
        """
        if not name:
            return None, 0

        # Паттерн: последний _ за которым только цифры до конца строки
        pattern = r'^(.+?)_(\d+)$'
        match = re.match(pattern, name)

        if match:
            base_name = match.group(1)
            instance_number = int(match.group(2))
            return base_name, instance_number
        else:
            return name, 0

    @staticmethod
    def get_or_create_catalog(base_name: str, app_type: str) -> ApplicationCatalog:
        """
        Получить существующую или создать новую запись в каталоге.

        Args:
            base_name: Базовое имя приложения (best-app, new-app)
            app_type: Тип приложения (docker, eureka, site, service)

        Returns:
            ApplicationCatalog: Объект каталога
        """
        if not base_name:
            raise ValueError("Базовое имя не может быть пустым")

        catalog = ApplicationCatalog.query.filter_by(name=base_name).first()

        if not catalog:
            logger.info(f"Создание новой записи в каталоге: {base_name} ({app_type})")
            catalog = ApplicationCatalog(
                name=base_name,
                app_type=app_type
            )
            db.session.add(catalog)
            db.session.flush()  # Получаем ID без полного коммита

        return catalog

    @staticmethod
    def get_or_create_group(group_name: str, catalog: Optional[ApplicationCatalog] = None) -> ApplicationGroup:
        """
        Получить существующую или создать новую группу.

        Args:
            group_name: Имя группы
            catalog: Объект каталога для связи (опционально)

        Returns:
            ApplicationGroup: Объект группы
        """
        if not group_name:
            raise ValueError("Имя группы не может быть пустым")

        group = ApplicationGroup.query.filter_by(name=group_name).first()

        if not group:
            logger.info(f"Создание новой группы приложения: {group_name}")
            group = ApplicationGroup(
                name=group_name,
                catalog_id=catalog.id if catalog else None
            )
            db.session.add(group)
            db.session.flush()  # Получаем ID без полного коммита
        elif catalog and not group.catalog_id:
            # Если группа существует, но не связана с каталогом - связываем
            group.catalog_id = catalog.id
            db.session.add(group)
            db.session.flush()

        return group

    @staticmethod
    def resolve_application_group(instance: ApplicationInstance) -> ApplicationInstance:
        """
        Определить группу и каталог для экземпляра приложения.

        Новая логика:
        1. Парсим имя экземпляра для получения базового имени и номера
        2. Находим/создаем запись в каталоге (ApplicationCatalog)
        3. Находим/создаем группу (ApplicationGroup)
        4. Связываем экземпляр с каталогом и группой

        Args:
            instance: Объект экземпляра приложения

        Returns:
            ApplicationInstance: Обновленный экземпляр
        """
        if not instance:
            logger.error("Попытка определить группу для None экземпляра")
            return None

        # Если уже определено, не проверяем повторно
        if instance.catalog_id and instance.group_id:
            logger.debug(f"Группа и каталог для экземпляра {instance.instance_name} уже определены")
            return instance

        # Парсим имя экземпляра
        base_name, instance_number = ApplicationGroupService.parse_application_name(instance.instance_name)

        if not base_name:
            logger.warning(f"Не удалось определить базовое имя для экземпляра {instance.instance_name}")
            return instance

        try:
            # Получаем или создаем запись в каталоге
            catalog = ApplicationGroupService.get_or_create_catalog(base_name, instance.app_type)

            # Связываем экземпляр с каталогом
            instance.catalog_id = catalog.id
            instance.instance_number = instance_number

            # Получаем или создаем группу
            group_name = f"Группа {base_name}"
            group = ApplicationGroupService.get_or_create_group(group_name, catalog)

            # Связываем экземпляр с группой
            instance.group_id = group.id

            db.session.add(instance)
            db.session.flush()

            logger.info(f"Экземпляр {instance.instance_name} связан с каталогом '{base_name}' и группой '{group_name}'")

            return instance

        except Exception as e:
            logger.error(f"Ошибка при определении группы для экземпляра {instance.instance_name}: {str(e)}")
            return instance

    @staticmethod
    def get_group_instances(group_name: str, server_id: Optional[int] = None) -> List[ApplicationInstance]:
        """
        Получить все экземпляры группы.

        Args:
            group_name: Имя группы
            server_id: ID сервера для фильтрации (опционально)

        Returns:
            list: Список экземпляров
        """
        query = db.session.query(ApplicationInstance).join(
            ApplicationGroup
        ).filter(
            ApplicationGroup.name == group_name
        )

        if server_id:
            query = query.filter(ApplicationInstance.server_id == server_id)

        return query.order_by(ApplicationInstance.instance_number).all()

    @staticmethod
    def get_catalog_instances(catalog_name: str) -> List[ApplicationInstance]:
        """
        Получить все экземпляры приложения из каталога.

        Args:
            catalog_name: Базовое имя приложения из каталога

        Returns:
            list: Список экземпляров
        """
        return db.session.query(ApplicationInstance).join(
            ApplicationCatalog
        ).filter(
            ApplicationCatalog.name == catalog_name
        ).order_by(
            ApplicationInstance.server_id,
            ApplicationInstance.instance_number
        ).all()

    @staticmethod
    def get_all_groups_summary() -> List[Dict[str, Any]]:
        """
        Получить сводную информацию по всем группам.

        Returns:
            list: Список словарей с информацией о группах
        """
        groups = ApplicationGroup.query.all()
        result = []

        for group in groups:
            # Получаем экземпляры группы
            instances = group.instances.all()

            # Собираем информацию о серверах
            servers_info = {}
            custom_count = 0

            for instance in instances:
                # Считаем кастомные настройки
                if instance.has_custom_settings():
                    custom_count += 1

                # Группируем по серверам
                if instance.server:
                    server_name = instance.server.name
                    if server_name not in servers_info:
                        servers_info[server_name] = []
                    servers_info[server_name].append(instance.instance_number)

            # Сортируем номера экземпляров на каждом сервере
            for server_name in servers_info:
                servers_info[server_name].sort()

            result.append({
                'group_id': group.id,
                'group_name': group.name,
                'description': group.description,
                'catalog_id': group.catalog_id,
                'catalog_name': group.catalog.name if group.catalog else None,
                'total_instances': len(instances),
                'custom_settings_count': custom_count,
                'servers': servers_info,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'update_playbook_path': group.update_playbook_path,
                'batch_grouping_strategy': group.batch_grouping_strategy,
                'artifacts_configured': bool(group.artifact_list_url or group.artifact_extension),
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None
            })

        # Сортируем по имени группы
        result.sort(key=lambda x: x['group_name'])

        return result

    @staticmethod
    def get_all_catalog_summary() -> List[Dict[str, Any]]:
        """
        Получить сводную информацию по всем записям каталога.

        Returns:
            list: Список словарей с информацией о приложениях в каталоге
        """
        catalogs = ApplicationCatalog.query.all()
        result = []

        for catalog in catalogs:
            instances = catalog.instances.all()
            groups = catalog.groups.all()

            result.append({
                'catalog_id': catalog.id,
                'name': catalog.name,
                'app_type': catalog.app_type,
                'description': catalog.description,
                'total_instances': len(instances),
                'total_groups': len(groups),
                'default_playbook_path': catalog.default_playbook_path,
                'default_artifact_url': catalog.default_artifact_url,
                'default_artifact_extension': catalog.default_artifact_extension,
                'created_at': catalog.created_at.isoformat() if catalog.created_at else None,
                'updated_at': catalog.updated_at.isoformat() if catalog.updated_at else None
            })

        # Сортируем по имени
        result.sort(key=lambda x: x['name'])

        return result

    @staticmethod
    def find_instances_with_custom_artifacts() -> List[ApplicationInstance]:
        """
        Найти все экземпляры с кастомными настройками артефактов.

        Returns:
            list: Список экземпляров с кастомными настройками
        """
        return ApplicationInstance.query.filter(
            db.or_(
                ApplicationInstance.custom_artifact_url.isnot(None),
                ApplicationInstance.custom_artifact_extension.isnot(None)
            )
        ).all()

    @staticmethod
    def find_instances_with_custom_playbook() -> List[ApplicationInstance]:
        """
        Найти все экземпляры с кастомным playbook.

        Returns:
            list: Список экземпляров с кастомным playbook
        """
        return ApplicationInstance.query.filter(
            ApplicationInstance.custom_playbook_path.isnot(None)
        ).all()

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Получить общую статистику по каталогу, группам и экземплярам.

        Returns:
            dict: Статистика
        """
        total_catalog = ApplicationCatalog.query.count()
        total_groups = ApplicationGroup.query.count()
        total_instances = ApplicationInstance.query.count()

        # Группы с настроенными артефактами
        configured_groups = ApplicationGroup.query.filter(
            db.or_(
                ApplicationGroup.artifact_list_url.isnot(None),
                ApplicationGroup.artifact_extension.isnot(None)
            )
        ).count()

        # Каталог с настроенными артефактами
        configured_catalog = ApplicationCatalog.query.filter(
            db.or_(
                ApplicationCatalog.default_artifact_url.isnot(None),
                ApplicationCatalog.default_artifact_extension.isnot(None)
            )
        ).count()

        # Экземпляры с кастомными настройками
        custom_artifacts = ApplicationInstance.query.filter(
            db.or_(
                ApplicationInstance.custom_artifact_url.isnot(None),
                ApplicationInstance.custom_artifact_extension.isnot(None)
            )
        ).count()

        custom_playbook = ApplicationInstance.query.filter(
            ApplicationInstance.custom_playbook_path.isnot(None)
        ).count()

        # Экземпляры со связями
        linked_to_catalog = ApplicationInstance.query.filter(
            ApplicationInstance.catalog_id.isnot(None)
        ).count()

        linked_to_group = ApplicationInstance.query.filter(
            ApplicationInstance.group_id.isnot(None)
        ).count()

        return {
            'total_catalog': total_catalog,
            'total_groups': total_groups,
            'total_instances': total_instances,
            'configured_catalog': configured_catalog,
            'configured_groups': configured_groups,
            'custom_artifacts_count': custom_artifacts,
            'custom_playbook_count': custom_playbook,
            'linked_to_catalog': linked_to_catalog,
            'linked_to_group': linked_to_group,
            'unlinked_catalog': total_instances - linked_to_catalog,
            'unlinked_group': total_instances - linked_to_group,
            'coverage': {
                'catalog_with_defaults': f"{(configured_catalog / total_catalog * 100) if total_catalog > 0 else 0:.1f}%",
                'groups_with_artifacts': f"{(configured_groups / total_groups * 100) if total_groups > 0 else 0:.1f}%",
                'instances_with_custom': f"{(custom_artifacts / total_instances * 100) if total_instances > 0 else 0:.1f}%",
                'instances_linked': f"{(linked_to_catalog / total_instances * 100) if total_instances > 0 else 0:.1f}%"
            }
        }

    @staticmethod
    def fix_all_applications() -> Dict[str, int]:
        """
        Исправить все существующие экземпляры без установленных catalog_id/group_id.
        Используется для миграции данных.

        Returns:
            dict: Статистика обработки
        """
        stats = {
            'processed': 0,
            'fixed': 0,
            'errors': 0
        }

        try:
            # Находим все экземпляры без catalog_id или group_id
            instances = ApplicationInstance.query.filter(
                db.or_(
                    ApplicationInstance.catalog_id.is_(None),
                    ApplicationInstance.group_id.is_(None)
                )
            ).all()

            logger.info(f"Найдено {len(instances)} экземпляров для обработки")

            for instance in instances:
                stats['processed'] += 1
                try:
                    updated_instance = ApplicationGroupService.resolve_application_group(instance)
                    if updated_instance and updated_instance.catalog_id and updated_instance.group_id:
                        stats['fixed'] += 1
                        logger.info(f"Исправлен экземпляр {instance.instance_name}")
                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"Ошибка при обработке экземпляра {instance.instance_name}: {str(e)}")

            # Коммитим все изменения
            db.session.commit()

            logger.info(f"Обработка завершена. Обработано: {stats['processed']}, "
                       f"Исправлено: {stats['fixed']}, Ошибок: {stats['errors']}")

            return stats

        except Exception as e:
            db.session.rollback()
            logger.error(f"Критическая ошибка при исправлении экземпляров: {str(e)}")
            raise

import re
import logging
from typing import Tuple, Optional, List, Dict, Any
from app import db
from app.models.application_group import ApplicationGroup, ApplicationInstance
from app.models.application import Application

logger = logging.getLogger(__name__)

class ApplicationGroupService:
    """Сервис для работы с группами приложений"""
    
    @staticmethod
    def parse_application_name(name: str) -> Tuple[Optional[str], int]:
        """
        Парсинг имени приложения для определения группы и номера экземпляра.
        
        Логика:
        - Ищем последний '_' за которым идут только цифры
        - Если найдено - это номер экземпляра, всё до него - имя группы
        - Если нет - всё имя является именем группы, номер экземпляра = 0
        
        Примеры:
        - jurws_1 -> (jurws, 1)
        - business_5 -> (business, 5)
        - salary-api -> (salary-api, 0)
        - my-app_test -> (my-app_test, 0)
        - service_prod_2 -> (service_prod, 2)
        
        Args:
            name: Имя приложения
            
        Returns:
            tuple: (имя_группы, номер_экземпляра)
        """
        if not name:
            return None, 0
        
        # Паттерн: последний _ за которым только цифры до конца строки
        pattern = r'^(.+?)_(\d+)$'
        match = re.match(pattern, name)
        
        if match:
            group_name = match.group(1)
            instance_number = int(match.group(2))
            return group_name, instance_number
        else:
            return name, 0
    
    @staticmethod
    def get_or_create_group(group_name: str) -> ApplicationGroup:
        """
        Получить существующую или создать новую группу.
        
        Args:
            group_name: Имя группы
            
        Returns:
            ApplicationGroup: Объект группы
        """
        if not group_name:
            raise ValueError("Имя группы не может быть пустым")
        
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            logger.info(f"Создание новой группы приложения: {group_name}")
            group = ApplicationGroup(name=group_name)
            db.session.add(group)
            db.session.flush()  # Получаем ID без полного коммита
        
        return group
    
    @staticmethod
    def resolve_application_group(application: Application) -> Optional[ApplicationInstance]:
        """
        Определить группу для приложения и создать/обновить экземпляр.
        
        Args:
            application: Объект приложения
            
        Returns:
            ApplicationInstance: Созданный или обновленный экземпляр
        """
        if not application:
            logger.error("Попытка определить группу для None приложения")
            return None
        
        # Проверяем, есть ли уже экземпляр
        if hasattr(application, 'instance') and application.instance:
            if application.instance.group_resolved:
                logger.debug(f"Группа для приложения {application.name} уже определена")
                return application.instance
        
        # Парсим имя приложения
        group_name, instance_number = ApplicationGroupService.parse_application_name(application.name)
        
        if not group_name:
            logger.warning(f"Не удалось определить группу для приложения {application.name}")
            return None
        
        try:
            # Получаем или создаем группу
            group = ApplicationGroupService.get_or_create_group(group_name)
            
            # Проверяем существующий экземпляр
            instance = getattr(application, 'instance', None)
            
            if not instance:
                # Создаем новый экземпляр
                logger.info(f"Создание экземпляра для {application.name}: группа={group_name}, номер={instance_number}")
                instance = ApplicationInstance(
                    original_name=application.name,
                    instance_number=instance_number,
                    group_id=group.id,
                    application_id=application.id,
                    group_resolved=True
                )
                db.session.add(instance)
            else:
                # Обновляем существующий экземпляр
                logger.info(f"Обновление экземпляра для {application.name}: группа={group_name}, номер={instance_number}")
                instance.group_id = group.id
                instance.instance_number = instance_number
                instance.original_name = application.name
                instance.group_resolved = True
                db.session.add(instance)
            
            db.session.flush()
            return instance
            
        except Exception as e:
            logger.error(f"Ошибка при определении группы для приложения {application.name}: {str(e)}")
            return None
    
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
            query = query.join(Application).filter(Application.server_id == server_id)
        
        return query.order_by(ApplicationInstance.instance_number).all()
    
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
                if instance.application and instance.application.server:
                    server_name = instance.application.server.name
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
                'total_instances': len(instances),
                'custom_settings_count': custom_count,
                'servers': servers_info,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'update_playbook_path': group.update_playbook_path,
                'artifacts_configured': bool(group.artifact_list_url or group.artifact_extension),
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None
            })
        
        # Сортируем по имени группы
        result.sort(key=lambda x: x['group_name'])
        
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
                ApplicationInstance.custom_artifact_list_url.isnot(None),
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
        Получить общую статистику по группам и экземплярам.
        
        Returns:
            dict: Статистика
        """
        total_groups = ApplicationGroup.query.count()
        total_instances = ApplicationInstance.query.count()
        
        # Группы с настроенными артефактами
        configured_groups = ApplicationGroup.query.filter(
            db.or_(
                ApplicationGroup.artifact_list_url.isnot(None),
                ApplicationGroup.artifact_extension.isnot(None)
            )
        ).count()
        
        # Экземпляры с кастомными настройками
        custom_artifacts = ApplicationInstance.query.filter(
            db.or_(
                ApplicationInstance.custom_artifact_list_url.isnot(None),
                ApplicationInstance.custom_artifact_extension.isnot(None)
            )
        ).count()
        
        custom_playbook = ApplicationInstance.query.filter(
            ApplicationInstance.custom_playbook_path.isnot(None)
        ).count()
        
        # Экземпляры с разрешенными группами
        resolved_instances = ApplicationInstance.query.filter_by(group_resolved=True).count()
        
        return {
            'total_groups': total_groups,
            'total_instances': total_instances,
            'configured_groups': configured_groups,
            'custom_artifacts_count': custom_artifacts,
            'custom_playbook_count': custom_playbook,
            'resolved_instances': resolved_instances,
            'unresolved_instances': total_instances - resolved_instances,
            'configuration_coverage': {
                'groups_with_artifacts': f"{(configured_groups / total_groups * 100) if total_groups > 0 else 0:.1f}%",
                'instances_with_custom': f"{(custom_artifacts / total_instances * 100) if total_instances > 0 else 0:.1f}%"
            }
        }
from app import db
from app.models.application import Application
from app.models.application_group import ApplicationGroup, ApplicationInstance
from app.models.tags import Tag
from app.models.tag_mixins import ApplicationInstanceTagMixin, ApplicationGroupTagMixin
import logging
import re

logger = logging.getLogger(__name__)


class AutoTaggingService:
    """Сервис для автоматического присвоения тегов приложениям и группам"""
    
    # Правила для определения окружения по имени
    ENVIRONMENT_PATTERNS = {
        'production': [r'.*prod.*', r'.*production.*', r'.*prd.*']
    }
    
    # Правила для определения приоритета
    PRIORITY_KEYWORDS = {
        'critical': ['payment', 'auth', 'mdse', 'db', 'core'],

    }
    
    @classmethod
    def apply_tags_from_agent_data(cls, application, agent_data):
        """
        Применить теги к приложению на основе данных от агента
        
        Args:
            application: Объект Application
            agent_data: Словарь с данными от агента
            
        Returns:
            list: Список добавленных тегов
        """
        if not application or not application.instance:
            logger.warning(f"Приложение {application.name if application else 'Unknown'} не имеет экземпляра")
            return []
        
        added_tags = []
        instance = application.instance
        
        # Добавляем методы тегов к экземпляру
        cls._add_tag_methods_to_instance(instance)
        
        try:
            # 1. Тег на основе типа приложения
            if application.app_type:
                tag_name = cls._get_service_type_tag(application.app_type)
                if tag_name and not instance.has_tag(tag_name):
                    if instance.add_tag(tag_name, assigned_by='auto_agent'):
                        added_tags.append(tag_name)
                        logger.info(f"Добавлен тег '{tag_name}' для {application.name} (тип: {application.app_type})")
            
            # 2. Тег на основе статуса
            if application.status:
                status_tag = cls._get_status_tag(application.status, agent_data)
                if status_tag and not instance.has_tag(status_tag):
                    if instance.add_tag(status_tag, assigned_by='auto_agent'):
                        added_tags.append(status_tag)
                        logger.info(f"Добавлен тег '{status_tag}' для {application.name} (статус: {application.status})")
            
            # 3. Тег окружения на основе имени
            env_tag = cls._detect_environment(application.name)
            if env_tag and not instance.has_tag(env_tag):
                if instance.add_tag(env_tag, assigned_by='auto_agent'):
                    added_tags.append(env_tag)
                    logger.info(f"Добавлен тег окружения '{env_tag}' для {application.name}")
            
            # 4. Тег приоритета на основе имени
            priority_tag = cls._detect_priority(application.name)
            if priority_tag and not instance.has_tag(priority_tag):
                if instance.add_tag(priority_tag, assigned_by='auto_agent'):
                    added_tags.append(priority_tag)
                    logger.info(f"Добавлен тег приоритета '{priority_tag}' для {application.name}")
            
            if application.version:
                version_tag = cls._get_version_tag(application.version)
                if version_tag and not instance.has_tag(version_tag):
                    if instance.add_tag(version_tag, assigned_by='auto_agent'):
                        added_tags.append(version_tag)
                        logger.info(f"Добавлен тег версии '{version_tag}' для {application.name}")
            
            # 6. Специальные теги на основе дополнительных данных
            special_tags = cls._get_special_tags(application, agent_data)
            for tag_name in special_tags:
                if not instance.has_tag(tag_name):
                    if instance.add_tag(tag_name, assigned_by='auto_agent'):
                        added_tags.append(tag_name)
                        logger.info(f"Добавлен специальный тег '{tag_name}' для {application.name}")
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при добавлении тегов для {application.name}: {e}")
        
        return added_tags
    
    @classmethod
    def apply_group_tags(cls, group):
        """
        Применить теги к группе на основе её характеристик
        
        Args:
            group: Объект ApplicationGroup
            
        Returns:
            list: Список добавленных тегов
        """
        if not group:
            return []
        
        added_tags = []
        
        # Добавляем методы тегов к группе
        cls._add_tag_methods_to_group(group)
        
        try:
            # 1. Определяем окружение группы
            env_tag = cls._detect_environment(group.name)
            if env_tag and not any(tag.name == env_tag for tag, _ in group.get_tags()):
                if group.add_tag(env_tag, inheritable=True, assigned_by='auto_group'):
                    added_tags.append(env_tag)
                    logger.info(f"Добавлен наследуемый тег '{env_tag}' для группы {group.name}")
            
            # 2. Определяем приоритет группы
            priority_tag = cls._detect_priority(group.name)
            if priority_tag and not any(tag.name == priority_tag for tag, _ in group.get_tags()):
                if group.add_tag(priority_tag, inheritable=True, assigned_by='auto_group'):
                    added_tags.append(priority_tag)
                    logger.info(f"Добавлен наследуемый тег приоритета '{priority_tag}' для группы {group.name}")
            
            # 3. Анализируем экземпляры группы для определения общих характеристик
            instances = group.instances.all()
            if instances:
                # Если все экземпляры имеют одинаковый тип
                app_types = set()
                for instance in instances:
                    if instance.application and instance.application.app_type:
                        app_types.add(instance.application.app_type)
                
                if len(app_types) == 1:
                    app_type = app_types.pop()
                    type_tag = cls._get_service_type_tag(app_type)
                    if type_tag and not any(tag.name == type_tag for tag, _ in group.get_tags()):
                        if group.add_tag(type_tag, inheritable=True, assigned_by='auto_group'):
                            added_tags.append(type_tag)
                            logger.info(f"Добавлен наследуемый тег типа '{type_tag}' для группы {group.name}")
            
            # 4. Синхронизируем теги с экземплярами
            if added_tags:
                updated_count = group.sync_tags_to_instances()
                logger.info(f"Синхронизировано {updated_count} экземпляров группы {group.name}")
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при добавлении тегов для группы {group.name}: {e}")
        
        return added_tags
    
    @classmethod
    def _detect_environment(cls, name):
        """Определить окружение по имени"""
        name_lower = name.lower()
        
        for env, patterns in cls.ENVIRONMENT_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, name_lower):
                    return env
        
        return None
    
    @classmethod
    def _detect_priority(cls, name):
        """Определить приоритет по имени"""
        name_lower = name.lower()
        
        for priority, keywords in cls.PRIORITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return priority
        
        return None
    
    @classmethod
    def _get_service_type_tag(cls, app_type):
        """Получить тег для типа сервиса"""
        type_mapping = {
            'docker': 'docker',
            'eureka': 'eureka',
            'service': 'system-service',
            'site-app': 'site-app'
        }
        return type_mapping.get(app_type.lower())
    
    @classmethod
    def _get_status_tag(cls, status, agent_data=None):
        """Получить тег на основе статуса"""
        if status == 'offline':
            return 'needs-attention'
        elif status == 'maintenance':
            return 'maintenance'
        
        # Проверяем дополнительные данные от агента
        if agent_data:
            # Например, если есть информация о планируемом выводе из эксплуатации
            if agent_data.get('deprecated'):
                return 'deprecated'
            if agent_data.get('legacy'):
                return 'legacy'
        
        return None
    
    @classmethod
    def _get_version_tag(cls, version):
        """Получить тег на основе версии"""
        if not version:
            return None
        
        # SNAPSHOT версии могут быть помечены как development
        if 'SNAPSHOT' in version.upper():
            return 'development'
        
        # RC версии могут быть помечены как staging
        if 'RC' in version.upper() or 'RELEASE-CANDIDATE' in version.upper():
            return 'staging'
        
        return None
    
    @classmethod
    def _get_special_tags(cls, application, agent_data):
        """Получить специальные теги на основе дополнительных данных"""
        special_tags = []
        
        # Проверяем наличие специальных полей в данных от агента
        if agent_data:
            # Если есть информация о критичности
            if agent_data.get('is_critical'):
                special_tags.append('critical')
                       
            # Если есть информация о репликации
            if agent_data.get('replicas'):
                replicas = agent_data['replicas']
                if replicas > 3:
                    special_tags.append('high-availability')
                elif replicas == 1:
                    special_tags.append('single-instance')
        
        # Проверяем порты для определения типа сервиса
        if application.port:
            if application.port == 5432:
                special_tags.append('database')
            elif application.port in [5672, 9092]:
                special_tags.append('message-queue')
        
        return special_tags
    
    @classmethod
    def _add_tag_methods_to_instance(cls, instance):
        """Добавить методы тегов к экземпляру"""
        if not hasattr(instance.__class__, 'add_tag'):
            for method_name in dir(ApplicationInstanceTagMixin):
                if not method_name.startswith('_'):
                    method = getattr(ApplicationInstanceTagMixin, method_name)
                    setattr(instance.__class__, method_name, method)
    
    @classmethod
    def _add_tag_methods_to_group(cls, group):
        """Добавить методы тегов к группе"""
        if not hasattr(group.__class__, 'add_tag'):
            for method_name in dir(ApplicationGroupTagMixin):
                if not method_name.startswith('_'):
                    method = getattr(ApplicationGroupTagMixin, method_name)
                    setattr(group.__class__, method_name, method)
    
    @classmethod
    def cleanup_conflicting_tags(cls, application):
        """
        Удалить конфликтующие теги (например, нельзя быть одновременно production и development)
        
        Args:
            application: Объект Application
        """
        if not application or not application.instance:
            return
        
        instance = application.instance
        cls._add_tag_methods_to_instance(instance)
        
        # Определяем группы взаимоисключающих тегов
        exclusive_groups = [
            ['production', 'staging', 'development', 'testing'],  # Окружения
            ['critical', 'high-priority', 'medium-priority', 'low-priority'],  # Приоритеты
        ]
        
        current_tags = instance.get_own_tags()
        current_tag_names = {tag.name for tag in current_tags}
        
        for exclusive_group in exclusive_groups:
            # Находим теги из этой группы
            group_tags = current_tag_names.intersection(exclusive_group)
            
            # Если больше одного тега из группы, оставляем только последний добавленный
            if len(group_tags) > 1:
                # Сортируем по времени добавления и удаляем все кроме последнего
                tags_to_remove = sorted(
                    [tag for tag in current_tags if tag.name in group_tags],
                    key=lambda t: getattr(t, 'assigned_at', None) or t.created_at
                )[:-1]
                
                for tag in tags_to_remove:
                    instance.remove_tag(tag.name)
                    logger.info(f"Удален конфликтующий тег '{tag.name}' у {application.name}")
        
        db.session.commit()
    
    @classmethod
    def auto_tag_all_applications(cls):
        """
        Применить автоматические теги ко всем приложениям
        
        Returns:
            dict: Статистика применения тегов
        """
        stats = {
            'total_applications': 0,
            'tagged_applications': 0,
            'total_tags_added': 0,
            'errors': []
        }
        
        try:
            applications = Application.query.all()
            stats['total_applications'] = len(applications)
            
            for app in applications:
                try:
                    # Применяем теги на основе текущих данных
                    added_tags = cls.apply_tags_from_agent_data(app, {})
                    
                    if added_tags:
                        stats['tagged_applications'] += 1
                        stats['total_tags_added'] += len(added_tags)
                    
                    # Очищаем конфликтующие теги
                    cls.cleanup_conflicting_tags(app)
                    
                except Exception as e:
                    stats['errors'].append({
                        'app_id': app.id,
                        'app_name': app.name,
                        'error': str(e)
                    })
                    logger.error(f"Ошибка при автоматическом присвоении тегов для {app.name}: {e}")
            
            logger.info(f"Автоматическое присвоение тегов завершено: {stats}")
            
        except Exception as e:
            logger.error(f"Ошибка при автоматическом присвоении тегов: {e}")
            stats['errors'].append({'error': str(e)})
        
        return stats
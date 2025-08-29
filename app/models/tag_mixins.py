"""
Миксины для добавления функциональности тегов к моделям Application и ApplicationInstance
"""

from app import db
from app.models.tags import Tag, ApplicationInstanceTag, ApplicationGroupTag
import logging

logger = logging.getLogger(__name__)


class ApplicationInstanceTagMixin:
    """Миксин для ApplicationInstance с методами работы с тегами"""
    
    def add_tag(self, tag_name, assigned_by=None):
        """
        Добавить тег к экземпляру приложения
        
        Args:
            tag_name: Имя тега или объект Tag
            assigned_by: Кто назначил тег (для аудита)
            
        Returns:
            ApplicationInstanceTag или None при ошибке
        """
        try:
            # Получаем объект тега
            if isinstance(tag_name, str):
                tag = Tag.get_or_create(tag_name)
            elif isinstance(tag_name, Tag):
                tag = tag_name
            else:
                raise ValueError("tag_name must be string or Tag instance")
            
            # Проверяем, не существует ли уже такая связь
            existing = ApplicationInstanceTag.query.filter_by(
                instance_id=self.id,
                tag_id=tag.id
            ).first()
            
            if existing:
                logger.debug(f"Tag {tag.name} already assigned to instance {self.id}")
                return existing
            
            # Создаем связь
            association = ApplicationInstanceTag(
                instance_id=self.id,
                tag_id=tag.id,
                assigned_by=assigned_by
            )
            db.session.add(association)
            db.session.commit()
            
            logger.info(f"Added tag {tag.name} to instance {self.id}")
            return association
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding tag to instance: {e}")
            return None
    
    def remove_tag(self, tag_name):
        """
        Удалить тег у экземпляра
        
        Args:
            tag_name: Имя тега или объект Tag
            
        Returns:
            bool: True если успешно удален
        """
        try:
            # Получаем объект тега
            if isinstance(tag_name, str):
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    return False
            elif isinstance(tag_name, Tag):
                tag = tag_name
            else:
                return False
            
            # Удаляем связь
            association = ApplicationInstanceTag.query.filter_by(
                instance_id=self.id,
                tag_id=tag.id
            ).first()
            
            if association:
                db.session.delete(association)
                db.session.commit()
                logger.info(f"Removed tag {tag.name} from instance {self.id}")
                return True
            
            return False
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing tag from instance: {e}")
            return False
    
    def get_own_tags(self):
        """
        Получить собственные теги экземпляра (без унаследованных)
        
        Returns:
            list: Список объектов Tag
        """
        return [assoc.tag for assoc in self.tag_associations]
    
    def get_inherited_tags(self):
        """
        Получить теги, унаследованные от группы
        
        Returns:
            list: Список объектов Tag
        """
        if not self.group:
            return []
        
        inherited = []
        for group_tag_assoc in self.group.tag_associations:
            if group_tag_assoc.inheritable:
                inherited.append(group_tag_assoc.tag)
        
        return inherited
    
    def get_all_tags(self):
        """
        Получить все теги (собственные + унаследованные)
        
        Returns:
            list: Список уникальных объектов Tag
        """
        # Используем dict для дедупликации по id
        all_tags = {}
        
        # Добавляем собственные теги
        for tag in self.get_own_tags():
            all_tags[tag.id] = tag
        
        # Добавляем унаследованные теги
        for tag in self.get_inherited_tags():
            if tag.id not in all_tags:
                all_tags[tag.id] = tag
        
        return list(all_tags.values())
    
    def has_tag(self, tag_name):
        """
        Проверить наличие тега (включая унаследованные)
        
        Args:
            tag_name: Имя тега
            
        Returns:
            bool: True если тег есть
        """
        return any(tag.name == tag_name for tag in self.get_all_tags())
    
    def clear_tags(self):
        """Удалить все собственные теги экземпляра"""
        try:
            ApplicationInstanceTag.query.filter_by(instance_id=self.id).delete()
            db.session.commit()
            logger.info(f"Cleared all tags from instance {self.id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error clearing tags: {e}")
            return False
    
    def sync_tags(self, tag_names, assigned_by=None):
        """
        Синхронизировать теги - установить точно указанный набор
        
        Args:
            tag_names: Список имен тегов
            assigned_by: Кто назначил теги
            
        Returns:
            bool: True если успешно
        """
        try:
            # Очищаем текущие теги
            self.clear_tags()
            
            # Добавляем новые
            for tag_name in tag_names:
                self.add_tag(tag_name, assigned_by)
            
            return True
        except Exception as e:
            logger.error(f"Error syncing tags: {e}")
            return False


class ApplicationGroupTagMixin:
    """Миксин для ApplicationGroup с методами работы с тегами"""
    
    def add_tag(self, tag_name, inheritable=True, assigned_by=None):
        """
        Добавить тег к группе
        
        Args:
            tag_name: Имя тега или объект Tag
            inheritable: Наследуется ли тег экземплярами
            assigned_by: Кто назначил тег
            
        Returns:
            ApplicationGroupTag или None при ошибке
        """
        try:
            # Получаем объект тега
            if isinstance(tag_name, str):
                tag = Tag.get_or_create(tag_name)
            elif isinstance(tag_name, Tag):
                tag = tag_name
            else:
                raise ValueError("tag_name must be string or Tag instance")
            
            # Проверяем существующую связь
            existing = ApplicationGroupTag.query.filter_by(
                group_id=self.id,
                tag_id=tag.id
            ).first()
            
            if existing:
                # Обновляем флаг наследования если нужно
                if existing.inheritable != inheritable:
                    existing.inheritable = inheritable
                    db.session.commit()
                return existing
            
            # Создаем связь
            association = ApplicationGroupTag(
                group_id=self.id,
                tag_id=tag.id,
                inheritable=inheritable,
                assigned_by=assigned_by
            )
            db.session.add(association)
            db.session.commit()
            
            logger.info(f"Added tag {tag.name} to group {self.id} (inheritable={inheritable})")
            return association
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding tag to group: {e}")
            return None
    
    def remove_tag(self, tag_name):
        """
        Удалить тег у группы
        
        Args:
            tag_name: Имя тега или объект Tag
            
        Returns:
            bool: True если успешно удален
        """
        try:
            # Получаем объект тега
            if isinstance(tag_name, str):
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    return False
            elif isinstance(tag_name, Tag):
                tag = tag_name
            else:
                return False
            
            # Удаляем связь
            association = ApplicationGroupTag.query.filter_by(
                group_id=self.id,
                tag_id=tag.id
            ).first()
            
            if association:
                db.session.delete(association)
                db.session.commit()
                logger.info(f"Removed tag {tag.name} from group {self.id}")
                return True
            
            return False
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing tag from group: {e}")
            return False
    
    def get_tags(self):
        """
        Получить все теги группы
        
        Returns:
            list: Список кортежей (Tag, inheritable)
        """
        return [(assoc.tag, assoc.inheritable) for assoc in self.tag_associations]
    
    def get_inheritable_tags(self):
        """
        Получить только наследуемые теги
        
        Returns:
            list: Список объектов Tag
        """
        return [assoc.tag for assoc in self.tag_associations if assoc.inheritable]
    
    def sync_tags_to_instances(self):
        """
        Синхронизировать наследуемые теги группы со всеми экземплярами
        
        Returns:
            int: Количество обновленных экземпляров
        """
        try:
            inheritable_tags = self.get_inheritable_tags()
            updated_count = 0
            
            for instance in self.instances:
                # Получаем текущие собственные теги экземпляра
                own_tags = instance.get_own_tags()
                own_tag_names = {tag.name for tag in own_tags}
                
                # Добавляем наследуемые теги, которых нет среди собственных
                for tag in inheritable_tags:
                    if tag.name not in own_tag_names:
                        instance.add_tag(tag, assigned_by="group_sync")
                        updated_count += 1
            
            logger.info(f"Synced {len(inheritable_tags)} tags to {updated_count} instances in group {self.id}")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error syncing group tags to instances: {e}")
            return 0


class ApplicationTagProxyMixin:
    """Миксин для Application с прокси-методами к ApplicationInstance"""
    
    def _ensure_instance(self):
        """Убедиться что есть ApplicationInstance, создать если нужно"""
        if not hasattr(self, 'instance') or not self.instance:
            from app.services.application_group_service import ApplicationGroupService
            ApplicationGroupService.determine_group_for_application(self)
        return self.instance
    
    def add_tag(self, tag_name, assigned_by=None):
        """Прокси-метод: добавить тег"""
        instance = self._ensure_instance()
        if instance:
            return instance.add_tag(tag_name, assigned_by)
        return None
    
    def remove_tag(self, tag_name):
        """Прокси-метод: удалить тег"""
        instance = self._ensure_instance()
        if instance:
            return instance.remove_tag(tag_name)
        return False
    
    def get_tags(self):
        """Прокси-метод: получить все теги (собственные + унаследованные)"""
        instance = self._ensure_instance()
        if instance:
            return instance.get_all_tags()
        return []
    
    def get_own_tags(self):
        """Прокси-метод: получить только собственные теги"""
        instance = self._ensure_instance()
        if instance:
            return instance.get_own_tags()
        return []
    
    def get_inherited_tags(self):
        """Прокси-метод: получить унаследованные теги"""
        instance = self._ensure_instance()
        if instance:
            return instance.get_inherited_tags()
        return []
    
    def has_tag(self, tag_name):
        """Прокси-метод: проверить наличие тега"""
        instance = self._ensure_instance()
        if instance:
            return instance.has_tag(tag_name)
        return False
    
    def clear_tags(self):
        """Прокси-метод: очистить все теги"""
        instance = self._ensure_instance()
        if instance:
            return instance.clear_tags()
        return False
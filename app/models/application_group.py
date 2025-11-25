# app/models/application_group.py
# РЕФАКТОРИНГ - добавлена связь со справочником приложений

from app import db
from datetime import datetime
from sqlalchemy import event

# Стратегии группировки для batch операций
BATCH_GROUPING_STRATEGIES = {
    'by_group': 'Группировать по (server, playbook, group_id) - разные группы в разных задачах',
    'by_server': 'Группировать по (server, playbook) - игнорировать group_id',
    'by_instance_name': 'Группировать по (server, playbook, original_name) - по имени экземпляра',
    'no_grouping': 'Не группировать - каждый экземпляр в отдельной задаче'
}

class ApplicationGroup(db.Model):
    """Группа приложений с настройками артефактов"""
    __tablename__ = 'application_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    # Связь со справочником приложений
    catalog_id = db.Column(db.Integer, db.ForeignKey('application_catalog.id', ondelete='SET NULL'), nullable=True)

    artifact_list_url = db.Column(db.String(512), nullable=True)
    artifact_extension = db.Column(db.String(32), nullable=True)
    update_playbook_path = db.Column(db.String(256), nullable=True)
    batch_grouping_strategy = db.Column(db.String(32), default='by_group', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Кэш тегов для быстрой фильтрации
    tags_cache = db.Column(db.String(512), nullable=True)

    # Relationships
    catalog = db.relationship('ApplicationCatalog', back_populates='groups')
    instances = db.relationship('ApplicationInstance', back_populates='group', lazy='dynamic', cascade="all, delete-orphan")
    
    def get_effective_playbook_path(self):
        """Получить путь к playbook (групповой или дефолтный)"""
        if self.update_playbook_path:
            return self.update_playbook_path
        from app.config import Config
        return getattr(Config, 'DEFAULT_UPDATE_PLAYBOOK', '/etc/ansible/update-app.yml')
    
    def get_instances_count(self):
        """Количество экземпляров в группе"""
        return self.instances.count()
    
    def get_custom_instances_count(self):
        """Количество экземпляров с кастомными настройками"""
        return self.instances.filter(
            db.or_(
                ApplicationInstance.custom_artifact_list_url.isnot(None),
                ApplicationInstance.custom_artifact_extension.isnot(None),
                ApplicationInstance.custom_playbook_path.isnot(None)
            )
        ).count()

    def get_batch_grouping_strategy(self):
        """Получить стратегию группировки (с fallback на 'by_group')"""
        strategy = self.batch_grouping_strategy or 'by_group'
        if strategy not in BATCH_GROUPING_STRATEGIES:
            return 'by_group'
        return strategy

    def set_batch_grouping_strategy(self, strategy):
        """Установить стратегию группировки с валидацией"""
        if strategy not in BATCH_GROUPING_STRATEGIES:
            raise ValueError(f"Недопустимая стратегия группировки: {strategy}. Допустимые значения: {', '.join(BATCH_GROUPING_STRATEGIES.keys())}")
        self.batch_grouping_strategy = strategy

    def sync_playbook_to_instances(self, old_playbook_path):
        """
        Синхронизировать playbook с экземплярами группы.

        Очищает custom_playbook_path у тех экземпляров, у которых он совпадает
        со старым значением группового playbook. Это гарантирует, что экземпляры,
        которые использовали старый групповой playbook, автоматически переключатся
        на новый групповой playbook.

        Экземпляры с реально кастомными playbook (отличными от старого группового)
        останутся без изменений.

        Args:
            old_playbook_path: Старый путь к playbook группы

        Returns:
            int: Количество синхронизированных экземпляров
        """
        if not old_playbook_path:
            return 0

        synced_count = 0
        for instance in self.instances:
            if instance.custom_playbook_path == old_playbook_path:
                instance.custom_playbook_path = None
                synced_count += 1

        return synced_count

    # ========== Методы работы с тегами ==========

    def add_tag(self, tag_name, user=None):
        """Добавить тег к группе"""
        from app.models.tag import Tag, TagHistory

        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name, display_name=tag_name.title())
            db.session.add(tag)

        if tag not in self.tags.all():
            self.tags.append(tag)
            self._update_tags_cache()

            history = TagHistory(
                entity_type='group',
                entity_id=self.id,
                tag_id=tag.id,
                action='assigned',
                changed_by=user,
                details={'tag_name': tag_name}
            )
            db.session.add(history)

        return tag

    def remove_tag(self, tag_name, user=None):
        """Удалить тег у группы"""
        from app.models.tag import Tag, TagHistory

        tag = Tag.query.filter_by(name=tag_name).first()
        if tag and tag in self.tags.all():
            self.tags.remove(tag)
            self._update_tags_cache()

            history = TagHistory(
                entity_type='group',
                entity_id=self.id,
                tag_id=tag.id,
                action='removed',
                changed_by=user
            )
            db.session.add(history)

        return tag

    def get_tag_names(self):
        """Получить список имен тегов"""
        return [t.name for t in self.tags.all()]

    def has_tags(self, tag_names):
        """Проверить наличие всех указанных тегов"""
        my_tags = set(self.get_tag_names())
        return all(t in my_tags for t in tag_names)

    def _update_tags_cache(self):
        """Обновить кэш тегов"""
        self.tags_cache = ','.join(sorted(self.get_tag_names()))

    def __repr__(self):
        return f'<ApplicationGroup {self.name}>'


# Автоматическое обновление updated_at при изменении записи
@event.listens_for(ApplicationGroup, 'before_update')
def update_group_timestamp(mapper, connection, target):
    target.updated_at = datetime.utcnow()
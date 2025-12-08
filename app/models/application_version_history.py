# app/models/application_version_history.py
# История изменений версий приложений

from app import db
from datetime import datetime
from app.utils import format_datetime_utc


class ApplicationVersionHistory(db.Model):
    """
    История изменений версий приложений.

    Записи создаются при:
    - Успешном обновлении через Ansible (changed_by='user')
    - Обнаружении новой версии агентом при polling (changed_by='agent')
    """
    __tablename__ = 'application_version_history'

    id = db.Column(db.Integer, primary_key=True)

    # Связь с экземпляром приложения
    instance_id = db.Column(
        db.Integer,
        db.ForeignKey('application_instances.id', ondelete='CASCADE'),
        nullable=False
    )

    # Данные о версии
    old_version = db.Column(db.String(128), nullable=True)  # NULL при первой записи
    new_version = db.Column(db.String(128), nullable=False)
    old_distr_path = db.Column(db.String(255), nullable=True)
    new_distr_path = db.Column(db.String(255), nullable=True)

    # Docker-специфичные поля
    old_tag = db.Column(db.String(64), nullable=True)
    new_tag = db.Column(db.String(64), nullable=True)
    old_image = db.Column(db.String(255), nullable=True)
    new_image = db.Column(db.String(255), nullable=True)

    # Метаданные изменения
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    changed_by = db.Column(db.String(20), nullable=False)  # 'user', 'agent', 'system'
    change_source = db.Column(db.String(50), nullable=True)  # 'update_task', 'polling', 'manual'

    # Дополнительные данные
    task_id = db.Column(db.String(64), nullable=True)  # ID задачи обновления
    notes = db.Column(db.Text, nullable=True)

    # Relationships
    instance = db.relationship(
        'ApplicationInstance',
        backref=db.backref('version_history', lazy='dynamic', cascade='all, delete-orphan')
    )

    # Индексы
    __table_args__ = (
        db.Index('idx_version_history_instance', 'instance_id'),
        db.Index('idx_version_history_changed_at', 'changed_at'),
        db.Index('idx_version_history_changed_by', 'changed_by'),
        db.Index('idx_version_history_instance_time', 'instance_id', 'changed_at'),
    )

    def to_dict(self, include_instance=False):
        """Преобразование в словарь для API"""
        result = {
            'id': self.id,
            'instance_id': self.instance_id,
            'old_version': self.old_version,
            'new_version': self.new_version,
            'old_distr_path': self.old_distr_path,
            'new_distr_path': self.new_distr_path,
            'old_tag': self.old_tag,
            'new_tag': self.new_tag,
            'old_image': self.old_image,
            'new_image': self.new_image,
            'changed_at': format_datetime_utc(self.changed_at),
            'changed_by': self.changed_by,
            'change_source': self.change_source,
            'task_id': self.task_id,
            'notes': self.notes
        }

        if include_instance and self.instance:
            result['instance'] = {
                'id': self.instance.id,
                'instance_name': self.instance.instance_name,
                'app_type': self.instance.app_type,
                'server_id': self.instance.server_id,
                'server_name': self.instance.server.name if self.instance.server else None,
                'group_id': self.instance.group_id,
                'group_name': self.instance.group.name if self.instance.group else None
            }

        return result

    def __repr__(self):
        return f'<ApplicationVersionHistory {self.instance_id}: {self.old_version} -> {self.new_version}>'

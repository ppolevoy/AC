# app/models/application_group.py
# ФИНАЛЬНАЯ ВЕРСИЯ - без хранения переменных в БД

from app import db
from datetime import datetime
from sqlalchemy import event

class ApplicationGroup(db.Model):
    """Группа приложений с настройками артефактов"""
    __tablename__ = 'application_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    artifact_list_url = db.Column(db.String(512), nullable=True)
    artifact_extension = db.Column(db.String(32), nullable=True)
    update_playbook_path = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с экземплярами
    instances = db.relationship('ApplicationInstance', backref='group', lazy='dynamic', cascade="all, delete-orphan")
    
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
    
    def __repr__(self):
        return f'<ApplicationGroup {self.name}>'


class ApplicationInstance(db.Model):
    """Экземпляр приложения с возможностью переопределения настроек"""
    __tablename__ = 'application_instances'
    
    id = db.Column(db.Integer, primary_key=True)
    original_name = db.Column(db.String(128), nullable=False, index=True)
    instance_number = db.Column(db.Integer, default=0, nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('application_groups.id'), nullable=False)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False, unique=True)
    group_resolved = db.Column(db.Boolean, default=False, nullable=False)
    custom_artifact_list_url = db.Column(db.String(512), nullable=True)
    custom_artifact_extension = db.Column(db.String(32), nullable=True)
    custom_playbook_path = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
        
    # Связь с Application
    application = db.relationship('Application', backref=db.backref('instance', uselist=False, cascade="all, delete-orphan"))
    
    # Уникальные ограничения
    __table_args__ = (
        db.UniqueConstraint('original_name', 'application_id', name='_original_name_app_uc'),
        db.Index('idx_group_instance', 'group_id', 'instance_number'),
        db.Index('idx_instance_resolved', 'group_resolved'),
    )
    
    def get_effective_artifact_url(self):
        """Получить эффективный URL артефактов"""
        return self.custom_artifact_list_url or (self.group.artifact_list_url if self.group else None)
    
    def get_effective_artifact_extension(self):
        """Получить эффективное расширение артефактов"""
        return self.custom_artifact_extension or (self.group.artifact_extension if self.group else None)
    
    def get_effective_playbook_path(self):
        """
        Получить эффективный путь к playbook с учетом приоритетов:
        1. Индивидуальный путь экземпляра
        2. Путь из Application
        3. Групповой путь
        4. Дефолтный путь
        
        Примеры возвращаемых значений:
        - "/etc/ansible/update.yml {server} {app} {distr_url}"
        - "/playbooks/deploy.yml {server} {app}"
        """
        from app.config import Config
        
        if self.custom_playbook_path:
            return self.custom_playbook_path
        
        if self.application and self.application.update_playbook_path:
            return self.application.update_playbook_path
        
        if self.group and self.group.update_playbook_path:
            return self.group.update_playbook_path
        
        return getattr(Config, 'DEFAULT_UPDATE_PLAYBOOK', '/etc/ansible/update-app.yml')
    
    def has_custom_settings(self):
        """Проверка наличия кастомных настроек"""
        return bool(
            self.custom_artifact_list_url or 
            self.custom_artifact_extension or 
            self.custom_playbook_path
        )
    
    def clear_custom_artifacts(self):
        """Очистить кастомные настройки артефактов"""
        self.custom_artifact_list_url = None
        self.custom_artifact_extension = None
    
    def clear_custom_playbook(self):
        """Очистить кастомный playbook"""
        self.custom_playbook_path = None
    
    def to_dict(self, include_effective=False):
        """Преобразование в словарь для API"""
        result = {
            'id': self.id,
            'original_name': self.original_name,
            'instance_number': self.instance_number,
            'group_id': self.group_id,
            'group_name': self.group.name if self.group else None,
            'application_id': self.application_id,
            'application_name': self.application.name if self.application else None,
            'server_name': self.application.server.name if self.application and self.application.server else None,
            'group_resolved': self.group_resolved,
            'custom_artifact_list_url': self.custom_artifact_list_url,
            'custom_artifact_extension': self.custom_artifact_extension,
            'custom_playbook_path': self.custom_playbook_path,
            'has_custom_settings': self.has_custom_settings(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_effective:
            result['effective'] = {
                'artifact_list_url': self.get_effective_artifact_url(),
                'artifact_extension': self.get_effective_artifact_extension(),
                'playbook_path': self.get_effective_playbook_path()
            }
        
        return result
    
    def __repr__(self):
        group_name = self.group.name if self.group else "None"
        custom = " [custom]" if self.has_custom_settings() else ""
        return f'<ApplicationInstance {self.original_name} (group: {group_name}, instance: {self.instance_number}){custom}>'


# Автоматическое обновление updated_at при изменении записи
@event.listens_for(ApplicationGroup, 'before_update')
def update_group_timestamp(mapper, connection, target):
    target.updated_at = datetime.utcnow()

@event.listens_for(ApplicationInstance, 'before_update')
def update_instance_timestamp(mapper, connection, target):
    target.updated_at = datetime.utcnow()
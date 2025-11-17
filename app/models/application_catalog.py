# app/models/application_catalog.py
from app import db
from datetime import datetime
from sqlalchemy import event

class ApplicationCatalog(db.Model):
    """
    Справочник приложений (Application Catalog).

    Хранит базовую информацию о приложениях (best-app, new-app, some-app),
    которые могут иметь множество экземпляров на разных серверах.
    """
    __tablename__ = 'application_catalog'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False, index=True)
    app_type = db.Column(db.String(32), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Значения по умолчанию для всех экземпляров этого приложения
    default_playbook_path = db.Column(db.String(255), nullable=True)
    default_artifact_url = db.Column(db.String(255), nullable=True)
    default_artifact_extension = db.Column(db.String(32), nullable=True)

    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    groups = db.relationship('ApplicationGroup', back_populates='catalog', lazy='dynamic')
    instances = db.relationship('ApplicationInstance', back_populates='catalog', lazy='dynamic')

    # Индексы
    __table_args__ = (
        db.Index('idx_catalog_name', 'name'),
        db.Index('idx_catalog_type', 'app_type'),
    )

    def get_instances_count(self):
        """Количество экземпляров этого приложения"""
        return self.instances.count()

    def get_groups_count(self):
        """Количество групп для этого приложения"""
        return self.groups.count()

    def get_effective_playbook_path(self):
        """Получить путь к playbook (дефолтный или из конфига)"""
        if self.default_playbook_path:
            return self.default_playbook_path
        from app.config import Config
        return getattr(Config, 'DEFAULT_UPDATE_PLAYBOOK', '/etc/ansible/update-app.yml')

    def to_dict(self, include_stats=False):
        """Преобразование в словарь для API"""
        result = {
            'id': self.id,
            'name': self.name,
            'app_type': self.app_type,
            'description': self.description,
            'default_playbook_path': self.default_playbook_path,
            'default_artifact_url': self.default_artifact_url,
            'default_artifact_extension': self.default_artifact_extension,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

        if include_stats:
            result['stats'] = {
                'instances_count': self.get_instances_count(),
                'groups_count': self.get_groups_count()
            }

        return result

    def __repr__(self):
        return f'<ApplicationCatalog {self.name} ({self.app_type})>'


# Автоматическое обновление updated_at при изменении записи
@event.listens_for(ApplicationCatalog, 'before_update')
def update_catalog_timestamp(mapper, connection, target):
    target.updated_at = datetime.utcnow()

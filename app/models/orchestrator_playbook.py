# app/models/orchestrator_playbook.py
from app import db
from datetime import datetime
from app.utils import format_datetime_utc

class OrchestratorPlaybook(db.Model):
    __tablename__ = 'orchestrator_playbooks'

    id = db.Column(db.Integer, primary_key=True)

    # Основная информация о playbook
    file_path = db.Column(db.String(512), nullable=False, unique=True, index=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    version = db.Column(db.String(32))

    # Метаданные параметров (хранятся в JSON)
    required_params = db.Column(db.JSON)  # {"param_name": "description"}
    optional_params = db.Column(db.JSON)  # {"param_name": {"description": "...", "default": "..."}}

    # Статус
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_scanned = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Необработанные метаданные (для отладки)
    raw_metadata = db.Column(db.JSON)

    def __repr__(self):
        return f'<OrchestratorPlaybook {self.name} v{self.version}>'

    def to_dict(self):
        """Преобразование модели в словарь для API"""
        return {
            'id': self.id,
            'file_path': self.file_path,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'required_params': self.required_params or {},
            'optional_params': self.optional_params or {},
            'is_active': self.is_active,
            'last_scanned': format_datetime_utc(self.last_scanned)
        }

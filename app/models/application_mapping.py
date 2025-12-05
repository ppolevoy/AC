# app/models/application_mapping.py
from enum import Enum
from datetime import datetime
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app import db


class MappingType(str, Enum):
    """Типы маппингов для различных сервисов"""
    HAPROXY_SERVER = 'haproxy_server'
    EUREKA_INSTANCE = 'eureka_instance'
    # Легко расширяется для новых типов (Consul, K8s и т.д.)


class ApplicationMapping(db.Model):
    """
    Унифицированная таблица маппингов приложений на внешние сервисы.
    Заменяет отдельные поля маппинга в haproxy_servers и eureka_instances.
    """
    __tablename__ = 'application_mappings'
    __table_args__ = (
        UniqueConstraint('application_id', 'entity_type', 'entity_id', name='uk_app_entity'),
        db.Index('idx_app_mappings_application_id', 'application_id'),
        db.Index('idx_app_mappings_entity', 'entity_type', 'entity_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='CASCADE'), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)  # 'haproxy_server', 'eureka_instance'
    entity_id = db.Column(db.Integer, nullable=False)  # ID сущности в соответствующей таблице
    is_manual = db.Column(db.Boolean, nullable=False, default=False)
    mapped_by = db.Column(db.String(64), nullable=True)
    mapped_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    mapping_metadata = db.Column(JSONB, nullable=True)  # Для специфичных данных сервиса
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    application = db.relationship('ApplicationInstance', backref=db.backref('mappings', lazy='dynamic', passive_deletes=True))

    def get_entity(self):
        """Получить связанную сущность"""
        if self.entity_type == MappingType.HAPROXY_SERVER.value:
            from app.models.haproxy import HAProxyServer
            return HAProxyServer.query.get(self.entity_id)
        elif self.entity_type == MappingType.EUREKA_INSTANCE.value:
            from app.models.eureka import EurekaInstance
            return EurekaInstance.query.get(self.entity_id)
        return None

    def to_dict(self, include_application=True, include_entity=False):
        """Преобразование в словарь для API"""
        result = {
            'id': self.id,
            'application_id': self.application_id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'is_manual': self.is_manual,
            'mapped_by': self.mapped_by,
            'mapped_at': self.mapped_at.isoformat() if self.mapped_at else None,
            'notes': self.notes,
            'is_active': self.is_active,
            'metadata': self.mapping_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

        if include_application and self.application:
            result['application'] = {
                'id': self.application.id,
                'instance_name': self.application.instance_name,
                'status': self.application.status,
                'server_name': self.application.server.name if self.application.server else None
            }

        if include_entity:
            entity = self.get_entity()
            if entity:
                result['entity'] = entity.to_dict() if hasattr(entity, 'to_dict') else {'id': entity.id}

        return result

    def __repr__(self):
        return f'<ApplicationMapping app={self.application_id} -> {self.entity_type}:{self.entity_id}>'


class ApplicationMappingHistory(db.Model):
    """
    История изменений маппингов приложений.
    Унифицированная таблица для всех типов маппингов.
    """
    __tablename__ = 'application_mapping_history'
    __table_args__ = (
        db.Index('idx_mapping_history_mapping_id', 'mapping_id'),
        db.Index('idx_mapping_history_application_id', 'application_id'),
        db.Index('idx_mapping_history_changed_at', 'changed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mapping_id = db.Column(db.Integer, db.ForeignKey('application_mappings.id', ondelete='SET NULL'), nullable=True)
    application_id = db.Column(db.Integer, nullable=False)  # Сохраняем для истории удаленных маппингов
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)  # 'created', 'updated', 'deleted', 'deactivated', 'activated'
    old_values = db.Column(JSONB, nullable=True)  # Старые значения полей
    new_values = db.Column(JSONB, nullable=True)  # Новые значения полей
    changed_by = db.Column(db.String(64), nullable=True)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reason = db.Column(db.Text, nullable=True)

    # Relationship
    mapping = db.relationship('ApplicationMapping', backref=db.backref('history', lazy='dynamic'))

    def to_dict(self):
        """Преобразование в словарь для API"""
        return {
            'id': self.id,
            'mapping_id': self.mapping_id,
            'application_id': self.application_id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'action': self.action,
            'old_values': self.old_values,
            'new_values': self.new_values,
            'changed_by': self.changed_by,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
            'reason': self.reason
        }

    def __repr__(self):
        return f'<ApplicationMappingHistory {self.action} mapping={self.mapping_id}>'

# План рефакторинга системы маппингов приложений на HAProxy и Eureka

## Цель рефакторинга

Вынести маппинги экземпляров приложений с HAProxy и Eureka из соответствующих таблиц (`haproxy_servers`, `eureka_instances`) в отдельные унифицированные таблицы для улучшения архитектуры, производительности и расширяемости системы.

## Текущая архитектура (AS-IS)

### Структура маппингов HAProxy

**Таблица: `haproxy_servers`**
```python
# Поля маппинга в app/models/haproxy.py:174-349
application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='SET NULL'), nullable=True)
is_manual_mapping = db.Column(db.Boolean, default=False, nullable=False)
mapped_by = db.Column(db.String(64), nullable=True)
mapped_at = db.Column(db.DateTime, nullable=True)
mapping_notes = db.Column(db.Text, nullable=True)
```

**Таблица истории: `haproxy_mapping_history`**
- Хранит полную историю изменений маппингов
- Поля: `haproxy_server_id`, `old_application_id`, `new_application_id`, `changed_at`, `change_reason`, `mapped_by`, `notes`

**Сервис: `app/services/haproxy_mapper.py`**
- Стратегии маппинга: по IP:port, по имени (hostname_appname_instance)
- Кеширование в памяти для производительности
- Методы: `map_by_address()`, `map_by_name()`, `remap_all_servers()`

### Структура маппингов Eureka

**Таблица: `eureka_instances`**
```python
# Поля маппинга в app/models/eureka.py:187-372
application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='SET NULL'), nullable=True)
is_manual_mapping = db.Column(db.Boolean, default=False, nullable=False)
mapped_by = db.Column(db.String(64), nullable=True)
mapped_at = db.Column(db.DateTime, nullable=True)
mapping_notes = db.Column(db.Text, nullable=True)
```

**Таблица истории: НЕТ**
- История маппингов для Eureka не ведется

**Сервис: `app/services/eureka_mapper.py`**
- Стратегии маппинга: по eureka_url (IP:port), по серверу и имени (fuzzy matching 60%)
- Без кеширования
- Методы: `map_by_eureka_url()`, `map_by_server_and_name()`, `map_instances_to_applications()`

### Проблемы текущей архитектуры

1. **Дублирование кода** - одинаковые поля и логика в двух местах
2. **Несогласованность** - HAProxy имеет историю, Eureka - нет
3. **Тесная связанность** - бизнес-логика маппинга смешана с инфраструктурными данными
4. **Ограничение 1:1** - невозможно замапить приложение на несколько сервисов
5. **Производительность** - нужны отдельные запросы для HAProxy и Eureka
6. **Расширяемость** - сложно добавить новые типы сервисов (Consul, K8s и т.д.)

## Целевая архитектура (TO-BE)

### 1. Новые таблицы

#### Таблица `application_mappings`

```sql
CREATE TABLE application_mappings (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL, -- 'haproxy_server', 'eureka_instance'
    entity_id INTEGER NOT NULL,       -- ID сущности в соответствующей таблице
    is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    mapped_by VARCHAR(64),
    mapped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB,                   -- Для специфичных данных сервиса
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Уникальность: одно приложение может быть замаплено на сущность только один раз
    CONSTRAINT uk_app_entity UNIQUE (application_id, entity_type, entity_id)
);

-- Индексы для производительности
CREATE INDEX idx_app_mappings_application_id ON application_mappings(application_id);
CREATE INDEX idx_app_mappings_entity ON application_mappings(entity_type, entity_id);
CREATE INDEX idx_app_mappings_active ON application_mappings(is_active) WHERE is_active = TRUE;
```

#### Таблица `application_mapping_history`

```sql
CREATE TABLE application_mapping_history (
    id SERIAL PRIMARY KEY,
    mapping_id INTEGER REFERENCES application_mappings(id) ON DELETE CASCADE,
    application_id INTEGER NOT NULL,  -- Сохраняем для истории удаленных маппингов
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,      -- 'created', 'updated', 'deleted', 'deactivated', 'activated'
    old_values JSONB,                  -- Старые значения полей
    new_values JSONB,                  -- Новые значения полей
    changed_by VARCHAR(64),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

-- Индексы
CREATE INDEX idx_mapping_history_mapping_id ON application_mapping_history(mapping_id);
CREATE INDEX idx_mapping_history_application_id ON application_mapping_history(application_id);
CREATE INDEX idx_mapping_history_changed_at ON application_mapping_history(changed_at DESC);
```

### 2. Новые модели

#### `app/models/application_mapping.py`

```python
from enum import Enum
from datetime import datetime
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.extensions import db

class MappingType(str, Enum):
    HAPROXY_SERVER = 'haproxy_server'
    EUREKA_INSTANCE = 'eureka_instance'
    # Легко расширяется для новых типов

class ApplicationMapping(db.Model):
    __tablename__ = 'application_mappings'
    __table_args__ = (
        UniqueConstraint('application_id', 'entity_type', 'entity_id', name='uk_app_entity'),
    )

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='CASCADE'), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    is_manual = db.Column(db.Boolean, nullable=False, default=False)
    mapped_by = db.Column(db.String(64))
    mapped_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    metadata = db.Column(JSONB)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    application = db.relationship('ApplicationInstance', backref='mappings', lazy='joined')

    def get_entity(self):
        """Получить связанную сущность"""
        if self.entity_type == MappingType.HAPROXY_SERVER:
            from app.models.haproxy import HAProxyServer
            return HAProxyServer.query.get(self.entity_id)
        elif self.entity_type == MappingType.EUREKA_INSTANCE:
            from app.models.eureka import EurekaInstance
            return EurekaInstance.query.get(self.entity_id)
        return None

    def to_dict(self):
        return {
            'id': self.id,
            'application_id': self.application_id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'is_manual': self.is_manual,
            'mapped_by': self.mapped_by,
            'mapped_at': self.mapped_at.isoformat() if self.mapped_at else None,
            'notes': self.notes,
            'is_active': self.is_active,
            'metadata': self.metadata,
            'application': self.application.to_dict() if self.application else None
        }

class ApplicationMappingHistory(db.Model):
    __tablename__ = 'application_mapping_history'

    id = db.Column(db.Integer, primary_key=True)
    mapping_id = db.Column(db.Integer, db.ForeignKey('application_mappings.id', ondelete='CASCADE'))
    application_id = db.Column(db.Integer, nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)
    old_values = db.Column(JSONB)
    new_values = db.Column(JSONB)
    changed_by = db.Column(db.String(64))
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reason = db.Column(db.Text)

    # Relationship
    mapping = db.relationship('ApplicationMapping', backref='history')
```

### 3. Новый унифицированный сервис

#### `app/services/mapping_service.py`

```python
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.application_mapping import ApplicationMapping, ApplicationMappingHistory, MappingType
from app.models.application_instance import ApplicationInstance
import logging

logger = logging.getLogger(__name__)

class MappingService:
    """Унифицированный сервис для управления маппингами приложений"""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 минут

    def create_mapping(
        self,
        application_id: int,
        entity_type: MappingType,
        entity_id: int,
        is_manual: bool = False,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ApplicationMapping]:
        """Создать новый маппинг"""
        try:
            # Проверка существования приложения
            app = ApplicationInstance.query.get(application_id)
            if not app:
                logger.error(f"Application {application_id} not found")
                return None

            # Создание маппинга
            mapping = ApplicationMapping(
                application_id=application_id,
                entity_type=entity_type,
                entity_id=entity_id,
                is_manual=is_manual,
                mapped_by=mapped_by,
                mapped_at=datetime.utcnow(),
                notes=notes,
                metadata=metadata
            )

            db.session.add(mapping)

            # Создание записи в истории
            self._create_history(
                mapping=mapping,
                action='created',
                new_values=mapping.to_dict(),
                changed_by=mapped_by,
                reason=notes
            )

            db.session.commit()
            self._invalidate_cache(application_id)

            logger.info(f"Created mapping: app={application_id}, type={entity_type}, entity={entity_id}")
            return mapping

        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Mapping already exists: {e}")
            return None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create mapping: {e}")
            return None

    def update_mapping(
        self,
        mapping_id: int,
        is_manual: Optional[bool] = None,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None
    ) -> Optional[ApplicationMapping]:
        """Обновить существующий маппинг"""
        mapping = ApplicationMapping.query.get(mapping_id)
        if not mapping:
            logger.error(f"Mapping {mapping_id} not found")
            return None

        old_values = mapping.to_dict()

        # Обновление полей
        if is_manual is not None:
            mapping.is_manual = is_manual
        if mapped_by is not None:
            mapping.mapped_by = mapped_by
        if notes is not None:
            mapping.notes = notes
        if metadata is not None:
            mapping.metadata = metadata
        if is_active is not None:
            mapping.is_active = is_active

        mapping.updated_at = datetime.utcnow()

        # История
        self._create_history(
            mapping=mapping,
            action='updated',
            old_values=old_values,
            new_values=mapping.to_dict(),
            changed_by=mapped_by,
            reason=notes
        )

        db.session.commit()
        self._invalidate_cache(mapping.application_id)

        return mapping

    def delete_mapping(
        self,
        mapping_id: int,
        deleted_by: Optional[str] = None,
        reason: Optional[str] = None
    ) -> bool:
        """Удалить маппинг"""
        mapping = ApplicationMapping.query.get(mapping_id)
        if not mapping:
            return False

        # История удаления
        self._create_history(
            mapping=mapping,
            action='deleted',
            old_values=mapping.to_dict(),
            changed_by=deleted_by,
            reason=reason
        )

        app_id = mapping.application_id
        db.session.delete(mapping)
        db.session.commit()

        self._invalidate_cache(app_id)
        return True

    def get_mappings_for_application(
        self,
        application_id: int,
        entity_type: Optional[MappingType] = None,
        active_only: bool = True
    ) -> List[ApplicationMapping]:
        """Получить все маппинги для приложения"""
        query = ApplicationMapping.query.filter_by(application_id=application_id)

        if entity_type:
            query = query.filter_by(entity_type=entity_type)

        if active_only:
            query = query.filter_by(is_active=True)

        return query.all()

    def get_mappings_for_entity(
        self,
        entity_type: MappingType,
        entity_id: int,
        active_only: bool = True
    ) -> List[ApplicationMapping]:
        """Получить маппинги для сущности"""
        query = ApplicationMapping.query.filter_by(
            entity_type=entity_type,
            entity_id=entity_id
        )

        if active_only:
            query = query.filter_by(is_active=True)

        return query.all()

    def map_haproxy_server(
        self,
        haproxy_server_id: int,
        application_id: int,
        is_manual: bool = False,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[ApplicationMapping]:
        """Специализированный метод для HAProxy"""
        # Проверка существования HAProxyServer
        from app.models.haproxy import HAProxyServer
        server = HAProxyServer.query.get(haproxy_server_id)
        if not server:
            logger.error(f"HAProxyServer {haproxy_server_id} not found")
            return None

        # Деактивация старых маппингов
        old_mappings = self.get_mappings_for_entity(
            MappingType.HAPROXY_SERVER,
            haproxy_server_id,
            active_only=True
        )

        for old_mapping in old_mappings:
            self.update_mapping(
                old_mapping.id,
                is_active=False,
                mapped_by=mapped_by,
                notes="Deactivated due to new mapping"
            )

        # Создание нового маппинга
        return self.create_mapping(
            application_id=application_id,
            entity_type=MappingType.HAPROXY_SERVER,
            entity_id=haproxy_server_id,
            is_manual=is_manual,
            mapped_by=mapped_by,
            notes=notes,
            metadata={
                'backend_name': server.backend.name if server.backend else None,
                'server_name': server.name,
                'address': server.address
            }
        )

    def map_eureka_instance(
        self,
        eureka_instance_id: int,
        application_id: int,
        is_manual: bool = False,
        mapped_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[ApplicationMapping]:
        """Специализированный метод для Eureka"""
        # Проверка существования EurekaInstance
        from app.models.eureka import EurekaInstance
        instance = EurekaInstance.query.get(eureka_instance_id)
        if not instance:
            logger.error(f"EurekaInstance {eureka_instance_id} not found")
            return None

        # Деактивация старых маппингов
        old_mappings = self.get_mappings_for_entity(
            MappingType.EUREKA_INSTANCE,
            eureka_instance_id,
            active_only=True
        )

        for old_mapping in old_mappings:
            self.update_mapping(
                old_mapping.id,
                is_active=False,
                mapped_by=mapped_by,
                notes="Deactivated due to new mapping"
            )

        # Создание нового маппинга
        return self.create_mapping(
            application_id=application_id,
            entity_type=MappingType.EUREKA_INSTANCE,
            entity_id=eureka_instance_id,
            is_manual=is_manual,
            mapped_by=mapped_by,
            notes=notes,
            metadata={
                'service_name': instance.application.name if instance.application else None,
                'instance_id': instance.instance_id,
                'eureka_url': instance.eureka_url
            }
        )

    def get_mapping_statistics(self) -> Dict[str, Any]:
        """Получить статистику маппингов"""
        stats = {
            'total': ApplicationMapping.query.count(),
            'active': ApplicationMapping.query.filter_by(is_active=True).count(),
            'manual': ApplicationMapping.query.filter_by(is_manual=True, is_active=True).count(),
            'automatic': ApplicationMapping.query.filter_by(is_manual=False, is_active=True).count(),
            'by_type': {}
        }

        for mapping_type in MappingType:
            stats['by_type'][mapping_type.value] = {
                'total': ApplicationMapping.query.filter_by(entity_type=mapping_type.value).count(),
                'active': ApplicationMapping.query.filter_by(
                    entity_type=mapping_type.value,
                    is_active=True
                ).count()
            }

        return stats

    def _create_history(
        self,
        mapping: ApplicationMapping,
        action: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """Создать запись в истории"""
        history = ApplicationMappingHistory(
            mapping_id=mapping.id if action != 'deleted' else None,
            application_id=mapping.application_id,
            entity_type=mapping.entity_type,
            entity_id=mapping.entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            changed_by=changed_by,
            changed_at=datetime.utcnow(),
            reason=reason
        )
        db.session.add(history)

    def _invalidate_cache(self, application_id: int):
        """Инвалидировать кеш для приложения"""
        cache_keys_to_remove = [
            key for key in self._cache.keys()
            if key.startswith(f"app_{application_id}_")
        ]
        for key in cache_keys_to_remove:
            del self._cache[key]

# Singleton
mapping_service = MappingService()
```

### 4. Обновление существующих сервисов

#### Изменения в `HAProxyMapper`

```python
# app/services/haproxy_mapper.py
from app.services.mapping_service import mapping_service, MappingType

class HAProxyMapper:
    def map_server_to_application(self, server, application_id=None):
        """Маппинг HAProxy сервера на приложение используя MappingService"""

        # Проверка на ручной маппинг через MappingService
        existing_mappings = mapping_service.get_mappings_for_entity(
            MappingType.HAPROXY_SERVER,
            server.id,
            active_only=True
        )

        if existing_mappings and existing_mappings[0].is_manual:
            logger.info(f"Server {server.name} has manual mapping, skipping auto-mapping")
            return existing_mappings[0].application

        # Автоматический маппинг
        if not application_id:
            application_id = self._find_application_for_server(server)

        if application_id:
            mapping = mapping_service.map_haproxy_server(
                haproxy_server_id=server.id,
                application_id=application_id,
                is_manual=False,
                mapped_by='auto',
                notes='Automatic mapping based on address or name'
            )
            return mapping.application if mapping else None

        return None
```

#### Изменения в `EurekaMapper`

```python
# app/services/eureka_mapper.py
from app.services.mapping_service import mapping_service, MappingType

class EurekaMapper:
    def map_instance_to_application(self, instance, application_id=None):
        """Маппинг Eureka инстанса на приложение используя MappingService"""

        # Проверка на ручной маппинг через MappingService
        existing_mappings = mapping_service.get_mappings_for_entity(
            MappingType.EUREKA_INSTANCE,
            instance.id,
            active_only=True
        )

        if existing_mappings and existing_mappings[0].is_manual:
            logger.info(f"Instance {instance.instance_id} has manual mapping, skipping auto-mapping")
            return existing_mappings[0].application

        # Автоматический маппинг
        if not application_id:
            application_id = self._find_application_for_instance(instance)

        if application_id:
            mapping = mapping_service.map_eureka_instance(
                eureka_instance_id=instance.id,
                application_id=application_id,
                is_manual=False,
                mapped_by='auto',
                notes='Automatic mapping based on eureka_url or name'
            )
            return mapping.application if mapping else None

        return None
```

### 5. API эндпоинты

#### `app/api/mappings_routes.py`

```python
from flask import Blueprint, jsonify, request
from app.services.mapping_service import mapping_service, MappingType
from app.models.application_mapping import ApplicationMapping, ApplicationMappingHistory

bp = Blueprint('mappings', __name__)

@bp.route('/api/mappings', methods=['GET'])
def get_mappings():
    """Получить все маппинги с фильтрацией"""
    application_id = request.args.get('application_id', type=int)
    entity_type = request.args.get('entity_type')
    entity_id = request.args.get('entity_id', type=int)
    active_only = request.args.get('active_only', 'true').lower() == 'true'

    if application_id:
        mappings = mapping_service.get_mappings_for_application(
            application_id, entity_type, active_only
        )
    elif entity_type and entity_id:
        mappings = mapping_service.get_mappings_for_entity(
            entity_type, entity_id, active_only
        )
    else:
        query = ApplicationMapping.query
        if active_only:
            query = query.filter_by(is_active=True)
        mappings = query.all()

    return jsonify([m.to_dict() for m in mappings])

@bp.route('/api/mappings', methods=['POST'])
def create_mapping():
    """Создать новый маппинг"""
    data = request.get_json()

    mapping = mapping_service.create_mapping(
        application_id=data['application_id'],
        entity_type=data['entity_type'],
        entity_id=data['entity_id'],
        is_manual=data.get('is_manual', False),
        mapped_by=data.get('mapped_by'),
        notes=data.get('notes'),
        metadata=data.get('metadata')
    )

    if mapping:
        return jsonify(mapping.to_dict()), 201
    return jsonify({'error': 'Failed to create mapping'}), 400

@bp.route('/api/mappings/<int:mapping_id>', methods=['PUT'])
def update_mapping(mapping_id):
    """Обновить маппинг"""
    data = request.get_json()

    mapping = mapping_service.update_mapping(
        mapping_id=mapping_id,
        is_manual=data.get('is_manual'),
        mapped_by=data.get('mapped_by'),
        notes=data.get('notes'),
        metadata=data.get('metadata'),
        is_active=data.get('is_active')
    )

    if mapping:
        return jsonify(mapping.to_dict())
    return jsonify({'error': 'Mapping not found'}), 404

@bp.route('/api/mappings/<int:mapping_id>', methods=['DELETE'])
def delete_mapping(mapping_id):
    """Удалить маппинг"""
    deleted_by = request.args.get('deleted_by')
    reason = request.args.get('reason')

    if mapping_service.delete_mapping(mapping_id, deleted_by, reason):
        return '', 204
    return jsonify({'error': 'Mapping not found'}), 404

@bp.route('/api/mappings/<int:mapping_id>/history', methods=['GET'])
def get_mapping_history(mapping_id):
    """История изменений маппинга"""
    history = ApplicationMappingHistory.query.filter_by(
        mapping_id=mapping_id
    ).order_by(ApplicationMappingHistory.changed_at.desc()).all()

    return jsonify([{
        'id': h.id,
        'action': h.action,
        'old_values': h.old_values,
        'new_values': h.new_values,
        'changed_by': h.changed_by,
        'changed_at': h.changed_at.isoformat() if h.changed_at else None,
        'reason': h.reason
    } for h in history])

@bp.route('/api/mappings/stats', methods=['GET'])
def get_mapping_stats():
    """Статистика маппингов"""
    return jsonify(mapping_service.get_mapping_statistics())

@bp.route('/api/mappings/auto-map', methods=['POST'])
def auto_map():
    """Запустить автоматический маппинг"""
    entity_type = request.args.get('entity_type')

    if entity_type == MappingType.HAPROXY_SERVER.value:
        from app.services.haproxy_mapper import haproxy_mapper
        result = haproxy_mapper.remap_all_servers()
    elif entity_type == MappingType.EUREKA_INSTANCE.value:
        from app.services.eureka_mapper import eureka_mapper
        result = eureka_mapper.map_instances_to_applications()
    else:
        return jsonify({'error': 'Invalid entity_type'}), 400

    return jsonify(result)
```

#### Регистрация blueprint в `app/api/__init__.py`

```python
# Добавить в app/api/__init__.py
from app.api import mappings_routes

def register_api_blueprints(app):
    # ... существующие blueprints ...
    app.register_blueprint(mappings_routes.bp)
```

### 6. Миграция базы данных

#### Alembic миграция для создания новых таблиц

```python
"""Create application mapping tables

Revision ID: xxx
Revises: yyy
Create Date: 2024-xx-xx

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Создание таблицы application_mappings
    op.create_table('application_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('is_manual', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('mapped_by', sa.String(length=64), nullable=True),
        sa.Column('mapped_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['application_id'], ['application_instances.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', 'entity_type', 'entity_id', name='uk_app_entity')
    )

    # Индексы
    op.create_index('idx_app_mappings_application_id', 'application_mappings', ['application_id'])
    op.create_index('idx_app_mappings_entity', 'application_mappings', ['entity_type', 'entity_id'])
    op.create_index('idx_app_mappings_active', 'application_mappings', ['is_active'],
                    postgresql_where=sa.text('is_active = true'))

    # Создание таблицы application_mapping_history
    op.create_table('application_mapping_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mapping_id', sa.Integer(), nullable=True),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('old_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_by', sa.String(length=64), nullable=True),
        sa.Column('changed_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['mapping_id'], ['application_mappings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Индексы для истории
    op.create_index('idx_mapping_history_mapping_id', 'application_mapping_history', ['mapping_id'])
    op.create_index('idx_mapping_history_application_id', 'application_mapping_history', ['application_id'])
    op.create_index('idx_mapping_history_changed_at', 'application_mapping_history', ['changed_at'],
                    postgresql_order_by='DESC')

def downgrade():
    op.drop_index('idx_mapping_history_changed_at', table_name='application_mapping_history')
    op.drop_index('idx_mapping_history_application_id', table_name='application_mapping_history')
    op.drop_index('idx_mapping_history_mapping_id', table_name='application_mapping_history')
    op.drop_table('application_mapping_history')

    op.drop_index('idx_app_mappings_active', table_name='application_mappings')
    op.drop_index('idx_app_mappings_entity', table_name='application_mappings')
    op.drop_index('idx_app_mappings_application_id', table_name='application_mappings')
    op.drop_table('application_mappings')
```

#### Миграция для удаления старых полей

```python
"""Remove old mapping fields from haproxy and eureka tables

Revision ID: zzz
Revises: xxx
Create Date: 2024-xx-xx

"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Удаление полей из haproxy_servers
    op.drop_column('haproxy_servers', 'application_id')
    op.drop_column('haproxy_servers', 'is_manual_mapping')
    op.drop_column('haproxy_servers', 'mapped_by')
    op.drop_column('haproxy_servers', 'mapped_at')
    op.drop_column('haproxy_servers', 'mapping_notes')

    # Удаление полей из eureka_instances
    op.drop_column('eureka_instances', 'application_id')
    op.drop_column('eureka_instances', 'is_manual_mapping')
    op.drop_column('eureka_instances', 'mapped_by')
    op.drop_column('eureka_instances', 'mapped_at')
    op.drop_column('eureka_instances', 'mapping_notes')

    # Удаление таблицы haproxy_mapping_history (заменена на общую)
    op.drop_table('haproxy_mapping_history')

def downgrade():
    # Восстановление полей в haproxy_servers
    op.add_column('haproxy_servers', sa.Column('application_id', sa.INTEGER(), nullable=True))
    op.add_column('haproxy_servers', sa.Column('is_manual_mapping', sa.BOOLEAN(), nullable=False, server_default='false'))
    op.add_column('haproxy_servers', sa.Column('mapped_by', sa.VARCHAR(length=64), nullable=True))
    op.add_column('haproxy_servers', sa.Column('mapped_at', sa.DATETIME(), nullable=True))
    op.add_column('haproxy_servers', sa.Column('mapping_notes', sa.TEXT(), nullable=True))

    # Восстановление полей в eureka_instances
    op.add_column('eureka_instances', sa.Column('application_id', sa.INTEGER(), nullable=True))
    op.add_column('eureka_instances', sa.Column('is_manual_mapping', sa.BOOLEAN(), nullable=False, server_default='false'))
    op.add_column('eureka_instances', sa.Column('mapped_by', sa.VARCHAR(length=64), nullable=True))
    op.add_column('eureka_instances', sa.Column('mapped_at', sa.DATETIME(), nullable=True))
    op.add_column('eureka_instances', sa.Column('mapping_notes', sa.TEXT(), nullable=True))
```

### 7. UI на странице Settings

#### Расположение: `/app/static/js/settings.js`

Добавить новый раздел для управления маппингами:

```javascript
// Новый раздел в settings.js
class MappingSettings {
    constructor() {
        this.initializeCollapsible();
        this.loadMappings();
    }

    initializeCollapsible() {
        // Создание раскрывающегося блока как у других настроек
        const mappingSection = `
            <div class="settings-section">
                <div class="settings-header" data-toggle="collapse" data-target="#mapping-settings">
                    <i class="fas fa-link"></i> Маппинги приложений
                    <i class="fas fa-chevron-down float-right"></i>
                </div>
                <div id="mapping-settings" class="collapse settings-content">
                    <div class="mapping-controls mb-3">
                        <button class="btn btn-primary" onclick="mappingSettings.autoMap('haproxy')">
                            <i class="fas fa-magic"></i> Авто-маппинг HAProxy
                        </button>
                        <button class="btn btn-primary" onclick="mappingSettings.autoMap('eureka')">
                            <i class="fas fa-magic"></i> Авто-маппинг Eureka
                        </button>
                        <button class="btn btn-info" onclick="mappingSettings.showStats()">
                            <i class="fas fa-chart-bar"></i> Статистика
                        </button>
                    </div>

                    <div class="mapping-filters mb-3">
                        <select id="mapping-type-filter" class="form-control d-inline-block w-auto">
                            <option value="">Все типы</option>
                            <option value="haproxy_server">HAProxy</option>
                            <option value="eureka_instance">Eureka</option>
                        </select>

                        <select id="mapping-status-filter" class="form-control d-inline-block w-auto">
                            <option value="active">Активные</option>
                            <option value="all">Все</option>
                        </select>

                        <input type="text" id="mapping-search" class="form-control d-inline-block w-auto"
                               placeholder="Поиск приложения...">
                    </div>

                    <div id="mapping-list" class="table-responsive">
                        <!-- Таблица маппингов загружается сюда -->
                    </div>
                </div>
            </div>
        `;

        $('#settings-container').append(mappingSection);
    }

    loadMappings() {
        const filters = {
            entity_type: $('#mapping-type-filter').val(),
            active_only: $('#mapping-status-filter').val() === 'active'
        };

        $.get('/api/mappings', filters)
            .done(data => this.renderMappings(data))
            .fail(error => this.showError('Ошибка загрузки маппингов'));
    }

    renderMappings(mappings) {
        let html = `
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th>Приложение</th>
                        <th>Тип</th>
                        <th>Сущность</th>
                        <th>Ручной</th>
                        <th>Создан</th>
                        <th>Кем</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
        `;

        mappings.forEach(mapping => {
            const manualBadge = mapping.is_manual ?
                '<span class="badge badge-warning">Ручной</span>' :
                '<span class="badge badge-success">Авто</span>';

            html += `
                <tr class="${!mapping.is_active ? 'table-secondary' : ''}">
                    <td>${mapping.application?.instance_name || mapping.application_id}</td>
                    <td>${mapping.entity_type}</td>
                    <td>${mapping.entity_id}</td>
                    <td>${manualBadge}</td>
                    <td>${new Date(mapping.mapped_at).toLocaleDateString()}</td>
                    <td>${mapping.mapped_by || '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-info" onclick="mappingSettings.showHistory(${mapping.id})">
                            <i class="fas fa-history"></i>
                        </button>
                        ${mapping.is_active ? `
                            <button class="btn btn-sm btn-danger" onclick="mappingSettings.deactivate(${mapping.id})">
                                <i class="fas fa-times"></i>
                            </button>
                        ` : ''}
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        $('#mapping-list').html(html);
    }

    autoMap(type) {
        const entityType = type === 'haproxy' ? 'haproxy_server' : 'eureka_instance';

        $.post(`/api/mappings/auto-map?entity_type=${entityType}`)
            .done(result => {
                this.showSuccess('Автоматический маппинг выполнен');
                this.loadMappings();
            })
            .fail(error => this.showError('Ошибка автоматического маппинга'));
    }

    showHistory(mappingId) {
        $.get(`/api/mappings/${mappingId}/history`)
            .done(history => {
                // Показать модальное окно с историей
                this.renderHistoryModal(history);
            });
    }

    showStats() {
        $.get('/api/mappings/stats')
            .done(stats => {
                // Показать модальное окно со статистикой
                this.renderStatsModal(stats);
            });
    }
}

// Инициализация при загрузке страницы
$(document).ready(() => {
    window.mappingSettings = new MappingSettings();
});
```

### 8. Преимущества новой архитектуры

1. **Унификация** - единая логика для всех типов маппингов
2. **Расширяемость** - легко добавить новые типы сервисов (Consul, K8s)
3. **История** - полная история изменений для всех маппингов
4. **Производительность** - оптимизированные индексы и запросы
5. **Целостность данных** - уникальные ограничения на уровне БД
6. **Гибкость** - поддержка N:M связей, soft-delete, метаданные

### 9. План тестирования

1. **Unit-тесты** для MappingService
2. **Интеграционные тесты** для API эндпоинтов
3. **Тесты производительности** для сравнения с текущей реализацией
4. **UI тесты** для новой страницы настроек

### 10. Дальнейшие улучшения (после MVP)

1. Добавление поддержки bulk операций
2. WebSocket уведомления об изменениях маппингов
3. Экспорт/импорт маппингов
4. Аудит и compliance отчеты
5. Графическая визуализация связей
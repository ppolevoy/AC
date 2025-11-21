# app/models/haproxy.py
from app import db
from datetime import datetime


class HAProxyInstance(db.Model):
    """
    Представляет HAProxy инстанс, доступный через FAgent API.
    Каждый сервер с FAgent может иметь один или несколько HAProxy инстансов.
    """
    __tablename__ = 'haproxy_instances'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)  # Имя инстанса (default, prod, etc.)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id', ondelete='CASCADE'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # Включен ли мониторинг
    socket_path = db.Column(db.String(256), nullable=True)  # unix:/path или ipv4@ip:port

    # Статус синхронизации
    last_sync = db.Column(db.DateTime, nullable=True)
    last_sync_status = db.Column(db.String(32), default='unknown')  # success/failed/unknown
    last_sync_error = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    server = db.relationship('Server', backref=db.backref('haproxy_instances', lazy='dynamic', cascade='all, delete-orphan'))
    backends = db.relationship('HAProxyBackend', back_populates='haproxy_instance', lazy='dynamic', cascade='all, delete-orphan')

    # Индексы
    __table_args__ = (
        db.UniqueConstraint('server_id', 'name', name='uq_haproxy_instance_per_server'),
        db.Index('idx_haproxy_instance_server', 'server_id'),
        db.Index('idx_haproxy_instance_active', 'is_active'),
    )

    def mark_sync_success(self):
        """Отметить успешную синхронизацию"""
        self.last_sync = datetime.utcnow()
        self.last_sync_status = 'success'
        self.last_sync_error = None

    def mark_sync_failed(self, error_message):
        """Отметить неудачную синхронизацию"""
        self.last_sync = datetime.utcnow()
        self.last_sync_status = 'failed'
        self.last_sync_error = error_message

    def to_dict(self, include_backends=False):
        """Преобразование в словарь для API"""
        # Подсчет backends (не удаленных)
        backends_count = self.backends.filter(HAProxyBackend.removed_at.is_(None)).count()

        result = {
            'id': self.id,
            'name': self.name,
            'server_id': self.server_id,
            'server_name': self.server.name if self.server else None,
            'is_active': self.is_active,
            'socket_path': self.socket_path,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'last_sync_at': self.last_sync.isoformat() if self.last_sync else None,  # Alias for frontend
            'last_sync_status': self.last_sync_status,
            'last_sync_error': self.last_sync_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'backends_count': backends_count
        }

        if include_backends:
            result['backends'] = [b.to_dict() for b in self.backends.filter(HAProxyBackend.removed_at.is_(None)).all()]

        return result

    def __repr__(self):
        return f'<HAProxyInstance {self.name} on {self.server.name if self.server else "?"}>'


class HAProxyBackend(db.Model):
    """
    Представляет backend (пул серверов) в HAProxy.
    """
    __tablename__ = 'haproxy_backends'

    id = db.Column(db.Integer, primary_key=True)
    haproxy_instance_id = db.Column(db.Integer, db.ForeignKey('haproxy_instances.id', ondelete='CASCADE'), nullable=False)
    backend_name = db.Column(db.String(128), nullable=False)

    # Backend polling configuration
    enable_polling = db.Column(db.Boolean, default=True, nullable=False)

    # Error tracking for backend data fetching
    last_fetch_status = db.Column(db.String(20), default='unknown')  # success, failed, unknown
    last_fetch_error = db.Column(db.Text, nullable=True)  # Error message if failed
    last_fetch_at = db.Column(db.DateTime, nullable=True)  # Last fetch attempt timestamp

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)  # Soft delete

    # Relationships
    haproxy_instance = db.relationship('HAProxyInstance', back_populates='backends')
    servers = db.relationship('HAProxyServer', back_populates='backend', lazy='dynamic', cascade='all, delete-orphan')

    # Индексы
    __table_args__ = (
        db.UniqueConstraint('haproxy_instance_id', 'backend_name', name='uq_backend_per_instance'),
        db.Index('idx_haproxy_backend_instance', 'haproxy_instance_id'),
        db.Index('idx_haproxy_backend_removed', 'removed_at'),
    )

    def soft_delete(self):
        """Мягкое удаление backend"""
        self.removed_at = datetime.utcnow()

    def is_removed(self):
        """Проверка, удален ли backend"""
        return self.removed_at is not None

    def restore(self):
        """Восстановление удаленного backend"""
        self.removed_at = None

    def mark_fetch_success(self):
        """Отметить успешное получение данных от агента"""
        self.last_fetch_status = 'success'
        self.last_fetch_error = None
        self.last_fetch_at = datetime.utcnow()

    def mark_fetch_failed(self, error_message):
        """Отметить неудачную попытку получения данных от агента"""
        self.last_fetch_status = 'failed'
        self.last_fetch_error = error_message
        self.last_fetch_at = datetime.utcnow()

    def to_dict(self, include_servers=False):
        """Преобразование в словарь для API"""
        # Подсчет servers (не удаленных)
        servers_count = self.servers.filter(HAProxyServer.removed_at.is_(None)).count()

        result = {
            'id': self.id,
            'haproxy_instance_id': self.haproxy_instance_id,
            'backend_name': self.backend_name,
            'enable_polling': self.enable_polling,
            'last_fetch_status': self.last_fetch_status,
            'last_fetch_error': self.last_fetch_error,
            'last_fetch_at': self.last_fetch_at.isoformat() if self.last_fetch_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'is_removed': self.is_removed(),
            'servers_count': servers_count
        }

        if include_servers:
            result['servers'] = [s.to_dict() for s in self.servers.filter(HAProxyServer.removed_at.is_(None)).all()]

            # Статистика по статусам
            servers_list = result['servers']
            result['status_stats'] = {
                'UP': sum(1 for s in servers_list if s.get('status') == 'UP'),
                'DOWN': sum(1 for s in servers_list if s.get('status') == 'DOWN'),
                'DRAIN': sum(1 for s in servers_list if s.get('status') == 'DRAIN'),
                'MAINT': sum(1 for s in servers_list if s.get('status') == 'MAINT'),
            }

        return result

    def __repr__(self):
        return f'<HAProxyBackend {self.backend_name}>'


class HAProxyServer(db.Model):
    """
    Представляет сервер (член backend'а) в HAProxy.
    Может быть связан с приложением из AC платформы.
    """
    __tablename__ = 'haproxy_servers'

    id = db.Column(db.Integer, primary_key=True)
    backend_id = db.Column(db.Integer, db.ForeignKey('haproxy_backends.id', ondelete='CASCADE'), nullable=False)
    server_name = db.Column(db.String(128), nullable=False)

    # Состояние сервера в HAProxy
    status = db.Column(db.String(32), nullable=True)  # UP, DOWN, MAINT, DRAIN
    weight = db.Column(db.Integer, default=1)
    check_status = db.Column(db.String(64), nullable=True)  # L4OK, L7OK, etc.
    addr = db.Column(db.String(128), nullable=True)  # IP:port

    # Метрики
    last_check_duration = db.Column(db.Integer, nullable=True)  # milliseconds
    last_state_change = db.Column(db.Integer, nullable=True)  # seconds since last change
    downtime = db.Column(db.Integer, nullable=True)  # total downtime in seconds

    # Подключения
    scur = db.Column(db.Integer, default=0)  # current sessions
    smax = db.Column(db.Integer, default=0)  # max sessions

    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)  # Soft delete

    # Relationships
    backend = db.relationship('HAProxyBackend', back_populates='servers')
    status_history = db.relationship('HAProxyServerStatusHistory', back_populates='haproxy_server', lazy='dynamic', cascade='all, delete-orphan')
    mapping_history = db.relationship('HAProxyMappingHistory', back_populates='haproxy_server', lazy='dynamic', cascade='all, delete-orphan')

    # Индексы
    __table_args__ = (
        db.UniqueConstraint('backend_id', 'server_name', name='uq_server_per_backend'),
        db.Index('idx_haproxy_server_backend', 'backend_id'),
        db.Index('idx_haproxy_server_status', 'status'),
        db.Index('idx_haproxy_server_removed', 'removed_at'),
    )

    def update_status(self, new_status, reason='sync'):
        """
        Обновить статус сервера и записать в историю.

        Args:
            new_status: Новый статус
            reason: Причина изменения (sync, command, manual)
        """
        if self.status != new_status:
            # Создаем запись в истории
            history = HAProxyServerStatusHistory(
                haproxy_server_id=self.id,
                old_status=self.status,
                new_status=new_status,
                change_reason=reason
            )
            db.session.add(history)

            # Обновляем статус
            self.status = new_status
            self.updated_at = datetime.utcnow()

    def soft_delete(self):
        """Мягкое удаление сервера"""
        self.removed_at = datetime.utcnow()

    def is_removed(self):
        """Проверка, удален ли сервер"""
        return self.removed_at is not None

    def restore(self):
        """Восстановление удаленного сервера"""
        self.removed_at = None

    def to_dict(self, include_application=True, include_backend=False):
        """Преобразование в словарь для API"""
        # Получаем маппинг из унифицированной таблицы
        from app.models.application_mapping import ApplicationMapping, MappingType

        mapping = ApplicationMapping.query.filter_by(
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=self.id,
            is_active=True
        ).first()

        # Данные маппинга из унифицированной таблицы
        if mapping:
            application_id = mapping.application_id
            is_manual_mapping = mapping.is_manual
            mapped_by = mapping.mapped_by
            mapped_at = mapping.mapped_at
            mapping_notes = mapping.notes
            application = mapping.application
        else:
            application_id = None
            is_manual_mapping = False
            mapped_by = None
            mapped_at = None
            mapping_notes = None
            application = None

        result = {
            'id': self.id,
            'backend_id': self.backend_id,
            'server_name': self.server_name,
            'status': self.status,
            'weight': self.weight,
            'check_status': self.check_status,
            'addr': self.addr,
            'last_check_duration': self.last_check_duration,
            'last_state_change': self.last_state_change,
            'downtime': self.downtime,
            'scur': self.scur,
            'smax': self.smax,
            'application_id': application_id,
            'is_manual_mapping': is_manual_mapping,
            'mapped_by': mapped_by,
            'mapped_at': mapped_at.isoformat() if mapped_at else None,
            'mapping_notes': mapping_notes,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'is_removed': self.is_removed()
        }

        if include_application and application:
            result['application'] = {
                'id': application.id,
                'name': application.instance_name,
                'status': application.status,
                'server_name': application.server.name if application.server else None
            }

        if include_backend and self.backend:
            result['backend'] = {
                'id': self.backend.id,
                'backend_name': self.backend.backend_name,
                'haproxy_instance_id': self.backend.haproxy_instance_id
            }

        return result

    def __repr__(self):
        return f'<HAProxyServer {self.server_name} ({self.status})>'


class HAProxyServerStatusHistory(db.Model):
    """
    История изменений статуса HAProxy сервера.
    """
    __tablename__ = 'haproxy_server_status_history'

    id = db.Column(db.Integer, primary_key=True)
    haproxy_server_id = db.Column(db.Integer, db.ForeignKey('haproxy_servers.id', ondelete='CASCADE'), nullable=False)
    old_status = db.Column(db.String(32), nullable=True)
    new_status = db.Column(db.String(32), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    change_reason = db.Column(db.String(64), nullable=True)  # sync, command, manual

    # Relationships
    haproxy_server = db.relationship('HAProxyServer', back_populates='status_history')

    # Индексы
    __table_args__ = (
        db.Index('idx_haproxy_history_server', 'haproxy_server_id'),
        db.Index('idx_haproxy_history_changed_at', 'changed_at'),
    )

    def to_dict(self):
        """Преобразование в словарь для API"""
        return {
            'id': self.id,
            'haproxy_server_id': self.haproxy_server_id,
            'old_status': self.old_status,
            'new_status': self.new_status,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
            'change_reason': self.change_reason
        }

    def __repr__(self):
        return f'<HAProxyServerStatusHistory {self.old_status} -> {self.new_status}>'


class HAProxyMappingHistory(db.Model):
    """
    История изменений маппинга HAProxy серверов на приложения AC.
    Записывает все изменения связывания серверов с приложениями.
    """
    __tablename__ = 'haproxy_mapping_history'

    id = db.Column(db.Integer, primary_key=True)
    haproxy_server_id = db.Column(db.Integer, db.ForeignKey('haproxy_servers.id', ondelete='CASCADE'), nullable=False)
    old_application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='SET NULL'), nullable=True)
    new_application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='SET NULL'), nullable=True)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    change_reason = db.Column(db.String(32), nullable=False)  # manual, automatic
    mapped_by = db.Column(db.String(64), nullable=True)  # Кто выполнил маппинг (для ручного)
    notes = db.Column(db.Text, nullable=True)  # Заметки о причине изменения

    # Relationships
    haproxy_server = db.relationship('HAProxyServer', back_populates='mapping_history')
    old_application = db.relationship('ApplicationInstance', foreign_keys=[old_application_id])
    new_application = db.relationship('ApplicationInstance', foreign_keys=[new_application_id])

    # Индексы
    __table_args__ = (
        db.Index('idx_haproxy_mapping_history_server', 'haproxy_server_id'),
        db.Index('idx_haproxy_mapping_history_changed_at', 'changed_at'),
        db.Index('idx_haproxy_mapping_history_reason', 'change_reason'),
    )

    def to_dict(self):
        """Преобразование в словарь для API"""
        result = {
            'id': self.id,
            'haproxy_server_id': self.haproxy_server_id,
            'old_application_id': self.old_application_id,
            'new_application_id': self.new_application_id,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
            'change_reason': self.change_reason,
            'mapped_by': self.mapped_by,
            'notes': self.notes
        }

        # Включаем информацию о старом приложении, если оно есть
        if self.old_application:
            result['old_application'] = {
                'id': self.old_application.id,
                'name': self.old_application.instance_name
            }

        # Включаем информацию о новом приложении, если оно есть
        if self.new_application:
            result['new_application'] = {
                'id': self.new_application.id,
                'name': self.new_application.instance_name
            }

        return result

    def __repr__(self):
        return f'<HAProxyMappingHistory server_id={self.haproxy_server_id} {self.old_application_id} -> {self.new_application_id}>'

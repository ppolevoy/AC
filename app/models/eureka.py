# app/models/eureka.py
from app import db
from datetime import datetime


class EurekaServer(db.Model):
    """
    Представляет Eureka Server (сервер реестра сервисов).
    Каждый сервер с FAgent может быть настроен как Eureka узел.
    """
    __tablename__ = 'eureka_servers'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id', ondelete='CASCADE'), nullable=False)
    eureka_host = db.Column(db.String(255), nullable=False)  # Хост Eureka реестра
    eureka_port = db.Column(db.Integer, nullable=False)  # Порт Eureka реестра
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # Активен ли мониторинг

    # Статус синхронизации
    last_sync = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    consecutive_failures = db.Column(db.Integer, default=0)  # Счетчик последовательных сбоев

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)  # Soft delete

    # Relationships
    server = db.relationship('Server', backref=db.backref('eureka_server', uselist=False, cascade='all, delete-orphan'))
    applications = db.relationship('EurekaApplication', back_populates='eureka_server', lazy='dynamic', cascade='all, delete-orphan')

    # Индексы и ограничения
    __table_args__ = (
        db.UniqueConstraint('server_id', name='uq_eureka_server_per_server'),
        db.UniqueConstraint('eureka_host', 'eureka_port', name='uq_eureka_endpoint'),
        db.Index('idx_eureka_server_server', 'server_id'),
        db.Index('idx_eureka_server_active', 'is_active'),
        db.Index('idx_eureka_server_removed', 'removed_at'),
    )

    def mark_sync_success(self):
        """Отметить успешную синхронизацию"""
        self.last_sync = datetime.utcnow()
        self.last_error = None
        self.consecutive_failures = 0  # Сброс счетчика при успехе

    def mark_sync_failed(self, error_message):
        """Отметить неудачную синхронизацию"""
        self.last_sync = datetime.utcnow()
        self.last_error = error_message
        self.consecutive_failures = (self.consecutive_failures or 0) + 1  # Увеличение счетчика

    def soft_delete(self):
        """Мягкое удаление Eureka сервера"""
        self.removed_at = datetime.utcnow()

    def is_removed(self):
        """Проверка, удален ли сервер"""
        return self.removed_at is not None

    def restore(self):
        """Восстановление удаленного сервера"""
        self.removed_at = None

    def to_dict(self, include_applications=False):
        """Преобразование в словарь для API"""
        # Подсчет приложений (не удаленных)
        apps_count = self.applications.count()

        # Подсчет экземпляров
        instances_count = sum(app.instances_count or 0 for app in self.applications.all())

        result = {
            'id': self.id,
            'server_id': self.server_id,
            'server_name': self.server.name if self.server else None,
            'eureka_host': self.eureka_host,
            'eureka_port': self.eureka_port,
            'is_active': self.is_active,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'last_error': self.last_error,
            'consecutive_failures': self.consecutive_failures or 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'is_removed': self.is_removed(),
            'applications_count': apps_count,
            'instances_count': instances_count
        }

        if include_applications:
            result['applications'] = [app.to_dict() for app in self.applications.all()]

        return result

    def __repr__(self):
        return f'<EurekaServer {self.eureka_host}:{self.eureka_port} on {self.server.name if self.server else "?"}>'


class EurekaApplication(db.Model):
    """
    Представляет приложение, зарегистрированное в Eureka.
    Группирует экземпляры одного приложения.
    """
    __tablename__ = 'eureka_applications'

    id = db.Column(db.Integer, primary_key=True)
    eureka_server_id = db.Column(db.Integer, db.ForeignKey('eureka_servers.id', ondelete='CASCADE'), nullable=False)
    app_name = db.Column(db.String(255), nullable=False)  # Имя приложения в Eureka (SERVICE-NAME)

    # Статистика по экземплярам
    instances_count = db.Column(db.Integer, default=0)
    instances_up = db.Column(db.Integer, default=0)
    instances_down = db.Column(db.Integer, default=0)
    instances_paused = db.Column(db.Integer, default=0)

    # Error tracking for application data fetching
    last_fetch_status = db.Column(db.String(20), default='unknown')  # success, failed, unknown
    last_fetch_error = db.Column(db.Text, nullable=True)  # Error message if failed
    last_fetch_at = db.Column(db.DateTime, nullable=True)  # Last fetch attempt timestamp

    last_sync = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    eureka_server = db.relationship('EurekaServer', back_populates='applications')
    instances = db.relationship('EurekaInstance', back_populates='eureka_application', lazy='dynamic', cascade='all, delete-orphan')

    # Индексы
    __table_args__ = (
        db.UniqueConstraint('eureka_server_id', 'app_name', name='uq_eureka_app_per_server'),
        db.Index('idx_eureka_application_server', 'eureka_server_id'),
        db.Index('idx_eureka_application_name', 'app_name'),
    )

    def update_statistics(self):
        """Обновить статистику по экземплярам"""
        instances_list = self.instances.filter(EurekaInstance.removed_at.is_(None)).all()

        self.instances_count = len(instances_list)
        self.instances_up = sum(1 for i in instances_list if i.status == 'UP')
        self.instances_down = sum(1 for i in instances_list if i.status == 'DOWN')
        self.instances_paused = sum(1 for i in instances_list if i.status == 'PAUSED')
        self.last_sync = datetime.utcnow()
        self.updated_at = datetime.utcnow()

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

    def to_dict(self, include_instances=False):
        """Преобразование в словарь для API"""
        result = {
            'id': self.id,
            'eureka_server_id': self.eureka_server_id,
            'app_name': self.app_name,
            'instances_count': self.instances_count,
            'instances_up': self.instances_up,
            'instances_down': self.instances_down,
            'instances_paused': self.instances_paused,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'last_fetch_status': self.last_fetch_status,
            'last_fetch_error': self.last_fetch_error,
            'last_fetch_at': self.last_fetch_at.isoformat() if self.last_fetch_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

        if include_instances:
            result['instances'] = [i.to_dict() for i in self.instances.filter(EurekaInstance.removed_at.is_(None)).all()]

        return result

    def __repr__(self):
        return f'<EurekaApplication {self.app_name} ({self.instances_count} instances)>'


class EurekaInstance(db.Model):
    """
    Представляет экземпляр сервиса, зарегистрированный в Eureka.
    Может быть связан с приложением из AC платформы.
    """
    __tablename__ = 'eureka_instances'

    id = db.Column(db.Integer, primary_key=True)
    eureka_application_id = db.Column(db.Integer, db.ForeignKey('eureka_applications.id', ondelete='CASCADE'), nullable=False)

    # Идентификация экземпляра
    instance_id = db.Column(db.String(255), nullable=False, unique=True)  # Формат: IP:service-name:port
    ip_address = db.Column(db.String(45), nullable=False)  # IP адрес экземпляра
    port = db.Column(db.Integer, nullable=False)  # Порт экземпляра
    service_name = db.Column(db.String(255), nullable=False)  # Имя сервиса

    # Состояние экземпляра
    status = db.Column(db.String(50), nullable=False, default='UNKNOWN')  # UP, DOWN, PAUSED, STARTING, OUT_OF_SERVICE
    last_heartbeat = db.Column(db.DateTime, nullable=True)  # Последний heartbeat

    # Метаданные и URL'ы
    instance_metadata = db.Column(db.JSON, nullable=True)  # Метаданные (version, environment и т.д.)
    health_check_url = db.Column(db.String(512), nullable=True)
    home_page_url = db.Column(db.String(512), nullable=True)
    status_page_url = db.Column(db.String(512), nullable=True)

    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)  # Soft delete

    # Relationships
    eureka_application = db.relationship('EurekaApplication', back_populates='instances')
    status_history = db.relationship('EurekaInstanceStatusHistory', back_populates='eureka_instance', lazy='dynamic', cascade='all, delete-orphan')
    actions = db.relationship('EurekaInstanceAction', back_populates='eureka_instance', lazy='dynamic', cascade='all, delete-orphan')

    # Индексы
    __table_args__ = (
        db.Index('idx_eureka_instance_application', 'eureka_application_id'),
        db.Index('idx_eureka_instance_status', 'status'),
        db.Index('idx_eureka_instance_instance_id', 'instance_id'),
        db.Index('idx_eureka_instance_ip', 'ip_address'),
        db.Index('idx_eureka_instance_removed', 'removed_at'),
    )

    def update_status(self, new_status, reason='sync', changed_by='system'):
        """
        Обновить статус экземпляра и записать в историю.

        Args:
            new_status: Новый статус
            reason: Причина изменения
            changed_by: Кто/что изменило (system, user, health_check)
        """
        if self.status != new_status:
            # Создаем запись в истории
            history = EurekaInstanceStatusHistory(
                eureka_instance_id=self.id,
                old_status=self.status,
                new_status=new_status,
                reason=reason,
                changed_by=changed_by
            )
            db.session.add(history)

            # Обновляем статус
            self.status = new_status
            self.updated_at = datetime.utcnow()

    def soft_delete(self):
        """Мягкое удаление экземпляра"""
        self.removed_at = datetime.utcnow()

    def is_removed(self):
        """Проверка, удален ли экземпляр"""
        return self.removed_at is not None

    def restore(self):
        """Восстановление удаленного экземпляра"""
        self.removed_at = None

    def get_ip_port(self):
        """Получить IP:port в формате строки для маппинга"""
        return f"{self.ip_address}:{self.port}"

    def to_dict(self, include_application=True, include_history=False):
        """Преобразование в словарь для API"""
        # Получаем маппинг из унифицированной таблицы
        from app.models.application_mapping import ApplicationMapping, MappingType

        mapping = ApplicationMapping.query.filter_by(
            entity_type=MappingType.EUREKA_INSTANCE.value,
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
            'eureka_application_id': self.eureka_application_id,
            'eureka_server_id': self.eureka_application.eureka_server_id if self.eureka_application else None,
            'instance_id': self.instance_id,
            'ip_address': self.ip_address,
            'port': self.port,
            'service_name': self.service_name,
            'status': self.status,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'metadata': self.instance_metadata,
            'health_check_url': self.health_check_url,
            'home_page_url': self.home_page_url,
            'status_page_url': self.status_page_url,
            'application_id': application_id,
            'is_manual_mapping': is_manual_mapping,
            'mapped_by': mapped_by,
            'mapped_at': mapped_at.isoformat() if mapped_at else None,
            'mapping_notes': mapping_notes,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'is_removed': self.is_removed()
        }

        # Include EurekaApplication (with error tracking)
        if include_application and self.eureka_application:
            result['eureka_application'] = {
                'id': self.eureka_application.id,
                'app_name': self.eureka_application.app_name,
                'eureka_server_id': self.eureka_application.eureka_server_id,
                'last_fetch_status': self.eureka_application.last_fetch_status,
                'last_fetch_error': self.eureka_application.last_fetch_error,
                'last_fetch_at': self.eureka_application.last_fetch_at.isoformat() if self.eureka_application.last_fetch_at else None
            }

        # Include mapped AC Application if exists
        if include_application and application:
            result['application'] = {
                'id': application.id,
                'name': application.instance_name,
                'status': application.status,
                'eureka_url': application.eureka_url,
                'server_name': application.server.name if application.server else None
            }

        if include_history:
            history_list = self.status_history.order_by(EurekaInstanceStatusHistory.changed_at.desc()).limit(10).all()
            result['status_history'] = [h.to_dict() for h in history_list]

            actions_list = self.actions.order_by(EurekaInstanceAction.started_at.desc()).limit(10).all()
            result['recent_actions'] = [a.to_dict() for a in actions_list]

        return result

    def __repr__(self):
        return f'<EurekaInstance {self.instance_id} ({self.status})>'


class EurekaInstanceStatusHistory(db.Model):
    """
    История изменений статуса Eureka экземпляра.
    """
    __tablename__ = 'eureka_instance_status_history'

    id = db.Column(db.Integer, primary_key=True)
    eureka_instance_id = db.Column(db.Integer, db.ForeignKey('eureka_instances.id', ondelete='CASCADE'), nullable=False)
    old_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text, nullable=True)  # Причина изменения статуса
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    changed_by = db.Column(db.String(255), nullable=True)  # Кто/что изменило (system, user, health_check)

    # Relationships
    eureka_instance = db.relationship('EurekaInstance', back_populates='status_history')

    # Индексы
    __table_args__ = (
        db.Index('idx_eureka_status_history_instance', 'eureka_instance_id'),
        db.Index('idx_eureka_status_history_changed_at', 'changed_at'),
    )

    def to_dict(self):
        """Преобразование в словарь для API"""
        return {
            'id': self.id,
            'eureka_instance_id': self.eureka_instance_id,
            'old_status': self.old_status,
            'new_status': self.new_status,
            'reason': self.reason,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
            'changed_by': self.changed_by
        }

    def __repr__(self):
        return f'<EurekaInstanceStatusHistory {self.old_status} -> {self.new_status}>'


class EurekaInstanceAction(db.Model):
    """
    Журнал действий, выполненных над Eureka экземплярами.
    Записывает все операции: health_check, pause, shutdown, log_level_change.
    """
    __tablename__ = 'eureka_instance_actions'

    id = db.Column(db.Integer, primary_key=True)
    eureka_instance_id = db.Column(db.Integer, db.ForeignKey('eureka_instances.id', ondelete='CASCADE'), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)  # health_check, pause, shutdown, log_level_change
    action_params = db.Column(db.JSON, nullable=True)  # Параметры действия
    status = db.Column(db.String(50), nullable=False, default='pending')  # pending, in_progress, success, failed
    result = db.Column(db.Text, nullable=True)  # Результат выполнения
    error_message = db.Column(db.Text, nullable=True)  # Сообщение об ошибке
    user_id = db.Column(db.Integer, nullable=True)  # Кто инициировал (без FK, т.к. модели User нет)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    eureka_instance = db.relationship('EurekaInstance', back_populates='actions')

    # Индексы
    __table_args__ = (
        db.Index('idx_eureka_action_instance', 'eureka_instance_id'),
        db.Index('idx_eureka_action_type', 'action_type'),
        db.Index('idx_eureka_action_status', 'status'),
        db.Index('idx_eureka_action_started_at', 'started_at'),
    )

    def mark_in_progress(self):
        """Отметить начало выполнения"""
        self.status = 'in_progress'
        self.started_at = datetime.utcnow()

    def mark_success(self, result=None):
        """Отметить успешное выполнение"""
        self.status = 'success'
        self.result = result
        self.completed_at = datetime.utcnow()

    def mark_failed(self, error_message):
        """Отметить неудачное выполнение"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = datetime.utcnow()

    def to_dict(self):
        """Преобразование в словарь для API"""
        return {
            'id': self.id,
            'eureka_instance_id': self.eureka_instance_id,
            'action_type': self.action_type,
            'action_params': self.action_params,
            'status': self.status,
            'result': self.result,
            'error_message': self.error_message,
            'user_id': self.user_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

    def __repr__(self):
        return f'<EurekaInstanceAction {self.action_type} ({self.status})>'

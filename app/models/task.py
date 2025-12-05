# app/models/task.py
"""
Модель Task для персистентного хранения задач в БД.
Заменяет хранение в памяти для обеспечения сохранности при перезагрузке сервера.
"""
from app import db
from datetime import datetime


class Task(db.Model):
    """
    Модель задачи для выполнения операций над приложениями.

    Статусы:
        - pending: задача создана, ожидает выполнения
        - processing: задача выполняется
        - completed: задача успешно завершена
        - failed: задача завершена с ошибкой
    """
    __tablename__ = 'tasks'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    task_type = db.Column(db.String(32), nullable=False)  # start, stop, restart, update
    status = db.Column(db.String(32), default='pending', nullable=False)

    # Параметры задачи (distr_url, playbook_path, app_ids и т.д.)
    params = db.Column(db.JSON, default=dict)

    # Связи с сервером и приложением
    server_id = db.Column(
        db.Integer,
        db.ForeignKey('servers.id', ondelete='SET NULL'),
        nullable=True
    )
    instance_id = db.Column(
        db.Integer,
        db.ForeignKey('application_instances.id', ondelete='SET NULL'),
        nullable=True
    )

    # Временные метки
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Результаты выполнения
    result = db.Column(db.Text, nullable=True)  # Результат успешного выполнения
    error = db.Column(db.Text, nullable=True)   # Текст ошибки при неудаче

    # Прогресс выполнения (для отображения в UI)
    progress = db.Column(db.JSON, default=dict)

    # PID процесса для возможности отмены
    pid = db.Column(db.Integer, nullable=True)
    cancelled = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships
    server = db.relationship('Server', backref=db.backref('tasks', lazy='dynamic'))
    instance = db.relationship('ApplicationInstance', backref=db.backref('tasks', lazy='dynamic'))

    def __repr__(self):
        return f'<Task {self.id[:8]}... {self.task_type} - {self.status}>'

    @property
    def application_id(self):
        """Алиас для обратной совместимости"""
        return self.instance_id

    @application_id.setter
    def application_id(self, value):
        """Сеттер для обратной совместимости"""
        self.instance_id = value

    def to_dict(self):
        """Преобразование задачи в словарь для API"""
        return {
            'id': self.id,
            'task_type': self.task_type,
            'status': self.status,
            'params': self.params or {},
            'server_id': self.server_id,
            'instance_id': self.instance_id,
            'application_id': self.instance_id,  # обратная совместимость
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result,
            'error': self.error,
            'progress': self.progress or {},
            'pid': self.pid,
            'cancelled': self.cancelled,
            'can_cancel': self.can_cancel
        }

    @property
    def can_cancel(self):
        """
        Проверка возможности отмены задачи.

        Задачу можно отменить если:
        - Она в статусе 'pending' (ещё не начала выполнение)
        - Она в статусе 'processing' и имеет PID процесса
        - Она ещё не была отменена ранее
        """
        if self.cancelled:
            return False
        if self.status == 'pending':
            return True
        if self.status == 'processing' and self.pid is not None:
            return True
        return False

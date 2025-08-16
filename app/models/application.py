from app import db
from datetime import datetime
import re

class Application(db.Model):
    __tablename__ = 'applications'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    path = db.Column(db.String(256), nullable=True)
    log_path = db.Column(db.String(256), nullable=True)
    version = db.Column(db.String(64), nullable=True)
    distr_path = db.Column(db.String(256), nullable=True)
    
    # Дополнительные поля из JSON-шаблона
    container_id = db.Column(db.String(64), nullable=True)
    container_name = db.Column(db.String(64), nullable=True)
    eureka_url = db.Column(db.String(256), nullable=True)
    compose_project_dir = db.Column(db.String(256), nullable=True)
    
    ip = db.Column(db.String(15), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='offline')
    start_time = db.Column(db.DateTime, nullable=True)
    
    # Тип приложения (docker, eureka, site, service)
    app_type = db.Column(db.String(32), nullable=True)
    
    # Путь до плейбука для обновления
    update_playbook_path = db.Column(db.String(256), nullable=True)
    
    # Номер экземпляра приложения (0 если не указан)
    instance_number = db.Column(db.Integer, default=0, nullable=False)
    
    # Связи
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id', ondelete='CASCADE'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('application_groups.id', ondelete='SET NULL'), nullable=True)
    
    group = db.relationship('ApplicationGroup', backref='applications')

    # Индекс для оптимизации запросов
    __table_args__ = (
        db.Index('idx_app_group_instance', 'group_id', 'instance_number'),
        db.Index('idx_app_server_name', 'server_id', 'name'),
    )
    
    @staticmethod
    def parse_application_name(app_name):
        """
        Парсит имя приложения и возвращает имя группы и номер экземпляра.
        Логика: {имя_приложения}_{номер_экземпляра}
        В имени приложения может быть знак "-", номер экземпляра определяется по последнему "_" и цифре.
        
        Args:
            app_name: Полное имя приложения
            
        Returns:
            tuple: (group_name, instance_number)
        """
        if not app_name:
            return None, 0
        
        # Паттерн: ищем последний "_" за которым следуют только цифры до конца строки
        pattern = r'^(.+?)_(\d+)$'
        match = re.match(pattern, app_name)
        
        if match:
            group_name = match.group(1)
            instance_number = int(match.group(2))
            return group_name, instance_number
        else:
            # Если нет номера экземпляра, считаем что это единственный экземпляр
            return app_name, 0
    
    def determine_group(self):
        """
        Определяет группу приложения на основе его имени.
        Создает новую группу если необходимо.
        """
        # Если группа уже определена, не проверяем повторно
        if self.group_id:
            return self.group
        
        group_name, instance_number = self.parse_application_name(self.name)
        
        if not group_name:
            return None
        
        # Ищем существующую группу
        from app.models.application_group import ApplicationGroup
        from app import db
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            # Создаем новую группу
            group = ApplicationGroup(name=group_name)
            db.session.add(group)
            db.session.flush()  # Чтобы получить ID группы
        
        # Присваиваем группу и номер экземпляра
        self.group_id = group.id
        self.instance_number = instance_number
        
        return group
    
    @property
    def application_group(self):
        """Получить группу приложения через экземпляр"""
        if hasattr(self, 'instance') and self.instance and self.instance.group:
            return self.instance.group
        return None

    @property
    def group_name(self):
        """Получить имя группы приложения"""
        # Сначала пытаемся через прямой relationship
        if self.group:
            return self.group.name
        # Потом через instance (для обратной совместимости)
        if hasattr(self, 'instance') and self.instance and self.instance.group:
            return self.instance.group.name
        # Fallback на парсинг имени
        parts = self.name.split('_')
        if len(parts) > 1 and parts[-1].isdigit():
            return '_'.join(parts[:-1])
        return self.name

    @property
    def instance_number_prop(self):
        """Получить номер экземпляра"""
        if hasattr(self, 'instance') and self.instance:
            return self.instance.instance_number
        # Fallback на старую логику для обратной совместимости
        parts = self.name.split('_')
        if len(parts) > 1 and parts[-1].isdigit():
            return int(parts[-1])
        return 0

    @property
    def is_grouped(self):
        """Проверка, определена ли группа для приложения"""
        return hasattr(self, 'instance') and self.instance and self.instance.group_resolved
    
    @property
    def effective_artifact_url(self):
        """Получить эффективный URL артефактов через экземпляр"""
        if hasattr(self, 'instance') and self.instance:
            return self.instance.get_effective_artifact_url()
        return None

    @property
    def effective_artifact_extension(self):
        """Получить эффективное расширение артефактов через экземпляр"""
        if hasattr(self, 'instance') and self.instance:
            return self.instance.get_effective_artifact_extension()
        return None    

    @property
    def effective_playbook_path(self):
        """Получить эффективный путь к playbook через экземпляр"""
        if hasattr(self, 'instance') and self.instance:
            return self.instance.get_effective_playbook_path()
        from app.config import Config
        return self.update_playbook_path or getattr(Config, 'DEFAULT_UPDATE_PLAYBOOK', '/etc/ansible/update-app.yml')

    @property
    def is_disabled(self):
        """Проверить, отключено ли приложение"""
        if hasattr(self, 'instance') and self.instance:
            return self.instance.is_disabled()
        return False

    @property
    def is_in_maintenance(self):
        """Проверить, находится ли приложение в режиме обслуживания"""
        if hasattr(self, 'instance') and self.instance:
            return self.instance.is_in_maintenance()
        return False

    def get_setting(self, key, default=None):
        """Получить настройку приложения через экземпляр"""
        if hasattr(self, 'instance') and self.instance:
            return self.instance.get_setting(key, default)
        return default

    def get_sibling_instances(self):
        """Получить другие экземпляры из той же группы"""
        if not self.application_group:
            return []
        
        from app.models.application_group import ApplicationInstance
        
        siblings = ApplicationInstance.query.filter(
            ApplicationInstance.group_id == self.application_group.id,
            ApplicationInstance.id != self.instance.id if self.instance else None
        ).all()
        
        return [s.application for s in siblings if s.application]

    def get_same_server_siblings(self):
        """Получить экземпляры из той же группы на том же сервере"""
        siblings = self.get_sibling_instances()
        return [s for s in siblings if s.server_id == self.server_id]

    def to_dict(self, include_group=False, include_settings=False):
        """Преобразование в словарь для API"""
        result = {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'log_path': self.log_path,
            'version': self.version,
            'distr_path': self.distr_path,
            'container_id': self.container_id,
            'container_name': self.container_name,
            'eureka_url': self.eureka_url,
            'compose_project_dir': self.compose_project_dir,
            'ip': self.ip,
            'port': self.port,
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'app_type': self.app_type,
            'server_id': self.server_id,
            'server_name': self.server.name if self.server else None
        }
        
        if include_group:
            result['group'] = {
                'name': self.group_name,
                'instance_number': self.instance_number,
                'is_grouped': self.is_grouped
            }
            if self.application_group:
                result['group']['id'] = self.application_group.id
        
        if include_settings and self.instance:
            result['settings'] = {
                'is_disabled': self.is_disabled,
                'is_maintenance': self.is_in_maintenance,
                'priority': self.instance.get_priority(),
                'tags': self.instance.tags or [],
                'effective_playbook': self.effective_playbook_path
            }
        
        return result
    
    @property
    def full_name(self):
        """Возвращает полное имя приложения с номером экземпляра"""
        if self.instance_number > 0:
            return f"{self.group_name}_{self.instance_number}"
        return self.group_name
    
    def __repr__(self):
        return f'<Application {self.name} ({self.status})>'
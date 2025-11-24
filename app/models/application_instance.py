# app/models/application_instance.py
# РЕФАКТОРИНГ - переименована из application.py
# Теперь это действительно экземпляры приложений на серверах

from app import db
from datetime import datetime
from sqlalchemy import event
import re

class ApplicationInstance(db.Model):
    """
    Экземпляр приложения на сервере.

    Представляет реальный экземпляр приложения, запущенный на конкретном сервере.
    Связан со справочником (ApplicationCatalog) и группой управления (ApplicationGroup).
    """
    __tablename__ = 'application_instances'

    id = db.Column(db.Integer, primary_key=True)

    # Связи с другими таблицами
    catalog_id = db.Column(db.Integer, db.ForeignKey('application_catalog.id', ondelete='SET NULL'), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('application_groups.id', ondelete='SET NULL'), nullable=True)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id', ondelete='CASCADE'), nullable=False)

    # Идентификация экземпляра
    instance_name = db.Column(db.String(128), nullable=False)  # Полное имя: best-app_1, new-app_2
    instance_number = db.Column(db.Integer, default=0, nullable=False)  # Номер экземпляра: 1, 2, 3
    app_type = db.Column(db.String(32), nullable=False)  # docker, eureka, site, service

    # Состояние
    status = db.Column(db.String(32), default='unknown')  # online, offline, unknown, starting, stopping, no_data
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    # Данные от агента (общие)
    path = db.Column(db.String(255), nullable=True)
    log_path = db.Column(db.String(255), nullable=True)
    version = db.Column(db.String(128), nullable=True)
    distr_path = db.Column(db.String(255), nullable=True)

    # Docker-специфичные поля
    container_id = db.Column(db.String(128), nullable=True)
    container_name = db.Column(db.String(128), nullable=True)
    compose_project_dir = db.Column(db.String(255), nullable=True)
    image = db.Column(db.String(255), nullable=True)  # Docker образ
    tag = db.Column(db.String(64), nullable=True)  # Версия образа
    eureka_registered = db.Column(db.Boolean, default=False, nullable=True)  # Флаг регистрации в Eureka

    # Eureka-специфичные поля
    eureka_url = db.Column(db.String(255), nullable=True)

    # Сетевые параметры
    ip = db.Column(db.String(45), nullable=True)  # Поддержка IPv6
    port = db.Column(db.Integer, nullable=True)

    # Процесс
    pid = db.Column(db.Integer, nullable=True)
    start_time = db.Column(db.DateTime, nullable=True)

    # Кастомизация (переопределение настроек группы/каталога)
    custom_playbook_path = db.Column(db.String(255), nullable=True)
    custom_artifact_url = db.Column(db.String(512), nullable=True)
    custom_artifact_extension = db.Column(db.String(32), nullable=True)

    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)  # Soft delete

    # Кэш тегов для быстрой фильтрации
    tags_cache = db.Column(db.String(512), nullable=True)

    # Relationships
    catalog = db.relationship('ApplicationCatalog', back_populates='instances')
    group = db.relationship('ApplicationGroup', back_populates='instances')
    server = db.relationship('Server', back_populates='instances')
    events = db.relationship('Event', back_populates='instance', cascade='all, delete-orphan')

    # Индексы и ограничения
    __table_args__ = (
        db.UniqueConstraint('server_id', 'instance_name', 'app_type', name='unique_instance_per_server'),
        db.Index('idx_instance_catalog', 'catalog_id'),
        db.Index('idx_instance_group', 'group_id'),
        db.Index('idx_instance_server', 'server_id'),
        db.Index('idx_instance_status', 'status'),
        db.Index('idx_instance_deleted', 'deleted_at'),
        db.Index('idx_instance_name', 'instance_name'),
        db.Index('idx_instance_type', 'app_type'),
    )

    @staticmethod
    def parse_application_name(app_name):
        """
        Парсит имя приложения и возвращает базовое имя и номер экземпляра.

        Логика: {базовое_имя}_{номер_экземпляра}
        В имени может быть знак "-", номер экземпляра определяется по последнему "_" и цифре.

        Args:
            app_name: Полное имя приложения (например, best-app_1, new-app_2)

        Returns:
            tuple: (базовое_имя, номер_экземпляра)

        Examples:
            >>> ApplicationInstance.parse_application_name('best-app_1')
            ('best-app', 1)
            >>> ApplicationInstance.parse_application_name('new-app_2')
            ('new-app', 2)
            >>> ApplicationInstance.parse_application_name('standalone-app')
            ('standalone-app', 0)
        """
        if not app_name:
            return None, 0

        # Паттерн: ищем последний "_" за которым следуют только цифры до конца строки
        pattern = r'^(.+?)_(\d+)$'
        match = re.match(pattern, app_name)

        if match:
            base_name = match.group(1)
            instance_number = int(match.group(2))
            return base_name, instance_number
        else:
            # Если нет номера экземпляра, считаем что это единственный экземпляр
            return app_name, 0

    @property
    def name(self):
        """Алиас для обратной совместимости с кодом, использующим app.name"""
        return self.instance_name

    @property
    def base_name(self):
        """Базовое имя приложения без номера экземпляра"""
        if self.catalog:
            return self.catalog.name
        # Парсим имя экземпляра
        parsed_name, _ = self.parse_application_name(self.instance_name)
        return parsed_name or self.instance_name

    @property
    def update_playbook_path(self):
        """Алиас для обратной совместимости - возвращает эффективный путь к playbook"""
        return self.get_effective_playbook_path()

    def get_effective_playbook_path(self):
        """
        Получить эффективный путь к playbook с учетом приоритетов:
        1. Индивидуальный путь экземпляра (custom_playbook_path)
        2. Групповой путь (group.update_playbook_path)
        3. Путь из каталога (catalog.default_playbook_path)
        4. Дефолтный путь из конфига

        Returns:
            str: Путь к playbook
        """
        from app.config import Config

        if self.custom_playbook_path:
            return self.custom_playbook_path

        if self.group and self.group.update_playbook_path:
            return self.group.update_playbook_path

        if self.catalog and self.catalog.default_playbook_path:
            return self.catalog.default_playbook_path

        return getattr(Config, 'DEFAULT_UPDATE_PLAYBOOK', '/etc/ansible/update-app.yml')

    def get_effective_artifact_url(self):
        """
        Получить эффективный URL артефактов с учетом приоритетов:
        1. Индивидуальный URL экземпляра
        2. URL группы
        3. URL каталога

        Returns:
            str: URL артефактов или None
        """
        if self.custom_artifact_url:
            return self.custom_artifact_url

        if self.group and self.group.artifact_list_url:
            return self.group.artifact_list_url

        if self.catalog and self.catalog.default_artifact_url:
            return self.catalog.default_artifact_url

        return None

    def get_effective_artifact_extension(self):
        """
        Получить эффективное расширение артефактов с учетом приоритетов:
        1. Индивидуальное расширение экземпляра
        2. Расширение группы
        3. Расширение каталога

        Returns:
            str: Расширение файла или None
        """
        if self.custom_artifact_extension:
            return self.custom_artifact_extension

        if self.group and self.group.artifact_extension:
            return self.group.artifact_extension

        if self.catalog and self.catalog.default_artifact_extension:
            return self.catalog.default_artifact_extension

        return None

    def has_custom_settings(self):
        """Проверка наличия кастомных настроек"""
        return bool(
            self.custom_playbook_path or
            self.custom_artifact_url or
            self.custom_artifact_extension
        )

    def clear_custom_settings(self):
        """Очистить все кастомные настройки"""
        self.custom_playbook_path = None
        self.custom_artifact_url = None
        self.custom_artifact_extension = None

    def add_tag(self, tag_name, user=None):
        """Добавить тег к экземпляру"""
        from app.models.tag import Tag, TagHistory

        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name, display_name=tag_name.title())
            db.session.add(tag)

        if tag not in self.tags.all():
            self.tags.append(tag)
            self._update_tags_cache()

            # Запись в историю
            history = TagHistory(
                entity_type='instance',
                entity_id=self.id,
                tag_id=tag.id,
                action='assigned',
                changed_by=user,
                details={'tag_name': tag_name}
            )
            db.session.add(history)

        return tag

    def remove_tag(self, tag_name, user=None):
        """Удалить тег у экземпляра"""
        from app.models.tag import Tag, TagHistory

        tag = Tag.query.filter_by(name=tag_name).first()
        if tag and tag in self.tags.all():
            self.tags.remove(tag)
            self._update_tags_cache()

            # Запись в историю
            history = TagHistory(
                entity_type='instance',
                entity_id=self.id,
                tag_id=tag.id,
                action='removed',
                changed_by=user
            )
            db.session.add(history)

        return tag

    def get_tag_names(self):
        """Получить список имен тегов"""
        return [t.name for t in self.tags.all()]

    def has_tags(self, tag_names):
        """Проверить наличие всех указанных тегов"""
        my_tags = set(self.get_tag_names())
        return all(t in my_tags for t in tag_names)

    def _update_tags_cache(self):
        """Обновить кэш тегов"""
        self.tags_cache = ','.join(sorted(self.get_tag_names()))

    def to_dict(self, include_group=False, include_settings=False, include_tags=False):
        """
        Преобразование в словарь для API.

        Args:
            include_group: Включить информацию о группе
            include_settings: Включить эффективные настройки

        Returns:
            dict: Словарь с данными экземпляра
        """
        result = {
            'id': self.id,
            'instance_name': self.instance_name,
            'name': self.instance_name,  # Для обратной совместимости
            'base_name': self.base_name,
            'instance_number': self.instance_number,
            'app_type': self.app_type,
            'status': self.status,
            'path': self.path,
            'log_path': self.log_path,
            'version': self.version,
            'distr_path': self.distr_path,
            'container_id': self.container_id,
            'container_name': self.container_name,
            'compose_project_dir': self.compose_project_dir,
            'image': self.image,
            'tag': self.tag,
            'eureka_registered': self.eureka_registered,
            'eureka_url': self.eureka_url,
            'ip': self.ip,
            'port': self.port,
            'pid': self.pid,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'server_id': self.server_id,
            'server_name': self.server.name if self.server else None,
            'catalog_id': self.catalog_id,
            'catalog_name': self.catalog.name if self.catalog else None,
            'group_id': self.group_id,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

        if include_group and self.group:
            result['group'] = {
                'id': self.group.id,
                'name': self.group.name,
                'description': self.group.description
            }

        if include_settings:
            result['settings'] = {
                'effective_playbook': self.get_effective_playbook_path(),
                'effective_artifact_url': self.get_effective_artifact_url(),
                'effective_artifact_extension': self.get_effective_artifact_extension(),
                'has_custom_settings': self.has_custom_settings(),
                'custom_playbook_path': self.custom_playbook_path,
                'custom_artifact_url': self.custom_artifact_url,
                'custom_artifact_extension': self.custom_artifact_extension
            }

        if include_tags:
            result['tags'] = [t.to_dict() for t in self.tags.all()]

        return result

    # Свойства для обратной совместимости со старым кодом
    @property
    def group_name(self):
        """Получить имя группы приложения"""
        if self.group:
            return self.group.name
        return self.base_name

    @property
    def effective_playbook_path(self):
        """Property версия get_effective_playbook_path для обратной совместимости"""
        return self.get_effective_playbook_path()

    @property
    def effective_artifact_url(self):
        """Property версия get_effective_artifact_url для обратной совместимости"""
        return self.get_effective_artifact_url()

    @property
    def effective_artifact_extension(self):
        """Property версия get_effective_artifact_extension для обратной совместимости"""
        return self.get_effective_artifact_extension()

    def __repr__(self):
        group_name = self.group.name if self.group else "no-group"
        return f'<ApplicationInstance {self.instance_name} ({self.app_type}, group: {group_name}, status: {self.status})>'


# Автоматическое обновление updated_at и last_seen при изменении записи
@event.listens_for(ApplicationInstance, 'before_update')
def update_instance_timestamp(mapper, connection, target):
    target.updated_at = datetime.utcnow()
    if target.status == 'online':
        target.last_seen = datetime.utcnow()

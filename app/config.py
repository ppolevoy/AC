# app/config.py
import os
from datetime import timedelta

def get_database_url():
    """Получение URL базы данных из переменных окружения"""
    # Проверяем наличие полной строки подключения
    uri = os.environ.get('DATABASE_URL')
    if uri:
        # Заменяем postgres:// на postgresql:// если нужно
        if uri.startswith('postgres://'):
            uri = uri.replace('postgres://', 'postgresql://', 1)
        return uri
        
    # Получаем отдельные параметры подключения
    host = os.environ.get('POSTGRES_HOST', '192.168.8.46')
    port = os.environ.get('POSTGRES_PORT', '5417')
    user = os.environ.get('POSTGRES_USER', 'fakadm')
    password = os.environ.get('POSTGRES_PASSWORD', 'fakadm')
    db_name = os.environ.get('POSTGRES_DB', 'appcontrol')
    
    # Формируем строку подключения
    if password:
        uri = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    else:
        uri = f"postgresql://{user}@{host}:{port}/{db_name}"
    
    return uri

class Config:
    # Базовая конфигурация
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'сложный-ключ-для-разработки'
    
    # Настройки базы данных PostgreSQL
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Настройки интервалов опроса серверов 
    POLLING_INTERVAL = int(os.environ.get('POLLING_INTERVAL') or 60)  # в секундах
    CONNECTION_TIMEOUT = int(os.environ.get('CONNECTION_TIMEOUT') or 5)  # в секундах
    
    # Пути для логов
    LOG_DIR = os.environ.get('LOG_DIR') or 'logs'
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    
    # Настройки для хранения информации о серверах и приложениях
    # MAX_EVENTS_PER_APP = int(os.environ.get('MAX_EVENTS_PER_APP') or 100)  # NOT USED
    CLEAN_EVENTS_OLDER_THAN = int(os.environ.get('CLEAN_EVENTS_OLDER_THAN') or 30)  # в днях
    CLEAN_TASKS_OLDER_THAN = int(os.environ.get('CLEAN_TASKS_OLDER_THAN') or 365)  # в днях

    # Настройки Ansible
    DEFAULT_UPDATE_PLAYBOOK = os.environ.get('DEFAULT_UPDATE_PLAYBOOK') or '/etc/ansible/update-app.yml'
    APP_CONTROL_PLAYBOOK = os.environ.get('APP_CONTROL_PLAYBOOK') or '/etc/ansible/app_control.yml'

    # Настройки для Orchestrator Playbooks
    # Используется тот же ANSIBLE_PATH что и для обычных playbook-ов
    ORCHESTRATOR_SCAN_PATTERN = os.environ.get('ORCHESTRATOR_SCAN_PATTERN') or '*orchestrator*.yml'

    # Включение SSH-режима для Ansible
    USE_SSH_ANSIBLE = os.environ.get('USE_SSH_ANSIBLE', 'true').lower() == 'true' 
    # Настройки SSH для Ansible
    SSH_HOST = os.environ.get('SSH_HOST') or '192.168.8.46'
    SSH_USER = os.environ.get('SSH_USER') or 'ansible'
    SSH_PORT = int(os.environ.get('SSH_PORT') or 22)
    SSH_KEY_FILE = os.environ.get('SSH_KEY_FILE') or '/app/.ssh/id_rsa'
    SSH_KNOWN_HOSTS_FILE = os.environ.get('SSH_KNOWN_HOSTS_FILE') or '/app/.ssh/known_hosts'
    SSH_CONNECTION_TIMEOUT = int(os.environ.get('SSH_CONNECTION_TIMEOUT') or 30)
    SSH_COMMAND_TIMEOUT = int(os.environ.get('SSH_COMMAND_TIMEOUT') or 300)
    ANSIBLE_PATH = os.environ.get('ANSIBLE_PATH') or '/etc/ansible'

    MAX_ARTIFACTS_DISPLAY = int(os.environ.get('MAX_ARTIFACTS_DISPLAY') or 120)
    INCLUDE_SNAPSHOT_VERSIONS = os.environ.get('INCLUDE_SNAPSHOT_VERSIONS', 'true').lower() == 'true'

    # Настройки для Docker
    DOCKER_UPDATE_PLAYBOOK = os.environ.get('DOCKER_UPDATE_PLAYBOOK', '/etc/ansible/docker_update_playbook.yaml')

    # Плейбук для обновления в ночной рестарт
    NIGHT_RESTART_PLAYBOOK = os.environ.get('NIGHT_RESTART_PLAYBOOK') or '/etc/ansible/night_restart_update.yaml'
    # DOCKER_REGISTRY_URL = os.environ.get('DOCKER_REGISTRY_URL', 'nexus.bankplus.ru')  # NOT USED
    # DOCKER_REGISTRY_PATH = os.environ.get('DOCKER_REGISTRY_PATH', 'repository/docker-local')  # NOT USED

    # Настройки для отображения версий
    # MAX_DOCKER_IMAGES_DISPLAY = int(os.environ.get('MAX_DOCKER_IMAGES_DISPLAY', '30'))  # NOT USED
    # INCLUDE_DEV_IMAGES = os.environ.get('INCLUDE_DEV_IMAGES', 'false').lower() == 'true'  # NOT USED
    # INCLUDE_SNAPSHOT_IMAGES = os.environ.get('INCLUDE_SNAPSHOT_IMAGES', 'false').lower() == 'true'  # NOT USED

    # Настройки HAProxy интеграции (Фаза 1: Мониторинг)
    HAPROXY_ENABLED = os.environ.get('HAPROXY_ENABLED', 'true').lower() == 'true'
    HAPROXY_POLLING_INTERVAL = int(os.environ.get('HAPROXY_POLLING_INTERVAL', '60'))  # секунды
    HAPROXY_CACHE_TTL = int(os.environ.get('HAPROXY_CACHE_TTL', '30'))  # секунды
    # HAPROXY_HISTORY_RETENTION_DAYS = int(os.environ.get('HAPROXY_HISTORY_RETENTION_DAYS', '30'))  # NOT USED
    # HAPROXY_DEFAULT_INSTANCE_NAME = os.environ.get('HAPROXY_DEFAULT_INSTANCE_NAME', 'default')  # NOT USED
    HAPROXY_REQUEST_TIMEOUT = int(os.environ.get('HAPROXY_REQUEST_TIMEOUT', '10'))  # секунды
    HAPROXY_MAX_RETRIES = int(os.environ.get('HAPROXY_MAX_RETRIES', '3'))  # количество попыток

    # Настройки Eureka интеграции
    EUREKA_ENABLED = os.environ.get('EUREKA_ENABLED', 'true').lower() == 'true'

    # Параметры подключения
    EUREKA_REQUEST_TIMEOUT = int(os.environ.get('EUREKA_REQUEST_TIMEOUT', '10'))  # секунды
    EUREKA_MAX_RETRIES = int(os.environ.get('EUREKA_MAX_RETRIES', '3'))  # количество попыток
    EUREKA_RETRY_DELAY = int(os.environ.get('EUREKA_RETRY_DELAY', '1'))  # секунды задержки между попытками

    # Интервалы синхронизации
    EUREKA_POLLING_INTERVAL = int(os.environ.get('EUREKA_POLLING_INTERVAL', '60'))  # секунды опроса
    # EUREKA_HEALTH_CHECK_INTERVAL = int(os.environ.get('EUREKA_HEALTH_CHECK_INTERVAL', '30'))  # NOT USED

    # Кэширование
    EUREKA_CACHE_TTL = int(os.environ.get('EUREKA_CACHE_TTL', '30'))  # секунды
    # EUREKA_CACHE_MAX_SIZE = int(os.environ.get('EUREKA_CACHE_MAX_SIZE', '1000'))  # NOT USED

    # Хранение истории
    # EUREKA_HISTORY_RETENTION_DAYS = int(os.environ.get('EUREKA_HISTORY_RETENTION_DAYS', '30'))  # NOT USED
    # EUREKA_MAX_HISTORY_RECORDS = int(os.environ.get('EUREKA_MAX_HISTORY_RECORDS', '10000'))  # NOT USED

    # Настройки рассылки отчётов по email
    REPORT_EMAIL_ENABLED = os.environ.get('REPORT_EMAIL_ENABLED', 'true').lower() == 'true'
    REPORT_EMAIL_FROM = os.environ.get('REPORT_EMAIL_FROM', 'ac-reports@localhost')
    REPORT_EMAIL_SUBJECT_PREFIX = os.environ.get('REPORT_EMAIL_SUBJECT_PREFIX', '[AC Report]')
    # REPORT_DEFAULT_RECIPIENTS = os.environ.get('REPORT_DEFAULT_RECIPIENTS', '')  # NOT USED
    # SMTP Configuration
    SMTP_HOST = os.environ.get('SMTP_HOST', 'localhost')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '25'))
    SMTP_TIMEOUT = int(os.environ.get('SMTP_TIMEOUT', '30'))
    SMTP_MAX_RETRIES = int(os.environ.get('SMTP_MAX_RETRIES', '3'))

    # Настройки системных тегов
    SYSTEM_TAGS_ENABLED = os.environ.get('SYSTEM_TAGS_ENABLED', 'true').lower() == 'true'

    # Автоназначение тегов по типам
    AUTO_TAG_HAPROXY_ENABLED = os.environ.get('AUTO_TAG_HAPROXY_ENABLED', 'true').lower() == 'true'
    AUTO_TAG_EUREKA_ENABLED = os.environ.get('AUTO_TAG_EUREKA_ENABLED', 'true').lower() == 'true'
    AUTO_TAG_DOCKER_ENABLED = os.environ.get('AUTO_TAG_DOCKER_ENABLED', 'true').lower() == 'true'
    AUTO_TAG_SMF_ENABLED = os.environ.get('AUTO_TAG_SMF_ENABLED', 'false').lower() == 'true'
    AUTO_TAG_SYSCTL_ENABLED = os.environ.get('AUTO_TAG_SYSCTL_ENABLED', 'false').lower() == 'true'

    # Автоматическое удаление offline-приложений
    APP_OFFLINE_REMOVAL_DAYS = int(os.environ.get('APP_OFFLINE_REMOVAL_DAYS', '7'))  # Soft delete через N дней offline
    APP_OFFLINE_WARNING_DAYS_BEFORE = 3  # За сколько дней до удаления ставить тег (тег на 4-й день при default=7)
    APP_HARD_DELETE_DAYS = int(os.environ.get('APP_HARD_DELETE_DAYS', '30'))  # Физическое удаление через N дней после soft delete
    APP_REMOVAL_PROTECTED_TAGS = ['ver.lock', 'status.lock', 'disable']  # Теги, защищающие от автоудаления

    @staticmethod
    def init_app(app):
        # Создание директории для логов, если её нет
        if not os.path.exists(Config.LOG_DIR):
            os.makedirs(Config.LOG_DIR)
        # Создание директории для SSH-ключей, если её нет
        ssh_dir = os.path.dirname(Config.SSH_KEY_FILE)
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir, mode=0o700)


class OrchestratorDefaults:
    """
    Константы для оркестраторов.
    Устраняет магические числа в коде обработки orchestrator playbooks.
    """
    # Время ожидания после drain в секундах (5 минут по умолчанию)
    DRAIN_DELAY_SECONDS = int(os.environ.get('ORCHESTRATOR_DRAIN_DELAY_SECONDS', '300'))

    # Количество строк для парсинга метаданных из playbook файла
    METADATA_SCAN_LINES = int(os.environ.get('ORCHESTRATOR_METADATA_SCAN_LINES', '150'))

    # Максимум символов для хранения raw metadata
    METADATA_MAX_CHARS = int(os.environ.get('ORCHESTRATOR_METADATA_MAX_CHARS', '500'))

    # Максимальная длина имени orchestrator playbook
    NAME_MAX_LENGTH = int(os.environ.get('ORCHESTRATOR_NAME_MAX_LENGTH', '128'))

    # Время ожидания после обновления в секундах (по умолчанию)
    # WAIT_AFTER_UPDATE_SECONDS = int(os.environ.get('ORCHESTRATOR_WAIT_AFTER_UPDATE', '60'))  # NOT USED


class TaskQueueDefaults:
    """
    Константы для очереди задач.
    Устраняет магические числа в коде TaskQueue.
    """
    # Таймаут на остановку потока обработки задач (секунды)
    SHUTDOWN_TIMEOUT = int(os.environ.get('TASK_QUEUE_SHUTDOWN_TIMEOUT', '30'))

    # Срок хранения истории задач (дни)
    HISTORY_RETENTION_DAYS = int(os.environ.get('TASK_QUEUE_HISTORY_RETENTION_DAYS', '365'))

    # Интервал проверки очереди (секунды)
    # POLL_INTERVAL = int(os.environ.get('TASK_QUEUE_POLL_INTERVAL', '1'))  # NOT USED


class DevelopmentConfig(Config):
    DEBUG = True
    # Используем настройки из базового класса

class ProductionConfig(Config):
    DEBUG = False
    
    # Более строгие настройки безопасности
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True

# Конфигурация по умолчанию
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

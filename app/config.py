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
    
    # Пути для шаблонов и статических файлов
    TEMPLATES_DIR = 'templates'
    STATIC_DIR = 'static'
    
    # Настройки для хранения информации о серверах и приложениях
    MAX_EVENTS_PER_APP = int(os.environ.get('MAX_EVENTS_PER_APP') or 100)
    CLEAN_EVENTS_OLDER_THAN = int(os.environ.get('CLEAN_EVENTS_OLDER_THAN') or 30)  # в днях
    
    # Настройки для группировки приложений
    APP_GROUP_PATTERN = r'(.+)_(\d+)$'  # Шаблон для определения группы и номера экземпляра

    # Настройки Ansible
    ANSIBLE_DIR = os.environ.get('ANSIBLE_DIR') or '/etc/ansible'
    DEFAULT_UPDATE_PLAYBOOK = os.environ.get('DEFAULT_UPDATE_PLAYBOOK') or '/etc/ansible/update-app.yml'
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

    MAX_ARTIFACTS_DISPLAY = int(os.environ.get('MAX_ARTIFACTS_DISPLAY') or 20)
    INCLUDE_SNAPSHOT_VERSIONS = os.environ.get('INCLUDE_SNAPSHOT_VERSIONS', 'true').lower() == 'true'

    # Настройки для Docker
    DOCKER_UPDATE_PLAYBOOK = os.environ.get('DOCKER_UPDATE_PLAYBOOK', '/etc/ansible/docker_update_playbook.yaml')
    DOCKER_REGISTRY_URL = os.environ.get('DOCKER_REGISTRY_URL', 'nexus.bankplus.ru')
    DOCKER_REGISTRY_PATH = os.environ.get('DOCKER_REGISTRY_PATH', 'repository/docker-local')
    
    # Настройки для отображения версий
    MAX_DOCKER_IMAGES_DISPLAY = int(os.environ.get('MAX_DOCKER_IMAGES_DISPLAY', '30'))
    INCLUDE_DEV_IMAGES = os.environ.get('INCLUDE_DEV_IMAGES', 'false').lower() == 'true'
    INCLUDE_SNAPSHOT_IMAGES = os.environ.get('INCLUDE_SNAPSHOT_IMAGES', 'false').lower() == 'true'    
    
    @staticmethod
    def init_app(app):
        # Создание директории для логов, если её нет
        if not os.path.exists(Config.LOG_DIR):
            os.makedirs(Config.LOG_DIR)
        # Создание директории для SSH-ключей, если её нет
        ssh_dir = os.path.dirname(Config.SSH_KEY_FILE)
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir, mode=0o700)


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

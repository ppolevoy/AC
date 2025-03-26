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
    user = os.environ.get('POSTGRES_USER', 'admin')
    password = os.environ.get('POSTGRES_PASSWORD', 'pwd')
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
    
    # Настройки Ansible
    ANSIBLE_DIR = os.environ.get('ANSIBLE_DIR') or '/etc/ansible'
    DEFAULT_UPDATE_PLAYBOOK = os.environ.get('DEFAULT_UPDATE_PLAYBOOK') or '/etc/ansible/update-app.yml'
    
    # Пути для шаблонов и статических файлов
    TEMPLATES_DIR = 'templates'
    STATIC_DIR = 'static'
    
    # Настройки для хранения информации о серверах и приложениях
    MAX_EVENTS_PER_APP = int(os.environ.get('MAX_EVENTS_PER_APP') or 100)
    CLEAN_EVENTS_OLDER_THAN = int(os.environ.get('CLEAN_EVENTS_OLDER_THAN') or 30)  # в днях
    
    # Настройки для группировки приложений
    APP_GROUP_PATTERN = r'(.+)_(\d+)$'  # Шаблон для определения группы и номера экземпляра
    
    @staticmethod
    def init_app(app):
        # Создание директории для логов, если её нет
        if not os.path.exists(Config.LOG_DIR):
            os.makedirs(Config.LOG_DIR)

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

# app/__init__.py
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from app.config import config

# Создаем экземпляры расширений
db = SQLAlchemy()
migrate = Migrate()

def create_app(config_name=None):
    if not config_name:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Инициализация расширений
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Настройка логирования
    setup_logging(app)
    
    # Регистрация схем
    with app.app_context():
        # Импортируем модели, чтобы SQLAlchemy их зарегистрировал
        from app.models.server import Server
        from app.models.application import Application
        from app.models.application_group import ApplicationGroup
        from app.models.event import Event
    
    # Регистрация маршрутов API
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Регистрация основных маршрутов для веб-интерфейса
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

   # Логирование зарегистрированных маршрутов
#    with app.app_context():
#        import logging
#        logger = logging.getLogger(__name__)
#        logger.info("Registered routes:")
#        for rule in app.url_map.iter_rules():
#            if '/api/' in rule.rule:
#                logger.info(f"  {rule.methods} {rule.rule}")
    
    return app    
    
    # Инициализация задач (вынесено в отдельный блок, после всех импортов)
    with app.app_context():
        from app.tasks import init_tasks
        init_tasks(app)
    
    return app

def setup_logging(app):
    if not os.path.exists(app.config['LOG_DIR']):
        os.mkdir(app.config['LOG_DIR'])
    
    file_handler = RotatingFileHandler(
        os.path.join(app.config['LOG_DIR'], 'faktura.log'),
        maxBytes=10240, 
        backupCount=10
    )
    
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    file_handler.setFormatter(formatter)
    
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    app.logger.setLevel(logging.INFO)
    app.logger.info('Faktura App запущено')

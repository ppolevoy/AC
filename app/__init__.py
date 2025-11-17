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
        from app.models.application_instance import ApplicationInstance
        from app.models.application_catalog import ApplicationCatalog
        from app.models.application_group import ApplicationGroup
        from app.models.event import Event
        from app.models.orchestrator_playbook import OrchestratorPlaybook
        from app.models.eureka import EurekaServer, EurekaApplication, EurekaInstance
    
    # Регистрация маршрутов API
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # Регистрация Eureka API
    from app.api.eureka_routes import eureka_bp
    app.register_blueprint(eureka_bp)

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
    
      
    
    # Инициализация задач (вынесено в отдельный блок, после всех импортов)
    with app.app_context():
        from app.tasks import init_tasks
        init_tasks(app)

        # Сканирование orchestrator playbooks при старте приложения
        try:
            from app.services.orchestrator_scanner import scan_orchestrators
            logger = logging.getLogger(__name__)
            logger.info("Scanning orchestrator playbooks on startup...")
            results = scan_orchestrators(force=True)
            logger.info(f"Orchestrator scan completed: {results['new']} new, "
                       f"{results['updated']} updated, {len(results['errors'])} errors")
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to scan orchestrator playbooks on startup: {e}")

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

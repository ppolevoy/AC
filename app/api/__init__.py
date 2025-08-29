from flask import Blueprint

bp = Blueprint('api', __name__)

# Импортируем существующие маршруты
from app.api import routes
from app.api import nexus_routes
from app.api import tags_routes

# Импортируем новые маршруты для Docker
#try:
#    from app.api import docker_routes
#except ImportError:
#    import logging
    #logging.warning("Docker routes not found, skipping import")
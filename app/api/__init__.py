from flask import Blueprint

bp = Blueprint('api', __name__)

# Импортируем все модули с маршрутами
# Разделенные модули routes.py:
from app.api import servers_routes
from app.api import applications_routes
from app.api import tasks_routes
from app.api import ssh_routes
from app.api import artifacts_routes
from app.api import ansible_routes
from app.api import app_groups_routes

# Дополнительные маршруты:
from app.api import nexus_routes
from app.api import orchestrator_routes
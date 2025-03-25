from flask import Blueprint

bp = Blueprint('api', __name__)

from app.api import routes  # Импортируем маршруты после создания Blueprint
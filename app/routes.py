# app/routes.py
from flask import Blueprint, render_template, redirect, url_for, current_app, jsonify
import logging

bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

@bp.route('/')
def index():
    """Главная страница - редирект на страницу серверов"""
    return redirect(url_for('main.servers'))

@bp.route('/servers')
def servers():
    """Страница со списком серверов"""
    return render_template('servers.html')

@bp.route('/applications')
def applications():
    """Страница со списком приложений"""
    return render_template('applications.html')

@bp.route('/tasks')
def tasks():
    """Страница с очередью задач"""
    return render_template('tasks.html')

@bp.route('/server/<int:server_id>')
def server_details(server_id):
    """Страница с детальной информацией о сервере"""
    return render_template('server_details.html', server_id=server_id)

@bp.route('/application/<int:app_id>')
def application_details(app_id):
    """Страница с детальной информацией о приложении"""
    return render_template('application_details.html', app_id=app_id)

# Добавим тестовый маршрут для проверки работы Blueprint
@bp.route('/hello')
def hello():
    return jsonify({
        'message': 'Hello from main Blueprint!',
        'routes_working': True
    })

@bp.app_errorhandler(404)
def page_not_found(e):
    """Обработчик ошибки 404"""
    logger.warning(f"Страница не найдена: {e}")
    return render_template('errors/404.html'), 404

@bp.app_errorhandler(500)
def internal_server_error(e):
    """Обработчик ошибки 500"""
    logger.error(f"Внутренняя ошибка сервера: {e}")
    return render_template('errors/500.html'), 500
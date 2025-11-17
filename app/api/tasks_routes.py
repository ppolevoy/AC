from flask import jsonify, request
import logging

from app.models.server import Server
from app.models.application_instance import ApplicationInstance
Application = ApplicationInstance  # Алиас
from app.tasks.queue import task_queue
from app.api import bp

logger = logging.getLogger(__name__)


@bp.route('/tasks', methods=['GET'])
def get_tasks():
    """Получение списка задач"""
    try:
        status = request.args.get('status')
        application_id = request.args.get('application_id', type=int)
        server_id = request.args.get('server_id', type=int)

        tasks = task_queue.get_tasks(status, application_id, server_id)
        result = []

        for task in tasks:
            task_data = task.to_dict()

            # Добавляем имена приложения и сервера вместо ID
            # Проверяем, является ли задача групповой (по наличию app_ids в params)
            app_ids = task.params.get('app_ids')
            if app_ids and isinstance(app_ids, list) and len(app_ids) > 1:
                # Групповая задача - загружаем приложения и формируем строку
                apps = Application.query.filter(Application.id.in_(app_ids)).all()
                if apps:
                    task_data['application_name'] = ','.join([app.name for app in apps])
                else:
                    task_data['application_name'] = f"Apps: {','.join(map(str, app_ids))}"
            elif task.application_id:
                # Одиночная задача
                app = Application.query.get(task.application_id)
                task_data['application_name'] = app.name if app else None
            else:
                task_data['application_name'] = None

            if task.server_id:
                server = Server.query.get(task.server_id)
                task_data['server_name'] = server.name if server else None
            else:
                task_data['server_name'] = None

            result.append(task_data)

        return jsonify({
            'success': True,
            'tasks': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка задач: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """Получение информации о конкретной задаче"""
    try:
        task = task_queue.get_task(task_id)

        if not task:
            return jsonify({
                'success': False,
                'error': f"Задача с id {task_id} не найдена"
            }), 404

        task_data = task.to_dict()

        # Добавляем имена приложения и сервера вместо ID
        # Проверяем, является ли задача групповой (по наличию app_ids в params)
        app_ids = task.params.get('app_ids')
        if app_ids and isinstance(app_ids, list) and len(app_ids) > 1:
            # Групповая задача - загружаем приложения и формируем строку
            apps = Application.query.filter(Application.id.in_(app_ids)).all()
            if apps:
                task_data['application_name'] = ','.join([app.name for app in apps])
            else:
                task_data['application_name'] = f"Apps: {','.join(map(str, app_ids))}"
        elif task.application_id:
            # Одиночная задача
            app = Application.query.get(task.application_id)
            task_data['application_name'] = app.name if app else None
        else:
            task_data['application_name'] = None

        if task.server_id:
            server = Server.query.get(task.server_id)
            task_data['server_name'] = server.name if server else None
        else:
            task_data['server_name'] = None

        return jsonify({
            'success': True,
            'task': task_data
        })
    except Exception as e:
        logger.error(f"Ошибка при получении информации о задаче {task_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

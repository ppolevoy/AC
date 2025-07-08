from flask import Blueprint, jsonify, request, current_app
import asyncio
from datetime import datetime
import logging

from app import db
from app.models.server import Server
from app.models.application import Application
from app.models.event import Event
from app.services.agent_service import AgentService
from app.services.ansible_service import AnsibleService
from app.api import bp

from app.tasks.queue import task_queue, Task

logger = logging.getLogger(__name__)

# Вспомогательная функция для запуска асинхронных операций в синхронном коде
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# API для работы с серверами
@bp.route('/servers', methods=['GET'])
def get_servers():
    """Получение списка всех серверов"""
    try:
        servers = Server.query.all()
        result = []
        
        for server in servers:
            app_count = Application.query.filter_by(server_id=server.id).count()
            
            result.append({
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None,
                'app_count': app_count
            })
        
        return jsonify({
            'success': True,
            'servers': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка серверов: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/servers/<int:server_id>', methods=['GET'])
def get_server(server_id):
    """Получение информации о конкретном сервере"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404
        
        apps = Application.query.filter_by(server_id=server.id).all()
        app_list = []
        
        for app in apps:
            app_list.append({
                'id': app.id,
                'name': app.name,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'start_time': app.start_time.isoformat() if app.start_time else None
            })
        
        return jsonify({
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None,
                'applications': app_list
            }
        })
    except Exception as e:
        logger.error(f"Ошибка при получении информации о сервере {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/servers', methods=['POST'])
def add_server():
    """Добавление нового сервера"""
    try:
        data = request.json
        
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные"
            }), 400
        
        required_fields = ['name', 'ip', 'port']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f"Поле {field} обязательно"
                }), 400
        
        # Проверяем, существует ли сервер с таким именем
        existing_server = Server.query.filter_by(name=data['name']).first()
        if existing_server:
            return jsonify({
                'success': False,
                'error': f"Сервер с именем {data['name']} уже существует"
            }), 400
        
        # Создаем новый сервер
        server = Server(
            name=data['name'],
            ip=data['ip'],
            port=data['port'],
            status='unknown',
            last_check=datetime.utcnow()
        )
        
        db.session.add(server)
        db.session.commit()
        
        # Запускаем проверку доступности сервера
        run_async(AgentService.update_server_applications(server.id))
        
        return jsonify({
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при добавлении сервера: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/servers/<int:server_id>', methods=['PUT'])
def update_server(server_id):
    """Обновление информации о сервере"""
    try:
        data = request.json
        
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные"
            }), 400
        
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404
        
        # Обновляем данные сервера
        if 'name' in data:
            # Проверяем, существует ли другой сервер с таким именем
            existing_server = Server.query.filter(Server.name == data['name'], Server.id != server_id).first()
            if existing_server:
                return jsonify({
                    'success': False,
                    'error': f"Сервер с именем {data['name']} уже существует"
                }), 400
            server.name = data['name']
        
        if 'ip' in data:
            server.ip = data['ip']
        
        if 'port' in data:
            server.port = data['port']
        
        db.session.commit()
        
        # Запускаем проверку доступности сервера после обновления
        run_async(AgentService.update_server_applications(server.id))
        
        return jsonify({
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении сервера {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/servers/<int:server_id>', methods=['DELETE'])
def delete_server(server_id):
    """Удаление сервера"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404
        
        # Удаляем сервер (приложения и события будут удалены автоматически из-за каскадного удаления)
        db.session.delete(server)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Сервер {server.name} успешно удален"
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при удалении сервера {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/servers/<int:server_id>/refresh', methods=['POST'])
def refresh_server(server_id):
    """Принудительное обновление информации о сервере"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404
        
        # Запускаем обновление информации о сервере
        result = run_async(AgentService.update_server_applications(server.id))
        
        if result:
            return jsonify({
                'success': True,
                'message': f"Информация о сервере {server.name} успешно обновлена",
                'server': {
                    'id': server.id,
                    'name': server.name,
                    'ip': server.ip,
                    'port': server.port,
                    'status': server.status,
                    'last_check': server.last_check.isoformat() if server.last_check else None
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': f"Не удалось обновить информацию о сервере {server.name}",
                'server': {
                    'id': server.id,
                    'name': server.name,
                    'ip': server.ip,
                    'port': server.port,
                    'status': server.status,
                    'last_check': server.last_check.isoformat() if server.last_check else None
                }
            })
    except Exception as e:
        logger.error(f"Ошибка при обновлении информации о сервере {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API для работы с приложениями
@bp.route('/applications', methods=['GET'])
def get_applications():
    """Получение списка всех приложений"""
    try:
        server_id = request.args.get('server_id', type=int)
        app_type = request.args.get('type')
        
        # Формируем базовый запрос
        query = Application.query
        
        # Применяем фильтры, если они указаны
        if server_id:
            query = query.filter_by(server_id=server_id)
        
        if app_type:
            query = query.filter_by(app_type=app_type)
        
        applications = query.all()
        result = []
        
        for app in applications:
            server = Server.query.get(app.server_id)
            
            result.append({
                'id': app.id,
                'name': app.name,
                'server_id': app.server_id,
                'server_name': server.name if server else None,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'group_name': app.group_name,
                'instance_number': app.instance_number,
                'start_time': app.start_time.isoformat() if app.start_time else None
            })
        
        return jsonify({
            'success': True,
            'applications': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка приложений: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/applications/<int:app_id>', methods=['GET'])
def get_application(app_id):
    """Получение информации о конкретном приложении"""
    try:
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        server = Server.query.get(app.server_id)
        
        # Получаем последние события для этого приложения
        events = Event.query.filter_by(application_id=app.id).order_by(Event.timestamp.desc()).limit(10).all()
        events_list = []
        
        for event in events:
            events_list.append({
                'id': event.id,
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type,
                'description': event.description,
                'status': event.status
            })
        
        result = {
            'id': app.id,
            'name': app.name,
            'path': app.path,
            'log_path': app.log_path,
            'version': app.version,
            'distr_path': app.distr_path,
            'container_id': app.container_id,
            'container_name': app.container_name,
            'eureka_url': app.eureka_url,
            'compose_project_dir': app.compose_project_dir,
            'ip': app.ip,
            'port': app.port,
            'status': app.status,
            'app_type': app.app_type,
            'update_playbook_path': app.update_playbook_path,
            'start_time': app.start_time.isoformat() if app.start_time else None,
            'server_id': app.server_id,
            'server_name': server.name if server else None,
            'group_name': app.group_name,
            'instance_number': app.instance_number,
            'events': events_list
        }
        
        return jsonify({
            'success': True,
            'application': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении информации о приложении {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/applications/<int:app_id>/update_playbook', methods=['PUT'])
def update_application_playbook(app_id):
    """Обновление пути к плейбуку обновления для приложения"""
    try:
        data = request.json
        
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле playbook_path"
            }), 400
        
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        # Обновляем путь к плейбуку
        app.update_playbook_path = data['playbook_path']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Путь к плейбуку обновления для приложения {app.name} успешно обновлен",
            'application': {
                'id': app.id,
                'name': app.name,
                'update_playbook_path': app.update_playbook_path
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении пути к плейбуку для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/applications/<int:app_id>/update', methods=['POST'])
def update_application(app_id):
    """Обновление приложения"""
    try:
        data = request.json
        
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные"
            }), 400
        
        required_fields = ['distr_url', 'restart_mode']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f"Поле {field} обязательно"
                }), 400
        
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        server = Server.query.get(app.server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер для приложения {app.name} не найден"
            }), 404
        
        # Создаем задачу и добавляем ее в очередь
        task = Task(
            task_type="update",
            params={
                "distr_url": data['distr_url'],
                "restart_mode": data['restart_mode']
            },
            server_id=server.id,
            application_id=app.id
        )
        
        task_queue.add_task(task)
        
        return jsonify({
            'success': True,
            'message': f"Обновление приложения {app.name} поставлено в очередь",
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Ошибка при обновлении приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/applications/<int:app_id>/manage', methods=['POST'])
def manage_application(app_id):
    """Управление приложением (запуск, остановка, перезапуск)"""
    try:
        data = request.json
        
        if not data or 'action' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле action"
            }), 400
        
        action = data['action']
        valid_actions = ['start', 'stop', 'restart']
        
        if action not in valid_actions:
            return jsonify({
                'success': False,
                'error': f"Неверное действие. Допустимые значения: {', '.join(valid_actions)}"
            }), 400
        
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        server = Server.query.get(app.server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер для приложения {app.name} не найден"
            }), 404
        
        # Создаем задачу и добавляем ее в очередь
        task = Task(
            task_type=action,
            params={},
            server_id=server.id,
            application_id=app.id
        )
        
        task_queue.add_task(task)
        
        return jsonify({
            'success': True,
            'message': f"{action} для приложения {app.name} поставлен в очередь",
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Ошибка при управлении приложением {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/applications/bulk/manage', methods=['POST'])
def bulk_manage_applications():
    """Массовое управление приложениями (запуск, остановка, перезапуск)"""
    try:
        data = request.json
        
        if not data or 'action' not in data or 'app_ids' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют обязательные поля action и app_ids"
            }), 400
        
        action = data['action']
        app_ids = data['app_ids']
        
        valid_actions = ['start', 'stop', 'restart']
        if action not in valid_actions:
            return jsonify({
                'success': False,
                'error': f"Неверное действие. Допустимые значения: {', '.join(valid_actions)}"
            }), 400
        
        if not isinstance(app_ids, list) or not app_ids:
            return jsonify({
                'success': False,
                'error': "app_ids должен быть непустым списком"
            }), 400
        
        results = []
        for app_id in app_ids:
            app = Application.query.get(app_id)
            if not app:
                results.append({
                    'app_id': app_id,
                    'success': False,
                    'message': f"Приложение с id {app_id} не найдено"
                })
                continue
            
            server = Server.query.get(app.server_id)
            if not server:
                results.append({
                    'app_id': app_id,
                    'app_name': app.name,
                    'success': False,
                    'message': f"Сервер для приложения {app.name} не найден"
                })
                continue
            
            # Создаем задачу и добавляем ее в очередь
            task = Task(
                task_type=action,
                params={},
                server_id=server.id,
                application_id=app.id
            )
            
            task_queue.add_task(task)
            
            results.append({
                'app_id': app_id,
                'app_name': app.name,
                'success': True,
                'message': f"{action} для приложения {app.name} поставлен в очередь",
                'task_id': task.id
            })
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        logger.error(f"Ошибка при массовом управлении приложениями: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/applications/grouped', methods=['GET'])
def get_grouped_applications():
    """Получение списка приложений, сгруппированных по группам"""
    try:
        server_id = request.args.get('server_id', type=int)
        
        # Формируем базовый запрос
        query = Application.query
        
        # Применяем фильтр по серверу, если он указан
        if server_id:
            query = query.filter_by(server_id=server_id)
        
        applications = query.all()
        
        # Группируем приложения по именам групп
        grouped = {}
        for app in applications:
            group_name = app.group_name
            
            if group_name not in grouped:
                grouped[group_name] = []
            
            server = Server.query.get(app.server_id)
            
            grouped[group_name].append({
                'id': app.id,
                'name': app.name,
                'server_id': app.server_id,
                'server_name': server.name if server else None,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'instance_number': app.instance_number,
                'start_time': app.start_time.isoformat() if app.start_time else None
            })
        
        # Сортируем приложения в каждой группе по номеру экземпляра
        for group_name in grouped:
            grouped[group_name] = sorted(grouped[group_name], key=lambda x: x['instance_number'])
        
        # Преобразуем словарь в список для удобства использования в клиенте
        result = []
        for group_name, apps in grouped.items():
            result.append({
                'group_name': group_name,
                'applications': apps
            })
        
        # Сортируем группы по имени
        result = sorted(result, key=lambda x: x['group_name'])
        
        return jsonify({
            'success': True,
            'groups': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении сгруппированных приложений: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
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
            if task.application_id:
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
        if task.application_id:
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
        
@bp.route('/test', methods=['GET'])
def test_api():
    """Тестовый маршрут для проверки работы API"""
    return jsonify({
        'success': True,
        'message': 'API работает корректно',
        'time': datetime.utcnow().isoformat()
    })        

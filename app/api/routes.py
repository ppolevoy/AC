from flask import Blueprint, jsonify, request, current_app
import asyncio
from datetime import datetime
import logging
import os

from app import db
from app.models.server import Server
from app.models.application import Application
from app.models.event import Event
from app.services.agent_service import AgentService
from app.services.ansible_service import AnsibleService
from app.api import bp
from app.api import app_groups_routes

from app.models.application_group import ApplicationGroup, ApplicationInstance
from app.services.application_group_service import ApplicationGroupService

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

@bp.route('/applications/<int:app_id>/update', methods=['POST'])
def update_application(app_id):
    """Запуск обновления приложения через Ansible playbook"""
    try:
        # Получаем приложение
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        # Получаем данные из запроса
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400
        
        # Получаем параметры обновления
        restart_mode = data.get('restart_mode', 'restart')
        
        # Определяем URL/имя дистрибутива в зависимости от типа приложения
        if app.app_type == 'docker':
            # Для Docker приложений используем image_name
            image_name = data.get('image_name') or data.get('distr_url')
            if not image_name:
                return jsonify({
                    'success': False,
                    'error': "Не указано имя Docker образа"
                }), 400
            
            # Сохраняем в distr_url для обратной совместимости
            distr_url = image_name
            
            # УДАЛЕНО: additional_vars больше не используется!
            # Значение image_url будет сформировано динамически в SSHAnsibleService
            
        else:
            # Для Maven/обычных приложений
            distr_url = data.get('distr_url')
            if not distr_url:
                return jsonify({
                    'success': False,
                    'error': "Не указан URL дистрибутива"
                }), 400
        
        # Получаем сервер приложения
        server = Server.query.get(app.server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер приложения не найден"
            }), 404
        
        # Определяем путь к playbook
        playbook_path = None
        
        # Приоритет 1: Путь из Application
        if app.update_playbook_path:
            playbook_path = app.update_playbook_path
            logger.info(f"Используется playbook приложения: {playbook_path}")
        
        # Приоритет 2: Если есть экземпляр, проверяем его настройки
        if not playbook_path:
            instance = ApplicationInstance.query.filter_by(application_id=app_id).first()
            if instance:
                # Приоритет 2a: Кастомный путь экземпляра
                if instance.custom_playbook_path:
                    playbook_path = instance.custom_playbook_path
                    logger.info(f"Используется кастомный playbook экземпляра: {playbook_path}")
                
                # Приоритет 2b: Групповой путь
                elif instance.group and instance.group.update_playbook_path:
                    playbook_path = instance.group.update_playbook_path
                    logger.info(f"Используется групповой playbook: {playbook_path}")
                
                # Приоритет 2c: Эффективный путь
                elif hasattr(instance, 'get_effective_playbook_path'):
                    playbook_path = instance.get_effective_playbook_path()
                    logger.info(f"Используется эффективный playbook экземпляра: {playbook_path}")
        
        # Приоритет 3: Дефолтный путь в зависимости от типа приложения
        if not playbook_path:
            from app.config import Config
            if app.app_type == 'docker':
                # Используем специальный playbook для Docker
                playbook_path = getattr(Config, 'DOCKER_UPDATE_PLAYBOOK', '/site/ansible/fmcc/docker_update_playbook.yaml')
            else:
                playbook_path = getattr(Config, 'DEFAULT_UPDATE_PLAYBOOK', '/site/ansible/fmcc/update-app.yml')
            logger.info(f"Используется дефолтный playbook для типа {app.app_type}: {playbook_path}")
        
        # Проверяем, что путь не пустой
        if not playbook_path or playbook_path.strip() == '':
            logger.error("Путь к playbook пустой")
            return jsonify({
                'success': False,
                'error': "Не настроен путь к Ansible playbook"
            }), 500
        
        logger.info(f"Финальный путь к playbook для {app.name}: {playbook_path}")

        # Создаем задачу для обновления
        task = Task(
            task_type='update',
            params={
                'app_id': app.id,
                'app_name': app.name,
                'app_type': app.app_type,
                'server_name': server.name,
                'distr_url': distr_url,
                'restart_mode': restart_mode,
                'playbook_path': playbook_path
            },
            server_id=server.id,
            application_id=app.id
        )

        # Добавляем задачу в очередь для асинхронной обработки
        task_queue.add_task(task)

        # Логируем событие
        event = Event(
            event_type='update',
            description=f"Запущено обновление {app.app_type} приложения {app.name} на версию из {distr_url}",
            status='pending',
            server_id=server.id,
            application_id=app.id
        )
        db.session.add(event)
        db.session.commit()

        logger.info(f"Задача обновления {app.name} добавлена в очередь (task_id: {task.id})")

        # Возвращаем успешный ответ сразу - обработка будет происходить асинхронно
        return jsonify({
            'success': True,
            'message': f"Обновление приложения {app.name} добавлено в очередь",
            'task_id': task.id
        })
            
    except Exception as e:
        logger.error(f"Ошибка при запуске обновления приложения {app_id}: {str(e)}")
        
        # Обновляем статус задачи и события в случае исключения
        if 'task' in locals():
            task.status = 'failed'
            task.error = str(e)
        
        if 'event' in locals():
            event.status = 'failed'
            event.description += f"\nКритическая ошибка: {str(e)}"
        
        db.session.commit()
        
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

@bp.route('/ssh/test', methods=['GET'])
def test_ssh_connection():
    """Тестирование SSH-подключения"""
    try:
        from app.config import Config
        
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400
        
        # Используем функцию из обновленного AnsibleService
        from app.services.ansible_service import AnsibleService
        
        # Запускаем тест подключения
        result = run_async(AnsibleService.test_ssh_connection())
        
        if result[0]:
            return jsonify({
                'success': True,
                'message': result[1]
            })
        else:
            return jsonify({
                'success': False,
                'error': result[1]
            }), 500
            
    except Exception as e:
        logger.error(f"Ошибка при тестировании SSH-подключения: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/ssh/config', methods=['GET'])
def get_ssh_config():
    """Получение конфигурации SSH"""
    try:
        from app.config import Config
        
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400
        
        # Возвращаем конфигурацию SSH (без приватных данных)
        ssh_config = {
            'host': getattr(Config, 'SSH_HOST', 'localhost'),
            'user': getattr(Config, 'SSH_USER', 'ansible'),
            'port': getattr(Config, 'SSH_PORT', 22),
            'key_file': getattr(Config, 'SSH_KEY_FILE', '/app/.ssh/id_rsa'),
            'connection_timeout': getattr(Config, 'SSH_CONNECTION_TIMEOUT', 30),
            'command_timeout': getattr(Config, 'SSH_COMMAND_TIMEOUT', 300),
            'ansible_path': getattr(Config, 'ANSIBLE_PATH', '/etc/ansible')
        }
        
        # Проверяем существование SSH-ключа
        import os
        key_exists = os.path.exists(ssh_config['key_file'])
        pub_key_exists = os.path.exists(ssh_config['key_file'] + '.pub')
        
        # Читаем публичный ключ, если он существует
        public_key = None
        if pub_key_exists:
            try:
                with open(ssh_config['key_file'] + '.pub', 'r') as f:
                    public_key = f.read().strip()
            except Exception as e:
                logger.warning(f"Не удалось прочитать публичный ключ: {str(e)}")
        
        return jsonify({
            'success': True,
            'config': ssh_config,
            'key_status': {
                'private_key_exists': key_exists,
                'public_key_exists': pub_key_exists,
                'public_key': public_key
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении конфигурации SSH: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/ssh/generate-key', methods=['POST'])
def generate_ssh_key():
    """Генерация нового SSH-ключа"""
    try:
        from app.config import Config
        import os
        import subprocess
        
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400
        
        key_file = getattr(Config, 'SSH_KEY_FILE', '/app/.ssh/id_rsa')
        
        # Создаем директорию для ключей, если она не существует
        key_dir = os.path.dirname(key_file)
        os.makedirs(key_dir, mode=0o700, exist_ok=True)
        
        # Удаляем существующие ключи
        if os.path.exists(key_file):
            os.remove(key_file)
        if os.path.exists(key_file + '.pub'):
            os.remove(key_file + '.pub')
        
        # Генерируем новый ключ
        cmd = [
            'ssh-keygen',
            '-t', 'rsa',
            '-b', '4096',
            '-f', key_file,
            '-N', ''  # Без пароля
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Читаем публичный ключ
            with open(key_file + '.pub', 'r') as f:
                public_key = f.read().strip()
            
            # Устанавливаем правильные права доступа
            os.chmod(key_file, 0o600)
            os.chmod(key_file + '.pub', 0o644)
            
            logger.info(f"Новый SSH-ключ сгенерирован: {key_file}")
            
            return jsonify({
                'success': True,
                'message': 'SSH-ключ успешно сгенерирован',
                'public_key': public_key
            })
        else:
            error_msg = result.stderr or result.stdout
            logger.error(f"Ошибка при генерации SSH-ключа: {error_msg}")
            return jsonify({
                'success': False,
                'error': f'Ошибка при генерации ключа: {error_msg}'
            }), 500
            
    except Exception as e:
        logger.error(f"Ошибка при генерации SSH-ключа: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/ssh/playbooks', methods=['GET'])
def check_playbooks():
    """Получение списка всех playbook файлов из ansible каталога на удаленном хосте"""
    try:
        from app.config import Config
        
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400
        
        from app.services.ssh_ansible_service import get_ssh_ansible_service
        
        # Получаем сервис
        ssh_service = get_ssh_ansible_service()
        
        # Получаем список всех playbook файлов из каталога
        async def get_all_playbook_files():
            return await ssh_service.get_all_playbooks()
        
        # Запускаем получение списка
        results = run_async(get_all_playbook_files())
        
        # Если список пустой, возвращаем предупреждение
        if not results:
            logger.warning(f"Не найдено playbook файлов в каталоге {ssh_service.ssh_config.ansible_path}")
            return jsonify({
                'success': True,
                'playbooks': {},
                'message': 'No playbook files found in ansible directory'
            })
        
        logger.info(f"Найдено {len(results)} playbook файлов")
        
        return jsonify({
            'success': True,
            'playbooks': results
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка playbook-ов: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/ssh/status', methods=['GET'])
def get_ssh_status():
    """Получение полного статуса SSH-подключения"""
    try:
        from app.config import Config
        import os
        
        # Базовая информация о статусе
        status = {
            'ssh_enabled': getattr(Config, 'USE_SSH_ANSIBLE', False),
            'config': {},
            'key_status': {},
            'connection_status': {},
            'playbooks_status': {}
        }
        
        # Если SSH отключен, возвращаем базовую информацию
        if not status['ssh_enabled']:
            return jsonify({
                'success': True,
                'status': status
            })
        
        # Конфигурация SSH
        status['config'] = {
            'host': getattr(Config, 'SSH_HOST', 'localhost'),
            'user': getattr(Config, 'SSH_USER', 'ansible'),
            'port': getattr(Config, 'SSH_PORT', 22),
            'key_file': getattr(Config, 'SSH_KEY_FILE', '/app/.ssh/id_rsa'),
            'ansible_path': getattr(Config, 'ANSIBLE_PATH', '/etc/ansible')
        }
        
        # Статус SSH-ключей
        key_file = status['config']['key_file']
        status['key_status'] = {
            'private_key_exists': os.path.exists(key_file),
            'public_key_exists': os.path.exists(key_file + '.pub'),
            'key_permissions_ok': False
        }
        
        # Проверяем права доступа к ключу
        if status['key_status']['private_key_exists']:
            try:
                key_stat = os.stat(key_file)
                status['key_status']['key_permissions_ok'] = not (key_stat.st_mode & 0o077)
            except:
                pass
        
        # Тестируем подключение
        if status['key_status']['private_key_exists']:
            try:
                from app.services.ssh_ansible_service import get_ssh_ansible_service
                ssh_service = get_ssh_ansible_service()
                
                # Тест подключения
                connection_result = run_async(ssh_service.test_connection())
                status['connection_status'] = {
                    'connected': connection_result[0],
                    'message': connection_result[1]
                }
                
                # Если подключение успешно, проверяем playbook-и
                if connection_result[0]:
                    # Используем новый метод для получения всех playbooks
                    async def get_all_playbook_files():
                        return await ssh_service.get_all_playbooks()
                    
                    playbook_results_dict = run_async(get_all_playbook_files())
                    
                    # Преобразуем для совместимости с текущим форматом
                    playbook_results = {}
                    for playbook_name, info in playbook_results_dict.items():
                        playbook_results[playbook_name] = info.get('exists', False)
                    
                    status['playbooks_status'] = playbook_results
                
            except Exception as e:
                status['connection_status'] = {
                    'connected': False,
                    'message': f'Ошибка при тестировании: {str(e)}'
                }
        else:
            status['connection_status'] = {
                'connected': False,
                'message': 'SSH-ключ не найден'
            }
        
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении статуса SSH: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/application-groups', methods=['GET'])
def get_application_groups():
    """Получение списка всех групп приложений"""
    try:
        groups = ApplicationGroup.query.all()
        result = []
        
        for group in groups:
            # Подсчитываем количество экземпляров в группе
            instance_count = Application.query.filter_by(group_id=group.id).count()
            
            # Получаем список серверов, где запущены экземпляры
            servers = db.session.query(Server).join(
                Application, Application.server_id == Server.id
            ).filter(
                Application.group_id == group.id
            ).distinct().all()
            
            result.append({
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'instance_count': instance_count,
                'servers': [{'id': s.id, 'name': s.name} for s in servers],
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None
            })
        
        return jsonify({
            'success': True,
            'groups': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка групп приложений: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<int:group_id>', methods=['GET'])
def get_application_group(group_id):
    """Получение информации о конкретной группе приложений"""
    try:
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа приложений с id {group_id} не найдена"
            }), 404
        
        # Получаем все экземпляры приложений в группе
        applications = Application.query.filter_by(group_id=group.id).all()
        app_list = []
        
        for app in applications:
            server = Server.query.get(app.server_id)
            app_list.append({
                'id': app.id,
                'name': app.name,
                'instance_number': app.instance_number,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'server': {
                    'id': server.id,
                    'name': server.name,
                    'ip': server.ip
                } if server else None,
                'start_time': app.start_time.isoformat() if app.start_time else None
            })
        
        return jsonify({
            'success': True,
            'group': {
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None,
                'applications': sorted(app_list, key=lambda x: x['instance_number'])
            }
        })
    except Exception as e:
        logger.error(f"Ошибка при получении информации о группе {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<int:group_id>', methods=['PUT'])
def update_application_group(group_id):
    """Обновление параметров группы приложений (artifact_list_url, artifact_extension)"""
    try:
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа приложений с id {group_id} не найдена"
            }), 404
        
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400
        
        # Обновляем только переданные поля
        if 'artifact_list_url' in data:
            group.artifact_list_url = data['artifact_list_url']
            logger.info(f"Обновлен artifact_list_url для группы {group.name}: {data['artifact_list_url']}")
        
        if 'artifact_extension' in data:
            group.artifact_extension = data['artifact_extension']
            logger.info(f"Обновлен artifact_extension для группы {group.name}: {data['artifact_extension']}")

#        if 'group-playbook-path' in data:
#            group.update_playbook_path = data['group-playbook-path']
#            logger.info(f"Обновлен playbook_path для группы {group.name}: {data['group-playbook-path']}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Группа приложений {group.name} успешно обновлена",
            'group': {
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении группы {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<int:group_id>/manage', methods=['POST'])
def manage_application_group(group_id):
    """Массовое управление всеми экземплярами группы приложений"""
    try:
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа приложений с id {group_id} не найдена"
            }), 404
        
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
        
        # Получаем все активные экземпляры приложений в группе
        applications = Application.query.filter_by(group_id=group.id).all()
        
        if not applications:
            return jsonify({
                'success': False,
                'error': f"В группе {group.name} нет приложений"
            }), 404
        
        task_ids = []
        
        for app in applications:
            # Создаем задачу для каждого экземпляра
            task = Task(
                task_type=action,
                params={},
                server_id=app.server_id,
                application_id=app.id
            )
            
            task_queue.add_task(task)
            task_ids.append(task.id)
            
            logger.info(f"Создана задача {action} для приложения {app.name} (экземпляр #{app.instance_number})")
        
        return jsonify({
            'success': True,
            'message': f"{action} для группы {group.name} поставлен в очередь",
            'task_ids': task_ids,
            'affected_instances': len(applications)
        })
    except Exception as e:
        logger.error(f"Ошибка при управлении группой {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/reassign-group', methods=['POST'])
def reassign_application_group(app_id):
    """Переопределение группы для приложения (ручное исправление)"""
    try:
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        data = request.json
        if not data or 'group_name' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле group_name"
            }), 400
        
        group_name = data['group_name']
        instance_number = data.get('instance_number', 0)
        
        # Ищем или создаем группу
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        if not group:
            group = ApplicationGroup(name=group_name)
            db.session.add(group)
            db.session.flush()
            logger.info(f"Создана новая группа приложений: {group_name}")
        
        # Сохраняем старое имя группы для логирования
        old_group_name = app.group.name if app.group else "без группы"
        
        # ВАЖНО: Синхронизируем обе таблицы
        # 1. Обновляем поля в Application
        app.group_id = group.id
        app.instance_number = instance_number
        
        # 2. Обновляем или создаем ApplicationInstance
        if hasattr(app, 'instance') and app.instance:
            # Обновляем существующий instance
            instance = app.instance
            instance.group_id = group.id
            instance.instance_number = instance_number
            instance.original_name = app.name
            instance.group_resolved = True
            logger.info(f"Обновлен ApplicationInstance для приложения {app.name}")
        else:
            # Создаем новый instance
            from app.models.application_group import ApplicationInstance
            instance = ApplicationInstance(
                original_name=app.name,
                instance_number=instance_number,
                group_id=group.id,
                application_id=app.id,
                group_resolved=True
            )
            db.session.add(instance)
            logger.info(f"Создан ApplicationInstance для приложения {app.name}")
        
        db.session.commit()
        
        logger.info(f"Приложение {app.name} переназначено из группы '{old_group_name}' в группу '{group.name}' с экземпляром #{instance_number}")
        
        return jsonify({
            'success': True,
            'message': f"Приложение {app.name} успешно переназначено в группу {group.name}",
            'application': {
                'id': app.id,
                'name': app.name,
                'group_name': group.name,
                'instance_number': instance_number
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при переназначении группы для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
# УПРАВЛЕНИЕ PLAYBOOK ПУТЯМИ
# ====================================

@bp.route('/application-groups/<string:group_name>/playbook', methods=['GET'])
def get_group_playbook(group_name):
    """Получить путь к playbook для группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        return jsonify({
            'success': True,
            'group_name': group.name,
            'playbook_path': group.update_playbook_path,
            'effective_path': group.get_effective_playbook_path()
        })
    except Exception as e:
        logger.error(f"Ошибка при получении playbook для группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<string:group_name>/playbook', methods=['PUT'])
def update_group_playbook(group_name):
    """Установить путь к playbook для группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле playbook_path"
            }), 400
        
        group.update_playbook_path = data['playbook_path']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Playbook путь для группы {group_name} обновлен",
            'playbook_path': group.update_playbook_path
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении playbook для группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ====================================
# УПРАВЛЕНИЕ НАСТРОЙКАМИ ГРУППЫ
# ====================================

@bp.route('/application-groups/<string:group_name>/settings', methods=['GET'])
def get_group_settings(group_name):
    """Получить настройки группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        return jsonify({
            'success': True,
            'group_name': group.name,
            'settings': group.group_settings or {}
        })
    except Exception as e:
        logger.error(f"Ошибка при получении настроек группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<string:group_name>/settings', methods=['PUT', 'PATCH'])
def update_group_settings(group_name):
    """Обновить настройки группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400
        
        if request.method == 'PUT':
            # PUT - полная замена настроек
            group.group_settings = data
        else:
            # PATCH - частичное обновление
            if not group.group_settings:
                group.group_settings = {}
            group.group_settings.update(data)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Настройки группы {group_name} обновлены",
            'settings': group.group_settings
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении настроек группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ====================================
# УПРАВЛЕНИЕ НАСТРОЙКАМИ ЭКЗЕМПЛЯРА
# ====================================

@bp.route('/applications/<int:app_id>/instance-settings', methods=['GET'])
def get_instance_settings(app_id):
    """Получить индивидуальные настройки экземпляра"""
    try:
        app = Application.query.get(app_id)
        
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        if not app.instance:
            return jsonify({
                'success': False,
                'error': 'Приложение не связано с экземпляром'
            }), 400
        
        instance = app.instance
        
        return jsonify({
            'success': True,
            'application': app.name,
            'instance_number': instance.instance_number,
            'individual_settings': instance.instance_settings or {},
            'group_settings': instance.group.group_settings if instance.group else {},
            'effective_settings': {
                **((instance.group.group_settings or {}) if instance.group else {}),
                **(instance.instance_settings or {})
            },
            'custom_playbook': instance.custom_playbook_path,
            'effective_playbook': instance.get_effective_playbook_path()
        })
    except Exception as e:
        logger.error(f"Ошибка при получении настроек экземпляра для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/instance-settings', methods=['PUT', 'PATCH'])
def update_instance_settings(app_id):
    """Обновить индивидуальные настройки экземпляра"""
    try:
        app = Application.query.get(app_id)
        
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        if not app.instance:
            return jsonify({
                'success': False,
                'error': 'Приложение не связано с экземпляром'
            }), 400
        
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400
        
        instance = app.instance
        
        if request.method == 'PUT':
            # PUT - полная замена настроек
            instance.instance_settings = data
        else:
            # PATCH - частичное обновление
            if not instance.instance_settings:
                instance.instance_settings = {}
            instance.instance_settings.update(data)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Настройки экземпляра {app.name} обновлены",
            'settings': instance.instance_settings
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении настроек экземпляра для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/custom-playbook', methods=['PUT', 'DELETE'])
def manage_instance_playbook(app_id):
    """Установить или удалить кастомный playbook для экземпляра"""
    try:
        app = Application.query.get(app_id)
        
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        if not app.instance:
            return jsonify({
                'success': False,
                'error': 'Приложение не связано с экземпляром'
            }), 400
        
        instance = app.instance
        
        if request.method == 'DELETE':
            # Удаление кастомного playbook
            instance.custom_playbook_path = None
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Кастомный playbook удален',
                'effective_playbook': instance.get_effective_playbook_path()
            })
        
        # PUT - установка кастомного playbook
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле playbook_path"
            }), 400
        
        instance.custom_playbook_path = data['playbook_path']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Кастомный playbook установлен',
            'custom_playbook': instance.custom_playbook_path,
            'effective_playbook': instance.get_effective_playbook_path()
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при управлении playbook для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_maven_versions_for_app(app):
    """
    Получение списка Maven артефактов для приложения
    """
    try:
        # Получаем экземпляр приложения
        instance = app.instance
        if not instance or not instance.group:
            logger.info(f"Приложение {app.name} не привязано к группе")
            return jsonify({
                'success': False,
                'error': 'Приложение не привязано к группе. Настройте группу приложений.'
            }), 404
        
        # Получаем URL артефактов и расширение
        artifact_url = instance.get_effective_artifact_url()
        artifact_extension = instance.get_effective_artifact_extension()
        
        if not artifact_url:
            logger.info(f"URL артефактов не настроен для приложения {app.name}")
            return jsonify({
                'success': False,
                'error': 'URL артефактов не настроен для данного приложения'
            }), 404
        
        logger.info(f"Загрузка Maven артефактов из: {artifact_url}")
        
        # Получаем параметры из запроса
        from app.config import Config
        limit = request.args.get('limit', type=int, default=Config.MAX_ARTIFACTS_DISPLAY)
        include_snapshots = request.args.get('include_snapshots', 
                                            default=str(Config.INCLUDE_SNAPSHOT_VERSIONS).lower()).lower() == 'true'
        
        # Получаем список артефактов через NexusArtifactService
        from app.services.nexus_artifact_service import NexusArtifactService
        
        # Запускаем асинхронную операцию
        async def fetch_maven_artifacts():
            async with NexusArtifactService() as service:
                artifacts = await service.get_artifacts_for_application(instance)
                
                # Фильтруем SNAPSHOT версии если нужно
                if not include_snapshots:
                    artifacts = [a for a in artifacts if not a.is_snapshot]
                
                # Ограничиваем количество версий
                if limit and limit > 0:
                    artifacts = artifacts[:limit]
                
                return artifacts
        
        import asyncio
        artifacts = asyncio.run(fetch_maven_artifacts())
        
        if not artifacts:
            logger.warning(f"Не удалось получить список артефактов для {app.name}")
            return jsonify({
                'success': False,
                'error': 'Не удалось получить список версий из репозитория'
            }), 404
        
        # Формируем список версий для отправки на frontend
        versions = []
        for artifact in artifacts:
            versions.append({
                'version': artifact.version,
                'url': artifact.download_url,
                'display_name': artifact.filename,  # Для единообразия с Docker
                'filename': artifact.filename,
                'is_release': artifact.is_release,
                'is_snapshot': artifact.is_snapshot,
                'is_dev': False,  # Maven не имеет dev версий
                'timestamp': artifact.timestamp.isoformat() if artifact.timestamp else None
            })
        
        logger.info(f"Загружено {len(versions)} Maven артефактов для приложения {app.name}")
        
        return jsonify({
            'success': True,
            'application': app.name,
            'app_type': app.app_type,
            'versions': versions,
            'total': len(versions),
            'limit_applied': limit,
            'snapshots_included': include_snapshots
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении Maven артефактов для приложения {app.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/artifacts', methods=['GET'])
def get_application_artifacts(app_id):
    """
    Получение списка артефактов/образов для приложения с поддержкой типов приложений
    
    Query Parameters:
        limit: максимальное количество версий для возврата (по умолчанию из конфигурации)
        include_snapshots: включать ли SNAPSHOT версии (по умолчанию из конфигурации)
        include_dev: включать ли DEV версии (для Docker, по умолчанию false)
    """
    try:
        # Получаем приложение
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        logger.info(f"Получение версий для приложения {app.name}, тип: {app.app_type}")
        
        # ВАЖНО: Проверяем тип приложения
        if app.app_type == 'docker':
            # Для Docker приложений используем NexusDockerService
            return get_docker_versions_for_app(app)
        else:
            # Для остальных (maven, site, service) используем NexusArtifactService
            return get_maven_versions_for_app(app)
            
    except Exception as e:
        logger.error(f"Ошибка при получении версий для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_docker_versions_for_app(app):
    """
    Получение списка Docker образов для приложения
    """
    try:
        # Получаем экземпляр приложения
        instance = app.instance
        if not instance:
            # Если экземпляра нет, пытаемся определить группу
            from app.services.application_group_service import ApplicationGroupService
            group = ApplicationGroupService.determine_group_for_application(app)
            if not group:
                return jsonify({
                    'success': False,
                    'error': 'Не удалось определить группу приложения для Docker'
                }), 404
            
            # Создаем временный экземпляр
            instance = ApplicationInstance(
                application_id=app.id,
                group_id=group.id,
                original_name=app.name
            )
        
        # Получаем URL Docker репозитория
        artifact_url = instance.get_effective_artifact_url()
        
        if not artifact_url:
            logger.warning(f"URL Docker репозитория не настроен для приложения {app.name}")
            return jsonify({
                'success': False,
                'error': 'URL Docker репозитория не настроен для данного приложения'
            }), 404
        
        logger.info(f"Загрузка Docker образов из: {artifact_url}")
        
        # Получаем параметры из запроса
        from app.config import Config
        limit = request.args.get('limit', type=int, default=Config.MAX_ARTIFACTS_DISPLAY)
        include_dev = request.args.get('include_dev', 'false').lower() == 'true'
        include_snapshots = request.args.get('include_snapshots', 'false').lower() == 'true'
        
        # Запускаем асинхронную операцию
        import asyncio
        from app.services.nexus_docker_service import NexusDockerService
        
        async def fetch_docker_images():
            async with NexusDockerService() as service:
                images = await service.get_docker_images(artifact_url, limit=limit*2)
                
                # Фильтруем версии
                filtered_images = []
                for image in images:
                    if not include_dev and image.is_dev:
                        continue
                    if not include_snapshots and image.is_snapshot:
                        continue
                    filtered_images.append(image)
                
                return filtered_images[:limit]
        
        images = asyncio.run(fetch_docker_images())
        
        if not images:
            logger.warning(f"Не удалось получить список Docker образов для {app.name}")
            return jsonify({
                'success': False,
                'error': 'Не удалось получить список образов из репозитория'
            }), 404
        
        # Формируем список версий для отправки на frontend
        versions = []
        for image in images:
            versions.append({
                'version': image.tag,
                'url': image.full_image_name,  # Полное имя образа для Docker
                'display_name': image.display_name,
                'filename': f"{image.repository.split('/')[-1]}:{image.tag}",  # Для совместимости
                'is_release': not (image.is_dev or image.is_snapshot),
                'is_snapshot': image.is_snapshot,
                'is_dev': image.is_dev,
                'timestamp': image.created.isoformat() if image.created else None
            })
        
        logger.info(f"Загружено {len(versions)} Docker образов для приложения {app.name}")
        
        return jsonify({
            'success': True,
            'application': app.name,
            'app_type': 'docker',
            'versions': versions,
            'total': len(versions),
            'limit_applied': limit,
            'snapshots_included': include_snapshots,
            'dev_included': include_dev
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении Docker образов для приложения {app.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    

@bp.route('/ansible/variables', methods=['GET'])
def get_available_variables():
    """
    Получить список доступных переменных и информацию о кастомных параметрах
    """
    try:
        from app.services.ssh_ansible_service import SSHAnsibleService
        
        return jsonify({
            'success': True,
            'dynamic_variables': SSHAnsibleService.AVAILABLE_VARIABLES,
            'custom_parameters': {
                'description': 'Кастомные параметры можно задавать с явными значениями',
                'format': '{parameter_name=value}',
                'examples': [
                    '{onlydeliver=true}',
                    '{env=production}',
                    '{timeout=30}',
                    '{debug=false}'
                ],
                'validation': {
                    'name_pattern': '^[a-zA-Z_][a-zA-Z0-9_]*$',
                    'value_pattern': '^[a-zA-Z0-9_\\-\\./:\\@\\=\\s]+$',
                    'description': 'Имя должно начинаться с буквы или _, значение может содержать буквы, цифры и безопасные символы'
                }
            },
            'usage_examples': [
                {
                    'description': 'Только динамические параметры',
                    'playbook_path': '/playbook.yml {server} {app} {distr_url}',
                    'result': 'ansible-playbook /playbook.yml -e server="srv01" -e app="myapp" -e distr_url="http://nexus/app.jar"'
                },
                {
                    'description': 'Смешанные параметры',
                    'playbook_path': '/playbook.yml {server} {app} {onlydeliver=true} {env=staging}',
                    'result': 'ansible-playbook /playbook.yml -e server="srv01" -e app="myapp" -e onlydeliver="true" -e env="staging"'
                },
                {
                    'description': 'Только кастомные параметры',
                    'playbook_path': '/custom.yml {deploy_mode=blue-green} {rollback=false} {timeout=300}',
                    'result': 'ansible-playbook /custom.yml -e deploy_mode="blue-green" -e rollback="false" -e timeout="300"'
                }
            ],
            'note': 'Динамические параметры берутся из контекста события, кастомные используют явные значения'
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка переменных: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
@bp.route('/ansible/validate-playbook', methods=['POST'])
def validate_playbook_config():
    """
    Валидация конфигурации playbook с параметрами
    
    Body:
    {
        "playbook_path": "/path/to/playbook.yml {server} {app} {onlydeliver=true}"
    }
    """
    try:
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле 'playbook_path'"
            }), 400
        
        playbook_path_with_params = data['playbook_path']
        
        from app.services.ssh_ansible_service import get_ssh_ansible_service, SSHAnsibleService
        ssh_service = get_ssh_ansible_service()
        
        # Парсим конфигурацию
        playbook_config = ssh_service.parse_playbook_config(playbook_path_with_params)
        
        # Валидируем параметры
        is_valid, invalid_params = ssh_service.validate_parameters(playbook_config.parameters)
        
        # Формируем детальную информацию о параметрах
        parameters_info = []
        for param in playbook_config.parameters:
            param_info = {
                'name': param.name,
                'type': 'custom' if param.is_custom else 'dynamic',
                'value': param.value if param.is_custom else None,
                'is_valid': True
            }
            
            if param.is_custom:
                param_info['description'] = f"Кастомный параметр со значением '{param.value}'"
            else:
                if param.name in SSHAnsibleService.AVAILABLE_VARIABLES:
                    param_info['description'] = SSHAnsibleService.AVAILABLE_VARIABLES[param.name]
                else:
                    param_info['is_valid'] = False
                    param_info['description'] = "Неизвестный динамический параметр"
            
            parameters_info.append(param_info)
        
        # Пример команды
        example_vars = {}
        for param in playbook_config.parameters:
            if param.is_custom:
                # Для кастомных параметров используем их явные значения
                example_vars[param.name] = param.value or ''
            else:
                # Для динамических параметров генерируем примеры
                if param.name == 'server':
                    example_vars[param.name] = 'web01.example.com'
                elif param.name in ['app', 'app_name']:
                    example_vars[param.name] = 'myapp'
                elif param.name == 'distr_url':
                    example_vars[param.name] = 'http://nexus/app.jar'
                elif param.name == 'restart_mode':
                    example_vars[param.name] = 'now'
                elif param.name == 'image_url':
                    example_vars[param.name] = 'docker.io/myapp:latest'
                elif param.name == 'app_id':
                    example_vars[param.name] = '1'
                elif param.name == 'server_id':
                    example_vars[param.name] = '1'
                else:
                    example_vars[param.name] = '<значение>'
        
        example_command = f"ansible-playbook {playbook_config.path}"
        for key, value in example_vars.items():
            example_command += f' -e {key}="{value}"'
        
        # Подсчет динамических и кастомных параметров
        dynamic_count = sum(1 for p in playbook_config.parameters if not p.is_custom)
        custom_count = sum(1 for p in playbook_config.parameters if p.is_custom)

        response = {
            'success': True,
            'is_valid': is_valid,
            'playbook_path': playbook_config.path,
            'parameters': parameters_info,
            'invalid_parameters': invalid_params,
            'example_command': example_command,
            # Для совместимости с фронтендом
            'dynamic_count': dynamic_count,
            'custom_count': custom_count,
            'statistics': {
                'total_parameters': len(playbook_config.parameters),
                'dynamic_parameters': dynamic_count,
                'custom_parameters': custom_count
            }
        }

        if not is_valid:
            response['message'] = f"Найдены недопустимые параметры: {', '.join(invalid_params)}"
            response['hint'] = "Проверьте имена динамических параметров и формат кастомных параметров"
        else:
            response['message'] = "Все параметры валидны и готовы к использованию"

        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Ошибка при валидации playbook конфигурации: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/applications/<int:app_id>/test-playbook', methods=['POST'])
def test_playbook_execution(app_id):
    """
    Тестовый прогон - показывает какая команда будет выполнена (dry run)
    Поддерживает как динамические, так и кастомные параметры
    
    Body:
    {
        "playbook_path": "/playbook.yml {server} {app} {distr_url} {onlydeliver=true}",
        "action": "update",
        "distr_url": "http://nexus/app.jar",
        "restart_mode": "now"
    }
    """
    try:
        from app.models.application import Application
        from app.models.server import Server
        from app.services.ssh_ansible_service import get_ssh_ansible_service
        
        # Получаем приложение
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        # Получаем сервер
        server = app.server
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер для приложения {app.name} не найден"
            }), 404
        
        # Получаем данные из запроса
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле 'playbook_path'"
            }), 400
        
        playbook_path = data['playbook_path']
        action = data.get('action', 'update')
        
        # Получаем сервис
        ssh_service = get_ssh_ansible_service()
        
        # Парсим конфигурацию
        playbook_config = ssh_service.parse_playbook_config(playbook_path)
        
        # Валидируем
        is_valid, invalid_params = ssh_service.validate_parameters(playbook_config.parameters)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': f"Недопустимые параметры: {', '.join(invalid_params)}",
                'invalid_parameters': invalid_params,
                'hint': "Проверьте параметры playbook"
            }), 400
        
        # Определяем image_url для Docker приложений
        image_url = None
        if hasattr(app, 'deployment_type') and app.deployment_type == 'docker':
            if hasattr(app, 'docker_image'):
                image_url = app.docker_image
        elif hasattr(app, 'app_type') and app.app_type == 'docker':
            if hasattr(app, 'docker_image'):
                image_url = app.docker_image
        
        # Формируем контекст
        context_vars = ssh_service.build_context_vars(
            server_name=server.name,
            app_name=app.name,
            app_id=app.id,
            server_id=server.id,
            distr_url=data.get('distr_url'),
            restart_mode=data.get('restart_mode'),
            image_url=image_url
        )
        
        # Формируем extra_vars с учетом кастомных параметров
        extra_vars = ssh_service.build_extra_vars(playbook_config, context_vars)
        
        # Разделяем параметры по типам для отображения
        dynamic_params = {}
        custom_params = {}
        
        for param in playbook_config.parameters:
            if param.is_custom:
                custom_params[param.name] = param.value
            else:
                if param.name in extra_vars:
                    dynamic_params[param.name] = extra_vars[param.name]
        
        # Формируем команду
        playbook_full_path = os.path.join(
            ssh_service.ssh_config.ansible_path,
            playbook_config.path.lstrip('/')
        )
        
        ansible_cmd = ssh_service.build_ansible_command(
            playbook_full_path,
            extra_vars,
            verbose=True
        )
        
        # Формируем читаемую команду
        readable_command = ' '.join(ansible_cmd)
        
        return jsonify({
            'success': True,
            'action': action,
            'application': {
                'id': app.id,
                'name': app.name,
                'type': getattr(app, 'app_type', 'standard')
            },
            'server': {
                'id': server.id,
                'name': server.name
            },
            'playbook_config': {
                'path': playbook_config.path,
                'full_path': playbook_full_path,
                'total_parameters': len(playbook_config.parameters)
            },
            'parameters': {
                'dynamic': {
                    'description': 'Параметры из контекста события',
                    'values': dynamic_params
                },
                'custom': {
                    'description': 'Параметры с явными значениями',
                    'values': custom_params
                }
            },
            'extra_vars': extra_vars,
            'command': readable_command,
            'message': 'Это тестовый прогон. Команда не была выполнена.',
            'note': 'Динамические параметры взяты из контекста, кастомные используют явные значения'
        })
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании playbook: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

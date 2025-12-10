from flask import jsonify, request
import logging
from collections import defaultdict
from sqlalchemy.orm import joinedload, selectinload

from app import db
from app.config import Config
from app.models.server import Server
from app.models.application_instance import ApplicationInstance
from app.models.application_group import ApplicationGroup
from app.models.event import Event
from app.models.tag import Tag, ApplicationInstanceTag, ApplicationGroupTag
from app.tasks.queue import task_queue
from app.models.task import Task
from app.api import bp

# Алиас для обратной совместимости
Application = ApplicationInstance

logger = logging.getLogger(__name__)


@bp.route('/applications', methods=['GET'])
def get_applications():
    """Получение списка всех приложений"""
    try:
        server_id = request.args.get('server_id', type=int)
        app_type = request.args.get('type')

        # Формируем базовый запрос с eager loading для server и group
        # Примечание: tags используют lazy='dynamic', поэтому загружаем отдельно
        query = Application.query.options(
            joinedload(Application.server),
            joinedload(Application.group)
        )

        # Применяем фильтры, если они указаны
        if server_id:
            query = query.filter_by(server_id=server_id)

        if app_type:
            query = query.filter_by(app_type=app_type)

        applications = query.all()
        app_ids = [app.id for app in applications]
        group_ids = {app.group_id for app in applications if app.group_id}

        # Предзагружаем теги приложений одним запросом
        app_tags_map = defaultdict(list)
        if app_ids:
            app_tags_query = db.session.query(
                ApplicationInstanceTag.application_id,
                Tag
            ).join(Tag).filter(ApplicationInstanceTag.application_id.in_(app_ids))

            for app_id, tag in app_tags_query:
                app_tags_map[app_id].append(tag)

        # Предзагружаем теги групп одним запросом
        group_tags_map = defaultdict(list)
        if group_ids:
            group_tags_query = db.session.query(
                ApplicationGroupTag.group_id,
                Tag
            ).join(Tag).filter(ApplicationGroupTag.group_id.in_(group_ids))

            for group_id, tag in group_tags_query:
                group_tags_map[group_id].append(tag)

        result = []
        for app in applications:
            # Используем уже загруженные данные (eager loading)
            server = app.server

            # Получаем теги из предзагруженных map (defaultdict возвращает [] для отсутствующих ключей)
            tags = [t.to_dict(include_usage_count=False) for t in app_tags_map[app.id]]
            group_tags = [t.to_dict(include_usage_count=False) for t in group_tags_map.get(app.group_id, [])]

            result.append({
                'id': app.id,
                'name': app.name,
                'server_id': app.server_id,
                'server_name': server.name if server else None,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'path': app.path,
                'group_id': app.group_id,
                'group_name': app.group_name,
                'instance_number': app.instance_number,
                'start_time': app.start_time.isoformat() if app.start_time else None,
                'tags': tags,
                'group_tags': group_tags,
                'effective_playbook_path': app.get_effective_playbook_path()
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
        events = Event.query.filter_by(instance_id=app.id).order_by(Event.timestamp.desc()).limit(10).all()
        events_list = []

        for event in events:
            events_list.append({
                'id': event.id,
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type,
                'description': event.description,
                'status': event.status
            })

        # Получаем теги приложения
        tags_list = []
        for tag in app.tags.all():
            tags_list.append({
                'id': tag.id,
                'name': tag.name,
                'display_name': tag.display_name,
                'css_class': tag.css_class,
                'border_color': tag.border_color,
                'text_color': tag.text_color
            })

        # Получаем теги группы (унаследованные)
        group_tags_list = []
        if app.group:
            for tag in app.group.tags.all():
                group_tags_list.append({
                    'id': tag.id,
                    'name': tag.name,
                    'display_name': tag.display_name,
                    'css_class': tag.css_class,
                    'border_color': tag.border_color,
                    'text_color': tag.text_color
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
            'events': events_list,
            'tags': tags_list,
            'group_tags': group_tags_list
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
        mode = data.get('mode', data.get('restart_mode', 'immediate'))  # Поддержка старого параметра restart_mode

        # Валидация: night-restart не поддерживается для Docker
        if mode == 'night-restart' and app.app_type == 'docker':
            return jsonify({
                'success': False,
                'error': 'Режим "В рестарт" не поддерживается для Docker-приложений'
            }), 400

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

        # Определяем путь к playbook (app уже является ApplicationInstance после рефакторинга)
        # Для режима night-restart используем специальный плейбук
        if mode == 'night-restart':
            playbook_path = Config.NIGHT_RESTART_PLAYBOOK
            logger.info(f"Режим night-restart: используется плейбук {playbook_path}")
        else:
            playbook_path = app.get_effective_playbook_path()
            logger.info(f"Используется playbook: {playbook_path}")

        # Приоритет 3: Дефолтный путь в зависимости от типа приложения
        if not playbook_path:
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
                'mode': mode,
                'playbook_path': playbook_path
            },
            server_id=server.id,
            instance_id=app.id
        )

        # Добавляем задачу в очередь для асинхронной обработки
        task_queue.add_task(task)

        # Логируем событие
        event = Event(
            event_type='update',
            description=f"Запущено обновление {app.app_type} приложения {app.instance_name} на версию из {distr_url}",
            status='pending',
            server_id=server.id,
            instance_id=app.id
        )
        db.session.add(event)
        db.session.commit()

        logger.info(f"Задача обновления {app.instance_name} добавлена в очередь (task_id: {task.id})")

        # Возвращаем успешный ответ сразу - обработка будет происходить асинхронно
        return jsonify({
            'success': True,
            'message': f"Обновление приложения {app.instance_name} добавлено в очередь",
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


@bp.route('/applications/batch_update', methods=['POST'])
def batch_update_applications():
    """
    Групповое обновление приложений с настраиваемой группировкой

    Принимает:
        app_ids: список ID приложений
        distr_url: URL дистрибутива
        mode: режим обновления (deliver, immediate, night-restart)

    Группирует приложения согласно стратегии группы (batch_grouping_strategy):
        - by_group: по (server, playbook, group_id) - разные группы отдельно [по умолчанию]
        - by_server: по (server, playbook) - игнорировать group_id
        - by_instance_name: по (server, playbook, original_name)
        - no_grouping: каждое приложение в отдельной задаче
    """
    try:
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400

        app_ids = data.get('app_ids', [])
        distr_url = data.get('distr_url')
        mode = data.get('mode', 'immediate')
        orchestrator_playbook = data.get('orchestrator_playbook')
        drain_wait_time = data.get('drain_wait_time')

        if not app_ids or len(app_ids) == 0:
            return jsonify({
                'success': False,
                'error': "Не указаны приложения для обновления"
            }), 400

        if not distr_url:
            return jsonify({
                'success': False,
                'error': "Не указан URL дистрибутива"
            }), 400

        # Загружаем все приложения и их instances
        applications = Application.query.filter(Application.id.in_(app_ids)).all()

        if len(applications) != len(app_ids):
            return jsonify({
                'success': False,
                'error': "Некоторые приложения не найдены"
            }), 404

        # Валидация: night-restart не поддерживается для Docker
        if mode == 'night-restart':
            docker_apps = [a for a in applications if a.app_type == 'docker']
            if docker_apps:
                docker_names = [a.name for a in docker_apps]
                return jsonify({
                    'success': False,
                    'error': f'Режим "В рестарт" не поддерживается для Docker-приложений: {docker_names}'
                }), 400

        # Группируем приложения согласно стратегии группы
        groups = defaultdict(list)

        # Определяем playbook_path для режима night-restart один раз
        night_restart_playbook = Config.NIGHT_RESTART_PLAYBOOK if mode == 'night-restart' else None

        for app in applications:
            # app уже является ApplicationInstance после рефакторинга
            # Определяем playbook_path
            if night_restart_playbook:
                playbook_path = night_restart_playbook
            else:
                playbook_path = app.get_effective_playbook_path()

            # Определяем ключ группировки на основе стратегии
            group = app.group
            strategy = group.get_batch_grouping_strategy() if group else 'by_group'

            # Проверяем, используется ли оркестратор
            # Если да - убираем server_id из ключа, т.к. оркестратор сам управляет серверами
            use_orchestrator = orchestrator_playbook and orchestrator_playbook != 'none'

            if strategy == 'by_group':
                # Группировка по (server, playbook, group_id) - default
                # Если оркестратор, то без server_id
                if use_orchestrator:
                    group_key = (playbook_path, group.id if group else None)
                else:
                    group_key = (app.server_id, playbook_path, group.id if group else None)
            elif strategy == 'by_server':
                # Группировка только по (server, playbook)
                # Если оркестратор, то только по playbook
                if use_orchestrator:
                    group_key = (playbook_path,)
                else:
                    group_key = (app.server_id, playbook_path)
            elif strategy == 'by_instance_name':
                # Группировка по (server, playbook, original_name)
                # Если оркестратор, то без server_id
                if use_orchestrator:
                    group_key = (playbook_path, instance.original_name if instance else app.name)
                else:
                    group_key = (app.server_id, playbook_path, instance.original_name if instance else app.name)
            elif strategy == 'no_grouping':
                # Каждое приложение в отдельной задаче
                group_key = (app.id,)
            else:
                # Fallback на by_group
                if use_orchestrator:
                    group_key = (playbook_path, group.id if group else None)
                else:
                    group_key = (app.server_id, playbook_path, group.id if group else None)

            logger.info(f"Группировка {app.name}: strategy={strategy}, orchestrator={use_orchestrator}, key={group_key}")
            groups[group_key].append(app)

        # Создаем задачи для каждой группы
        logger.info(f"Создано {len(groups)} групп для {len(applications)} приложений (стратегии применены)")
        created_tasks = []

        for group_key, apps_in_group in groups.items():
            # Собираем ID приложений
            grouped_app_ids = [app.id for app in apps_in_group]

            # Получаем playbook_path и server_id из первого приложения группы
            first_app = apps_in_group[0]
            # first_app уже является ApplicationInstance после рефакторинга
            # playbook_path уже определён в цикле группировки выше
            if night_restart_playbook:
                playbook_path = night_restart_playbook
            else:
                playbook_path = first_app.get_effective_playbook_path()

            # Создаем задачу для группы
            task = Task(
                task_type='update',
                params={
                    'app_ids': grouped_app_ids,
                    'distr_url': distr_url,
                    'mode': mode,
                    'playbook_path': playbook_path,
                    'orchestrator_playbook': orchestrator_playbook,
                    'drain_wait_time': drain_wait_time
                },
                server_id=first_app.server_id,
                instance_id=grouped_app_ids[0]
            )

            # Добавляем задачу в очередь
            task_queue.add_task(task)
            created_tasks.append(task.id)

            # Логируем события для каждого приложения в группе
            app_names_for_log = ','.join([app.instance_name for app in apps_in_group])
            for app in apps_in_group:
                event = Event(
                    event_type='update',
                    description=f"Запущено обновление {app.app_type} приложения {app.instance_name} на версию из {distr_url} (группа: {app_names_for_log})",
                    status='pending',
                    server_id=first_app.server_id,
                    instance_id=app.id
                )
                db.session.add(event)

            logger.info(f"Создана задача для группы (IDs: {grouped_app_ids}, names: {app_names_for_log}, task_id: {task.id})")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Создано задач: {len(created_tasks)} для {len(applications)} приложений",
            'task_ids': created_tasks,
            'groups_count': len(groups)
        })

    except Exception as e:
        logger.error(f"Ошибка при групповом обновлении приложений: {str(e)}")
        db.session.rollback()
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
            params={
                'action': action,
                'server_name': server.name,
                'app_name': app.instance_name
            },
            server_id=server.id,
            instance_id=app.id
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
                params={
                    'action': action,
                    'server_name': server.name,
                    'app_name': app.instance_name
                },
                server_id=server.id,
                instance_id=app.id
            )

            task_queue.add_task(task)

            results.append({
                'app_id': app_id,
                'app_name': app.instance_name,
                'success': True,
                'message': f"{action} для приложения {app.instance_name} поставлен в очередь",
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

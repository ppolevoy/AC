from flask import jsonify, request
import logging
import re

from app import db
from app.models.server import Server
from app.models.application_instance import ApplicationInstance
from app.models.task import Task
Application = ApplicationInstance  # Алиас
from app.tasks.queue import task_queue
from app.api import bp
from app.services.ssh_ansible_service import SSHAnsibleService

logger = logging.getLogger(__name__)


def parse_ansible_summary(output: str) -> list:
    """
    Парсит PLAY RECAP из вывода Ansible.
    Возвращает список словарей с результатами для каждого хоста/плейбука.

    Формат PLAY RECAP:
    PLAY RECAP *********************************************************************
    localhost                  : ok=10   changed=2    unreachable=0    failed=0    skipped=1

    Args:
        output: Полный вывод Ansible

    Returns:
        Список словарей с summary для каждого PLAY RECAP
    """
    if not output:
        return []

    summaries = []

    # Находим все блоки PLAY RECAP
    # Паттерн для поиска PLAY RECAP и последующих строк с результатами
    recap_pattern = re.compile(
        r'PLAY RECAP \*+\s*\n((?:[^\n]+\n)*?)(?=\n(?:PLAY |$)|\Z)',
        re.MULTILINE
    )

    # Паттерн для парсинга строки с результатами хоста
    host_pattern = re.compile(
        r'^(\S+)\s*:\s*'
        r'ok=(\d+)\s+'
        r'changed=(\d+)\s+'
        r'unreachable=(\d+)\s+'
        r'failed=(\d+)'
        r'(?:\s+skipped=(\d+))?'
        r'(?:\s+rescued=(\d+))?'
        r'(?:\s+ignored=(\d+))?',
        re.MULTILINE
    )

    # Ищем все PLAY RECAP блоки
    for match in recap_pattern.finditer(output):
        recap_block = match.group(1)

        # Парсим каждую строку хоста в блоке
        for host_match in host_pattern.finditer(recap_block):
            summary = {
                'host': host_match.group(1),
                'ok': int(host_match.group(2)),
                'changed': int(host_match.group(3)),
                'unreachable': int(host_match.group(4)),
                'failed': int(host_match.group(5)),
                'skipped': int(host_match.group(6)) if host_match.group(6) else 0,
                'rescued': int(host_match.group(7)) if host_match.group(7) else 0,
                'ignored': int(host_match.group(8)) if host_match.group(8) else 0
            }
            summaries.append(summary)

    return summaries


def parse_display_summary_tasks(output: str) -> list:
    """
    Извлекает содержимое из TASK [Display.*summary] блоков.
    Это более читаемая сводка, которую плейбуки выводят в конце.

    Обрабатывает два формата:
    1. Прямой вывод с реальными переносами строк
    2. Escaped вывод с \\n внутри строк (от вложенных плейбуков)

    Args:
        output: Полный вывод Ansible

    Returns:
        Список словарей с содержимым summary tasks
    """
    if not output:
        return []

    summaries = []
    seen_content = set()  # Для дедупликации

    # Паттерн 1: Прямой формат (реальные переносы строк)
    # TASK [Display summary] ***
    # ok: [localhost] => {
    #     "msg": "..."
    # }
    pattern1 = re.compile(
        r'TASK \[([^\]]*[Ss]ummary[^\]]*)\] \*+\s*\n'
        r'(?:ok|changed): \[([^\]]+)\] => \{\s*\n'
        r'\s*"msg":\s*(.+?)\n\}',
        re.DOTALL
    )

    for match in pattern1.finditer(output):
        task_name = match.group(1)
        host = match.group(2)
        msg_content = match.group(3).strip()

        content = _parse_msg_content(msg_content)
        if content:
            content_hash = hash(content)
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                # Добавляем хост в название если это не localhost
                display_name = task_name if host == 'localhost' else f"{task_name} ({host})"
                summaries.append({
                    'task_name': display_name,
                    'content': content
                })

    # Паттерн 2: Escaped формат (\\n вместо реальных переносов)
    # Обычно появляется когда include_tasks логирует вывод
    pattern2 = re.compile(
        r'TASK \[([^\]]*[Ss]ummary[^\]]*)\] \*+\\n'
        r'(?:ok|changed): \[([^\]]+)\] => \{\\n'
        r'\s*\\"msg\\":\s*(.+?)(?:\\n\}|"\s*\])',
        re.DOTALL
    )

    for match in pattern2.finditer(output):
        task_name = match.group(1)
        host = match.group(2)
        msg_content = match.group(3).strip()

        # Для escaped формата сначала unescape
        msg_content = msg_content.replace('\\n', '\n').replace('\\"', '"')
        content = _parse_msg_content(msg_content)
        if content:
            content_hash = hash(content)
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                display_name = task_name if host == 'localhost' else f"{task_name} ({host})"
                summaries.append({
                    'task_name': display_name,
                    'content': content
                })

    return summaries


def _parse_msg_content(msg_content: str) -> str:
    """
    Парсит содержимое msg из debug task.

    Args:
        msg_content: Сырое содержимое msg

    Returns:
        Отформатированная строка
    """
    try:
        msg_content = msg_content.strip()

        if msg_content.startswith('['):
            # Массив строк - извлекаем строки
            lines = re.findall(r'"([^"]*)"', msg_content)
            return '\n'.join(lines)
        elif msg_content.startswith('"'):
            # Одна строка (может содержать \n)
            content = msg_content.strip('"')
            content = content.replace('\\n', '\n')
            return content
        else:
            return msg_content
    except Exception:
        return ""


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
            params = task.params or {}
            app_ids = params.get('app_ids')
            if app_ids and isinstance(app_ids, list) and len(app_ids) > 1:
                # Групповая задача - загружаем приложения и формируем строку
                apps = Application.query.filter(Application.id.in_(app_ids)).all()
                if apps:
                    task_data['application_name'] = ','.join([app.instance_name for app in apps])
                else:
                    task_data['application_name'] = f"Apps: {','.join(map(str, app_ids))}"
            elif task.instance_id:
                # Одиночная задача
                app = Application.query.get(task.instance_id)
                task_data['application_name'] = app.instance_name if app else None
            else:
                task_data['application_name'] = None

            if task.server_id:
                server = Server.query.get(task.server_id)
                task_data['server_name'] = server.name if server else None
            else:
                task_data['server_name'] = None

            # Добавляем информацию об оркестраторе для задач обновления
            orchestrator = params.get('orchestrator_playbook')
            if orchestrator and orchestrator != 'none':
                task_data['orchestrator_playbook'] = orchestrator
            else:
                task_data['orchestrator_playbook'] = None

            # Добавляем текущий TASK для выполняющихся задач
            if task.status == 'processing':
                progress = SSHAnsibleService.get_task_progress(task.id)
                task_data['current_task'] = progress.get('current_task', '') if progress else None
            else:
                task_data['current_task'] = None

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
        params = task.params or {}
        app_ids = params.get('app_ids')
        if app_ids and isinstance(app_ids, list) and len(app_ids) > 1:
            # Групповая задача - загружаем приложения и формируем строку
            apps = Application.query.filter(Application.id.in_(app_ids)).all()
            if apps:
                task_data['application_name'] = ','.join([app.instance_name for app in apps])
            else:
                task_data['application_name'] = f"Apps: {','.join(map(str, app_ids))}"
        elif task.application_id:
            # Одиночная задача
            app = Application.query.get(task.application_id)
            task_data['application_name'] = app.instance_name if app else None
        else:
            task_data['application_name'] = None

        if task.server_id:
            server = Server.query.get(task.server_id)
            task_data['server_name'] = server.name if server else None
        else:
            task_data['server_name'] = None

        # Добавляем информацию об оркестраторе для задач обновления
        orchestrator = params.get('orchestrator_playbook')
        if orchestrator and orchestrator != 'none':
            task_data['orchestrator_playbook'] = orchestrator
        else:
            task_data['orchestrator_playbook'] = None

        # Добавляем текущий TASK для выполняющихся задач
        if task.status == 'processing':
            progress = SSHAnsibleService.get_task_progress(task.id)
            task_data['current_task'] = progress.get('current_task', '') if progress else None
        else:
            task_data['current_task'] = None

        # Парсим данные из результата Ansible для отображения
        # Поддерживаем все типы задач: update, start, stop, restart
        if task.result:
            # PLAY RECAP - статистика выполнения
            task_data['ansible_summary'] = parse_ansible_summary(task.result)
            # Display summary tasks - читаемые сводки из плейбуков
            task_data['display_summaries'] = parse_display_summary_tasks(task.result)
        else:
            task_data['ansible_summary'] = []
            task_data['display_summaries'] = []

        # Добавляем параметры запуска для start/stop/restart задач
        if task.task_type in ['start', 'stop', 'restart']:
            task_data['action'] = task.task_type
            task_data['playbook_params'] = {
                'server': task_data.get('server_name'),
                'app_name': task_data.get('application_name'),
                'action': task.task_type
            }

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


@bp.route('/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """
    Отмена задачи.

    Поддерживает отмену:
    - pending задач: помечает как отмененную, worker пропустит при обработке
    - processing задач: отправляет SIGTERM процессу Ansible
    """
    try:
        # Получаем задачу из БД
        task = Task.query.get(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': f"Задача {task_id} не найдена"
            }), 404

        if task.cancelled:
            return jsonify({
                'success': False,
                'error': "Задача уже отменена"
            }), 400

        # Обработка в зависимости от статуса задачи
        if task.status == 'pending':
            # Отмена ожидающей задачи через TaskQueue
            success, message = task_queue.cancel_pending_task(task_id)

            if success:
                logger.info(f"Задача {task_id} (pending) отменена пользователем")
                return jsonify({
                    'success': True,
                    'message': 'Задача отменена'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': message
                }), 400

        elif task.status == 'processing':
            # Отмена выполняющейся задачи через SSHAnsibleService
            success, message = SSHAnsibleService.cancel_task(task_id)

            if success:
                # Помечаем задачу как отмененную
                task.cancelled = True
                task.status = 'failed'
                task.error = 'Задача отменена пользователем'
                db.session.commit()

                logger.info(f"Задача {task_id} (processing) отменена пользователем")

                return jsonify({
                    'success': True,
                    'message': 'Задача отменена'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': message
                }), 400
        else:
            return jsonify({
                'success': False,
                'error': f"Невозможно отменить задачу в статусе '{task.status}'"
            }), 400

    except Exception as e:
        logger.error(f"Ошибка при отмене задачи {task_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

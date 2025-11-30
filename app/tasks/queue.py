"""
Модуль управления очередью задач.

Задачи хранятся персистентно в БД (таблица tasks).
При перезагрузке сервера незавершённые задачи помечаются как failed.
"""
import uuid
import queue
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskQueue:
    """
    Класс для управления очередью задач.
    Задачи хранятся в БД, очередь используется только для обработки.
    """

    def __init__(self, app=None):
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.app = app

        # Если приложение уже передано, инициализируем с ним
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Инициализация с приложением Flask"""
        self.app = app

        # Помечаем незавершенные задачи как failed при старте
        if app:
            with app.app_context():
                self.mark_interrupted_tasks()

    def mark_interrupted_tasks(self):
        """
        Находит незавершенные задачи в БД и помечает их как failed
        из-за перезапуска сервера.
        """
        try:
            from app import db
            from app.models.task import Task

            # Находим все незавершенные задачи (pending или processing)
            interrupted = Task.query.filter(
                Task.status.in_(['pending', 'processing'])
            ).all()

            if not interrupted:
                logger.info("Незавершенных задач не найдено")
                return

            logger.info(f"Найдено {len(interrupted)} незавершенных задач")

            # Помечаем все как failed
            for task in interrupted:
                task.status = 'failed'
                task.completed_at = datetime.utcnow()
                task.error = 'Прервано перезагрузкой сервера'
                logger.info(f"Задача {task.id[:8]}... ({task.task_type}) помечена как failed")

            db.session.commit()
            logger.info(f"Все {len(interrupted)} незавершенных задач помечены как failed")

        except Exception as e:
            logger.error(f"Ошибка при обработке незавершенных задач: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                from app import db
                db.session.rollback()
            except:
                pass

    def add_task(self, task):
        """
        Добавление задачи в очередь.

        Args:
            task: Экземпляр модели Task (уже созданный, но не сохранённый)
                  или dict с параметрами для создания Task

        Returns:
            Task: Добавленная задача
        """
        if not self.app:
            raise RuntimeError("TaskQueue не инициализирован с приложением Flask")

        with self.app.app_context():
            from app import db
            from app.models.task import Task as TaskModel

            # Если передан dict, создаём Task
            if isinstance(task, dict):
                task = TaskModel(
                    id=str(uuid.uuid4()),
                    task_type=task.get('task_type'),
                    params=task.get('params', {}),
                    server_id=task.get('server_id'),
                    instance_id=task.get('instance_id') or task.get('application_id'),
                    status='pending'
                )

            # Если Task ещё не имеет ID, генерируем
            if not task.id:
                task.id = str(uuid.uuid4())

            # Сохраняем в БД
            db.session.add(task)
            db.session.commit()

            logger.info(f"Задача {task.id[:8]}... ({task.task_type}) добавлена в очередь")

            # Добавляем ID в очередь для обработки
            self.queue.put(task.id)

            return task

    def get_task(self, task_id):
        """
        Получение информации о задаче по ID.

        Args:
            task_id: ID задачи

        Returns:
            Task: Найденная задача или None
        """
        if not self.app:
            return None

        with self.app.app_context():
            from app.models.task import Task
            return Task.query.get(task_id)

    def get_tasks(self, status=None, application_id=None, server_id=None, instance_id=None):
        """
        Получение списка задач с возможностью фильтрации.

        Args:
            status: Статус задачи для фильтрации (опционально)
            application_id: ID приложения для фильтрации (опционально, алиас instance_id)
            server_id: ID сервера для фильтрации (опционально)
            instance_id: ID экземпляра приложения для фильтрации (опционально)

        Returns:
            list: Список задач, соответствующих условиям фильтрации
        """
        if not self.app:
            return []

        with self.app.app_context():
            from app.models.task import Task

            query = Task.query

            if status:
                query = query.filter(Task.status == status)

            # instance_id или application_id (для обратной совместимости)
            filter_instance_id = instance_id or application_id
            if filter_instance_id:
                query = query.filter(Task.instance_id == filter_instance_id)

            if server_id:
                query = query.filter(Task.server_id == server_id)

            return query.order_by(Task.created_at.desc()).all()

    def start_processing(self):
        """Запуск потока обработки задач из очереди."""
        if self.thread and self.thread.is_alive():
            logger.warning("Обработчик задач уже запущен")
            return

        # Проверяем, что приложение установлено
        if not self.app:
            logger.error("Невозможно запустить обработчик задач без контекста приложения")
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._process_tasks, daemon=True)
        self.thread.start()
        logger.info("Обработчик задач запущен")

    def stop_processing(self):
        """Остановка потока обработки задач."""
        if not self.thread or not self.thread.is_alive():
            logger.warning("Обработчик задач не запущен")
            return

        logger.info("Останавливаем обработчик задач...")
        self.stop_event.set()
        self.thread.join(timeout=30)
        logger.info("Обработчик задач остановлен")

    def _process_tasks(self):
        """Функция обработки задач из очереди."""
        logger.info("Запущен процесс обработки задач")

        while not self.stop_event.is_set():
            try:
                # Попытка получить задачу из очереди с таймаутом
                try:
                    task_id = self.queue.get(timeout=1)
                except queue.Empty:
                    continue

                # Получаем задачу из БД
                with self.app.app_context():
                    from app import db
                    from app.models.task import Task

                    task = Task.query.get(task_id)
                    if not task:
                        logger.warning(f"Задача {task_id} не найдена в БД")
                        continue

                    # Сохраняем тип задачи для использования вне контекста
                    task_type = task.task_type

                    # Обновляем статус задачи - начало обработки
                    task.status = "processing"
                    task.started_at = datetime.utcnow()
                    db.session.commit()

                logger.info(f"Обработка задачи {task_id[:8]}... ({task_type})")

                try:
                    # Обработка задачи в зависимости от типа
                    # Передаём task_id, чтобы перезагружать объект в контексте
                    if task_type == "start":
                        result = self._process_start_task(task_id)
                    elif task_type == "stop":
                        result = self._process_stop_task(task_id)
                    elif task_type == "restart":
                        result = self._process_restart_task(task_id)
                    elif task_type == "update":
                        result = self._process_update_task(task_id)
                    else:
                        raise ValueError(f"Неизвестный тип задачи: {task_type}")

                    # Обновляем задачу как успешно завершённую
                    with self.app.app_context():
                        from app import db
                        from app.models.task import Task

                        task = Task.query.get(task_id)
                        if task:
                            task.status = "completed"
                            task.completed_at = datetime.utcnow()
                            task.result = result
                            db.session.commit()

                    logger.info(f"Задача {task_id[:8]}... успешно выполнена")

                except Exception as e:
                    # Обрабатываем ошибку
                    with self.app.app_context():
                        from app import db
                        from app.models.task import Task

                        task = Task.query.get(task_id)
                        if task:
                            task.status = "failed"
                            task.completed_at = datetime.utcnow()
                            task.error = str(e)
                            db.session.commit()

                    logger.error(f"Ошибка при выполнении задачи {task_id[:8]}...: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())

                finally:
                    # Отмечаем задачу как обработанную в очереди
                    self.queue.task_done()

            except Exception as e:
                logger.error(f"Непредвиденная ошибка в обработчике задач: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())

        logger.info("Процесс обработки задач завершен")

    def _process_start_task(self, task_id):
        """
        Обработка задачи запуска приложения.

        Args:
            task_id: ID задачи

        Returns:
            str: Результат выполнения задачи
        """
        import asyncio

        if not self.app:
            raise RuntimeError("Отсутствует контекст приложения для работы с базой данных")

        # Получаем информацию о приложении внутри контекста приложения
        with self.app.app_context():
            from app.services.ansible_service import AnsibleService
            from app.models.application_instance import ApplicationInstance
            from app.models.server import Server
            from app.models.task import Task

            task = Task.query.get(task_id)
            if not task:
                raise ValueError(f"Задача {task_id} не найдена")

            app = ApplicationInstance.query.get(task.instance_id)
            if not app:
                raise ValueError(f"Приложение с id {task.instance_id} не найдено")

            server = Server.query.get(app.server_id)
            if not server:
                raise ValueError(f"Сервер для приложения {app.instance_name} не найден")

            # Сохраняем необходимые данные для использования вне контекста приложения
            app_id = app.id
            app_name = app.instance_name
            server_name = server.name

        # Создаем event loop внутри метода
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Запускаем асинхронную функцию внутри event loop
            with self.app.app_context():
                success, message = loop.run_until_complete(
                    AnsibleService.manage_application(
                        server_name=server_name,
                        app_name=app_name,
                        app_id=app_id,
                        action="start"
                    )
                )

                if not success:
                    raise Exception(message)

                return message
        finally:
            # Закрываем event loop
            loop.close()

    def _process_stop_task(self, task_id):
        """
        Обработка задачи остановки приложения.

        Args:
            task_id: ID задачи

        Returns:
            str: Результат выполнения задачи
        """
        import asyncio

        if not self.app:
            raise RuntimeError("Отсутствует контекст приложения для работы с базой данных")

        # Получаем информацию о приложении внутри контекста приложения
        with self.app.app_context():
            from app.services.ansible_service import AnsibleService
            from app.models.application_instance import ApplicationInstance
            from app.models.server import Server
            from app.models.task import Task

            task = Task.query.get(task_id)
            if not task:
                raise ValueError(f"Задача {task_id} не найдена")

            app = ApplicationInstance.query.get(task.instance_id)
            if not app:
                raise ValueError(f"Приложение с id {task.instance_id} не найдено")

            server = Server.query.get(app.server_id)
            if not server:
                raise ValueError(f"Сервер для приложения {app.instance_name} не найден")

            # Сохраняем необходимые данные для использования вне контекста приложения
            app_id = app.id
            app_name = app.instance_name
            server_name = server.name

        # Создаем event loop внутри метода
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Запускаем асинхронную функцию внутри event loop
            with self.app.app_context():
                success, message = loop.run_until_complete(
                    AnsibleService.manage_application(
                        server_name=server_name,
                        app_name=app_name,
                        app_id=app_id,
                        action="stop"
                    )
                )

                if not success:
                    raise Exception(message)

                return message
        finally:
            # Закрываем event loop
            loop.close()

    def _process_restart_task(self, task_id):
        """
        Обработка задачи перезапуска приложения.

        Args:
            task_id: ID задачи

        Returns:
            str: Результат выполнения задачи
        """
        import asyncio

        if not self.app:
            raise RuntimeError("Отсутствует контекст приложения для работы с базой данных")

        # Получаем информацию о приложении внутри контекста приложения
        with self.app.app_context():
            from app.services.ansible_service import AnsibleService
            from app.models.application_instance import ApplicationInstance
            from app.models.server import Server
            from app.models.task import Task

            task = Task.query.get(task_id)
            if not task:
                raise ValueError(f"Задача {task_id} не найдена")

            app = ApplicationInstance.query.get(task.instance_id)
            if not app:
                raise ValueError(f"Приложение с id {task.instance_id} не найдено")

            server = Server.query.get(app.server_id)
            if not server:
                raise ValueError(f"Сервер для приложения {app.instance_name} не найден")

            # Сохраняем необходимые данные для использования вне контекста приложения
            app_id = app.id
            app_name = app.instance_name
            server_name = server.name

        # Создаем event loop внутри метода
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Запускаем асинхронную функцию внутри event loop
            with self.app.app_context():
                success, message = loop.run_until_complete(
                    AnsibleService.manage_application(
                        server_name=server_name,
                        app_name=app_name,
                        app_id=app_id,
                        action="restart"
                    )
                )

                if not success:
                    raise Exception(message)

                return message
        finally:
            # Закрываем event loop
            loop.close()

    def _prepare_orchestrator_instances_with_haproxy(self, apps):
        """
        Формирует список instances с HAProxy маппингом.

        Args:
            apps: Список объектов ApplicationInstance для обновления

        Returns:
            tuple: (instances_list, backend_info, haproxy_api_url)
            - instances_list: Список строк вида "server::app::haproxy_server"
            - backend_info: Словарь с информацией о backends
            - haproxy_api_url: URL для HAProxy API (или None)
        """
        from app.models.application_mapping import ApplicationMapping
        from app.models.haproxy import HAProxyServer, HAProxyBackend, HAProxyInstance
        from app.models.server import Server
        from flask import current_app

        instances = []
        backend_info = {}
        haproxy_api_url = None
        unmapped_count = 0

        for app in apps:
            server = Server.query.get(app.server_id)
            if not server:
                logger.warning(f"Server not found for app {app.instance_name}")
                continue

            # Извлекаем короткое имя из FQDN
            short_name = server.name.split('.')[0] if '.' in server.name else server.name

            # Получаем HAProxy маппинг из таблицы ApplicationMapping
            mapping = ApplicationMapping.query.filter_by(
                application_id=app.id,
                entity_type='haproxy_server'
            ).first()

            if mapping and mapping.entity_id:
                # Есть маппинг - используем его
                haproxy_server = HAProxyServer.query.get(mapping.entity_id)
                if haproxy_server:
                    instance = f"{short_name}::{app.instance_name}::{haproxy_server.server_name}"

                    # Собираем информацию о backend
                    if haproxy_server.backend_id:
                        backend = HAProxyBackend.query.get(haproxy_server.backend_id)
                        if backend:
                            backend_info[backend.backend_name] = {
                                'name': backend.backend_name,
                                'instance_id': backend.haproxy_instance_id
                            }

                            # Получаем API URL из HAProxy Instance
                            if not haproxy_api_url and backend.haproxy_instance_id:
                                haproxy_instance = HAProxyInstance.query.get(backend.haproxy_instance_id)
                                if haproxy_instance and haproxy_instance.server:
                                    # Формируем URL: http://{server_ip}:{agent_port}/api/v1/haproxy/{instance_name}
                                    # Порт берём из сервера (agent port), не из глобального конфига
                                    agent_port = haproxy_instance.server.port
                                    haproxy_api_url = f"http://{haproxy_instance.server.ip}:{agent_port}/api/v1/haproxy/{haproxy_instance.name}"
                                    logger.info(f"HAProxy API URL: {haproxy_api_url}")

                    logger.info(f"App {app.instance_name} mapped to HAProxy server {haproxy_server.server_name}")
                else:
                    # Маппинг есть, но HAProxy сервер не найден
                    instance = f"{short_name}::{app.instance_name}::{short_name}_{app.instance_name}"
                    unmapped_count += 1
                    logger.warning(f"HAProxy server {mapping.entity_id} not found for app {app.instance_name}")
            else:
                # Нет маппинга - используем стандартное именование
                instance = f"{short_name}::{app.instance_name}::{short_name}_{app.instance_name}"
                unmapped_count += 1
                logger.info(f"No HAProxy mapping for app {app.instance_name}, using default naming")

            instances.append(instance)

        if unmapped_count > 0:
            logger.warning(f"Total unmapped applications: {unmapped_count} of {len(apps)}")

        return instances, backend_info, haproxy_api_url

    def _process_update_task(self, task_id):
        """
        Обработка задачи обновления приложения через SSH Ansible сервис.

        Args:
            task_id: ID задачи

        Returns:
            str: Результат выполнения задачи
        """
        import asyncio

        if not self.app:
            raise RuntimeError("Отсутствует контекст приложения для работы с базой данных")

        # Получаем данные внутри контекста приложения
        with self.app.app_context():
            from app.models.application_instance import ApplicationInstance
            from app.models.server import Server
            from app.models.task import Task
            from app.services.ssh_ansible_service import SSHAnsibleService
            from app import db

            task = Task.query.get(task_id)
            if not task:
                raise ValueError(f"Задача {task_id} не найдена")

            # Проверяем, является ли задача групповой (по наличию app_ids в params)
            app_ids = task.params.get("app_ids") if task.params else None
            is_batch_task = app_ids is not None and isinstance(app_ids, list) and len(app_ids) >= 1

            if is_batch_task:
                # Групповая задача - загружаем все приложения по ID
                apps = ApplicationInstance.query.filter(ApplicationInstance.id.in_(app_ids)).all()

                if not apps:
                    raise ValueError(f"Приложения с ID {app_ids} не найдены")

                if len(apps) != len(app_ids):
                    found_ids = [app.id for app in apps]
                    missing_ids = set(app_ids) - set(found_ids)
                    logger.warning(f"Некоторые приложения не найдены: {missing_ids}")

                # Формируем список имен через запятую
                app_name = ','.join([app.instance_name for app in apps])

                # Берем данные из первого приложения
                first_app = apps[0]
                server = Server.query.get(first_app.server_id)
                if not server:
                    raise ValueError(f"Сервер для приложения {first_app.instance_name} не найден")

                server_id = server.id
                server_name = server.name
                app_type = first_app.app_type
                app_id = first_app.id  # Для логирования используем первый ID

            else:
                # Одиночная задача - используем instance_id
                app = ApplicationInstance.query.get(task.instance_id)
                if not app:
                    raise ValueError(f"Приложение с id {task.instance_id} не найдено")

                server = Server.query.get(app.server_id)
                if not server:
                    raise ValueError(f"Сервер для приложения {app.instance_name} не найден")

                app_id = app.id
                app_name = app.instance_name
                app_type = app.app_type
                server_id = server.id
                server_name = server.name

            # Общие параметры для обеих типов задач
            params = task.params or {}
            distr_url = params.get("distr_url")
            if not distr_url:
                raise ValueError("URL дистрибутива не указан")

            mode = params.get("mode", params.get("restart_mode", "immediate"))
            playbook_path = params.get("playbook_path")

            if not playbook_path:
                raise ValueError("Путь к playbook не указан в параметрах задачи")

            # Получаем параметры для orchestrator playbook
            orchestrator_playbook = params.get("orchestrator_playbook")
            drain_wait_time = params.get("drain_wait_time")

            # Подготовка параметров для orchestrator (если режим update/immediate и orchestrator указан)
            # Игнорируем специальное значение "none" (Без оркестрации)
            # ВАЖНО: фронтенд отправляет 'update' для режима "Сейчас", поддерживаем оба значения
            extra_params = {}
            if mode in ('update', 'immediate') and orchestrator_playbook and orchestrator_playbook != 'none' and is_batch_task:
                logger.info(f"Режим orchestrator активирован: {orchestrator_playbook}")

                # Загружаем метаданные orchestrator playbook из БД
                from app.models.orchestrator_playbook import OrchestratorPlaybook
                orchestrator = OrchestratorPlaybook.query.filter_by(
                    file_path=orchestrator_playbook,
                    is_active=True
                ).first()

                if not orchestrator:
                    raise ValueError(f"Orchestrator playbook не найден в БД: {orchestrator_playbook}")

                logger.info(f"Загружен orchestrator: {orchestrator.name} v{orchestrator.version}")

                # Сохраняем оригинальный playbook для передачи в orchestrator
                original_playbook_path = playbook_path

                # Формируем составные имена server::app::haproxy_server для передачи в orchestrator
                # Используем расширенный формат с HAProxy маппингом
                composite_names, haproxy_backend_info, haproxy_api_url = self._prepare_orchestrator_instances_with_haproxy(apps)

                # Формируем servers_apps_map для логирования
                servers_apps_map = {}
                for comp in composite_names:
                    parts = comp.split('::')
                    short_name = parts[0]
                    comp_app_name = parts[1]
                    if short_name not in servers_apps_map:
                        servers_apps_map[short_name] = []
                    servers_apps_map[short_name].append(comp_app_name)

                logger.info(f"Сформированы составные имена для orchestrator (расширенный формат с HAProxy):")
                for comp in composite_names:
                    logger.info(f"  {comp}")

                logger.info(f"Mapping серверов и приложений:")
                for srv, app_list in sorted(servers_apps_map.items()):
                    logger.info(f"  {srv}: {', '.join(app_list)}")

                # Логируем информацию о HAProxy backends
                if haproxy_backend_info:
                    logger.info(f"HAProxy backends: {', '.join(haproxy_backend_info.keys())}")
                else:
                    logger.warning("No HAProxy backend information available, will use app_mapping.yml")

                # Формируем строку для передачи в orchestrator
                app_instances_list = ','.join(composite_names)

                # Конвертируем drain_wait_time из минут в секунды
                drain_delay_seconds = int(drain_wait_time * 60) if drain_wait_time else 300

                # Извлекаем только имя файла из оригинального playbook
                # Убираем параметры в фигурных скобках если они есть
                import re
                playbook_filename = original_playbook_path.split('/')[-1]
                update_playbook_name = re.sub(r'\s*\{[^}]+\}', '', playbook_filename).strip()

                # Определяем backend (берем первый, если несколько)
                haproxy_backend = None
                if haproxy_backend_info:
                    haproxy_backend = next(iter(haproxy_backend_info.keys()))
                    logger.info(f"Using HAProxy backend '{haproxy_backend}' from database mapping")

                # Формируем словарь значений параметров
                param_values = {
                    'app_instances': app_instances_list,  # Новый параметр вместо app_name и target_servers
                    'drain_delay': drain_delay_seconds,
                    'update_playbook': update_playbook_name,
                    'distr_url': distr_url
                }

                # Добавляем haproxy_backend если он определен
                if haproxy_backend:
                    param_values['haproxy_backend'] = haproxy_backend

                # Добавляем haproxy_api_url если он определен
                if haproxy_api_url:
                    param_values['haproxy_api_url'] = haproxy_api_url
                else:
                    logger.warning("HAProxy API URL not found in database mappings")

                # Формируем список параметров для playbook на основе required_params из БД
                # Структура в БД:
                # required_params: {"param_name": "description"}
                # optional_params: {"param_name": {"description": "...", "default": "..."}}
                required_params = orchestrator.required_params or {}
                optional_params = orchestrator.optional_params or {}

                # Извлекаем только имена параметров (ключи), игнорируя описания
                required_param_names = list(required_params.keys())
                optional_param_names = list(optional_params.keys())

                # Объединяем required и optional параметры (используем dict.fromkeys для сохранения порядка и уникальности)
                all_params = list(dict.fromkeys(required_param_names + optional_param_names))

                logger.info(f"Параметры orchestrator из БД:")
                logger.info(f"  Required: {required_param_names}")
                logger.info(f"  Optional: {optional_param_names}")

                # Формируем строку с параметрами в фигурных скобках
                params_string = ' '.join([f'{{{param}}}' for param in all_params])
                playbook_path = f"{orchestrator_playbook} {params_string}"

                logger.info(f"Сформирован playbook_path с параметрами: {playbook_path}")

                # Формируем extra_params только для тех параметров, для которых есть значения
                # ВАЖНО: передаем только значения, без описаний
                extra_params = {}
                missing_params = []

                for param in all_params:
                    if param in param_values:
                        # Берем только значение, игнорируя описания из БД
                        extra_params[param] = param_values[param]
                    else:
                        # Параметр есть в БД, но нет значения
                        missing_params.append(param)
                        # Для optional параметров можно попробовать взять default из БД
                        if param in optional_params:
                            param_info = optional_params[param]
                            if isinstance(param_info, dict) and 'default' in param_info:
                                default_value = param_info['default']

                                # Для wait_after_update пытаемся извлечь число секунд из строки типа "300 сек = 30 мин"
                                if param == 'wait_after_update' and isinstance(default_value, str):
                                    # Ищем первое число в строке
                                    match = re.search(r'(\d+)', default_value)
                                    if match:
                                        parsed_value = int(match.group(1))
                                        logger.info(f"Используется default для '{param}': извлечено {parsed_value} из '{default_value}'")
                                        extra_params[param] = parsed_value
                                    else:
                                        logger.warning(f"Не удалось извлечь число из default для '{param}': {default_value}")
                                        extra_params[param] = default_value
                                else:
                                    logger.info(f"Используется default значение для '{param}': {default_value}")
                                    extra_params[param] = default_value
                            else:
                                logger.warning(f"Optional параметр '{param}' не имеет значения и default")
                        else:
                            logger.warning(f"Required параметр '{param}' не имеет значения!")

                if missing_params:
                    logger.warning(f"Параметры без значений: {missing_params}")

                logger.info(f"Финальные значения extra_params (только значения, без описаний):")
                for key, value in extra_params.items():
                    logger.info(f"  {key} = {value} (type: {type(value).__name__})")

        # Создаем event loop внутри метода
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Запускаем асинхронное обновление через SSH Ansible внутри контекста приложения
            # Это необходимо, так как ssh_service.update_application создает события в БД
            with self.app.app_context():
                from app import db
                from app.models.application_instance import ApplicationInstance

                # Создаем SSH Ansible сервис внутри контекста
                ssh_service = SSHAnsibleService.from_config()

                success, message = loop.run_until_complete(
                    ssh_service.update_application(
                        server_name=server_name,
                        app_name=app_name,
                        app_id=app_id,
                        distr_url=distr_url,
                        mode=mode,
                        playbook_path=playbook_path,
                        extra_params=extra_params if extra_params else None
                    )
                )

                # Обновляем информацию о приложении при успешном обновлении
                # Только для одиночных задач (не для групповых)
                if success and not is_batch_task:
                    app = ApplicationInstance.query.get(app_id)
                    if app:
                        # Сохраняем старые значения для истории
                        old_version = app.version
                        old_distr_path = app.distr_path
                        old_tag = app.tag
                        old_image = app.image

                        # Обновляем данные
                        app.distr_path = distr_url

                        # Для Docker приложений пытаемся извлечь версию из тега
                        if app_type == 'docker' and ':' in distr_url:
                            app.version = distr_url.split(':')[-1]
                        else:
                            # Для обычных приложений пытаемся извлечь версию из URL
                            import re
                            version_match = re.search(r'(\d+\.[\d\.]+)', distr_url)
                            if version_match:
                                app.version = version_match.group(1)

                        # Записываем историю изменения версии
                        if old_version != app.version or old_distr_path != distr_url:
                            from app.models.application_version_history import ApplicationVersionHistory
                            history_entry = ApplicationVersionHistory(
                                instance_id=app.id,
                                old_version=old_version,
                                new_version=app.version,
                                old_distr_path=old_distr_path,
                                new_distr_path=distr_url,
                                old_tag=old_tag,
                                new_tag=app.tag,
                                old_image=old_image,
                                new_image=app.image,
                                changed_by='user',
                                change_source='update_task',
                                task_id=task_id
                            )
                            db.session.add(history_entry)
                            logger.info(f"Записана история версии для {app_name}: {old_version} -> {app.version}")

                        db.session.commit()
                        logger.info(f"Обновлена информация о приложении {app_name}: distr_path={distr_url}, version={app.version}")

            if not success:
                raise Exception(message)

            return message

        finally:
            # Закрываем event loop
            loop.close()


# Создаем глобальный экземпляр очереди задач
task_queue = TaskQueue()

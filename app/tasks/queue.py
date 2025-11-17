import uuid
import queue
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class Task:
    """
    Класс, представляющий задачу для выполнения.
    """
    
    def __init__(self, task_type, params, server_id=None, application_id=None):
        """
        Инициализация новой задачи.
        
        Args:
            task_type: Тип задачи (start, stop, restart, update)
            params: Словарь с параметрами задачи
            server_id: ID сервера (опционально)
            application_id: ID приложения (опционально)
        """
        self.id = str(uuid.uuid4())
        self.task_type = task_type
        self.params = params
        self.server_id = server_id
        self.application_id = application_id
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.status = "pending"  # pending, processing, completed, failed
        self.result = None
        self.error = None
        self.progress = {}  # Для отслеживания прогресса выполнения
    
    def to_dict(self):
        """Преобразование задачи в словарь для сериализации."""
        return {
            "id": self.id,
            "task_type": self.task_type,
            "params": self.params,
            "server_id": self.server_id,
            "application_id": self.application_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "progress": self.progress
        }

class TaskQueue:
    """
    Класс для управления очередью задач.
    """
    
    def __init__(self, app=None):
        self.queue = queue.Queue()
        self.tasks = {}  # Dictionary to store tasks by ID
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
        
        # Загружаем незавершенные задачи из базы данных и помечаем их как неудачные
        if app:
            with app.app_context():
                self.mark_interrupted_tasks()
    
    def mark_interrupted_tasks(self):
        """
        Находит незавершенные задачи в базе данных и помечает их как неудачные
        из-за перезапуска сервера. Также загружает их в текущий список задач.
        """
        try:
            from app import db
            from app.models.event import Event
            
            # Находим все незавершенные задачи (со статусом 'pending' или 'processing')
            pending_events = Event.query.filter(
                Event.status.in_(['pending', 'processing'])
            ).order_by(Event.timestamp.desc()).all()
            
            if not pending_events:
                logger.info("Незавершенных задач не найдено")
                return
            
            logger.info(f"Найдено {len(pending_events)} незавершенных задач")
            
            # Обрабатываем каждое незавершенное событие
            for event in pending_events:
                # Обновляем статус события
                event.status = 'failed'
                event.description = f"{event.description}\nПричина ошибки: Завершение работы сервера"
                
                # Создаем задачу для этого события
                task = Task(
                    task_type=event.event_type,
                    params={},
                    server_id=event.server_id,
                    application_id=event.application_id
                )
                task.status = 'failed'
                task.created_at = event.timestamp
                task.started_at = event.timestamp
                task.completed_at = datetime.utcnow()
                task.error = "Завершение работы сервера"
                
                # Добавляем задачу в список задач
                with self.lock:
                    self.tasks[task.id] = task
            
            # Сохраняем изменения в базе данных
            db.session.commit()
            logger.info(f"Все незавершенные задачи помечены как неудачные из-за перезапуска сервера")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке незавершенных задач: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                db.session.rollback()
            except:
                pass
    
    def add_task(self, task):
        """
        Добавление задачи в очередь.
        
        Args:
            task: Экземпляр класса Task
            
        Returns:
            Task: Добавленная задача
        """
        with self.lock:
            self.tasks[task.id] = task
            self.queue.put(task.id)
            logger.info(f"Задача {task.id} ({task.task_type}) добавлена в очередь")
            
            # Создаем запись о событии в БД
            if self.app:
                with self.app.app_context():
                    try:
                        from app import db
                        from app.models.event import Event
                        
                        # Проверяем, есть ли уже такое событие в обработке
                        existing_event = Event.query.filter_by(
                            event_type=task.task_type,
                            status='pending',
                            server_id=task.server_id,
                            application_id=task.application_id
                        ).first()
                        
                        if existing_event:
                            # Обновляем существующее событие
                            existing_event.description = f"Задача {task.task_type} добавлена в очередь (повторно)"
                            existing_event.timestamp = datetime.utcnow()
                            db.session.commit()
                            logger.info(f"Обновлено существующее событие для задачи {task.id}")
                        else:
                            # Создаем новое событие
                            event = Event(
                                event_type=task.task_type,
                                description=f"Задача {task.task_type} добавлена в очередь",
                                status="pending",
                                server_id=task.server_id,
                                application_id=task.application_id
                            )
                            db.session.add(event)
                            db.session.commit()
                            logger.info(f"Событие для задачи {task.id} создано")
                    except Exception as e:
                        logger.error(f"Ошибка при создании события для задачи {task.id}: {str(e)}")
                        try:
                            db.session.rollback()
                        except:
                            pass
            
            return task
    
    def get_task(self, task_id):
        """
        Получение информации о задаче по ID.
        
        Args:
            task_id: ID задачи
            
        Returns:
            Task: Найденная задача или None
        """
        with self.lock:
            return self.tasks.get(task_id)
    
    def get_tasks(self, status=None, application_id=None, server_id=None):
        """
        Получение списка задач с возможностью фильтрации.
        
        Args:
            status: Статус задачи для фильтрации (опционально)
            application_id: ID приложения для фильтрации (опционально)
            server_id: ID сервера для фильтрации (опционально)
            
        Returns:
            list: Список задач, соответствующих условиям фильтрации
        """
        with self.lock:
            tasks = list(self.tasks.values())
            
            if status:
                tasks = [task for task in tasks if task.status == status]
            
            if application_id:
                tasks = [task for task in tasks if task.application_id == application_id]
            
            if server_id:
                tasks = [task for task in tasks if task.server_id == server_id]
            
            return sorted(tasks, key=lambda x: x.created_at, reverse=True)
    
    def clear_completed_tasks(self, max_age_hours=24):
        """
        Очистка завершенных и неудачных задач старше указанного времени.
        
        Args:
            max_age_hours: Максимальный возраст задачи в часах
        """
        with self.lock:
            now = datetime.utcnow()
            task_ids_to_remove = []
            
            for task_id, task in self.tasks.items():
                if task.status in ["completed", "failed"]:
                    if task.completed_at and (now - task.completed_at).total_seconds() > max_age_hours * 3600:
                        task_ids_to_remove.append(task_id)
            
            for task_id in task_ids_to_remove:
                del self.tasks[task_id]
            
            if task_ids_to_remove:
                logger.info(f"Удалено {len(task_ids_to_remove)} старых задач")
    
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
                
                with self.lock:
                    task = self.tasks.get(task_id)
                    
                if not task:
                    logger.warning(f"Задача {task_id} не найдена в списке задач")
                    continue
                
                # Обновляем статус задачи
                task.status = "processing"
                task.started_at = datetime.utcnow()
                
                # Используем контекст приложения для операций с БД
                if self.app:
                    with self.app.app_context():
                        # Обновляем событие в БД
                        self._update_task_event(task, "processing", f"Началась обработка задачи {task.task_type}")
                
                logger.info(f"Обработка задачи {task.id} ({task.task_type})")
                
                try:
                    # Обработка задачи в зависимости от типа
                    if task.task_type == "start":
                        result = self._process_start_task(task)
                    elif task.task_type == "stop":
                        result = self._process_stop_task(task)
                    elif task.task_type == "restart":
                        result = self._process_restart_task(task)
                    elif task.task_type == "update":
                        result = self._process_update_task(task)
                    else:
                        raise ValueError(f"Неизвестный тип задачи: {task.task_type}")
                    
                    # Обновляем информацию о задаче
                    task.status = "completed"
                    task.completed_at = datetime.utcnow()
                    task.result = result
                    
                    # Обновляем событие в БД
                    if self.app:
                        with self.app.app_context():
                            self._update_task_event(task, "success", f"Задача {task.task_type} успешно выполнена: {result}")
                    
                    logger.info(f"Задача {task.id} успешно выполнена")
                    
                except Exception as e:
                    # Обрабатываем ошибку
                    task.status = "failed"
                    task.completed_at = datetime.utcnow()
                    task.error = str(e)
                    
                    # Обновляем событие в БД
                    if self.app:
                        with self.app.app_context():
                            self._update_task_event(task, "failed", f"Ошибка при выполнении задачи {task.task_type}: {str(e)}")
                    
                    logger.error(f"Ошибка при выполнении задачи {task.id}: {str(e)}")
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
    
    def _update_task_event(self, task, status, description):
        """
        Обновление события в БД для задачи.
        
        Args:
            task: Задача
            status: Новый статус
            description: Описание события
        """
        try:
            from app import db
            from app.models.event import Event
            
            # Ищем существующее событие для задачи
            event = Event.query.filter_by(
                event_type=task.task_type,
                server_id=task.server_id,
                application_id=task.application_id
            ).order_by(Event.timestamp.desc()).first()
            
            if event and event.status == "pending":
                # Обновляем существующее событие
                event.status = status
                event.description = description
                db.session.commit()
                logger.info(f"Событие для задачи {task.id} обновлено")
            else:
                # Создаем новое событие
                event = Event(
                    event_type=task.task_type,
                    description=description,
                    status=status,
                    server_id=task.server_id,
                    application_id=task.application_id
                )
                db.session.add(event)
                db.session.commit()
                logger.info(f"Создано новое событие для задачи {task.id}")
        
        except Exception as e:
            logger.error(f"Ошибка при обновлении события для задачи {task.id}: {str(e)}")
            try:
                db.session.rollback()
            except:
                pass

    def _process_start_task(self, task):
        """
        Обработка задачи запуска приложения.

        Args:
            task: Задача

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

            app = ApplicationInstance.query.get(task.application_id)
            if not app:
                raise ValueError(f"Приложение с id {task.application_id} не найдено")

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
    
    def _process_stop_task(self, task):
        """
        Обработка задачи остановки приложения.

        Args:
            task: Задача

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

            app = ApplicationInstance.query.get(task.application_id)
            if not app:
                raise ValueError(f"Приложение с id {task.application_id} не найдено")

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
    
    def _process_restart_task(self, task):
        """
        Обработка задачи перезапуска приложения.

        Args:
            task: Задача

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

            app = ApplicationInstance.query.get(task.application_id)
            if not app:
                raise ValueError(f"Приложение с id {task.application_id} не найдено")

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
    
    def _process_update_task(self, task):
        """
        Обработка задачи обновления приложения через SSH Ansible сервис.

        Args:
            task: Задача с параметрами обновления

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
            from app.services.ssh_ansible_service import SSHAnsibleService
            from app import db

            # Проверяем, является ли задача групповой (по наличию app_ids в params)
            app_ids = task.params.get("app_ids")
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
                # Одиночная задача - используем application_id
                app = ApplicationInstance.query.get(task.application_id)
                if not app:
                    raise ValueError(f"Приложение с id {task.application_id} не найдено")

                server = Server.query.get(app.server_id)
                if not server:
                    raise ValueError(f"Сервер для приложения {app.instance_name} не найден")

                app_id = app.id
                app_name = app.instance_name
                app_type = app.app_type
                server_id = server.id
                server_name = server.name

            # Общие параметры для обеих типов задач
            distr_url = task.params.get("distr_url")
            if not distr_url:
                raise ValueError("URL дистрибутива не указан")

            mode = task.params.get("mode", task.params.get("restart_mode", "immediate"))
            playbook_path = task.params.get("playbook_path")

            if not playbook_path:
                raise ValueError("Путь к playbook не указан в параметрах задачи")

            # Получаем параметры для orchestrator playbook
            orchestrator_playbook = task.params.get("orchestrator_playbook")
            drain_wait_time = task.params.get("drain_wait_time")

            # Подготовка параметров для orchestrator (если режим immediate и orchestrator указан)
            # Игнорируем специальное значение "none" (Без оркестрации)
            extra_params = {}
            if mode == 'immediate' and orchestrator_playbook and orchestrator_playbook != 'none' and is_batch_task:
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

                # Формируем составные имена server::app для передачи в orchestrator
                # Используем разделитель :: для связывания сервера и приложения
                composite_names = []
                servers_apps_map = {}  # для логирования

                for app in apps:
                    srv = Server.query.get(app.server_id)
                    if srv:
                        # Извлекаем короткое имя из FQDN (до первой точки)
                        short_name = srv.name.split('.')[0] if '.' in srv.name else srv.name
                        # Формируем составное имя с разделителем ::
                        composite_name = f"{short_name}::{app.instance_name}"
                        composite_names.append(composite_name)

                        # Сохраняем mapping для логирования
                        if short_name not in servers_apps_map:
                            servers_apps_map[short_name] = []
                        servers_apps_map[short_name].append(app.instance_name)

                logger.info(f"Сформированы составные имена для orchestrator:")
                for comp in composite_names:
                    logger.info(f"  {comp}")

                logger.info(f"Mapping серверов и приложений:")
                for server, app_list in sorted(servers_apps_map.items()):
                    logger.info(f"  {server}: {', '.join(app_list)}")

                # Формируем строку для передачи в orchestrator
                app_instances_list = ','.join(composite_names)

                # Конвертируем drain_wait_time из минут в секунды
                drain_delay_seconds = int(drain_wait_time * 60) if drain_wait_time else 300

                # Извлекаем только имя файла из оригинального playbook
                # Убираем параметры в фигурных скобках если они есть
                import re
                playbook_filename = original_playbook_path.split('/')[-1]
                update_playbook_name = re.sub(r'\s*\{[^}]+\}', '', playbook_filename).strip()

                # Формируем словарь значений параметров
                param_values = {
                    'app_instances': app_instances_list,  # Новый параметр вместо app_name и target_servers
                    'drain_delay': drain_delay_seconds,
                    'update_playbook': update_playbook_name,
                    'distr_url': distr_url
                }

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
                                    import re
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
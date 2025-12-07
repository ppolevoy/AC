"""
Модуль управления очередью задач.

Задачи хранятся персистентно в БД (таблица tasks).
При перезагрузке сервера незавершённые задачи помечаются как failed.
"""
import uuid
import queue
import logging
import threading
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskQueue:
    """
    Класс для управления очередью задач.
    Задачи хранятся в БД, очередь используется только для обработки.

    Поддерживает DI для SSHAnsibleService (для тестирования).
    """

    def __init__(self, app=None, ansible_service=None):
        """
        Args:
            app: Flask application instance
            ansible_service: Опциональный SSHAnsibleService для DI (используется в тестах)
        """
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.app = app
        self._ansible_service = ansible_service  # DI: для тестирования

        # Если приложение уже передано, инициализируем с ним
        if app:
            self.init_app(app)

    def _get_ansible_service(self):
        """
        Получает SSHAnsibleService для выполнения задач.

        Поддерживает DI: если сервис был передан в конструктор, использует его.
        Иначе создаёт новый из конфигурации.

        Returns:
            SSHAnsibleService instance
        """
        if self._ansible_service:
            return self._ansible_service

        from app.services.ssh_ansible_service import SSHAnsibleService
        return SSHAnsibleService.from_config()

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

    def cancel_pending_task(self, task_id):
        """
        Отмена задачи в статусе pending.

        Задача помечается как cancelled и failed в БД.
        При обработке очереди worker пропустит отмененную задачу.

        Args:
            task_id: ID задачи

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.app:
            return False, "TaskQueue не инициализирован"

        try:
            with self.app.app_context():
                from app import db
                from app.models.task import Task

                task = Task.query.get(task_id)
                if not task:
                    return False, f"Задача {task_id} не найдена"

                if task.status != 'pending':
                    return False, f"Задача не в статусе ожидания (текущий статус: {task.status})"

                if task.cancelled:
                    return False, "Задача уже была отменена"

                # Помечаем задачу как отмененную
                task.cancelled = True
                task.status = 'failed'
                task.completed_at = datetime.utcnow()
                task.error = 'Задача отменена пользователем'
                db.session.commit()

                logger.info(f"Задача {task_id[:8]}... ({task.task_type}) отменена пользователем")
                return True, "Задача успешно отменена"

        except Exception as e:
            logger.error(f"Ошибка при отмене задачи {task_id}: {str(e)}")
            try:
                from app import db
                db.session.rollback()
            except:
                pass
            return False, str(e)

    def clear_completed_tasks(self, days_old: int = None):
        # Используем константу по умолчанию
        if days_old is None:
            from app.config import TaskQueueDefaults
            days_old = TaskQueueDefaults.HISTORY_RETENTION_DAYS
        """
        Очистка старых завершённых задач из БД.

        Args:
            days_old: Удалять задачи старше указанного количества дней (по умолчанию 7)
        """
        if not self.app:
            logger.warning("TaskQueue не инициализирован, пропуск очистки задач")
            return

        try:
            from app import db
            from app.models.task import Task
            from datetime import timedelta

            # Определяем дату, старше которой задачи нужно удалить
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)

            # Удаляем только завершённые и неудачные задачи старше cutoff_date
            deleted_count = Task.query.filter(
                Task.status.in_(['completed', 'failed']),
                Task.completed_at < cutoff_date
            ).delete(synchronize_session=False)

            db.session.commit()

            if deleted_count > 0:
                logger.info(f"Удалено {deleted_count} старых задач (старше {days_old} дней)")

        except Exception as e:
            logger.error(f"Ошибка при очистке старых задач: {str(e)}")
            try:
                from app import db
                db.session.rollback()
            except:
                pass

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
        from app.config import TaskQueueDefaults
        self.thread.join(timeout=TaskQueueDefaults.SHUTDOWN_TIMEOUT)
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

                    # Проверяем, не была ли задача отменена или уже обработана
                    if task.status != 'pending' or task.cancelled:
                        logger.info(f"Задача {task_id[:8]}... пропущена (статус: {task.status}, отменена: {task.cancelled})")
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
                success, message, output = loop.run_until_complete(
                    AnsibleService.manage_application(
                        server_name=server_name,
                        app_name=app_name,
                        app_id=app_id,
                        action="start"
                    )
                )

                if not success:
                    raise Exception(message)

                # Возвращаем вывод Ansible для отображения в task.result
                return output if output else message
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
                success, message, output = loop.run_until_complete(
                    AnsibleService.manage_application(
                        server_name=server_name,
                        app_name=app_name,
                        app_id=app_id,
                        action="stop"
                    )
                )

                if not success:
                    raise Exception(message)

                # Возвращаем вывод Ansible для отображения в task.result
                return output if output else message
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
                success, message, output = loop.run_until_complete(
                    AnsibleService.manage_application(
                        server_name=server_name,
                        app_name=app_name,
                        app_id=app_id,
                        action="restart"
                    )
                )

                if not success:
                    raise Exception(message)

                # Возвращаем вывод Ansible для отображения в task.result
                return output if output else message
        finally:
            # Закрываем event loop
            loop.close()

    def _process_update_task(self, task_id):
        """
        Обработка задачи обновления приложения через SSH Ansible сервис.

        Использует:
        - UpdateTaskContextProvider для загрузки контекста из БД
        - OrchestratorExecutor для подготовки параметров orchestrator

        Args:
            task_id: ID задачи

        Returns:
            str: Результат выполнения задачи
        """
        import asyncio

        if not self.app:
            raise RuntimeError("Отсутствует контекст приложения для работы с базой данных")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Единый app_context для всей операции - предотвращает detached ORM objects
            with self.app.app_context():
                from app import db
                from app.services.update_task_context import UpdateTaskContextProvider

                # 1. ЗАГРУЗКА КОНТЕКСТА
                context = UpdateTaskContextProvider.load(task_id)

                # 2. ПОДГОТОВКА ПАРАМЕТРОВ
                playbook_path = context.playbook_path
                extra_params = {}

                if UpdateTaskContextProvider.should_use_orchestrator(context):
                    logger.info(f"Режим orchestrator активирован: {context.orchestrator_playbook}")

                    # Загружаем метаданные orchestrator из БД
                    metadata = UpdateTaskContextProvider.load_orchestrator_metadata(
                        context.orchestrator_playbook
                    )

                    # Создаем контекст и executor для orchestrator
                    from app.services.orchestrator_executor import (
                        OrchestratorContext,
                        create_orchestrator_executor
                    )

                    orch_context = OrchestratorContext(
                        task_id=task_id,
                        apps=context.apps,
                        distr_url=context.distr_url,
                        orchestrator_playbook=context.orchestrator_playbook,
                        original_playbook_path=context.playbook_path,
                        drain_wait_time=context.drain_wait_time,
                        required_params=metadata['required_params'],
                        optional_params=metadata['optional_params']
                    )

                    executor = create_orchestrator_executor(orch_context)
                    playbook_path, extra_params = executor.prepare()

                # 3. ВЫПОЛНЕНИЕ ANSIBLE
                ssh_service = self._get_ansible_service()

                success, message, ansible_output = loop.run_until_complete(
                    ssh_service.update_application(
                        server_name=context.server_name,
                        app_name=context.app_name,
                        app_id=context.app_id,
                        distr_url=context.distr_url,
                        mode=context.mode,
                        playbook_path=playbook_path,
                        extra_params=extra_params if extra_params else None,
                        task_id=task_id
                    )
                )

                # 4. ПОСТОБРАБОТКА: обновляем версию приложения (только single tasks)
                # Best-effort: ошибка обновления версии НЕ должна влиять на статус задачи,
                # т.к. Ansible уже успешно выполнился и приложение обновлено на сервере
                if success and not context.is_batch:
                    try:
                        self._update_app_version_after_success(
                            context.app_id,
                            context.app_name,
                            context.app_type,
                            context.distr_url,
                            task_id,
                            db
                        )
                    except Exception as version_update_error:
                        logger.error(
                            f"Не удалось обновить версию приложения {context.app_name} в БД "
                            f"(задача {task_id[:8]}... будет отмечена успешной, т.к. Ansible выполнился): "
                            f"{version_update_error}"
                        )
                        # Пытаемся откатить незакоммиченные изменения
                        try:
                            db.session.rollback()
                        except Exception:
                            pass

                if not success:
                    raise Exception(message)

                return ansible_output if ansible_output else message

        finally:
            loop.close()

    def _update_app_version_after_success(
        self,
        app_id: int,
        app_name: str,
        app_type: str,
        distr_url: str,
        task_id: str,
        db
    ) -> None:
        """
        Обновляет версию приложения после успешного обновления.

        Args:
            app_id: ID приложения
            app_name: Имя приложения (для логирования)
            app_type: Тип приложения (docker, service, etc.)
            distr_url: URL дистрибутива
            task_id: ID задачи
            db: SQLAlchemy db session
        """
        from app.models.application_instance import ApplicationInstance

        app = ApplicationInstance.query.get(app_id)
        if not app:
            return

        # Сохраняем старые значения для истории
        old_version = app.version
        old_distr_path = app.distr_path
        old_tag = app.tag
        old_image = app.image

        # Обновляем данные
        app.distr_path = distr_url

        # Извлекаем версию из URL
        if app_type == 'docker' and ':' in distr_url:
            app.version = distr_url.split(':')[-1]
        else:
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


# Создаем глобальный экземпляр очереди задач
task_queue = TaskQueue()

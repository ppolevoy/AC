# app/services/update_task_context.py
"""
Провайдер контекста для задач обновления приложений.

Извлекает логику загрузки данных из БД в отдельный слой,
обеспечивая чистое разделение data access от business logic.

Использование:
    context = UpdateTaskContextProvider.load(task_id)
    # context содержит все данные для выполнения задачи
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING

# TYPE_CHECKING для избежания circular imports при типизации
if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.server import Server
    from app.models.application_instance import ApplicationInstance

logger = logging.getLogger(__name__)


@dataclass
class UpdateTaskContext:
    """
    Контекст задачи обновления приложения.

    Содержит все данные, необходимые для выполнения задачи обновления,
    загруженные из БД и нормализованные.

    Attributes:
        task_id: ID задачи в БД
        task: Объект Task из БД
        apps: Список ApplicationInstance для обновления
        server: Объект Server (для одиночных задач)
        server_id: ID сервера
        server_name: Имя сервера
        app_name: Имя приложения(й) через запятую
        app_id: ID первого приложения (для логирования)
        app_type: Тип приложения (docker, service, etc.)
        is_batch: True если это групповая задача
        distr_url: URL дистрибутива
        mode: Режим обновления (immediate, deliver, etc.)
        playbook_path: Путь к playbook
        orchestrator_playbook: Имя orchestrator playbook (или None)
        drain_wait_time: Время ожидания drain (минуты)
        params: Полные параметры задачи из БД
    """
    task_id: str
    task: "Task"
    apps: List["ApplicationInstance"]
    server: Optional["Server"]
    server_id: int
    server_name: str
    app_name: str
    app_id: int
    app_type: str
    is_batch: bool
    distr_url: str
    mode: str
    playbook_path: str
    orchestrator_playbook: Optional[str] = None
    drain_wait_time: Optional[float] = None
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Валидация обязательных полей при создании контекста."""
        if not self.task_id:
            raise ValueError("task_id не может быть пустым")
        if self.task is None:
            raise ValueError("task не может быть None")
        if not self.apps:
            raise ValueError("apps не может быть пустым списком")
        if not self.server_name:
            raise ValueError("server_name не может быть пустым")
        if not self.app_name:
            raise ValueError("app_name не может быть пустым")
        if not self.playbook_path:
            raise ValueError("playbook_path не может быть пустым")


class UpdateTaskContextProvider:
    """
    Провайдер контекста для задач обновления.

    Инкапсулирует всю логику загрузки данных из БД,
    валидации и подготовки контекста для выполнения задачи.
    """

    @staticmethod
    def load(task_id: str, app_context=None) -> UpdateTaskContext:
        """
        Загружает полный контекст для задачи обновления.

        Args:
            task_id: ID задачи в БД
            app_context: Flask app context (опционально, если уже в контексте)

        Returns:
            UpdateTaskContext со всеми данными для выполнения

        Raises:
            ValueError: Если задача, приложение или сервер не найдены
        """
        from app.models.application_instance import ApplicationInstance
        from app.models.server import Server
        from app.models.task import Task

        task = Task.query.get(task_id)
        if not task:
            raise ValueError(f"Задача {task_id} не найдена")

        # Проверяем, является ли задача групповой
        app_ids = task.params.get("app_ids") if task.params else None
        is_batch = app_ids is not None and isinstance(app_ids, list) and len(app_ids) >= 1

        if is_batch:
            return UpdateTaskContextProvider._load_batch_context(task, task_id, app_ids)
        else:
            return UpdateTaskContextProvider._load_single_context(task, task_id)

    @staticmethod
    def _load_batch_context(task, task_id: str, app_ids: List[int]) -> UpdateTaskContext:
        """
        Загружает контекст для групповой задачи.

        Args:
            task: Объект Task
            task_id: ID задачи
            app_ids: Список ID приложений

        Returns:
            UpdateTaskContext
        """
        from app.models.application_instance import ApplicationInstance
        from app.models.server import Server

        # Загружаем все приложения по ID
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

        # Загружаем общие параметры
        params = task.params or {}
        distr_url = params.get("distr_url")
        if not distr_url:
            raise ValueError("URL дистрибутива не указан")

        mode = params.get("mode", params.get("restart_mode", "immediate"))
        playbook_path = params.get("playbook_path")

        if not playbook_path:
            raise ValueError("Путь к playbook не указан в параметрах задачи")

        return UpdateTaskContext(
            task_id=task_id,
            task=task,
            apps=apps,
            server=server,
            server_id=server.id,
            server_name=server.name,
            app_name=app_name,
            app_id=first_app.id,
            app_type=first_app.app_type,
            is_batch=True,
            distr_url=distr_url,
            mode=mode,
            playbook_path=playbook_path,
            orchestrator_playbook=params.get("orchestrator_playbook"),
            drain_wait_time=params.get("drain_wait_time"),
            params=params
        )

    @staticmethod
    def _load_single_context(task, task_id: str) -> UpdateTaskContext:
        """
        Загружает контекст для одиночной задачи.

        Args:
            task: Объект Task
            task_id: ID задачи

        Returns:
            UpdateTaskContext
        """
        from app.models.application_instance import ApplicationInstance
        from app.models.server import Server

        app = ApplicationInstance.query.get(task.instance_id)
        if not app:
            raise ValueError(f"Приложение с id {task.instance_id} не найдено")

        server = Server.query.get(app.server_id)
        if not server:
            raise ValueError(f"Сервер для приложения {app.instance_name} не найден")

        # Загружаем параметры
        params = task.params or {}
        distr_url = params.get("distr_url")
        if not distr_url:
            raise ValueError("URL дистрибутива не указан")

        mode = params.get("mode", params.get("restart_mode", "immediate"))
        playbook_path = params.get("playbook_path")

        if not playbook_path:
            raise ValueError("Путь к playbook не указан в параметрах задачи")

        return UpdateTaskContext(
            task_id=task_id,
            task=task,
            apps=[app],  # Одиночное приложение в списке для унификации
            server=server,
            server_id=server.id,
            server_name=server.name,
            app_name=app.instance_name,
            app_id=app.id,
            app_type=app.app_type,
            is_batch=False,
            distr_url=distr_url,
            mode=mode,
            playbook_path=playbook_path,
            orchestrator_playbook=params.get("orchestrator_playbook"),
            drain_wait_time=params.get("drain_wait_time"),
            params=params
        )

    @staticmethod
    def should_use_orchestrator(context: UpdateTaskContext) -> bool:
        """
        Определяет, нужно ли использовать оркестратор для данной задачи.

        Условия:
        1. Режим update или immediate
        2. orchestrator_playbook указан и не равен 'none'
        3. Это batch задача (несколько приложений)

        Args:
            context: Загруженный контекст задачи

        Returns:
            True если нужно использовать оркестратор
        """
        return (
            context.mode in ('update', 'immediate') and
            context.orchestrator_playbook and
            context.orchestrator_playbook != 'none' and
            context.is_batch
        )

    @staticmethod
    def load_orchestrator_metadata(orchestrator_playbook: str) -> Dict[str, Any]:
        """
        Загружает метаданные orchestrator playbook из БД.

        Args:
            orchestrator_playbook: Имя файла orchestrator playbook

        Returns:
            Dict с required_params и optional_params

        Raises:
            ValueError: Если orchestrator не найден в БД
        """
        from app.models.orchestrator_playbook import OrchestratorPlaybook

        orchestrator = OrchestratorPlaybook.query.filter_by(
            file_path=orchestrator_playbook,
            is_active=True
        ).first()

        if not orchestrator:
            raise ValueError(f"Orchestrator playbook не найден в БД: {orchestrator_playbook}")

        logger.info(f"Загружен orchestrator: {orchestrator.name} v{orchestrator.version}")

        return {
            'name': orchestrator.name,
            'version': orchestrator.version,
            'required_params': orchestrator.required_params or {},
            'optional_params': orchestrator.optional_params or {}
        }

# app/services/orchestrator_executor.py
"""
Модуль оркестрации обновлений приложений.

Содержит:
- OrchestratorContext: сессионный контекст для конкретного запуска
- OrchestratorExecutor: базовый класс с общей логикой
- HAProxyOrchestratorExecutor: оркестратор с HAProxy drain/ready
- SimpleOrchestratorExecutor: базовый rolling update без внешних зависимостей
- create_orchestrator_executor: фабрика для выбора executor'а

Сессионность: OrchestratorContext создаётся для каждой задачи,
все вычисления и состояние хранятся в нём.
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional, TYPE_CHECKING

from app.config import OrchestratorDefaults
from app.core.playbook_parameters import PlaybookParameterParser

# TYPE_CHECKING для избежания circular imports при типизации
if TYPE_CHECKING:
    from app.models.application_instance import ApplicationInstance

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorContext:
    """
    Сессионный контекст для конкретного запуска оркестратора.

    Создаётся для каждой задачи и содержит все данные,
    необходимые для формирования параметров playbook.

    Attributes:
        task_id: ID задачи в БД
        apps: Список ApplicationInstance для обновления
        distr_url: URL дистрибутива/образа
        orchestrator_playbook: Имя файла orchestrator playbook
        original_playbook_path: Оригинальный путь к update playbook (может содержать параметры)
        drain_wait_time: Время ожидания drain в минутах (из UI)
        required_params: Обязательные параметры из метаданных orchestrator
        optional_params: Опциональные параметры из метаданных orchestrator

        # Вычисляемые поля (заполняются в prepare)
        composite_names: Список строк server::app::haproxy_server
        haproxy_backend: Имя backend в HAProxy
        haproxy_api_url: URL API HAProxy
        servers_apps_map: Маппинг сервер -> список приложений (для логирования)
    """
    task_id: str
    apps: List["ApplicationInstance"]
    distr_url: str
    orchestrator_playbook: str
    original_playbook_path: str
    drain_wait_time: Optional[float] = None
    required_params: Dict[str, Any] = field(default_factory=dict)
    optional_params: Dict[str, Any] = field(default_factory=dict)

    # Вычисляемые поля
    composite_names: List[str] = field(default_factory=list)
    haproxy_backend: Optional[str] = None
    haproxy_api_url: Optional[str] = None
    servers_apps_map: Dict[str, List[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Валидация обязательных полей при создании контекста."""
        if not self.task_id:
            raise ValueError("task_id не может быть пустым")
        if not self.apps:
            raise ValueError("apps не может быть пустым списком")
        if not self.distr_url:
            raise ValueError("distr_url не может быть пустым")
        if not self.orchestrator_playbook:
            raise ValueError("orchestrator_playbook не может быть пустым")
        if not self.original_playbook_path:
            raise ValueError("original_playbook_path не может быть пустым")


class OrchestratorExecutor(ABC):
    """
    Базовый класс оркестратора обновлений.

    Инкапсулирует логику подготовки параметров для orchestrator playbook.
    Экземпляр создаётся для каждой задачи (сессионный).

    Использование:
        context = OrchestratorContext(...)
        executor = create_orchestrator_executor(context)
        playbook_path, extra_params = executor.prepare()
    """

    def __init__(self, context: OrchestratorContext):
        """
        Args:
            context: Сессионный контекст с данными задачи
        """
        self.context = context

    def prepare(self) -> Tuple[str, Dict[str, Any]]:
        """
        Template Method: подготавливает playbook_path и extra_params для Ansible.

        Реализует общий алгоритм, делегируя специфичные шаги подклассам:
        1. _build_composite_names() - абстрактный, реализуется подклассами
        2. _add_specific_params() - виртуальный, может быть переопределён

        Returns:
            Tuple[str, Dict[str, Any]]:
                - playbook_path: Путь к orchestrator playbook с параметрами
                - extra_params: Словарь параметров для --extra-vars
        """
        # 1. Формируем composite_names (специфично для подкласса)
        self._build_composite_names()

        # 2. Извлекаем кастомные параметры из оригинального playbook_path
        config = PlaybookParameterParser.parse(self.context.original_playbook_path)
        custom_params = config.get_explicit_params()
        if custom_params:
            logger.debug(f"Извлечены кастомные параметры из playbook_path: {custom_params}")

        # 3. Формируем базовые параметры
        param_values = self._build_base_param_values()

        # 4. Добавляем кастомные параметры
        for param_name, param_value in custom_params.items():
            param_values[param_name] = param_value
            logger.debug(f"Добавлен параметр из playbook_path: {param_name}={param_value}")

        # 5. Добавляем специфичные параметры (hook для подклассов)
        self._add_specific_params(param_values)

        # 6. Формируем финальные playbook_path и extra_params
        playbook_path = self._build_playbook_path_with_params(param_values, custom_params)
        extra_params = self._build_extra_params(param_values)

        return playbook_path, extra_params

    @abstractmethod
    def _build_composite_names(self) -> None:
        """
        Абстрактный метод: формирует composite_names в контексте.

        Реализуется подклассами для специфичного формата имён.
        """
        pass

    def _add_specific_params(self, param_values: Dict[str, Any]) -> None:
        """
        Виртуальный метод: добавляет специфичные параметры.

        По умолчанию ничего не делает. Подклассы могут переопределить
        для добавления своих параметров (например, HAProxy).

        Args:
            param_values: Словарь параметров для модификации
        """
        pass

    def sort_instances_for_batches(self, apps: List["ApplicationInstance"]) -> List["ApplicationInstance"]:
        """
        Сортирует экземпляры для корректного разделения на EVEN/ODD батчи.

        Гарантирует, что парные экземпляры одного приложения на разных серверах
        получат соседние индексы и попадут в разные батчи при делении по чёт/нечёт.

        Алгоритм:
        1. Группируем экземпляры по имени приложения (instance_name)
        2. Для каждой группы сортируем по имени сервера
        3. Чередуем распределение: первый сервер → EVEN, второй → ODD
        4. Формируем финальный список чередованием

        Args:
            apps: Список объектов ApplicationInstance

        Returns:
            Отсортированный список ApplicationInstance
        """
        from app.models.server import Server

        if len(apps) <= 1:
            return list(apps)

        # Предзагружаем все серверы одним запросом (оптимизация N+1)
        server_ids = list(set(app.server_id for app in apps))
        servers = Server.query.filter(Server.id.in_(server_ids)).all()
        server_names_map = {s.id: s.name for s in servers}

        # Группируем по instance_name
        groups: Dict[str, List["ApplicationInstance"]] = {}
        for app in apps:
            name = app.instance_name
            if name not in groups:
                groups[name] = []
            groups[name].append(app)

        # Формируем два списка для чередования
        even_list = []
        odd_list = []
        toggle = False

        for name in sorted(groups.keys()):
            instances = groups[name]

            # Сортируем по имени сервера для консистентности (используем предзагруженный кэш)
            instances_with_servers = []
            for inst in instances:
                server_name = server_names_map.get(inst.server_id, '')
                instances_with_servers.append((inst, server_name))

            instances_with_servers.sort(key=lambda x: x[1])
            sorted_instances = [x[0] for x in instances_with_servers]

            if len(sorted_instances) >= 2:
                # Парные экземпляры - чередуем распределение для балансировки
                # Сохраняем initial_toggle для распределения 3+ элементов
                initial_toggle = toggle
                if toggle:
                    even_list.append(sorted_instances[1])
                    odd_list.append(sorted_instances[0])
                else:
                    even_list.append(sorted_instances[0])
                    odd_list.append(sorted_instances[1])
                toggle = not toggle

                # Если больше 2 экземпляров, распределяем остальные
                # Формула: (i % 2 == 0) XOR initial_toggle определяет целевой список
                # Это гарантирует чередование между группами для балансировки по серверам
                # Работает корректно для любого N серверов (3, 5, 7, 10, ...)
                for i, inst in enumerate(sorted_instances[2:]):
                    if (i % 2 == 0) != initial_toggle:
                        odd_list.append(inst)
                    else:
                        even_list.append(inst)
            else:
                # Один экземпляр - кладём в менее заполненный список
                if len(even_list) <= len(odd_list):
                    even_list.append(sorted_instances[0])
                else:
                    odd_list.append(sorted_instances[0])

        # Формируем финальный список чередованием
        result = []
        for i in range(max(len(even_list), len(odd_list))):
            if i < len(even_list):
                result.append(even_list[i])
            if i < len(odd_list):
                result.append(odd_list[i])

        # Логируем результат сортировки (передаём кэш серверов для избежания N+1)
        self._log_sorting_result(result, server_names_map)

        return result

    def _log_sorting_result(self, result: List["ApplicationInstance"], server_names_map: Dict[int, str]) -> None:
        """
        Логирует результат сортировки для EVEN/ODD батчей.

        Args:
            result: Отсортированный список инстансов
            server_names_map: Предзагруженная карта {server_id: server_name}
        """
        logger.debug("Cross-server sorting for EVEN/ODD splitting:")
        for idx, app in enumerate(result):
            server_name = server_names_map.get(app.server_id, 'unknown')
            short_name = server_name.split('.')[0] if '.' in server_name else server_name
            batch = "EVEN" if idx % 2 == 0 else "ODD"
            logger.debug(f"  [{idx}] {batch}: {short_name}::{app.instance_name}")

    def _get_short_server_name(self, server) -> str:
        """Извлекает короткое имя сервера из FQDN."""
        if not server:
            return 'unknown'
        return server.name.split('.')[0] if '.' in server.name else server.name

    def _extract_update_playbook_name(self, playbook_path: str) -> str:
        """
        Извлекает имя playbook без пути и параметров.

        Args:
            playbook_path: Полный путь с параметрами, например:
                "/etc/ansible/update.yml {server} {unpack=true}"

        Returns:
            Имя файла без параметров, например: "update.yml"
        """
        filename = playbook_path.split('/')[-1]
        return re.sub(r'\s*\{[^}]+\}', '', filename).strip()

    def _calculate_drain_delay_seconds(self) -> int:
        """
        Конвертирует drain_wait_time из минут в секунды.

        Returns:
            Время в секундах или значение по умолчанию
        """
        if self.context.drain_wait_time:
            return int(self.context.drain_wait_time * 60)
        return OrchestratorDefaults.DRAIN_DELAY_SECONDS

    def _build_base_param_values(self) -> Dict[str, Any]:
        """
        Формирует базовый словарь значений параметров.

        Returns:
            Словарь с базовыми параметрами для orchestrator
        """
        update_playbook_name = self._extract_update_playbook_name(
            self.context.original_playbook_path
        )
        drain_delay = self._calculate_drain_delay_seconds()

        return {
            'app_instances': ','.join(self.context.composite_names),
            'drain_delay': drain_delay,
            'update_playbook': update_playbook_name,
            'distr_url': self.context.distr_url,
            'image_url': self.context.distr_url,  # Алиас для docker оркестратора
        }

    def _build_playbook_path_with_params(
        self,
        param_values: Dict[str, Any],
        custom_params: Dict[str, str]
    ) -> str:
        """
        Формирует строку playbook_path с параметрами в фигурных скобках.

        Args:
            param_values: Словарь всех значений параметров
            custom_params: Кастомные параметры из оригинального playbook_path

        Returns:
            Строка вида "orchestrator.yml {param1} {param2=value}"
        """
        required_param_names = list(self.context.required_params.keys())
        optional_param_names = list(self.context.optional_params.keys())
        all_params = list(dict.fromkeys(required_param_names + optional_param_names))

        logger.debug(f"Параметры orchestrator из БД:")
        logger.debug(f"  Required: {required_param_names}")
        logger.debug(f"  Optional: {optional_param_names}")

        params_parts = []
        for param in all_params:
            if param in param_values:
                value = param_values[param]
                # Для булевых значений и кастомных параметров используем формат {param=value}
                if isinstance(value, bool) or param in custom_params:
                    formatted_value = str(value).lower() if isinstance(value, bool) else str(value)
                    params_parts.append(f'{{{param}={formatted_value}}}')
                else:
                    # Динамический параметр с известным значением
                    params_parts.append(f'{{{param}}}')
            elif param in optional_param_names:
                # Optional параметр без значения - пропускаем
                logger.debug(f"Optional параметр '{param}' пропущен (плейбук использует свой default)")
            elif param in required_param_names:
                # Required параметр без значения - добавляем как динамический
                logger.warning(f"Required параметр '{param}' не имеет значения!")
                params_parts.append(f'{{{param}}}')
            else:
                logger.warning(f"Неизвестный параметр '{param}' пропущен")

        params_string = ' '.join(params_parts)
        playbook_path = f"{self.context.orchestrator_playbook} {params_string}"

        logger.debug(f"Сформирован playbook_path с параметрами: {playbook_path}")

        return playbook_path

    def _build_extra_params(self, param_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Формирует extra_params для передачи в Ansible.

        Args:
            param_values: Словарь всех значений параметров

        Returns:
            Словарь параметров для --extra-vars
        """
        required_param_names = list(self.context.required_params.keys())
        optional_param_names = list(self.context.optional_params.keys())
        all_params = list(dict.fromkeys(required_param_names + optional_param_names))

        extra_params = {}
        for param in all_params:
            if param in param_values:
                extra_params[param] = param_values[param]
            elif param in required_param_names:
                logger.warning(f"Required параметр '{param}' не имеет значения!")

        logger.debug(f"Финальные значения extra_params:")
        for key, value in extra_params.items():
            logger.debug(f"  {key} = {value} (type: {type(value).__name__})")

        return extra_params


class HAProxyOrchestratorExecutor(OrchestratorExecutor):
    """
    Оркестратор с интеграцией HAProxy.

    Использует маппинги из таблицы ApplicationMapping для:
    - Формирования составных имён server::app::haproxy_server
    - Получения HAProxy backend и API URL
    """

    def _add_specific_params(self, param_values: Dict[str, Any]) -> None:
        """
        Добавляет HAProxy-специфичные параметры.

        Args:
            param_values: Словарь параметров для модификации
        """
        if self.context.haproxy_backend:
            param_values['haproxy_backend'] = self.context.haproxy_backend

        if self.context.haproxy_api_url:
            param_values['haproxy_api_url'] = self.context.haproxy_api_url
        else:
            logger.warning("HAProxy API URL not found in database mappings")

    def _build_composite_names(self) -> None:
        """
        Формирует список composite_names с HAProxy маппингом.

        Оптимизировано: все данные загружаются batch-запросами (6-8 SQL вместо N×5).

        Заполняет в контексте:
        - composite_names: Список строк server::app::haproxy_server
        - haproxy_backend: Имя первого найденного backend
        - haproxy_api_url: URL API HAProxy
        - servers_apps_map: Маппинг для логирования
        """
        from app.models.application_mapping import ApplicationMapping
        from app.models.haproxy import HAProxyServer, HAProxyBackend, HAProxyInstance
        from app.models.server import Server

        # Сортируем для корректного cross-server разделения
        sorted_apps = self.sort_instances_for_batches(self.context.apps)

        # ====== BATCH PRELOAD: 6 запросов вместо N×5 ======

        # 1. Предзагрузка серверов (1 запрос)
        server_ids = list(set(app.server_id for app in sorted_apps))
        servers = Server.query.filter(Server.id.in_(server_ids)).all()
        servers_map = {s.id: s for s in servers}

        # 2. Предзагрузка маппингов (1 запрос)
        app_ids = [app.id for app in sorted_apps]
        mappings = ApplicationMapping.query.filter(
            ApplicationMapping.application_id.in_(app_ids),
            ApplicationMapping.entity_type == 'haproxy_server'
        ).all()
        mappings_map = {m.application_id: m for m in mappings}

        # 3. Предзагрузка HAProxy серверов (1 запрос)
        haproxy_server_ids = [m.entity_id for m in mappings if m.entity_id]
        haproxy_servers = {}
        if haproxy_server_ids:
            hs_list = HAProxyServer.query.filter(HAProxyServer.id.in_(haproxy_server_ids)).all()
            haproxy_servers = {hs.id: hs for hs in hs_list}

        # 4. Предзагрузка backends (1 запрос)
        backend_ids = list(set(hs.backend_id for hs in haproxy_servers.values() if hs.backend_id))
        backends_map = {}
        if backend_ids:
            backends = HAProxyBackend.query.filter(HAProxyBackend.id.in_(backend_ids)).all()
            backends_map = {b.id: b for b in backends}

        # 5. Предзагрузка HAProxy instances для API URL (1 запрос)
        instance_ids = list(set(b.haproxy_instance_id for b in backends_map.values() if b.haproxy_instance_id))
        haproxy_instances_map = {}
        if instance_ids:
            # Используем joinedload для загрузки server в одном запросе
            from sqlalchemy.orm import joinedload
            hi_list = HAProxyInstance.query.options(
                joinedload(HAProxyInstance.server)
            ).filter(HAProxyInstance.id.in_(instance_ids)).all()
            haproxy_instances_map = {hi.id: hi for hi in hi_list}

        # ====== ФОРМИРОВАНИЕ РЕЗУЛЬТАТА (без SQL запросов) ======

        instances = []
        backend_info = {}
        haproxy_api_url = None
        unmapped_count = 0

        for app in sorted_apps:
            server = servers_map.get(app.server_id)
            if not server:
                logger.warning(f"Server not found for app {app.instance_name}")
                continue

            short_name = self._get_short_server_name(server)

            # Получаем HAProxy маппинг из предзагруженных данных
            mapping = mappings_map.get(app.id)

            if mapping and mapping.entity_id:
                haproxy_server = haproxy_servers.get(mapping.entity_id)
                if haproxy_server:
                    instance = f"{short_name}::{app.instance_name}::{haproxy_server.server_name}"

                    # Собираем информацию о backend
                    if haproxy_server.backend_id:
                        backend = backends_map.get(haproxy_server.backend_id)
                        if backend:
                            backend_info[backend.backend_name] = {
                                'name': backend.backend_name,
                                'instance_id': backend.haproxy_instance_id
                            }

                            # Получаем API URL из HAProxy Instance
                            if not haproxy_api_url and backend.haproxy_instance_id:
                                haproxy_instance = haproxy_instances_map.get(backend.haproxy_instance_id)
                                if haproxy_instance and haproxy_instance.server:
                                    agent_port = haproxy_instance.server.port
                                    haproxy_api_url = (
                                        f"http://{haproxy_instance.server.ip}:{agent_port}"
                                        f"/api/v1/haproxy/{haproxy_instance.name}"
                                    )
                                    logger.debug(f"HAProxy API URL: {haproxy_api_url}")

                    logger.debug(f"App {app.instance_name} mapped to HAProxy server {haproxy_server.server_name}")
                else:
                    instance = f"{short_name}::{app.instance_name}::{short_name}_{app.instance_name}"
                    unmapped_count += 1
                    logger.warning(f"HAProxy server {mapping.entity_id} not found for app {app.instance_name}")
            else:
                instance = f"{short_name}::{app.instance_name}::{short_name}_{app.instance_name}"
                unmapped_count += 1
                logger.debug(f"No HAProxy mapping for app {app.instance_name}, using default naming")

            instances.append(instance)

        if unmapped_count > 0:
            logger.warning(f"Total unmapped applications: {unmapped_count} of {len(self.context.apps)}")

        # Сохраняем в контекст
        self.context.composite_names = instances

        if backend_info:
            self.context.haproxy_backend = next(iter(backend_info.keys()))
            logger.debug(f"Using HAProxy backend '{self.context.haproxy_backend}' from database mapping")

        self.context.haproxy_api_url = haproxy_api_url

        # Формируем servers_apps_map для логирования
        servers_apps_map = {}
        for comp in instances:
            parts = comp.split('::')
            short_name = parts[0]
            comp_app_name = parts[1]
            if short_name not in servers_apps_map:
                servers_apps_map[short_name] = []
            servers_apps_map[short_name].append(comp_app_name)

        self.context.servers_apps_map = servers_apps_map

        # Логируем результат
        logger.debug(f"Сформированы составные имена для orchestrator (расширенный формат с HAProxy):")
        for comp in instances:
            logger.debug(f"  {comp}")

        logger.debug(f"Mapping серверов и приложений:")
        for srv, app_list in sorted(servers_apps_map.items()):
            logger.debug(f"  {srv}: {', '.join(app_list)}")

        if backend_info:
            logger.debug(f"HAProxy backends: {', '.join(backend_info.keys())}")
        else:
            logger.warning("No HAProxy backend information available, will use app_mapping.yml")


class SimpleOrchestratorExecutor(OrchestratorExecutor):
    """
    Простой оркестратор без внешних зависимостей.

    Используется когда нет HAProxy/Eureka маппингов.
    Формирует composite_names в формате server::app.
    """

    def _build_composite_names(self) -> None:
        """
        Формирует простой список composite_names без HAProxy.

        Оптимизировано: серверы загружаются одним batch-запросом.

        Формат: server::app
        """
        from app.models.server import Server

        sorted_apps = self.sort_instances_for_batches(self.context.apps)

        # Предзагрузка серверов одним запросом (оптимизация N+1)
        server_ids = list(set(app.server_id for app in sorted_apps))
        servers = Server.query.filter(Server.id.in_(server_ids)).all()
        servers_map = {s.id: s for s in servers}

        instances = []
        servers_apps_map = {}

        for app in sorted_apps:
            server = servers_map.get(app.server_id)
            if not server:
                logger.warning(f"Server not found for app {app.instance_name}")
                continue

            short_name = self._get_short_server_name(server)
            instance = f"{short_name}::{app.instance_name}"
            instances.append(instance)

            if short_name not in servers_apps_map:
                servers_apps_map[short_name] = []
            servers_apps_map[short_name].append(app.instance_name)

        self.context.composite_names = instances
        self.context.servers_apps_map = servers_apps_map

        logger.debug(f"Сформированы составные имена для orchestrator (простой формат):")
        for comp in instances:
            logger.debug(f"  {comp}")


def create_orchestrator_executor(context: OrchestratorContext) -> OrchestratorExecutor:
    """
    Фабрика для создания подходящего executor'а.

    Логика выбора:
    1. Если все apps имеют HAProxy mapping → HAProxyOrchestratorExecutor
    2. Иначе → SimpleOrchestratorExecutor

    В будущем можно добавить:
    - EurekaOrchestratorExecutor для Eureka pause/resume

    Args:
        context: Сессионный контекст задачи

    Returns:
        Подходящий OrchestratorExecutor
    """
    from app.models.application_mapping import ApplicationMapping

    # Проверяем наличие HAProxy маппингов для любого из приложений
    has_haproxy_mappings = False

    for app in context.apps:
        mapping = ApplicationMapping.query.filter_by(
            application_id=app.id,
            entity_type='haproxy_server'
        ).first()

        if mapping and mapping.entity_id:
            has_haproxy_mappings = True
            break

    if has_haproxy_mappings:
        logger.info("Using HAProxyOrchestratorExecutor (HAProxy mappings found)")
        return HAProxyOrchestratorExecutor(context)
    else:
        logger.info("Using SimpleOrchestratorExecutor (no HAProxy mappings)")
        return SimpleOrchestratorExecutor(context)

# tests/test_orchestrator_executor.py
"""
Тесты для модуля orchestrator_executor.

Покрывает:
- OrchestratorContext создание и заполнение
- HAProxyOrchestratorExecutor.prepare()
- SimpleOrchestratorExecutor.prepare()
- create_orchestrator_executor() — выбор правильного executor
- sort_instances_for_batches() — сортировка для EVEN/ODD
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from app.services.orchestrator_executor import (
    OrchestratorContext,
    OrchestratorExecutor,
    HAProxyOrchestratorExecutor,
    SimpleOrchestratorExecutor,
    create_orchestrator_executor
)


@dataclass
class MockServer:
    """Мок для модели Server."""
    id: int
    name: str


@dataclass
class MockApplicationInstance:
    """Мок для модели ApplicationInstance."""
    id: int
    instance_name: str
    server_id: int


@dataclass
class MockApplicationMapping:
    """Мок для модели ApplicationMapping."""
    id: int
    application_id: int
    entity_type: str
    entity_id: int = None


@dataclass
class MockHAProxyServer:
    """Мок для модели HAProxyServer."""
    id: int
    server_name: str
    backend_id: int = None


@dataclass
class MockHAProxyBackend:
    """Мок для модели HAProxyBackend."""
    id: int
    backend_name: str
    haproxy_instance_id: int = None


class TestOrchestratorContext:
    """Тесты для dataclass OrchestratorContext."""

    def test_create_minimal_context(self):
        """Создание контекста с минимальными данными."""
        apps = [MockApplicationInstance(id=1, instance_name="app_1", server_id=1)]

        context = OrchestratorContext(
            task_id="task-123",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator-even-odd.yml",
            original_playbook_path="/etc/ansible/update.yml {server}"
        )

        assert context.task_id == "task-123"
        assert context.apps == apps
        assert context.distr_url == "http://nexus/app.zip"
        assert context.orchestrator_playbook == "orchestrator-even-odd.yml"
        assert context.composite_names == []
        assert context.haproxy_backend is None

    def test_create_full_context(self):
        """Создание контекста со всеми полями."""
        apps = [MockApplicationInstance(id=1, instance_name="app_1", server_id=1)]

        context = OrchestratorContext(
            task_id="task-456",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml",
            drain_wait_time=5.0,
            required_params={'app_instances': 'string', 'distr_url': 'string'},
            optional_params={'wait_after_update': 'int'}
        )

        assert context.task_id == "task-456"
        assert len(context.apps) == 1
        assert context.drain_wait_time == 5.0
        assert 'app_instances' in context.required_params


class TestSortInstancesForBatches:
    """Тесты для метода sort_instances_for_batches."""

    @patch('app.models.server.Server')
    def test_single_instance_unchanged(self, mock_server_class):
        """Один экземпляр возвращается как есть."""
        mock_server_class.query.get.return_value = MockServer(id=1, name="server1")

        app = MockApplicationInstance(id=1, instance_name="app_1", server_id=1)
        context = OrchestratorContext(
            task_id="task-1",
            apps=[app],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml"
        )

        executor = SimpleOrchestratorExecutor(context)
        result = executor.sort_instances_for_batches([app])

        assert len(result) == 1
        assert result[0] == app

    @patch('app.models.server.Server')
    def test_two_instances_same_app_different_servers(self, mock_server_class):
        """Два экземпляра одного приложения на разных серверах."""
        def get_server(server_id):
            servers = {
                1: MockServer(id=1, name="server1"),
                2: MockServer(id=2, name="server2"),
            }
            return servers.get(server_id)

        mock_server_class.query.get.side_effect = get_server

        app1 = MockApplicationInstance(id=1, instance_name="app_1", server_id=1)
        app2 = MockApplicationInstance(id=2, instance_name="app_1", server_id=2)

        context = OrchestratorContext(
            task_id="task-1",
            apps=[app1, app2],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml"
        )

        executor = SimpleOrchestratorExecutor(context)
        result = executor.sort_instances_for_batches([app1, app2])

        assert len(result) == 2
        # Проверяем что оба экземпляра присутствуют
        result_ids = [r.id for r in result]
        assert 1 in result_ids
        assert 2 in result_ids

    @patch('app.models.server.Server')
    def test_four_instances_cross_server_distribution(self, mock_server_class):
        """Четыре экземпляра: два приложения x два сервера."""
        def get_server(server_id):
            servers = {
                1: MockServer(id=1, name="server1"),
                2: MockServer(id=2, name="server2"),
            }
            return servers.get(server_id)

        mock_server_class.query.get.side_effect = get_server

        # app_1 на server1 и server2
        app1_s1 = MockApplicationInstance(id=1, instance_name="app_1", server_id=1)
        app1_s2 = MockApplicationInstance(id=2, instance_name="app_1", server_id=2)
        # app_2 на server1 и server2
        app2_s1 = MockApplicationInstance(id=3, instance_name="app_2", server_id=1)
        app2_s2 = MockApplicationInstance(id=4, instance_name="app_2", server_id=2)

        apps = [app1_s1, app1_s2, app2_s1, app2_s2]

        context = OrchestratorContext(
            task_id="task-1",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml"
        )

        executor = SimpleOrchestratorExecutor(context)
        result = executor.sort_instances_for_batches(apps)

        assert len(result) == 4
        # Все экземпляры должны присутствовать
        result_ids = set(r.id for r in result)
        assert result_ids == {1, 2, 3, 4}


class TestSimpleOrchestratorExecutor:
    """Тесты для SimpleOrchestratorExecutor."""

    @patch('app.models.server.Server')
    def test_prepare_builds_composite_names(self, mock_server_class):
        """prepare() формирует composite_names в формате server::app."""
        # Мокаем batch-запрос filter().all() и индивидуальный query.get()
        mock_server = MockServer(id=1, name="fdmz01.example.com")
        mock_server_class.query.filter.return_value.all.return_value = [mock_server]
        mock_server_class.query.get.return_value = mock_server

        app = MockApplicationInstance(id=1, instance_name="jurws_1", server_id=1)
        context = OrchestratorContext(
            task_id="task-1",
            apps=[app],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="docker-orchestrator-sequential.yml",
            original_playbook_path="/etc/ansible/update.yml {server}",
            required_params={'app_instances': 'string', 'distr_url': 'string'},
            optional_params={}
        )

        executor = SimpleOrchestratorExecutor(context)
        playbook_path, extra_params = executor.prepare()

        # Проверяем composite_names
        assert len(context.composite_names) == 1
        assert "fdmz01::jurws_1" in context.composite_names[0]

        # Проверяем что playbook_path содержит параметры
        assert "docker-orchestrator-sequential.yml" in playbook_path

        # Проверяем extra_params
        assert 'app_instances' in extra_params
        assert 'distr_url' in extra_params

    @patch('app.models.server.Server')
    def test_prepare_with_custom_params(self, mock_server_class):
        """prepare() извлекает кастомные параметры из playbook_path."""
        mock_server = MockServer(id=1, name="server1")
        mock_server_class.query.filter.return_value.all.return_value = [mock_server]
        mock_server_class.query.get.return_value = mock_server

        app = MockApplicationInstance(id=1, instance_name="app_1", server_id=1)
        context = OrchestratorContext(
            task_id="task-1",
            apps=[app],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml {server} {unpack=true}",
            required_params={'app_instances': 'string'},
            optional_params={'unpack': 'bool'}
        )

        executor = SimpleOrchestratorExecutor(context)
        playbook_path, extra_params = executor.prepare()

        # Кастомный параметр unpack должен быть в extra_params
        assert 'unpack' in extra_params
        assert extra_params['unpack'] == 'true'


class TestHAProxyOrchestratorExecutor:
    """Тесты для HAProxyOrchestratorExecutor."""

    @patch('sqlalchemy.orm.joinedload')
    @patch('app.models.haproxy.HAProxyInstance')
    @patch('app.models.haproxy.HAProxyBackend')
    @patch('app.models.haproxy.HAProxyServer')
    @patch('app.models.application_mapping.ApplicationMapping')
    @patch('app.models.server.Server')
    def test_prepare_with_haproxy_mapping(
        self,
        mock_server_class,
        mock_mapping_class,
        mock_haproxy_server_class,
        mock_haproxy_backend_class,
        mock_haproxy_instance_class,
        mock_joinedload
    ):
        """prepare() использует HAProxy маппинги для формирования composite_names."""
        # Настройка моков для batch-запросов (filter().all())
        mock_server = MockServer(id=1, name="fdmz01")
        mock_server_class.query.filter.return_value.all.return_value = [mock_server]
        mock_server_class.query.get.return_value = mock_server

        mock_mapping = MockApplicationMapping(
            id=1,
            application_id=1,
            entity_type='haproxy_server',
            entity_id=100
        )
        # Batch-запрос для маппингов
        mock_mapping_class.query.filter.return_value.all.return_value = [mock_mapping]

        mock_haproxy_server = MockHAProxyServer(
            id=100,
            server_name="srv1_jurws_1",
            backend_id=200
        )
        # Batch-запрос для HAProxy серверов
        mock_haproxy_server_class.query.filter.return_value.all.return_value = [mock_haproxy_server]

        mock_haproxy_backend = MockHAProxyBackend(
            id=200,
            backend_name="jurws_backend",
            haproxy_instance_id=300
        )
        # Batch-запрос для backends
        mock_haproxy_backend_class.query.filter.return_value.all.return_value = [mock_haproxy_backend]

        # Настройка HAProxyInstance мока (с joinedload)
        mock_haproxy_instance = MagicMock()
        mock_haproxy_instance.id = 300
        mock_haproxy_instance.name = "default"
        mock_haproxy_instance.server = MagicMock()
        mock_haproxy_instance.server.ip = "10.0.0.1"
        mock_haproxy_instance.server.port = 5000
        # Batch-запрос для HAProxy instances (с options().filter().all())
        mock_haproxy_instance_class.query.options.return_value.filter.return_value.all.return_value = [mock_haproxy_instance]

        app = MockApplicationInstance(id=1, instance_name="jurws_1", server_id=1)
        context = OrchestratorContext(
            task_id="task-1",
            apps=[app],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator-even-odd.yml",
            original_playbook_path="/etc/ansible/update.yml",
            required_params={'app_instances': 'string', 'haproxy_backend': 'string'},
            optional_params={}
        )

        executor = HAProxyOrchestratorExecutor(context)
        playbook_path, extra_params = executor.prepare()

        # Проверяем что composite_names содержит HAProxy server name
        assert len(context.composite_names) == 1
        assert "srv1_jurws_1" in context.composite_names[0]

        # Проверяем что haproxy_backend установлен
        assert context.haproxy_backend == "jurws_backend"

        # Проверяем extra_params
        assert 'haproxy_backend' in extra_params
        assert extra_params['haproxy_backend'] == "jurws_backend"


class TestCreateOrchestratorExecutor:
    """Тесты для фабрики create_orchestrator_executor."""

    @patch('app.models.application_mapping.ApplicationMapping')
    def test_selects_haproxy_executor_when_mapping_exists(self, mock_mapping_class):
        """Выбирает HAProxyOrchestratorExecutor при наличии маппинга."""
        mock_mapping = MockApplicationMapping(
            id=1,
            application_id=1,
            entity_type='haproxy_server',
            entity_id=100
        )
        mock_mapping_class.query.filter_by.return_value.first.return_value = mock_mapping

        app = MockApplicationInstance(id=1, instance_name="app_1", server_id=1)
        context = OrchestratorContext(
            task_id="task-1",
            apps=[app],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml"
        )

        executor = create_orchestrator_executor(context)

        assert isinstance(executor, HAProxyOrchestratorExecutor)

    @patch('app.models.application_mapping.ApplicationMapping')
    def test_selects_simple_executor_when_no_mapping(self, mock_mapping_class):
        """Выбирает SimpleOrchestratorExecutor при отсутствии маппинга."""
        mock_mapping_class.query.filter_by.return_value.first.return_value = None

        app = MockApplicationInstance(id=1, instance_name="app_1", server_id=1)
        context = OrchestratorContext(
            task_id="task-1",
            apps=[app],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml"
        )

        executor = create_orchestrator_executor(context)

        assert isinstance(executor, SimpleOrchestratorExecutor)

    @patch('app.models.application_mapping.ApplicationMapping')
    def test_selects_simple_executor_when_mapping_without_entity_id(self, mock_mapping_class):
        """Выбирает SimpleOrchestratorExecutor если mapping есть, но entity_id пустой."""
        mock_mapping = MockApplicationMapping(
            id=1,
            application_id=1,
            entity_type='haproxy_server',
            entity_id=None  # Нет entity_id
        )
        mock_mapping_class.query.filter_by.return_value.first.return_value = mock_mapping

        app = MockApplicationInstance(id=1, instance_name="app_1", server_id=1)
        context = OrchestratorContext(
            task_id="task-1",
            apps=[app],
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml"
        )

        executor = create_orchestrator_executor(context)

        assert isinstance(executor, SimpleOrchestratorExecutor)


class TestDrainDelayCalculation:
    """Тесты для расчёта drain_delay."""

    def test_drain_delay_from_context(self):
        """drain_wait_time из контекста конвертируется в секунды."""
        apps = [MockApplicationInstance(id=1, instance_name="app_1", server_id=1)]

        context = OrchestratorContext(
            task_id="task-1",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml",
            drain_wait_time=5.0  # 5 минут
        )

        executor = SimpleOrchestratorExecutor(context)
        drain_delay = executor._calculate_drain_delay_seconds()

        assert drain_delay == 300  # 5 * 60 = 300 секунд

    def test_drain_delay_default_when_not_set(self):
        """Используется значение по умолчанию если drain_wait_time не задан."""
        from app.config import OrchestratorDefaults

        apps = [MockApplicationInstance(id=1, instance_name="app_1", server_id=1)]

        context = OrchestratorContext(
            task_id="task-1",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml",
            drain_wait_time=None
        )

        executor = SimpleOrchestratorExecutor(context)
        drain_delay = executor._calculate_drain_delay_seconds()

        assert drain_delay == OrchestratorDefaults.DRAIN_DELAY_SECONDS


class TestExtractUpdatePlaybookName:
    """Тесты для извлечения имени playbook."""

    def test_extract_simple_name(self):
        """Извлечение имени из простого пути."""
        apps = [MockApplicationInstance(id=1, instance_name="app_1", server_id=1)]

        context = OrchestratorContext(
            task_id="task-1",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml"
        )

        executor = SimpleOrchestratorExecutor(context)
        name = executor._extract_update_playbook_name("/etc/ansible/update.yml")

        assert name == "update.yml"

    def test_extract_name_with_params(self):
        """Извлечение имени из пути с параметрами."""
        apps = [MockApplicationInstance(id=1, instance_name="app_1", server_id=1)]

        context = OrchestratorContext(
            task_id="task-1",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="/etc/ansible/update.yml {server} {unpack=true}"
        )

        executor = SimpleOrchestratorExecutor(context)
        name = executor._extract_update_playbook_name(
            "/etc/ansible/update.yml {server} {unpack=true}"
        )

        assert name == "update.yml"

    def test_extract_name_multiple_params(self):
        """Извлечение имени при множественных параметрах."""
        apps = [MockApplicationInstance(id=1, instance_name="app_1", server_id=1)]

        context = OrchestratorContext(
            task_id="task-1",
            apps=apps,
            distr_url="http://nexus/app.zip",
            orchestrator_playbook="orchestrator.yml",
            original_playbook_path="update.yml"
        )

        executor = SimpleOrchestratorExecutor(context)
        name = executor._extract_update_playbook_name(
            "update_multiple_instances.yaml {server} {app} {mode=deliver} {unpack=true}"
        )

        assert name == "update_multiple_instances.yaml"

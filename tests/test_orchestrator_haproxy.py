"""
test_orchestrator_haproxy.py - Unit тесты для интеграции оркестратора с HAProxy
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


def create_test_application(name, server_hostname, app_id=None, server_id=None):
    """Создает тестовое приложение"""
    app = Mock()
    app.id = app_id or 1
    app.instance_name = name
    app.server_id = server_id or 1
    return app


def create_test_server(name, server_id=None):
    """Создает тестовый сервер"""
    server = Mock()
    server.id = server_id or 1
    server.name = name
    return server


def create_test_haproxy_server(name, backend_name=None, server_id=None, backend_id=None):
    """Создает тестовый HAProxy сервер"""
    server = Mock()
    server.id = server_id or 1
    server.name = name
    server.backend_id = backend_id
    return server


def create_test_backend(name, backend_id=None, instance_id=None):
    """Создает тестовый HAProxy backend"""
    backend = Mock()
    backend.id = backend_id or 1
    backend.name = name
    backend.instance_id = instance_id or 1
    return backend


def create_application_mapping(app_id, haproxy_server_id):
    """Создает маппинг между приложением и HAProxy сервером"""
    mapping = Mock()
    mapping.application_id = app_id
    mapping.external_server_id = haproxy_server_id
    mapping.service_type = 'haproxy'
    return mapping


class TestOrchestratorHAProxyIntegration:
    """Тесты интеграции оркестратора с HAProxy"""

    @patch('app.tasks.queue.HAProxyBackend')
    @patch('app.tasks.queue.HAProxyServer')
    @patch('app.tasks.queue.ApplicationMapping')
    @patch('app.tasks.queue.Server')
    def test_prepare_orchestrator_instances_with_mapping(
        self, mock_server_class, mock_mapping_class, mock_haproxy_class, mock_backend_class
    ):
        """Тест формирования параметров с HAProxy маппингом"""
        from app.tasks.queue import TaskQueue

        # Создаем тестовые данные
        app1 = create_test_application("business_1", "node-1", 1, 1)
        app2 = create_test_application("business_2", "node-2", 2, 2)

        server1 = create_test_server("node-1", 1)
        server2 = create_test_server("node-2", 2)

        # Настраиваем Server.query.get
        mock_server_class.query.get.side_effect = lambda x: {1: server1, 2: server2}.get(x)

        # Создаем HAProxy маппинг для app1
        haproxy_server = create_test_haproxy_server("srv1_business_1", server_id=100, backend_id=1)
        backend = create_test_backend("backend1", backend_id=1)
        mapping = create_application_mapping(1, 100)

        # Настраиваем ApplicationMapping.query.filter_by
        def mapping_filter(**kwargs):
            mock_result = Mock()
            if kwargs.get('application_id') == 1:
                mock_result.first.return_value = mapping
            else:
                mock_result.first.return_value = None
            return mock_result

        mock_mapping_class.query.filter_by.side_effect = mapping_filter

        # Настраиваем HAProxyServer.query.get
        mock_haproxy_class.query.get.return_value = haproxy_server

        # Настраиваем HAProxyBackend.query.get
        mock_backend_class.query.get.return_value = backend

        # Создаем TaskQueue и вызываем метод
        task_queue = TaskQueue()
        instances, backend_info, haproxy_api_url = task_queue._prepare_orchestrator_instances_with_haproxy([app1, app2])

        # Проверяем результат
        assert len(instances) == 2
        assert instances[0] == "node-1::business_1::srv1_business_1"
        assert instances[1] == "node-2::business_2::node-2_business_2"
        assert "backend1" in backend_info

    @patch('app.tasks.queue.ApplicationMapping')
    @patch('app.tasks.queue.Server')
    def test_prepare_orchestrator_instances_without_mapping(
        self, mock_server_class, mock_mapping_class
    ):
        """Тест fallback для немаппированных приложений"""
        from app.tasks.queue import TaskQueue

        app = create_test_application("business_1", "node-1", 1, 1)
        server = create_test_server("node-1", 1)

        mock_server_class.query.get.return_value = server

        # Нет маппинга
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_mapping_class.query.filter_by.return_value = mock_filter

        # Вызываем функцию
        task_queue = TaskQueue()
        instances, backend_info, haproxy_api_url = task_queue._prepare_orchestrator_instances_with_haproxy([app])

        # Проверяем результат - должен использоваться fallback формат
        assert len(instances) == 1
        assert instances[0] == "node-1::business_1::node-1_business_1"
        assert backend_info == {}
        assert haproxy_api_url is None

    @patch('app.tasks.queue.HAProxyBackend')
    @patch('app.tasks.queue.HAProxyServer')
    @patch('app.tasks.queue.ApplicationMapping')
    @patch('app.tasks.queue.Server')
    def test_prepare_orchestrator_instances_mixed(
        self, mock_server_class, mock_mapping_class, mock_haproxy_class, mock_backend_class
    ):
        """Тест смешанного сценария (частично маппированные приложения)"""
        from app.tasks.queue import TaskQueue

        # Создаем приложения
        app1 = create_test_application("business_1", "node-1", 1, 1)
        app2 = create_test_application("business_2", "node-2", 2, 2)
        app3 = create_test_application("business_3", "node-3", 3, 3)

        server1 = create_test_server("node-1", 1)
        server2 = create_test_server("node-2", 2)
        server3 = create_test_server("node-3", 3)

        mock_server_class.query.get.side_effect = lambda x: {1: server1, 2: server2, 3: server3}.get(x)

        # Маппинг только для app1 и app3
        haproxy1 = create_test_haproxy_server("srv1_business_1", server_id=100, backend_id=1)
        haproxy3 = create_test_haproxy_server("srv3_business_3", server_id=300, backend_id=2)

        backend1 = create_test_backend("backend1", backend_id=1)
        backend2 = create_test_backend("backend2", backend_id=2)

        mapping1 = create_application_mapping(1, 100)
        mapping3 = create_application_mapping(3, 300)

        def mapping_filter(**kwargs):
            mock_result = Mock()
            app_id = kwargs.get('application_id')
            if app_id == 1:
                mock_result.first.return_value = mapping1
            elif app_id == 3:
                mock_result.first.return_value = mapping3
            else:
                mock_result.first.return_value = None
            return mock_result

        mock_mapping_class.query.filter_by.side_effect = mapping_filter

        mock_haproxy_class.query.get.side_effect = lambda x: {100: haproxy1, 300: haproxy3}.get(x)
        mock_backend_class.query.get.side_effect = lambda x: {1: backend1, 2: backend2}.get(x)

        # Вызываем функцию
        task_queue = TaskQueue()
        instances, backend_info, haproxy_api_url = task_queue._prepare_orchestrator_instances_with_haproxy([app1, app2, app3])

        # Проверяем результат
        assert len(instances) == 3
        assert instances[0] == "node-1::business_1::srv1_business_1"
        assert instances[1] == "node-2::business_2::node-2_business_2"
        assert instances[2] == "node-3::business_3::srv3_business_3"
        assert len(backend_info) == 2
        assert "backend1" in backend_info
        assert "backend2" in backend_info

    @patch('app.tasks.queue.Server')
    def test_prepare_orchestrator_instances_fqdn_parsing(self, mock_server_class):
        """Тест парсинга FQDN имен серверов"""
        from app.tasks.queue import TaskQueue

        app = create_test_application("business_1", "node-1.example.com", 1, 1)
        server = create_test_server("node-1.example.com", 1)

        mock_server_class.query.get.return_value = server

        with patch('app.tasks.queue.ApplicationMapping') as mock_mapping_class:
            mock_filter = Mock()
            mock_filter.first.return_value = None
            mock_mapping_class.query.filter_by.return_value = mock_filter

            task_queue = TaskQueue()
            instances, backend_info, haproxy_api_url = task_queue._prepare_orchestrator_instances_with_haproxy([app])

            # Проверяем что FQDN правильно парсится до короткого имени
            assert len(instances) == 1
            assert instances[0] == "node-1::business_1::node-1_business_1"


class TestValidateHAProxyMappingEndpoint:
    """Тесты API endpoint валидации маппинга"""

    def test_validate_haproxy_mapping_empty_request(self, client):
        """Тест валидации с пустым запросом"""
        response = client.post(
            '/api/orchestrators/validate-haproxy-mapping',
            json={'application_ids': []}
        )
        assert response.status_code == 400

    def test_validate_haproxy_mapping_with_apps(self, client, app):
        """Тест валидации с приложениями"""
        with app.app_context():
            # Создаем тестовые данные в БД
            from app.models.application_instance import ApplicationInstance
            from app.models.server import Server
            from app import db

            # Создаем сервер
            server = Server(name='test-node-1', ip_address='127.0.0.1')
            db.session.add(server)
            db.session.commit()

            # Создаем приложение
            app_instance = ApplicationInstance(
                instance_name='test_app_1',
                server_id=server.id,
                app_type='docker'
            )
            db.session.add(app_instance)
            db.session.commit()

            # Вызываем endpoint
            response = client.post(
                '/api/orchestrators/validate-haproxy-mapping',
                json={'application_ids': [app_instance.id]}
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data['total'] == 1
            assert 'details' in data


# Фикстуры для тестов
@pytest.fixture
def app():
    """Создает Flask приложение для тестов"""
    from app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True

    with app.app_context():
        from app import db
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Создает тестовый клиент"""
    return app.test_client()

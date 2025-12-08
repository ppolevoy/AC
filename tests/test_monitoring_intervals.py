# tests/test_monitoring_intervals.py
"""
Тесты для независимых интервалов опроса в MonitoringTasks.

Покрывает:
- Независимые интервалы для servers, haproxy, eureka
- Обратную совместимость при одинаковых интервалах
- Корректную остановку цикла
- Первый запуск выполняет все операции
- Интеграционный тест реального цикла
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock

# Константа для симуляции времени в тестах
SIMULATION_START_TIME = 1000.0  # Произвольное начальное время для симуляции


class TestMonitoringTasksIntervals:
    """Тесты для независимых интервалов опроса."""

    @patch('app.tasks.monitoring.asyncio')
    def test_first_run_executes_all_operations(self, mock_asyncio):
        """При первом запуске все операции выполняются сразу (last_*=0)."""
        from app.tasks.monitoring import MonitoringTasks

        # Мокаем Flask app
        mock_app = Mock()
        mock_app.app_context.return_value.__enter__ = Mock()
        mock_app.app_context.return_value.__exit__ = Mock()

        # Создаем экземпляр
        monitoring = MonitoringTasks(mock_app)

        # Проверяем начальные значения
        assert monitoring.last_servers_poll == 0
        assert monitoring.last_haproxy_sync == 0
        assert monitoring.last_eureka_sync == 0
        # Отдельные поля для каждой cleanup операции
        assert monitoring.last_cleanup_events == 0
        assert monitoring.last_cleanup_tasks == 0
        assert monitoring.last_cleanup_stale == 0

        # При last_*=0 и now > 0, все условия (now - last >= interval) будут True
        now = time.time()
        assert now - monitoring.last_servers_poll >= 0
        assert now - monitoring.last_haproxy_sync >= 0
        assert now - monitoring.last_eureka_sync >= 0
        assert now - monitoring.last_cleanup_events >= 0

    def test_interval_check_logic(self):
        """Проверка логики проверки интервалов (симуляция алгоритма)."""
        # Симулируем конфигурацию без патчинга (тест не вызывает реальный код)
        POLLING_INTERVAL = 30
        HAPROXY_POLLING_INTERVAL = 60
        EUREKA_POLLING_INTERVAL = 120
        HAPROXY_ENABLED = True
        EUREKA_ENABLED = True

        # Симуляция временных меток
        now = 100.0  # текущее время

        # Последний опрос серверов был 40 секунд назад
        last_servers = 60.0  # now - 40 = 60
        servers_elapsed = now - last_servers
        assert servers_elapsed == 40

        # 40 >= 30 (POLLING_INTERVAL) -> True, должен выполниться
        assert servers_elapsed >= POLLING_INTERVAL

        # Последняя синхронизация HAProxy была 50 секунд назад
        last_haproxy = 50.0  # now - 50 = 50
        haproxy_elapsed = now - last_haproxy
        assert haproxy_elapsed == 50

        # 50 < 60 (HAPROXY_POLLING_INTERVAL) -> False, не должен выполняться
        assert not (haproxy_elapsed >= HAPROXY_POLLING_INTERVAL)

        # Последняя синхронизация Eureka была 130 секунд назад
        last_eureka = -30.0  # now - 130 = -30
        eureka_elapsed = now - last_eureka
        assert eureka_elapsed == 130

        # 130 >= 120 (EUREKA_POLLING_INTERVAL) -> True, должен выполниться
        assert eureka_elapsed >= EUREKA_POLLING_INTERVAL

    def test_time_tracking_fields_exist(self):
        """Проверка наличия полей отслеживания времени в __init__."""
        from app.tasks.monitoring import MonitoringTasks

        mock_app = Mock()
        monitoring = MonitoringTasks(mock_app)

        # Проверяем что все поля существуют и инициализированы в 0
        assert hasattr(monitoring, 'last_servers_poll')
        assert hasattr(monitoring, 'last_haproxy_sync')
        assert hasattr(monitoring, 'last_eureka_sync')
        # Отдельные поля для каждой cleanup операции (изоляция ошибок)
        assert hasattr(monitoring, 'last_cleanup_events')
        assert hasattr(monitoring, 'last_cleanup_tasks')
        assert hasattr(monitoring, 'last_cleanup_stale')

        assert monitoring.last_servers_poll == 0
        assert monitoring.last_haproxy_sync == 0
        assert monitoring.last_eureka_sync == 0
        assert monitoring.last_cleanup_events == 0
        assert monitoring.last_cleanup_tasks == 0
        assert monitoring.last_cleanup_stale == 0

    def test_independent_intervals_correct_simulation(self):
        """
        Корректная симуляция независимых интервалов (не вызывает реальный код).

        Начальные last_* = 0, time.time() возвращает большое значение,
        поэтому первая итерация выполняет все операции.
        """
        # Локальные переменные конфигурации для симуляции
        POLLING_INTERVAL = 2
        HAPROXY_POLLING_INTERVAL = 4
        EUREKA_POLLING_INTERVAL = 6
        HAPROXY_ENABLED = True
        EUREKA_ENABLED = True

        servers_calls = 0
        haproxy_calls = 0
        eureka_calls = 0

        # Начинаем с большого времени (как в реальности)
        start_time = SIMULATION_START_TIME
        last_servers = 0  # Изначально 0, как в коде
        last_haproxy = 0
        last_eureka = 0

        # Симуляция 8 итераций (0-7 секунд)
        for i in range(8):
            now = start_time + i

            if now - last_servers >= POLLING_INTERVAL:
                servers_calls += 1
                last_servers = now

            if HAPROXY_ENABLED and now - last_haproxy >= HAPROXY_POLLING_INTERVAL:
                haproxy_calls += 1
                last_haproxy = now

            if EUREKA_ENABLED and now - last_eureka >= EUREKA_POLLING_INTERVAL:
                eureka_calls += 1
                last_eureka = now

        # t=1000: all execute (1000 - 0 >= any interval)
        #   last_servers=1000, last_haproxy=1000, last_eureka=1000
        # t=1001: none (elapsed=1 < all intervals)
        # t=1002: servers (1002-1000=2 >= 2), last_servers=1002
        # t=1003: none
        # t=1004: servers (1004-1002=2 >= 2), haproxy (1004-1000=4 >= 4)
        #   last_servers=1004, last_haproxy=1004
        # t=1005: none
        # t=1006: servers (1006-1004=2 >= 2), eureka (1006-1000=6 >= 6)
        #   last_servers=1006, last_eureka=1006
        # t=1007: none

        # servers: t=1000,1002,1004,1006 = 4 calls
        assert servers_calls == 4, f"Expected 4 servers calls, got {servers_calls}"
        # haproxy: t=1000,1004 = 2 calls
        assert haproxy_calls == 2, f"Expected 2 haproxy calls, got {haproxy_calls}"
        # eureka: t=1000,1006 = 2 calls
        assert eureka_calls == 2, f"Expected 2 eureka calls, got {eureka_calls}"

    def test_same_intervals_behavior(self):
        """
        При одинаковых интервалах все операции выполняются вместе.
        Проверка обратной совместимости (симуляция алгоритма).
        """
        # Локальные переменные конфигурации для симуляции
        POLLING_INTERVAL = 3
        HAPROXY_POLLING_INTERVAL = 3
        EUREKA_POLLING_INTERVAL = 3
        HAPROXY_ENABLED = True
        EUREKA_ENABLED = True

        servers_calls = 0
        haproxy_calls = 0
        eureka_calls = 0

        start_time = SIMULATION_START_TIME
        last_servers = 0
        last_haproxy = 0
        last_eureka = 0

        # Симуляция 7 итераций
        for i in range(7):
            now = start_time + i

            if now - last_servers >= POLLING_INTERVAL:
                servers_calls += 1
                last_servers = now

            if HAPROXY_ENABLED and now - last_haproxy >= HAPROXY_POLLING_INTERVAL:
                haproxy_calls += 1
                last_haproxy = now

            if EUREKA_ENABLED and now - last_eureka >= EUREKA_POLLING_INTERVAL:
                eureka_calls += 1
                last_eureka = now

        # При одинаковых интервалах все операции выполняются одновременно
        # t=1000: all (first run)
        # t=1001,1002: none
        # t=1003: all (1003-1000=3 >= 3)
        # t=1004,1005: none
        # t=1006: all (1006-1003=3 >= 3)

        assert servers_calls == haproxy_calls == eureka_calls
        assert servers_calls == 3

    def test_disabled_services_not_polled(self):
        """Отключенные сервисы (HAPROXY_ENABLED=False) не опрашиваются (симуляция)."""
        # Локальные переменные конфигурации для симуляции
        POLLING_INTERVAL = 2
        HAPROXY_POLLING_INTERVAL = 2
        EUREKA_POLLING_INTERVAL = 2
        HAPROXY_ENABLED = False  # Отключен
        EUREKA_ENABLED = False   # Отключен

        servers_calls = 0
        haproxy_calls = 0
        eureka_calls = 0

        start_time = SIMULATION_START_TIME
        last_servers = 0
        last_haproxy = 0
        last_eureka = 0

        for i in range(5):
            now = start_time + i

            if now - last_servers >= POLLING_INTERVAL:
                servers_calls += 1
                last_servers = now

            # HAProxy отключен
            if HAPROXY_ENABLED and now - last_haproxy >= HAPROXY_POLLING_INTERVAL:
                haproxy_calls += 1
                last_haproxy = now

            # Eureka отключена
            if EUREKA_ENABLED and now - last_eureka >= EUREKA_POLLING_INTERVAL:
                eureka_calls += 1
                last_eureka = now

        # servers вызывается
        assert servers_calls > 0
        # haproxy и eureka НЕ вызываются (отключены)
        assert haproxy_calls == 0
        assert eureka_calls == 0


class TestMonitoringTasksGracefulShutdown:
    """Тесты для корректной остановки цикла мониторинга."""

    def test_stop_event_exists(self):
        """Проверка наличия stop_event."""
        from app.tasks.monitoring import MonitoringTasks

        mock_app = Mock()
        monitoring = MonitoringTasks(mock_app)

        assert hasattr(monitoring, 'stop_event')
        assert isinstance(monitoring.stop_event, threading.Event)
        assert not monitoring.stop_event.is_set()

    def test_stop_sets_event(self):
        """stop() устанавливает stop_event."""
        from app.tasks.monitoring import MonitoringTasks

        mock_app = Mock()
        monitoring = MonitoringTasks(mock_app)

        # Симуляция запущенного потока
        monitoring.thread = Mock()
        monitoring.thread.is_alive.return_value = True

        with patch('app.tasks.queue.task_queue'):
            monitoring.stop()

        assert monitoring.stop_event.is_set()

    @patch('app.tasks.monitoring.time.sleep')
    @patch('app.tasks.monitoring.asyncio')
    def test_loop_exits_on_stop_event(self, mock_asyncio, mock_sleep):
        """Цикл завершается при установке stop_event."""
        from app.tasks.monitoring import MonitoringTasks

        mock_app = Mock()
        mock_app.app_context.return_value.__enter__ = Mock()
        mock_app.app_context.return_value.__exit__ = Mock()

        monitoring = MonitoringTasks(mock_app)

        # Устанавливаем stop_event до запуска
        monitoring.stop_event.set()

        # Мокаем asyncio
        mock_loop = Mock()
        mock_asyncio.new_event_loop.return_value = mock_loop

        # Запускаем _run_monitoring напрямую
        monitoring._run_monitoring()

        # Цикл должен завершиться сразу (while not stop_event.is_set() = False)
        # sleep не должен вызываться много раз
        assert mock_sleep.call_count == 0  # Цикл не выполнился ни разу


class TestMonitoringTasksStartLogging:
    """Тесты для логирования интервалов при старте."""

    @patch('app.tasks.queue.task_queue')
    @patch('app.tasks.monitoring.logger')
    def test_start_logs_intervals(self, mock_logger, mock_task_queue):
        """start() логирует настроенные интервалы."""
        from app.tasks.monitoring import MonitoringTasks

        mock_app = Mock()
        monitoring = MonitoringTasks(mock_app)

        # Мокаем thread чтобы не запускать реальный поток
        with patch.object(monitoring, 'thread', None):
            with patch('threading.Thread') as mock_thread:
                mock_thread_instance = Mock()
                mock_thread.return_value = mock_thread_instance

                monitoring.start()

                # Проверяем что logger.info был вызван с информацией об интервалах
                # (используются реальные значения Config)
                calls = [str(call) for call in mock_logger.info.call_args_list]
                interval_log_found = any(
                    'servers=' in str(call) and 'haproxy=' in str(call) and 'eureka=' in str(call)
                    for call in calls
                )
                assert interval_log_found, f"Interval logging not found in: {calls}"


class TestMonitoringTasksIntegration:
    """Интеграционные тесты для реального цикла мониторинга."""

    @patch('app.tasks.monitoring.time.sleep')
    @patch('app.tasks.monitoring.time.time')
    def test_real_monitoring_executes_tasks_by_interval(self, mock_time, mock_sleep):
        """
        Интеграционный тест: проверяет что реальный _run_task_if_due()
        вызывает методы по интервалам.
        """
        from app.tasks.monitoring import MonitoringTasks

        # Создаём mock app
        mock_app = Mock()
        mock_app.app_context.return_value.__enter__ = Mock(return_value=None)
        mock_app.app_context.return_value.__exit__ = Mock(return_value=None)

        monitoring = MonitoringTasks(mock_app)

        # Счётчики вызовов
        poll_calls = []

        # Создаём async mock для _poll_servers
        async def mock_poll():
            poll_calls.append(mock_time.return_value)

        # Симуляция времени: каждый вызов time.time() возвращает следующее значение
        time_sequence = [SIMULATION_START_TIME + i for i in range(10)]
        mock_time.side_effect = time_sequence

        # Мокаем loop
        mock_loop = Mock()
        mock_loop.run_until_complete = Mock(side_effect=lambda coro: None)
        mock_loop.is_closed.return_value = False
        monitoring.loop = mock_loop

        # Интервал передаётся напрямую в _run_task_if_due, патч Config не нужен
        POLLING_INTERVAL = 2

        # Патчим метод _poll_servers
        with patch.object(monitoring, '_poll_servers', mock_poll):
            # Вызываем _run_task_if_due напрямую несколько раз
            # t=1000: should execute (1000 - 0 >= 2)
            monitoring._run_task_if_due(
                task_name="опрос серверов",
                last_run_attr="last_servers_poll",
                interval=POLLING_INTERVAL,
                task_method=monitoring._poll_servers
            )
            first_last = monitoring.last_servers_poll

            # t=1001: should NOT execute (1001 - 1000 = 1 < 2)
            monitoring._run_task_if_due(
                task_name="опрос серверов",
                last_run_attr="last_servers_poll",
                interval=POLLING_INTERVAL,
                task_method=monitoring._poll_servers
            )

            # t=1002: should execute (1002 - 1000 = 2 >= 2)
            monitoring._run_task_if_due(
                task_name="опрос серверов",
                last_run_attr="last_servers_poll",
                interval=POLLING_INTERVAL,
                task_method=monitoring._poll_servers
            )

        # Проверяем что run_until_complete был вызван 2 раза
        assert mock_loop.run_until_complete.call_count == 2
        # Проверяем что last_servers_poll обновился
        assert monitoring.last_servers_poll > first_last

    def test_run_task_if_due_updates_time_only_on_success(self):
        """
        Проверяет что _run_task_if_due() обновляет last_run только при успехе.
        При ошибке время не обновляется для быстрого retry.
        """
        from app.tasks.monitoring import MonitoringTasks

        mock_app = Mock()
        mock_app.app_context.return_value.__enter__ = Mock(return_value=None)
        mock_app.app_context.return_value.__exit__ = Mock(return_value=None)

        monitoring = MonitoringTasks(mock_app)
        monitoring.loop = Mock()
        monitoring.loop.run_until_complete = Mock()
        monitoring.loop.is_closed.return_value = False

        # Метод который всегда падает
        call_count = 0

        async def failing_method():
            nonlocal call_count
            call_count += 1
            raise Exception("Test error")

        initial_last = monitoring.last_servers_poll  # 0
        POLLING_INTERVAL = 1

        with patch('app.tasks.monitoring.time.time', return_value=SIMULATION_START_TIME):
            # Мокаем run_until_complete чтобы он вызывал исключение
            monitoring.loop.run_until_complete.side_effect = Exception("Test error")

            monitoring._run_task_if_due(
                task_name="опрос серверов",
                last_run_attr="last_servers_poll",
                interval=POLLING_INTERVAL,
                task_method=failing_method
            )

        # Время НЕ должно обновиться при ошибке
        assert monitoring.last_servers_poll == initial_last

    def test_helper_method_exists_and_callable(self):
        """Проверяет что helper-метод _run_task_if_due() существует."""
        from app.tasks.monitoring import MonitoringTasks

        mock_app = Mock()
        monitoring = MonitoringTasks(mock_app)

        assert hasattr(monitoring, '_run_task_if_due')
        assert callable(monitoring._run_task_if_due)

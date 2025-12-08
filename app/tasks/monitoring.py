import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MonitoringTasks:
    """
    Класс для управления задачами мониторинга серверов и приложений
    """
    
    def __init__(self, app):
        self.app = app
        self.loop = None
        self.stop_event = threading.Event()
        self.thread = None

        # Время последнего выполнения каждой операции (для независимых интервалов)
        self.last_servers_poll = 0
        self.last_haproxy_sync = 0
        self.last_eureka_sync = 0
        # Отдельные поля для каждой cleanup операции (изоляция ошибок)
        self.last_cleanup_events = 0
        self.last_cleanup_tasks = 0
        self.last_cleanup_stale = 0
    
    def start(self):
        """Запуск потока с циклом задач мониторинга"""
        if self.thread and self.thread.is_alive():
            logger.warning("Задачи мониторинга уже запущены")
            return
        
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_monitoring, daemon=True)

        # Логируем настроенные интервалы ДО запуска потока
        from app.config import Config
        logger.info(
            f"Интервалы опроса: servers={Config.POLLING_INTERVAL}s, "
            f"haproxy={Config.HAPROXY_POLLING_INTERVAL}s (enabled={Config.HAPROXY_ENABLED}), "
            f"eureka={Config.EUREKA_POLLING_INTERVAL}s (enabled={Config.EUREKA_ENABLED})"
        )

        self.thread.start()

        # Запускаем обработчик очереди задач
        from app.tasks.queue import task_queue
        task_queue.start_processing()

        logger.info("Задачи мониторинга и обработчик очереди задач запущены")
    
    def stop(self):
        """Остановка потока с задачами мониторинга"""
        if not self.thread or not self.thread.is_alive():
            logger.warning("Задачи мониторинга не запущены")
            return
        
        logger.info("Останавливаем задачи мониторинга...")
        self.stop_event.set()
        self.thread.join(timeout=30)
        
        # Останавливаем обработчик очереди задач
        from app.tasks.queue import task_queue
        task_queue.stop_processing()
        
        logger.info("Задачи мониторинга и обработчик очереди задач остановлены")

    def _run_task_if_due(self, task_name: str, last_run_attr: str, interval: int,
                         task_method, is_async: bool = True) -> None:
        """
        Выполняет задачу если прошёл интервал с последнего запуска.
        Обновляет last_run только при успешном выполнении.

        Args:
            task_name: Имя задачи для логирования ошибок
            last_run_attr: Имя атрибута для хранения времени последнего запуска
            interval: Интервал в секундах между запусками
            task_method: Метод для выполнения
            is_async: True если метод асинхронный (требует run_until_complete)
        """
        now = time.time()
        if now - getattr(self, last_run_attr) < interval:
            return

        with self.app.app_context():
            try:
                if is_async:
                    self.loop.run_until_complete(task_method())
                else:
                    task_method()
                # Обновляем время только при успехе - при ошибке retry через 1 сек
                setattr(self, last_run_attr, now)
            except Exception as e:
                logger.error(f"Ошибка при {task_name}: {str(e)}")

    def _run_monitoring(self):
        """
        Основной метод выполнения задач мониторинга.

        Каждая операция выполняется по своему интервалу:
        - Опрос серверов: POLLING_INTERVAL
        - Синхронизация HAProxy: HAPROXY_POLLING_INTERVAL
        - Синхронизация Eureka: EUREKA_POLLING_INTERVAL
        - Очистки: POLLING_INTERVAL

        Config читается каждую итерацию для поддержки hot-reload интервалов.
        """
        from app.config import Config

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            logger.info("Цикл мониторинга запущен")

            while not self.stop_event.is_set():
                # Опрос серверов
                self._run_task_if_due(
                    task_name="опрос серверов",
                    last_run_attr="last_servers_poll",
                    interval=Config.POLLING_INTERVAL,
                    task_method=self._poll_servers
                )

                # Синхронизация HAProxy
                if Config.HAPROXY_ENABLED:
                    self._run_task_if_due(
                        task_name="синхронизация HAProxy",
                        last_run_attr="last_haproxy_sync",
                        interval=Config.HAPROXY_POLLING_INTERVAL,
                        task_method=self._sync_haproxy_instances
                    )

                # Синхронизация Eureka
                if Config.EUREKA_ENABLED:
                    self._run_task_if_due(
                        task_name="синхронизация Eureka",
                        last_run_attr="last_eureka_sync",
                        interval=Config.EUREKA_POLLING_INTERVAL,
                        task_method=self._sync_eureka_servers
                    )

                # Cleanup операции (каждая в своём контексте для изоляции ошибок)
                self._run_task_if_due(
                    task_name="очистка старых событий",
                    last_run_attr="last_cleanup_events",
                    interval=Config.POLLING_INTERVAL,
                    task_method=self._clean_old_events,
                    is_async=False
                )

                self._run_task_if_due(
                    task_name="очистка старых задач",
                    last_run_attr="last_cleanup_tasks",
                    interval=Config.POLLING_INTERVAL,
                    task_method=self._cleanup_old_tasks,
                    is_async=False
                )

                self._run_task_if_due(
                    task_name="очистка stale-приложений",
                    last_run_attr="last_cleanup_stale",
                    interval=Config.POLLING_INTERVAL,
                    task_method=self._cleanup_stale_applications,
                    is_async=False
                )

                # Проверка каждую секунду для быстрого реагирования на stop_event
                time.sleep(1)

        except Exception as e:
            logger.error(f"Критическая ошибка в цикле мониторинга: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            if self.loop and not self.loop.is_closed():
                self.loop.close()
            logger.info("Цикл мониторинга завершен")

    def _cleanup_old_tasks(self):
        """Очистка старых задач в очереди."""
        from app.tasks.queue import task_queue
        from app.config import Config
        task_queue.clear_completed_tasks(days_old=Config.CLEAN_TASKS_OLDER_THAN)
    
    async def _poll_servers(self):
        """Опрос всех серверов"""
        try:
            from app.models.server import Server
            from app.services.agent_service import AgentService
            
            servers = Server.query.all()
            
            if not servers:
                logger.info("Нет серверов для опроса")
                return
            
            logger.info(f"Начинаем опрос {len(servers)} серверов")
            
            # Создаем список задач для асинхронного выполнения
            tasks = []
            for server in servers:
                task = AgentService.update_server_applications(server.id)
                tasks.append(task)
            
            # Запускаем все задачи асинхронно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            success_count = sum(1 for r in results if r is True)
            error_count = sum(1 for r in results if isinstance(r, Exception))
            skipped_count = len(results) - success_count - error_count
            
            logger.info(f"Опрос серверов завершен: {success_count} успешно, {error_count} с ошибками, {skipped_count} пропущено")
            
            # Логируем ошибки
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    server = servers[i]
                    logger.error(f"Ошибка при опросе сервера {server.name}: {str(result)}")
            
        except Exception as e:
            logger.error(f"Ошибка при опросе серверов: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _sync_haproxy_instances(self):
        """Синхронизация всех активных HAProxy инстансов"""
        try:
            from app.models.haproxy import HAProxyInstance
            from app.services.haproxy_service import HAProxyService
            from app.services.haproxy_mapper import HAProxyMapper

            # Получаем все активные HAProxy инстансы
            instances = HAProxyInstance.query.filter_by(is_active=True).all()

            if not instances:
                logger.debug("Нет активных HAProxy инстансов для синхронизации")
                return

            logger.info(f"Начинаем синхронизацию {len(instances)} HAProxy инстансов")

            # Создаем список задач для асинхронного выполнения
            tasks = []
            for instance in instances:
                task = HAProxyService.sync_haproxy_instance(instance)
                tasks.append(task)

            # Запускаем все задачи асинхронно
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Обрабатываем результаты
            success_count = sum(1 for r in results if r is True)
            error_count = sum(1 for r in results if isinstance(r, Exception) or r is False)

            logger.info(f"Синхронизация HAProxy завершена: {success_count} успешно, {error_count} с ошибками")

            # Выполняем маппинг серверов на приложения после синхронизации
            try:
                mapped, total = HAProxyMapper.remap_all_servers()
                if total > 0:
                    logger.info(f"Маппинг HAProxy серверов: {mapped}/{total} сопоставлено")
            except Exception as e:
                logger.error(f"Ошибка при маппинге серверов: {str(e)}")

        except Exception as e:
            logger.error(f"Ошибка при синхронизации HAProxy инстансов: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    async def _sync_eureka_servers(self):
        """Синхронизация всех активных Eureka серверов"""
        try:
            from app.models.eureka import EurekaServer
            from app.services.eureka_service import EurekaService
            from app.services.eureka_mapper import EurekaMapper

            # Получаем все активные Eureka серверы
            eureka_servers = EurekaServer.query.filter_by(
                is_active=True,
                removed_at=None
            ).all()

            if not eureka_servers:
                logger.debug("Нет активных Eureka серверов для синхронизации")
                return

            logger.info(f"Начинаем синхронизацию {len(eureka_servers)} Eureka серверов")

            # Создаем список задач для асинхронного выполнения
            tasks = []
            for eureka_server in eureka_servers:
                task = EurekaService.sync_eureka_server(eureka_server)
                tasks.append(task)

            # Запускаем все задачи асинхронно
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Обрабатываем результаты
            success_count = sum(1 for r in results if r is True)
            error_count = sum(1 for r in results if isinstance(r, Exception) or r is False)

            logger.info(f"Синхронизация Eureka завершена: {success_count} успешно, {error_count} с ошибками")

            # Выполняем маппинг экземпляров на приложения после синхронизации
            try:
                mapped_count, total_unmapped = EurekaMapper.map_instances_to_applications()
                if total_unmapped > 0:
                    logger.info(f"Маппинг Eureka экземпляров: {mapped_count}/{total_unmapped} сопоставлено")
            except Exception as e:
                logger.error(f"Ошибка при маппинге экземпляров: {str(e)}")

        except Exception as e:
            logger.error(f"Ошибка при синхронизации Eureka серверов: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _clean_old_events(self):
        """Очистка старых событий"""
        try:
            from app import db
            from app.models.event import Event
            from app.config import Config

            # Определяем дату, старше которой события нужно удалить
            cutoff_date = datetime.utcnow() - timedelta(days=Config.CLEAN_EVENTS_OLDER_THAN)

            # Удаляем старые события
            deleted_count = Event.query.filter(Event.timestamp < cutoff_date).delete()
            db.session.commit()

            if deleted_count > 0:
                logger.info(f"Удалено {deleted_count} старых событий")

        except Exception as e:
            from app import db
            db.session.rollback()
            logger.error(f"Ошибка при очистке старых событий: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _cleanup_stale_applications(self):
        """
        Обрабатывает приложения в статусе offline:
        1. День 4: назначает тег 'pending_removal'
        2. День 7: устанавливает deleted_at (soft delete) + Event
        3. День 37: физическое удаление из БД (hard delete)
        """
        try:
            from app import db
            from app.models.application_instance import ApplicationInstance
            from app.models.event import Event
            from app.services.system_tags import SystemTagsService
            from app.config import Config

            now = datetime.utcnow()
            warning_threshold = now - timedelta(
                days=Config.APP_OFFLINE_REMOVAL_DAYS - Config.APP_OFFLINE_WARNING_DAYS_BEFORE
            )
            removal_threshold = now - timedelta(days=Config.APP_OFFLINE_REMOVAL_DAYS)
            hard_delete_threshold = now - timedelta(
                days=Config.APP_OFFLINE_REMOVAL_DAYS + Config.APP_HARD_DELETE_DAYS
            )

            protected_tags = set(Config.APP_REMOVAL_PROTECTED_TAGS)

            def is_protected(app):
                """Проверка защиты тегами ver.lock/status.lock/disable"""
                app_tags = set(app.tags_cache.split(',')) if app.tags_cache else set()
                return bool(app_tags & protected_tags)

            # 1. Предупреждение (тег pending_removal на 4-й день)
            apps_to_warn = ApplicationInstance.query.filter(
                ApplicationInstance.status == 'offline',
                ApplicationInstance.deleted_at.is_(None),
                ApplicationInstance.last_seen <= warning_threshold,
                ApplicationInstance.last_seen > removal_threshold
            ).all()

            warned_count = 0
            for app in apps_to_warn:
                if not is_protected(app):
                    SystemTagsService.assign_tag(app.id, 'pending_removal')
                    warned_count += 1

            # 2. Soft delete (deleted_at на 7-й день)
            apps_to_remove = ApplicationInstance.query.filter(
                ApplicationInstance.status == 'offline',
                ApplicationInstance.deleted_at.is_(None),
                ApplicationInstance.last_seen <= removal_threshold
            ).all()

            removed_count = 0
            for app in apps_to_remove:
                if not is_protected(app):
                    app.deleted_at = now
                    SystemTagsService.remove_tag(app.id, 'pending_removal')
                    # Event аудит
                    event = Event(
                        instance_id=app.id,
                        server_id=app.server_id,
                        event_type='auto_removed',
                        status='success',
                        details=f'Auto-removed after {Config.APP_OFFLINE_REMOVAL_DAYS} days offline'
                    )
                    db.session.add(event)
                    removed_count += 1

            # 3. Hard delete (физическое удаление через +30 дней после soft delete)
            apps_to_hard_delete = ApplicationInstance.query.filter(
                ApplicationInstance.deleted_at.isnot(None),
                ApplicationInstance.deleted_at <= hard_delete_threshold
            ).all()

            hard_deleted_count = 0
            for app in apps_to_hard_delete:
                db.session.delete(app)
                hard_deleted_count += 1

            db.session.commit()

            if warned_count or removed_count or hard_deleted_count:
                logger.info(
                    f"Stale apps cleanup: {warned_count} warned, "
                    f"{removed_count} soft-deleted, {hard_deleted_count} hard-deleted"
                )

        except Exception as e:
            from app import db
            db.session.rollback()
            logger.error(f"Ошибка при очистке stale-приложений: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

# Глобальный экземпляр задач мониторинга
monitoring_tasks = None

def init_monitoring(app):
    """Инициализация задач мониторинга при запуске приложения"""
    global monitoring_tasks
    
    if monitoring_tasks:
        # Останавливаем существующие задачи, если они были
        monitoring_tasks.stop()
    
    # Создаем и запускаем новый экземпляр задач
    monitoring_tasks = MonitoringTasks(app)
    monitoring_tasks.start()
    
    # Регистрируем обработчик для корректной остановки при завершении приложения
    import atexit
    atexit.register(lambda: monitoring_tasks.stop() if monitoring_tasks else None)

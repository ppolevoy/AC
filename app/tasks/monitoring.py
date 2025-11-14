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
    
    def start(self):
        """Запуск потока с циклом задач мониторинга"""
        if self.thread and self.thread.is_alive():
            logger.warning("Задачи мониторинга уже запущены")
            return
        
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_monitoring, daemon=True)
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
    
    def _run_monitoring(self):
        """Основной метод выполнения задач мониторинга"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            logger.info("Цикл мониторинга запущен")
            while not self.stop_event.is_set():
                # Запускаем основную задачу мониторинга
                with self.app.app_context():
                    try:
                        self.loop.run_until_complete(self._poll_servers())
                    except Exception as e:
                        logger.error(f"Ошибка при опросе серверов: {str(e)}")
                
                # Запускаем задачу очистки старых событий
                with self.app.app_context():
                    try:
                        self._clean_old_events()
                    except Exception as e:
                        logger.error(f"Ошибка при очистке старых событий: {str(e)}")
                
                # Запускаем задачу очистки старых задач в очереди
                with self.app.app_context():
                    try:
                        from app.tasks.queue import task_queue
                        task_queue.clear_completed_tasks()
                    except Exception as e:
                        logger.error(f"Ошибка при очистке старых задач: {str(e)}")

                # Запускаем задачу синхронизации HAProxy (если включена)
                with self.app.app_context():
                    try:
                        from app.config import Config
                        if Config.HAPROXY_ENABLED:
                            self.loop.run_until_complete(self._sync_haproxy_instances())
                    except Exception as e:
                        logger.error(f"Ошибка при синхронизации HAProxy: {str(e)}")

                # Запускаем задачу синхронизации Eureka (если включена)
                with self.app.app_context():
                    try:
                        from app.config import Config
                        if Config.EUREKA_ENABLED:
                            self.loop.run_until_complete(self._sync_eureka_servers())
                    except Exception as e:
                        logger.error(f"Ошибка при синхронизации Eureka: {str(e)}")

                # Ждем до следующего цикла опроса
                from app.config import Config
                logger.info(f"Следующий опрос через {Config.POLLING_INTERVAL} секунд")
                for _ in range(Config.POLLING_INTERVAL):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
        except Exception as e:
            logger.error(f"Критическая ошибка в цикле мониторинга: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            if self.loop and not self.loop.is_closed():
                self.loop.close()
            logger.info("Цикл мониторинга завершен")
    
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

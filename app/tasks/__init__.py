# app/tasks/__init__.py

def init_tasks(app):
    """Инициализация задач мониторинга при запуске приложения"""
    from app.tasks.monitoring import init_monitoring
    from app.tasks.queue import task_queue
    
    # Инициализация очереди задач
    task_queue.init_app(app)
    
    # Инициализация задач мониторинга
    init_monitoring(app)

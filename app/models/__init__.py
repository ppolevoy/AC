# app/models/__init__.py
# РЕФАКТОРИНГ - обновлены импорты после переработки моделей

from app.models.server import Server
from app.models.application_catalog import ApplicationCatalog
from app.models.application_instance import ApplicationInstance
from app.models.application_group import ApplicationGroup
from app.models.event import Event
from app.models.orchestrator_playbook import OrchestratorPlaybook
from app.models.haproxy import HAProxyInstance, HAProxyBackend, HAProxyServer, HAProxyServerStatusHistory

# Алиас для обратной совместимости с кодом, использующим Application
Application = ApplicationInstance

__all__ = [
    'Server',
    'Application',  # Алиас для ApplicationInstance
    'ApplicationInstance',
    'ApplicationCatalog',
    'ApplicationGroup',
    'Event',
    'OrchestratorPlaybook',
    'HAProxyInstance',
    'HAProxyBackend',
    'HAProxyServer',
    'HAProxyServerStatusHistory'
]
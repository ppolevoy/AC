# app/models/__init__.py
# РЕФАКТОРИНГ - обновлены импорты после переработки моделей

from app.models.server import Server
from app.models.application_catalog import ApplicationCatalog
from app.models.application_instance import ApplicationInstance
from app.models.application_group import ApplicationGroup
from app.models.event import Event
from app.models.orchestrator_playbook import OrchestratorPlaybook
from app.models.haproxy import HAProxyInstance, HAProxyBackend, HAProxyServer, HAProxyServerStatusHistory
from app.models.application_mapping import ApplicationMapping, ApplicationMappingHistory, MappingType
from app.models.tag import Tag, ApplicationInstanceTag, ApplicationGroupTag, TagHistory
from app.models.application_version_history import ApplicationVersionHistory
from app.models.mailing_group import MailingGroup
from app.models.task import Task

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
    'HAProxyServerStatusHistory',
    'ApplicationMapping',
    'ApplicationMappingHistory',
    'MappingType',
    'Tag',
    'ApplicationInstanceTag',
    'ApplicationGroupTag',
    'TagHistory',
    'ApplicationVersionHistory',
    'MailingGroup',
    'Task'
]
# app/api/haproxy_routes.py
"""
API endpoints для управления HAProxy интеграцией.
Фаза 1: Read-only операции (мониторинг).
"""

from flask import jsonify, request
import logging
import asyncio
from datetime import datetime

from app.api import bp
from app import db
from app.models.haproxy import HAProxyInstance, HAProxyBackend, HAProxyServer
from app.models.server import Server
from app.services.haproxy_service import HAProxyService
from app.services.haproxy_mapper import HAProxyMapper

logger = logging.getLogger(__name__)


@bp.route('/haproxy/instances', methods=['GET'])
def get_haproxy_instances():
    """
    Получение списка всех HAProxy инстансов.

    Query parameters:
        active_only: если true, возвращает только активные инстансы
    """
    try:
        active_only = request.args.get('active_only', 'false').lower() == 'true'

        query = HAProxyInstance.query
        if active_only:
            query = query.filter_by(is_active=True)

        instances = query.all()

        result = {
            'success': True,
            'count': len(instances),
            'instances': [inst.to_dict() for inst in instances]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting HAProxy instances: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/instances/<int:instance_id>', methods=['GET'])
def get_haproxy_instance(instance_id):
    """
    Получение деталей конкретного HAProxy инстанса.

    Args:
        instance_id: ID HAProxy инстанса
    """
    try:
        instance = HAProxyInstance.query.get(instance_id)

        if not instance:
            return jsonify({
                'success': False,
                'error': 'HAProxy instance not found'
            }), 404

        return jsonify({
            'success': True,
            'instance': instance.to_dict(include_backends=True)
        }), 200

    except Exception as e:
        logger.error(f"Error getting HAProxy instance {instance_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/instances/<int:instance_id>/backends', methods=['GET'])
def get_instance_backends(instance_id):
    """
    Получение списка backends для HAProxy инстанса.

    Args:
        instance_id: ID HAProxy инстанса

    Query parameters:
        include_removed: если true, возвращает также удаленные бэкенды
    """
    try:
        instance = HAProxyInstance.query.get(instance_id)

        if not instance:
            return jsonify({
                'success': False,
                'error': 'HAProxy instance not found'
            }), 404

        # Новый параметр для показа удаленных бэкендов
        include_removed = request.args.get('include_removed', 'false').lower() == 'true'

        query = HAProxyBackend.query.filter_by(haproxy_instance_id=instance_id)

        # Фильтрация удаленных только если не запрошено обратное
        if not include_removed:
            query = query.filter(HAProxyBackend.removed_at.is_(None))

        backends = query.order_by(HAProxyBackend.backend_name).all()

        result = {
            'success': True,
            'instance_id': instance_id,
            'instance_name': instance.name,
            'count': len(backends),
            'backends': [backend.to_dict(include_servers=True) for backend in backends],
            'include_removed': include_removed
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting backends for instance {instance_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/backends/<int:backend_id>/servers', methods=['GET'])
def get_backend_servers(backend_id):
    """
    Получение списка серверов в backend.

    Args:
        backend_id: ID backend
    """
    try:
        backend = HAProxyBackend.query.get(backend_id)

        if not backend:
            return jsonify({
                'success': False,
                'error': 'Backend not found'
            }), 404

        # Получаем только не удаленные серверы
        servers = HAProxyServer.query.filter_by(
            backend_id=backend_id
        ).filter(HAProxyServer.removed_at.is_(None)).all()

        result = {
            'success': True,
            'backend_id': backend_id,
            'backend_name': backend.backend_name,
            'count': len(servers),
            'servers': [server.to_dict(include_application=True) for server in servers]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting servers for backend {backend_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/backends/<int:backend_id>/polling', methods=['PUT'])
def update_backend_polling(backend_id):
    """
    Включить или отключить опрос для конкретного бэкенда.

    Args:
        backend_id: ID бэкенда

    Body:
        enable_polling: bool - включить (true) или отключить (false) опрос
    """
    try:
        data = request.json
        if not data or 'enable_polling' not in data:
            return jsonify({
                'success': False,
                'error': 'Поле enable_polling обязательно'
            }), 400

        backend = HAProxyBackend.query.get(backend_id)
        if not backend:
            return jsonify({
                'success': False,
                'error': 'Backend не найден'
            }), 404

        old_state = backend.enable_polling
        new_state = data['enable_polling']

        # Обновляем состояние опроса
        backend.enable_polling = new_state

        # При отключении опроса помечаем как удаленный
        if not new_state and old_state:
            backend.soft_delete()
            logger.info(f"Backend {backend.backend_name} (id={backend_id}) polling disabled and marked as removed")
        # При включении опроса восстанавливаем
        elif new_state and not old_state:
            backend.restore()
            logger.info(f"Backend {backend.backend_name} (id={backend_id}) polling enabled and restored")

        backend.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Опрос {"включен" if new_state else "отключен"} для бэкенда {backend.backend_name}',
            'backend': backend.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating backend polling for backend {backend_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/summary', methods=['GET'])
def get_haproxy_summary():
    """
    Получение сводной статистики по всем HAProxy инстансам.
    """
    try:
        # Получаем все активные инстансы
        instances = HAProxyInstance.query.filter_by(is_active=True).all()

        # Считаем статистику
        total_backends = HAProxyBackend.query.filter(
            HAProxyBackend.removed_at.is_(None)
        ).count()

        total_servers = HAProxyServer.query.filter(
            HAProxyServer.removed_at.is_(None)
        ).count()

        # Статистика по статусам серверов
        status_stats = {}
        for status in ['UP', 'DOWN', 'DRAIN', 'MAINT']:
            count = HAProxyServer.query.filter_by(status=status).filter(
                HAProxyServer.removed_at.is_(None)
            ).count()
            status_stats[status] = count

        # Статистика маппинга
        mapping_stats = HAProxyMapper.get_mapping_stats()

        result = {
            'success': True,
            'instances_count': len(instances),
            'backends_count': total_backends,
            'servers_count': total_servers,
            'status_stats': status_stats,
            'mapping_stats': mapping_stats,
            'instances': [inst.to_dict() for inst in instances]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting HAProxy summary: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/errors/summary', methods=['GET'])
def get_errors_summary():
    """
    Получение списка бэкендов с ошибками получения данных от агентов.
    """
    try:
        # Получаем все бэкенды со статусом ошибки
        backends_with_errors = HAProxyBackend.query.filter(
            HAProxyBackend.last_fetch_status == 'failed',
            HAProxyBackend.removed_at.is_(None)
        ).all()

        result = {
            'success': True,
            'count': len(backends_with_errors),
            'backends': [backend.to_dict() for backend in backends_with_errors]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting error summary: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/instances/<int:instance_id>/sync', methods=['POST'])
def sync_haproxy_instance(instance_id):
    """
    Принудительная синхронизация HAProxy инстанса.

    Args:
        instance_id: ID HAProxy инстанса
    """
    try:
        instance = HAProxyInstance.query.get(instance_id)

        if not instance:
            return jsonify({
                'success': False,
                'error': 'HAProxy instance not found'
            }), 404

        if not instance.is_active:
            return jsonify({
                'success': False,
                'error': 'HAProxy instance is not active'
            }), 400

        # Запускаем синхронизацию в асинхронном режиме
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            success = loop.run_until_complete(HAProxyService.sync_haproxy_instance(instance))
        finally:
            loop.close()

        if success:
            # Выполняем маппинг после синхронизации
            try:
                HAProxyMapper.remap_all_servers()
            except Exception as e:
                logger.warning(f"Error during mapping: {e}")

            return jsonify({
                'success': True,
                'message': f'Синхронизация инстанса {instance.name} завершена успешно',
                'instance': instance.to_dict()
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': instance.last_sync_error or 'Синхронизация не удалась',
                'instance': instance.to_dict()
            }), 500

    except Exception as e:
        logger.error(f"Error syncing HAProxy instance {instance_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/servers/<int:server_id>/history', methods=['GET'])
def get_server_history(server_id):
    """
    Получение истории изменений статуса HAProxy сервера.

    Args:
        server_id: ID HAProxy сервера

    Query parameters:
        limit: максимальное количество записей (по умолчанию 50)
    """
    try:
        from app.models.haproxy import HAProxyServerStatusHistory

        server = HAProxyServer.query.get(server_id)

        if not server:
            return jsonify({
                'success': False,
                'error': 'HAProxy server not found'
            }), 404

        limit = request.args.get('limit', 50, type=int)

        history = HAProxyServerStatusHistory.query.filter_by(
            haproxy_server_id=server_id
        ).order_by(HAProxyServerStatusHistory.changed_at.desc()).limit(limit).all()

        result = {
            'success': True,
            'server_id': server_id,
            'server_name': server.server_name,
            'count': len(history),
            'history': [h.to_dict() for h in history]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting history for server {server_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/mapping/remap', methods=['POST'])
def remap_servers():
    """
    Повторный маппинг всех HAProxy серверов на приложения.
    """
    try:
        mapped, total = HAProxyMapper.remap_all_servers()

        result = {
            'success': True,
            'message': f'Маппинг завершен: {mapped}/{total} серверов сопоставлено',
            'mapped': mapped,
            'total': total,
            'mapping_rate': round(mapped / total * 100, 2) if total > 0 else 0
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error remapping servers: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/cache/clear', methods=['POST'])
def clear_cache():
    """
    Очистка кэша HAProxy сервиса и mapper.
    """
    try:
        HAProxyService.clear_cache()
        HAProxyMapper.clear_cache()

        return jsonify({
            'success': True,
            'message': 'Кэш очищен'
        }), 200

    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== Manual Mapping Operations ====================

@bp.route('/haproxy/servers/<int:server_id>/map', methods=['POST'])
def map_server_to_application(server_id):
    """
    Установить ручной маппинг HAProxy сервера на приложение.

    Args:
        server_id: ID HAProxy сервера

    Body:
        application_id: int - ID приложения для связывания
        notes: str (optional) - Заметки о маппинге
    """
    try:
        from app.models.application_instance import ApplicationInstance as Application

        data = request.json
        if not data or 'application_id' not in data:
            return jsonify({
                'success': False,
                'error': 'Отсутствует application_id'
            }), 400

        # Получаем HAProxy сервер
        haproxy_server = HAProxyServer.query.get(server_id)
        if not haproxy_server:
            return jsonify({
                'success': False,
                'error': 'HAProxy сервер не найден'
            }), 404

        # Получаем приложение
        application_id = data['application_id']
        application = Application.query.get(application_id)
        if not application:
            return jsonify({
                'success': False,
                'error': f'Приложение с ID {application_id} не найдено'
            }), 404

        # Проверка: приложение должно быть на сервере с тем же IP, что и HAProxy server
        if haproxy_server.addr:
            server_ip = haproxy_server.addr.split(':')[0] if ':' in haproxy_server.addr else None
            if server_ip and application.ip != server_ip:
                return jsonify({
                    'success': False,
                    'error': f'IP приложения ({application.ip}) не совпадает с IP сервера в бэкэнде ({server_ip})'
                }), 400

        notes = data.get('notes', '')

        # Устанавливаем ручной маппинг
        haproxy_server.map_to_application(
            application_id=application_id,
            is_manual=True,
            mapped_by='admin',  # Статическое значение согласно требованиям
            notes=notes
        )

        db.session.commit()

        logger.info(f"Установлен ручной маппинг: {haproxy_server.server_name} -> {application.instance_name}")

        return jsonify({
            'success': True,
            'message': f'Сервер {haproxy_server.server_name} успешно связан с приложением {application.instance_name}',
            'server': haproxy_server.to_dict(include_application=True)
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error mapping server {server_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/servers/<int:server_id>/unmap', methods=['POST'])
def unmap_server_from_application(server_id):
    """
    Удалить маппинг HAProxy сервера (как ручной, так и автоматический).

    Args:
        server_id: ID HAProxy сервера

    Body:
        notes: str (optional) - Причина удаления маппинга
    """
    try:
        from app.models.application_mapping import ApplicationMapping, MappingType
        from app.services.mapping_service import mapping_service

        data = request.json or {}

        # Получаем HAProxy сервер
        haproxy_server = HAProxyServer.query.get(server_id)
        if not haproxy_server:
            return jsonify({
                'success': False,
                'error': 'HAProxy сервер не найден'
            }), 404

        # Проверяем наличие маппинга в унифицированной таблице
        mapping = ApplicationMapping.query.filter_by(
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=server_id,
            is_active=True
        ).first()

        if not mapping:
            return jsonify({
                'success': False,
                'error': 'Сервер не связан с приложением'
            }), 400

        notes = data.get('notes', 'Маппинг удален вручную')

        # Удаляем маппинг через MappingService
        count = mapping_service.unmap_entity(
            entity_type=MappingType.HAPROXY_SERVER.value,
            entity_id=server_id,
            unmapped_by='admin',
            reason=notes
        )

        logger.info(f"Удален маппинг для сервера {haproxy_server.server_name}")

        return jsonify({
            'success': True,
            'message': f'Маппинг для сервера {haproxy_server.server_name} удален',
            'server': haproxy_server.to_dict(include_application=True)
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error unmapping server {server_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/servers/unmapped', methods=['GET'])
def get_unmapped_servers():
    """
    Получить список HAProxy серверов без маппинга.

    Query parameters:
        backend_id: int (optional) - Фильтр по backend
        instance_id: int (optional) - Фильтр по HAProxy instance
    """
    try:
        from app.models.application_mapping import ApplicationMapping, MappingType

        backend_id = request.args.get('backend_id', type=int)
        instance_id = request.args.get('instance_id', type=int)

        # Подзапрос для получения ID HAProxy серверов с активными маппингами
        mapped_server_ids = db.session.query(ApplicationMapping.entity_id).filter(
            ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
            ApplicationMapping.is_active == True
        ).subquery()

        # Базовый запрос: серверы без маппинга в новой таблице
        query = HAProxyServer.query.filter(
            ~HAProxyServer.id.in_(mapped_server_ids),
            HAProxyServer.removed_at.is_(None)
        )

        # Фильтрация по backend
        if backend_id:
            query = query.filter(HAProxyServer.backend_id == backend_id)

        # Фильтрация по instance
        if instance_id:
            query = query.join(HAProxyBackend).filter(
                HAProxyBackend.haproxy_instance_id == instance_id
            )

        unmapped_servers = query.all()

        result = {
            'success': True,
            'count': len(unmapped_servers),
            'servers': [server.to_dict(include_backend=True) for server in unmapped_servers]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting unmapped servers: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/servers/<int:server_id>/mapping-history', methods=['GET'])
def get_server_mapping_history(server_id):
    """
    Получение истории изменений маппинга HAProxy сервера.

    Args:
        server_id: ID HAProxy сервера

    Query parameters:
        limit: максимальное количество записей (по умолчанию 50)
    """
    try:
        from app.models.haproxy import HAProxyMappingHistory

        server = HAProxyServer.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': 'HAProxy сервер не найден'
            }), 404

        limit = request.args.get('limit', 50, type=int)

        history = HAProxyMappingHistory.query.filter_by(
            haproxy_server_id=server_id
        ).order_by(HAProxyMappingHistory.changed_at.desc()).limit(limit).all()

        result = {
            'success': True,
            'server_id': server_id,
            'server_name': server.server_name,
            'count': len(history),
            'history': [h.to_dict() for h in history]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting mapping history for server {server_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/applications/search', methods=['GET'])
def search_applications_for_mapping():
    """
    Поиск приложений для маппинга HAProxy сервера.

    Query parameters:
        server_id: int (required) - ID HAProxy сервера (для фильтрации по IP)
        query: str (optional) - Поисковый запрос по имени приложения
    """
    try:
        from app.models.application_instance import ApplicationInstance as Application
        from app.models.application_mapping import ApplicationMapping, MappingType

        server_id = request.args.get('server_id', type=int)
        if not server_id:
            return jsonify({
                'success': False,
                'error': 'Параметр server_id обязателен'
            }), 400

        # Получаем HAProxy сервер
        haproxy_server = HAProxyServer.query.get(server_id)
        if not haproxy_server:
            return jsonify({
                'success': False,
                'error': 'HAProxy сервер не найден'
            }), 404

        # Извлекаем IP из адреса HAProxy сервера
        server_ip = None
        if haproxy_server.addr and ':' in haproxy_server.addr:
            server_ip = haproxy_server.addr.split(':')[0]

        if not server_ip:
            return jsonify({
                'success': False,
                'error': 'Не удалось определить IP адрес HAProxy сервера'
            }), 400

        # Подзапрос для получения ID приложений с активными HAProxy маппингами
        mapped_app_ids = db.session.query(ApplicationMapping.application_id).filter(
            ApplicationMapping.entity_type == MappingType.HAPROXY_SERVER.value,
            ApplicationMapping.is_active == True
        ).subquery()

        # Ищем приложения с таким же IP, исключая уже замапленные
        query_obj = Application.query.filter(
            Application.ip == server_ip,
            ~Application.id.in_(mapped_app_ids)  # Исключаем уже замапленные приложения
        )

        # Дополнительный поиск по имени, если указан
        search_query = request.args.get('query', '').strip()
        if search_query:
            query_obj = query_obj.filter(
                Application.instance_name.ilike(f'%{search_query}%')
            )

        applications = query_obj.all()

        result = {
            'success': True,
            'server_id': server_id,
            'server_name': haproxy_server.server_name,
            'server_ip': server_ip,
            'count': len(applications),
            'applications': [{
                'id': app.id,
                'name': app.instance_name,
                'ip': app.ip,
                'port': app.port,
                'status': app.status,
                'server_name': app.server.name if app.server else None,
                'server_id': app.server_id
            } for app in applications]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error searching applications: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== CRUD Operations for HAProxy Instances ====================

@bp.route('/haproxy/instances', methods=['POST'])
def create_haproxy_instance():
    """
    Создание нового HAProxy инстанса.

    Body:
        name: str - Имя инстанса (default, prod, etc.)
        server_id: int - ID сервера
        socket_path: str (optional) - Путь к socket
        is_active: bool (optional) - Активен ли (default: True)
    """
    try:
        data = request.json

        if not data:
            return jsonify({
                'success': False,
                'error': 'Отсутствуют данные'
            }), 400

        # Валидация обязательных полей
        required_fields = {'name': 'Имя инстанса', 'server_id': 'ID сервера'}
        for field, description in required_fields.items():
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{description} обязательно'
                }), 400

        # Проверка существования сервера
        server = Server.query.get(data['server_id'])
        if not server:
            return jsonify({
                'success': False,
                'error': f'Сервер с id {data["server_id"]} не найден'
            }), 404

        # Проверка что сервер помечен как HAProxy узел
        if not server.is_haproxy_node:
            return jsonify({
                'success': False,
                'error': 'Сервер не помечен как HAProxy узел. Сначала установите флаг is_haproxy_node.'
            }), 400

        # Проверка уникальности (server_id, name)
        existing = HAProxyInstance.query.filter_by(
            server_id=data['server_id'],
            name=data['name']
        ).first()

        if existing:
            return jsonify({
                'success': False,
                'error': f'HAProxy инстанс "{data["name"]}" уже существует на сервере {server.name}'
            }), 409

        # Создание нового инстанса
        instance = HAProxyInstance(
            name=data['name'],
            server_id=data['server_id'],
            socket_path=data.get('socket_path'),
            is_active=data.get('is_active', True)
        )

        db.session.add(instance)
        db.session.commit()

        logger.info(f"Created HAProxy instance: {instance.name} on server {server.name}")

        return jsonify({
            'success': True,
            'message': f'HAProxy инстанс "{instance.name}" создан успешно',
            'instance': instance.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating HAProxy instance: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/instances/<int:instance_id>', methods=['PUT'])
def update_haproxy_instance(instance_id):
    """
    Обновление HAProxy инстанса.

    Args:
        instance_id: ID инстанса

    Body:
        name: str (optional) - Имя инстанса
        socket_path: str (optional) - Путь к socket
        is_active: bool (optional) - Активен ли
    """
    try:
        data = request.json

        if not data:
            return jsonify({
                'success': False,
                'error': 'Отсутствуют данные'
            }), 400

        instance = HAProxyInstance.query.get(instance_id)
        if not instance:
            return jsonify({
                'success': False,
                'error': 'HAProxy инстанс не найден'
            }), 404

        # Обновление полей
        if 'name' in data:
            # Проверка уникальности нового имени
            existing = HAProxyInstance.query.filter(
                HAProxyInstance.server_id == instance.server_id,
                HAProxyInstance.name == data['name'],
                HAProxyInstance.id != instance_id
            ).first()

            if existing:
                return jsonify({
                    'success': False,
                    'error': f'HAProxy инстанс с именем "{data["name"]}" уже существует на этом сервере'
                }), 409

            instance.name = data['name']

        if 'socket_path' in data:
            instance.socket_path = data['socket_path']

        if 'is_active' in data:
            instance.is_active = data['is_active']

        instance.updated_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Updated HAProxy instance: {instance.name} (id={instance_id})")

        return jsonify({
            'success': True,
            'message': 'HAProxy инстанс обновлен успешно',
            'instance': instance.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating HAProxy instance {instance_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/instances/<int:instance_id>', methods=['DELETE'])
def delete_haproxy_instance(instance_id):
    """
    Удаление HAProxy инстанса.

    Args:
        instance_id: ID инстанса

    Note:
        Удаляет инстанс вместе со всеми связанными backends и серверами (CASCADE).
    """
    try:
        instance = HAProxyInstance.query.get(instance_id)
        if not instance:
            return jsonify({
                'success': False,
                'error': 'HAProxy инстанс не найден'
            }), 404

        instance_name = instance.name
        server_name = instance.server.name if instance.server else "Unknown"

        # Подсчет связанных данных
        backends_count = instance.backends.count()
        servers_count = sum(backend.servers.count() for backend in instance.backends)

        db.session.delete(instance)
        db.session.commit()

        logger.info(f"Deleted HAProxy instance: {instance_name} from server {server_name} "
                   f"(deleted {backends_count} backends, {servers_count} servers)")

        return jsonify({
            'success': True,
            'message': f'HAProxy инстанс "{instance_name}" удален успешно',
            'deleted': {
                'instance': instance_name,
                'backends': backends_count,
                'servers': servers_count
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting HAProxy instance {instance_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/haproxy/mappings/all', methods=['GET'])
def get_all_mappings():
    """
    Получение всех маппингов HAProxy серверов на приложения.

    Возвращает структуру:
    {
        "hostname1": [
            {
                "app_name": "app1",
                "server_addr": "10.0.0.1:8080",
                "app_addr": "10.0.0.1:8080",
                "backend_name": "backend1",
                "server_name": "server1"
            }
        ],
        "hostname2": [...]
    }
    """
    try:
        from app.models.application_instance import ApplicationInstance as Application
        from app.models.application_mapping import ApplicationMapping, MappingType
        from collections import defaultdict

        # Получаем все активные маппинги из унифицированной таблицы
        mappings = ApplicationMapping.query.filter_by(
            entity_type=MappingType.HAPROXY_SERVER.value,
            is_active=True
        ).all()

        # Группируем по hostname
        mappings_by_host = defaultdict(list)

        for mapping in mappings:
            # Получаем HAProxy сервер
            haproxy_server = HAProxyServer.query.get(mapping.entity_id)
            if not haproxy_server or haproxy_server.removed_at:
                continue

            app = mapping.application
            if not app:
                continue

            backend = haproxy_server.backend
            hostname = app.server.name if app.server else "Unknown"

            mapping_info = {
                'app_name': app.instance_name,
                'server_addr': haproxy_server.addr or '',
                'app_addr': f"{app.ip}:{app.port}" if app.ip and app.port else '',
                'backend_name': backend.backend_name if backend else '',
                'server_name': haproxy_server.server_name or ''
            }

            mappings_by_host[hostname].append(mapping_info)

        # Сортируем результаты для консистентности
        result = dict(sorted(mappings_by_host.items()))

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting all mappings: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

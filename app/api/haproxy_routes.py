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
    """
    try:
        instance = HAProxyInstance.query.get(instance_id)

        if not instance:
            return jsonify({
                'success': False,
                'error': 'HAProxy instance not found'
            }), 404

        # Получаем только не удаленные backends
        backends = HAProxyBackend.query.filter_by(
            haproxy_instance_id=instance_id
        ).filter(HAProxyBackend.removed_at.is_(None)).all()

        result = {
            'success': True,
            'instance_id': instance_id,
            'instance_name': instance.name,
            'count': len(backends),
            'backends': [backend.to_dict(include_servers=True) for backend in backends]
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

# app/api/mappings_routes.py
"""
API endpoints для управления маппингами приложений.
"""

from flask import jsonify, request
import logging

from app.api import bp
from app.services.mapping_service import mapping_service, MappingType
from app.models.application_mapping import ApplicationMapping, ApplicationMappingHistory

logger = logging.getLogger(__name__)


@bp.route('/mappings', methods=['GET'])
def get_mappings():
    """
    Получить список маппингов с фильтрацией.

    Query parameters:
        application_id: фильтр по ID приложения
        entity_type: фильтр по типу сущности (haproxy_server, eureka_instance)
        entity_id: фильтр по ID сущности
        active_only: если true, только активные маппинги (default: true)
    """
    try:
        application_id = request.args.get('application_id', type=int)
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id', type=int)
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        if application_id:
            mappings = mapping_service.get_mappings_for_application(
                application_id, entity_type, active_only
            )
        elif entity_type and entity_id:
            mappings = mapping_service.get_mappings_for_entity(
                entity_type, entity_id, active_only
            )
        else:
            query = ApplicationMapping.query
            if active_only:
                query = query.filter_by(is_active=True)
            if entity_type:
                query = query.filter_by(entity_type=entity_type)
            mappings = query.all()

        return jsonify({
            'success': True,
            'count': len(mappings),
            'mappings': [m.to_dict() for m in mappings]
        }), 200

    except Exception as e:
        logger.error(f"Error getting mappings: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/<int:mapping_id>', methods=['GET'])
def get_mapping(mapping_id):
    """Получить маппинг по ID"""
    try:
        mapping = mapping_service.get_mapping_by_id(mapping_id)

        if not mapping:
            return jsonify({
                'success': False,
                'error': 'Mapping not found'
            }), 404

        return jsonify({
            'success': True,
            'mapping': mapping.to_dict(include_entity=True)
        }), 200

    except Exception as e:
        logger.error(f"Error getting mapping {mapping_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings', methods=['POST'])
def create_mapping():
    """
    Создать новый маппинг.

    JSON body:
        application_id: ID приложения (required)
        entity_type: тип сущности (required)
        entity_id: ID сущности (required)
        is_manual: ручной маппинг (default: false)
        mapped_by: кто создал маппинг
        notes: заметки
        metadata: дополнительные данные (JSON)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400

        required_fields = ['application_id', 'entity_type', 'entity_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        mapping = mapping_service.create_mapping(
            application_id=data['application_id'],
            entity_type=data['entity_type'],
            entity_id=data['entity_id'],
            is_manual=data.get('is_manual', False),
            mapped_by=data.get('mapped_by'),
            notes=data.get('notes'),
            metadata=data.get('metadata')
        )

        if mapping:
            return jsonify({
                'success': True,
                'mapping': mapping.to_dict()
            }), 201

        return jsonify({
            'success': False,
            'error': 'Failed to create mapping'
        }), 400

    except Exception as e:
        logger.error(f"Error creating mapping: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/<int:mapping_id>', methods=['PUT'])
def update_mapping(mapping_id):
    """
    Обновить маппинг.

    JSON body:
        is_manual: ручной маппинг
        mapped_by: кто изменил маппинг
        notes: заметки
        metadata: дополнительные данные
        is_active: активность маппинга
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400

        mapping = mapping_service.update_mapping(
            mapping_id=mapping_id,
            is_manual=data.get('is_manual'),
            mapped_by=data.get('mapped_by'),
            notes=data.get('notes'),
            metadata=data.get('metadata'),
            is_active=data.get('is_active')
        )

        if mapping:
            return jsonify({
                'success': True,
                'mapping': mapping.to_dict()
            }), 200

        return jsonify({
            'success': False,
            'error': 'Mapping not found'
        }), 404

    except Exception as e:
        logger.error(f"Error updating mapping {mapping_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/<int:mapping_id>', methods=['DELETE'])
def delete_mapping(mapping_id):
    """Удалить маппинг"""
    try:
        deleted_by = request.args.get('deleted_by')
        reason = request.args.get('reason')

        if mapping_service.delete_mapping(mapping_id, deleted_by, reason):
            return jsonify({
                'success': True,
                'message': 'Mapping deleted'
            }), 200

        return jsonify({
            'success': False,
            'error': 'Mapping not found'
        }), 404

    except Exception as e:
        logger.error(f"Error deleting mapping {mapping_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/<int:mapping_id>/history', methods=['GET'])
def get_mapping_history(mapping_id):
    """Получить историю изменений маппинга"""
    try:
        history = mapping_service.get_mapping_history(mapping_id=mapping_id)

        return jsonify({
            'success': True,
            'count': len(history),
            'history': [h.to_dict() for h in history]
        }), 200

    except Exception as e:
        logger.error(f"Error getting mapping history for {mapping_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/stats', methods=['GET'])
def get_mapping_stats():
    """Получить статистику маппингов"""
    try:
        stats = mapping_service.get_mapping_statistics()

        return jsonify({
            'success': True,
            'stats': stats
        }), 200

    except Exception as e:
        logger.error(f"Error getting mapping statistics: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/auto-map', methods=['POST'])
def auto_map():
    """
    Запустить автоматический маппинг.

    Query parameters:
        entity_type: тип сущности для маппинга (haproxy_server или eureka_instance)
    """
    try:
        entity_type = request.args.get('entity_type')

        if entity_type == MappingType.HAPROXY_SERVER.value:
            from app.services.haproxy_mapper import HAProxyMapper
            mapper = HAProxyMapper()
            result = mapper.remap_all_servers()
        elif entity_type == MappingType.EUREKA_INSTANCE.value:
            from app.services.eureka_mapper import EurekaMapper
            mapper = EurekaMapper()
            result = mapper.map_instances_to_applications()
        else:
            return jsonify({
                'success': False,
                'error': f'Invalid entity_type: {entity_type}. Must be haproxy_server or eureka_instance'
            }), 400

        return jsonify({
            'success': True,
            'result': result
        }), 200

    except Exception as e:
        logger.error(f"Error during auto-mapping for {entity_type}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/entity/<entity_type>/<int:entity_id>', methods=['DELETE'])
def unmap_entity(entity_type, entity_id):
    """
    Отвязать все маппинги для сущности.

    Query parameters:
        unmapped_by: кто выполнил отвязку
        reason: причина отвязки
    """
    try:
        unmapped_by = request.args.get('unmapped_by')
        reason = request.args.get('reason')

        count = mapping_service.unmap_entity(entity_type, entity_id, unmapped_by, reason)

        return jsonify({
            'success': True,
            'unmapped_count': count
        }), 200

    except Exception as e:
        logger.error(f"Error unmapping entity {entity_type}:{entity_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/application/<int:application_id>/history', methods=['GET'])
def get_application_mapping_history(application_id):
    """Получить историю маппингов для приложения"""
    try:
        limit = request.args.get('limit', 100, type=int)
        history = mapping_service.get_mapping_history(application_id=application_id, limit=limit)

        return jsonify({
            'success': True,
            'count': len(history),
            'history': [h.to_dict() for h in history]
        }), 200

    except Exception as e:
        logger.error(f"Error getting mapping history for application {application_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/mappings/cleanup-orphaned', methods=['POST'])
def cleanup_orphaned_mappings():
    """
    Очистка orphaned маппингов - маппингов, ссылающихся на несуществующие сущности.

    Это необходимо, так как ApplicationMapping использует полиморфную связь (entity_id)
    без FK constraint, и при удалении HAProxy/Eureka сущностей маппинги могут остаться.

    Returns:
        {
            "success": true,
            "cleaned": {
                "haproxy_server": 5,
                "eureka_instance": 2
            },
            "total": 7
        }
    """
    from app import db
    from app.models.haproxy import HAProxyServer
    from app.models.eureka import EurekaInstance

    try:
        cleaned = {
            'haproxy_server': 0,
            'eureka_instance': 0
        }

        # Получаем все активные маппинги
        all_mappings = ApplicationMapping.query.filter_by(is_active=True).all()

        orphaned_ids = []

        for mapping in all_mappings:
            is_orphaned = False

            if mapping.entity_type == 'haproxy_server':
                entity = HAProxyServer.query.get(mapping.entity_id)
                if not entity or entity.removed_at is not None:
                    is_orphaned = True
                    cleaned['haproxy_server'] += 1

            elif mapping.entity_type == 'eureka_instance':
                entity = EurekaInstance.query.get(mapping.entity_id)
                if not entity or entity.removed_at is not None:
                    is_orphaned = True
                    cleaned['eureka_instance'] += 1

            if is_orphaned:
                orphaned_ids.append(mapping.id)

        # Удаляем orphaned маппинги
        if orphaned_ids:
            ApplicationMapping.query.filter(
                ApplicationMapping.id.in_(orphaned_ids)
            ).delete(synchronize_session=False)
            db.session.commit()

        total = cleaned['haproxy_server'] + cleaned['eureka_instance']

        logger.info(f"Cleaned up {total} orphaned mappings: {cleaned}")

        return jsonify({
            'success': True,
            'cleaned': cleaned,
            'total': total
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cleaning up orphaned mappings: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

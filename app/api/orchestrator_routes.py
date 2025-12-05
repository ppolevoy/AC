# app/api/orchestrator_routes.py
"""
API endpoints для управления orchestrator playbooks
"""

from flask import jsonify, request
from sqlalchemy import func
import logging

from app import db
from app.api import bp
from app.services.orchestrator_scanner import (
    scan_orchestrators,
    get_all_orchestrators,
    get_orchestrator_by_id,
    toggle_orchestrator_status
)
from app.models.application_instance import ApplicationInstance
from app.models.application_mapping import ApplicationMapping
from app.models.haproxy import HAProxyServer, HAProxyBackend
from app.models.server import Server

logger = logging.getLogger(__name__)


@bp.route('/orchestrators', methods=['GET'])
def get_orchestrators():
    """
    Получение списка всех orchestrator playbooks.

    Query parameters:
        active_only: если true, возвращает только активные playbooks
    """
    try:
        active_only = request.args.get('active_only', 'false').lower() == 'true'

        orchestrators = get_all_orchestrators(active_only=active_only)

        result = {
            'success': True,
            'count': len(orchestrators),
            'orchestrators': [orch.to_dict() for orch in orchestrators]
        }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting orchestrators: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/orchestrators/<int:orchestrator_id>', methods=['GET'])
def get_orchestrator(orchestrator_id):
    """
    Получение деталей конкретного orchestrator playbook.

    Args:
        orchestrator_id: ID записи
    """
    try:
        orchestrator = get_orchestrator_by_id(orchestrator_id)

        if not orchestrator:
            return jsonify({
                'success': False,
                'error': 'Orchestrator playbook not found'
            }), 404

        return jsonify({
            'success': True,
            'orchestrator': orchestrator.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Error getting orchestrator {orchestrator_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/orchestrators/scan', methods=['POST'])
def scan_orchestrators_endpoint():
    """
    Принудительное пересканирование каталога orchestrator playbooks.

    Находит все файлы *orchestrator*.yml в настроенном каталоге,
    парсит метаданные и создает/обновляет записи в БД.

    Returns:
        {
            'success': True/False,
            'scanned': количество найденных файлов,
            'new': количество новых записей,
            'updated': количество обновленных записей,
            'errors': список ошибок
        }
    """
    try:
        logger.info("Manual orchestrator scan triggered")

        # Запуск сканирования (всегда принудительно)
        results = scan_orchestrators(force=True)

        # Проверка на ошибки
        has_errors = len(results['errors']) > 0

        return jsonify({
            'success': not has_errors or (results['new'] > 0 or results['updated'] > 0),
            'scanned': results['scanned'],
            'new': results['new'],
            'updated': results['updated'],
            'errors': results['errors']
        }), 200 if not has_errors else 207  # 207 Multi-Status если есть частичные ошибки

    except Exception as e:
        logger.error(f"Error during orchestrator scan: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/orchestrators/<int:orchestrator_id>/toggle', methods=['PATCH'])
def toggle_orchestrator(orchestrator_id):
    """
    Переключение статуса активности orchestrator playbook.

    Args:
        orchestrator_id: ID записи

    Returns:
        Обновленный orchestrator playbook
    """
    try:
        orchestrator = toggle_orchestrator_status(orchestrator_id)

        if not orchestrator:
            return jsonify({
                'success': False,
                'error': 'Orchestrator playbook not found'
            }), 404

        return jsonify({
            'success': True,
            'orchestrator': orchestrator.to_dict(),
            'message': f"Orchestrator {'activated' if orchestrator.is_active else 'deactivated'}"
        }), 200

    except Exception as e:
        logger.error(f"Error toggling orchestrator {orchestrator_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/orchestrators/validate-haproxy-mapping', methods=['POST'])
def validate_haproxy_mapping():
    """
    Проверяет HAProxy маппинг для списка приложений.
    Используется перед запуском оркестратора для валидации конфигурации.

    Request body:
    {
        "application_ids": [1, 2, 3]
    }

    Response:
    {
        "total": 3,
        "mapped": 2,
        "unmapped": 1,
        "backends": ["backend1", "backend2"],
        "details": [...]
    }
    """
    try:
        data = request.get_json()
        app_ids = data.get('application_ids', [])

        if not app_ids:
            return jsonify({'error': 'No application IDs provided'}), 400

        result = {
            'total': len(app_ids),
            'mapped': 0,
            'unmapped': 0,
            'backends': set(),
            'details': []
        }

        for app_id in app_ids:
            app = ApplicationInstance.query.get(app_id)
            if not app:
                result['details'].append({
                    'app_id': app_id,
                    'error': 'Application not found'
                })
                continue

            server = Server.query.get(app.server_id)
            short_name = server.name.split('.')[0] if server and '.' in server.name else (server.name if server else 'unknown')

            # Проверяем маппинг
            mapping = ApplicationMapping.query.filter_by(
                application_id=app_id,
                entity_type='haproxy_server',
                is_active=True
            ).first()

            detail = {
                'app_id': app_id,
                'app_name': app.instance_name,
                'server': short_name,
                'mapped': False,
                'haproxy_server': None,
                'backend': None,
                'instance_string': None
            }

            if mapping and mapping.entity_id:
                haproxy_server = HAProxyServer.query.get(mapping.entity_id)
                if haproxy_server:
                    detail['mapped'] = True
                    detail['haproxy_server'] = haproxy_server.name

                    if haproxy_server.backend_id:
                        backend = HAProxyBackend.query.get(haproxy_server.backend_id)
                        if backend:
                            detail['backend'] = backend.name
                            result['backends'].add(backend.name)

                    detail['instance_string'] = f"{short_name}::{app.instance_name}::{haproxy_server.name}"
                    result['mapped'] += 1
                else:
                    detail['error'] = f"HAProxy server {mapping.entity_id} not found"
                    detail['instance_string'] = f"{short_name}::{app.instance_name}::{short_name}_{app.instance_name}"
                    result['unmapped'] += 1
            else:
                detail['instance_string'] = f"{short_name}::{app.instance_name}::{short_name}_{app.instance_name}"
                result['unmapped'] += 1

            result['details'].append(detail)

        # Преобразуем set в list для JSON
        result['backends'] = list(result['backends'])

        # Добавляем предупреждения
        if result['unmapped'] > 0:
            result['warning'] = f"{result['unmapped']} applications will use fallback naming"

        if len(result['backends']) > 1:
            result['warning'] = f"Multiple backends detected: {', '.join(result['backends'])}"

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error validating HAProxy mapping: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@bp.route('/orchestrators/validate-mappings', methods=['POST'])
def validate_mappings():
    """
    Проверяет наличие маппингов (HAProxy или Eureka) для списка приложений.
    Используется для определения значения оркестратора по умолчанию.

    Условие для оркестрации: ВСЕ приложения должны иметь маппинг одного типа.

    Request body:
    {
        "application_ids": [1, 2, 3]
    }

    Response:
    {
        "total": 3,
        "haproxy_mapped": 3,
        "eureka_mapped": 0,
        "all_haproxy": true,
        "all_eureka": false,
        "can_orchestrate": true
    }
    """
    try:
        data = request.get_json()
        app_ids = data.get('application_ids', [])

        if not app_ids:
            return jsonify({
                'total': 0,
                'haproxy_mapped': 0,
                'eureka_mapped': 0,
                'all_haproxy': False,
                'all_eureka': False,
                'can_orchestrate': False
            })

        total = len(app_ids)

        # Один запрос с GROUP BY - подсчёт уникальных app_id по типам
        counts = db.session.query(
            ApplicationMapping.entity_type,
            func.count(func.distinct(ApplicationMapping.application_id))
        ).filter(
            ApplicationMapping.application_id.in_(app_ids),
            ApplicationMapping.is_active == True
        ).group_by(ApplicationMapping.entity_type).all()

        # Преобразуем в словарь
        counts_dict = {entity_type: count for entity_type, count in counts}
        haproxy_count = counts_dict.get('haproxy_server', 0)
        eureka_count = counts_dict.get('eureka_instance', 0)

        # Условие: ВСЕ приложения имеют маппинг одного типа
        all_haproxy = (haproxy_count == total)
        all_eureka = (eureka_count == total)
        can_orchestrate = all_haproxy or all_eureka

        logger.debug(f"Mapping check for {total} apps: haproxy={haproxy_count}, eureka={eureka_count}, can_orchestrate={can_orchestrate}")

        return jsonify({
            'total': total,
            'haproxy_mapped': haproxy_count,
            'eureka_mapped': eureka_count,
            'all_haproxy': all_haproxy,
            'all_eureka': all_eureka,
            'can_orchestrate': can_orchestrate
        })

    except Exception as e:
        logger.error(f"Error validating mappings: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

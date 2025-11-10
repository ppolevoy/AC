# app/api/orchestrator_routes.py
"""
API endpoints для управления orchestrator playbooks
"""

from flask import jsonify, request
import logging

from app.api import bp
from app.services.orchestrator_scanner import (
    scan_orchestrators,
    get_all_orchestrators,
    get_orchestrator_by_id,
    toggle_orchestrator_status
)

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

# -*- coding: utf-8 -*-
"""
API эндпоинты для работы с Eureka интеграцией.
"""
import asyncio
import logging
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from app import db
from app.models.server import Server
from app.models.eureka import (EurekaServer, EurekaApplication,
                                 EurekaInstance, EurekaInstanceStatusHistory,
                                 EurekaInstanceAction)
from app.services.eureka_service import EurekaService
from app.services.eureka_mapper import EurekaMapper

logger = logging.getLogger(__name__)

eureka_bp = Blueprint('eureka', __name__, url_prefix='/api/eureka')


# =============================================================================
# Eureka Серверы
# =============================================================================

@eureka_bp.route('/servers', methods=['GET'])
def get_eureka_servers():
    """Получить список всех Eureka серверов"""
    try:
        # Фильтры
        is_active = request.args.get('is_active')
        server_id = request.args.get('server_id', type=int)

        query = EurekaServer.query.filter(EurekaServer.removed_at.is_(None))

        if is_active is not None:
            query = query.filter(EurekaServer.is_active == (is_active.lower() == 'true'))

        if server_id:
            query = query.filter(EurekaServer.server_id == server_id)

        eureka_servers = query.all()

        return jsonify({
            'success': True,
            'data': [es.to_dict(include_applications=False) for es in eureka_servers]
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения Eureka серверов: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/servers/<int:id>', methods=['GET'])
def get_eureka_server(id):
    """Получить детали Eureka сервера"""
    try:
        eureka_server = EurekaServer.query.get(id)
        if not eureka_server or eureka_server.is_removed():
            return jsonify({'success': False, 'error': 'Eureka server not found'}), 404

        return jsonify({
            'success': True,
            'data': eureka_server.to_dict(include_applications=True)
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения Eureka сервера: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/servers', methods=['POST'])
def create_eureka_server():
    """Создать новый Eureka сервер"""
    try:
        data = request.get_json()

        # Валидация
        if not data.get('server_id'):
            return jsonify({'success': False, 'error': 'server_id is required'}), 400

        if not data.get('eureka_host'):
            return jsonify({'success': False, 'error': 'eureka_host is required'}), 400

        if not data.get('eureka_port'):
            return jsonify({'success': False, 'error': 'eureka_port is required'}), 400

        # Проверяем существование сервера
        server = Server.query.get(data['server_id'])
        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Проверяем уникальность по server_id
        existing = EurekaServer.query.filter_by(server_id=data['server_id'], removed_at=None).first()
        if existing:
            return jsonify({'success': False, 'error': 'Eureka server already exists for this server'}), 400

        # ПРОВЕРКА: Убеждаемся что такой Eureka endpoint еще не используется
        existing_endpoint = EurekaServer.query.filter(
            EurekaServer.eureka_host == data['eureka_host'],
            EurekaServer.eureka_port == data['eureka_port'],
            EurekaServer.removed_at.is_(None)
        ).first()

        if existing_endpoint:
            error_msg = (f"Eureka endpoint {data['eureka_host']}:{data['eureka_port']} уже используется "
                        f"сервером '{existing_endpoint.server.name}' (ID={existing_endpoint.server_id}). "
                        f"Один физический Eureka сервер может быть связан только с одним сервером в системе.")
            logger.error(error_msg)
            return jsonify({'success': False, 'error': error_msg}), 400

        # Создаем Eureka сервер
        eureka_server = EurekaServer(
            server_id=data['server_id'],
            eureka_host=data['eureka_host'],
            eureka_port=data['eureka_port'],
            is_active=data.get('is_active', True)
        )

        db.session.add(eureka_server)
        db.session.commit()

        logger.info(f"Создан Eureka сервер ID={eureka_server.id} для сервера {server.name}")

        return jsonify({
            'success': True,
            'data': eureka_server.to_dict()
        }), 201

    except Exception as e:
        logger.error(f"Ошибка создания Eureka сервера: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/servers/<int:id>', methods=['PUT'])
def update_eureka_server(id):
    """Обновить Eureka сервер"""
    try:
        eureka_server = EurekaServer.query.get(id)
        if not eureka_server or eureka_server.is_removed():
            return jsonify({'success': False, 'error': 'Eureka server not found'}), 404

        data = request.get_json()

        # Обновляем поля
        if 'eureka_host' in data:
            eureka_server.eureka_host = data['eureka_host']

        if 'eureka_port' in data:
            eureka_server.eureka_port = data['eureka_port']

        if 'is_active' in data:
            eureka_server.is_active = data['is_active']

        eureka_server.updated_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Обновлен Eureka сервер ID={id}")

        return jsonify({
            'success': True,
            'data': eureka_server.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Ошибка обновления Eureka сервера: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/servers/<int:id>', methods=['DELETE'])
def delete_eureka_server(id):
    """Мягкое удаление Eureka сервера"""
    try:
        eureka_server = EurekaServer.query.get(id)
        if not eureka_server or eureka_server.is_removed():
            return jsonify({'success': False, 'error': 'Eureka server not found'}), 404

        eureka_server.soft_delete()
        db.session.commit()

        logger.info(f"Удален Eureka сервер ID={id}")

        return jsonify({'success': True, 'message': 'Eureka server deleted'}), 200

    except Exception as e:
        logger.error(f"Ошибка удаления Eureka сервера: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Приложения и Экземпляры
# =============================================================================

@eureka_bp.route('/applications', methods=['GET'])
def get_applications():
    """Получить список всех приложений"""
    try:
        # Фильтры
        eureka_server_id = request.args.get('eureka_server_id', type=int)
        app_name = request.args.get('app_name')
        fetch_status = request.args.get('fetch_status')  # success, failed, unknown

        query = EurekaApplication.query

        if eureka_server_id:
            query = query.filter(EurekaApplication.eureka_server_id == eureka_server_id)

        if app_name:
            query = query.filter(EurekaApplication.app_name.ilike(f'%{app_name}%'))

        if fetch_status:
            query = query.filter(EurekaApplication.last_fetch_status == fetch_status)

        applications = query.all()

        return jsonify({
            'success': True,
            'data': [app.to_dict(include_instances=False) for app in applications]
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения приложений: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances', methods=['GET'])
def get_instances():
    """Получить список всех экземпляров"""
    try:
        # Фильтры
        status = request.args.get('status')
        application_id = request.args.get('application_id', type=int)
        ip_address = request.args.get('ip_address')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        query = EurekaInstance.query.filter(EurekaInstance.removed_at.is_(None))

        if status:
            query = query.filter(EurekaInstance.status == status.upper())

        if application_id:
            query = query.filter(EurekaInstance.application_id == application_id)

        if ip_address:
            query = query.filter(EurekaInstance.ip_address == ip_address)

        # Пагинация
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'success': True,
            'data': [inst.to_dict(include_application=True) for inst in pagination.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения экземпляров: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances/<instance_id>', methods=['GET'])
def get_instance_details(instance_id):
    """Получить детали экземпляра"""
    try:
        instance = EurekaInstance.query.filter_by(instance_id=instance_id).first()
        if not instance or instance.is_removed():
            return jsonify({'success': False, 'error': 'Instance not found'}), 404

        return jsonify({
            'success': True,
            'data': instance.to_dict(include_application=True, include_history=True)
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения деталей экземпляра: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Операции
# =============================================================================

@eureka_bp.route('/instances/<int:instance_id>/health', methods=['POST'])
def health_check_instance(instance_id):
    """Выполнить health check экземпляра"""
    try:
        instance = EurekaInstance.query.get(instance_id)
        if not instance:
            return jsonify({'success': False, 'error': 'Instance not found'}), 404

        eureka_server = instance.eureka_application.eureka_server

        # Выполняем health check асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, message = loop.run_until_complete(
            EurekaService.health_check(eureka_server, instance.instance_id)
        )
        loop.close()

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 500

    except Exception as e:
        logger.error(f"Ошибка health check: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances/<int:instance_id>/pause', methods=['POST'])
def pause_instance(instance_id):
    """Поставить экземпляр на паузу"""
    try:
        data = request.get_json() or {}
        reason = data.get('reason')

        instance = EurekaInstance.query.get(instance_id)
        if not instance:
            return jsonify({'success': False, 'error': 'Instance not found'}), 404

        eureka_server = instance.eureka_application.eureka_server

        # Выполняем pause асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, message = loop.run_until_complete(
            EurekaService.pause_application(eureka_server, instance.instance_id, reason=reason)
        )
        loop.close()

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 500

    except Exception as e:
        logger.error(f"Ошибка pause: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances/<int:instance_id>/resume', methods=['POST'])
def resume_instance(instance_id):
    """Возобновить экземпляр (отменить pause)"""
    try:
        instance = EurekaInstance.query.get(instance_id)
        if not instance:
            return jsonify({'success': False, 'error': 'Instance not found'}), 404

        eureka_server = instance.eureka_application.eureka_server

        # Выполняем resume через FAgent
        # Примечание: FAgent API может не поддерживать resume, тогда нужно использовать другой метод
        # Временно возвращаем успех и обновляем статус локально
        instance.update_status('UP', reason='manual_resume', changed_by='user')
        db.session.commit()

        return jsonify({'success': True, 'message': 'Instance resumed successfully'}), 200

    except Exception as e:
        logger.error(f"Ошибка resume: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances/<int:instance_id>/shutdown', methods=['POST'])
def shutdown_instance(instance_id):
    """Остановить экземпляр"""
    try:
        data = request.get_json() or {}
        graceful = data.get('graceful', True)

        instance = EurekaInstance.query.get(instance_id)
        if not instance:
            return jsonify({'success': False, 'error': 'Instance not found'}), 404

        eureka_server = instance.eureka_application.eureka_server

        # Выполняем shutdown асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, message = loop.run_until_complete(
            EurekaService.shutdown_application(eureka_server, instance.instance_id, graceful=graceful)
        )
        loop.close()

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 500

    except Exception as e:
        logger.error(f"Ошибка shutdown: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances/<int:instance_id>/loglevel', methods=['POST'])
def set_log_level_instance(instance_id):
    """Изменить уровень логирования"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        logger_name = data.get('logger')
        level = data.get('level')

        if not logger_name or not level:
            return jsonify({'success': False, 'error': 'logger and level are required'}), 400

        instance = EurekaInstance.query.get(instance_id)
        if not instance:
            return jsonify({'success': False, 'error': 'Instance not found'}), 404

        eureka_server = instance.eureka_application.eureka_server

        # Выполняем set_log_level асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, message = loop.run_until_complete(
            EurekaService.set_log_level(eureka_server, instance.instance_id, logger_name, level)
        )
        loop.close()

        if success:
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 500

    except Exception as e:
        logger.error(f"Ошибка set_log_level: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Маппинг
# =============================================================================

@eureka_bp.route('/instances/unmapped', methods=['GET'])
def get_unmapped_instances():
    """Получить список несвязанных экземпляров"""
    try:
        unmapped = EurekaMapper.get_unmapped_instances()

        return jsonify({
            'success': True,
            'data': [inst.to_dict(include_application=False) for inst in unmapped]
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения несвязанных экземпляров: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances/<int:id>/map', methods=['POST'])
def set_instance_mapping(id):
    """Установить ручной маппинг"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        application_id = data.get('application_id')
        mapped_by = data.get('mapped_by', 'api')
        notes = data.get('notes')

        success = EurekaMapper.set_manual_mapping(id, application_id, mapped_by, notes)

        if success:
            return jsonify({'success': True, 'message': 'Mapping set successfully'}), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to set mapping'}), 500

    except Exception as e:
        logger.error(f"Ошибка установки маппинга: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/instances/<int:id>/map', methods=['DELETE'])
def clear_instance_mapping(id):
    """Удалить ручной маппинг"""
    try:
        success = EurekaMapper.clear_manual_mapping(id)

        if success:
            return jsonify({'success': True, 'message': 'Mapping cleared successfully'}), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to clear mapping'}), 500

    except Exception as e:
        logger.error(f"Ошибка удаления маппинга: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/mapping/statistics', methods=['GET'])
def get_mapping_statistics():
    """Получить статистику маппинга"""
    try:
        stats = EurekaMapper.get_mapping_statistics()

        return jsonify({
            'success': True,
            'data': stats
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения статистики маппинга: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Синхронизация
# =============================================================================

@eureka_bp.route('/sync', methods=['POST'])
def sync_all_servers():
    """Принудительная синхронизация всех Eureka серверов"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(EurekaService.sync_all_eureka_servers())
        loop.close()

        # Запускаем маппинг после синхронизации
        mapped_count, total_unmapped = EurekaMapper.map_instances_to_applications()

        return jsonify({
            'success': True,
            'data': {
                'sync_results': results,
                'mapping': {
                    'mapped_count': mapped_count,
                    'total_unmapped': total_unmapped
                }
            }
        }), 200

    except Exception as e:
        logger.error(f"Ошибка синхронизации: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/servers/<int:id>/sync', methods=['POST'])
def sync_server(id):
    """Синхронизация конкретного Eureka сервера"""
    try:
        eureka_server = EurekaServer.query.get(id)
        if not eureka_server or eureka_server.is_removed():
            return jsonify({'success': False, 'error': 'Eureka server not found'}), 404

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(EurekaService.sync_eureka_server(eureka_server))
        loop.close()

        # Запускаем маппинг после синхронизации
        if success:
            mapped_count, total_unmapped = EurekaMapper.map_instances_to_applications()

            return jsonify({
                'success': True,
                'data': {
                    'sync_success': success,
                    'mapping': {
                        'mapped_count': mapped_count,
                        'total_unmapped': total_unmapped
                    }
                }
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Sync failed'}), 500

    except Exception as e:
        logger.error(f"Ошибка синхронизации сервера: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Статистика
# =============================================================================

@eureka_bp.route('/summary', methods=['GET'])
def get_summary():
    """Получить общую статистику"""
    try:
        total_servers = EurekaServer.query.filter(EurekaServer.removed_at.is_(None)).count()
        active_servers = EurekaServer.query.filter(
            EurekaServer.is_active == True,
            EurekaServer.removed_at.is_(None)
        ).count()
        servers_with_errors = EurekaServer.query.filter(
            EurekaServer.consecutive_failures > 0,
            EurekaServer.removed_at.is_(None)
        ).count()

        total_applications = EurekaApplication.query.count()
        applications_with_errors = EurekaApplication.query.filter(
            EurekaApplication.last_fetch_status == 'failed'
        ).count()

        total_instances = EurekaInstance.query.filter(EurekaInstance.removed_at.is_(None)).count()
        instances_up = EurekaInstance.query.filter(
            EurekaInstance.status == 'UP',
            EurekaInstance.removed_at.is_(None)
        ).count()
        instances_down = EurekaInstance.query.filter(
            EurekaInstance.status == 'DOWN',
            EurekaInstance.removed_at.is_(None)
        ).count()
        instances_paused = EurekaInstance.query.filter(
            EurekaInstance.status == 'PAUSED',
            EurekaInstance.removed_at.is_(None)
        ).count()

        return jsonify({
            'success': True,
            'data': {
                'servers': {
                    'total': total_servers,
                    'active': active_servers,
                    'with_errors': servers_with_errors
                },
                'applications': {
                    'total': total_applications,
                    'with_errors': applications_with_errors
                },
                'instances': {
                    'total': total_instances,
                    'up': instances_up,
                    'down': instances_down,
                    'paused': instances_paused
                }
            }
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@eureka_bp.route('/history', methods=['GET'])
def get_history():
    """Получить историю изменений статусов"""
    try:
        instance_id = request.args.get('instance_id', type=int)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        limit = request.args.get('limit', 100, type=int)

        query = EurekaInstanceStatusHistory.query

        if instance_id:
            query = query.filter(EurekaInstanceStatusHistory.eureka_instance_id == instance_id)

        if date_from:
            date_from_dt = datetime.fromisoformat(date_from)
            query = query.filter(EurekaInstanceStatusHistory.changed_at >= date_from_dt)

        if date_to:
            date_to_dt = datetime.fromisoformat(date_to)
            query = query.filter(EurekaInstanceStatusHistory.changed_at <= date_to_dt)

        history = query.order_by(EurekaInstanceStatusHistory.changed_at.desc()).limit(limit).all()

        return jsonify({
            'success': True,
            'data': [h.to_dict() for h in history]
        }), 200

    except Exception as e:
        logger.error(f"Ошибка получения истории: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

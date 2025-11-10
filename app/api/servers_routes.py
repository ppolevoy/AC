from flask import jsonify, request
import asyncio
from datetime import datetime
import logging

from app import db
from app.models.server import Server
from app.models.application import Application
from app.services.agent_service import AgentService
from app.api import bp

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper function to run async operations in sync code"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@bp.route('/servers', methods=['GET'])
def get_servers():
    """Получение списка всех серверов"""
    try:
        servers = Server.query.all()
        result = []

        for server in servers:
            app_count = Application.query.filter_by(server_id=server.id).count()

            result.append({
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None,
                'app_count': app_count
            })

        return jsonify({
            'success': True,
            'servers': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка серверов: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/servers/<int:server_id>', methods=['GET'])
def get_server(server_id):
    """Получение информации о конкретном сервере"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404

        apps = Application.query.filter_by(server_id=server.id).all()
        app_list = []

        for app in apps:
            app_list.append({
                'id': app.id,
                'name': app.name,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'start_time': app.start_time.isoformat() if app.start_time else None
            })

        return jsonify({
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None,
                'applications': app_list
            }
        })
    except Exception as e:
        logger.error(f"Ошибка при получении информации о сервере {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/servers', methods=['POST'])
def add_server():
    """Добавление нового сервера"""
    try:
        data = request.json

        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные"
            }), 400

        required_fields = ['name', 'ip', 'port']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f"Поле {field} обязательно"
                }), 400

        # Проверяем, существует ли сервер с таким именем
        existing_server = Server.query.filter_by(name=data['name']).first()
        if existing_server:
            return jsonify({
                'success': False,
                'error': f"Сервер с именем {data['name']} уже существует"
            }), 400

        # Создаем новый сервер
        server = Server(
            name=data['name'],
            ip=data['ip'],
            port=data['port'],
            status='unknown',
            last_check=datetime.utcnow()
        )

        db.session.add(server)
        db.session.commit()

        # Запускаем проверку доступности сервера
        run_async(AgentService.update_server_applications(server.id))

        return jsonify({
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при добавлении сервера: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/servers/<int:server_id>', methods=['PUT'])
def update_server(server_id):
    """Обновление информации о сервере"""
    try:
        data = request.json

        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные"
            }), 400

        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404

        # Обновляем данные сервера
        if 'name' in data:
            # Проверяем, существует ли другой сервер с таким именем
            existing_server = Server.query.filter(Server.name == data['name'], Server.id != server_id).first()
            if existing_server:
                return jsonify({
                    'success': False,
                    'error': f"Сервер с именем {data['name']} уже существует"
                }), 400
            server.name = data['name']

        if 'ip' in data:
            server.ip = data['ip']

        if 'port' in data:
            server.port = data['port']

        db.session.commit()

        # Запускаем проверку доступности сервера после обновления
        run_async(AgentService.update_server_applications(server.id))

        return jsonify({
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'last_check': server.last_check.isoformat() if server.last_check else None
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении сервера {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/servers/<int:server_id>', methods=['DELETE'])
def delete_server(server_id):
    """Удаление сервера"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404

        # Удаляем сервер (приложения и события будут удалены автоматически из-за каскадного удаления)
        db.session.delete(server)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f"Сервер {server.name} успешно удален"
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при удалении сервера {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/servers/<int:server_id>/refresh', methods=['POST'])
def refresh_server(server_id):
    """Принудительное обновление информации о сервере"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404

        # Запускаем обновление информации о сервере
        result = run_async(AgentService.update_server_applications(server.id))

        if result:
            return jsonify({
                'success': True,
                'message': f"Информация о сервере {server.name} успешно обновлена",
                'server': {
                    'id': server.id,
                    'name': server.name,
                    'ip': server.ip,
                    'port': server.port,
                    'status': server.status,
                    'last_check': server.last_check.isoformat() if server.last_check else None
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': f"Не удалось обновить информацию о сервере {server.name}",
                'server': {
                    'id': server.id,
                    'name': server.name,
                    'ip': server.ip,
                    'port': server.port,
                    'status': server.status,
                    'last_check': server.last_check.isoformat() if server.last_check else None
                }
            })
    except Exception as e:
        logger.error(f"Ошибка при обновлении информации о сервере {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/test', methods=['GET'])
def test_api():
    """Тестовый маршрут для проверки работы API"""
    return jsonify({
        'success': True,
        'message': 'API работает корректно',
        'time': datetime.utcnow().isoformat()
    })

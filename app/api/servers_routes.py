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

        # Формируем ответ
        response_data = {
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'is_haproxy_node': server.is_haproxy_node,
                'last_check': server.last_check.isoformat() if server.last_check else None,
                'applications': app_list
            }
        }

        # Добавляем информацию о HAProxy instances если сервер является HAProxy узлом
        if server.is_haproxy_node:
            from app.models.haproxy import HAProxyInstance
            instances = HAProxyInstance.query.filter_by(server_id=server.id).all()
            response_data['haproxy_instances_count'] = len(instances)
            response_data['haproxy_instances'] = [
                {
                    'id': inst.id,
                    'name': inst.name,
                    'socket_path': inst.socket_path,
                    'is_active': inst.is_active
                } for inst in instances
            ]

        return jsonify(response_data)
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

        # HAProxy integration
        if 'is_haproxy_node' in data:
            is_haproxy_node = bool(data['is_haproxy_node'])
            old_value = server.is_haproxy_node
            logger.info(f"HAProxy флаг изменяется для {server.name}: {old_value} -> {is_haproxy_node}")
            server.is_haproxy_node = is_haproxy_node

            # Если HAProxy узел выключается, удаляем все instances
            if not is_haproxy_node and old_value:
                from app.models.haproxy import HAProxyInstance

                # Удаляем все HAProxy instances на этом сервере
                instances = HAProxyInstance.query.filter_by(server_id=server.id).all()
                for instance in instances:
                    db.session.delete(instance)
                    logger.info(f"Удален HAProxy instance {instance.name} для сервера {server.name}")

            # Если HAProxy узел включается, автоматически обнаруживаем instances
            elif is_haproxy_node and not old_value:
                from app.models.haproxy import HAProxyInstance
                from app.services.haproxy_service import HAProxyService

                logger.info(f"HAProxy узел активирован для {server.name}, запускаем обнаружение instances")

                # Запускаем обнаружение и синхронизацию instances асинхронно
                async def auto_discover_instances():
                    try:
                        logger.info(f"[AUTO-DISCOVER] Запрос instances к FAgent: http://{server.ip}:{server.port}/api/v1/haproxy/instances")
                        success, instances_data = await HAProxyService.get_instances(server)

                        if success and instances_data:
                            logger.info(f"[AUTO-DISCOVER] Обнаружено {len(instances_data)} HAProxy instances на {server.name}")

                            for instance_data in instances_data:
                                instance_name = instance_data.get('name')
                                socket_path = instance_data.get('socket_path')

                                if not instance_name:
                                    continue

                                # Создаем новый instance
                                new_instance = HAProxyInstance(
                                    name=instance_name,
                                    server_id=server.id,
                                    is_active=True,
                                    socket_path=socket_path
                                )
                                db.session.add(new_instance)
                                db.session.flush()
                                logger.info(f"[AUTO-DISCOVER] Создан HAProxy instance '{instance_name}' для сервера {server.name}")

                                # Запускаем синхронизацию
                                await HAProxyService.sync_haproxy_instance(new_instance)

                            db.session.commit()
                            logger.info(f"[AUTO-DISCOVER] Автоматическое обнаружение завершено для {server.name}")
                        else:
                            logger.warning(f"[AUTO-DISCOVER] Не удалось обнаружить instances на {server.name}")
                    except Exception as e:
                        logger.error(f"[AUTO-DISCOVER] Ошибка при автоматическом обнаружении instances: {str(e)}")
                        db.session.rollback()

                # Запускаем в фоне
                try:
                    run_async(auto_discover_instances())
                except Exception as e:
                    logger.error(f"Ошибка при запуске автоматического обнаружения instances: {str(e)}")

        db.session.commit()

        # Запускаем проверку доступности сервера после обновления
        run_async(AgentService.update_server_applications(server.id))

        # Формируем ответ с информацией о HAProxy instances если они были добавлены
        response_data = {
            'success': True,
            'server': {
                'id': server.id,
                'name': server.name,
                'ip': server.ip,
                'port': server.port,
                'status': server.status,
                'is_haproxy_node': server.is_haproxy_node,
                'last_check': server.last_check.isoformat() if server.last_check else None
            }
        }

        # Добавляем информацию о HAProxy instances если сервер является HAProxy узлом
        if server.is_haproxy_node:
            from app.models.haproxy import HAProxyInstance
            instances = HAProxyInstance.query.filter_by(server_id=server.id).all()
            response_data['haproxy_instances_count'] = len(instances)
            response_data['haproxy_instances'] = [
                {
                    'id': inst.id,
                    'name': inst.name,
                    'socket_path': inst.socket_path,
                    'is_active': inst.is_active
                } for inst in instances
            ]

        return jsonify(response_data)
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


@bp.route('/servers/<int:server_id>/discover-haproxy-instances', methods=['POST'])
def discover_haproxy_instances(server_id):
    """Обнаружение и синхронизация HAProxy instances на сервере"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404

        if not server.is_haproxy_node:
            return jsonify({
                'success': False,
                'error': 'Сервер не помечен как HAProxy узел'
            }), 400

        from app.models.haproxy import HAProxyInstance
        from app.services.haproxy_service import HAProxyService

        # Запрашиваем список instances у FAgent
        async def discover_and_sync_instances():
            logger.info(f"[ASYNC] Начинаем обнаружение instances для {server.name}")
            try:
                # Получаем список instances от FAgent
                logger.info(f"[ASYNC] Запрос instances к FAgent: http://{server.ip}:{server.port}/api/v1/haproxy/instances")
                success, instances_data = await HAProxyService.get_instances(server)
                logger.info(f"[ASYNC] Результат запроса instances: success={success}, count={len(instances_data) if instances_data else 0}")

                if not success:
                    logger.error(f"Не удалось получить список HAProxy instances от {server.name}")
                    return False, "Не удалось получить список instances от FAgent"

                if not instances_data or len(instances_data) == 0:
                    logger.warning(f"FAgent на {server.name} не вернул ни одного HAProxy instance")
                    return False, "На сервере не обнаружено HAProxy instances"

                logger.info(f"Обнаружено {len(instances_data)} HAProxy instances на {server.name}")

                created_instances = []

                # Создаем или обновляем каждый instance в БД
                for instance_data in instances_data:
                    instance_name = instance_data.get('name')
                    socket_path = instance_data.get('socket_path')
                    available = instance_data.get('available', True)

                    if not instance_name:
                        logger.warning(f"Пропущен instance без имени: {instance_data}")
                        continue

                    # Проверяем, существует ли instance
                    existing_instance = HAProxyInstance.query.filter_by(
                        server_id=server.id,
                        name=instance_name
                    ).first()

                    if existing_instance:
                        # Обновляем существующий instance
                        existing_instance.socket_path = socket_path
                        existing_instance.is_active = True
                        logger.info(f"Обновлен HAProxy instance '{instance_name}' для сервера {server.name}")
                        created_instances.append(existing_instance)
                    else:
                        # Создаем новый instance
                        new_instance = HAProxyInstance(
                            name=instance_name,
                            server_id=server.id,
                            is_active=True,
                            socket_path=socket_path
                        )
                        db.session.add(new_instance)
                        db.session.flush()  # Получить ID
                        logger.info(f"Создан HAProxy instance '{instance_name}' для сервера {server.name}")
                        created_instances.append(new_instance)

                db.session.commit()

                # Запускаем синхронизацию для каждого instance
                sync_results = []
                for instance in created_instances:
                    try:
                        success = await HAProxyService.sync_haproxy_instance(instance)
                        sync_results.append((instance.name, success))
                        if success:
                            logger.info(f"Синхронизация instance '{instance.name}' завершена успешно")
                        else:
                            logger.warning(f"Синхронизация instance '{instance.name}' завершилась с ошибками")
                    except Exception as e:
                        logger.error(f"Ошибка при синхронизации instance '{instance.name}': {str(e)}")
                        sync_results.append((instance.name, False))

                success_count = sum(1 for _, success in sync_results if success)
                logger.info(f"Синхронизировано {success_count}/{len(created_instances)} instances для {server.name}")

                return True, {
                    'instances_count': len(created_instances),
                    'synced_count': success_count,
                    'message': f"Добавлено {len(created_instances)} instances, синхронизировано {success_count}"
                }

            except Exception as e:
                logger.error(f"Ошибка при обнаружении и синхронизации instances: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return False, f"Ошибка: {str(e)}"

        # Запускаем обнаружение и синхронизацию
        logger.info(f"Запуск async функции discover_and_sync_instances для {server.name}...")
        success, result = run_async(discover_and_sync_instances())
        logger.info(f"Функция discover_and_sync_instances завершена. Success: {success}, Result: {result}")

        if success:
            return jsonify({
                'success': True,
                'instances_count': result['instances_count'],
                'synced_count': result['synced_count'],
                'message': result['message']
            })
        else:
            return jsonify({
                'success': False,
                'error': result
            }), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обнаружении HAProxy instances для сервера {server_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/servers/<int:server_id>/refresh', methods=['POST'])
def refresh_server_applications(server_id):
    """Обновление списка приложений на сервере"""
    try:
        server = Server.query.get(server_id)
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер с id {server_id} не найден"
            }), 404

        # Запускаем обновление приложений
        logger.info(f"Запрос обновления списка приложений для сервера {server.name} (ID: {server_id})")
        run_async(AgentService.update_server_applications(server_id))

        return jsonify({
            'success': True,
            'message': f'Запрос на обновление отправлен для сервера {server.name}'
        })

    except Exception as e:
        logger.error(f"Ошибка при обновлении приложений для сервера {server_id}: {str(e)}")
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

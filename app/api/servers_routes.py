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


def _build_server_response(server, include_haproxy=True, include_eureka=True):
    """
    Вспомогательная функция для формирования server response.

    Args:
        server: Объект Server
        include_haproxy: Включать ли информацию о HAProxy instances
        include_eureka: Включать ли информацию о Eureka server

    Returns:
        dict: Server response
    """
    response = {
        'id': server.id,
        'name': server.name,
        'ip': server.ip,
        'port': server.port,
        'status': server.status,
        'is_haproxy_node': server.is_haproxy_node,
        'is_eureka_node': server.is_eureka_node,
        'last_check': server.last_check.isoformat() if server.last_check else None
    }

    if include_haproxy and server.is_haproxy_node:
        from app.models.haproxy import HAProxyInstance
        instances = HAProxyInstance.query.filter_by(server_id=server.id).all()
        response['haproxy_instances_count'] = len(instances)
        response['haproxy_instances'] = [
            {
                'id': inst.id,
                'name': inst.name,
                'socket_path': inst.socket_path,
                'is_active': inst.is_active
            } for inst in instances
        ]

    if include_eureka and server.is_eureka_node:
        from app.models.eureka import EurekaServer
        eureka_server = EurekaServer.query.filter_by(server_id=server.id, removed_at=None).first()
        if eureka_server:
            response['eureka_server'] = {
                'id': eureka_server.id,
                'eureka_host': eureka_server.eureka_host,
                'eureka_port': eureka_server.eureka_port,
                'is_active': eureka_server.is_active,
                'last_sync': eureka_server.last_sync.isoformat() if eureka_server.last_sync else None
            }
        else:
            response['eureka_server'] = None

    return response


async def _discover_and_sync_instances_internal(server):
    """
    Внутренняя функция для обнаружения и синхронизации HAProxy instances.
    Используется в discover_haproxy_instances endpoint и при автоактивации узла.

    Args:
        server: Объект Server

    Returns:
        Tuple[bool, Union[dict, str]]: (success, result_dict или error_message)
    """
    from app.models.haproxy import HAProxyInstance
    from app.services.haproxy_service import HAProxyService

    logger.debug(f"Discovering HAProxy instances for {server.name}")

    try:
        # Получаем список instances от FAgent
        success, instances_data = await HAProxyService.get_instances(server)

        if not success:
            logger.error(f"Не удалось получить список HAProxy instances от {server.name}")
            return False, "Не удалось получить список instances от FAgent"

        if not instances_data:
            logger.warning(f"FAgent на {server.name} не вернул ни одного HAProxy instance")
            return False, "На сервере не обнаружено HAProxy instances"

        logger.debug(f"Found {len(instances_data)} HAProxy instances on {server.name}")

        created_instances = []

        # Создаем или обновляем каждый instance в БД
        for instance_data in instances_data:
            instance_name = instance_data.get('name')
            socket_path = instance_data.get('socket_path')

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
                logger.debug(f"Updated HAProxy instance '{instance_name}'")
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
                logger.debug(f"Created HAProxy instance '{instance_name}'")
                created_instances.append(new_instance)

        db.session.commit()

        # Запускаем синхронизацию для каждого instance
        sync_results = []
        for instance in created_instances:
            try:
                success = await HAProxyService.sync_haproxy_instance(instance)
                sync_results.append((instance.name, success))
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
        logger.exception(f"Ошибка при обнаружении и синхронизации instances")
        return False, str(e)


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
                'is_haproxy_node': server.is_haproxy_node,
                'is_eureka_node': server.is_eureka_node,
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

        # Формируем ответ используя вспомогательную функцию
        server_data = _build_server_response(server, include_haproxy=True)
        server_data['applications'] = app_list

        return jsonify({
            'success': True,
            'server': server_data
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
                logger.info(f"HAProxy узел активирован для {server.name}, запускаем обнаружение instances")

                # Запускаем обнаружение и синхронизацию используя общую функцию
                try:
                    success, result = run_async(_discover_and_sync_instances_internal(server))
                    if not success:
                        logger.warning(f"Автоматическое обнаружение instances не удалось: {result}")
                except Exception as e:
                    logger.exception(f"Ошибка при автоматическом обнаружении instances")
                    db.session.rollback()

        # Eureka integration
        if 'is_eureka_node' in data:
            is_eureka_node = bool(data['is_eureka_node'])
            old_value = server.is_eureka_node
            logger.info(f"Eureka флаг изменяется для {server.name}: {old_value} -> {is_eureka_node}")
            server.is_eureka_node = is_eureka_node

            # Если Eureka узел выключается, удаляем Eureka server
            if not is_eureka_node and old_value:
                from app.models.eureka import EurekaServer

                # Делаем soft delete Eureka server
                eureka_server = EurekaServer.query.filter_by(server_id=server.id, removed_at=None).first()
                if eureka_server:
                    from datetime import datetime
                    eureka_server.soft_delete()
                    eureka_server.is_active = False
                    logger.info(f"Деактивирован Eureka server для {server.name}")

            # Если Eureka узел включается, создаем или восстанавливаем Eureka server запись
            elif is_eureka_node and not old_value:
                logger.info(f"Eureka узел активирован для {server.name}")

                from app.models.eureka import EurekaServer

                # Получаем параметры Eureka из запроса или используем значения по умолчанию
                eureka_host = data.get('eureka_host', server.ip)
                eureka_port = data.get('eureka_port', 8761)  # Стандартный порт Eureka

                # ПРОВЕРКА: Убеждаемся что такой Eureka endpoint еще не используется другим сервером
                existing_eureka = EurekaServer.query.filter(
                    EurekaServer.eureka_host == eureka_host,
                    EurekaServer.eureka_port == eureka_port,
                    EurekaServer.server_id != server.id,
                    EurekaServer.removed_at.is_(None)
                ).first()

                if existing_eureka:
                    error_msg = (f"Eureka endpoint {eureka_host}:{eureka_port} уже используется "
                                f"сервером '{existing_eureka.server.name}' (ID={existing_eureka.server_id}). "
                                f"Один физический Eureka сервер может быть связан только с одним сервером в системе.")
                    logger.error(error_msg)
                    return jsonify({
                        'success': False,
                        'error': error_msg
                    }), 400

                # Проверяем, есть ли уже запись для этого сервера (включая удаленные)
                eureka_server = EurekaServer.query.filter_by(server_id=server.id).first()

                if eureka_server:
                    # Восстанавливаем существующую запись
                    eureka_server.restore()
                    eureka_server.eureka_host = eureka_host
                    eureka_server.eureka_port = eureka_port
                    eureka_server.is_active = True
                    logger.info(f"Восстановлен EurekaServer ID={eureka_server.id} для {server.name} ({eureka_host}:{eureka_port})")
                else:
                    # Создаем новый EurekaServer
                    eureka_server = EurekaServer(
                        server_id=server.id,
                        eureka_host=eureka_host,
                        eureka_port=eureka_port,
                        is_active=True
                    )
                    db.session.add(eureka_server)
                    db.session.flush()
                    logger.info(f"Создан EurekaServer ID={eureka_server.id} для {server.name} ({eureka_host}:{eureka_port})")

        db.session.commit()

        # Запускаем проверку доступности сервера после обновления
        run_async(AgentService.update_server_applications(server.id))

        # Формируем ответ используя вспомогательную функцию
        return jsonify({
            'success': True,
            'server': _build_server_response(server, include_haproxy=True)
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

        # Запускаем обнаружение и синхронизацию используя общую функцию
        success, result = run_async(_discover_and_sync_instances_internal(server))

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


@bp.route('/test', methods=['GET'])
def test_api():
    """Тестовый маршрут для проверки работы API"""
    return jsonify({
        'success': True,
        'message': 'API работает корректно',
        'time': datetime.utcnow().isoformat()
    })

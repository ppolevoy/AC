from flask import jsonify, request
import asyncio
import logging
import os
import subprocess

from app.config import Config
from app.services.ssh_ansible_service import get_ssh_ansible_service
from app.services.ansible_service import AnsibleService
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


@bp.route('/ssh/test', methods=['GET'])
def test_ssh_connection():
    """Тестирование SSH-подключения"""
    try:
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400

        # Запускаем тест подключения
        result = run_async(AnsibleService.test_ssh_connection())

        if result[0]:
            return jsonify({
                'success': True,
                'message': result[1]
            })
        else:
            return jsonify({
                'success': False,
                'error': result[1]
            }), 500

    except Exception as e:
        logger.error(f"Ошибка при тестировании SSH-подключения: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/ssh/config', methods=['GET'])
def get_ssh_config():
    """Получение конфигурации SSH"""
    try:
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400

        # Возвращаем конфигурацию SSH (без приватных данных)
        ssh_config = {
            'host': getattr(Config, 'SSH_HOST', 'localhost'),
            'user': getattr(Config, 'SSH_USER', 'ansible'),
            'port': getattr(Config, 'SSH_PORT', 22),
            'key_file': getattr(Config, 'SSH_KEY_FILE', '/app/.ssh/id_rsa'),
            'connection_timeout': getattr(Config, 'SSH_CONNECTION_TIMEOUT', 30),
            'command_timeout': getattr(Config, 'SSH_COMMAND_TIMEOUT', 300),
            'ansible_path': getattr(Config, 'ANSIBLE_PATH', '/etc/ansible')
        }

        # Проверяем существование SSH-ключа
        key_exists = os.path.exists(ssh_config['key_file'])
        pub_key_exists = os.path.exists(ssh_config['key_file'] + '.pub')

        # Читаем публичный ключ, если он существует
        public_key = None
        if pub_key_exists:
            try:
                with open(ssh_config['key_file'] + '.pub', 'r') as f:
                    public_key = f.read().strip()
            except Exception as e:
                logger.warning(f"Не удалось прочитать публичный ключ: {str(e)}")

        return jsonify({
            'success': True,
            'config': ssh_config,
            'key_status': {
                'private_key_exists': key_exists,
                'public_key_exists': pub_key_exists,
                'public_key': public_key
            }
        })

    except Exception as e:
        logger.error(f"Ошибка при получении конфигурации SSH: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/ssh/generate-key', methods=['POST'])
def generate_ssh_key():
    """Генерация нового SSH-ключа"""
    try:
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400

        key_file = getattr(Config, 'SSH_KEY_FILE', '/app/.ssh/id_rsa')

        # Создаем директорию для ключей, если она не существует
        key_dir = os.path.dirname(key_file)
        os.makedirs(key_dir, mode=0o700, exist_ok=True)

        # Удаляем существующие ключи
        if os.path.exists(key_file):
            os.remove(key_file)
        if os.path.exists(key_file + '.pub'):
            os.remove(key_file + '.pub')

        # Генерируем новый ключ
        cmd = [
            'ssh-keygen',
            '-t', 'rsa',
            '-b', '4096',
            '-f', key_file,
            '-N', ''  # Без пароля
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            # Читаем публичный ключ
            with open(key_file + '.pub', 'r') as f:
                public_key = f.read().strip()

            # Устанавливаем правильные права доступа
            os.chmod(key_file, 0o600)
            os.chmod(key_file + '.pub', 0o644)

            logger.info(f"Новый SSH-ключ сгенерирован: {key_file}")

            return jsonify({
                'success': True,
                'message': 'SSH-ключ успешно сгенерирован',
                'public_key': public_key
            })
        else:
            error_msg = result.stderr or result.stdout
            logger.error(f"Ошибка при генерации SSH-ключа: {error_msg}")
            return jsonify({
                'success': False,
                'error': f'Ошибка при генерации ключа: {error_msg}'
            }), 500

    except Exception as e:
        logger.error(f"Ошибка при генерации SSH-ключа: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/ssh/playbooks', methods=['GET'])
def check_playbooks():
    """Получение списка всех playbook файлов из ansible каталога на удаленном хосте"""
    try:
        # Проверяем, включен ли SSH-режим
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return jsonify({
                'success': False,
                'error': 'SSH-режим отключен в конфигурации'
            }), 400

        # Получаем сервис
        ssh_service = get_ssh_ansible_service()

        # Получаем список всех playbook файлов из каталога
        async def get_all_playbook_files():
            return await ssh_service.get_all_playbooks()

        # Запускаем получение списка
        results = run_async(get_all_playbook_files())

        # Если список пустой, возвращаем предупреждение
        if not results:
            logger.warning(f"Не найдено playbook файлов в каталоге {ssh_service.ssh_config.ansible_path}")
            return jsonify({
                'success': True,
                'playbooks': {},
                'message': 'No playbook files found in ansible directory'
            })

        logger.info(f"Найдено {len(results)} playbook файлов")

        return jsonify({
            'success': True,
            'playbooks': results
        })

    except Exception as e:
        logger.error(f"Ошибка при получении списка playbook-ов: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/ssh/status', methods=['GET'])
def get_ssh_status():
    """Получение полного статуса SSH-подключения"""
    try:
        # Базовая информация о статусе
        status = {
            'ssh_enabled': getattr(Config, 'USE_SSH_ANSIBLE', False),
            'config': {},
            'key_status': {},
            'connection_status': {},
            'playbooks_status': {}
        }

        # Если SSH отключен, возвращаем базовую информацию
        if not status['ssh_enabled']:
            return jsonify({
                'success': True,
                'status': status
            })

        # Конфигурация SSH
        status['config'] = {
            'host': getattr(Config, 'SSH_HOST', 'localhost'),
            'user': getattr(Config, 'SSH_USER', 'ansible'),
            'port': getattr(Config, 'SSH_PORT', 22),
            'key_file': getattr(Config, 'SSH_KEY_FILE', '/app/.ssh/id_rsa'),
            'ansible_path': getattr(Config, 'ANSIBLE_PATH', '/etc/ansible')
        }

        # Статус SSH-ключей
        key_file = status['config']['key_file']
        status['key_status'] = {
            'private_key_exists': os.path.exists(key_file),
            'public_key_exists': os.path.exists(key_file + '.pub'),
            'key_permissions_ok': False
        }

        # Проверяем права доступа к ключу
        if status['key_status']['private_key_exists']:
            try:
                key_stat = os.stat(key_file)
                status['key_status']['key_permissions_ok'] = not (key_stat.st_mode & 0o077)
            except:
                pass

        # Тестируем подключение
        if status['key_status']['private_key_exists']:
            try:
                ssh_service = get_ssh_ansible_service()

                # Тест подключения
                connection_result = run_async(ssh_service.test_connection())
                status['connection_status'] = {
                    'connected': connection_result[0],
                    'message': connection_result[1]
                }

                # Если подключение успешно, проверяем playbook-и
                if connection_result[0]:
                    # Используем новый метод для получения всех playbooks
                    async def get_all_playbook_files():
                        return await ssh_service.get_all_playbooks()

                    playbook_results_dict = run_async(get_all_playbook_files())

                    # Преобразуем для совместимости с текущим форматом
                    playbook_results = {}
                    for playbook_name, info in playbook_results_dict.items():
                        playbook_results[playbook_name] = info.get('exists', False)

                    status['playbooks_status'] = playbook_results

            except Exception as e:
                status['connection_status'] = {
                    'connected': False,
                    'message': f'Ошибка при тестировании: {str(e)}'
                }
        else:
            status['connection_status'] = {
                'connected': False,
                'message': 'SSH-ключ не найден'
            }

        return jsonify({
            'success': True,
            'status': status
        })

    except Exception as e:
        logger.error(f"Ошибка при получении статуса SSH: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

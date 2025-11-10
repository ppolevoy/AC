from flask import jsonify, request
import os
import logging

from app.models.application import Application
from app.models.server import Server
from app.services.ssh_ansible_service import get_ssh_ansible_service, SSHAnsibleService
from app.api import bp

logger = logging.getLogger(__name__)


@bp.route('/ansible/variables', methods=['GET'])
def get_available_variables():
    """
    Получить список доступных переменных и информацию о кастомных параметрах
    """
    try:
        return jsonify({
            'success': True,
            'dynamic_variables': SSHAnsibleService.AVAILABLE_VARIABLES,
            'custom_parameters': {
                'description': 'Кастомные параметры можно задавать с явными значениями',
                'format': '{parameter_name=value}',
                'examples': [
                    '{onlydeliver=true}',
                    '{env=production}',
                    '{timeout=30}',
                    '{debug=false}'
                ],
                'validation': {
                    'name_pattern': '^[a-zA-Z_][a-zA-Z0-9_]*$',
                    'value_pattern': '^[a-zA-Z0-9_\\-\\./:\\@\\=\\s]+$',
                    'description': 'Имя должно начинаться с буквы или _, значение может содержать буквы, цифры и безопасные символы'
                }
            },
            'usage_examples': [
                {
                    'description': 'Только динамические параметры',
                    'playbook_path': '/playbook.yml {server} {app} {distr_url}',
                    'result': 'ansible-playbook /playbook.yml -e server="srv01" -e app="myapp" -e distr_url="http://nexus/app.jar"'
                },
                {
                    'description': 'Смешанные параметры',
                    'playbook_path': '/playbook.yml {server} {app} {onlydeliver=true} {env=staging}',
                    'result': 'ansible-playbook /playbook.yml -e server="srv01" -e app="myapp" -e onlydeliver="true" -e env="staging"'
                },
                {
                    'description': 'Только кастомные параметры',
                    'playbook_path': '/custom.yml {deploy_mode=blue-green} {rollback=false} {timeout=300}',
                    'result': 'ansible-playbook /custom.yml -e deploy_mode="blue-green" -e rollback="false" -e timeout="300"'
                }
            ],
            'note': 'Динамические параметры берутся из контекста события, кастомные используют явные значения'
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка переменных: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/ansible/validate-playbook', methods=['POST'])
def validate_playbook_config():
    """
    Валидация конфигурации playbook с параметрами

    Body:
    {
        "playbook_path": "/path/to/playbook.yml {server} {app} {onlydeliver=true}"
    }
    """
    try:
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле 'playbook_path'"
            }), 400

        playbook_path_with_params = data['playbook_path']

        ssh_service = get_ssh_ansible_service()

        # Парсим конфигурацию
        playbook_config = ssh_service.parse_playbook_config(playbook_path_with_params)

        # Валидируем параметры
        is_valid, invalid_params = ssh_service.validate_parameters(playbook_config.parameters)

        # Формируем детальную информацию о параметрах
        parameters_info = []
        for param in playbook_config.parameters:
            param_info = {
                'name': param.name,
                'type': 'custom' if param.is_custom else 'dynamic',
                'value': param.value if param.is_custom else None,
                'is_valid': True
            }

            if param.is_custom:
                param_info['description'] = f"Кастомный параметр со значением '{param.value}'"
            else:
                if param.name in SSHAnsibleService.AVAILABLE_VARIABLES:
                    param_info['description'] = SSHAnsibleService.AVAILABLE_VARIABLES[param.name]
                else:
                    param_info['is_valid'] = False
                    param_info['description'] = "Неизвестный динамический параметр"

            parameters_info.append(param_info)

        # Пример команды
        example_vars = {}
        for param in playbook_config.parameters:
            if param.is_custom:
                # Для кастомных параметров используем их явные значения
                example_vars[param.name] = param.value or ''
            else:
                # Для динамических параметров генерируем примеры
                if param.name == 'server':
                    example_vars[param.name] = 'web01.example.com'
                elif param.name in ['app', 'app_name']:
                    example_vars[param.name] = 'myapp'
                elif param.name == 'distr_url':
                    example_vars[param.name] = 'http://nexus/app.jar'
                elif param.name == 'mode':
                    example_vars[param.name] = 'immediate'
                elif param.name == 'restart_mode':  # Старое название для совместимости
                    example_vars[param.name] = 'now'
                elif param.name == 'image_url':
                    example_vars[param.name] = 'docker.io/myapp:latest'
                elif param.name == 'app_id':
                    example_vars[param.name] = '1'
                elif param.name == 'server_id':
                    example_vars[param.name] = '1'
                else:
                    example_vars[param.name] = '<значение>'

        example_command = f"ansible-playbook {playbook_config.path}"
        for key, value in example_vars.items():
            example_command += f' -e {key}="{value}"'

        # Подсчет динамических и кастомных параметров
        dynamic_count = sum(1 for p in playbook_config.parameters if not p.is_custom)
        custom_count = sum(1 for p in playbook_config.parameters if p.is_custom)

        response = {
            'success': True,
            'is_valid': is_valid,
            'playbook_path': playbook_config.path,
            'parameters': parameters_info,
            'invalid_parameters': invalid_params,
            'example_command': example_command,
            # Для совместимости с фронтендом
            'dynamic_count': dynamic_count,
            'custom_count': custom_count,
            'statistics': {
                'total_parameters': len(playbook_config.parameters),
                'dynamic_parameters': dynamic_count,
                'custom_parameters': custom_count
            }
        }

        if not is_valid:
            response['message'] = f"Найдены недопустимые параметры: {', '.join(invalid_params)}"
            response['hint'] = "Проверьте имена динамических параметров и формат кастомных параметров"
        else:
            response['message'] = "Все параметры валидны и готовы к использованию"

        return jsonify(response)

    except Exception as e:
        logger.error(f"Ошибка при валидации playbook конфигурации: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/test-playbook', methods=['POST'])
def test_playbook_execution(app_id):
    """
    Тестовый прогон - показывает какая команда будет выполнена (dry run)
    Поддерживает как динамические, так и кастомные параметры

    Body:
    {
        "playbook_path": "/playbook.yml {server} {app} {distr_url} {onlydeliver=true}",
        "action": "update",
        "distr_url": "http://nexus/app.jar",
        "mode": "immediate"
    }
    """
    try:
        # Получаем приложение
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404

        # Получаем сервер
        server = app.server
        if not server:
            return jsonify({
                'success': False,
                'error': f"Сервер для приложения {app.name} не найден"
            }), 404

        # Получаем данные из запроса
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле 'playbook_path'"
            }), 400

        playbook_path = data['playbook_path']
        action = data.get('action', 'update')

        # Получаем сервис
        ssh_service = get_ssh_ansible_service()

        # Парсим конфигурацию
        playbook_config = ssh_service.parse_playbook_config(playbook_path)

        # Валидируем
        is_valid, invalid_params = ssh_service.validate_parameters(playbook_config.parameters)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': f"Недопустимые параметры: {', '.join(invalid_params)}",
                'invalid_parameters': invalid_params,
                'hint': "Проверьте параметры playbook"
            }), 400

        # Определяем image_url для Docker приложений
        image_url = None
        if hasattr(app, 'deployment_type') and app.deployment_type == 'docker':
            if hasattr(app, 'docker_image'):
                image_url = app.docker_image
        elif hasattr(app, 'app_type') and app.app_type == 'docker':
            if hasattr(app, 'docker_image'):
                image_url = app.docker_image

        # Формируем контекст
        context_vars = ssh_service.build_context_vars(
            server_name=server.name,
            app_name=app.name,
            app_id=app.id,
            server_id=server.id,
            distr_url=data.get('distr_url'),
            mode=data.get('mode', data.get('restart_mode')),  # Поддержка старого параметра
            image_url=image_url
        )

        # Формируем extra_vars с учетом кастомных параметров
        extra_vars = ssh_service.build_extra_vars(playbook_config, context_vars)

        # Разделяем параметры по типам для отображения
        dynamic_params = {}
        custom_params = {}

        for param in playbook_config.parameters:
            if param.is_custom:
                custom_params[param.name] = param.value
            else:
                if param.name in extra_vars:
                    dynamic_params[param.name] = extra_vars[param.name]

        # Формируем команду
        playbook_full_path = os.path.join(
            ssh_service.ssh_config.ansible_path,
            playbook_config.path.lstrip('/')
        )

        ansible_cmd = ssh_service.build_ansible_command(
            playbook_full_path,
            extra_vars,
            verbose=True
        )

        # Формируем читаемую команду
        readable_command = ' '.join(ansible_cmd)

        return jsonify({
            'success': True,
            'action': action,
            'application': {
                'id': app.id,
                'name': app.name,
                'type': getattr(app, 'app_type', 'standard')
            },
            'server': {
                'id': server.id,
                'name': server.name
            },
            'playbook_config': {
                'path': playbook_config.path,
                'full_path': playbook_full_path,
                'total_parameters': len(playbook_config.parameters)
            },
            'parameters': {
                'dynamic': {
                    'description': 'Параметры из контекста события',
                    'values': dynamic_params
                },
                'custom': {
                    'description': 'Параметры с явными значениями',
                    'values': custom_params
                }
            },
            'extra_vars': extra_vars,
            'command': readable_command,
            'message': 'Это тестовый прогон. Команда не была выполнена.',
            'note': 'Динамические параметры взяты из контекста, кастомные используют явные значения'
        })

    except Exception as e:
        logger.error(f"Ошибка при тестировании playbook: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

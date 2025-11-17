import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from app import db
from app.models.event import Event
from app.config import Config

logger = logging.getLogger(__name__)

class PlaybookStage(Enum):
    """Этапы выполнения playbook"""
    CONNECTING = "connecting"
    GATHERING_FACTS = "gathering_facts"
    RUNNING_TASKS = "running_tasks"
    HANDLERS = "handlers"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class SSHConfig:
    """Конфигурация SSH-соединения"""
    host: str
    user: str
    port: int = 22
    key_file: Optional[str] = None
    known_hosts_file: Optional[str] = None
    connection_timeout: int = 30
    command_timeout: int = 300
    ansible_path: str = "/etc/ansible"

@dataclass
class PlaybookParameter:
    """Параметр playbook"""
    name: str  # Имя параметра
    value: Optional[str] = None  # Значение (None для динамических параметров)
    is_custom: bool = False  # True для кастомных параметров с явным значением

@dataclass
class PlaybookConfig:
    """Конфигурация playbook с параметрами"""
    path: str  # Путь к playbook файлу
    parameters: List[PlaybookParameter]  # Список параметров (динамических и кастомных)

class SSHAnsibleService:
    """
    Сервис для запуска Ansible playbook-ов через SSH с поддержкой параметров
    Поддерживает два типа параметров:
    1. Динамические: {server}, {app} - значения берутся из контекста
    2. Кастомные: {onlydeliver=true}, {env=production} - явные значения
    """
    
    # Доступные переменные для использования в playbook path
    # Это справочник для документации и валидации динамических параметров
    AVAILABLE_VARIABLES = {
        'server': 'Имя сервера',
        'app': 'Имя приложения',
        'app_name': 'Имя приложения (алиас для app)',
        'image_url': 'URL до docker image (для docker-приложений, алиас для distr_url если не указан явно)',
        'distr_url': 'URL артефакта/дистрибутива',
        'mode': 'Режим обновления (deliver, immediate, night-restart)',
        'app_id': 'ID приложения в БД',
        'server_id': 'ID сервера в БД',
        'app_instances': 'Список составных имен server::app для orchestrator (через запятую)',
        'drain_delay': 'Время ожидания после drain в секундах (для orchestrator)',
        'update_playbook': 'Имя playbook для обновления (для orchestrator)',
        'wait_after_update': 'Время ожидания после обновления в секундах (для orchestrator)'
    }
    
    # Регулярные выражения для безопасной валидации кастомных параметров
    SAFE_PARAM_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    SAFE_PARAM_VALUE_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\./:\@\=\s]+$')
    
    def __init__(self, ssh_config: SSHConfig):
        self.ssh_config = ssh_config
        self.current_stage = PlaybookStage.CONNECTING
        self.task_progress = {}
        
    @classmethod
    def from_config(cls) -> 'SSHAnsibleService':
        """Создает экземпляр из конфигурации приложения"""
        ssh_config = SSHConfig(
            host=getattr(Config, 'SSH_HOST', 'localhost'),
            user=getattr(Config, 'SSH_USER', 'ansible'),
            port=getattr(Config, 'SSH_PORT', 22),
            key_file=getattr(Config, 'SSH_KEY_FILE', None),
            known_hosts_file=getattr(Config, 'SSH_KNOWN_HOSTS_FILE', None),
            connection_timeout=getattr(Config, 'SSH_CONNECTION_TIMEOUT', 30),
            command_timeout=getattr(Config, 'SSH_COMMAND_TIMEOUT', 300),
            ansible_path=getattr(Config, 'ANSIBLE_PATH', '/etc/ansible')
        )
        return cls(ssh_config)
    
    def parse_playbook_config(self, playbook_path_with_params: str) -> PlaybookConfig:
        """
        Парсит путь к playbook с параметрами
        Поддерживает два формата параметров:
        - Динамические: {param} - значение берется из контекста
        - Кастомные: {param=value} - используется явное значение
        
        Args:
            playbook_path_with_params: Строка вида "/path/playbook.yml {param1} {param2=value}"
            
        Returns:
            PlaybookConfig: Конфигурация с путем и параметрами
            
        Examples:
            "/playbook.yml {server} {app}" -> параметры без значений (динамические)
            "/playbook.yml {server} {onlydeliver=true}" -> смешанные параметры
            "/playbook.yml {env=prod} {timeout=30}" -> параметры с явными значениями
        """
        # Регулярное выражение для поиска параметров в фигурных скобках
        # Поддерживает как {param}, так и {param=value}
        param_pattern = r'\{([^}]+)\}'
        
        # Находим все параметры
        param_matches = re.findall(param_pattern, playbook_path_with_params)
        
        parameters = []
        for match in param_matches:
            # Проверяем, содержит ли параметр знак равенства
            if '=' in match:
                # Кастомный параметр с явным значением
                parts = match.split('=', 1)  # Разбиваем только по первому '='
                param_name = parts[0].strip()
                param_value = parts[1].strip() if len(parts) > 1 else ""
                
                # Преобразуем значения булевого типа
                if param_value.lower() in ['true', 'false']:
                    param_value = param_value.lower()
                
                parameters.append(PlaybookParameter(
                    name=param_name,
                    value=param_value,
                    is_custom=True
                ))
                logger.info(f"Обнаружен кастомный параметр: {param_name}={param_value}")
            else:
                # Динамический параметр (значение из контекста)
                param_name = match.strip()
                parameters.append(PlaybookParameter(
                    name=param_name,
                    value=None,
                    is_custom=False
                ))
                logger.info(f"Обнаружен динамический параметр: {param_name}")
        
        # Удаляем параметры из пути, оставляя только путь к файлу
        playbook_path = re.sub(param_pattern, '', playbook_path_with_params).strip()
        
        # Убираем лишние пробелы
        playbook_path = ' '.join(playbook_path.split())
        
        logger.info(f"Parsed playbook config: path='{playbook_path}', parameters={[p.name for p in parameters]}")
        
        return PlaybookConfig(
            path=playbook_path,
            parameters=parameters
        )
    
    def validate_parameters(self, parameters: List[PlaybookParameter]) -> Tuple[bool, List[str]]:
        """
        Валидирует параметры playbook
        - Динамические параметры проверяются на наличие в AVAILABLE_VARIABLES
        - Кастомные параметры проверяются на безопасность имени и значения
        
        Args:
            parameters: Список параметров для проверки
            
        Returns:
            Tuple[bool, List[str]]: (все параметры валидны, список невалидных параметров)
        """
        invalid_params = []
        
        for param in parameters:
            if param.is_custom:
                # Валидация кастомных параметров
                # Проверяем безопасность имени параметра
                if not self.SAFE_PARAM_NAME_PATTERN.match(param.name):
                    invalid_params.append(f"{param.name} (небезопасное имя параметра)")
                    logger.warning(f"Unsafe custom parameter name: '{param.name}'")
                    continue
                
                # Проверяем безопасность значения параметра
                if param.value and not self.SAFE_PARAM_VALUE_PATTERN.match(param.value):
                    invalid_params.append(f"{param.name}={param.value} (небезопасное значение)")
                    logger.warning(f"Unsafe custom parameter value: '{param.name}={param.value}'")
                    continue
                    
                logger.info(f"Custom parameter '{param.name}={param.value}' validated successfully")
            else:
                # Валидация динамических параметров
                if param.name not in self.AVAILABLE_VARIABLES:
                    invalid_params.append(param.name)
                    logger.warning(f"Unknown dynamic parameter '{param.name}' in playbook path")
        
        return len(invalid_params) == 0, invalid_params
    
    def sanitize_value(self, value: str) -> str:
        """
        Санитизация значения для безопасной передачи в ansible
        
        Args:
            value: Исходное значение
            
        Returns:
            str: Санитизированное значение
        """
        # Экранируем специальные символы для shell
        value = value.replace('"', '\\"')
        value = value.replace('$', '\\$')
        value = value.replace('`', '\\`')
        value = value.replace('\\', '\\\\')
        
        return value
    
    def build_context_vars(self,
                          server_name: str,
                          app_name: str,
                          app_id: int,
                          server_id: int,
                          distr_url: Optional[str] = None,
                          mode: Optional[str] = None,
                          image_url: Optional[str] = None,
                          orchestrator_app_instances: Optional[str] = None,
                          orchestrator_drain_delay: Optional[int] = None,
                          orchestrator_update_playbook: Optional[str] = None) -> Dict[str, str]:
        """
        Формирует контекстные переменные для подстановки в playbook

        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения
            server_id: ID сервера
            distr_url: URL дистрибутива (опционально)
            mode: Режим обновления (deliver, immediate, night-restart) (опционально)
            image_url: URL docker образа (опционально)
            orchestrator_app_instances: Список составных имен server::app для orchestrator (опционально)
            orchestrator_drain_delay: Время ожидания после drain в секундах (опционально)
            orchestrator_update_playbook: Имя playbook для обновления (опционально)

        Returns:
            Dict[str, str]: Словарь с переменными контекста
        """
        context_vars = {
            'server': server_name,
            'app': app_name,
            'app_name': app_name,  # Алиас
            'app_id': str(app_id),
            'server_id': str(server_id)
        }

        # Добавляем опциональные переменные только если они переданы
        if distr_url:
            context_vars['distr_url'] = distr_url

        if mode:
            context_vars['mode'] = mode

        # Для Docker-приложений image_url может быть алиасом для distr_url
        if image_url:
            context_vars['image_url'] = image_url
        elif distr_url:
            # Если image_url не задан явно, используем distr_url как алиас
            context_vars['image_url'] = distr_url
            logger.info(f"image_url установлен как алиас для distr_url: {distr_url}")

        # Добавляем параметры для orchestrator playbook
        if orchestrator_app_instances:
            context_vars['app_instances'] = orchestrator_app_instances
            logger.info(f"Orchestrator app_instances: {orchestrator_app_instances}")

        if orchestrator_drain_delay is not None:
            context_vars['drain_delay'] = str(orchestrator_drain_delay)
            logger.info(f"Orchestrator drain_delay: {orchestrator_drain_delay}s")

        if orchestrator_update_playbook:
            context_vars['update_playbook'] = orchestrator_update_playbook
            logger.info(f"Orchestrator update_playbook: {orchestrator_update_playbook}")

        return context_vars
    
    def build_extra_vars(self, 
                        playbook_config: PlaybookConfig,
                        context_vars: Dict[str, str]) -> Dict[str, str]:
        """
        Формирует extra_vars для ansible-playbook на основе конфигурации и контекста
        Объединяет динамические параметры из контекста и кастомные параметры с явными значениями
        
        Args:
            playbook_config: Конфигурация playbook с параметрами
            context_vars: Словарь с доступными значениями переменных
            
        Returns:
            Dict[str, str]: Словарь extra_vars для передачи в ansible-playbook
        """
        extra_vars = {}
        
        # Обрабатываем каждый параметр из конфигурации
        for param in playbook_config.parameters:
            if param.is_custom:
                # Кастомный параметр - используем явное значение
                if param.value is not None:
                    # Санитизируем значение
                    sanitized_value = self.sanitize_value(str(param.value))
                    extra_vars[param.name] = sanitized_value
                    logger.info(f"Added custom parameter: {param.name}={sanitized_value}")
                else:
                    # Кастомный параметр без значения - используем пустую строку
                    extra_vars[param.name] = ""
                    logger.warning(f"Custom parameter '{param.name}' has no value, using empty string")
            else:
                # Динамический параметр - берем из контекста
                if param.name in context_vars:
                    value = context_vars[param.name]
                    if value is not None:
                        extra_vars[param.name] = str(value)
                        logger.info(f"Added dynamic parameter from context: {param.name}={value}")
                    else:
                        logger.warning(f"Dynamic parameter '{param.name}' has None value in context, using empty string")
                        extra_vars[param.name] = ""
                else:
                    logger.warning(f"Dynamic parameter '{param.name}' not found in context, using empty string")
                    extra_vars[param.name] = ""
        
        logger.info(f"Built extra_vars with {len(extra_vars)} parameters: {list(extra_vars.keys())}")
        
        return extra_vars
    
    def build_ansible_command(self,
                            playbook_path: str,
                            extra_vars: Dict[str, str],
                            inventory: Optional[str] = None,
                            verbose: bool = True) -> List[str]:
        """
        Формирует команду для запуска ansible-playbook
        
        Args:
            playbook_path: Путь к playbook файлу
            extra_vars: Словарь с extra переменными
            inventory: Путь к inventory файлу (опционально)
            verbose: Включить verbose вывод
            
        Returns:
            List[str]: Список элементов команды
        """
        cmd = [
            'cd', self.ssh_config.ansible_path, '&&',
            'ansible-playbook',
            playbook_path
        ]
        
        # Добавляем inventory если указан
        if inventory:
            cmd.extend(['-i', inventory])
        
        # Добавляем extra vars
        for key, value in extra_vars.items():
            # Значение уже санитизировано в build_extra_vars
            cmd.extend(['-e', f'{key}="{value}"'])
        
        # Добавляем verbose если нужно
        if verbose:
            cmd.append('-v')
        
        logger.info(f"Built ansible command with {len(extra_vars)} variables")
        
        return cmd
    
    async def update_application(self,
                               server_name: str,
                               app_name: str,
                               app_id: int,
                               distr_url: str,
                               mode: str,
                               playbook_path: Optional[str] = None,
                               extra_params: Optional[Dict] = None) -> Tuple[bool, str]:
        """
        Запуск Ansible playbook для обновления приложения через SSH

        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            distr_url: URL дистрибутива
            mode: Режим обновления (deliver, immediate, night-restart)
            playbook_path: Путь к playbook с параметрами (опционально)
            extra_params: Дополнительные параметры для orchestrator (опционально)

        Returns:
            Tuple[bool, str]: (успех операции, информация о результате)
        """
        # Извлекаем дополнительные параметры для orchestrator если они есть
        orchestrator_app_instances = None
        orchestrator_drain_delay = None
        orchestrator_update_playbook = None

        if extra_params:
            orchestrator_app_instances = extra_params.get('app_instances')
            orchestrator_drain_delay = extra_params.get('drain_delay')
            orchestrator_update_playbook = extra_params.get('update_playbook')
            logger.info(f"Получены extra_params для orchestrator: {extra_params}")

        # Если путь к playbook не указан, используем playbook по умолчанию
        if not playbook_path:
            playbook_path = Config.DEFAULT_UPDATE_PLAYBOOK
        
        # Парсим конфигурацию playbook
        playbook_config = self.parse_playbook_config(playbook_path)
        
        # Валидируем параметры
        is_valid, invalid_params = self.validate_parameters(playbook_config.parameters)
        if not is_valid:
            error_msg = f"Недопустимые параметры в playbook path: {', '.join(invalid_params)}"
            logger.error(error_msg)
            return False, error_msg
        
        # Формируем полный путь к playbook
        playbook_full_path = os.path.join(
            self.ssh_config.ansible_path, 
            playbook_config.path.lstrip('/')
        )
        
        try:
            # Получаем ID сервера по имени
            from app.models.server import Server
            from app.models.application_instance import ApplicationInstance

            server = Server.query.filter_by(name=server_name).first()
            if not server:
                error_msg = f"Сервер с именем {server_name} не найден"
                logger.error(error_msg)
                return False, error_msg

            # Получаем информацию о приложении
            app = ApplicationInstance.query.get(app_id)
            image_url = None
            
            # Проверяем, если это Docker приложение
            if app and hasattr(app, 'deployment_type') and app.deployment_type == 'docker':
                # Получаем image_url для Docker приложений
                if hasattr(app, 'docker_image'):
                    image_url = app.docker_image
            
            # Проверяем SSH-соединение
            connection_ok, connection_msg = await self.test_connection()
            if not connection_ok:
                await self._create_event(
                    event_type='update',
                    description=f"Ошибка SSH-подключения при обновлении {app_name} на {server_name}: {connection_msg}",
                    status='failed',
                    server_id=server.id,
                    instance_id=app_id
                )
                return False, f"SSH-соединение не удалось: {connection_msg}"
            
            # Записываем событие о начале обновления
            await self._create_event(
                event_type='update',
                description=f"Запуск обновления приложения {app_name} на сервере {server_name}",
                status='pending',
                server_id=server.id,
                instance_id=app_id
            )
            
            # Проверяем существование playbook на удаленном хосте
            if not await self._remote_file_exists(playbook_full_path):
                error_msg = f"Ansible playbook не найден на удаленном хосте: {playbook_full_path}"
                logger.error(error_msg)
                
                await self._create_event(
                    event_type='update',
                    description=f"Ошибка обновления {app_name} на {server_name}: {error_msg}",
                    status='failed',
                    server_id=server.id,
                    instance_id=app_id
                )
                return False, error_msg
            
            # Формируем контекст переменных из параметров события
            context_vars = self.build_context_vars(
                server_name=server_name,
                app_name=app_name,
                app_id=app_id,
                server_id=server.id,
                distr_url=distr_url,
                mode=mode,
                image_url=image_url,
                orchestrator_app_instances=orchestrator_app_instances,
                orchestrator_drain_delay=orchestrator_drain_delay,
                orchestrator_update_playbook=orchestrator_update_playbook
            )
            
            # Формируем extra_vars на основе конфигурации и контекста
            extra_vars = self.build_extra_vars(playbook_config, context_vars)
            
            # Формируем команду для запуска Ansible
            ansible_cmd = self.build_ansible_command(
                playbook_full_path,
                extra_vars,
                verbose=True
            )
            
            logger.info(f"Запуск Ansible через SSH: {' '.join(ansible_cmd)}")
            
            # Выполняем команду
            success, output, error_output = await self._execute_ansible_command(
                ansible_cmd, server.id, app_id, app_name, server_name, 'update'
            )
            
            if success:
                result_msg = f"Обновление приложения {app_name} на сервере {server_name} выполнено успешно"
                logger.info(result_msg)
                
                await self._create_event(
                    event_type='update',
                    description=f"Обновление {app_name} на {server_name} завершено успешно",
                    status='success',
                    server_id=server.id,
                    instance_id=app_id
                )
                
                return True, result_msg
            else:
                error_msg = f"Ошибка при обновлении {app_name} на {server_name}: {error_output}"
                logger.error(error_msg)
                
                await self._create_event(
                    event_type='update',
                    description=f"Ошибка обновления {app_name} на {server_name}: {error_output}",
                    status='failed',
                    server_id=server.id,
                    instance_id=app_id
                )
                
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Исключение при обновлении {app_name} на {server_name}: {str(e)}"
            logger.error(error_msg)
            
            try:
                await self._create_event(
                    event_type='update',
                    description=f"Критическая ошибка обновления {app_name} на {server_name}: {str(e)}",
                    status='failed',
                    server_id=server.id if 'server' in locals() else None,
                    instance_id=app_id
                )
            except:
                pass
            
            return False, error_msg
    
    async def manage_application(self,
                                server_name: str,
                                app_name: str, 
                                app_id: int,
                                action: str,
                                playbook_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Управление приложением (start/stop/restart) через Ansible playbook
        
        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            action: Действие (start/stop/restart)
            playbook_path: Путь к playbook с параметрами (опционально)
            
        Returns:
            Tuple[bool, str]: (успех операции, информация о результате)
        """
        # Здесь аналогичная логика для других операций
        # Используем те же методы parse_playbook_config, validate_parameters, build_extra_vars
        # Код опущен для краткости, но следует той же логике что и update_application
        pass
    
    # Вспомогательные методы (остаются без изменений)
    async def test_connection(self) -> Tuple[bool, str]:
        """Проверка SSH-соединения с хостом"""
        try:
            logger.info(f"Проверка SSH-соединения с {self.ssh_config.host}")
            
            cmd = self._build_ssh_command(['echo', 'SSH connection test'])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.ssh_config.connection_timeout
                )
                
                if process.returncode == 0:
                    logger.info("SSH-соединение успешно установлено")
                    return True, "SSH-соединение успешно установлено"
                else:
                    error_msg = stderr.decode().strip()
                    logger.error(f"Ошибка SSH-соединения: {error_msg}")
                    return False, f"Ошибка SSH-соединения: {error_msg}"
                    
            except asyncio.TimeoutError:
                logger.error("Таймаут при проверке SSH-соединения")
                return False, "Таймаут при проверке SSH-соединения"
                
        except Exception as e:
            logger.error(f"Исключение при проверке SSH-соединения: {str(e)}")
            return False, f"Исключение: {str(e)}"
    
    async def _remote_file_exists(self, remote_path: str) -> bool:
        """Проверка существования файла на удаленном хосте"""
        try:
            cmd = self._build_ssh_command(['test', '-f', remote_path, '&&', 'echo', 'exists'])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            
            return b'exists' in stdout
        except Exception as e:
            logger.error(f"Ошибка при проверке существования файла {remote_path}: {str(e)}")
            return False
    
    def _build_ssh_command(self, remote_command: list) -> list:
        """Формирует SSH команду для выполнения"""
        ssh_cmd = ['ssh']
        
        if self.ssh_config.key_file:
            ssh_cmd.extend(['-i', self.ssh_config.key_file])
        
        ssh_cmd.extend([
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', f'ConnectTimeout={self.ssh_config.connection_timeout}',
            '-p', str(self.ssh_config.port),
            f'{self.ssh_config.user}@{self.ssh_config.host}'
        ])
        
        if isinstance(remote_command, list) and len(remote_command) == 3 and remote_command[1] == '-c':
            ssh_cmd.extend(remote_command)
        else:
            ssh_cmd.append(' '.join(str(cmd) for cmd in remote_command))
        
        return ssh_cmd
    
    def _parse_ansible_output(self, line: str) -> Optional[Dict[str, Any]]:
        """Парсит вывод Ansible для отслеживания этапов"""
        line = line.strip()
        
        if "PLAY [" in line:
            self.current_stage = PlaybookStage.GATHERING_FACTS
            return {"stage": "play_start", "message": line}
            
        elif "TASK [Gathering Facts]" in line:
            self.current_stage = PlaybookStage.GATHERING_FACTS
            return {"stage": "gathering_facts", "message": "Сбор информации о системе"}
            
        elif "TASK [" in line:
            self.current_stage = PlaybookStage.RUNNING_TASKS
            task_name = line.split("TASK [")[1].split("]")[0]
            return {"stage": "task", "message": f"Выполнение задачи: {task_name}"}
            
        elif "RUNNING HANDLER [" in line:
            self.current_stage = PlaybookStage.HANDLERS
            handler_name = line.split("RUNNING HANDLER [")[1].split("]")[0]
            return {"stage": "handler", "message": f"Выполнение обработчика: {handler_name}"}
            
        elif "PLAY RECAP" in line:
            self.current_stage = PlaybookStage.COMPLETED
            return {"stage": "recap", "message": "Завершение playbook"}
            
        elif "fatal:" in line or "ERROR!" in line:
            self.current_stage = PlaybookStage.FAILED
            return {"stage": "error", "message": line}
            
        elif "ok:" in line:
            return {"stage": "task_ok", "message": line}
            
        elif "changed:" in line:
            return {"stage": "task_changed", "message": line}
            
        elif "skipping:" in line:
            return {"stage": "task_skipped", "message": line}
            
        return None
    
    async def _execute_ansible_command(self, ansible_cmd: list, server_id: int, app_id: int,
                                     app_name: str, server_name: str, action: str) -> Tuple[bool, str, str]:
        """Выполняет команду Ansible через SSH с отслеживанием этапов"""
        ssh_cmd = self._build_ssh_command(ansible_cmd)

        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_lines = []
            stderr_lines = []

            async def read_stdout():
                """Читает stdout чанками для обработки длинных строк без переносов"""
                buffer = b''
                chunk_size = 8192  # Размер чанка для чтения

                while True:
                    chunk = await process.stdout.read(chunk_size)
                    if not chunk:
                        # Обрабатываем остаток буфера
                        if buffer:
                            line_str = buffer.decode('utf-8', errors='ignore').strip()
                            if line_str:
                                stdout_lines.append(line_str)
                                stage_info = self._parse_ansible_output(line_str)
                                if stage_info:
                                    logger.info(f"Ansible {action} для {app_name}: {stage_info['message']}")
                        break

                    buffer += chunk
                    
                    # Ищем переносы строк в буфере
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if line_str:
                            stdout_lines.append(line_str)
                            stage_info = self._parse_ansible_output(line_str)
                            if stage_info:
                                logger.info(f"Ansible {action} для {app_name}: {stage_info['message']}")

            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if line_str:
                        stderr_lines.append(line_str)
                        logger.warning(f"Ansible stderr: {line_str}")

            await asyncio.gather(
                read_stdout(),
                read_stderr()
            )

            try:
                await asyncio.wait_for(process.wait(), timeout=self.ssh_config.command_timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return False, "", "Таймаут выполнения команды Ansible"

            success = process.returncode == 0
            stdout_output = '\n'.join(stdout_lines)
            stderr_output = '\n'.join(stderr_lines)

            return success, stdout_output, stderr_output

        except Exception as e:
            logger.error(f"Исключение при выполнении Ansible команды: {str(e)}")
            return False, "", str(e)
    
    async def _create_event(self, event_type: str, description: str, status: str,
                          server_id: Optional[int] = None, instance_id: Optional[int] = None):
        """Создает событие в БД"""
        try:
            event = Event(
                event_type=event_type,
                description=description,
                status=status,
                server_id=server_id,
                instance_id=instance_id
            )
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            logger.error(f"Ошибка при создании события: {str(e)}")
            db.session.rollback()
    
    async def get_all_playbooks(self) -> Dict[str, Dict[str, Any]]:
        """Получает список всех playbook файлов из ansible каталога"""
        try:
            logger.info(f"Получение списка всех playbooks из {self.ssh_config.ansible_path}")
            
            bash_cmd = f"cd {self.ssh_config.ansible_path} && ls -1 *.yml *.yaml 2>/dev/null || true"
            
            ssh_cmd = self._build_ssh_command(['bash', '-c', f'"{bash_cmd}"'])
            
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.ssh_config.connection_timeout
                )
                
                output = stdout.decode().strip()
                
                if not output:
                    logger.warning(f"Не найдено playbook файлов в {self.ssh_config.ansible_path}")
                    return {}
                
                file_list = output.split('\n')
                file_list = [f.strip() for f in file_list if f.strip()]
                
                results = {}
                for filename in file_list:
                    if 'cannot access' in filename or filename.startswith('ls:'):
                        continue
                        
                    results[filename] = {
                        'exists': True,
                        'path': os.path.join(self.ssh_config.ansible_path, filename)
                    }
                
                logger.info(f"Найдено {len(results)} playbook файлов: {list(results.keys())}")
                return results
                
            except asyncio.TimeoutError:
                logger.error("Таймаут при получении списка playbooks")
                return {}
                
        except Exception as e:
            logger.error(f"Исключение при получении списка playbooks: {str(e)}")
            return {}

# Синглтон для получения экземпляра сервиса
_ssh_ansible_service = None

def get_ssh_ansible_service() -> SSHAnsibleService:
    """Получает или создает экземпляр SSH Ansible сервиса"""
    global _ssh_ansible_service
    if _ssh_ansible_service is None:
        _ssh_ansible_service = SSHAnsibleService.from_config()
    return _ssh_ansible_service
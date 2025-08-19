import asyncio
import logging
import os
import tempfile
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
class PlaybookConfig:
    """Конфигурация playbook с параметрами"""
    path: str  # Путь к playbook файлу
    parameters: List[str]  # Список параметров в фигурных скобках
    extra_vars: Dict[str, str]  # Словарь дополнительных переменных

class SSHAnsibleService:
    """
    Сервис для запуска Ansible playbook-ов через SSH с поддержкой параметров
    """
    
    # Базовые переменные, доступные для всех приложений
    BASE_VARIABLES = {
        'server': 'Имя сервера',
        'app': 'Имя приложения', 
        'app_name': 'Имя приложения (альтернатива)',
        'distr_url': 'URL артефакта/дистрибутива',
        'restart_mode': 'Режим установки/перезапуска',
        'version': 'Версия приложения',
        'environment': 'Окружение (dev/test/prod)',
        'deploy_user': 'Пользователь для деплоя',
        'deploy_path': 'Путь установки',
        'backup_enabled': 'Включить резервное копирование',
        'port': 'Порт приложения',
        'java_opts': 'Параметры JVM',
        'config_url': 'URL конфигурации',
        'log_level': 'Уровень логирования'
    }
    
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
        
        Args:
            playbook_path_with_params: Строка вида "/path/playbook.yml {param1} {param2}"
            
        Returns:
            PlaybookConfig: Конфигурация с путем и параметрами
            
        Examples:
            "/playbook.yml {server} {app}" -> PlaybookConfig(path="/playbook.yml", parameters=["server", "app"])
            "/playbook.yml" -> PlaybookConfig(path="/playbook.yml", parameters=[])
        """
        # Регулярное выражение для поиска параметров в фигурных скобках
        param_pattern = r'\{([^}]+)\}'
        
        # Находим все параметры
        parameters = re.findall(param_pattern, playbook_path_with_params)
        
        # Удаляем параметры из пути, оставляя только путь к файлу
        playbook_path = re.sub(param_pattern, '', playbook_path_with_params).strip()
        
        # Убираем лишние пробелы
        playbook_path = ' '.join(playbook_path.split())
        
        logger.info(f"Parsed playbook config: path='{playbook_path}', parameters={parameters}")
        
        return PlaybookConfig(
            path=playbook_path,
            parameters=parameters,
            extra_vars={}
        )
    
    def build_extra_vars(self, 
                        playbook_config: PlaybookConfig,
                        context_vars: Dict[str, Any]) -> Dict[str, str]:
        """
        Формирует extra_vars для ansible-playbook на основе конфигурации и контекста
        
        Args:
            playbook_config: Конфигурация playbook с параметрами
            context_vars: Словарь с доступными значениями переменных
            
        Returns:
            Dict[str, str]: Словарь extra_vars для передачи в ansible-playbook
            
        Examples:
            parameters=["server", "app"], context={"server": "web01", "app": "myapp"}
            -> {"server": "web01", "app": "myapp"}
        """
        extra_vars = {}
        
        # Обрабатываем параметры из конфигурации
        for param in playbook_config.parameters:
            # Проверяем наличие параметра в контексте
            if param in context_vars:
                value = context_vars[param]
                # Преобразуем значение в строку
                if value is not None:
                    extra_vars[param] = str(value)
                else:
                    logger.warning(f"Parameter '{param}' has None value, skipping")
            else:
                # Если параметр не найден в контексте, логируем предупреждение
                logger.warning(f"Parameter '{param}' not found in context, available: {list(context_vars.keys())}")
                # Можно использовать дефолтное значение или пустую строку
                extra_vars[param] = ""
        
        # Добавляем дополнительные переменные из конфигурации
        extra_vars.update(playbook_config.extra_vars)
        
        logger.info(f"Built extra_vars: {extra_vars}")
        
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
            # Экранируем значения для безопасной передачи через shell
            escaped_value = value.replace('"', '\\"')
            cmd.extend(['-e', f'{key}="{escaped_value}"'])
        
        # Добавляем verbose если нужно
        if verbose:
            cmd.append('-v')
        
        return cmd
    
    async def update_application(self, 
                               server_name: str, 
                               app_name: str, 
                               app_id: int, 
                               distr_url: str, 
                               restart_mode: str, 
                               playbook_path: Optional[str] = None,
                               additional_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
        """
        Запуск Ansible playbook для обновления приложения через SSH с поддержкой параметров
        
        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            distr_url: URL дистрибутива
            restart_mode: Режим рестарта ('restart' или 'immediate')
            playbook_path: Путь к playbook с параметрами (опционально)
            additional_vars: Дополнительные переменные (опционально)
        
        Returns:
            Tuple[bool, str]: (успех операции, информация о результате)
        """
        # Если путь к playbook не указан, используем playbook по умолчанию
        if not playbook_path:
            playbook_path = Config.DEFAULT_UPDATE_PLAYBOOK
        
        # Парсим конфигурацию playbook (извлекаем параметры)
        playbook_config = self.parse_playbook_config(playbook_path)
        
        # Используем путь из конфигурации (уже очищенный от параметров)
        if os.path.isabs(playbook_config.path):
            # Путь уже абсолютный
            playbook_full_path = playbook_config.path
        else:
            # Относительный путь - добавляем базовый путь Ansible
            playbook_full_path = os.path.join(self.ssh_config.ansible_path, playbook_config.path)
            
        
        # Нормализуем путь (убираем дублирования типа /etc/ansible/./update.yml)
        playbook_full_path = os.path.normpath(playbook_full_path)
        
        logger.info(f"Final playbook path: {playbook_full_path}, parameters: {playbook_config.parameters}")
        
        try:
            # Получаем ID сервера по имени
            from app.models.server import Server
            server = Server.query.filter_by(name=server_name).first()
            
            if not server:
                error_msg = f"Сервер с именем {server_name} не найден"
                logger.error(error_msg)
                return False, error_msg
            
            # Проверяем SSH-соединение
            connection_ok, connection_msg = await self.test_connection()
            if not connection_ok:
                await self._create_event(
                    event_type='update',
                    description=f"Ошибка SSH-подключения при обновлении {app_name} на {server_name}: {connection_msg}",
                    status='failed',
                    server_id=server.id,
                    application_id=app_id
                )
                return False, f"SSH-соединение не удалось: {connection_msg}"
            
            # Записываем событие о начале обновления
            await self._create_event(
                event_type='update',
                description=f"Запуск обновления приложения {app_name} на сервере {server_name}",
                status='pending',
                server_id=server.id,
                application_id=app_id
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
                    application_id=app_id
                )
                return False, error_msg
            
            # Формируем контекст переменных для подстановки
            context_vars = {
                'server': server_name,
                'app': app_name,
                'app_name': app_name,
                'distr_url': distr_url,
                'restart_mode': restart_mode,
                'server_id': str(server.id),
                'app_id': str(app_id),
                'ansible_user': self.ssh_config.user,
                'ansible_host': self.ssh_config.host
            }
            
            # Добавляем дополнительные переменные если они переданы
            if additional_vars:
                context_vars.update(additional_vars)
            
            # Получаем информацию о приложении для дополнительного контекста
            from app.models.application import Application
            app = Application.query.get(app_id)
            if app:
                context_vars['version'] = app.version or ''
                context_vars['port'] = str(app.port) if hasattr(app, 'port') else ''
                
                # Если у приложения есть instance с дополнительными настройками
                if hasattr(app, 'instance') and app.instance:
                    instance = app.instance
                    # Проверяем наличие custom_vars
                    if hasattr(instance, 'get_custom_vars'):
                        custom_vars = instance.get_custom_vars()
                    if custom_vars:
                        context_vars.update(instance.custom_vars)
            
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
                    description=f"Обновление {app_name} на {server_name} успешно завершено",
                    status='success',
                    server_id=server.id,
                    application_id=app_id
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
                    application_id=app_id
                )
                
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Исключение при обновлении {app_name} на {server_name}: {str(e)}"
            logger.error(error_msg)
            
            try:
                await self._create_event(
                    event_type='update',
                    description=f"Критическая ошибка при обновлении {app_name} на {server_name}: {str(e)}",
                    status='failed',
                    server_id=server.id if 'server' in locals() else None,
                    application_id=app_id
                )
            except:
                pass
            
            return False, error_msg
    
    async def manage_application(self, 
                               server_name: str, 
                               app_name: str, 
                               app_id: int, 
                               action: str,
                               playbook_path: Optional[str] = None,
                               additional_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
        """
        Управление состоянием приложения через SSH с поддержкой параметров
        
        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            action: Действие (start, stop, restart)
            playbook_path: Путь к playbook с параметрами (опционально)
            additional_vars: Дополнительные переменные (опционально)
        
        Returns:
            Tuple[bool, str]: (успех операции, информация о результате)
        """
        # Проверяем валидность действия
        valid_actions = ['start', 'stop', 'restart']
        if action not in valid_actions:
            error_msg = f"Недопустимое действие: {action}. Допустимые значения: {', '.join(valid_actions)}"
            logger.error(error_msg)
            return False, error_msg
        
        try:
            # Получаем ID сервера по его имени
            from app.models.server import Server
            server = Server.query.filter_by(name=server_name).first()
            
            if not server:
                error_msg = f"Сервер с именем {server_name} не найден"
                logger.error(error_msg)
                return False, error_msg
            
            # Проверяем SSH-соединение
            connection_ok, connection_msg = await self.test_connection()
            if not connection_ok:
                await self._create_event(
                    event_type=action,
                    description=f"Ошибка SSH-подключения при выполнении {action} для {app_name} на {server_name}: {connection_msg}",
                    status='failed',
                    server_id=server.id,
                    application_id=app_id
                )
                return False, f"SSH-соединение не удалось: {connection_msg}"
            
            # Записываем событие о начале операции
            await self._create_event(
                event_type=action,
                description=f"Запуск {action} для приложения {app_name} на сервере {server_name}",
                status='pending',
                server_id=server.id,
                application_id=app_id
            )
            
            # Если путь к playbook не указан, используем стандартный
            if not playbook_path:
                playbook_path = f"app_{action}.yml"
            
            # Парсим конфигурацию playbook
            playbook_config = self.parse_playbook_config(playbook_path)
            
            # Формируем полный путь к playbook
#            playbook_full_path = os.path.join(
#                self.ssh_config.ansible_path,
#                playbook_config.path.lstrip('/')
#            )
            
            # Проверяем существование playbook
            if not await self._remote_file_exists(playbook_full_path):
                error_msg = f"Ansible playbook не найден на удаленном хосте: {playbook_full_path}"
                logger.error(error_msg)
                
                await self._create_event(
                    event_type=action,
                    description=f"Ошибка {action} для {app_name} на {server_name}: {error_msg}",
                    status='failed',
                    server_id=server.id,
                    application_id=app_id
                )
                return False, error_msg
            
            # Формируем контекст переменных
            context_vars = {
                'server': server_name,
                'app': app_name,
                'app_name': app_name,
                'action': action,
                'server_id': str(server.id),
                'app_id': str(app_id)
            }
            
            # Добавляем дополнительные переменные
            if additional_vars:
                context_vars.update(additional_vars)
            
            # Формируем extra_vars
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
                ansible_cmd, server.id, app_id, app_name, server_name, action
            )
            
            if success:
                result_msg = f"{action} для приложения {app_name} на сервере {server_name} выполнен успешно"
                logger.info(result_msg)
                
                await self._create_event(
                    event_type=action,
                    description=f"{action} для {app_name} на {server_name} успешно выполнен",
                    status='success',
                    server_id=server.id,
                    application_id=app_id
                )
                
                return True, result_msg
            else:
                error_msg = f"Ошибка при выполнении {action} для {app_name} на {server_name}: {error_output}"
                logger.error(error_msg)
                
                await self._create_event(
                    event_type=action,
                    description=f"Ошибка {action} для {app_name} на {server_name}: {error_output}",
                    status='failed',
                    server_id=server.id,
                    application_id=app_id
                )
                
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Исключение при выполнении {action} для {app_name} на {server_name}: {str(e)}"
            logger.error(error_msg)
            
            try:
                await self._create_event(
                    event_type=action,
                    description=f"Критическая ошибка при выполнении {action} для {app_name} на {server_name}: {str(e)}",
                    status='failed',
                    server_id=server.id if 'server' in locals() else None,
                    application_id=app_id
                )
            except:
                pass
            
            return False, error_msg
    
    # Вспомогательные методы остаются без изменений
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
                    return True, "SSH-соединение успешно"
                else:
                    error_msg = f"SSH-соединение не удалось: {stderr.decode()}"
                    logger.error(error_msg)
                    return False, error_msg
                    
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                error_msg = "Таймаут SSH-соединения"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Ошибка при проверке SSH-соединения: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    async def _remote_file_exists(self, file_path: str) -> bool:
        """Проверяет существование файла на удаленном хосте"""
        try:
            check_cmd = f"test -f '{file_path}' && echo 'EXISTS' || echo 'NOT_EXISTS'"
            ssh_cmd = self._build_ssh_command(['bash', '-c', check_cmd])
            
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            output = stdout.decode().strip()
            exists = 'EXISTS' in output
            
            if exists:
                logger.debug(f"Файл {file_path} существует на удаленном хосте")
            else:
                logger.debug(f"Файл {file_path} не найден на удаленном хосте")
                
            return exists
            
        except Exception as e:
            logger.error(f"Ошибка при проверке существования файла {file_path}: {str(e)}")
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
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
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
                    stderr_lines.append(line_str)
                    
                    if line_str:
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
                          server_id: Optional[int] = None, application_id: Optional[int] = None):
        """Создает событие в БД"""
        try:
            event = Event(
                event_type=event_type,
                description=description,
                status=status,
                server_id=server_id,
                application_id=application_id
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
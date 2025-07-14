import asyncio
import logging
import os
import tempfile
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
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

class SSHAnsibleService:
    """
    Сервис для запуска Ansible playbook-ов через SSH
    """
    
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
    
    async def test_connection(self) -> Tuple[bool, str]:
        """
        Проверка SSH-соединения с хостом
        
        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
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
    
    def _build_ssh_command(self, remote_command: list) -> list:
        """
        Создает команду SSH с необходимыми параметрами
        
        Args:
            remote_command: Команда для выполнения на удаленном хосте
            
        Returns:
            list: Полная команда SSH
        """
        ssh_cmd = [
            'ssh',
            '-o', 'BatchMode=yes',  # Отключить интерактивные запросы
            '-o', f'ConnectTimeout={self.ssh_config.connection_timeout}',
            '-o', 'StrictHostKeyChecking=no',  # Можно изменить на yes для большей безопасности
        ]
        
        if self.ssh_config.key_file:
            ssh_cmd.extend(['-i', self.ssh_config.key_file])
            
        if self.ssh_config.port != 22:
            ssh_cmd.extend(['-p', str(self.ssh_config.port)])
            
        if self.ssh_config.known_hosts_file:
            ssh_cmd.extend(['-o', f'UserKnownHostsFile={self.ssh_config.known_hosts_file}'])
        
        # Добавляем хост и команду
        ssh_cmd.append(f'{self.ssh_config.user}@{self.ssh_config.host}')
        
        # Объединяем удаленную команду в одну строку
        ssh_cmd.append(' '.join(remote_command))
        
        return ssh_cmd
    
    def _parse_ansible_output(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Парсит вывод Ansible для отслеживания этапов
        
        Args:
            line: Строка вывода Ansible
            
        Returns:
            Dict с информацией об этапе или None
        """
        line = line.strip()
        
        # Определяем этапы выполнения
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
    
    async def update_application(self, server_name: str, app_name: str, app_id: int, 
                               distr_url: str, restart_mode: str, 
                               playbook_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Запуск Ansible playbook для обновления приложения через SSH
        
        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            distr_url: URL дистрибутива
            restart_mode: Режим рестарта ('restart' или 'immediate')
            playbook_path: Путь к playbook (опционально)
        
        Returns:
            Tuple[bool, str]: (успех операции, информация о результате)
        """
        # Если путь к playbook не указан, используем playbook по умолчанию
        if not playbook_path:
            playbook_path = Config.DEFAULT_UPDATE_PLAYBOOK
        
        # Проверяем, что playbook существует на удаленном хосте
        playbook_full_path = os.path.join(self.ssh_config.ansible_path, playbook_path.lstrip('/'))
        
        try:
            # Получаем ID сервера по имени
            from app.models.server import Server
            server = Server.query.filter_by(name=server_name).first()
            
            if not server:
                return False, f"Сервер с именем {server_name} не найден"
            
            # Проверяем SSH-соединение
            connection_ok, connection_msg = await self.test_connection()
            if not connection_ok:
                # Записываем событие об ошибке подключения
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
            check_cmd = ['test', '-f', playbook_full_path]
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
            
            # Формируем команду для запуска Ansible на удаленном хосте
            ansible_cmd = [
                'cd', self.ssh_config.ansible_path, '&&',
                'ansible-playbook',
                playbook_full_path,
                '-e', f'server={server_name}',
                '-e', f'app_name={app_name}',
                '-e', f'distr_url={distr_url}',
                '-e', f'restart_mode={restart_mode}',
                '-v'  # Verbose output для отслеживания этапов
            ]
            
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
                pass  # Избегаем вложенных исключений
            
            return False, error_msg
    
    async def manage_application(self, server_name: str, app_name: str, app_id: int, 
                               action: str) -> Tuple[bool, str]:
        """
        Управление состоянием приложения через SSH (запуск, остановка, перезапуск)
        
        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            action: Действие (start, stop, restart)
        
        Returns:
            Tuple[bool, str]: (успех операции, информация о результате)
        """
        # Проверяем корректность действия
        valid_actions = ['start', 'stop', 'restart']
        if action not in valid_actions:
            error_msg = f"Некорректное действие: {action}. Допустимые значения: {', '.join(valid_actions)}"
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
            
            # Формируем путь к playbook
            playbook_path = os.path.join(self.ssh_config.ansible_path, f"app_{action}.yml")
            
            # Проверяем существование playbook
            if not await self._remote_file_exists(playbook_path):
                error_msg = f"Ansible playbook не найден на удаленном хосте: {playbook_path}"
                logger.error(error_msg)
                
                await self._create_event(
                    event_type=action,
                    description=f"Ошибка {action} для {app_name} на {server_name}: {error_msg}",
                    status='failed',
                    server_id=server.id,
                    application_id=app_id
                )
                return False, error_msg
            
            # Формируем команду для запуска Ansible
            ansible_cmd = [
                'cd', self.ssh_config.ansible_path, '&&',
                'ansible-playbook',
                playbook_path,
                '-e', f'server={server_name}',
                '-e', f'app_name={app_name}',
                '-v'
            ]
            
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
    
    async def _remote_file_exists(self, file_path: str) -> bool:
        """
        Проверяет существование файла на удаленном хосте
        
        Args:
            file_path: Путь к файлу на удаленном хосте
            
        Returns:
            bool: True, если файл существует
        """
        try:
            check_cmd = ['test', '-f', file_path]
            ssh_cmd = self._build_ssh_command(check_cmd)
            
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Ошибка при проверке существования файла {file_path}: {str(e)}")
            return False
    
    async def _execute_ansible_command(self, ansible_cmd: list, server_id: int, app_id: int,
                                     app_name: str, server_name: str, action: str) -> Tuple[bool, str, str]:
        """
        Выполняет команду Ansible через SSH с отслеживанием этапов
        
        Args:
            ansible_cmd: Команда Ansible для выполнения
            server_id: ID сервера
            app_id: ID приложения
            app_name: Имя приложения
            server_name: Имя сервера
            action: Действие
            
        Returns:
            Tuple[bool, str, str]: (успех, stdout, stderr)
        """
        ssh_cmd = self._build_ssh_command(ansible_cmd)
        
        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Отслеживаем вывод в реальном времени
            stdout_lines = []
            stderr_lines = []
            
            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    stdout_lines.append(line_str)
                    
                    # Парсим вывод для отслеживания этапов
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
                    
                    # Логируем ошибки
                    if line_str:
                        logger.warning(f"Ansible stderr: {line_str}")
            
            # Запускаем чтение stdout и stderr параллельно
            await asyncio.gather(
                read_stdout(),
                read_stderr()
            )
            
            # Ждем завершения процесса с таймаутом
            try:
                await asyncio.wait_for(process.wait(), timeout=self.ssh_config.command_timeout)
            except asyncio.TimeoutError:
                logger.error(f"Таймаут выполнения команды Ansible для {app_name}")
                process.kill()
                await process.wait()
                return False, '\n'.join(stdout_lines), f"Таймаут выполнения команды (>{self.ssh_config.command_timeout}s)"
            
            stdout_text = '\n'.join(stdout_lines)
            stderr_text = '\n'.join(stderr_lines)
            
            # Логируем результат
            logger.info(f"Ansible {action} для {app_name} завершен с кодом: {process.returncode}")
            
            return process.returncode == 0, stdout_text, stderr_text
            
        except Exception as e:
            error_msg = f"Исключение при выполнении SSH-команды: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg
    
    async def _create_event(self, event_type: str, description: str, status: str,
                          server_id: Optional[int], application_id: Optional[int]):
        """
        Создает событие в базе данных
        
        Args:
            event_type: Тип события
            description: Описание события
            status: Статус события
            server_id: ID сервера
            application_id: ID приложения
        """
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
            try:
                db.session.rollback()
            except:
                pass


# Глобальный экземпляр сервиса
ssh_ansible_service = None

def get_ssh_ansible_service() -> SSHAnsibleService:
    """Возвращает глобальный экземпляр SSH Ansible сервиса"""
    global ssh_ansible_service
    if ssh_ansible_service is None:
        ssh_ansible_service = SSHAnsibleService.from_config()
    return ssh_ansible_service    
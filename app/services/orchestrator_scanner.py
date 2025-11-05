# app/services/orchestrator_scanner.py
"""
Сервис для сканирования удаленного каталога на наличие orchestrator playbooks
через SSH и регистрации их в базе данных.
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from app import db
from app.models import OrchestratorPlaybook
from app.config import Config
from app.services.orchestrator_parser import parse_orchestrator_metadata, validate_metadata

logger = logging.getLogger(__name__)


class OrchestratorScanner:
    """
    Сканер orchestrator playbooks через SSH.
    Работает аналогично SSHAnsibleService - подключается к удаленному хосту.
    """

    def __init__(self, ssh_config: Dict[str, any]):
        """
        Args:
            ssh_config: словарь с SSH настройками
                - host: хост для подключения
                - user: пользователь SSH
                - port: порт SSH
                - key_file: путь к SSH ключу (опционально)
                - ansible_path: путь к каталогу с playbook-ами на удаленном хосте
                - scan_pattern: паттерн для поиска orchestrator playbooks
        """
        self.ssh_config = ssh_config
        self.host = ssh_config.get('host', 'localhost')
        self.user = ssh_config.get('user', 'ansible')
        self.port = ssh_config.get('port', 22)
        self.key_file = ssh_config.get('key_file')
        self.ansible_path = ssh_config.get('ansible_path', '/etc/ansible')
        self.scan_pattern = ssh_config.get('scan_pattern', '*orchestrator*.yml')
        self.connection_timeout = ssh_config.get('connection_timeout', 30)

    def _build_ssh_command(self, remote_command: list) -> list:
        """
        Формирует SSH команду для выполнения на удаленном хосте.
        Аналог метода из SSHAnsibleService.

        Args:
            remote_command: список элементов команды для выполнения

        Returns:
            список элементов SSH команды
        """
        ssh_cmd = ['ssh']

        if self.key_file:
            ssh_cmd.extend(['-i', self.key_file])

        ssh_cmd.extend([
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', f'ConnectTimeout={self.connection_timeout}',
            '-p', str(self.port),
            f'{self.user}@{self.host}'
        ])

        # Если remote_command это список с bash -c, передаем как есть
        if isinstance(remote_command, list) and len(remote_command) == 3 and remote_command[1] == '-c':
            ssh_cmd.extend(remote_command)
        else:
            # Иначе объединяем в одну команду
            ssh_cmd.append(' '.join(str(cmd) for cmd in remote_command))

        return ssh_cmd

    async def _execute_ssh_command(self, command: list) -> Tuple[bool, str, str]:
        """
        Выполняет SSH команду асинхронно.

        Args:
            command: список элементов команды

        Returns:
            (success, stdout, stderr)
        """
        ssh_cmd = self._build_ssh_command(command)

        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.connection_timeout
                )

                stdout_str = stdout.decode('utf-8', errors='ignore')
                stderr_str = stderr.decode('utf-8', errors='ignore')

                success = process.returncode == 0
                return success, stdout_str, stderr_str

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return False, "", "SSH command timeout"

        except Exception as e:
            logger.error(f"Exception executing SSH command: {e}")
            return False, "", str(e)

    async def find_orchestrator_files(self) -> List[str]:
        """
        Находит все orchestrator playbook файлы на удаленном хосте.

        Returns:
            список имен файлов
        """
        logger.info(f"Searching for orchestrator playbooks on {self.host}:{self.ansible_path}")
        logger.info(f"Using pattern: {self.scan_pattern}")

        # Используем find вместо ls для более надежного поиска
        # find ищет файлы с именем содержащим "orchestrator" и расширением .yml или .yaml
        # Используем exec basename для совместимости (вместо -printf)
        bash_cmd = (
            f"cd {self.ansible_path} && "
            f"find . -maxdepth 1 -type f "
            f"\\( -name '*orchestrator*.yml' -o -name '*orchestrator*.yaml' \\) "
            f"-exec basename {{}} \\; 2>/dev/null || true"
        )

        logger.info(f"Executing find command: {bash_cmd}")

        # Важно: bash_cmd нужно обернуть в двойные кавычки как в ssh_ansible_service
        success, stdout, stderr = await self._execute_ssh_command(['bash', '-c', f'"{bash_cmd}"'])

        logger.info(f"Find command result - success: {success}, stdout length: {len(stdout)}, stderr: '{stderr}'")
        logger.info(f"Find stdout: '{stdout[:200]}'")  # Первые 200 символов

        if not success:
            logger.error(f"Failed to list orchestrator files: {stderr}")
            return []

        if not stdout.strip():
            logger.warning(f"No orchestrator playbooks found matching pattern '{self.scan_pattern}'")
            logger.info("Trying to list all files in directory for debugging...")

            # Для отладки - показать все файлы в каталоге
            debug_cmd = f"ls -1 {self.ansible_path}"
            logger.info(f"Debug command: {debug_cmd}")
            debug_success, debug_stdout, debug_stderr = await self._execute_ssh_command(['bash', '-c', f'"{debug_cmd}"'])
            logger.info(f"Debug success: {debug_success}, stdout length: {len(debug_stdout)}, stderr: {debug_stderr}")

            if debug_success and debug_stdout:
                files = [f for f in debug_stdout.strip().split('\n') if f.strip()]
                logger.info(f"All files in {self.ansible_path}: {files}")
            else:
                logger.error(f"Failed to list directory. stdout: '{debug_stdout}', stderr: '{debug_stderr}'")

            return []

        # Парсим список файлов
        file_list = stdout.strip().split('\n')
        file_list = [f.strip() for f in file_list if f.strip() and not f.startswith('find:')]

        logger.info(f"Found {len(file_list)} orchestrator playbook files: {file_list}")

        return file_list

    async def read_file_content(self, filename: str) -> str:
        """
        Читает содержимое файла с удаленного хоста.

        Args:
            filename: имя файла (без пути)

        Returns:
            содержимое файла или пустая строка при ошибке
        """
        file_path = os.path.join(self.ansible_path, filename)

        # Команда для чтения файла
        bash_cmd = f"cat {file_path}"

        success, stdout, stderr = await self._execute_ssh_command(['bash', '-c', f'"{bash_cmd}"'])

        if not success:
            logger.error(f"Failed to read file {file_path}: {stderr}")
            return ""

        return stdout

    async def scan_orchestrators_async(self, force=True) -> Dict:
        """
        Асинхронное сканирование orchestrator playbooks.

        Args:
            force: всегда обновлять записи (игнорировать mtime)

        Returns:
            dict с результатами сканирования
        """
        logger.info("Starting orchestrator playbooks scan via SSH")

        results = {
            'scanned': 0,
            'new': 0,
            'updated': 0,
            'errors': []
        }

        try:
            # Найти файлы на удаленном хосте
            files = await self.find_orchestrator_files()

            if not files:
                logger.warning("No orchestrator playbooks found")
                return results

            # Обработать каждый файл
            for filename in files:
                results['scanned'] += 1

                try:
                    # Прочитать содержимое файла
                    logger.debug(f"Reading file: {filename}")
                    content = await self.read_file_content(filename)

                    if not content:
                        logger.warning(f"Empty content for {filename}, skipping")
                        results['errors'].append({
                            'file': filename,
                            'error': 'Empty file content'
                        })
                        continue

                    # Парсить метаданные
                    logger.debug(f"Parsing metadata from {filename}")
                    metadata = parse_orchestrator_metadata(content, filename)

                    if not validate_metadata(metadata):
                        logger.warning(f"Invalid metadata in {filename}, skipping")
                        results['errors'].append({
                            'file': filename,
                            'error': 'Invalid metadata structure'
                        })
                        continue

                    # Формируем полный путь для хранения в БД
                    file_path = os.path.join(self.ansible_path, filename)

                    # Поиск существующей записи по пути
                    existing = OrchestratorPlaybook.query.filter_by(
                        file_path=file_path
                    ).first()

                    if existing:
                        # Обновить существующую запись
                        update_orchestrator_playbook(existing, metadata)
                        results['updated'] += 1
                        logger.info(f"Updated orchestrator playbook: {metadata['name']} ({filename})")
                    else:
                        # Создать новую запись
                        create_orchestrator_playbook(file_path, metadata)
                        results['new'] += 1
                        logger.info(f"Created new orchestrator playbook: {metadata['name']} ({filename})")

                except Exception as e:
                    logger.error(f"Error processing {filename}: {e}", exc_info=True)
                    results['errors'].append({
                        'file': filename,
                        'error': str(e)
                    })

            # Commit изменений в БД
            try:
                db.session.commit()
                logger.info(f"Scan completed: {results['new']} new, {results['updated']} updated, "
                           f"{len(results['errors'])} errors")
            except Exception as e:
                logger.error(f"Failed to commit changes: {e}")
                db.session.rollback()
                results['errors'].append({
                    'file': 'database',
                    'error': f'Commit failed: {str(e)}'
                })

        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
            results['errors'].append({
                'file': 'scan',
                'error': str(e)
            })

        return results


def create_orchestrator_playbook(file_path, metadata):
    """
    Создает новую запись OrchestratorPlaybook в БД.

    Args:
        file_path: полный путь к файлу playbook на удаленном хосте
        metadata: словарь с метаданными
    """
    playbook = OrchestratorPlaybook(
        file_path=file_path,
        name=metadata['name'],
        description=metadata.get('description'),
        version=metadata.get('version'),
        required_params=metadata.get('required_params', {}),
        optional_params=metadata.get('optional_params', {}),
        is_active=True,
        last_scanned=datetime.utcnow(),
        raw_metadata=metadata.get('raw_metadata')
    )

    db.session.add(playbook)
    logger.debug(f"Created OrchestratorPlaybook: {playbook}")


def update_orchestrator_playbook(playbook, metadata):
    """
    Обновляет существующую запись OrchestratorPlaybook.

    Args:
        playbook: экземпляр OrchestratorPlaybook
        metadata: словарь с новыми метаданными
    """
    playbook.name = metadata['name']
    playbook.description = metadata.get('description')
    playbook.version = metadata.get('version')
    playbook.required_params = metadata.get('required_params', {})
    playbook.optional_params = metadata.get('optional_params', {})
    playbook.last_scanned = datetime.utcnow()
    playbook.raw_metadata = metadata.get('raw_metadata')

    # is_active не обновляем - пользователь мог его изменить вручную

    logger.debug(f"Updated OrchestratorPlaybook: {playbook}")


def get_orchestrator_by_id(orchestrator_id):
    """
    Получает orchestrator playbook по ID.

    Args:
        orchestrator_id: ID записи

    Returns:
        OrchestratorPlaybook или None
    """
    return OrchestratorPlaybook.query.get(orchestrator_id)


def get_all_orchestrators(active_only=False):
    """
    Получает список всех orchestrator playbooks.

    Args:
        active_only: если True, возвращает только активные

    Returns:
        список OrchestratorPlaybook
    """
    query = OrchestratorPlaybook.query

    if active_only:
        query = query.filter_by(is_active=True)

    return query.order_by(OrchestratorPlaybook.name).all()


def toggle_orchestrator_status(orchestrator_id):
    """
    Переключает статус активности orchestrator playbook.

    Args:
        orchestrator_id: ID записи

    Returns:
        обновленный OrchestratorPlaybook или None
    """
    playbook = OrchestratorPlaybook.query.get(orchestrator_id)

    if not playbook:
        return None

    playbook.is_active = not playbook.is_active
    db.session.commit()

    logger.info(f"Toggled orchestrator {playbook.name} status to {playbook.is_active}")

    return playbook


def scan_orchestrators(force=True):
    """
    Синхронная обертка для асинхронного сканирования.
    Используется при старте приложения и в API endpoints.

    Args:
        force: всегда обновлять записи (игнорировать mtime)

    Returns:
        dict с результатами сканирования
    """
    # Формируем SSH конфигурацию из Config
    ssh_config = {
        'host': getattr(Config, 'SSH_HOST', 'localhost'),
        'user': getattr(Config, 'SSH_USER', 'ansible'),
        'port': getattr(Config, 'SSH_PORT', 22),
        'key_file': getattr(Config, 'SSH_KEY_FILE', None),
        'ansible_path': getattr(Config, 'ANSIBLE_PATH', '/etc/ansible'),
        'scan_pattern': getattr(Config, 'ORCHESTRATOR_SCAN_PATTERN', '*orchestrator*.yml'),
        'connection_timeout': getattr(Config, 'SSH_CONNECTION_TIMEOUT', 30)
    }

    scanner = OrchestratorScanner(ssh_config)

    # Запуск асинхронной функции в синхронном контексте
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(scanner.scan_orchestrators_async(force=force))

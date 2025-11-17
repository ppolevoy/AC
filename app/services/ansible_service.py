import subprocess
import logging
import os
from datetime import datetime
from app import db
from app.models.event import Event
from app.config import Config

logger = logging.getLogger(__name__)

class AnsibleService:
    """
    Сервис для запуска Ansible плейбуков
    Поддерживает как локальный запуск, так и выполнение через SSH
    """
    
    @staticmethod
    async def update_application(server_name, app_name, app_id, distr_url, mode, playbook_path=None):
        """
        Запуск Ansible плейбука для обновления приложения

        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            distr_url: URL дистрибутива
            mode: Режим обновления (deliver, immediate, night-restart)
            playbook_path: Путь к плейбуку Ansible (опционально)

        Returns:
            tuple: (успех операции (bool), информация о результате (str))
        """
        # Проверяем, нужно ли использовать SSH
        if getattr(Config, 'USE_SSH_ANSIBLE', False):
            logger.info(f"Использование SSH для выполнения Ansible playbook: {app_name}")

            # Импортируем SSH-сервис
            from app.services.ssh_ansible_service import get_ssh_ansible_service
            ssh_service = get_ssh_ansible_service()

            return await ssh_service.update_application(
                server_name, app_name, app_id, distr_url, mode, playbook_path
            )
        else:
            logger.info(f"Использование локального выполнения Ansible playbook: {app_name}")

            # Используем старый подход с локальным выполнением
            return await AnsibleService._local_update_application(
                server_name, app_name, app_id, distr_url, mode, playbook_path
            )
    
    @staticmethod
    async def manage_application(server_name, app_name, app_id, action):
        """
        Управление состоянием приложения (запуск, остановка, перезапуск)
        
        Args:
            server_name: Имя сервера
            app_name: Имя приложения
            app_id: ID приложения в БД
            action: Действие (start, stop, restart)
        
        Returns:
            tuple: (успех операции (bool), информация о результате (str))
        """
        # Проверяем, нужно ли использовать SSH
        if getattr(Config, 'USE_SSH_ANSIBLE', False):
            logger.info(f"Использование SSH для управления приложением: {app_name}, действие: {action}")
            
            # Импортируем SSH-сервис
            from app.services.ssh_ansible_service import get_ssh_ansible_service
            ssh_service = get_ssh_ansible_service()
            
            return await ssh_service.manage_application(
                server_name, app_name, app_id, action
            )
        else:
            logger.info(f"Использование локального выполнения для управления приложением: {app_name}, действие: {action}")
            
            # Используем старый подход с локальным выполнением
            return await AnsibleService._local_manage_application(
                server_name, app_name, app_id, action
            )
    
    @staticmethod
    async def _local_update_application(server_name, app_name, app_id, distr_url, mode, playbook_path=None):
        """
        Локальное выполнение Ansible плейбука для обновления приложения
        """
        # Если путь к плейбуку не указан, используем плейбук по умолчанию
        if not playbook_path:
            playbook_path = Config.DEFAULT_UPDATE_PLAYBOOK
        
        # Проверяем существование плейбука
        if not os.path.exists(playbook_path):
            error_msg = f"Ansible playbook не найден по пути: {playbook_path}"
            logger.error(error_msg)
            
            # Получаем ID сервера по имени
            from app.models.server import Server
            server = Server.query.filter_by(name=server_name).first()
            
            if not server:
                return False, f"Сервер с именем {server_name} не найден"
            
            # Записываем событие в БД
            event = Event(
                event_type='update',
                description=f"Ошибка обновления приложения {app_name} на сервере {server_name}: {error_msg}",
                status='failed',
                server_id=server.id,
                instance_id=app_id
            )
            db.session.add(event)
            db.session.commit()
            
            return False, error_msg
        
        try:
            # Получаем ID сервера по имени
            from app.models.server import Server
            server = Server.query.filter_by(name=server_name).first()
            
            if not server:
                return False, f"Сервер с именем {server_name} не найден"
            
            # Записываем событие о начале обновления
            event = Event(
                event_type='update',
                description=f"Запуск обновления приложения {app_name} на сервере {server_name}",
                status='pending',
                server_id=server.id,
                instance_id=app_id
            )
            db.session.add(event)
            db.session.commit()
            
            # Формируем команду для запуска Ansible
            cmd = [
                'ansible-playbook',
                playbook_path,
                '-e', f"server={server_name}",
                '-e', f"app_name={app_name}",
                '-e', f"distr_url={distr_url}",
                '-e', f"mode={mode}"
            ]
            
            logger.info(f"Запуск Ansible: {' '.join(cmd)}")
            
            # Запускаем процесс Ansible
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Получаем вывод процесса
            stdout, stderr = process.communicate()
            
            # Проверяем результат выполнения
            if process.returncode == 0:
                result_msg = f"Обновление приложения {app_name} на сервере {server_name} выполнено успешно"
                logger.info(result_msg)
                
                # Обновляем статус события
                event.status = 'success'
                event.description = f"{event.description}\nРезультат: {result_msg}"
                db.session.commit()
                
                return True, result_msg
            else:
                error_msg = f"Ошибка при обновлении приложения {app_name} на сервере {server_name}: {stderr}"
                logger.error(error_msg)
                
                # Обновляем статус события
                event.status = 'failed'
                event.description = f"{event.description}\nОшибка: {error_msg}"
                db.session.commit()
                
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Исключение при обновлении приложения {app_name} на сервере {server_name}: {str(e)}"
            logger.error(error_msg)
            
            # Обновляем статус события, если оно было создано
            if 'event' in locals():
                event.status = 'failed'
                event.description = f"{event.description}\nИсключение: {error_msg}"
                db.session.commit()
            
            return False, error_msg
    
    @staticmethod
    async def _local_manage_application(server_name, app_name, app_id, action):
        """
        Локальное управление состоянием приложения (запуск, остановка, перезапуск)
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
                
            # Записываем событие о начале операции
            event = Event(
                event_type=action,
                description=f"Запуск {action} для приложения {app_name} на сервере {server_name}",
                status='pending',
                server_id=server.id,
                instance_id=app_id
            )
            db.session.add(event)
            db.session.commit()
            
            # Формируем команду для запуска Ansible
            playbook_path = os.path.join(Config.ANSIBLE_DIR, f"app_{action}.yml")
            
            # Проверяем существование плейбука
            if not os.path.exists(playbook_path):
                error_msg = f"Ansible playbook не найден по пути: {playbook_path}"
                logger.error(error_msg)
                
                # Обновляем статус события
                event.status = 'failed'
                event.description = f"{event.description}\nОшибка: {error_msg}"
                db.session.commit()
                
                return False, error_msg
            
            cmd = [
                'ansible-playbook',
                playbook_path,
                '-e', f"server={server_name}",
                '-e', f"app_name={app_name}"
            ]
            
            logger.info(f"Запуск Ansible: {' '.join(cmd)}")
            
            # Запускаем процесс Ansible
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Получаем вывод процесса
            stdout, stderr = process.communicate()
            
            # Проверяем результат выполнения
            if process.returncode == 0:
                result_msg = f"{action} для приложения {app_name} на сервере {server_name} выполнен успешно"
                logger.info(result_msg)
                
                # Обновляем статус события
                event.status = 'success'
                event.description = f"{event.description}\nРезультат: {result_msg}"
                db.session.commit()
                
                return True, result_msg
            else:
                error_msg = f"Ошибка при выполнении {action} для приложения {app_name} на сервере {server_name}: {stderr}"
                logger.error(error_msg)
                
                # Обновляем статус события
                event.status = 'failed'
                event.description = f"{event.description}\nОшибка: {error_msg}"
                db.session.commit()
                
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Исключение при выполнении {action} для приложения {app_name} на сервере {server_name}: {str(e)}"
            logger.error(error_msg)
            
            # Обновляем статус события, если оно было создано
            if 'event' in locals() and event:
                event.status = 'failed'
                event.description = f"{event.description}\nИсключение: {error_msg}"
                db.session.commit()
            
            return False, error_msg
    
    @staticmethod
    async def test_ssh_connection():
        """
        Тестирование SSH-соединения (доступно только в SSH-режиме)
        
        Returns:
            tuple: (успех соединения (bool), сообщение (str))
        """
        if not getattr(Config, 'USE_SSH_ANSIBLE', False):
            return False, "SSH-режим отключен в конфигурации"
        
        try:
            from app.services.ssh_ansible_service import get_ssh_ansible_service
            ssh_service = get_ssh_ansible_service()
            
            return await ssh_service.test_connection()
        except Exception as e:
            error_msg = f"Ошибка при тестировании SSH-соединения: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
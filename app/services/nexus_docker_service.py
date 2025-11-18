import logging
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import aiohttp
import asyncio
from datetime import datetime
import re
from typing import Tuple

from app.models.application_group import ApplicationGroup
from app.models.application_instance import ApplicationInstance

logger = logging.getLogger(__name__)


@dataclass
class DockerImage:
    """
    Класс для хранения информации о Docker образе
    """
    registry_url: str  # URL реестра (например: nexus.bankplus.ru)
    repository: str  # Репозиторий (например: docker-prod-local/fcloud/acquiring-api)
    tag: str  # Тег образа (например: 0.2.1)
    digest: Optional[str] = None  # SHA256 digest образа
    created: Optional[datetime] = None  # Время создания образа
    size: Optional[int] = None  # Размер образа в байтах
    is_dev: bool = False  # Флаг dev версии
    is_snapshot: bool = False  # Флаг snapshot версии
    
    @property
    def full_image_name(self) -> str:
        """Полное имя образа для Docker (например: nexus.bankplus.ru/docker-prod-local/fcloud/acquiring-api:0.2.1)"""
        return f"{self.registry_url}/{self.repository}:{self.tag}"
    
    @property
    def display_name(self) -> str:
        """Отображаемое имя (например: acquiring-api:0.2.1)"""
        # Извлекаем имя приложения из repository
        app_name = self.repository.split('/')[-1]
        return f"{app_name}:{self.tag}"
    
    def to_dict(self) -> dict:
        """Преобразование в словарь для сериализации"""
        return {
            'registry_url': self.registry_url,
            'repository': self.repository,
            'tag': self.tag,
            'digest': self.digest,
            'created': self.created.isoformat() if self.created else None,
            'size': self.size,
            'is_dev': self.is_dev,
            'is_snapshot': self.is_snapshot,
            'full_image_name': self.full_image_name,
            'display_name': self.display_name
        }


class NexusDockerService:
    """
    Сервис для работы с Nexus Docker Registry API v2
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session = None
    
    async def __aenter__(self):
        """Асинхронный вход в контекстный менеджер"""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный выход из контекстного менеджера"""
        if self.session:
            await self.session.close()
    
    def parse_docker_url(self, artifact_url: str) -> tuple[str, str, str]:
        """
        Парсинг URL Docker Registry для извлечения компонентов.
        
        Args:
            artifact_url: URL вида https://nexus.bankplus.ru/repository/docker-local/v2/docker-prod-local/fcloud/acquiring-api
            
        Returns:
            tuple: (registry_url, docker_repo_path, app_name)
            Например: ('nexus.bankplus.ru', 'docker-prod-local/fcloud/acquiring-api', 'acquiring-api')
        """
        # Убираем протокол и путь до /v2/
        parsed = urlparse(artifact_url)
        registry_url = parsed.hostname
        
        # Извлекаем путь после /v2/
        path_parts = parsed.path.split('/v2/')
        if len(path_parts) > 1:
            docker_path = path_parts[1]
        else:
            # Возможно URL уже без /repository/docker-local/v2/
            docker_path = parsed.path.lstrip('/')
        
        # Имя приложения - последняя часть пути
        app_name = docker_path.split('/')[-1]
        
        logger.debug(f"Parsed Docker URL: registry={registry_url}, path={docker_path}, app={app_name}")
        
        return registry_url, docker_path, app_name
    
    async def get_tags(self, artifact_url: str) -> List[str]:
        """
        Получение списка тегов для Docker образа через Nexus API.
        
        Args:
            artifact_url: URL к Docker репозиторию
            
        Returns:
            Список тегов
        """
        try:
            # Парсим URL
            registry_url, docker_path, app_name = self.parse_docker_url(artifact_url)
            
            # Формируем URL для получения списка тегов
            # https://nexus.bankplus.ru/repository/docker-local/v2/{repository}/tags/list
            if '/v2/' in artifact_url:
                base_url = artifact_url.split('/v2/')[0]
                tags_url = f"{base_url}/v2/{docker_path}/tags/list"
            else:
                tags_url = f"https://{registry_url}/repository/docker-local/v2/{docker_path}/tags/list"
            
            logger.info(f"Запрос списка тегов: {tags_url}")
            
            async with self.session.get(tags_url) as response:
                if response.status == 200:
                    data = await response.json()
                    tags = data.get('tags', [])
                    logger.info(f"Получено {len(tags)} тегов для {app_name}")
                    return tags
                else:
                    logger.error(f"Ошибка получения тегов: HTTP {response.status}")
                    text = await response.text()
                    logger.error(f"Ответ сервера: {text}")
                    return []
                    
        except Exception as e:
            logger.error(f"Ошибка при получении тегов Docker образа: {str(e)}")
            return []
    
    async def get_manifest(self, artifact_url: str, tag: str) -> Optional[Dict[str, Any]]:
        """
        Получение манифеста Docker образа для извлечения метаданных.
        
        Args:
            artifact_url: URL к Docker репозиторию
            tag: Тег образа
            
        Returns:
            Манифест образа или None
        """
        try:
            registry_url, docker_path, app_name = self.parse_docker_url(artifact_url)
            
            # Формируем URL для получения манифеста
            if '/v2/' in artifact_url:
                base_url = artifact_url.split('/v2/')[0]
                manifest_url = f"{base_url}/v2/{docker_path}/manifests/{tag}"
            else:
                manifest_url = f"https://{registry_url}/repository/docker-local/v2/{docker_path}/manifests/{tag}"
            
            headers = {
                'Accept': 'application/vnd.docker.distribution.manifest.v2+json'
            }
            
            async with self.session.get(manifest_url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.debug(f"Не удалось получить манифест для {tag}: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            logger.debug(f"Ошибка при получении манифеста: {str(e)}")
            return None

    def parse_tag_version(self, tag: str) -> Tuple[Tuple[int, ...], str, bool, bool]:
        """
        Парсинг тега Docker образа для правильной сортировки.
        
        Разбивает тег на числовые части для корректного сравнения.
        Например: "0.2.1-SNAPSHOT" -> ((0, 2, 1), "snapshot", True, False)
        
        Args:
            tag: Тег Docker образа (например: "0.2.1", "1.0.0-dev", "latest")
            
        Returns:
            Кортеж: (числовые_части, суффикс, is_snapshot, is_special)
        """
        # Особые случаи
        if tag == 'latest':
            # latest всегда должен быть первым
            return ((999999, 999999, 999999, 999999), '', False, False)
        
        # Разделяем основную версию и суффикс
        # Поддерживаем форматы: X.Y.Z, X.Y.Z-suffix, X.Y, X.Y.Z.W и т.д.
        match = re.match(r'^v?([\d.]+)(-.*)?$', tag, re.IGNORECASE)
        if not match:
            # Если формат тега нестандартный
            return ((0, 0, 0, 0), tag.lower(), self.is_snapshot_tag(tag), True)
        
        main_version = match.group(1)
        suffix = match.group(2) or ''
        
        # Парсим числовые части основной версии
        try:
            parts = tuple(int(p) for p in main_version.split('.') if p.isdigit())
            if not parts:
                parts = (0,)
        except (ValueError, AttributeError):
            parts = (0,)
        
        # Дополняем нулями до 4 частей для корректного сравнения
        # (major, minor, patch, build)
        parts = parts[:4] + (0,) * (4 - min(len(parts), 4))
        
        # Определяем тип версии
        is_snapshot = self.is_snapshot_tag(tag)
        is_dev = self.is_dev_tag(tag)
        is_special = bool(suffix) and not is_snapshot and not is_dev
        
        return (parts, suffix.lower(), is_snapshot, is_special)

    def is_dev_tag(self, tag: str) -> bool:
        """Проверка, является ли тег dev версией"""
        tag_lower = tag.lower()
        # Расширенная проверка для dev версий
        dev_patterns = ['dev', 'develop', 'development', '-dev', '.dev']
        return any(pattern in tag_lower for pattern in dev_patterns)
    
    def is_snapshot_tag(self, tag: str) -> bool:
        """Проверка, является ли тег snapshot версией"""
        tag_lower = tag.lower()
        # Расширенная проверка для snapshot версий
        snapshot_patterns = ['snapshot', 'snap', '-snapshot', '.snapshot']
        return any(pattern in tag_lower for pattern in snapshot_patterns)
    
    def sort_tags(self, tags: List[str]) -> List[str]:
        """
        сортировка тегов Docker образов.
        
        Приоритеты:
        1. latest (всегда первый)
        2. Релизные версии (чистые числовые версии)
        3. Dev версии
        4. Snapshot версии
        5. Прочие версии со специальными суффиксами
        
        Внутри каждой категории - сортировка по числовым частям версии (от новых к старым)
        
        Args:
            tags: Список тегов
            
        Returns:
            Отсортированный список тегов
        """
        def tag_sort_key(tag):
            parsed = self.parse_tag_version(tag)
            version_parts, suffix, is_snapshot, is_special = parsed
            
            # Приоритет категории
            if tag == 'latest':
                priority = 0
            elif re.match(r'^v?\d+\.\d+(\.\d+)?(\.\d+)?$', tag, re.IGNORECASE):
                # Чистые релизные версии (например: 1.0.0, v2.3.4)
                priority = 1
            elif self.is_dev_tag(tag):
                priority = 2
            elif is_snapshot:
                priority = 3
            elif is_special:
                priority = 4
            else:
                priority = 5
            
            # Возвращаем кортеж для сортировки:
            # (приоритет_категории, инвертированные_числовые_части, суффикс)
            # Инвертируем числовые части для сортировки по убыванию
            inverted_version = tuple(-part for part in version_parts)
            
            return (priority, inverted_version, suffix, tag)
        
        return sorted(tags, key=tag_sort_key)
    
    async def get_docker_images(self, artifact_url: str, limit: Optional[int] = None) -> List[DockerImage]:
        """
        Получение списка Docker образов с метаданными.
        
        Args:
            artifact_url: URL к Docker репозиторию
            limit: Максимальное количество образов
            
        Returns:
            Список DockerImage объектов
        """
        # Получаем список тегов
        tags = await self.get_tags(artifact_url)
        
        if not tags:
            logger.warning(f"Не найдено тегов для {artifact_url}")
            return []
        
        # Сортируем теги
        sorted_tags = self.sort_tags(tags)
        
        # Ограничиваем количество если указано
        if limit and limit > 0:
            sorted_tags = sorted_tags[:limit]
        
        # Парсим URL для получения компонентов
        registry_url, docker_path, app_name = self.parse_docker_url(artifact_url)
        
        # Создаем список образов
        images = []
        for tag in sorted_tags:
            image = DockerImage(
                registry_url=registry_url,
                repository=docker_path,
                tag=tag,
                is_dev=self.is_dev_tag(tag),
                is_snapshot=self.is_snapshot_tag(tag)
            )
            images.append(image)
        
        logger.info(f"Подготовлено {len(images)} Docker образов для {app_name}")
        
        return images
    
    async def get_images_for_application(self, 
                                        application_instance: ApplicationInstance,
                                        limit: Optional[int] = None) -> List[DockerImage]:
        """
        Получение списка Docker образов для экземпляра приложения.
        
        Args:
            application_instance: Экземпляр приложения
            limit: Максимальное количество образов
            
        Returns:
            Список Docker образов
        """
        # Получаем URL артефактов
        artifact_url = application_instance.get_effective_artifact_url()
        
        if not artifact_url:
            logger.warning(f"Не задан artifact_url для Docker приложения {application_instance.original_name}")
            return []
        
        # Проверяем, что это Docker приложение
        if application_instance.application and application_instance.application.app_type != 'docker':
            logger.warning(f"Приложение {application_instance.original_name} не является Docker приложением")
            return []
        
        return await self.get_docker_images(artifact_url, limit)
    
    async def get_images_for_group(self, 
                                  application_group: ApplicationGroup,
                                  limit: Optional[int] = None) -> List[DockerImage]:
        """
        Получение списка Docker образов для группы приложений.
        
        Args:
            application_group: Группа приложений
            limit: Максимальное количество образов
            
        Returns:
            Список Docker образов
        """
        if not application_group.artifact_list_url:
            logger.warning(f"Не задан artifact_list_url для группы {application_group.name}")
            return []
        
        return await self.get_docker_images(application_group.artifact_list_url, limit)

"""
Сервис для получения списка артефактов из Sonatype Nexus
Парсит maven-metadata.xml и формирует ссылки для загрузки артефактов
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import aiohttp
import asyncio
from datetime import datetime
import re
from typing import Tuple

from app.models.application_group import ApplicationGroup, ApplicationInstance

logger = logging.getLogger(__name__)


@dataclass
class Artifact:
    """
    Класс для хранения информации об артефакте
    """
    group_id: str  # Имя группы (например: ru.cft.faktura.mdse)
    artifact_id: str  # Имя артефакта (например: mDSE)
    version: str  # Версия артефакта (например: 3.131.1)
    filename: str  # Имя файла (например: mDSE-3.131.1.jar)
    download_url: str  # Полная ссылка для загрузки
    is_snapshot: bool = False  # Флаг SNAPSHOT версии
    is_release: bool = False  # Флаг релизной версии
    timestamp: Optional[datetime] = None  # Время последнего обновления (если доступно)
    
    def to_dict(self) -> dict:
        """Преобразование в словарь для сериализации"""
        return {
            'group_id': self.group_id,
            'artifact_id': self.artifact_id,
            'version': self.version,
            'filename': self.filename,
            'download_url': self.download_url,
            'is_snapshot': self.is_snapshot,
            'is_release': self.is_release,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class NexusArtifactService:
    """
    Сервис для работы с артефактами Sonatype Nexus
    """
    
    def __init__(self, timeout: int = 30):
        """
        Инициализация сервиса
        
        Args:
            timeout: Таймаут для HTTP запросов в секундах
        """
        self.timeout = timeout
        self.session = None
    
    async def __aenter__(self):
        """Асинхронный вход в контекстный менеджер"""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный выход из контекстного менеджера"""
        if self.session:
            await self.session.close()
    
    async def fetch_maven_metadata(self, metadata_url: str) -> Optional[str]:
        """
        Получение содержимого maven-metadata.xml
        
        Args:
            metadata_url: URL к maven-metadata.xml файлу
            
        Returns:
            Содержимое XML файла или None в случае ошибки
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
            
            logger.info(f"Запрос maven-metadata.xml: {metadata_url}")
            
            async with self.session.get(metadata_url) as response:
                if response.status == 200:
                    content = await response.text()
                    logger.debug(f"Успешно получен maven-metadata.xml, размер: {len(content)} байт")
                    return content
                else:
                    logger.error(f"Ошибка получения maven-metadata.xml: HTTP {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при получении maven-metadata.xml: {metadata_url}")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении maven-metadata.xml: {str(e)}")
            return None
    
    def parse_maven_metadata(self, xml_content: str) -> Tuple[Optional[str], Optional[str], Optional[str], List[str], Optional[datetime]]:
        """
        Парсинг maven-metadata.xml
        
        Args:
            xml_content: Содержимое XML файла
            
        Returns:
            Кортеж (group_id, artifact_id, latest_version, список версий, lastUpdated)
        """
        try:
            root = ET.fromstring(xml_content)
            
            # Извлекаем основную информацию
            group_id = root.findtext('groupId', default='')
            artifact_id = root.findtext('artifactId', default='')
            
            # Извлекаем информацию о версиях
            versioning = root.find('versioning')
            if versioning is None:
                logger.warning("Отсутствует элемент 'versioning' в maven-metadata.xml")
                return group_id, artifact_id, None, [], None
            
            latest = versioning.findtext('latest')
            release = versioning.findtext('release')
            
            # Получаем список всех версий
            versions_elem = versioning.find('versions')
            versions = []
            if versions_elem is not None:
                for version_elem in versions_elem.findall('version'):
                    version = version_elem.text
                    if version:
                        versions.append(version)
            
            # Парсим время последнего обновления
            last_updated_str = versioning.findtext('lastUpdated')
            last_updated = None
            if last_updated_str:
                try:
                    # Формат: YYYYMMDDHHMMSS
                    last_updated = datetime.strptime(last_updated_str, '%Y%m%d%H%M%S')
                except ValueError:
                    logger.warning(f"Не удалось распарсить lastUpdated: {last_updated_str}")
            
            logger.info(f"Распарсено: {group_id}:{artifact_id}, версий: {len(versions)}, latest: {latest}, release: {release}")
            
            return group_id, artifact_id, release or latest, versions, last_updated
            
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML: {str(e)}")
            return None, None, None, [], None
        except Exception as e:
            logger.error(f"Ошибка при парсинге maven-metadata.xml: {str(e)}")
            return None, None, None, [], None
    
    def build_download_url(self, base_url: str, artifact_id: str, version: str, extension: str) -> str:
        """
        Формирование URL для загрузки артефакта
        
        Args:
            base_url: Базовый URL репозитория (путь к папке с maven-metadata.xml)
            artifact_id: ID артефакта
            version: Версия артефакта
            extension: Расширение файла (jar, war, zip и т.д.)
            
        Returns:
            Полный URL для загрузки артефакта
        """
        # Убираем maven-metadata.xml из URL если он там есть
        if base_url.endswith('maven-metadata.xml'):
            base_url = base_url.rsplit('/', 1)[0]
        
        # Убеждаемся, что base_url заканчивается на /
        if not base_url.endswith('/'):
            base_url += '/'
        
        # Формируем имя файла
        filename = f"{artifact_id}-{version}.{extension}"
        
        # Формируем полный URL: base_url/version/filename
        download_url = urljoin(base_url, f"{version}/{filename}")
        
        return download_url
    
    async def get_artifacts_for_application(self, 
                                           application_instance: ApplicationInstance) -> List[Artifact]:
        """
        Получение списка артефактов для экземпляра приложения
        
        Args:
            application_instance: Экземпляр приложения
            
        Returns:
            Список артефактов
        """
        # Получаем эффективные настройки артефактов
        artifact_list_url = application_instance.get_effective_artifact_url()
        artifact_extension = application_instance.get_effective_artifact_extension()
        
        if not artifact_list_url:
            logger.warning(f"Не задан artifact_list_url для приложения {application_instance.original_name}")
            return []
        
        if not artifact_extension:
            # Используем jar по умолчанию для Maven репозиториев
            artifact_extension = 'jar'
            logger.info(f"Используется расширение по умолчанию: {artifact_extension}")
        
        # Убираем расширение, если оно начинается с точки
        if artifact_extension.startswith('.'):
            artifact_extension = artifact_extension[1:]
        
        return await self.get_artifacts(artifact_list_url, artifact_extension)
    
    async def get_artifacts_for_group(self, 
                                     application_group: ApplicationGroup) -> List[Artifact]:
        """
        Получение списка артефактов для группы приложений
        
        Args:
            application_group: Группа приложений
            
        Returns:
            Список артефактов
        """
        if not application_group.artifact_list_url:
            logger.warning(f"Не задан artifact_list_url для группы {application_group.name}")
            return []
        
        artifact_extension = application_group.artifact_extension or 'jar'
        
        # Убираем расширение, если оно начинается с точки
        if artifact_extension.startswith('.'):
            artifact_extension = artifact_extension[1:]
        
        return await self.get_artifacts(application_group.artifact_list_url, artifact_extension)
    
    def parse_version_for_sorting(self, version_string: str) -> Tuple[Tuple[int, ...], str, bool, bool]:
        """
        Парсинг версии для правильной сортировки.
        
        Разбивает версию на числовые части для корректного сравнения.
        Например, "3.131.1-SNAPSHOT" -> ((3, 131, 1), "SNAPSHOT", True, False)
        
        Args:
            version_string: Строка версии (например: "3.131.1", "3.100-SNAPSHOT")
            
        Returns:
            Кортеж: (числовые_части, суффикс, is_snapshot, is_special)
            - числовые_части: кортеж чисел для сортировки
            - суффикс: текстовый суффикс после основной версии
            - is_snapshot: True если это SNAPSHOT версия
            - is_special: True если есть специальный суффикс (DSE, TEST и т.д.)
        """
        # Разделяем основную версию и суффикс
        match = re.match(r'^([\d.]+)(-.*)?$', version_string)
        if not match:
            # Если формат версии нестандартный, возвращаем минимальные значения
            return ((0,), version_string, 'SNAPSHOT' in version_string.upper(), True)
        
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
        parts = parts + (0,) * (4 - len(parts))
        
        # Определяем тип версии
        is_snapshot = 'SNAPSHOT' in suffix.upper()
        is_special = bool(suffix) and not is_snapshot
        
        return (parts, suffix.lower(), is_snapshot, is_special)    
      
    
    async def get_artifacts(self, metadata_url: str, extension: str = 'jar') -> List[Artifact]:
        """
        Получение списка артефактов по URL к maven-metadata.xml
        
        Args:
            metadata_url: URL к maven-metadata.xml или к директории с ним
            extension: Расширение файлов артефактов
            
        Returns:
            Список артефактов
        """
        # Если URL не заканчивается на maven-metadata.xml, добавляем его
        if not metadata_url.endswith('maven-metadata.xml'):
            if not metadata_url.endswith('/'):
                metadata_url += '/'
            metadata_url += 'maven-metadata.xml'
        
        # Получаем содержимое XML
        xml_content = await self.fetch_maven_metadata(metadata_url)
        if not xml_content:
            return []
        
        # Парсим XML
        group_id, artifact_id, latest_version, versions, last_updated = self.parse_maven_metadata(xml_content)
        
        if not artifact_id or not versions:
            logger.warning("Не удалось извлечь информацию об артефактах из maven-metadata.xml")
            return []
        
        # Базовый URL для формирования ссылок на загрузку
        base_url = metadata_url.rsplit('maven-metadata.xml', 1)[0]
        
        # Создаем список артефактов
        artifacts = []
        for version in versions:
            is_snapshot = 'SNAPSHOT' in version
            is_release = (version == latest_version)
            
            artifact = Artifact(
                group_id=group_id,
                artifact_id=artifact_id,
                version=version,
                filename=f"{artifact_id}-{version}.{extension}",
                download_url=self.build_download_url(base_url, artifact_id, version, extension),
                is_snapshot=is_snapshot,
                is_release=is_release,
                timestamp=last_updated
            )
            artifacts.append(artifact)
        
        # Сортируем артефакты по числовым частям версии в порядке убывания
        artifacts.sort(
            key=lambda a: (
                # Первый критерий: релизы приоритетнее
                not a.is_release,
                # Второй критерий: числовые части версии (от большего к меньшему)
                # Инвертируем кортеж для сортировки по убыванию
                tuple(-part for part in self.parse_version_for_sorting(a.version)[0]),
                # Третий критерий: не-SNAPSHOT версии приоритетнее
                a.is_snapshot,
                # Четвертый критерий: версии без специальных суффиксов приоритетнее
                self.parse_version_for_sorting(a.version)[3],
                # Пятый критерий: алфавитная сортировка суффикса
                self.parse_version_for_sorting(a.version)[1]
            )
        )
        
        logger.info(f"Получено {len(artifacts)} артефактов для {group_id}:{artifact_id}")
        
        return artifacts
      
    async def get_latest_artifact(self, metadata_url: str, extension: str = 'jar',
                                 include_snapshots: bool = False) -> Optional[Artifact]:
        """
        Получение последней версии артефакта
        
        Args:
            metadata_url: URL к maven-metadata.xml
            extension: Расширение файла
            include_snapshots: Включать SNAPSHOT версии
            
        Returns:
            Последний артефакт или None
        """
        artifacts = await self.get_artifacts(metadata_url, extension)
        
        if not artifacts:
            return None
        
        # Фильтруем SNAPSHOT версии если нужно
        if not include_snapshots:
            artifacts = [a for a in artifacts if not a.is_snapshot]
        
        # Возвращаем первый (самый новый) артефакт
        return artifacts[0] if artifacts else None
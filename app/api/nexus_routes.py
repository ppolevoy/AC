from flask import jsonify, request
from app import db
from app.models.application import Application
from app.models.application_group import ApplicationGroup, ApplicationInstance
from app.services.application_group_service import ApplicationGroupService
from app.api import bp
import logging

from app.services.nexus_artifact_service import NexusArtifactService, Artifact
import asyncio

logger = logging.getLogger(__name__)

@bp.route('/artifacts/group/<int:group_id>', methods=['GET'])
def get_group_artifacts(group_id):
    """
    Получение списка артефактов для группы приложений
    
    Args:
        group_id: ID группы приложений
        
    Query Parameters:
        include_snapshots: включать SNAPSHOT версии (по умолчанию true)
        limit: максимальное количество версий (по умолчанию все)
    """
    try:
        # Получаем группу
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа приложений с id {group_id} не найдена"
            }), 404
        
        if not group.artifact_list_url:
            return jsonify({
                'success': False,
                'error': f"Для группы {group.name} не настроен artifact_list_url"
            }), 400
        
        # Получаем параметры из запроса
        include_snapshots = request.args.get('include_snapshots', 'true').lower() == 'true'
        limit = request.args.get('limit', type=int)
        
        # Запускаем асинхронный сервис
        async def fetch_artifacts():
            async with NexusArtifactService() as service:
                artifacts = await service.get_artifacts_for_group(group)
                
                # Фильтруем SNAPSHOT версии если нужно
                if not include_snapshots:
                    artifacts = [a for a in artifacts if not a.is_snapshot]
                
                # Ограничиваем количество если указан limit
                if limit and limit > 0:
                    artifacts = artifacts[:limit]
                
                return artifacts
        
        # Выполняем асинхронную операцию
        artifacts = asyncio.run(fetch_artifacts())
        
        return jsonify({
            'success': True,
            'group': {
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension
            },
            'artifacts_count': len(artifacts),
            'artifacts': [a.to_dict() for a in artifacts]
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении артефактов для группы {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/artifacts/instance/<int:instance_id>', methods=['GET'])
def get_instance_artifacts(instance_id):
    """
    Получение списка артефактов для экземпляра приложения
    
    Args:
        instance_id: ID экземпляра приложения
        
    Query Parameters:
        include_snapshots: включать SNAPSHOT версии (по умолчанию true)
        limit: максимальное количество версий (по умолчанию все)
    """
    try:
        # Получаем экземпляр
        instance = ApplicationInstance.query.get(instance_id)
        if not instance:
            return jsonify({
                'success': False,
                'error': f"Экземпляр приложения с id {instance_id} не найден"
            }), 404
        
        # Проверяем наличие URL артефактов
        artifact_url = instance.get_effective_artifact_url()
        if not artifact_url:
            return jsonify({
                'success': False,
                'error': f"Для экземпляра {instance.original_name} не настроен artifact_list_url"
            }), 400
        
        # Получаем параметры из запроса
        include_snapshots = request.args.get('include_snapshots', 'true').lower() == 'true'
        limit = request.args.get('limit', type=int)
        
        # Запускаем асинхронный сервис
        async def fetch_artifacts():
            async with NexusArtifactService() as service:
                artifacts = await service.get_artifacts_for_application(instance)
                
                # Фильтруем SNAPSHOT версии если нужно
                if not include_snapshots:
                    artifacts = [a for a in artifacts if not a.is_snapshot]
                
                # Ограничиваем количество если указан limit
                if limit and limit > 0:
                    artifacts = artifacts[:limit]
                
                return artifacts
        
        # Выполняем асинхронную операцию
        artifacts = asyncio.run(fetch_artifacts())
        
        return jsonify({
            'success': True,
            'instance': {
                'id': instance.id,
                'original_name': instance.original_name,
                'group_name': instance.group.name if instance.group else None,
                'effective_artifact_url': instance.get_effective_artifact_url(),
                'effective_artifact_extension': instance.get_effective_artifact_extension()
            },
            'artifacts_count': len(artifacts),
            'artifacts': [a.to_dict() for a in artifacts]
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении артефактов для экземпляра {instance_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/artifacts/latest', methods=['POST'])
def get_latest_artifact():
    """
    Получение последней версии артефакта по URL
    
    Body Parameters:
        metadata_url: URL к maven-metadata.xml
        extension: расширение файла (по умолчанию jar)
        include_snapshots: включать SNAPSHOT версии (по умолчанию false)
    """
    try:
        data = request.json
        if not data or 'metadata_url' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует обязательный параметр metadata_url"
            }), 400
        
        metadata_url = data['metadata_url']
        extension = data.get('extension', 'jar')
        include_snapshots = data.get('include_snapshots', False)
        
        # Запускаем асинхронный сервис
        async def fetch_latest():
            async with NexusArtifactService() as service:
                return await service.get_latest_artifact(
                    metadata_url, 
                    extension, 
                    include_snapshots
                )
        
        # Выполняем асинхронную операцию
        latest_artifact = asyncio.run(fetch_latest())
        
        if not latest_artifact:
            return jsonify({
                'success': False,
                'error': "Не найдено доступных артефактов"
            }), 404
        
        return jsonify({
            'success': True,
            'artifact': latest_artifact.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Ошибка при получении последнего артефакта: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/artifacts/test-connection', methods=['POST'])
def test_nexus_connection():
    """
    Тестирование подключения к Nexus репозиторию
    
    Body Parameters:
        metadata_url: URL к maven-metadata.xml для тестирования
    """
    try:
        data = request.json
        if not data or 'metadata_url' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует обязательный параметр metadata_url"
            }), 400
        
        metadata_url = data['metadata_url']
        
        # Проверяем доступность и парсинг maven-metadata.xml
        async def test_connection():
            async with NexusArtifactService(timeout=10) as service:
                xml_content = await service.fetch_maven_metadata(metadata_url)
                if not xml_content:
                    return False, "Не удалось получить maven-metadata.xml"
                
                group_id, artifact_id, latest_version, versions, last_updated = service.parse_maven_metadata(xml_content)
                
                if not artifact_id or not versions:
                    return False, "Не удалось распарсить maven-metadata.xml"
                
                return True, {
                    'group_id': group_id,
                    'artifact_id': artifact_id,
                    'latest_version': latest_version,
                    'versions_count': len(versions),
                    'last_updated': last_updated.isoformat() if last_updated else None
                }
        
        # Выполняем тест
        success, result = asyncio.run(test_connection())
        
        if success:
            return jsonify({
                'success': True,
                'message': "Подключение к Nexus успешно установлено",
                'metadata': result
            })
        else:
            return jsonify({
                'success': False,
                'error': result
            }), 400
            
    except Exception as e:
        logger.error(f"Ошибка при тестировании подключения к Nexus: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
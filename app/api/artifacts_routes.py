from flask import jsonify, request
import asyncio
import logging

from app.models.application_instance import ApplicationInstance
from app.api import bp

# Алиас для обратной совместимости
Application = ApplicationInstance

logger = logging.getLogger(__name__)


def get_maven_versions_for_app(app):
    """
    Получение списка Maven артефактов для приложения
    """
    try:
        # app уже является ApplicationInstance после рефакторинга
        if not app.group:
            logger.info(f"Приложение {app.instance_name} не привязано к группе")
            return jsonify({
                'success': False,
                'error': 'Приложение не привязано к группе. Настройте группу приложений.'
            }), 404

        # Получаем URL артефактов и расширение
        artifact_url = app.get_effective_artifact_url()
        artifact_extension = app.get_effective_artifact_extension()

        if not artifact_url:
            logger.info(f"URL артефактов не настроен для приложения {app.instance_name}")
            return jsonify({
                'success': False,
                'error': 'URL артефактов не настроен для данного приложения'
            }), 404

        logger.info(f"Загрузка Maven артефактов из: {artifact_url}")

        # Получаем параметры из запроса
        from app.config import Config
        limit = request.args.get('limit', type=int, default=Config.MAX_ARTIFACTS_DISPLAY)
        include_snapshots = request.args.get('include_snapshots',
                                            default=str(Config.INCLUDE_SNAPSHOT_VERSIONS).lower()).lower() == 'true'

        # Получаем список артефактов через NexusArtifactService
        from app.services.nexus_artifact_service import NexusArtifactService

        # Запускаем асинхронную операцию
        async def fetch_maven_artifacts():
            async with NexusArtifactService() as service:
                artifacts = await service.get_artifacts_for_application(app)

                # Фильтруем SNAPSHOT версии если нужно
                if not include_snapshots:
                    artifacts = [a for a in artifacts if not a.is_snapshot]

                # Ограничиваем количество версий
                if limit and limit > 0:
                    artifacts = artifacts[:limit]

                return artifacts

        artifacts = asyncio.run(fetch_maven_artifacts())

        if not artifacts:
            logger.warning(f"Не удалось получить список артефактов для {app.instance_name}")
            return jsonify({
                'success': False,
                'error': 'Не удалось получить список версий из репозитория'
            }), 404

        # Формируем список версий для отправки на frontend
        versions = []
        for artifact in artifacts:
            versions.append({
                'version': artifact.version,
                'url': artifact.download_url,
                'display_name': artifact.filename,  # Для единообразия с Docker
                'filename': artifact.filename,
                'is_release': artifact.is_release,
                'is_snapshot': artifact.is_snapshot,
                'is_dev': False,  # Maven не имеет dev версий
                'timestamp': artifact.timestamp.isoformat() if artifact.timestamp else None
            })

        logger.info(f"Загружено {len(versions)} Maven артефактов для приложения {app.instance_name}")

        return jsonify({
            'success': True,
            'application': app.instance_name,
            'app_type': app.app_type,
            'versions': versions,
            'total': len(versions),
            'limit_applied': limit,
            'snapshots_included': include_snapshots
        })

    except Exception as e:
        logger.error(f"Ошибка при получении Maven артефактов для приложения {app.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_docker_versions_for_app(app):
    """
    Получение списка Docker образов для приложения
    """
    try:
        # app уже является ApplicationInstance после рефакторинга
        if not app.group:
            logger.warning(f"Приложение {app.instance_name} не привязано к группе")
            return jsonify({
                'success': False,
                'error': 'Приложение не привязано к группе. Настройте группу приложений для Docker.'
            }), 404

        # Получаем URL Docker репозитория
        artifact_url = app.get_effective_artifact_url()

        if not artifact_url:
            logger.warning(f"URL Docker репозитория не настроен для приложения {app.instance_name}")
            return jsonify({
                'success': False,
                'error': 'URL Docker репозитория не настроен для данного приложения'
            }), 404

        logger.info(f"Загрузка Docker образов из: {artifact_url}")

        # Получаем параметры из запроса
        from app.config import Config
        limit = request.args.get('limit', type=int, default=Config.MAX_ARTIFACTS_DISPLAY)
        include_dev = request.args.get('include_dev', 'false').lower() == 'true'
        include_snapshots = request.args.get('include_snapshots', 'false').lower() == 'true'

        # Запускаем асинхронную операцию
        from app.services.nexus_docker_service import NexusDockerService

        async def fetch_docker_images():
            async with NexusDockerService() as service:
                images = await service.get_docker_images(artifact_url, limit=limit*2)

                # Фильтруем версии
                filtered_images = []
                for image in images:
                    if not include_dev and image.is_dev:
                        continue
                    if not include_snapshots and image.is_snapshot:
                        continue
                    filtered_images.append(image)

                return filtered_images[:limit]

        images = asyncio.run(fetch_docker_images())

        if not images:
            logger.warning(f"Не удалось получить список Docker образов для {app.instance_name}")
            return jsonify({
                'success': False,
                'error': 'Не удалось получить список образов из репозитория'
            }), 404

        # Формируем список версий для отправки на frontend
        versions = []
        for image in images:
            versions.append({
                'version': image.tag,
                'url': image.full_image_name,  # Полное имя образа для Docker
                'display_name': image.display_name,
                'filename': f"{image.repository.split('/')[-1]}:{image.tag}",  # Для совместимости
                'is_release': not (image.is_dev or image.is_snapshot),
                'is_snapshot': image.is_snapshot,
                'is_dev': image.is_dev,
                'timestamp': image.created.isoformat() if image.created else None
            })

        logger.info(f"Загружено {len(versions)} Docker образов для приложения {app.instance_name}")

        return jsonify({
            'success': True,
            'application': app.instance_name,
            'app_type': 'docker',
            'versions': versions,
            'total': len(versions),
            'limit_applied': limit,
            'snapshots_included': include_snapshots,
            'dev_included': include_dev
        })

    except Exception as e:
        logger.error(f"Ошибка при получении Docker образов для приложения {app.id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/artifacts', methods=['GET'])
def get_application_artifacts(app_id):
    """
    Получение списка артефактов/образов для приложения с поддержкой типов приложений

    Query Parameters:
        limit: максимальное количество версий для возврата (по умолчанию из конфигурации)
        include_snapshots: включать ли SNAPSHOT версии (по умолчанию из конфигурации)
        include_dev: включать ли DEV версии (для Docker, по умолчанию false)
    """
    try:
        # Получаем приложение
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404

        logger.info(f"Получение версий для приложения {app.instance_name}, тип: {app.app_type}")

        # ВАЖНО: Проверяем тип приложения
        if app.app_type == 'docker':
            # Для Docker приложений используем NexusDockerService
            return get_docker_versions_for_app(app)
        else:
            # Для остальных (maven, site, service) используем NexusArtifactService
            return get_maven_versions_for_app(app)

    except Exception as e:
        logger.error(f"Ошибка при получении версий для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

from flask import jsonify, request
from app import db
from app.models.application import Application
from app.models.application_group import ApplicationGroup, ApplicationInstance
from app.services.application_group_service import ApplicationGroupService
from app.api import bp
import logging

logger = logging.getLogger(__name__)

@bp.route('/applications/with-groups', methods=['GET'])
def get_applications_with_groups():
    """Получить список всех приложений с информацией о группах"""
    try:
        # Получаем все приложения с информацией о группах через application_instances
        apps = db.session.query(
            Application,
            ApplicationInstance,
            ApplicationGroup
        ).outerjoin(
            ApplicationInstance,
            Application.id == ApplicationInstance.application_id
        ).outerjoin(
            ApplicationGroup,
            ApplicationInstance.group_id == ApplicationGroup.id
        ).all()
        
        result = []
        for app, instance, group in apps:
            result.append({
                'id': app.id,
                'name': app.name,
                'server_name': app.server.name if app.server else 'Unknown',
                'server_id': app.server_id,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'group_id': group.id if group else None,
                'group_name': group.name if group else None,
                'instance_number': instance.instance_number if instance else 0,
                'has_instance': instance is not None,
                'group_resolved': instance.group_resolved if instance else False
            })
        
        return jsonify({
            'success': True,
            'applications': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении приложений с группами: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/with-group', methods=['GET'])
def get_application_with_group(app_id):
    """Получить информацию о приложении с его группой"""
    try:
        # Получаем приложение с информацией о группе
        result = db.session.query(
            Application,
            ApplicationInstance,
            ApplicationGroup
        ).outerjoin(
            ApplicationInstance,
            Application.id == ApplicationInstance.application_id
        ).outerjoin(
            ApplicationGroup,
            ApplicationInstance.group_id == ApplicationGroup.id
        ).filter(Application.id == app_id).first()
        
        if not result:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        app, instance, group = result
        
        return jsonify({
            'success': True,
            'application': {
                'id': app.id,
                'name': app.name,
                'server_name': app.server.name if app.server else 'Unknown',
                'server_id': app.server_id,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'group_id': group.id if group else None,
                'group_name': group.name if group else None,
                'instance_number': instance.instance_number if instance else 0,
                'has_instance': instance is not None,
                'group_resolved': instance.group_resolved if instance else False
            }
        })
    except Exception as e:
        logger.error(f"Ошибка при получении приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/ungrouped', methods=['GET'])
def get_ungrouped_applications():
    """Получить список приложений без назначенной группы"""
    try:
        # Найти все приложения без группы или с неразрешенной группой
        ungrouped_apps = db.session.query(Application).outerjoin(
            ApplicationInstance,
            Application.id == ApplicationInstance.application_id
        ).filter(
            db.or_(
                ApplicationInstance.id.is_(None),
                ApplicationInstance.group_resolved == False,
                ApplicationInstance.group_id.is_(None)
            )
        ).all()
        
        result = []
        for app in ungrouped_apps:
            result.append({
                'id': app.id,
                'name': app.name,
                'server_name': app.server.name if app.server else 'Unknown',
                'server_id': app.server_id,
                'type': app.app_type,
                'status': app.status,
                'version': app.version
            })
        
        return jsonify({
            'success': True,
            'applications': result,
            'count': len(result)
        })
    except Exception as e:
        logger.error(f"Ошибка при получении приложений без группы: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/statistics', methods=['GET'])
def get_groups_statistics():
    """Получить статистику по группам и экземплярам"""
    try:
        stats = ApplicationGroupService.get_statistics()
        
        return jsonify({
            'success': True,
            **stats
        })
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/reassign-group', methods=['POST'])
def reassign_application_group_manual(app_id):
    """Ручное переназначение группы для приложения с флагом manual_assignment"""
    try:
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        data = request.json
        if not data or 'group_name' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле group_name"
            }), 400
        
        group_name = data['group_name']
        instance_number = data.get('instance_number', 0)
        manual_assignment = data.get('manual_assignment', False)
        
        # Получаем или создаем группу
        group = ApplicationGroupService.get_or_create_group(group_name)
        
        # Проверяем существующий экземпляр
        instance = ApplicationInstance.query.filter_by(application_id=app.id).first()
        
        if not instance:
            # Создаем новый экземпляр
            instance = ApplicationInstance(
                original_name=app.name,
                instance_number=instance_number,
                group_id=group.id,
                application_id=app.id,
                group_resolved=True
            )
            db.session.add(instance)
            logger.info(f"Создан экземпляр для {app.name}: группа={group_name}, номер={instance_number}")
        else:
            # Обновляем существующий экземпляр
            old_group_name = instance.group.name if instance.group else "без группы"
            
            # Если это ручное назначение, устанавливаем специальный флаг
            if manual_assignment:
                instance.group_resolved = True  # Помечаем как разрешенную вручную
            
            instance.group_id = group.id
            instance.instance_number = instance_number
            instance.original_name = app.name
            
            logger.info(f"Приложение {app.name} переназначено из группы '{old_group_name}' в группу '{group_name}'")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Приложение {app.name} успешно назначено в группу {group_name}",
            'application': {
                'id': app.id,
                'name': app.name,
                'group_name': group.name,
                'instance_number': instance_number,
                'manual_assignment': manual_assignment
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при переназначении группы для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<int:group_id>/instances', methods=['GET'])
def get_group_instances_detailed(group_id):
    """Получить детальную информацию об экземплярах группы"""
    try:
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа с id {group_id} не найдена"
            }), 404
        
        instances = []
        for instance in group.instances:
            app = instance.application
            if app:
                instances.append({
                    'id': app.id,
                    'instance_id': instance.id,
                    'name': app.name,
                    'instance_number': instance.instance_number,
                    'server': {
                        'id': app.server.id,
                        'name': app.server.name
                    } if app.server else None,
                    'status': app.status,
                    'version': app.version,
                    'has_custom_settings': instance.has_custom_settings(),
                    'custom_artifact_url': instance.custom_artifact_list_url,
                    'custom_artifact_extension': instance.custom_artifact_extension,
                    'custom_playbook': instance.custom_playbook_path,
                    'group_resolved': instance.group_resolved
                })
        
        return jsonify({
            'success': True,
            'group': {
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'update_playbook_path': group.update_playbook_path
            },
            'instances': sorted(instances, key=lambda x: x['instance_number'])
        })
    except Exception as e:
        logger.error(f"Ошибка при получении экземпляров группы {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/instance-settings', methods=['GET'])
def get_application_instance_settings(app_id):
    """Получить настройки экземпляра приложения"""
    try:
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        instance = ApplicationInstance.query.filter_by(application_id=app.id).first()
        
        if not instance:
            # Если экземпляра нет, создаем его
            logger.info(f"Создание экземпляра для приложения {app.name}")
            from app.services.application_group_service import ApplicationGroupService
            instance = ApplicationGroupService.resolve_application_group(app)
            
            if instance:
                db.session.commit()
                logger.info(f"Экземпляр создан для приложения {app.name}")
            else:
                # Создаем экземпляр без группы
                group_name = app.name
                group = ApplicationGroup(name=group_name)
                db.session.add(group)
                db.session.flush()
                
                instance = ApplicationInstance(
                    original_name=app.name,
                    instance_number=0,
                    group_id=group.id,
                    application_id=app.id,
                    group_resolved=False
                )
                db.session.add(instance)
                db.session.commit()
                logger.info(f"Создан экземпляр без группы для приложения {app.name}")
        
        return jsonify({
            'success': True,
            'application': app.name,
            'instance_number': instance.instance_number,
            'individual_settings': {
                'custom_artifact_list_url': instance.custom_artifact_list_url,
                'custom_artifact_extension': instance.custom_artifact_extension,
                'custom_playbook_path': instance.custom_playbook_path
            },
            'group_settings': {
                'artifact_list_url': instance.group.artifact_list_url,
                'artifact_extension': instance.group.artifact_extension,
                'update_playbook_path': instance.group.update_playbook_path
            } if instance.group else {},
            'effective_settings': {
                'artifact_list_url': instance.get_effective_artifact_url() if hasattr(instance, 'get_effective_artifact_url') else None,
                'artifact_extension': instance.get_effective_artifact_extension() if hasattr(instance, 'get_effective_artifact_extension') else None,
                'playbook_path': instance.get_effective_playbook_path() if hasattr(instance, 'get_effective_playbook_path') else None
            },
            'custom_playbook': instance.custom_playbook_path
        })
    except Exception as e:
        logger.error(f"Ошибка при получении настроек экземпляра для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/applications/<int:app_id>/instance-settings', methods=['PATCH'])
def update_application_instance_settings(app_id):
    """Обновить настройки экземпляра приложения"""
    try:
        app = Application.query.get(app_id)
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        instance = ApplicationInstance.query.filter_by(application_id=app.id).first()
        
        if not instance:
            # Если экземпляра нет, создаем его
            from app.services.application_group_service import ApplicationGroupService
            instance = ApplicationGroupService.resolve_application_group(app)
            if not instance:
                return jsonify({
                    'success': False,
                    'error': 'Не удалось создать экземпляр для приложения'
                }), 400
        
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400
        
        # Обновляем кастомные настройки экземпляра
        if 'custom_artifact_list_url' in data:
            instance.custom_artifact_list_url = data['custom_artifact_list_url'] or None
        
        if 'custom_artifact_extension' in data:
            instance.custom_artifact_extension = data['custom_artifact_extension'] or None
        
        if 'custom_playbook_path' in data:
            instance.custom_playbook_path = data['custom_playbook_path'] or None
        
        from datetime import datetime
        instance.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        logger.info(f"Обновлены настройки экземпляра для приложения {app.name}")
        
        return jsonify({
            'success': True,
            'message': f"Настройки экземпляра {app.name} обновлены",
            'settings': {
                'custom_artifact_list_url': instance.custom_artifact_list_url,
                'custom_artifact_extension': instance.custom_artifact_extension,
                'custom_playbook_path': instance.custom_playbook_path
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении настроек экземпляра для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/init-instances', methods=['POST'])
def init_application_instances():
    """Инициализировать экземпляры для всех приложений"""
    try:
        # Получаем все приложения
        applications = Application.query.all()
        
        created_count = 0
        error_count = 0
        errors = []
        
        for application in applications:
            try:
                # Проверяем, есть ли уже экземпляр
                existing_instance = ApplicationInstance.query.filter_by(
                    application_id=application.id
                ).first()
                
                if existing_instance:
                    logger.debug(f"Приложение {application.name} уже имеет экземпляр")
                    continue
                
                # Определяем группу для приложения
                instance = ApplicationGroupService.resolve_application_group(application)
                
                if instance:
                    created_count += 1
                    logger.info(f"Создан экземпляр для {application.name}")
                else:
                    # Если не удалось определить группу, создаем отдельную
                    group_name = application.name
                    group = ApplicationGroup(name=group_name)
                    db.session.add(group)
                    db.session.flush()
                    
                    instance = ApplicationInstance(
                        original_name=application.name,
                        instance_number=0,
                        group_id=group.id,
                        application_id=application.id,
                        group_resolved=False
                    )
                    db.session.add(instance)
                    created_count += 1
                    logger.info(f"Создан экземпляр для {application.name} в отдельной группе")
                    
            except Exception as e:
                error_count += 1
                errors.append({
                    'app_id': application.id,
                    'app_name': application.name,
                    'error': str(e)
                })
                logger.error(f"Ошибка при создании экземпляра для {application.name}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Инициализация завершена. Создано {created_count} экземпляров",
            'created_count': created_count,
            'error_count': error_count,
            'total_apps': len(applications),
            'errors': errors if errors else None
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при инициализации экземпляров: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ====================================
# CRUD для групп приложений
# ====================================

@bp.route('/application-groups', methods=['GET'])
def get_application_groups():
    """Получение списка всех групп приложений"""
    try:
        from app.models.server import Server
        groups = ApplicationGroup.query.all()
        result = []
        
        for group in groups:
            # Подсчитываем количество экземпляров в группе
            instance_count = Application.query.filter_by(group_id=group.id).count()
            
            # Получаем список серверов, где запущены экземпляры
            servers = db.session.query(Server).join(
                Application, Application.server_id == Server.id
            ).filter(
                Application.group_id == group.id
            ).distinct().all()
            
            result.append({
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'instance_count': instance_count,
                'servers': [{'id': s.id, 'name': s.name} for s in servers],
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None
            })
        
        return jsonify({
            'success': True,
            'groups': result
        })
    except Exception as e:
        logger.error(f"Ошибка при получении списка групп приложений: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<int:group_id>', methods=['GET'])
def get_application_group(group_id):
    """Получение информации о конкретной группе приложений"""
    try:
        from app.models.server import Server
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа приложений с id {group_id} не найдена"
            }), 404
        
        # Получаем все экземпляры приложений в группе
        applications = Application.query.filter_by(group_id=group.id).all()
        app_list = []
        
        for app in applications:
            server = Server.query.get(app.server_id)
            app_list.append({
                'id': app.id,
                'name': app.name,
                'instance_number': app.instance_number,
                'type': app.app_type,
                'status': app.status,
                'version': app.version,
                'server': {
                    'id': server.id,
                    'name': server.name,
                    'ip': server.ip
                } if server else None,
                'start_time': app.start_time.isoformat() if app.start_time else None
            })
        
        return jsonify({
            'success': True,
            'group': {
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None,
                'applications': sorted(app_list, key=lambda x: x['instance_number'])
            }
        })
    except Exception as e:
        logger.error(f"Ошибка при получении информации о группе {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<int:group_id>', methods=['PUT'])
def update_application_group(group_id):
    """Обновление параметров группы приложений (artifact_list_url, artifact_extension)"""
    try:
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа приложений с id {group_id} не найдена"
            }), 404
        
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400
        
        # Обновляем только переданные поля
        if 'artifact_list_url' in data:
            group.artifact_list_url = data['artifact_list_url']
            logger.info(f"Обновлен artifact_list_url для группы {group.name}: {data['artifact_list_url']}")
        
        if 'artifact_extension' in data:
            group.artifact_extension = data['artifact_extension']
            logger.info(f"Обновлен artifact_extension для группы {group.name}: {data['artifact_extension']}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Группа приложений {group.name} успешно обновлена",
            'group': {
                'id': group.id,
                'name': group.name,
                'artifact_list_url': group.artifact_list_url,
                'artifact_extension': group.artifact_extension,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении группы {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<int:group_id>/manage', methods=['POST'])
def manage_application_group(group_id):
    """Массовое управление всеми экземплярами группы приложений"""
    try:
        from app.tasks.queue import task_queue, Task
        group = ApplicationGroup.query.get(group_id)
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа приложений с id {group_id} не найдена"
            }), 404
        
        data = request.json
        if not data or 'action' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле action"
            }), 400
        
        action = data['action']
        valid_actions = ['start', 'stop', 'restart']
        
        if action not in valid_actions:
            return jsonify({
                'success': False,
                'error': f"Неверное действие. Допустимые значения: {', '.join(valid_actions)}"
            }), 400
        
        # Получаем все активные экземпляры приложений в группе
        applications = Application.query.filter_by(group_id=group.id).all()
        
        if not applications:
            return jsonify({
                'success': False,
                'error': f"В группе {group.name} нет приложений"
            }), 404
        
        task_ids = []
        
        for app in applications:
            # Создаем задачу для каждого экземпляра
            task = Task(
                task_type=action,
                params={},
                server_id=app.server_id,
                application_id=app.id
            )
            
            task_queue.add_task(task)
            task_ids.append(task.id)
            
            logger.info(f"Создана задача {action} для приложения {app.name} (экземпляр #{app.instance_number})")
        
        return jsonify({
            'success': True,
            'message': f"{action} для группы {group.name} поставлен в очередь",
            'task_ids': task_ids,
            'affected_instances': len(applications)
        })
    except Exception as e:
        logger.error(f"Ошибка при управлении группой {group_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ====================================
# УПРАВЛЕНИЕ PLAYBOOK ПУТЯМИ
# ====================================

@bp.route('/application-groups/<string:group_name>/playbook', methods=['GET'])
def get_group_playbook(group_name):
    """Получить путь к playbook для группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        return jsonify({
            'success': True,
            'group_name': group.name,
            'playbook_path': group.update_playbook_path,
            'effective_path': group.get_effective_playbook_path() if hasattr(group, 'get_effective_playbook_path') else group.update_playbook_path
        })
    except Exception as e:
        logger.error(f"Ошибка при получении playbook для группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<string:group_name>/playbook', methods=['PUT'])
def update_group_playbook(group_name):
    """Установить путь к playbook для группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле playbook_path"
            }), 400
        
        group.update_playbook_path = data['playbook_path']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Playbook путь для группы {group_name} обновлен",
            'playbook_path': group.update_playbook_path
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении playbook для группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ====================================
# УПРАВЛЕНИЕ НАСТРОЙКАМИ ГРУППЫ
# ====================================

@bp.route('/application-groups/<string:group_name>/settings', methods=['GET'])
def get_group_settings(group_name):
    """Получить настройки группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        return jsonify({
            'success': True,
            'group_name': group.name,
            'settings': group.group_settings or {}
        })
    except Exception as e:
        logger.error(f"Ошибка при получении настроек группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/application-groups/<string:group_name>/settings', methods=['PUT', 'PATCH'])
def update_group_settings(group_name):
    """Обновить настройки группы"""
    try:
        group = ApplicationGroup.query.filter_by(name=group_name).first()
        
        if not group:
            return jsonify({
                'success': False,
                'error': f"Группа {group_name} не найдена"
            }), 404
        
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': "Отсутствуют данные для обновления"
            }), 400
        
        if request.method == 'PUT':
            # PUT - полная замена настроек
            group.group_settings = data
        else:
            # PATCH - частичное обновление
            if not group.group_settings:
                group.group_settings = {}
            group.group_settings.update(data)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Настройки группы {group_name} обновлены",
            'settings': group.group_settings
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при обновлении настроек группы {group_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ====================================
# УПРАВЛЕНИЕ КАСТОМНЫМ PLAYBOOK ЭКЗЕМПЛЯРА
# ====================================

@bp.route('/applications/<int:app_id>/custom-playbook', methods=['PUT', 'DELETE'])
def manage_instance_playbook(app_id):
    """Установить или удалить кастомный playbook для экземпляра"""
    try:
        app = Application.query.get(app_id)
        
        if not app:
            return jsonify({
                'success': False,
                'error': f"Приложение с id {app_id} не найдено"
            }), 404
        
        if not app.instance:
            return jsonify({
                'success': False,
                'error': 'Приложение не связано с экземпляром'
            }), 400
        
        instance = app.instance
        
        if request.method == 'DELETE':
            # Удаление кастомного playbook
            instance.custom_playbook_path = None
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Кастомный playbook удален',
                'effective_playbook': instance.get_effective_playbook_path() if hasattr(instance, 'get_effective_playbook_path') else None
            })
        
        # PUT - установка кастомного playbook
        data = request.json
        if not data or 'playbook_path' not in data:
            return jsonify({
                'success': False,
                'error': "Отсутствует поле playbook_path"
            }), 400
        
        instance.custom_playbook_path = data['playbook_path']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Кастомный playbook установлен',
            'custom_playbook': instance.custom_playbook_path,
            'effective_playbook': instance.get_effective_playbook_path() if hasattr(instance, 'get_effective_playbook_path') else instance.custom_playbook_path
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при управлении playbook для приложения {app_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

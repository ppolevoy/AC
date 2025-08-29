# app/api/tags_routes.py
from flask import jsonify, request
from app import db
from app.models.application import Application
from app.models.application_group import ApplicationGroup, ApplicationInstance
from app.models.tags import Tag, ApplicationInstanceTag, ApplicationGroupTag
from app.api import bp
import logging

logger = logging.getLogger(__name__)


# ===== TAGS CRUD =====

@bp.route('/tags', methods=['GET'])
def get_tags():
    """Получить список всех тегов"""
    try:
        tags = Tag.query.order_by(Tag.category, Tag.name).all()
        
        # Группируем по категориям
        tags_by_category = {}
        for tag in tags:
            if tag.category not in tags_by_category:
                tags_by_category[tag.category] = []
            tags_by_category[tag.category].append(tag.to_dict())
        
        return jsonify({
            'success': True,
            'tags': [tag.to_dict() for tag in tags],
            'by_category': tags_by_category,
            'total': len(tags)
        })
    except Exception as e:
        logger.error(f"Error getting tags: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/tags', methods=['POST'])
def create_tag():
    """Создать новый тег"""
    try:
        data = request.get_json()
        
        # Валидация
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        
        # Проверка существования
        existing = Tag.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({'success': False, 'error': 'Tag already exists'}), 409
        
        # Создание тега
        tag = Tag(
            name=data['name'],
            category=data.get('category', Tag.CATEGORY_CUSTOM),
            color=data.get('color', '#6c757d'),
            description=data.get('description'),
            is_system=False
        )
        
        db.session.add(tag)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'tag': tag.to_dict()
        }), 201
        
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating tag: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    """Обновить тег"""
    try:
        tag = Tag.query.get_or_404(tag_id)
        
        # Защита системных тегов
        if tag.is_system:
            return jsonify({'success': False, 'error': 'Cannot modify system tag'}), 403
        
        data = request.get_json()
        
        # Обновление полей
        if 'color' in data:
            tag.color = data['color']
        if 'description' in data:
            tag.description = data['description']
        if 'category' in data:
            tag.category = data['category']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'tag': tag.to_dict()
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating tag: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    """Удалить тег"""
    try:
        tag = Tag.query.get_or_404(tag_id)
        
        # Защита системных тегов
        if tag.is_system:
            return jsonify({'success': False, 'error': 'Cannot delete system tag'}), 403
        
        db.session.delete(tag)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting tag: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ===== APPLICATION TAGS =====

@bp.route('/applications/<int:app_id>/tags', methods=['GET'])
def get_application_tags(app_id):
    """Получить теги приложения"""
    try:
        app = Application.query.get_or_404(app_id)
        
        # Получаем экземпляр приложения
        instance = ApplicationInstance.query.filter_by(application_id=app_id).first()
        
        if not instance:
            return jsonify({
                'success': True,
                'tags': [],
                'own_tags': [],
                'inherited_tags': []
            })
        
        # Импортируем миксины и добавляем методы к классу
        from app.models.tag_mixins import ApplicationInstanceTagMixin
        
        # Динамически добавляем методы (в реальном коде лучше добавить в класс напрямую)
        for method_name in dir(ApplicationInstanceTagMixin):
            if not method_name.startswith('_'):
                method = getattr(ApplicationInstanceTagMixin, method_name)
                setattr(instance.__class__, method_name, method)
        
        own_tags = instance.get_own_tags()
        inherited_tags = instance.get_inherited_tags()
        all_tags = instance.get_all_tags()
        
        return jsonify({
            'success': True,
            'tags': [tag.to_dict() for tag in all_tags],
            'own_tags': [tag.to_dict() for tag in own_tags],
            'inherited_tags': [tag.to_dict() for tag in inherited_tags]
        })
        
    except Exception as e:
        logger.error(f"Error getting application tags: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/applications/<int:app_id>/tags', methods=['POST'])
def add_application_tag(app_id):
    """Добавить тег к приложению"""
    try:
        app = Application.query.get_or_404(app_id)
        data = request.get_json()
        
        if not data.get('tag_name'):
            return jsonify({'success': False, 'error': 'tag_name is required'}), 400
        
        # Получаем или создаем экземпляр
        instance = ApplicationInstance.query.filter_by(application_id=app_id).first()
        if not instance:
            from app.services.application_group_service import ApplicationGroupService
            instance = ApplicationGroupService.determine_group_for_application(app)
        
        if not instance:
            return jsonify({'success': False, 'error': 'Could not create application instance'}), 500
        
        # Добавляем методы тегов
        from app.models.tag_mixins import ApplicationInstanceTagMixin
        for method_name in dir(ApplicationInstanceTagMixin):
            if not method_name.startswith('_'):
                method = getattr(ApplicationInstanceTagMixin, method_name)
                setattr(instance.__class__, method_name, method)
        
        # Добавляем тег
        association = instance.add_tag(
            data['tag_name'],
            assigned_by=data.get('assigned_by', 'api')
        )
        
        if association:
            return jsonify({
                'success': True,
                'message': f"Tag '{data['tag_name']}' added successfully"
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to add tag'}), 500
            
    except Exception as e:
        logger.error(f"Error adding tag to application: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/applications/<int:app_id>/tags/<string:tag_name>', methods=['DELETE'])
def remove_application_tag(app_id, tag_name):
    """Удалить тег у приложения"""
    try:
        app = Application.query.get_or_404(app_id)
        
        instance = ApplicationInstance.query.filter_by(application_id=app_id).first()
        if not instance:
            return jsonify({'success': False, 'error': 'Application instance not found'}), 404
        
        # Добавляем методы тегов
        from app.models.tag_mixins import ApplicationInstanceTagMixin
        for method_name in dir(ApplicationInstanceTagMixin):
            if not method_name.startswith('_'):
                method = getattr(ApplicationInstanceTagMixin, method_name)
                setattr(instance.__class__, method_name, method)
        
        if instance.remove_tag(tag_name):
            return jsonify({
                'success': True,
                'message': f"Tag '{tag_name}' removed successfully"
            })
        else:
            return jsonify({'success': False, 'error': 'Tag not found'}), 404
            
    except Exception as e:
        logger.error(f"Error removing tag from application: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ===== GROUP TAGS =====

@bp.route('/groups/<int:group_id>/tags', methods=['GET'])
def get_group_tags(group_id):
    """Получить теги группы"""
    try:
        group = ApplicationGroup.query.get_or_404(group_id)
        
        # Добавляем методы тегов
        from app.models.tag_mixins import ApplicationGroupTagMixin
        for method_name in dir(ApplicationGroupTagMixin):
            if not method_name.startswith('_'):
                method = getattr(ApplicationGroupTagMixin, method_name)
                setattr(group.__class__, method_name, method)
        
        tags = group.get_tags()
        
        return jsonify({
            'success': True,
            'tags': [
                {
                    **tag.to_dict(),
                    'inheritable': inheritable
                }
                for tag, inheritable in tags
            ]
        })
        
    except Exception as e:
        logger.error(f"Error getting group tags: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/groups/<int:group_id>/tags', methods=['POST'])
def add_group_tag(group_id):
    """Добавить тег к группе"""
    try:
        group = ApplicationGroup.query.get_or_404(group_id)
        data = request.get_json()
        
        if not data.get('tag_name'):
            return jsonify({'success': False, 'error': 'tag_name is required'}), 400
        
        # Добавляем методы тегов
        from app.models.tag_mixins import ApplicationGroupTagMixin
        for method_name in dir(ApplicationGroupTagMixin):
            if not method_name.startswith('_'):
                method = getattr(ApplicationGroupTagMixin, method_name)
                setattr(group.__class__, method_name, method)
        
        association = group.add_tag(
            data['tag_name'],
            inheritable=data.get('inheritable', True),
            assigned_by=data.get('assigned_by', 'api')
        )
        
        if association:
            return jsonify({
                'success': True,
                'message': f"Tag '{data['tag_name']}' added to group"
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to add tag'}), 500
            
    except Exception as e:
        logger.error(f"Error adding tag to group: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/groups/<int:group_id>/sync-tags', methods=['POST'])
def sync_group_tags(group_id):
    """Синхронизировать теги группы с экземплярами"""
    try:
        group = ApplicationGroup.query.get_or_404(group_id)
        
        # Добавляем методы тегов
        from app.models.tag_mixins import ApplicationGroupTagMixin
        for method_name in dir(ApplicationGroupTagMixin):
            if not method_name.startswith('_'):
                method = getattr(ApplicationGroupTagMixin, method_name)
                setattr(group.__class__, method_name, method)
        
        updated_count = group.sync_tags_to_instances()
        
        return jsonify({
            'success': True,
            'message': f"Synced tags to {updated_count} instances"
        })
        
    except Exception as e:
        logger.error(f"Error syncing group tags: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ===== SEARCH AND FILTER =====

@bp.route('/tags/search', methods=['POST'])
def search_by_tags():
    """Поиск приложений по тегам"""
    try:
        data = request.get_json()
        tag_names = data.get('tags', [])
        match_all = data.get('match_all', False)  # True = AND, False = OR
        
        if not tag_names:
            return jsonify({'success': False, 'error': 'No tags specified'}), 400
        
        # Получаем ID тегов
        tag_ids = db.session.query(Tag.id).filter(Tag.name.in_(tag_names)).all()
        tag_ids = [t[0] for t in tag_ids]
        
        if not tag_ids:
            return jsonify({
                'success': True,
                'applications': [],
                'count': 0
            })
        
        # Строим запрос
        query = db.session.query(Application).join(
            ApplicationInstance,
            Application.id == ApplicationInstance.application_id
        )
        
        if match_all:
            # AND логика - приложение должно иметь ВСЕ указанные теги
            for tag_id in tag_ids:
                subquery = db.session.query(ApplicationInstanceTag.instance_id).filter(
                    ApplicationInstanceTag.tag_id == tag_id
                ).union(
                    db.session.query(ApplicationInstance.id).join(
                        ApplicationGroupTag,
                        ApplicationInstance.group_id == ApplicationGroupTag.group_id
                    ).filter(
                        ApplicationGroupTag.tag_id == tag_id,
                        ApplicationGroupTag.inheritable == True
                    )
                ).subquery()
                
                query = query.filter(ApplicationInstance.id.in_(subquery))
        else:
            # OR логика - приложение должно иметь ХОТЯ БЫ ОДИН из указанных тегов
            subquery = db.session.query(ApplicationInstanceTag.instance_id).filter(
                ApplicationInstanceTag.tag_id.in_(tag_ids)
            ).union(
                db.session.query(ApplicationInstance.id).join(
                    ApplicationGroupTag,
                    ApplicationInstance.group_id == ApplicationGroupTag.group_id
                ).filter(
                    ApplicationGroupTag.tag_id.in_(tag_ids),
                    ApplicationGroupTag.inheritable == True
                )
            ).subquery()
            
            query = query.filter(ApplicationInstance.id.in_(subquery))
        
        applications = query.all()
        
        # Формируем результат
        result = []
        for app in applications:
            app_data = {
                'id': app.id,
                'name': app.name,
                'server_name': app.server.name if app.server else None,
                'status': app.status,
                'version': app.version
            }
            result.append(app_data)
        
        return jsonify({
            'success': True,
            'applications': result,
            'count': len(result)
        })
        
    except Exception as e:
        logger.error(f"Error searching by tags: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ===== BATCH OPERATIONS =====

@bp.route('/applications/batch-tag', methods=['POST'])
def batch_tag_applications():
    """Добавить тег к нескольким приложениям"""
    try:
        data = request.get_json()
        app_ids = data.get('application_ids', [])
        tag_name = data.get('tag_name')
        
        if not app_ids or not tag_name:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Получаем или создаем тег
        tag = Tag.get_or_create(tag_name)
        
        success_count = 0
        errors = []
        
        for app_id in app_ids:
            try:
                app = Application.query.get(app_id)
                if not app:
                    errors.append(f"Application {app_id} not found")
                    continue
                
                # Получаем или создаем экземпляр
                instance = ApplicationInstance.query.filter_by(application_id=app_id).first()
                if not instance:
                    from app.services.application_group_service import ApplicationGroupService
                    instance = ApplicationGroupService.determine_group_for_application(app)
                
                if instance:
                    # Добавляем методы тегов
                    from app.models.tag_mixins import ApplicationInstanceTagMixin
                    for method_name in dir(ApplicationInstanceTagMixin):
                        if not method_name.startswith('_'):
                            method = getattr(ApplicationInstanceTagMixin, method_name)
                            setattr(instance.__class__, method_name, method)
                    
                    if instance.add_tag(tag, assigned_by='batch_operation'):
                        success_count += 1
                else:
                    errors.append(f"Could not create instance for application {app_id}")
                    
            except Exception as e:
                errors.append(f"Error processing app {app_id}: {str(e)}")
        
        return jsonify({
            'success': True,
            'processed': success_count,
            'total': len(app_ids),
            'errors': errors if errors else None
        })
        
    except Exception as e:
        logger.error(f"Error in batch tag operation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
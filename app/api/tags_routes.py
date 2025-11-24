# app/api/tags_routes.py
# API endpoints для системы тегов

from flask import request, jsonify
from app import db
from app.api import bp
from app.models.tag import Tag, TagHistory
from app.models.application_instance import ApplicationInstance
from app.models.application_group import ApplicationGroup


@bp.route('/tags', methods=['GET'])
def get_tags():
    """Получить список всех тегов"""
    tags = Tag.query.all()
    return jsonify({
        'success': True,
        'tags': [tag.to_dict() for tag in tags],
        'total': len(tags)
    })


@bp.route('/tags', methods=['POST'])
def create_tag():
    """Создать новый тег"""
    data = request.json

    # Валидация
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # Нормализация имени
    name = data['name'].lower().strip().replace(' ', '-')

    # Проверка уникальности
    if Tag.query.filter_by(name=name).first():
        return jsonify({'success': False, 'error': 'Tag already exists'}), 409

    tag = Tag(
        name=name,
        display_name=data.get('display_name', data['name'].title()),
        description=data.get('description'),
        icon=data.get('icon', '●'),
        tag_type=data.get('tag_type', 'custom'),
        css_class=data.get('css_class'),
        border_color=data.get('border_color'),
        text_color=data.get('text_color')
    )

    db.session.add(tag)
    db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    }), 201


@bp.route('/tags/<int:tag_id>', methods=['GET'])
def get_tag(tag_id):
    """Получить информацию о теге"""
    tag = Tag.query.get_or_404(tag_id)
    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    })


@bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    """Обновить существующий тег"""
    tag = Tag.query.get_or_404(tag_id)
    data = request.json

    # Обновляем только переданные поля
    for field in ['display_name', 'description', 'icon', 'css_class', 'border_color', 'text_color']:
        if field in data:
            setattr(tag, field, data[field])

    db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    })


@bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    """Удалить тег"""
    tag = Tag.query.get_or_404(tag_id)

    # Записываем в историю перед удалением
    for instance in tag.instances:
        history = TagHistory(
            entity_type='instance',
            entity_id=instance.id,
            tag_id=tag.id,
            action='removed',
            changed_by='system',
            details={'reason': 'tag_deleted'}
        )
        db.session.add(history)

    for group in tag.groups:
        history = TagHistory(
            entity_type='group',
            entity_id=group.id,
            tag_id=tag.id,
            action='removed',
            changed_by='system',
            details={'reason': 'tag_deleted'}
        )
        db.session.add(history)

    db.session.delete(tag)
    db.session.commit()

    return jsonify({'success': True})


# ========== Application Instance Tags ==========

@bp.route('/applications/<int:app_id>/tags', methods=['GET'])
def get_application_tags(app_id):
    """Получить теги приложения"""
    app = ApplicationInstance.query.get_or_404(app_id)
    return jsonify({
        'success': True,
        'tags': [tag.to_dict() for tag in app.tags.all()]
    })


@bp.route('/applications/<int:app_id>/tags', methods=['POST'])
def add_application_tag(app_id):
    """Добавить тег к приложению"""
    app = ApplicationInstance.query.get_or_404(app_id)
    data = request.json

    tag_name = data.get('tag_name')
    if not tag_name:
        return jsonify({'success': False, 'error': 'tag_name is required'}), 400

    tag = app.add_tag(tag_name, user=data.get('user'))
    db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    })


@bp.route('/applications/<int:app_id>/tags/<int:tag_id>', methods=['DELETE'])
def remove_application_tag(app_id, tag_id):
    """Удалить тег у приложения"""
    app = ApplicationInstance.query.get_or_404(app_id)
    tag = Tag.query.get_or_404(tag_id)

    app.remove_tag(tag.name, user=request.args.get('user'))
    db.session.commit()

    return jsonify({'success': True})


# ========== Application Group Tags ==========

@bp.route('/app-groups/<int:group_id>/tags', methods=['GET'])
def get_group_tags(group_id):
    """Получить теги группы"""
    group = ApplicationGroup.query.get_or_404(group_id)
    return jsonify({
        'success': True,
        'tags': [tag.to_dict() for tag in group.tags.all()]
    })


@bp.route('/app-groups/<int:group_id>/tags', methods=['POST'])
def add_group_tag(group_id):
    """Добавить тег к группе"""
    group = ApplicationGroup.query.get_or_404(group_id)
    data = request.json

    tag_name = data.get('tag_name')
    if not tag_name:
        return jsonify({'success': False, 'error': 'tag_name is required'}), 400

    # Найти или создать тег
    tag = Tag.query.filter_by(name=tag_name).first()
    if not tag:
        tag = Tag(name=tag_name, display_name=tag_name.title())
        db.session.add(tag)

    if tag not in group.tags.all():
        group.tags.append(tag)

        # Обновить кэш
        group.tags_cache = ','.join(sorted([t.name for t in group.tags.all()]))

        # Запись в историю
        history = TagHistory(
            entity_type='group',
            entity_id=group.id,
            tag_id=tag.id,
            action='assigned',
            changed_by=data.get('user'),
            details={'tag_name': tag_name}
        )
        db.session.add(history)

    db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    })


@bp.route('/app-groups/<int:group_id>/tags/<int:tag_id>', methods=['DELETE'])
def remove_group_tag(group_id, tag_id):
    """Удалить тег у группы"""
    group = ApplicationGroup.query.get_or_404(group_id)
    tag = Tag.query.get_or_404(tag_id)

    if tag in group.tags.all():
        group.tags.remove(tag)

        # Обновить кэш
        group.tags_cache = ','.join(sorted([t.name for t in group.tags.all()]))

        # Запись в историю
        history = TagHistory(
            entity_type='group',
            entity_id=group.id,
            tag_id=tag.id,
            action='removed',
            changed_by=request.args.get('user')
        )
        db.session.add(history)

    db.session.commit()

    return jsonify({'success': True})


# ========== Filtering ==========

@bp.route('/applications/filter/by-tags', methods=['POST'])
def filter_by_tags():
    """Фильтрация приложений по тегам"""
    data = request.json
    tag_names = data.get('tags', [])
    operator = data.get('operator', 'OR')  # OR или AND

    query = ApplicationInstance.query.filter(ApplicationInstance.deleted_at.is_(None))

    if tag_names:
        if operator == 'AND':
            # Все теги должны присутствовать
            for tag_name in tag_names:
                query = query.filter(
                    ApplicationInstance.tags.any(Tag.name == tag_name)
                )
        else:  # OR
            # Хотя бы один тег
            query = query.filter(
                ApplicationInstance.tags.any(Tag.name.in_(tag_names))
            )

    apps = query.all()

    return jsonify({
        'success': True,
        'applications': [app.to_dict(include_tags=True) for app in apps],
        'total': len(apps),
        'filter': {
            'tags': tag_names,
            'operator': operator
        }
    })


# ========== Bulk Operations ==========

@bp.route('/tags/bulk-assign', methods=['POST'])
def bulk_assign_tags():
    """Массовое присвоение/удаление тегов"""
    data = request.json

    # Поддержка двух форматов
    tag_ids = data.get('tag_ids', [])
    tag_names = data.get('tag_names', [])
    target_type = data.get('target_type', 'instances')
    target_ids = data.get('target_ids', [])
    app_ids = data.get('app_ids', [])  # альтернативное имя для target_ids
    action = data.get('action', 'add')  # 'add' или 'remove'
    user = data.get('user')

    # Используем app_ids если target_ids не указан
    if not target_ids and app_ids:
        target_ids = app_ids

    # Получаем теги по ID или по именам
    if tag_ids:
        tags = Tag.query.filter(Tag.id.in_(tag_ids)).all()
    elif tag_names:
        tags = Tag.query.filter(Tag.name.in_(tag_names)).all()
    else:
        return jsonify({'success': False, 'error': 'tag_ids or tag_names required'}), 400

    if not target_ids:
        return jsonify({'success': False, 'error': 'target_ids or app_ids required'}), 400

    count = 0

    if target_type == 'instances':
        instances = ApplicationInstance.query.filter(ApplicationInstance.id.in_(target_ids)).all()
        for instance in instances:
            for tag in tags:
                if action == 'add':
                    if tag not in instance.tags.all():
                        instance.tags.append(tag)
                        count += 1
                        history = TagHistory(
                            entity_type='instance',
                            entity_id=instance.id,
                            tag_id=tag.id,
                            action='assigned',
                            changed_by=user,
                            details={'bulk': True}
                        )
                        db.session.add(history)
                elif action == 'remove':
                    if tag in instance.tags.all():
                        instance.tags.remove(tag)
                        count += 1
                        history = TagHistory(
                            entity_type='instance',
                            entity_id=instance.id,
                            tag_id=tag.id,
                            action='removed',
                            changed_by=user,
                            details={'bulk': True}
                        )
                        db.session.add(history)

            instance._update_tags_cache()

    elif target_type == 'groups':
        groups = ApplicationGroup.query.filter(ApplicationGroup.id.in_(target_ids)).all()
        for group in groups:
            for tag in tags:
                if action == 'add':
                    if tag not in group.tags.all():
                        group.tags.append(tag)
                        count += 1
                        history = TagHistory(
                            entity_type='group',
                            entity_id=group.id,
                            tag_id=tag.id,
                            action='assigned',
                            changed_by=user,
                            details={'bulk': True}
                        )
                        db.session.add(history)
                elif action == 'remove':
                    if tag in group.tags.all():
                        group.tags.remove(tag)
                        count += 1
                        history = TagHistory(
                            entity_type='group',
                            entity_id=group.id,
                            tag_id=tag.id,
                            action='removed',
                            changed_by=user,
                            details={'bulk': True}
                        )
                        db.session.add(history)

            group.tags_cache = ','.join(sorted([t.name for t in group.tags.all()]))

    db.session.commit()

    return jsonify({
        'success': True,
        'count': count,
        'action': action
    })


@bp.route('/tags/sync', methods=['PUT'])
def sync_tags():
    """Синхронизация тегов приложений - устанавливает желаемое состояние"""
    data = request.json

    app_ids = data.get('app_ids', [])
    desired_tags = data.get('desired_tags', [])  # список имён тегов
    user = data.get('user')

    if not app_ids:
        return jsonify({'success': False, 'error': 'app_ids required'}), 400

    # Получаем все нужные теги по именам
    desired_tag_objects = Tag.query.filter(Tag.name.in_(desired_tags)).all() if desired_tags else []
    desired_tag_names = set(t.name for t in desired_tag_objects)

    # Получаем приложения
    instances = ApplicationInstance.query.filter(ApplicationInstance.id.in_(app_ids)).all()

    added_count = 0
    removed_count = 0

    for instance in instances:
        current_tags = set(t.name for t in instance.tags.all())

        # Теги для добавления
        to_add = desired_tag_names - current_tags
        # Теги для удаления
        to_remove = current_tags - desired_tag_names

        # Добавляем новые теги
        for tag in desired_tag_objects:
            if tag.name in to_add:
                instance.tags.append(tag)
                added_count += 1
                history = TagHistory(
                    entity_type='instance',
                    entity_id=instance.id,
                    tag_id=tag.id,
                    action='assigned',
                    changed_by=user,
                    details={'sync': True}
                )
                db.session.add(history)

        # Удаляем лишние теги (создаём копию списка, т.к. модифицируем коллекцию)
        for tag in list(instance.tags.all()):
            if tag.name in to_remove:
                instance.tags.remove(tag)
                removed_count += 1
                history = TagHistory(
                    entity_type='instance',
                    entity_id=instance.id,
                    tag_id=tag.id,
                    action='removed',
                    changed_by=user,
                    details={'sync': True}
                )
                db.session.add(history)

        instance._update_tags_cache()

    db.session.commit()

    return jsonify({
        'success': True,
        'added': added_count,
        'removed': removed_count
    })


# ========== Statistics ==========

@bp.route('/tags/statistics', methods=['GET'])
def get_tag_statistics():
    """Статистика использования тегов"""
    stats = []

    for tag in Tag.query.all():
        stats.append({
            'tag': tag.to_dict(),
            'instances_count': tag.instances.count(),
            'groups_count': tag.groups.count(),
            'total_usage': tag.get_usage_count()
        })

    # Сортируем по использованию
    stats.sort(key=lambda x: x['total_usage'], reverse=True)

    return jsonify({
        'success': True,
        'statistics': stats,
        'total_tags': len(stats)
    })

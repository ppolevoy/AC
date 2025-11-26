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
    """Получить список тегов с опциональной пагинацией"""
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', 50, type=int)

    if per_page > 100:
        per_page = 100

    # Если page указан - используем пагинацию
    if page is not None:
        pagination = Tag.query.order_by(Tag.name).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return jsonify({
            'success': True,
            'tags': [tag.to_dict() for tag in pagination.items],
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages,
            'per_page': per_page
        })

    # Без page - возвращаем все (обратная совместимость)
    tags = Tag.query.order_by(Tag.name).all()
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
    """Фильтрация приложений по тегам (включая теги групп)"""
    from sqlalchemy import or_
    from app.models.tag import ApplicationInstanceTag, ApplicationGroupTag

    data = request.json
    tag_names = data.get('tags', [])
    operator = data.get('operator', 'OR')  # OR или AND

    query = ApplicationInstance.query.filter(ApplicationInstance.deleted_at.is_(None))

    if tag_names:
        if operator == 'AND':
            # AND: все теги должны быть у приложения ИЛИ его группы (в сумме)
            instances = query.options(
                db.joinedload(ApplicationInstance.group)
            ).all()

            filtered = []
            tag_names_set = set(tag_names)
            for inst in instances:
                all_tags = set(t.name for t in inst.tags.all())
                if inst.group:
                    all_tags.update(t.name for t in inst.group.tags.all())
                if tag_names_set.issubset(all_tags):
                    filtered.append(inst)

            return jsonify({
                'success': True,
                'applications': [app.to_dict(include_tags=True) for app in filtered],
                'total': len(filtered),
                'filter': {'tags': tag_names, 'operator': operator}
            })
        else:  # OR
            # Подзапрос для приложений с нужными тегами
            instance_subq = db.session.query(
                ApplicationInstanceTag.application_id
            ).join(Tag).filter(Tag.name.in_(tag_names)).scalar_subquery()

            # Подзапрос для групп с нужными тегами
            group_subq = db.session.query(
                ApplicationGroupTag.group_id
            ).join(Tag).filter(Tag.name.in_(tag_names)).scalar_subquery()

            query = query.filter(
                or_(
                    ApplicationInstance.id.in_(instance_subq),
                    ApplicationInstance.group_id.in_(group_subq)
                )
            )

    apps = query.all()

    return jsonify({
        'success': True,
        'applications': [app.to_dict(include_tags=True) for app in apps],
        'total': len(apps),
        'filter': {'tags': tag_names, 'operator': operator}
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
        # Предзагружаем теги для избежания N+1
        instance_tags = {inst.id: set(t.id for t in inst.tags) for inst in instances}

        for instance in instances:
            current_tag_ids = instance_tags[instance.id]
            for tag in tags:
                if action == 'add':
                    if tag.id not in current_tag_ids:
                        instance.tags.append(tag)
                        current_tag_ids.add(tag.id)
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
                    if tag.id in current_tag_ids:
                        instance.tags.remove(tag)
                        current_tag_ids.discard(tag.id)
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

    elif target_type == 'groups':
        groups = ApplicationGroup.query.filter(ApplicationGroup.id.in_(target_ids)).all()
        # Предзагружаем теги для избежания N+1
        group_tags = {grp.id: set(t.id for t in grp.tags) for grp in groups}

        for group in groups:
            current_tag_ids = group_tags[group.id]
            for tag in tags:
                if action == 'add':
                    if tag.id not in current_tag_ids:
                        group.tags.append(tag)
                        current_tag_ids.add(tag.id)
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
                    if tag.id in current_tag_ids:
                        group.tags.remove(tag)
                        current_tag_ids.discard(tag.id)
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

    # Предзагружаем теги для избежания N+1
    instance_current_tags = {
        inst.id: {t.name: t for t in inst.tags}
        for inst in instances
    }

    added_count = 0
    removed_count = 0

    for instance in instances:
        current_tags_dict = instance_current_tags[instance.id]
        current_tag_names = set(current_tags_dict.keys())

        to_add = desired_tag_names - current_tag_names
        to_remove = current_tag_names - desired_tag_names

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

        # Удаляем лишние теги
        for tag_name in to_remove:
            tag = current_tags_dict[tag_name]
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

    db.session.commit()

    return jsonify({
        'success': True,
        'added': added_count,
        'removed': removed_count
    })


# ========== Statistics ==========

@bp.route('/tags/statistics', methods=['GET'])
def get_tag_statistics():
    """Статистика использования тегов (оптимизированная)"""
    from sqlalchemy import func
    from app.models.tag import ApplicationInstanceTag, ApplicationGroupTag

    # Подзапрос для подсчёта instances
    instances_subq = db.session.query(
        ApplicationInstanceTag.tag_id,
        func.count(ApplicationInstanceTag.id).label('instances_count')
    ).group_by(ApplicationInstanceTag.tag_id).subquery()

    # Подзапрос для подсчёта groups
    groups_subq = db.session.query(
        ApplicationGroupTag.tag_id,
        func.count(ApplicationGroupTag.id).label('groups_count')
    ).group_by(ApplicationGroupTag.tag_id).subquery()

    # Основной запрос с JOIN
    results = db.session.query(
        Tag,
        func.coalesce(instances_subq.c.instances_count, 0).label('instances_count'),
        func.coalesce(groups_subq.c.groups_count, 0).label('groups_count')
    ).outerjoin(
        instances_subq, Tag.id == instances_subq.c.tag_id
    ).outerjoin(
        groups_subq, Tag.id == groups_subq.c.tag_id
    ).all()

    stats = []
    for tag, instances_count, groups_count in results:
        total_usage = instances_count + groups_count
        stats.append({
            'tag': tag.to_dict(),
            'instances_count': instances_count,
            'groups_count': groups_count,
            'total_usage': total_usage
        })

    stats.sort(key=lambda x: x['total_usage'], reverse=True)

    return jsonify({
        'success': True,
        'statistics': stats,
        'total_tags': len(stats)
    })


# ========== Tag History ==========

@bp.route('/applications/<int:app_id>/tag-history', methods=['GET'])
def get_application_tag_history(app_id):
    """История тегов приложения"""
    app = ApplicationInstance.query.get_or_404(app_id)

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 100)

    pagination = TagHistory.query.filter_by(
        entity_type='instance',
        entity_id=app_id
    ).order_by(TagHistory.changed_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Предзагружаем теги для истории
    tag_ids = [h.tag_id for h in pagination.items if h.tag_id]
    tags_dict = {t.id: t for t in Tag.query.filter(Tag.id.in_(tag_ids)).all()} if tag_ids else {}

    history = []
    for h in pagination.items:
        tag = tags_dict.get(h.tag_id)
        history.append({
            'id': h.id,
            'tag_id': h.tag_id,
            'tag_name': tag.name if tag else None,
            'tag_display_name': tag.display_name if tag else None,
            'action': h.action,
            'changed_by': h.changed_by,
            'changed_at': h.changed_at.isoformat() if h.changed_at else None,
            'details': h.details
        })

    return jsonify({
        'success': True,
        'history': history,
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })


@bp.route('/app-groups/<int:group_id>/tag-history', methods=['GET'])
def get_group_tag_history(group_id):
    """История тегов группы"""
    group = ApplicationGroup.query.get_or_404(group_id)

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 100)

    pagination = TagHistory.query.filter_by(
        entity_type='group',
        entity_id=group_id
    ).order_by(TagHistory.changed_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    tag_ids = [h.tag_id for h in pagination.items if h.tag_id]
    tags_dict = {t.id: t for t in Tag.query.filter(Tag.id.in_(tag_ids)).all()} if tag_ids else {}

    history = []
    for h in pagination.items:
        tag = tags_dict.get(h.tag_id)
        history.append({
            'id': h.id,
            'tag_id': h.tag_id,
            'tag_name': tag.name if tag else None,
            'tag_display_name': tag.display_name if tag else None,
            'action': h.action,
            'changed_by': h.changed_by,
            'changed_at': h.changed_at.isoformat() if h.changed_at else None,
            'details': h.details
        })

    return jsonify({
        'success': True,
        'history': history,
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })


@bp.route('/tags/<int:tag_id>/history', methods=['GET'])
def get_tag_usage_history(tag_id):
    """История использования конкретного тега"""
    tag = Tag.query.get_or_404(tag_id)

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 100)

    pagination = TagHistory.query.filter_by(
        tag_id=tag_id
    ).order_by(TagHistory.changed_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    history = []
    for h in pagination.items:
        history.append({
            'id': h.id,
            'entity_type': h.entity_type,
            'entity_id': h.entity_id,
            'action': h.action,
            'changed_by': h.changed_by,
            'changed_at': h.changed_at.isoformat() if h.changed_at else None,
            'details': h.details
        })

    return jsonify({
        'success': True,
        'tag': tag.to_dict(),
        'history': history,
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages
    })

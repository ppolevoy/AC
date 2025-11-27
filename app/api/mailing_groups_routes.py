# app/api/mailing_groups_routes.py
# API endpoints для управления группами рассылки

from flask import request, jsonify
from app import db
from app.api import bp
from app.models.mailing_group import MailingGroup


@bp.route('/mailing-groups', methods=['GET'])
def get_mailing_groups():
    """Получить список всех групп рассылки"""
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

    query = MailingGroup.query
    if not include_inactive:
        query = query.filter(MailingGroup.is_active == True)

    groups = query.order_by(MailingGroup.name).all()

    return jsonify({
        'success': True,
        'groups': [group.to_dict() for group in groups],
        'total': len(groups)
    })


@bp.route('/mailing-groups/<int:group_id>', methods=['GET'])
def get_mailing_group(group_id):
    """Получить информацию о группе рассылки по ID"""
    group = MailingGroup.query.get_or_404(group_id)
    return jsonify({
        'success': True,
        'group': group.to_dict()
    })


@bp.route('/mailing-groups', methods=['POST'])
def create_mailing_group():
    """Создать новую группу рассылки"""
    data = request.json

    # Валидация обязательных полей
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Имя группы обязательно'}), 400

    if not data.get('emails'):
        return jsonify({'success': False, 'error': 'Список email-адресов обязателен'}), 400

    # Нормализация имени (без пробелов, lowercase)
    name = data['name'].strip().lower().replace(' ', '_')

    # Проверка уникальности имени
    existing = MailingGroup.query.filter(
        db.func.lower(MailingGroup.name) == name
    ).first()
    if existing:
        return jsonify({
            'success': False,
            'error': f'Группа с именем "{name}" уже существует'
        }), 409

    # Обработка emails - может быть строкой или списком
    emails = data['emails']
    if isinstance(emails, list):
        emails = ','.join(emails)

    group = MailingGroup(
        name=name,
        description=data.get('description', ''),
        emails=emails,
        is_active=data.get('is_active', True)
    )

    # Валидация email-адресов
    valid_emails, invalid_emails = group.validate_emails()
    if invalid_emails:
        return jsonify({
            'success': False,
            'error': f'Некорректные email-адреса: {", ".join(invalid_emails)}',
            'invalid_emails': invalid_emails
        }), 400

    db.session.add(group)
    db.session.commit()

    return jsonify({
        'success': True,
        'group': group.to_dict()
    }), 201


@bp.route('/mailing-groups/<int:group_id>', methods=['PUT'])
def update_mailing_group(group_id):
    """Обновить группу рассылки"""
    group = MailingGroup.query.get_or_404(group_id)
    data = request.json

    # Обновляем имя если передано
    if 'name' in data:
        new_name = data['name'].strip().lower().replace(' ', '_')
        # Проверяем уникальность нового имени
        existing = MailingGroup.query.filter(
            db.func.lower(MailingGroup.name) == new_name,
            MailingGroup.id != group_id
        ).first()
        if existing:
            return jsonify({
                'success': False,
                'error': f'Группа с именем "{new_name}" уже существует'
            }), 409
        group.name = new_name

    # Обновляем описание
    if 'description' in data:
        group.description = data['description']

    # Обновляем emails
    if 'emails' in data:
        emails = data['emails']
        if isinstance(emails, list):
            emails = ','.join(emails)
        group.emails = emails

        # Валидация email-адресов
        valid_emails, invalid_emails = group.validate_emails()
        if invalid_emails:
            return jsonify({
                'success': False,
                'error': f'Некорректные email-адреса: {", ".join(invalid_emails)}',
                'invalid_emails': invalid_emails
            }), 400

    # Обновляем статус активности
    if 'is_active' in data:
        group.is_active = bool(data['is_active'])

    db.session.commit()

    return jsonify({
        'success': True,
        'group': group.to_dict()
    })


@bp.route('/mailing-groups/<int:group_id>', methods=['DELETE'])
def delete_mailing_group(group_id):
    """Удалить группу рассылки"""
    group = MailingGroup.query.get_or_404(group_id)

    db.session.delete(group)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Группа "{group.name}" удалена'
    })


@bp.route('/mailing-groups/resolve', methods=['GET'])
def resolve_recipients():
    """
    Разрешить список получателей в email-адреса.

    Query params:
        recipients: строка с получателями через запятую (email или имена групп)

    Returns:
        Список уникальных email-адресов
    """
    recipients_str = request.args.get('recipients', '')
    if not recipients_str:
        return jsonify({
            'success': False,
            'error': 'Параметр recipients обязателен'
        }), 400

    # Парсим получателей
    recipients = [r.strip() for r in recipients_str.split(',') if r.strip()]

    # Разрешаем имена групп в email-адреса
    resolved = MailingGroup.resolve_recipients(recipients)

    return jsonify({
        'success': True,
        'original': recipients,
        'resolved': resolved,
        'count': len(resolved)
    })


@bp.route('/mailing-groups/by-name/<name>', methods=['GET'])
def get_mailing_group_by_name(name):
    """Получить группу рассылки по имени"""
    group = MailingGroup.find_by_name(name)
    if not group:
        return jsonify({
            'success': False,
            'error': f'Группа "{name}" не найдена'
        }), 404

    return jsonify({
        'success': True,
        'group': group.to_dict()
    })


@bp.route('/mailing-groups/<int:group_id>/validate', methods=['GET'])
def validate_mailing_group(group_id):
    """Проверить валидность email-адресов в группе"""
    group = MailingGroup.query.get_or_404(group_id)

    valid_emails, invalid_emails = group.validate_emails()

    return jsonify({
        'success': True,
        'group_name': group.name,
        'valid_emails': valid_emails,
        'invalid_emails': invalid_emails,
        'valid_count': len(valid_emails),
        'invalid_count': len(invalid_emails),
        'is_fully_valid': len(invalid_emails) == 0
    })

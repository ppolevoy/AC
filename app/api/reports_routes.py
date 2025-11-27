# app/api/reports_routes.py
# API endpoints для отчётов о версиях приложений

from flask import request, jsonify, Response
from datetime import datetime, timedelta
from sqlalchemy import func
import csv
import io
import json

from app import db
from app.api import bp
from app.models.application_instance import ApplicationInstance
from app.models.application_group import ApplicationGroup
from app.models.application_catalog import ApplicationCatalog
from app.models.server import Server
from app.models.application_version_history import ApplicationVersionHistory


# ========== Отчёт: Текущие версии ==========

@bp.route('/reports/current-versions', methods=['GET'])
def get_current_versions_report():
    """
    Получить отчёт о текущих версиях всех приложений

    Query params:
        server_ids: список ID серверов (через запятую)
        catalog_ids: список ID приложений из словаря (через запятую)
        app_type: тип приложения (docker, site, service)
        sort_by: поле сортировки (name, server, status, updated)
        sort_order: направление (asc, desc)
    """
    # Парсинг параметров фильтрации
    server_ids = request.args.get('server_ids')
    if server_ids:
        server_ids = [int(x) for x in server_ids.split(',') if x.strip().isdigit()]

    catalog_ids = request.args.get('catalog_ids')
    if catalog_ids:
        catalog_ids = [int(x) for x in catalog_ids.split(',') if x.strip().isdigit()]

    app_type = request.args.get('app_type')

    # Сортировка
    sort_by = request.args.get('sort_by', 'name')
    sort_order = request.args.get('sort_order', 'asc')

    # Построение запроса
    query = ApplicationInstance.query.filter(
        ApplicationInstance.deleted_at.is_(None)
    )

    if server_ids:
        query = query.filter(ApplicationInstance.server_id.in_(server_ids))

    if catalog_ids:
        query = query.filter(ApplicationInstance.catalog_id.in_(catalog_ids))

    if app_type:
        query = query.filter(ApplicationInstance.app_type == app_type)

    # Определение сортировки
    sort_column = {
        'name': ApplicationInstance.instance_name,
        'server': ApplicationInstance.server_id,
        'updated': ApplicationInstance.updated_at
    }.get(sort_by, ApplicationInstance.instance_name)

    if sort_order == 'desc':
        query = query.order_by(sort_column.desc().nulls_last())
    else:
        query = query.order_by(sort_column.asc().nulls_last())

    # Получаем все записи (без пагинации)
    applications = query.all()

    # Формирование результата
    data = []
    for app in applications:
        data.append({
            'id': app.id,
            'instance_name': app.instance_name,
            'app_type': app.app_type,
            'version': app.version,
            'tag': app.tag,
            'image': app.image,
            'distr_path': app.distr_path,
            'server_id': app.server_id,
            'server_name': app.server.name if app.server else None,
            'catalog_id': app.catalog_id,
            'catalog_name': app.catalog.name if app.catalog else None,
            'updated_at': app.updated_at.isoformat() if app.updated_at else None,
            'last_seen': app.last_seen.isoformat() if app.last_seen else None
        })

    return jsonify({
        'success': True,
        'data': data,
        'total': len(data)
    })


@bp.route('/reports/current-versions/export', methods=['GET'])
def export_current_versions():
    """
    Экспорт отчёта о текущих версиях в CSV или JSON

    Query params:
        format: csv или json (по умолчанию json)
        + все параметры фильтрации из get_current_versions_report
    """
    export_format = request.args.get('format', 'json').lower()

    # Парсинг параметров фильтрации
    server_ids = request.args.get('server_ids')
    if server_ids:
        server_ids = [int(x) for x in server_ids.split(',') if x.strip().isdigit()]

    catalog_ids = request.args.get('catalog_ids')
    if catalog_ids:
        catalog_ids = [int(x) for x in catalog_ids.split(',') if x.strip().isdigit()]

    app_type = request.args.get('app_type')

    # Построение запроса
    query = ApplicationInstance.query.filter(
        ApplicationInstance.deleted_at.is_(None)
    )

    if server_ids:
        query = query.filter(ApplicationInstance.server_id.in_(server_ids))

    if catalog_ids:
        query = query.filter(ApplicationInstance.catalog_id.in_(catalog_ids))

    if app_type:
        query = query.filter(ApplicationInstance.app_type == app_type)

    applications = query.order_by(
        ApplicationInstance.server_id,
        ApplicationInstance.instance_name
    ).all()

    # Формирование данных
    data = []
    for app in applications:
        data.append({
            'instance_name': app.instance_name,
            'app_type': app.app_type,
            'version': app.version or app.tag or '',
            'server_name': app.server.name if app.server else '',
            'distr_path': app.distr_path or '',
            'updated_at': app.updated_at.isoformat() if app.updated_at else ''
        })

    if export_format == 'csv':
        # CSV экспорт с BOM и разделителем ; для Excel
        output = io.StringIO()
        output.write('\ufeff')  # BOM для корректного отображения UTF-8 в Excel
        writer = csv.DictWriter(output, fieldnames=[
            'instance_name', 'app_type', 'version',
            'server_name', 'distr_path', 'updated_at'
        ], delimiter=';')
        writer.writeheader()
        writer.writerows(data)

        return Response(
            output.getvalue(),
            mimetype='text/csv; charset=utf-8-sig',
            headers={
                'Content-Disposition': f'attachment; filename=current_versions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
    else:
        # JSON экспорт
        return Response(
            json.dumps({'data': data, 'exported_at': datetime.now().isoformat()}, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename=current_versions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            }
        )


# ========== Отчёт: История изменений версий ==========

@bp.route('/reports/version-history', methods=['GET'])
def get_version_history_report():
    """
    Получить отчёт об истории изменений версий

    Query params:
        server_ids: список ID серверов
        catalog_ids: список ID приложений из словаря
        instance_ids: список ID экземпляров
        date_from: начало периода (ISO формат)
        date_to: конец периода (ISO формат)
        changed_by: фильтр по источнику изменения (user, agent)
        sort_by: поле сортировки (name, server, changed_at)
        sort_order: направление (asc, desc)
    """
    # Парсинг параметров фильтрации
    server_ids = request.args.get('server_ids')
    if server_ids:
        server_ids = [int(x) for x in server_ids.split(',') if x.strip().isdigit()]

    catalog_ids = request.args.get('catalog_ids')
    if catalog_ids:
        catalog_ids = [int(x) for x in catalog_ids.split(',') if x.strip().isdigit()]

    instance_ids = request.args.get('instance_ids')
    if instance_ids:
        instance_ids = [int(x) for x in instance_ids.split(',') if x.strip().isdigit()]

    date_from = request.args.get('date_from')
    if date_from:
        try:
            date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        except ValueError:
            date_from = None

    date_to = request.args.get('date_to')
    if date_to:
        try:
            date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        except ValueError:
            date_to = None

    changed_by = request.args.get('changed_by')

    # Сортировка
    sort_by = request.args.get('sort_by', 'changed_at')
    sort_order = request.args.get('sort_order', 'desc')

    # Построение запроса
    query = ApplicationVersionHistory.query.join(
        ApplicationInstance,
        ApplicationVersionHistory.instance_id == ApplicationInstance.id
    )

    if server_ids:
        query = query.filter(ApplicationInstance.server_id.in_(server_ids))

    if catalog_ids:
        query = query.filter(ApplicationInstance.catalog_id.in_(catalog_ids))

    if instance_ids:
        query = query.filter(ApplicationVersionHistory.instance_id.in_(instance_ids))

    if date_from:
        query = query.filter(ApplicationVersionHistory.changed_at >= date_from)

    if date_to:
        query = query.filter(ApplicationVersionHistory.changed_at <= date_to)

    if changed_by:
        query = query.filter(ApplicationVersionHistory.changed_by == changed_by)

    # Определение сортировки
    sort_column = {
        'name': ApplicationInstance.instance_name,
        'server': ApplicationInstance.server_id,
        'changed_at': ApplicationVersionHistory.changed_at
    }.get(sort_by, ApplicationVersionHistory.changed_at)

    if sort_order == 'desc':
        query = query.order_by(sort_column.desc().nulls_last())
    else:
        query = query.order_by(sort_column.asc().nulls_last())

    # Получаем все записи (без пагинации, с лимитом)
    history_records = query.limit(5000).all()

    # Формирование результата
    data = []
    for history in history_records:
        data.append(history.to_dict(include_instance=True))

    return jsonify({
        'success': True,
        'data': data,
        'total': len(data)
    })


@bp.route('/reports/version-history/export', methods=['GET'])
def export_version_history():
    """
    Экспорт истории изменений версий в CSV или JSON

    Query params:
        format: csv или json (по умолчанию json)
        + все параметры фильтрации из get_version_history_report
    """
    export_format = request.args.get('format', 'json').lower()

    # Парсинг параметров
    server_ids = request.args.get('server_ids')
    if server_ids:
        server_ids = [int(x) for x in server_ids.split(',') if x.strip().isdigit()]

    catalog_ids = request.args.get('catalog_ids')
    if catalog_ids:
        catalog_ids = [int(x) for x in catalog_ids.split(',') if x.strip().isdigit()]

    date_from = request.args.get('date_from')
    if date_from:
        try:
            date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        except ValueError:
            date_from = None

    date_to = request.args.get('date_to')
    if date_to:
        try:
            date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        except ValueError:
            date_to = None

    changed_by = request.args.get('changed_by')

    # Построение запроса
    query = ApplicationVersionHistory.query.join(
        ApplicationInstance,
        ApplicationVersionHistory.instance_id == ApplicationInstance.id
    )

    if server_ids:
        query = query.filter(ApplicationInstance.server_id.in_(server_ids))

    if catalog_ids:
        query = query.filter(ApplicationInstance.catalog_id.in_(catalog_ids))

    if date_from:
        query = query.filter(ApplicationVersionHistory.changed_at >= date_from)

    if date_to:
        query = query.filter(ApplicationVersionHistory.changed_at <= date_to)

    if changed_by:
        query = query.filter(ApplicationVersionHistory.changed_by == changed_by)

    # Лимит для экспорта
    history_records = query.order_by(
        ApplicationVersionHistory.changed_at.desc()
    ).limit(10000).all()

    # Формирование данных
    data = []
    for history in history_records:
        data.append({
            'instance_name': history.instance.instance_name if history.instance else '',
            'server_name': history.instance.server.name if history.instance and history.instance.server else '',
            'old_version': history.old_version or '',
            'new_version': history.new_version or '',
            'old_distr_path': history.old_distr_path or '',
            'new_distr_path': history.new_distr_path or '',
            'changed_at': history.changed_at.isoformat() if history.changed_at else '',
            'changed_by': history.changed_by or '',
            'change_source': history.change_source or ''
        })

    if export_format == 'csv':
        # CSV экспорт с BOM и разделителем ; для Excel
        output = io.StringIO()
        output.write('\ufeff')  # BOM для корректного отображения UTF-8 в Excel
        writer = csv.DictWriter(output, fieldnames=[
            'instance_name', 'server_name',
            'old_version', 'new_version', 'old_distr_path', 'new_distr_path',
            'changed_at', 'changed_by', 'change_source'
        ], delimiter=';')
        writer.writeheader()
        writer.writerows(data)

        return Response(
            output.getvalue(),
            mimetype='text/csv; charset=utf-8-sig',
            headers={
                'Content-Disposition': f'attachment; filename=version_history_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
    else:
        return Response(
            json.dumps({'data': data, 'exported_at': datetime.now().isoformat()}, ensure_ascii=False, indent=2),
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename=version_history_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            }
        )


# ========== Вспомогательные endpoints ==========

@bp.route('/reports/filters', methods=['GET'])
def get_report_filters():
    """Получить данные для фильтров отчётов"""
    servers = Server.query.order_by(Server.name).all()
    catalogs = ApplicationCatalog.query.order_by(ApplicationCatalog.name).all()

    return jsonify({
        'success': True,
        'servers': [{'id': s.id, 'name': s.name} for s in servers],
        'catalogs': [{'id': c.id, 'name': c.name} for c in catalogs],
        'app_types': ['docker', 'site', 'service'],
        'change_sources': ['user', 'agent', 'system']
    })


@bp.route('/reports/version-history/statistics', methods=['GET'])
def get_version_history_statistics():
    """Статистика изменений версий за период"""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    if date_from:
        try:
            date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        except ValueError:
            date_from = datetime.now() - timedelta(days=30)
    else:
        date_from = datetime.now() - timedelta(days=30)

    if date_to:
        try:
            date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        except ValueError:
            date_to = datetime.now()
    else:
        date_to = datetime.now()

    # Общее количество изменений
    total_changes = ApplicationVersionHistory.query.filter(
        ApplicationVersionHistory.changed_at.between(date_from, date_to)
    ).count()

    # Изменения по источникам
    by_source = db.session.query(
        ApplicationVersionHistory.changed_by,
        func.count(ApplicationVersionHistory.id)
    ).filter(
        ApplicationVersionHistory.changed_at.between(date_from, date_to)
    ).group_by(ApplicationVersionHistory.changed_by).all()

    # Топ приложений по количеству обновлений
    top_apps = db.session.query(
        ApplicationInstance.instance_name,
        func.count(ApplicationVersionHistory.id).label('updates_count')
    ).join(
        ApplicationVersionHistory,
        ApplicationVersionHistory.instance_id == ApplicationInstance.id
    ).filter(
        ApplicationVersionHistory.changed_at.between(date_from, date_to)
    ).group_by(
        ApplicationInstance.id, ApplicationInstance.instance_name
    ).order_by(
        func.count(ApplicationVersionHistory.id).desc()
    ).limit(10).all()

    return jsonify({
        'success': True,
        'period': {
            'from': date_from.isoformat(),
            'to': date_to.isoformat()
        },
        'total_changes': total_changes,
        'by_source': {source: count for source, count in by_source},
        'top_applications': [
            {'name': name, 'updates_count': count}
            for name, count in top_apps
        ]
    })

# app/services/report_mailer.py
# Сервис рассылки отчётов по email

import subprocess
import csv
import io
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Any
from flask import current_app, render_template_string

from app import db
from app.models.application_instance import ApplicationInstance
from app.models.application_version_history import ApplicationVersionHistory
from app.models.mailing_group import MailingGroup

logger = logging.getLogger(__name__)


class ReportMailerService:
    """Сервис для генерации и отправки отчётов по email"""

    # HTML шаблон для отчётов
    EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h2 { color: #333; border-bottom: 2px solid #4a5568; padding-bottom: 10px; }
        .meta { color: #666; margin-bottom: 20px; font-size: 14px; }
        table { border-collapse: collapse; width: 100%; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background-color: #4a5568; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        tr:hover { background-color: #f0f0f0; }
        .footer { margin-top: 20px; padding-top: 15px; border-top: 1px solid #ddd; color: #888; font-size: 12px; }
        .version { font-family: monospace; background-color: #e2e8f0; padding: 2px 6px; border-radius: 4px; }
        .type-docker { background-color: #3182ce; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .type-site { background-color: #38a169; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .type-service { background-color: #805ad5; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
        .change-arrow { color: #4a5568; margin: 0 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>{{ title }}</h2>
        <div class="meta">
            <p>Дата генерации: {{ generated_at }}</p>
            {% if filters_info %}
            <p>Фильтры: {{ filters_info }}</p>
            {% endif %}
        </div>
        {{ table_html | safe }}
        <div class="footer">
            <p>Отчёт сгенерирован системой Application Control</p>
            <p>Всего записей: {{ total_records }}</p>
        </div>
    </div>
</body>
</html>
"""

    def __init__(self):
        pass

    def resolve_recipients(self, recipients: List[str]) -> List[str]:
        """
        Разрешает список получателей в email-адреса.
        Поддерживает как прямые email, так и имена групп рассылки.
        """
        return MailingGroup.resolve_recipients(recipients)

    def send_current_versions_report(
        self,
        recipients: List[str],
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Отправить отчёт о текущих версиях приложений.

        Args:
            recipients: Список получателей (email или имена групп)
            filters: Фильтры (server_ids, catalog_ids, app_type)

        Returns:
            Результат отправки
        """
        filters = filters or {}

        # Получаем данные
        data = self._get_current_versions_data(filters)

        if not data:
            return {
                'success': False,
                'error': 'Нет данных для отчёта с заданными фильтрами'
            }

        # Генерируем HTML
        html_content = self._generate_current_versions_html(data, filters)

        # Генерируем CSV
        csv_content = self._generate_current_versions_csv(data)

        # Формируем тему письма
        subject = f"{current_app.config.get('REPORT_EMAIL_SUBJECT_PREFIX', '[AC Report]')} Текущие версии приложений"

        # Разрешаем получателей
        resolved_recipients = self.resolve_recipients(recipients)

        if not resolved_recipients:
            return {
                'success': False,
                'error': 'Не найдено ни одного email-адреса для отправки'
            }

        # Отправляем
        result = self._send_email(
            to=resolved_recipients,
            subject=subject,
            html_body=html_content,
            attachments=[{
                'filename': f'current_versions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                'content': csv_content,
                'content_type': 'text/csv'
            }]
        )

        result['recipients_count'] = len(resolved_recipients)
        result['resolved_recipients'] = resolved_recipients
        result['records_count'] = len(data)

        return result

    def send_version_history_report(
        self,
        recipients: List[str],
        filters: Optional[Dict] = None,
        period: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Отправить отчёт об истории изменений версий.

        Args:
            recipients: Список получателей (email или имена групп)
            filters: Фильтры (server_ids, catalog_ids)
            period: Период в виде dict:
                - date_from/date_to: конкретные даты (ISO формат)
                - days: количество дней назад

        Returns:
            Результат отправки
        """
        filters = filters or {}
        period = period or {}

        # Определяем период
        date_to = datetime.now()
        period_text = 'за последний день'

        if period.get('date_from'):
            try:
                date_from = datetime.fromisoformat(period['date_from'].replace('Z', '+00:00'))
                if period.get('date_to'):
                    date_to = datetime.fromisoformat(period['date_to'].replace('Z', '+00:00'))
                period_text = f"с {date_from.strftime('%Y-%m-%d')} по {date_to.strftime('%Y-%m-%d')}"
            except ValueError:
                date_from = datetime.now() - timedelta(days=1)
        elif period.get('days'):
            days = int(period['days'])
            date_from = datetime.now() - timedelta(days=days)
            period_text = f'за последние {days} дней'
        else:
            date_from = datetime.now() - timedelta(days=1)

        # Получаем данные
        data = self._get_version_history_data(filters, date_from)

        if not data:
            return {
                'success': False,
                'error': f'Нет изменений {period_text}'
            }

        # Генерируем HTML
        html_content = self._generate_version_history_html(data, filters, period_text)

        # Генерируем CSV
        csv_content = self._generate_version_history_csv(data)

        # Формируем тему письма
        subject = f"{current_app.config.get('REPORT_EMAIL_SUBJECT_PREFIX', '[AC Report]')} История изменений {period_text}"

        # Разрешаем получателей
        resolved_recipients = self.resolve_recipients(recipients)

        if not resolved_recipients:
            return {
                'success': False,
                'error': 'Не найдено ни одного email-адреса для отправки'
            }

        # Отправляем
        result = self._send_email(
            to=resolved_recipients,
            subject=subject,
            html_body=html_content,
            attachments=[{
                'filename': f'version_history_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                'content': csv_content,
                'content_type': 'text/csv'
            }]
        )

        result['recipients_count'] = len(resolved_recipients)
        result['resolved_recipients'] = resolved_recipients
        result['records_count'] = len(data)

        return result

    def _get_current_versions_data(self, filters: Dict) -> List[Dict]:
        """Получить данные о текущих версиях"""
        query = ApplicationInstance.query.filter(
            ApplicationInstance.deleted_at.is_(None)
        )

        if filters.get('server_ids'):
            query = query.filter(ApplicationInstance.server_id.in_(filters['server_ids']))

        if filters.get('catalog_ids'):
            query = query.filter(ApplicationInstance.catalog_id.in_(filters['catalog_ids']))

        if filters.get('app_type'):
            query = query.filter(ApplicationInstance.app_type == filters['app_type'])

        applications = query.order_by(
            ApplicationInstance.server_id,
            ApplicationInstance.instance_name
        ).all()

        data = []
        for app in applications:
            data.append({
                'instance_name': app.instance_name,
                'app_type': app.app_type,
                'version': app.version or app.tag or '-',
                'server_name': app.server.name if app.server else '-',
                'distr_path': app.distr_path or '-',
                'updated_at': app.updated_at.strftime('%Y-%m-%d %H:%M') if app.updated_at else '-'
            })

        return data

    def _get_version_history_data(self, filters: Dict, date_from: datetime) -> List[Dict]:
        """Получить данные об истории изменений"""
        query = ApplicationVersionHistory.query.join(
            ApplicationInstance,
            ApplicationVersionHistory.instance_id == ApplicationInstance.id
        ).filter(
            ApplicationVersionHistory.changed_at >= date_from
        )

        if filters.get('server_ids'):
            query = query.filter(ApplicationInstance.server_id.in_(filters['server_ids']))

        if filters.get('catalog_ids'):
            query = query.filter(ApplicationInstance.catalog_id.in_(filters['catalog_ids']))

        history_records = query.order_by(
            ApplicationVersionHistory.changed_at.desc()
        ).limit(1000).all()

        data = []
        for history in history_records:
            data.append({
                'instance_name': history.instance.instance_name if history.instance else '-',
                'server_name': history.instance.server.name if history.instance and history.instance.server else '-',
                'old_version': history.old_version or '-',
                'new_version': history.new_version or '-',
                'changed_at': history.changed_at.strftime('%Y-%m-%d %H:%M') if history.changed_at else '-',
                'changed_by': history.changed_by or '-',
                'change_source': history.change_source or '-'
            })

        return data

    def _generate_current_versions_html(self, data: List[Dict], filters: Dict) -> str:
        """Генерировать HTML для отчёта о текущих версиях"""
        table_html = """
        <table>
            <thead>
                <tr>
                    <th>Приложение</th>
                    <th>Тип</th>
                    <th>Сервер</th>
                    <th>Версия</th>
                    <th>Обновлено</th>
                </tr>
            </thead>
            <tbody>
        """

        for row in data:
            type_class = f"type-{row['app_type']}" if row['app_type'] else ""
            table_html += f"""
                <tr>
                    <td>{self._escape_html(row['instance_name'])}</td>
                    <td><span class="{type_class}">{self._escape_html(row['app_type'])}</span></td>
                    <td>{self._escape_html(row['server_name'])}</td>
                    <td><span class="version">{self._escape_html(row['version'])}</span></td>
                    <td>{row['updated_at']}</td>
                </tr>
            """

        table_html += "</tbody></table>"

        # Формируем информацию о фильтрах
        filters_info = self._format_filters_info(filters) if filters else None

        return render_template_string(
            self.EMAIL_TEMPLATE,
            title="Текущие версии приложений",
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            table_html=table_html,
            total_records=len(data),
            filters_info=filters_info
        )

    def _generate_version_history_html(self, data: List[Dict], filters: Dict, period_text: str) -> str:
        """Генерировать HTML для отчёта об истории изменений"""

        table_html = """
        <table>
            <thead>
                <tr>
                    <th>Приложение</th>
                    <th>Сервер</th>
                    <th>Изменение версии</th>
                    <th>Дата</th>
                    <th>Источник</th>
                </tr>
            </thead>
            <tbody>
        """

        for row in data:
            table_html += f"""
                <tr>
                    <td>{self._escape_html(row['instance_name'])}</td>
                    <td>{self._escape_html(row['server_name'])}</td>
                    <td>
                        <span class="version">{self._escape_html(row['old_version'])}</span>
                        <span class="change-arrow">&rarr;</span>
                        <span class="version">{self._escape_html(row['new_version'])}</span>
                    </td>
                    <td>{row['changed_at']}</td>
                    <td>{self._escape_html(row['changed_by'])}</td>
                </tr>
            """

        table_html += "</tbody></table>"

        filters_info = self._format_filters_info(filters) if filters else None

        return render_template_string(
            self.EMAIL_TEMPLATE,
            title=f"История изменений версий {period_text}",
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            table_html=table_html,
            total_records=len(data),
            filters_info=filters_info
        )

    def _generate_current_versions_csv(self, data: List[Dict]) -> str:
        """Генерировать CSV для отчёта о текущих версиях"""
        output = io.StringIO()
        output.write('\ufeff')  # BOM для Excel

        writer = csv.DictWriter(output, fieldnames=[
            'instance_name', 'app_type', 'version',
            'server_name', 'distr_path', 'updated_at'
        ], delimiter=';')
        writer.writeheader()
        writer.writerows(data)

        return output.getvalue()

    def _generate_version_history_csv(self, data: List[Dict]) -> str:
        """Генерировать CSV для отчёта об истории изменений"""
        output = io.StringIO()
        output.write('\ufeff')  # BOM для Excel

        writer = csv.DictWriter(output, fieldnames=[
            'instance_name', 'server_name',
            'old_version', 'new_version',
            'changed_at', 'changed_by', 'change_source'
        ], delimiter=';')
        writer.writeheader()
        writer.writerows(data)

        return output.getvalue()

    def _send_email(
        self,
        to: List[str],
        subject: str,
        html_body: str,
        attachments: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Отправить email через sendmail.

        Args:
            to: Список email-адресов получателей
            subject: Тема письма
            html_body: HTML тело письма
            attachments: Список вложений

        Returns:
            Результат отправки
        """
        if not current_app.config.get('REPORT_EMAIL_ENABLED', True):
            return {
                'success': False,
                'error': 'Рассылка отчётов отключена в конфигурации'
            }

        email_from = current_app.config.get('REPORT_EMAIL_FROM', 'ac-reports@localhost')
        sendmail_path = current_app.config.get('SENDMAIL_PATH', '/usr/sbin/sendmail')

        try:
            # Создаём сообщение
            msg = MIMEMultipart('mixed')
            msg['From'] = email_from
            msg['To'] = ', '.join(to)
            msg['Subject'] = subject
            msg['Content-Type'] = 'text/html; charset=utf-8'

            # Добавляем HTML тело
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)

            # Добавляем вложения
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'].encode('utf-8'))
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{attachment["filename"]}"'
                    )
                    msg.attach(part)

            # Отправляем через sendmail
            process = subprocess.Popen(
                [sendmail_path, '-t', '-oi'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            stdout, stderr = process.communicate(msg.as_string().encode('utf-8'))

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else 'Unknown error'
                logger.error(f"Sendmail error: {error_msg}")
                return {
                    'success': False,
                    'error': f'Ошибка отправки: {error_msg}'
                }

            logger.info(f"Email sent successfully to {len(to)} recipients")
            return {
                'success': True,
                'message': f'Отчёт отправлен {len(to)} получателям'
            }

        except FileNotFoundError:
            logger.error(f"Sendmail not found at {sendmail_path}")
            return {
                'success': False,
                'error': f'Sendmail не найден: {sendmail_path}'
            }
        except Exception as e:
            logger.error(f"Email sending error: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка отправки: {str(e)}'
            }

    def _escape_html(self, text: str) -> str:
        """Экранирование HTML символов"""
        if text is None:
            return ''
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def _format_filters_info(self, filters: Dict) -> str:
        """Форматировать информацию о фильтрах"""
        parts = []
        if filters.get('server_ids'):
            parts.append(f"Серверы: {len(filters['server_ids'])} выбрано")
        if filters.get('catalog_ids'):
            parts.append(f"Приложения: {len(filters['catalog_ids'])} выбрано")
        if filters.get('app_type'):
            parts.append(f"Тип: {filters['app_type']}")
        return ', '.join(parts) if parts else None


# Создаём экземпляр сервиса
report_mailer = ReportMailerService()

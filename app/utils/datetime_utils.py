# app/utils/datetime_utils.py
"""
Утилиты для работы с датами и временем.
Все даты хранятся в UTC и передаются клиенту в ISO 8601 с суффиксом Z.
"""
from datetime import datetime


def format_datetime_utc(dt):
    """
    Форматирует datetime в ISO 8601 строку с суффиксом Z (UTC).

    Args:
        dt: datetime объект (предполагается UTC)

    Returns:
        str: ISO 8601 строка с суффиксом Z, например '2024-12-08T10:30:00Z'
        None: если dt is None
    """
    if dt is None:
        return None
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

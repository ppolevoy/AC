# app/models/mailing_group.py
# Модель для хранения групп рассылки email

from app import db
from datetime import datetime
from typing import List
import re


class MailingGroup(db.Model):
    """Группа рассылки для отправки отчётов по email"""
    __tablename__ = 'mailing_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255))
    emails = db.Column(db.Text, nullable=False)  # email-адреса через запятую
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_mailing_group_name', 'name'),
        db.Index('idx_mailing_group_active', 'is_active'),
    )

    def get_emails_list(self) -> List[str]:
        """
        Возвращает список email-адресов из группы.
        Фильтрует пустые строки и удаляет пробелы.
        """
        if not self.emails:
            return []
        return [
            email.strip()
            for email in self.emails.split(',')
            if email.strip()
        ]

    def set_emails_list(self, emails: List[str]) -> None:
        """
        Устанавливает список email-адресов.
        """
        # Фильтруем и очищаем email-адреса
        clean_emails = [email.strip() for email in emails if email and email.strip()]
        self.emails = ','.join(clean_emails)

    @property
    def emails_count(self) -> int:
        """Количество email-адресов в группе"""
        return len(self.get_emails_list())

    @staticmethod
    def validate_email(email: str) -> bool:
        """Простая валидация email-адреса"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email.strip()))

    def validate_emails(self) -> tuple:
        """
        Валидирует все email-адреса в группе.
        Возвращает (valid_emails, invalid_emails)
        """
        valid = []
        invalid = []
        for email in self.get_emails_list():
            if self.validate_email(email):
                valid.append(email)
            else:
                invalid.append(email)
        return valid, invalid

    def to_dict(self) -> dict:
        """Сериализация для API"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'emails': self.emails,
            'emails_list': self.get_emails_list(),
            'emails_count': self.emails_count,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def find_by_name(cls, name: str):
        """Поиск группы по имени (без учёта регистра)"""
        # Убираем префикс @ если есть
        clean_name = name.lstrip('@').strip()
        return cls.query.filter(
            db.func.lower(cls.name) == clean_name.lower(),
            cls.is_active == True
        ).first()

    @classmethod
    def resolve_recipients(cls, recipients: List[str]) -> List[str]:
        """
        Разрешает список получателей в email-адреса.

        Логика:
        - Если строка содержит '@' и похожа на email - оставляет как есть
        - Иначе ищет группу рассылки по имени и подставляет её email-адреса

        Args:
            recipients: Список получателей (email или имена групп)

        Returns:
            Список уникальных email-адресов
        """
        resolved_emails = set()

        for recipient in recipients:
            recipient = recipient.strip()
            if not recipient:
                continue

            # Проверяем, похоже ли на email (содержит @ и точку после @)
            if '@' in recipient and '.' in recipient.split('@')[-1]:
                resolved_emails.add(recipient)
            else:
                # Ищем группу по имени
                group = cls.find_by_name(recipient)
                if group:
                    for email in group.get_emails_list():
                        resolved_emails.add(email)

        return list(resolved_emails)

    def __repr__(self):
        return f'<MailingGroup {self.name} ({self.emails_count} emails)>'

# app/models/server.py
# РЕФАКТОРИНГ - обновлен relationship на ApplicationInstance
from app import db
from datetime import datetime

class Server(db.Model):
    __tablename__ = 'servers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    ip = db.Column(db.String(15), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    last_check = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='offline')

    # HAProxy integration
    is_haproxy_node = db.Column(db.Boolean, default=False, nullable=False)

    # Eureka integration
    is_eureka_node = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships
    instances = db.relationship('ApplicationInstance', back_populates='server', lazy='dynamic', cascade="all, delete-orphan")
    events = db.relationship('Event', back_populates='server', lazy='dynamic', cascade="all, delete-orphan")

    # Алиас для обратной совместимости
    @property
    def applications(self):
        """Алиас для обратной совместимости с кодом, использующим server.applications"""
        return self.instances

    def __repr__(self):
        return f'<Server {self.name} ({self.ip})>'

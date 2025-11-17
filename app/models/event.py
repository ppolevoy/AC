# app/models/event.py
# РЕФАКТОРИНГ - переименован application_id в instance_id
from app import db
from datetime import datetime

class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    event_type = db.Column(db.String(32), nullable=False)  # start, stop, restart, update, connect, disconnect
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), default='success')  # success, failed, pending

    server_id = db.Column(db.Integer, db.ForeignKey('servers.id', ondelete='CASCADE'), nullable=False)
    instance_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='CASCADE'), nullable=True)

    # Relationships
    server = db.relationship('Server', back_populates='events')
    instance = db.relationship('ApplicationInstance', back_populates='events')

    def __repr__(self):
        return f'<Event {self.event_type} - {self.timestamp}>'

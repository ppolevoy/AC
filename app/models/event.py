# app/models/event.py
from app import db
from datetime import datetime

class Event(db.Model):
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    event_type = db.Column(db.String(32), nullable=False)  # start, stop, restart, update
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), default='success')  # success, failed, pending
    
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), nullable=False)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=True)
    
    def __repr__(self):
        return f'<Event {self.event_type} - {self.timestamp}>'

# app/models/server.py
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
    
    applications = db.relationship('Application', backref='server', lazy='dynamic', cascade="all, delete-orphan")
    events = db.relationship('Event', backref='server', lazy='dynamic', cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Server {self.name} ({self.ip})>'

# app/models/application.py
from app import db
from datetime import datetime

class Application(db.Model):
    __tablename__ = 'applications'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    path = db.Column(db.String(256), nullable=True)
    log_path = db.Column(db.String(256), nullable=True)
    version = db.Column(db.String(64), nullable=True)
    distr_path = db.Column(db.String(256), nullable=True)
    
    # Дополнительные поля из JSON-шаблона
    container_id = db.Column(db.String(64), nullable=True)
    container_name = db.Column(db.String(64), nullable=True)
    eureka_url = db.Column(db.String(256), nullable=True)
    compose_project_dir = db.Column(db.String(256), nullable=True)
    
    ip = db.Column(db.String(15), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='offline')
    start_time = db.Column(db.DateTime, nullable=True)
    
    # Тип приложения (docker, eureka, site, service)
    app_type = db.Column(db.String(32), nullable=True)
    
    # Путь до плейбука для обновления
    update_playbook_path = db.Column(db.String(256), nullable=True)
    
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id', ondelete='CASCADE'), nullable=False)
    
    # Вычисление группы и номера экземпляра из имени
    @property
    def group_name(self):
        # Пытаемся найти формат %имя_приложения%_%номер_экземпляра%
        parts = self.name.split('_')
        if len(parts) > 1 and parts[-1].isdigit():
            return '_'.join(parts[:-1])
        return self.name
    
    @property
    def instance_number(self):
        parts = self.name.split('_')
        if len(parts) > 1 and parts[-1].isdigit():
            return int(parts[-1])
        return 0
    
    def __repr__(self):
        return f'<Application {self.name} ({self.status})>'

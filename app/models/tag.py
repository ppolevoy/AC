# app/models/tag.py
# Система тегов для ApplicationInstance и ApplicationGroup

from app import db
from datetime import datetime
from sqlalchemy import event


class Tag(db.Model):
    """Тег для маркировки приложений и групп"""
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(64))
    description = db.Column(db.Text)
    icon = db.Column(db.String(20))
    tag_type = db.Column(db.String(20))  # status, env, version, special, custom
    css_class = db.Column(db.String(50))
    border_color = db.Column(db.String(7))
    text_color = db.Column(db.String(7))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связи many-to-many
    instances = db.relationship(
        'ApplicationInstance',
        secondary='application_instance_tags',
        backref=db.backref('tags', lazy='dynamic'),
        lazy='dynamic'
    )

    groups = db.relationship(
        'ApplicationGroup',
        secondary='application_group_tags',
        backref=db.backref('tags', lazy='dynamic'),
        lazy='dynamic'
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name or self.name,
            'description': self.description,
            'icon': self.icon,
            'tag_type': self.tag_type,
            'css_class': self.css_class,
            'border_color': self.border_color,
            'text_color': self.text_color,
            'usage_count': self.get_usage_count(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def get_usage_count(self):
        """Подсчет использования тега"""
        return self.instances.count() + self.groups.count()

    def __repr__(self):
        return f'<Tag {self.name}>'


class ApplicationInstanceTag(db.Model):
    """Связь между ApplicationInstance и Tag"""
    __tablename__ = 'application_instance_tags'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.String(64))

    __table_args__ = (
        db.UniqueConstraint('application_id', 'tag_id', name='uq_app_instance_tag'),
        db.Index('idx_app_tags_app', 'application_id'),
        db.Index('idx_app_tags_tag', 'tag_id'),
    )


class ApplicationGroupTag(db.Model):
    """Связь между ApplicationGroup и Tag"""
    __tablename__ = 'application_group_tags'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('application_groups.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.String(64))

    __table_args__ = (
        db.UniqueConstraint('group_id', 'tag_id', name='uq_app_group_tag'),
        db.Index('idx_group_tags_group', 'group_id'),
        db.Index('idx_group_tags_tag', 'tag_id'),
    )


class TagHistory(db.Model):
    """История изменений тегов"""
    __tablename__ = 'tag_history'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(20), nullable=False)  # 'instance', 'group'
    entity_id = db.Column(db.Integer, nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='SET NULL'))
    action = db.Column(db.String(20), nullable=False)  # 'assigned', 'removed', 'updated'
    changed_by = db.Column(db.String(64))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.JSON)

    __table_args__ = (
        db.Index('idx_tag_history_entity', 'entity_type', 'entity_id'),
        db.Index('idx_tag_history_time', 'changed_at'),
    )


# Автоматическое обновление updated_at при изменении Tag
@event.listens_for(Tag, 'before_update')
def update_tag_timestamp(mapper, connection, target):
    target.updated_at = datetime.utcnow()

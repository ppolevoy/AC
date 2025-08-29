from app import db
from datetime import datetime
from sqlalchemy import UniqueConstraint, event
from sqlalchemy.orm import validates
import logging

logger = logging.getLogger(__name__)


class Tag(db.Model):
    """Справочник тегов с категориями и стилями"""
    __tablename__ = 'tags'
    
    # Категории тегов
    CATEGORY_ENVIRONMENT = 'environment'
    CATEGORY_SERVICE_TYPE = 'service_type'
    CATEGORY_PRIORITY = 'priority'
    CATEGORY_STATUS = 'status'
    CATEGORY_CUSTOM = 'custom'
    
    CATEGORIES = [
        CATEGORY_ENVIRONMENT,
        CATEGORY_SERVICE_TYPE,
        CATEGORY_PRIORITY,
        CATEGORY_STATUS,
        CATEGORY_CUSTOM
    ]
    
    # Предопределенные цвета для категорий
    CATEGORY_COLORS = {
        CATEGORY_ENVIRONMENT: {
            'production': '#dc3545',    # Красный
            'staging': '#fd7e14',        # Оранжевый
            'development': '#28a745',    # Зеленый
            'testing': '#6c757d'         # Серый
        },
        CATEGORY_SERVICE_TYPE: {
            'docker': '#0db7ed',         # Docker синий
            'eureka': '#6db33f',         # Spring зеленый
            'microservice': '#17a2b8',   # Бирюзовый
            'api': '#007bff',            # Синий
            'database': '#563d7c'        # Фиолетовый
        },
        CATEGORY_PRIORITY: {
            'critical': '#dc3545',       # Красный
            'high-priority': '#fd7e14',  # Оранжевый
            'medium-priority': '#ffc107', # Желтый
            'low-priority': '#28a745'     # Зеленый
        },
        CATEGORY_STATUS: {
            'maintenance': '#ffc107',     # Желтый
            'deprecated': '#6c757d',      # Серый
            'legacy': '#795548',          # Коричневый
            'needs-attention': '#dc3545'  # Красный
        }
    }
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    category = db.Column(db.String(32), nullable=False, default=CATEGORY_CUSTOM)
    color = db.Column(db.String(7), nullable=False)  # HEX цвет
    description = db.Column(db.Text, nullable=True)
    is_system = db.Column(db.Boolean, default=False, nullable=False)  # Защита от удаления
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи many-to-many
    instance_associations = db.relationship(
        'ApplicationInstanceTag',
        back_populates='tag',
        cascade='all, delete-orphan'
    )
    
    group_associations = db.relationship(
        'ApplicationGroupTag',
        back_populates='tag',
        cascade='all, delete-orphan'
    )
    
    @validates('category')
    def validate_category(self, key, value):
        """Валидация категории"""
        if value not in self.CATEGORIES:
            raise ValueError(f"Invalid category: {value}. Must be one of {self.CATEGORIES}")
        return value
    
    @validates('color')
    def validate_color(self, key, value):
        """Валидация HEX цвета"""
        if not value:
            return '#6c757d'  # Дефолтный серый
        
        if not value.startswith('#'):
            value = '#' + value
            
        if len(value) != 7 or not all(c in '0123456789abcdefABCDEF' for c in value[1:]):
            raise ValueError(f"Invalid HEX color: {value}")
            
        return value.lower()
    
    @classmethod
    def get_or_create(cls, name, category=None, color=None, description=None):
        """Получить существующий тег или создать новый"""
        tag = cls.query.filter_by(name=name).first()
        
        if not tag:
            # Определяем цвет на основе категории и имени
            if not color and category in cls.CATEGORY_COLORS:
                color = cls.CATEGORY_COLORS[category].get(name, '#6c757d')
            elif not color:
                color = '#6c757d'
            
            tag = cls(
                name=name,
                category=category or cls.CATEGORY_CUSTOM,
                color=color,
                description=description
            )
            db.session.add(tag)
            db.session.commit()
            logger.info(f"Created new tag: {name} (category: {category})")
        
        return tag
    
    def to_dict(self):
        """Преобразование в словарь для API"""
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'color': self.color,
            'description': self.description,
            'is_system': self.is_system,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Tag {self.name} ({self.category})>'


class ApplicationInstanceTag(db.Model):
    """Связь между ApplicationInstance и Tag"""
    __tablename__ = 'application_instance_tags'
    
    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False)
    assigned_by = db.Column(db.String(128), nullable=True)  # Для аудита
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    instance = db.relationship('ApplicationInstance', backref=db.backref('tag_associations', cascade='all, delete-orphan'))
    tag = db.relationship('Tag', back_populates='instance_associations')
    
    # Уникальный индекс для предотвращения дублирования
    __table_args__ = (
        UniqueConstraint('instance_id', 'tag_id', name='uq_instance_tag'),
        db.Index('idx_instance_tags', 'instance_id', 'tag_id'),
    )
    
    def __repr__(self):
        return f'<ApplicationInstanceTag instance={self.instance_id} tag={self.tag_id}>'


class ApplicationGroupTag(db.Model):
    """Связь между ApplicationGroup и Tag с флагом наследования"""
    __tablename__ = 'application_group_tags'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('application_groups.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False)
    inheritable = db.Column(db.Boolean, default=True, nullable=False)  # Наследуется ли экземплярами
    assigned_by = db.Column(db.String(128), nullable=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    group = db.relationship('ApplicationGroup', backref=db.backref('tag_associations', cascade='all, delete-orphan'))
    tag = db.relationship('Tag', back_populates='group_associations')
    
    # Уникальный индекс
    __table_args__ = (
        UniqueConstraint('group_id', 'tag_id', name='uq_group_tag'),
        db.Index('idx_group_tags', 'group_id', 'tag_id'),
        db.Index('idx_inheritable_tags', 'group_id', 'inheritable'),
    )
    
    def __repr__(self):
        return f'<ApplicationGroupTag group={self.group_id} tag={self.tag_id} inheritable={self.inheritable}>'


# Инициализация системных тегов при первом запуске
def init_system_tags():
    """Создание предопределенных системных тегов"""
    system_tags = [
        # Environment tags
        {'name': 'production', 'category': Tag.CATEGORY_ENVIRONMENT, 'color': '#dc3545', 'description': 'Production environment', 'is_system': True},
        {'name': 'staging', 'category': Tag.CATEGORY_ENVIRONMENT, 'color': '#fd7e14', 'description': 'Staging environment', 'is_system': True},
        {'name': 'development', 'category': Tag.CATEGORY_ENVIRONMENT, 'color': '#28a745', 'description': 'Development environment', 'is_system': True},
        
        # Service type tags
        {'name': 'docker', 'category': Tag.CATEGORY_SERVICE_TYPE, 'color': '#0db7ed', 'description': 'Docker container', 'is_system': True},
        {'name': 'eureka', 'category': Tag.CATEGORY_SERVICE_TYPE, 'color': '#6db33f', 'description': 'Eureka service', 'is_system': True},
        {'name': 'microservice', 'category': Tag.CATEGORY_SERVICE_TYPE, 'color': '#17a2b8', 'description': 'Microservice', 'is_system': True},
        
        # Priority tags
        {'name': 'critical', 'category': Tag.CATEGORY_PRIORITY, 'color': '#dc3545', 'description': 'Critical priority', 'is_system': True},
        {'name': 'high-priority', 'category': Tag.CATEGORY_PRIORITY, 'color': '#fd7e14', 'description': 'High priority', 'is_system': True},
        
        # Status tags
        {'name': 'maintenance', 'category': Tag.CATEGORY_STATUS, 'color': '#ffc107', 'description': 'Under maintenance', 'is_system': True},
        {'name': 'legacy', 'category': Tag.CATEGORY_STATUS, 'color': '#795548', 'description': 'Legacy system', 'is_system': True},
    ]
    
    for tag_data in system_tags:
        existing = Tag.query.filter_by(name=tag_data['name']).first()
        if not existing:
            tag = Tag(**tag_data)
            db.session.add(tag)
    
    try:
        db.session.commit()
        logger.info("System tags initialized successfully")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing system tags: {e}")
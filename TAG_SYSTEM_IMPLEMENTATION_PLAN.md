# План реализации системы тэгов для Application Control

## 📋 Содержание
1. [Контекст и требования](#контекст-и-требования)
2. [Архитектурное решение](#архитектурное-решение)
3. [Детальный план реализации по фазам](#детальный-план-реализации-по-фазам)
4. [Технические спецификации](#технические-спецификации)
5. [Примеры кода и интеграции](#примеры-кода-и-интеграции)
6. [Контрольные точки и тестирование](#контрольные-точки-и-тестирование)

---

## Контекст и требования

### Исходная задача
Добавить систему тэгов для экземпляров приложений в проект **AC (Application Control)** - Flask-based платформу управления распределенными приложениями.

### Требования пользователя
1. **Уровень применения**: ApplicationInstance + ApplicationGroup
2. **Подход к реализации**: Гибридный (нормализованные таблицы + кэш)
3. **Важные функции**: Фильтрация и Batch операции
4. **UI интеграция**: Полная интеграция с интерфейсом
5. **Дизайн**: Минималистичные тэги с обводкой (tag_design_option2.html)
6. **Размещение управления**: На странице settings в отдельном блоке

### Текущая архитектура проекта
```
ApplicationCatalog → ApplicationGroup → ApplicationInstance → Server
                                    ↓
                                  Event
```

---

## Архитектурное решение

### Гибридный подход
- **Нормализованные таблицы** для целостности данных и управления
- **Кэш в основных таблицах** для быстрой фильтрации
- **Many-to-Many связи** через промежуточные таблицы

### Схема базы данных
```sql
-- Основная таблица тэгов
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,      -- уникальный идентификатор (online, offline, production)
    display_name VARCHAR(64),              -- отображаемое имя (Online, Offline, Production)
    description TEXT,                      -- описание для администратора
    icon VARCHAR(20),                      -- emoji иконка (●, ✓, ⚠, 🏢, 🧪, etc)
    tag_type VARCHAR(20),                  -- категория (status, env, version, special)
    css_class VARCHAR(50),                 -- CSS класс из дизайна
    border_color VARCHAR(7),               -- HEX цвет обводки
    text_color VARCHAR(7),                 -- HEX цвет текста
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Связь с ApplicationInstance
CREATE TABLE application_instance_tags (
    id SERIAL PRIMARY KEY,
    application_id INT NOT NULL REFERENCES application_instances(id) ON DELETE CASCADE,
    tag_id INT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(64),
    UNIQUE(application_id, tag_id),
    INDEX idx_app_tags_app (application_id),
    INDEX idx_app_tags_tag (tag_id)
);

-- Связь с ApplicationGroup
CREATE TABLE application_group_tags (
    id SERIAL PRIMARY KEY,
    group_id INT NOT NULL REFERENCES application_groups(id) ON DELETE CASCADE,
    tag_id INT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(64),
    UNIQUE(group_id, tag_id),
    INDEX idx_group_tags_group (group_id),
    INDEX idx_group_tags_tag (tag_id)
);

-- Кэш для быстрого поиска
ALTER TABLE application_instances
    ADD COLUMN tags_cache VARCHAR(512) DEFAULT NULL,
    ADD INDEX idx_instance_tags_cache (tags_cache);

ALTER TABLE application_groups
    ADD COLUMN tags_cache VARCHAR(512) DEFAULT NULL,
    ADD INDEX idx_group_tags_cache (tags_cache);

-- История изменений тэгов
CREATE TABLE tag_history (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,      -- 'instance' или 'group'
    entity_id INT NOT NULL,
    tag_id INT,
    action VARCHAR(20) NOT NULL,           -- 'assigned', 'removed', 'updated'
    changed_by VARCHAR(64),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details JSON,                          -- дополнительная информация
    INDEX idx_tag_history_entity (entity_type, entity_id),
    INDEX idx_tag_history_time (changed_at)
);
```

---

## Детальный план реализации по фазам

### ФАЗА 1: База данных и модели (Приоритет: ВЫСОКИЙ)

#### 1.1 Создание моделей

**Новый файл: `app/models/tag.py`**
```python
from datetime import datetime
from app import db

class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(64))
    description = db.Column(db.Text)
    icon = db.Column(db.String(20))
    tag_type = db.Column(db.String(20))  # status, env, version, special
    css_class = db.Column(db.String(50))
    border_color = db.Column(db.String(7))
    text_color = db.Column(db.String(7))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        """Подсчет использования тэга"""
        return self.instances.count() + self.groups.count()

class ApplicationInstanceTag(db.Model):
    __tablename__ = 'application_instance_tags'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application_instances.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.String(64))

    __table_args__ = (
        db.UniqueConstraint('application_id', 'tag_id'),
        db.Index('idx_app_tags_app', 'application_id'),
        db.Index('idx_app_tags_tag', 'tag_id'),
    )

class ApplicationGroupTag(db.Model):
    __tablename__ = 'application_group_tags'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('application_groups.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.String(64))

    __table_args__ = (
        db.UniqueConstraint('group_id', 'tag_id'),
        db.Index('idx_group_tags_group', 'group_id'),
        db.Index('idx_group_tags_tag', 'tag_id'),
    )

class TagHistory(db.Model):
    __tablename__ = 'tag_history'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(20), nullable=False)  # 'instance', 'group'
    entity_id = db.Column(db.Integer, nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'))
    action = db.Column(db.String(20), nullable=False)  # 'assigned', 'removed', 'updated'
    changed_by = db.Column(db.String(64))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.JSON)

    __table_args__ = (
        db.Index('idx_tag_history_entity', 'entity_type', 'entity_id'),
        db.Index('idx_tag_history_time', 'changed_at'),
    )
```

#### 1.2 Расширение существующих моделей

**Изменения в `app/models/application.py`:**
```python
# Добавить в класс ApplicationInstance:

def add_tag(self, tag_name, user=None):
    """Добавить тэг к экземпляру"""
    from app.models.tag import Tag, TagHistory

    tag = Tag.query.filter_by(name=tag_name).first()
    if not tag:
        tag = Tag(name=tag_name, display_name=tag_name.title())
        db.session.add(tag)

    if tag not in self.tags:
        self.tags.append(tag)
        self._update_tags_cache()

        # Запись в историю
        history = TagHistory(
            entity_type='instance',
            entity_id=self.id,
            tag_id=tag.id,
            action='assigned',
            changed_by=user,
            details={'tag_name': tag_name}
        )
        db.session.add(history)

    return tag

def remove_tag(self, tag_name, user=None):
    """Удалить тэг у экземпляра"""
    from app.models.tag import Tag, TagHistory

    tag = Tag.query.filter_by(name=tag_name).first()
    if tag and tag in self.tags:
        self.tags.remove(tag)
        self._update_tags_cache()

        # Запись в историю
        history = TagHistory(
            entity_type='instance',
            entity_id=self.id,
            tag_id=tag.id,
            action='removed',
            changed_by=user
        )
        db.session.add(history)

    return tag

def get_tag_names(self):
    """Получить список имен тэгов"""
    return [t.name for t in self.tags]

def has_tags(self, tag_names):
    """Проверить наличие всех указанных тэгов"""
    my_tags = set(self.get_tag_names())
    return all(t in my_tags for t in tag_names)

def _update_tags_cache(self):
    """Обновить кэш тэгов"""
    self.tags_cache = ','.join(sorted(self.get_tag_names()))

def to_dict(self, include_tags=True):
    result = {
        # ... существующие поля ...
    }
    if include_tags:
        result['tags'] = [t.to_dict() for t in self.tags]
    return result
```

#### 1.3 Миграция базы данных

**Новый файл: `migrations/versions/xxx_add_tag_system.py`**
```python
"""Add tag system

Revision ID: xxx
Revises: previous_revision
Create Date: 2024-xx-xx

"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Создание таблицы tags
    op.create_table('tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(64)),
        sa.Column('description', sa.Text()),
        sa.Column('icon', sa.String(20)),
        sa.Column('tag_type', sa.String(20)),
        sa.Column('css_class', sa.String(50)),
        sa.Column('border_color', sa.String(7)),
        sa.Column('text_color', sa.String(7)),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('idx_tag_name', 'tags', ['name'])

    # Создание связующих таблиц
    op.create_table('application_instance_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime()),
        sa.Column('assigned_by', sa.String(64)),
        sa.ForeignKeyConstraint(['application_id'], ['application_instances.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', 'tag_id')
    )

    # ... аналогично для application_group_tags и tag_history ...

    # Добавление кэш полей
    op.add_column('application_instances',
        sa.Column('tags_cache', sa.String(512)))
    op.add_column('application_groups',
        sa.Column('tags_cache', sa.String(512)))

    # Предустановленные тэги
    op.execute("""
        INSERT INTO tags (name, display_name, icon, tag_type, css_class) VALUES
        ('online', 'Online', '●', 'status', 'tag-status-online'),
        ('offline', 'Offline', '●', 'status', 'tag-status-offline'),
        ('warning', 'Warning', '●', 'status', 'tag-status-warning'),
        ('production', 'Production', '🏢', 'env', 'tag-env-prod'),
        ('test', 'Test', '🧪', 'env', 'tag-env-test'),
        ('development', 'Development', '🔧', 'env', 'tag-env-dev'),
        ('release', 'Release', '✓', 'version', 'tag-version-release'),
        ('snapshot', 'Snapshot', '📸', 'version', 'tag-version-snapshot'),
        ('dev', 'Dev', '🔹', 'version', 'tag-version-dev'),
        ('critical', 'Critical', '⚠', 'special', 'tag-critical'),
        ('monitored', 'Monitored', '📊', 'special', 'tag-monitored'),
        ('deprecated', 'Deprecated', '🗑', 'special', 'tag-deprecated')
    """)

def downgrade():
    op.drop_column('application_groups', 'tags_cache')
    op.drop_column('application_instances', 'tags_cache')
    op.drop_table('tag_history')
    op.drop_table('application_group_tags')
    op.drop_table('application_instance_tags')
    op.drop_table('tags')
```

---

### ФАЗА 2: API Endpoints (Приоритет: ВЫСОКИЙ)

#### 2.1 Создание API для тэгов

**Новый файл: `app/api/tags_routes.py`**
```python
from flask import Blueprint, request, jsonify
from app import db
from app.models.tag import Tag, TagHistory
from app.models.application import ApplicationInstance
from app.models.application_group import ApplicationGroup

bp = Blueprint('tags', __name__, url_prefix='/api')

@bp.route('/tags', methods=['GET'])
def get_tags():
    """Получить список всех тэгов"""
    tags = Tag.query.all()
    return jsonify({
        'success': True,
        'tags': [tag.to_dict() for tag in tags],
        'total': len(tags)
    })

@bp.route('/tags', methods=['POST'])
def create_tag():
    """Создать новый тэг"""
    data = request.json

    # Валидация
    if not data.get('name'):
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # Проверка уникальности
    if Tag.query.filter_by(name=data['name']).first():
        return jsonify({'success': False, 'error': 'Tag already exists'}), 409

    tag = Tag(
        name=data['name'],
        display_name=data.get('display_name', data['name'].title()),
        description=data.get('description'),
        icon=data.get('icon', '●'),
        tag_type=data.get('tag_type', 'custom'),
        css_class=data.get('css_class'),
        border_color=data.get('border_color'),
        text_color=data.get('text_color')
    )

    db.session.add(tag)
    db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    }), 201

@bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    """Обновить существующий тэг"""
    tag = Tag.query.get_or_404(tag_id)
    data = request.json

    # Обновляем только переданные поля
    for field in ['display_name', 'description', 'icon', 'css_class', 'border_color', 'text_color']:
        if field in data:
            setattr(tag, field, data[field])

    db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    })

@bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    """Удалить тэг"""
    tag = Tag.query.get_or_404(tag_id)

    # Записываем в историю перед удалением
    for instance in tag.instances:
        history = TagHistory(
            entity_type='instance',
            entity_id=instance.id,
            tag_id=tag.id,
            action='removed',
            changed_by='system',
            details={'reason': 'tag_deleted'}
        )
        db.session.add(history)

    db.session.delete(tag)
    db.session.commit()

    return jsonify({'success': True})

@bp.route('/applications/<int:app_id>/tags', methods=['GET'])
def get_application_tags(app_id):
    """Получить тэги приложения"""
    app = ApplicationInstance.query.get_or_404(app_id)
    return jsonify({
        'success': True,
        'tags': [tag.to_dict() for tag in app.tags]
    })

@bp.route('/applications/<int:app_id>/tags', methods=['POST'])
def add_application_tag(app_id):
    """Добавить тэг к приложению"""
    app = ApplicationInstance.query.get_or_404(app_id)
    data = request.json

    tag_name = data.get('tag_name')
    if not tag_name:
        return jsonify({'success': False, 'error': 'tag_name is required'}), 400

    tag = app.add_tag(tag_name, user=data.get('user'))
    db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.to_dict()
    })

@bp.route('/applications/<int:app_id>/tags/<int:tag_id>', methods=['DELETE'])
def remove_application_tag(app_id, tag_id):
    """Удалить тэг у приложения"""
    app = ApplicationInstance.query.get_or_404(app_id)
    tag = Tag.query.get_or_404(tag_id)

    app.remove_tag(tag.name, user=request.args.get('user'))
    db.session.commit()

    return jsonify({'success': True})

@bp.route('/applications/filter/by-tags', methods=['POST'])
def filter_by_tags():
    """Фильтрация приложений по тэгам"""
    data = request.json
    tag_names = data.get('tags', [])
    operator = data.get('operator', 'OR')  # OR или AND

    query = ApplicationInstance.query

    if tag_names:
        if operator == 'AND':
            # Все тэги должны присутствовать
            for tag_name in tag_names:
                query = query.filter(
                    ApplicationInstance.tags.any(Tag.name == tag_name)
                )
        else:  # OR
            # Хотя бы один тэг
            query = query.filter(
                ApplicationInstance.tags.any(Tag.name.in_(tag_names))
            )

    apps = query.all()

    return jsonify({
        'success': True,
        'applications': [app.to_dict() for app in apps],
        'total': len(apps),
        'filter': {
            'tags': tag_names,
            'operator': operator
        }
    })

@bp.route('/tags/statistics', methods=['GET'])
def get_tag_statistics():
    """Статистика использования тэгов"""
    stats = []

    for tag in Tag.query.all():
        stats.append({
            'tag': tag.to_dict(),
            'instances_count': tag.instances.count(),
            'groups_count': tag.groups.count(),
            'total_usage': tag.get_usage_count()
        })

    # Сортируем по использованию
    stats.sort(key=lambda x: x['total_usage'], reverse=True)

    return jsonify({
        'success': True,
        'statistics': stats,
        'total_tags': len(stats)
    })

# Аналогичные endpoints для ApplicationGroup
# ...
```

#### 2.2 Регистрация Blueprint

**Изменения в `app/api/__init__.py`:**
```python
from app.api import tags_routes

def register_blueprints(app):
    # ... существующие blueprints ...
    app.register_blueprint(tags_routes.bp)
```

---

### ФАЗА 3: Интеграция дизайна в UI (Приоритет: ВЫСОКИЙ)

#### 3.1 CSS стили

**Новый файл: `app/static/css/tags.css`**
```css
/* Основной контейнер для тэгов */
.tags-container {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
}

/* Базовый стиль тэга */
.tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.2px;
    white-space: nowrap;
    background: transparent;
    border: 1.5px solid;
    transition: all 0.2s;
    cursor: default;
}

.tag:hover {
    background: rgba(255, 255, 255, 0.05);
    transform: translateY(-1px);
}

.tag-icon {
    font-size: 13px;
    line-height: 1;
}

/* Статусы */
.tag-status-online {
    border-color: #10b981;
    color: #10b981;
}

.tag-status-offline {
    border-color: #ef4444;
    color: #ef4444;
}

.tag-status-warning {
    border-color: #f59e0b;
    color: #f59e0b;
}

.tag-status-unknown {
    border-color: #6b7280;
    color: #9ca3af;
}

/* Типы версий */
.tag-version-release {
    border-color: #3b82f6;
    color: #60a5fa;
}

.tag-version-snapshot {
    border-color: #8b5cf6;
    color: #a78bfa;
}

.tag-version-dev {
    border-color: #ec4899;
    color: #f472b6;
}

/* Окружения */
.tag-env-prod {
    border-color: #14b8a6;
    color: #2dd4bf;
}

.tag-env-test {
    border-color: #f97316;
    color: #fb923c;
}

.tag-env-dev {
    border-color: #a855f7;
    color: #c084fc;
}

/* Специальные метки */
.tag-critical {
    border-color: #dc2626;
    color: #ef4444;
    animation: border-pulse 2s infinite;
}

.tag-monitored {
    border-color: #0ea5e9;
    color: #38bdf8;
}

.tag-deprecated {
    border-color: #78716c;
    color: #a8a29e;
    opacity: 0.7;
}

/* Анимация для критических тэгов */
@keyframes border-pulse {
    0%, 100% {
        border-width: 1.5px;
        box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.4);
    }
    50% {
        border-width: 2px;
        box-shadow: 0 0 0 4px rgba(220, 38, 38, 0.1);
    }
}

/* Hover эффекты для специальных тэгов */
.tag-critical:hover {
    background: rgba(220, 38, 38, 0.1);
    border-color: #ef4444;
}

.tag-monitored:hover {
    background: rgba(14, 165, 233, 0.1);
}

/* Фильтр тэгов */
.tag-filter-section {
    margin: 15px 0;
    padding: 10px;
    background: #252528;
    border-radius: 6px;
}

.tag-filter-toggle {
    background: #5ca5e1;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    cursor: pointer;
    font-size: 14px;
}

.tag-filter-toggle:hover {
    background: #4b8ec9;
}

.tag-filter-panel {
    display: none;
    margin-top: 15px;
    padding: 15px;
    background: #1e1e20;
    border-radius: 4px;
}

.tag-filter-panel.active {
    display: block;
}

.tag-filter-group {
    margin-bottom: 15px;
}

.tag-filter-group h4 {
    color: #5ca5e1;
    font-size: 14px;
    margin-bottom: 10px;
}

.tag-checkbox {
    display: inline-block;
    margin-right: 15px;
    margin-bottom: 8px;
}

.tag-checkbox label {
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 5px;
}

/* Компактный вид для таблицы */
.table-tags-container {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    max-width: 300px;
}

.table-tags-container .tag {
    padding: 3px 8px;
    font-size: 11px;
}
```

#### 3.2 Подключение стилей

**Изменения в `app/templates/base.html`:**
```html
<!-- Добавить в секцию <head> -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/tags.css') }}">
```

---

### ФАЗА 4: Модификация таблицы приложений (Приоритет: ВЫСОКИЙ)

#### 4.1 Изменения в HTML

**Изменения в `app/templates/applications.html`:**
```html
<!-- В заголовке таблицы после "Имя сервиса" -->
<th>Тэги</th>
```

#### 4.2 Изменения в JavaScript

**Изменения в `app/static/js/applications/applications.js`:**
```javascript
// Добавить новый метод в объект
renderTags(tags) {
    if (!tags || tags.length === 0) {
        return '<span class="no-tags">—</span>';
    }

    const container = document.createElement('div');
    container.className = 'table-tags-container';

    tags.forEach(tag => {
        const span = document.createElement('span');
        span.className = `tag ${tag.css_class || ''}`;

        const icon = document.createElement('span');
        icon.className = 'tag-icon';
        icon.textContent = tag.icon || '●';

        const text = document.createTextNode(' ' + (tag.display_name || tag.name));

        span.appendChild(icon);
        span.appendChild(text);
        container.appendChild(span);
    });

    return container.outerHTML;
},

// В функции createApplicationRow после создания nameTd:
// 3. Тэги (НОВАЯ ЯЧЕЙКА)
const tagsTd = document.createElement('td');
tagsTd.innerHTML = this.renderTags(app.tags || []);

// Изменить порядок добавления ячеек:
row.appendChild(checkboxTd);
row.appendChild(nameTd);
row.appendChild(tagsTd);  // НОВАЯ
row.appendChild(versionTd);
row.appendChild(statusTd);
row.appendChild(serverTd);
row.appendChild(actionsTd);

// Аналогично для createGroupRow
```

---

### ФАЗА 5: Функциональность фильтрации (Приоритет: СРЕДНИЙ)

#### 5.1 HTML для фильтров

**Добавить в `app/templates/applications.html` после search-container:**
```html
<div class="tag-filter-section">
    <button class="tag-filter-toggle" id="tag-filter-toggle">
        <span>🔍</span> Фильтр по тэгам
    </button>
    <div class="tag-filter-panel" id="tag-filter-panel">
        <div class="tag-filter-controls">
            <label>
                <input type="radio" name="tag-operator" value="OR" checked>
                Любой из выбранных
            </label>
            <label>
                <input type="radio" name="tag-operator" value="AND">
                Все выбранные
            </label>
        </div>

        <div class="tag-filter-group">
            <h4>Статусы</h4>
            <div class="tag-checkbox">
                <label>
                    <input type="checkbox" class="tag-filter-checkbox" value="online">
                    <span class="tag tag-status-online">
                        <span class="tag-icon">●</span> Online
                    </span>
                </label>
            </div>
            <div class="tag-checkbox">
                <label>
                    <input type="checkbox" class="tag-filter-checkbox" value="offline">
                    <span class="tag tag-status-offline">
                        <span class="tag-icon">●</span> Offline
                    </span>
                </label>
            </div>
            <!-- Остальные статусы -->
        </div>

        <div class="tag-filter-group">
            <h4>Окружения</h4>
            <!-- Чекбоксы для окружений -->
        </div>

        <div class="tag-filter-group">
            <h4>Версии</h4>
            <!-- Чекбоксы для версий -->
        </div>

        <div class="tag-filter-actions">
            <button class="action-btn" id="apply-tag-filter">Применить</button>
            <button class="action-btn" id="clear-tag-filter">Очистить</button>
        </div>
    </div>
</div>
```

#### 5.2 JavaScript для фильтрации

**Добавить в `app/static/js/applications/applications.js`:**
```javascript
// Состояние фильтров
tagFilters: {
    enabled: false,
    tags: [],
    operator: 'OR'
},

// Инициализация фильтров
initTagFilters() {
    const toggle = document.getElementById('tag-filter-toggle');
    const panel = document.getElementById('tag-filter-panel');
    const applyBtn = document.getElementById('apply-tag-filter');
    const clearBtn = document.getElementById('clear-tag-filter');

    toggle.addEventListener('click', () => {
        panel.classList.toggle('active');
    });

    applyBtn.addEventListener('click', () => {
        this.applyTagFilter();
    });

    clearBtn.addEventListener('click', () => {
        this.clearTagFilter();
    });
},

applyTagFilter() {
    const checkboxes = document.querySelectorAll('.tag-filter-checkbox:checked');
    const operator = document.querySelector('input[name="tag-operator"]:checked').value;

    this.tagFilters.tags = Array.from(checkboxes).map(cb => cb.value);
    this.tagFilters.operator = operator;
    this.tagFilters.enabled = this.tagFilters.tags.length > 0;

    this.loadApplications();
},

clearTagFilter() {
    document.querySelectorAll('.tag-filter-checkbox').forEach(cb => {
        cb.checked = false;
    });

    this.tagFilters.enabled = false;
    this.tagFilters.tags = [];

    this.loadApplications();
},

// Модификация загрузки приложений
async loadApplications() {
    let url = '/api/applications';

    if (this.tagFilters.enabled) {
        const response = await fetch('/api/applications/filter/by-tags', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                tags: this.tagFilters.tags,
                operator: this.tagFilters.operator
            })
        });
        const data = await response.json();
        this.renderApplications(data.applications);
    } else {
        // Обычная загрузка
        const response = await fetch(url);
        const data = await response.json();
        this.renderApplications(data.applications);
    }
}
```

---

### ФАЗА 6: Блок управления в настройках (Приоритет: СРЕДНИЙ)

#### 6.1 HTML блок в settings

**Добавить в `app/templates/settings.html` после блока маппингов:**
```html
<div class="settings-section">
    <h4>Управление тэгами</h4>

    <div class="tags-status-compact" id="tags-status-compact">
        <div class="status-line" id="tags-status-line">
            <span class="status-label">Система тэгов</span>
            <span class="status-spacer"></span>
            <span class="status-indicator" id="tags-status-indicator">
                <span class="status-dot connected"></span>
                <span class="status-text">Загрузка...</span>
            </span>
            <span class="expand-arrow" id="tags-expand-arrow">▼</span>
        </div>

        <div class="tags-details" id="tags-details" style="display: none;">
            <div class="tags-details-content">

                <!-- Создание нового тега -->
                <div class="detail-section">
                    <h5>Создание тега</h5>
                    <div class="tag-creator-form">
                        <div class="form-row">
                            <div class="form-group">
                                <label for="tag-name">Имя тега (уникальное)</label>
                                <input type="text" id="tag-name" class="form-control"
                                    placeholder="например: production">
                            </div>
                            <div class="form-group">
                                <label for="tag-display">Отображаемое имя</label>
                                <input type="text" id="tag-display" class="form-control"
                                    placeholder="например: Production">
                            </div>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label for="tag-type">Категория</label>
                                <select id="tag-type" class="form-control">
                                    <option value="status">Статус</option>
                                    <option value="env">Окружение</option>
                                    <option value="version">Версия</option>
                                    <option value="special">Специальный</option>
                                    <option value="custom">Пользовательский</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="tag-icon">Иконка</label>
                                <select id="tag-icon" class="form-control">
                                    <option value="●">● (точка)</option>
                                    <option value="✓">✓ (галочка)</option>
                                    <option value="⚠">⚠ (warning)</option>
                                    <option value="🏢">🏢 (production)</option>
                                    <option value="🧪">🧪 (test)</option>
                                    <option value="🔧">🔧 (dev)</option>
                                    <option value="📊">📊 (monitored)</option>
                                    <option value="🗑">🗑 (deprecated)</option>
                                    <option value="📸">📸 (snapshot)</option>
                                    <option value="🔹">🔹 (diamond)</option>
                                </select>
                            </div>
                        </div>

                        <div class="form-group">
                            <label for="tag-css">Стиль отображения</label>
                            <select id="tag-css" class="form-control">
                                <option value="">-- Выберите стиль --</option>
                                <optgroup label="Статусы">
                                    <option value="tag-status-online">Online (зеленый)</option>
                                    <option value="tag-status-offline">Offline (красный)</option>
                                    <option value="tag-status-warning">Warning (оранжевый)</option>
                                </optgroup>
                                <optgroup label="Окружения">
                                    <option value="tag-env-prod">Production (бирюзовый)</option>
                                    <option value="tag-env-test">Test (оранжевый)</option>
                                    <option value="tag-env-dev">Development (фиолетовый)</option>
                                </optgroup>
                                <optgroup label="Версии">
                                    <option value="tag-version-release">Release (синий)</option>
                                    <option value="tag-version-snapshot">Snapshot (фиолетовый)</option>
                                    <option value="tag-version-dev">Dev (розовый)</option>
                                </optgroup>
                                <optgroup label="Специальные">
                                    <option value="tag-critical">Critical (красный пульс)</option>
                                    <option value="tag-monitored">Monitored (голубой)</option>
                                    <option value="tag-deprecated">Deprecated (серый)</option>
                                </optgroup>
                            </select>
                        </div>

                        <div class="form-group">
                            <label>Предпросмотр</label>
                            <div id="tag-preview">
                                <span class="tag" id="tag-preview-element">
                                    <span class="tag-icon">●</span>
                                    <span class="tag-text">Preview</span>
                                </span>
                            </div>
                        </div>

                        <button class="action-btn" id="create-tag-btn">
                            ✅ Создать тег
                        </button>
                    </div>
                </div>

                <!-- Список существующих тегов -->
                <div class="detail-section">
                    <h5>Существующие теги</h5>
                    <div id="tags-list-container" class="tags-list-container">
                        <div class="info-loading">Загрузка тегов...</div>
                    </div>
                </div>

                <!-- Массовые операции -->
                <div class="detail-section">
                    <h5>Массовое присвоение</h5>
                    <div class="bulk-assignment">
                        <div class="form-group">
                            <label>Выберите теги для присвоения</label>
                            <div id="bulk-tags-select" class="bulk-tags-select">
                                <!-- Динамически заполняется -->
                            </div>
                        </div>

                        <div class="form-group">
                            <label for="bulk-target">Применить к</label>
                            <select id="bulk-target" class="form-control">
                                <option value="">-- Выберите цель --</option>
                                <option value="group">Группе приложений</option>
                                <option value="server">Всем приложениям на сервере</option>
                                <option value="type">Типу приложений</option>
                            </select>
                        </div>

                        <div class="form-group" id="bulk-target-select" style="display: none;">
                            <label>Выберите конкретную цель</label>
                            <select id="bulk-target-value" class="form-control">
                                <option value="">-- Выберите --</option>
                            </select>
                        </div>

                        <button class="action-btn" id="bulk-assign-btn" disabled>
                            Применить теги
                        </button>
                    </div>
                </div>

                <!-- Статистика -->
                <div class="detail-section">
                    <h5>Статистика использования</h5>
                    <div id="tags-statistics" class="statistics-container">
                        <div class="info-loading">Загрузка статистики...</div>
                    </div>
                </div>

            </div>
        </div>
    </div>
</div>
```

#### 6.2 JavaScript для управления

**Новый файл: `app/static/js/settings/tags-management.js`**
```javascript
const TagsManagement = {
    tags: [],
    statistics: null,

    init() {
        this.setupEventHandlers();
        this.loadTags();
        this.loadStatistics();
    },

    setupEventHandlers() {
        // Разворачивание/сворачивание блока
        const statusLine = document.getElementById('tags-status-line');
        const details = document.getElementById('tags-details');
        const arrow = document.getElementById('tags-expand-arrow');
        let isExpanded = false;

        statusLine.addEventListener('click', () => {
            isExpanded = !isExpanded;
            details.style.display = isExpanded ? 'block' : 'none';
            arrow.classList.toggle('expanded', isExpanded);

            if (isExpanded && this.tags.length === 0) {
                this.loadTags();
            }
        });

        // Создание тега
        document.getElementById('create-tag-btn').addEventListener('click', () => {
            this.createTag();
        });

        // Предпросмотр
        this.setupPreview();

        // Массовое присвоение
        this.setupBulkAssignment();
    },

    setupPreview() {
        const nameInput = document.getElementById('tag-name');
        const displayInput = document.getElementById('tag-display');
        const iconSelect = document.getElementById('tag-icon');
        const cssSelect = document.getElementById('tag-css');
        const preview = document.getElementById('tag-preview-element');

        const updatePreview = () => {
            const icon = iconSelect.value;
            const text = displayInput.value || nameInput.value || 'Preview';
            const cssClass = cssSelect.value;

            preview.className = `tag ${cssClass}`;
            preview.innerHTML = `
                <span class="tag-icon">${icon}</span>
                <span class="tag-text">${text}</span>
            `;
        };

        [nameInput, displayInput, iconSelect, cssSelect].forEach(el => {
            el.addEventListener('input', updatePreview);
        });
    },

    setupBulkAssignment() {
        const targetSelect = document.getElementById('bulk-target');
        const targetValueGroup = document.getElementById('bulk-target-select');
        const targetValue = document.getElementById('bulk-target-value');
        const assignBtn = document.getElementById('bulk-assign-btn');

        targetSelect.addEventListener('change', async () => {
            const target = targetSelect.value;

            if (!target) {
                targetValueGroup.style.display = 'none';
                assignBtn.disabled = true;
                return;
            }

            targetValueGroup.style.display = 'block';

            // Загрузка опций в зависимости от типа
            let options = [];

            switch (target) {
                case 'group':
                    const groupsResp = await fetch('/api/app-groups');
                    const groupsData = await groupsResp.json();
                    options = groupsData.groups.map(g => ({
                        value: g.id,
                        text: g.name
                    }));
                    break;

                case 'server':
                    const serversResp = await fetch('/api/servers');
                    const serversData = await serversResp.json();
                    options = serversData.servers.map(s => ({
                        value: s.id,
                        text: s.hostname
                    }));
                    break;

                case 'type':
                    options = [
                        {value: 'docker', text: 'Docker'},
                        {value: 'eureka', text: 'Eureka'},
                        {value: 'site', text: 'Site'},
                        {value: 'service', text: 'Service'}
                    ];
                    break;
            }

            targetValue.innerHTML = '<option value="">-- Выберите --</option>';
            options.forEach(opt => {
                targetValue.innerHTML += `<option value="${opt.value}">${opt.text}</option>`;
            });

            assignBtn.disabled = false;
        });

        assignBtn.addEventListener('click', () => {
            this.performBulkAssignment();
        });
    },

    async loadTags() {
        try {
            const response = await fetch('/api/tags');
            const data = await response.json();

            if (data.success) {
                this.tags = data.tags;
                this.renderTagsList();
                this.renderBulkTagsSelect();
                this.updateStatusIndicator(data.total);
            }
        } catch (error) {
            console.error('Error loading tags:', error);
        }
    },

    renderTagsList() {
        const container = document.getElementById('tags-list-container');

        if (this.tags.length === 0) {
            container.innerHTML = '<div class="info-loading">Нет созданных тегов</div>';
            return;
        }

        let html = `
            <table class="tags-table">
                <thead>
                    <tr>
                        <th>Тег</th>
                        <th>Имя</th>
                        <th>Тип</th>
                        <th>Использование</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
        `;

        this.tags.forEach(tag => {
            html += `
                <tr>
                    <td>
                        <span class="tag ${tag.css_class}">
                            <span class="tag-icon">${tag.icon}</span>
                            ${tag.display_name}
                        </span>
                    </td>
                    <td>${tag.name}</td>
                    <td>${tag.tag_type}</td>
                    <td>${tag.usage_count}</td>
                    <td>
                        <button class="btn-small btn-info" onclick="TagsManagement.editTag(${tag.id})">
                            Изменить
                        </button>
                        <button class="btn-small btn-danger" onclick="TagsManagement.deleteTag(${tag.id})">
                            Удалить
                        </button>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    },

    renderBulkTagsSelect() {
        const container = document.getElementById('bulk-tags-select');

        let html = '';
        this.tags.forEach(tag => {
            html += `
                <div class="tag-checkbox">
                    <label>
                        <input type="checkbox" class="bulk-tag-checkbox" value="${tag.id}">
                        <span class="tag ${tag.css_class}">
                            <span class="tag-icon">${tag.icon}</span>
                            ${tag.display_name}
                        </span>
                    </label>
                </div>
            `;
        });

        container.innerHTML = html;
    },

    async createTag() {
        const name = document.getElementById('tag-name').value.trim();
        const displayName = document.getElementById('tag-display').value.trim();
        const type = document.getElementById('tag-type').value;
        const icon = document.getElementById('tag-icon').value;
        const cssClass = document.getElementById('tag-css').value;

        if (!name) {
            alert('Введите имя тега');
            return;
        }

        try {
            const response = await fetch('/api/tags', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: name,
                    display_name: displayName || name.charAt(0).toUpperCase() + name.slice(1),
                    tag_type: type,
                    icon: icon,
                    css_class: cssClass
                })
            });

            const data = await response.json();

            if (data.success) {
                showNotification('Тег создан успешно');
                this.loadTags();

                // Очистка формы
                document.getElementById('tag-name').value = '';
                document.getElementById('tag-display').value = '';
            } else {
                showError('Ошибка создания тега: ' + data.error);
            }
        } catch (error) {
            console.error('Error creating tag:', error);
            showError('Ошибка создания тега');
        }
    },

    async deleteTag(tagId) {
        if (!confirm('Удалить этот тег? Он будет удален у всех приложений.')) {
            return;
        }

        try {
            const response = await fetch(`/api/tags/${tagId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                showNotification('Тег удален');
                this.loadTags();
            }
        } catch (error) {
            console.error('Error deleting tag:', error);
        }
    },

    async performBulkAssignment() {
        const selectedTags = Array.from(
            document.querySelectorAll('.bulk-tag-checkbox:checked')
        ).map(cb => cb.value);

        const target = document.getElementById('bulk-target').value;
        const targetValue = document.getElementById('bulk-target-value').value;

        if (selectedTags.length === 0) {
            alert('Выберите теги для присвоения');
            return;
        }

        if (!targetValue) {
            alert('Выберите цель для присвоения');
            return;
        }

        // В зависимости от target делаем разные запросы
        // ... реализация массового присвоения ...

        showNotification('Теги применены');
        this.loadStatistics();
    },

    async loadStatistics() {
        try {
            const response = await fetch('/api/tags/statistics');
            const data = await response.json();

            if (data.success) {
                this.statistics = data.statistics;
                this.renderStatistics();
            }
        } catch (error) {
            console.error('Error loading statistics:', error);
        }
    },

    renderStatistics() {
        const container = document.getElementById('tags-statistics');

        if (!this.statistics || this.statistics.length === 0) {
            container.innerHTML = '<div class="info-loading">Нет данных</div>';
            return;
        }

        let html = '<div class="statistics-grid">';

        // Топ-5 используемых тегов
        const top5 = this.statistics.slice(0, 5);

        top5.forEach(stat => {
            html += `
                <div class="stat-item">
                    <div class="stat-label">
                        <span class="tag ${stat.tag.css_class}">
                            <span class="tag-icon">${stat.tag.icon}</span>
                            ${stat.tag.display_name}
                        </span>
                    </div>
                    <div class="stat-value">${stat.total_usage}</div>
                    <div class="stat-detail">
                        Экземпляры: ${stat.instances_count}, Группы: ${stat.groups_count}
                    </div>
                </div>
            `;
        });

        html += '</div>';
        container.innerHTML = html;
    },

    updateStatusIndicator(count) {
        const statusText = document.querySelector('#tags-status-indicator .status-text');
        statusText.textContent = `${count} тегов`;
    }
};

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('tags-status-compact')) {
        TagsManagement.init();
    }
});
```

---

### ФАЗА 7: Интеграция с batch операциями (Приоритет: НИЗКИЙ)

#### 7.1 Обновление batch операций

**Изменения в `app/api/routes.py`:**
```python
@bp.route('/applications/batch_update', methods=['POST'])
def batch_update_applications():
    """Обновление приложений с поддержкой фильтрации по тегам"""
    data = request.json

    # Базовый запрос
    query = ApplicationInstance.query

    # Фильтрация по тегам если указана
    if 'tag_filter' in data:
        tag_names = data['tag_filter']
        tag_operator = data.get('tag_filter_operator', 'OR')

        if tag_operator == 'AND':
            for tag_name in tag_names:
                query = query.filter(
                    ApplicationInstance.tags.any(Tag.name == tag_name)
                )
        else:  # OR
            query = query.filter(
                ApplicationInstance.tags.any(Tag.name.in_(tag_names))
            )

    # Существующая фильтрация по app_ids
    if 'app_ids' in data:
        query = query.filter(ApplicationInstance.id.in_(data['app_ids']))

    applications = query.all()

    # Группировка
    strategy = data.get('grouping_strategy', 'by_group')

    if strategy == 'by_tags':
        # Новая стратегия группировки по тегам
        groups = {}
        for app in applications:
            tag_key = ','.join(sorted(app.get_tag_names()))
            if tag_key not in groups:
                groups[tag_key] = []
            groups[tag_key].append(app)

        # Создание задач для каждой группы
        for tag_key, apps in groups.items():
            task = Task(
                task_type='update',
                app_ids=[app.id for app in apps],
                distr_url=data.get('distr_url'),
                restart_mode=data.get('restart_mode'),
                grouping_key=tag_key
            )
            db.session.add(task)

    elif strategy == 'by_tags_and_group':
        # Комбинированная группировка
        # ... реализация ...

    else:
        # Существующие стратегии
        # ... существующий код ...

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Создано задач: {len(groups)}',
        'affected_apps': len(applications)
    })
```

#### 7.2 Обновление констант группировки

**Изменения в `app/models/application_group.py`:**
```python
BATCH_GROUPING_STRATEGIES = {
    'by_group': 'по группам приложений',
    'by_server': 'по серверам',
    'by_instance_name': 'по именам экземпляров',
    'no_grouping': 'без группировки',
    'by_tags': 'по тегам',  # НОВАЯ
    'by_tags_and_group': 'по тегам и группам'  # НОВАЯ
}
```

---

## Технические спецификации

### API Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| GET | /api/tags | Список всех тегов |
| POST | /api/tags | Создание тега |
| PUT | /api/tags/{id} | Обновление тега |
| DELETE | /api/tags/{id} | Удаление тега |
| GET | /api/applications/{id}/tags | Теги приложения |
| POST | /api/applications/{id}/tags | Добавить тег |
| DELETE | /api/applications/{id}/tags/{tag_id} | Удалить тег |
| POST | /api/applications/filter/by-tags | Фильтрация по тегам |
| GET | /api/tags/statistics | Статистика использования |
| POST | /api/tags/bulk-assign | Массовое присвоение |

### Предустановленные теги

| Имя | Категория | CSS класс | Иконка | Цвет |
|-----|-----------|-----------|--------|------|
| online | status | tag-status-online | ● | #10b981 |
| offline | status | tag-status-offline | ● | #ef4444 |
| warning | status | tag-status-warning | ● | #f59e0b |
| production | env | tag-env-prod | 🏢 | #14b8a6 |
| test | env | tag-env-test | 🧪 | #f97316 |
| development | env | tag-env-dev | 🔧 | #a855f7 |
| release | version | tag-version-release | ✓ | #3b82f6 |
| snapshot | version | tag-version-snapshot | 📸 | #8b5cf6 |
| dev | version | tag-version-dev | 🔹 | #ec4899 |
| critical | special | tag-critical | ⚠ | #dc2626 |
| monitored | special | tag-monitored | 📊 | #0ea5e9 |
| deprecated | special | tag-deprecated | 🗑 | #78716c |

---

## Контрольные точки и тестирование

### Контрольные точки по фазам

#### После Фазы 1 (БД):
- [ ] Миграция применена успешно
- [ ] Модели созданы и импортируются
- [ ] Предустановленные теги в БД
- [ ] Методы add_tag/remove_tag работают

#### После Фазы 2 (API):
- [ ] Все endpoints отвечают
- [ ] CRUD операции работают
- [ ] Фильтрация возвращает корректные данные
- [ ] Статистика подсчитывается правильно

#### После Фазы 3 (Дизайн):
- [ ] CSS подключен и применяется
- [ ] Теги отображаются с правильными стилями
- [ ] Анимации работают (critical pulse)
- [ ] Hover эффекты работают

#### После Фазы 4 (Таблица):
- [ ] Новая колонка отображается
- [ ] Теги рендерятся в таблице
- [ ] Нет ошибок JavaScript в консоли
- [ ] Теги корректно отображаются для групп

#### После Фазы 5 (Фильтрация):
- [ ] Панель фильтров открывается/закрывается
- [ ] Фильтрация работает (OR/AND)
- [ ] Очистка фильтров работает
- [ ] Счетчики обновляются

#### После Фазы 6 (Настройки):
- [ ] Блок в настройках отображается
- [ ] Создание тегов работает
- [ ] Предпросмотр обновляется
- [ ] Статистика загружается

#### После Фазы 7 (Batch):
- [ ] Новые стратегии доступны
- [ ] Группировка по тегам работает
- [ ] Задачи создаются корректно

### Тестовые сценарии

#### Сценарий 1: Создание и присвоение тега
1. Открыть настройки
2. Развернуть блок "Управление тегами"
3. Создать новый тег "custom-tag"
4. Открыть страницу приложений
5. Выбрать приложение
6. Присвоить тег через API
7. Проверить отображение

#### Сценарий 2: Фильтрация
1. Открыть страницу приложений
2. Открыть панель фильтров
3. Выбрать теги "production" и "critical"
4. Применить с оператором AND
5. Проверить результаты
6. Изменить на OR
7. Проверить результаты

#### Сценарий 3: Batch операция
1. Отфильтровать по тегу "test"
2. Выбрать все приложения
3. Запустить batch update
4. Выбрать стратегию "by_tags"
5. Проверить создание задач

---

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Производительность при большом количестве тегов | Средняя | Высокое | Использование кэша, индексы БД |
| Конфликты при одновременном редактировании | Низкая | Среднее | Оптимистичная блокировка |
| Потеря данных при удалении тега | Низкая | Высокое | История изменений, подтверждение |
| Несовместимость со старыми браузерами | Низкая | Низкое | Полифиллы для CSS |

---

## Заключение

Данный план обеспечивает полную реализацию системы тегов с:
- Гибридной архитектурой для производительности
- Минималистичным дизайном из предоставленного макета
- Интеграцией во все ключевые компоненты системы
- Централизованным управлением через настройки
- Полной обратной совместимостью

Рекомендуемый порядок реализации: Фазы 1-4 (критические), затем 5-7 (дополнительные).

---

**Документ подготовлен**: {{ current_date }}
**Версия плана**: 1.0
**Статус**: Готов к реализации
# ПЛАН РЕФАКТОРИНГА БАЗЫ ДАННЫХ - Application Control System

## Оглавление
1. [Резюме](#резюме)
2. [Текущие проблемы](#текущие-проблемы)
3. [Целевая архитектура](#целевая-архитектура)
4. [Новая структура БД](#новая-структура-бд)
5. [План миграции](#план-миграции)
6. [Изменения в коде](#изменения-в-коде)
7. [Оценка рисков](#оценка-рисков)
8. [Контрольный список](#контрольный-список)

---

## Резюме

### Цель рефакторинга
Привести структуру БД к изначально задуманной концепции:
- **application_catalog** - справочник приложений
- **application_instances** - экземпляры приложений на серверах
- **application_groups** - группы для управления экземплярами

### Масштаб изменений
- **23 API файла** с эндпоинтами
- **10 сервисных файлов** с бизнес-логикой
- **Система обработки задач** (Task Queue)
- **Система событий** с внешними ключами
- **Фоновый мониторинг**
- **~50+ функций** с прямыми запросами к Application

### Уровень риска: **КРИТИЧЕСКИЙ**

### Примечание
Это комплекс разработки, потеря данных не критична.

---

## Текущие проблемы

### 1. Концептуальные проблемы
- **Смешение концепций**: Таблица `applications` хранит обнаруженные экземпляры, а не справочник
- **Неправильная иерархия**: ApplicationInstance работает как junction table с 1:1 связью
- **Отсутствие каталога**: Нет централизованного справочника приложений

### 2. Технические проблемы
- **Дублирование данных**:
  - `instance_number` хранится в Application И ApplicationInstance
  - `group_id` хранится в Application И ApplicationInstance
- **Сложная логика совместимости**: Множественные fallback пути для обратной совместимости
- **Неэффективные запросы**: Сложные JOIN'ы из-за неоптимальной структуры

### 3. Текущая структура связей
```
Server → Application (обнаруженный экземпляр)
         ├→ ApplicationInstance (1:1, junction для группировки)
         │   └→ ApplicationGroup
         └→ ApplicationGroup (прямая связь, legacy)
```

---

## Целевая архитектура

### Концептуальная модель
```
ApplicationCatalog (Справочник)
    ↓
ApplicationGroup (Группы управления)
    ↓
ApplicationInstance (Реальные экземпляры на серверах)
    ↑
Server (Физические/виртуальные хосты)
```

### Примеры данных после рефакторинга

**application_catalog:**
| id | name | app_type | description |
|----|------|----------|-------------|
| 1 | best-app | tomcat | Основное приложение |
| 2 | new-app | spring | Новый микросервис |
| 3 | some-app | docker | Контейнерное приложение |

**application_groups:**
| id | name | catalog_id | batch_grouping_strategy |
|----|------|------------|-------------------------|
| 1 | Группа best-app | 1 | by_group |
| 2 | Группа new-app | 2 | by_server |
| 3 | Группа some-app | 3 | no_grouping |

**application_instances:**
| id | catalog_id | group_id | server_id | instance_name | instance_number | status |
|----|------------|----------|-----------|---------------|-----------------|--------|
| 1 | 1 | 1 | 1 | best-app_1 | 1 | online |
| 2 | 1 | 1 | 1 | best-app_2 | 2 | online |
| 3 | 1 | 1 | 2 | best-app_3 | 3 | online |
| 4 | 2 | 2 | 1 | new-app_1 | 1 | online |
| 5 | 2 | 2 | 2 | new-app_2 | 2 | offline |

---

## Новая структура БД

### 1. application_catalog (Справочник приложений)
```sql
CREATE TABLE application_catalog (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,  -- Базовое имя (best-app, new-app)
    app_type VARCHAR(32) NOT NULL,      -- docker/eureka/site/service
    description TEXT,

    -- Значения по умолчанию
    default_playbook_path VARCHAR(255),
    default_artifact_url VARCHAR(255),
    default_artifact_extension VARCHAR(32),

    -- Метаданные
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_app_type CHECK (app_type IN ('docker', 'eureka', 'site', 'service'))
);

CREATE INDEX idx_catalog_name ON application_catalog(name);
CREATE INDEX idx_catalog_type ON application_catalog(app_type);
```

### 2. application_groups (Группы управления)
```sql
CREATE TABLE application_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,

    -- Связь со справочником
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,

    -- Настройки группы
    artifact_list_url VARCHAR(255),
    artifact_extension VARCHAR(32),
    update_playbook_path VARCHAR(255),
    batch_grouping_strategy VARCHAR(32) DEFAULT 'by_group',

    -- Метаданные
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_strategy CHECK (
        batch_grouping_strategy IN ('by_group', 'by_server', 'by_instance_name', 'no_grouping')
    )
);

CREATE INDEX idx_group_catalog ON application_groups(catalog_id);
```

### 3. application_instances (Обнаруженные экземпляры)
```sql
CREATE TABLE application_instances (
    id SERIAL PRIMARY KEY,

    -- Связи
    catalog_id INTEGER REFERENCES application_catalog(id) ON DELETE SET NULL,
    group_id INTEGER REFERENCES application_groups(id) ON DELETE SET NULL,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,

    -- Идентификация
    instance_name VARCHAR(128) NOT NULL,  -- Полное имя: best-app_1
    instance_number INTEGER DEFAULT 0,     -- Номер экземпляра: 1, 2, 3
    app_type VARCHAR(32) NOT NULL,        -- Наследуется от catalog

    -- Состояние
    status VARCHAR(32) DEFAULT 'unknown',
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Данные от агента
    path VARCHAR(255),
    log_path VARCHAR(255),
    version VARCHAR(128),
    distr_path VARCHAR(255),

    -- Docker-специфичные
    container_id VARCHAR(128),
    container_name VARCHAR(128),
    compose_project_dir VARCHAR(255),

    -- Eureka-специфичные
    eureka_url VARCHAR(255),

    -- Сетевые параметры
    ip VARCHAR(45),
    port INTEGER,

    -- Процесс
    pid INTEGER,
    start_time TIMESTAMP,

    -- Кастомизация (переопределение настроек группы)
    custom_playbook_path VARCHAR(255),
    custom_artifact_url VARCHAR(255),
    custom_artifact_extension VARCHAR(32),

    -- Метаданные
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,  -- Soft delete

    CONSTRAINT unique_instance_per_server UNIQUE (server_id, instance_name, app_type),
    CONSTRAINT check_app_type CHECK (app_type IN ('docker', 'eureka', 'site', 'service')),
    CONSTRAINT check_status CHECK (status IN ('online', 'offline', 'unknown', 'starting', 'stopping'))
);

CREATE INDEX idx_instance_catalog ON application_instances(catalog_id);
CREATE INDEX idx_instance_group ON application_instances(group_id);
CREATE INDEX idx_instance_server ON application_instances(server_id);
CREATE INDEX idx_instance_status ON application_instances(status);
CREATE INDEX idx_instance_deleted ON application_instances(deleted_at);
CREATE INDEX idx_instance_name ON application_instances(instance_name);
```

### 4. Обновление таблицы events
```sql
-- Изменение внешнего ключа
ALTER TABLE events
    DROP CONSTRAINT events_application_id_fkey,
    ADD CONSTRAINT events_instance_id_fkey
        FOREIGN KEY (application_id)
        REFERENCES application_instances(id) ON DELETE CASCADE;

-- Переименование колонки для ясности
ALTER TABLE events RENAME COLUMN application_id TO instance_id;
```

---

## План миграции

### Фаза 1: Подготовка (без простоя)

#### Шаг 1.1: Создание новых таблиц
```sql
-- Создаем новые таблицы параллельно со старыми
CREATE TABLE application_catalog (...);
CREATE TABLE application_instances_new (...);
ALTER TABLE application_groups ADD COLUMN catalog_id INTEGER;
```

#### Шаг 1.2: Заполнение справочника
```sql
-- Извлекаем уникальные базовые имена приложений
INSERT INTO application_catalog (name, app_type, description)
SELECT DISTINCT
    REGEXP_REPLACE(name, '_[0-9]+$', '') as base_name,
    app_type,
    'Автоматически создано при миграции'
FROM applications
WHERE name IS NOT NULL;
```

#### Шаг 1.3: Связывание групп со справочником
```sql
UPDATE application_groups ag
SET catalog_id = (
    SELECT ac.id
    FROM application_catalog ac
    WHERE ac.name = ag.name
    LIMIT 1
)
WHERE EXISTS (
    SELECT 1 FROM application_catalog ac WHERE ac.name = ag.name
);
```

### Фаза 2: Миграция данных

#### Шаг 2.1: Перенос данных в application_instances_new
```sql
INSERT INTO application_instances_new (
    catalog_id, group_id, server_id, instance_name, instance_number,
    app_type, status, path, log_path, version, distr_path,
    container_id, container_name, compose_project_dir, eureka_url,
    ip, port, pid, start_time, created_at, updated_at
)
SELECT
    ac.id as catalog_id,
    COALESCE(ai.group_id, a.group_id) as group_id,
    a.server_id,
    a.name as instance_name,
    COALESCE(ai.instance_number, a.instance_number, 0) as instance_number,
    a.app_type,
    a.status,
    a.path, a.log_path, a.version, a.distr_path,
    a.container_id, a.container_name, a.compose_project_dir, a.eureka_url,
    a.ip, a.port, a.pid, a.start_time,
    COALESCE(a.created_at, NOW()), COALESCE(a.updated_at, NOW())
FROM applications a
LEFT JOIN application_instances ai ON ai.application_id = a.id
LEFT JOIN application_catalog ac ON ac.name = REGEXP_REPLACE(a.name, '_[0-9]+$', '')
WHERE a.deleted_at IS NULL;  -- Если есть soft delete
```

#### Шаг 2.2: Перенос кастомных настроек
```sql
UPDATE application_instances_new ain
SET
    custom_playbook_path = ai.custom_playbook_path,
    custom_artifact_url = ai.custom_artifact_list_url,
    custom_artifact_extension = ai.custom_artifact_extension
FROM application_instances ai
JOIN applications a ON ai.application_id = a.id
WHERE ain.server_id = a.server_id
  AND ain.instance_name = a.name;
```

### Фаза 3: Переключение (требуется короткий простой)

#### Шаг 3.1: Остановка приложения
```bash
# Остановить Flask приложение
systemctl stop appcontrol
```

#### Шаг 3.2: Переименование таблиц
```sql
BEGIN;

-- Сохраняем старые таблицы
ALTER TABLE applications RENAME TO applications_old;
ALTER TABLE application_instances RENAME TO application_instances_old;

-- Активируем новые
ALTER TABLE application_instances_new RENAME TO application_instances;

-- Обновляем sequences
SELECT setval('application_instances_id_seq',
    (SELECT MAX(id) FROM application_instances));

COMMIT;
```

#### Шаг 3.3: Обновление внешних ключей
```sql
-- Events
ALTER TABLE events RENAME COLUMN application_id TO instance_id;

-- HAProxy mappings
ALTER TABLE haproxy_servers
    DROP CONSTRAINT IF EXISTS haproxy_servers_application_id_fkey,
    ADD CONSTRAINT haproxy_servers_instance_id_fkey
        FOREIGN KEY (application_id)
        REFERENCES application_instances(id);

-- Eureka mappings
ALTER TABLE eureka_instances
    DROP CONSTRAINT IF EXISTS eureka_instances_application_id_fkey,
    ADD CONSTRAINT eureka_instances_instance_id_fkey
        FOREIGN KEY (application_id)
        REFERENCES application_instances(id);
```

### Фаза 4: Обновление кода

Развертывание новой версии приложения с обновленными моделями и запросами.

### Фаза 5: Очистка (после проверки)

```sql
-- После успешной работы в течение недели
DROP TABLE applications_old CASCADE;
DROP TABLE application_instances_old CASCADE;
```

---

## Изменения в коде

### 1. Модели (app/models/)

#### 1.1 Новая модель ApplicationCatalog
```python
# app/models/application_catalog.py
class ApplicationCatalog(db.Model):
    __tablename__ = 'application_catalog'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    app_type = db.Column(db.String(32), nullable=False)
    description = db.Column(db.Text)

    default_playbook_path = db.Column(db.String(255))
    default_artifact_url = db.Column(db.String(255))
    default_artifact_extension = db.Column(db.String(32))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    groups = db.relationship('ApplicationGroup', back_populates='catalog')
    instances = db.relationship('ApplicationInstance', back_populates='catalog')
```

#### 1.2 Обновление ApplicationInstance
```python
# app/models/application_instance.py (переименован из application.py)
class ApplicationInstance(db.Model):
    __tablename__ = 'application_instances'

    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys
    catalog_id = db.Column(db.Integer, db.ForeignKey('application_catalog.id'))
    group_id = db.Column(db.Integer, db.ForeignKey('application_groups.id'))
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), nullable=False)

    # Instance data
    instance_name = db.Column(db.String(128), nullable=False)
    instance_number = db.Column(db.Integer, default=0)
    app_type = db.Column(db.String(32), nullable=False)

    # ... остальные поля из старой Application модели ...

    # Relationships
    catalog = db.relationship('ApplicationCatalog', back_populates='instances')
    group = db.relationship('ApplicationGroup', back_populates='instances')
    server = db.relationship('Server', back_populates='instances')
    events = db.relationship('Event', back_populates='instance', cascade='all, delete-orphan')

    # Методы для совместимости
    @property
    def name(self):
        """Для обратной совместимости"""
        return self.instance_name

    def get_effective_playbook_path(self):
        """Приоритет: custom → group → catalog → config"""
        return (
            self.custom_playbook_path or
            (self.group and self.group.update_playbook_path) or
            (self.catalog and self.catalog.default_playbook_path) or
            current_app.config.get('DEFAULT_UPDATE_PLAYBOOK')
        )
```

#### 1.3 Обновление ApplicationGroup
```python
class ApplicationGroup(db.Model):
    # Добавляем связь со справочником
    catalog_id = db.Column(db.Integer, db.ForeignKey('application_catalog.id'))
    catalog = db.relationship('ApplicationCatalog', back_populates='groups')

    # Обновляем relationship
    instances = db.relationship(
        'ApplicationInstance',
        back_populates='group',
        lazy='dynamic'
    )

    # Удаляем старый relationship к Application
    # applications = ... (удалить)
```

### 2. Сервисы (app/services/)

#### 2.1 ApplicationGroupService
```python
# app/services/application_group_service.py

def resolve_application_group(instance):
    """Определяет группу для экземпляра приложения"""

    # Парсим имя экземпляра
    group_name, instance_number = parse_application_name(instance.instance_name)

    # Находим или создаем запись в каталоге
    catalog = ApplicationCatalog.query.filter_by(name=group_name).first()
    if not catalog:
        catalog = ApplicationCatalog(
            name=group_name,
            app_type=instance.app_type
        )
        db.session.add(catalog)

    # Связываем экземпляр с каталогом
    instance.catalog_id = catalog.id
    instance.instance_number = instance_number

    # Находим или создаем группу
    group = ApplicationGroup.query.filter_by(name=f"Группа {group_name}").first()
    if not group:
        group = ApplicationGroup(
            name=f"Группа {group_name}",
            catalog_id=catalog.id
        )
        db.session.add(group)

    # Связываем экземпляр с группой
    instance.group_id = group.id

    db.session.commit()
    return instance
```

#### 2.2 AgentService
```python
# app/services/agent_service.py

def update_server_applications(server):
    """Обновляет список приложений сервера"""

    # ... получение данных от агента ...

    for app_data in applications_data:
        # Ищем существующий экземпляр
        instance = ApplicationInstance.query.filter_by(
            server_id=server.id,
            instance_name=app_data['name'],
            app_type=app_type
        ).first()

        if not instance:
            instance = ApplicationInstance(
                server_id=server.id,
                instance_name=app_data['name'],
                app_type=app_type
            )
            db.session.add(instance)

        # Обновляем данные
        instance.status = app_data.get('status', 'unknown')
        instance.path = app_data.get('path')
        instance.version = app_data.get('version')
        # ... остальные поля ...

        # Определяем группу
        ApplicationGroupService.resolve_application_group(instance)

    # Помечаем отсутствующие как offline
    ApplicationInstance.query.filter(
        ApplicationInstance.server_id == server.id,
        ApplicationInstance.instance_name.notin_(seen_names)
    ).update({'status': 'offline', 'last_seen': datetime.utcnow()})

    db.session.commit()
```

### 3. API Routes

#### 3.1 Основные изменения в applications_routes.py
```python
# app/api/applications_routes.py

@bp.route('/applications')
def get_applications():
    # Было:
    # apps = Application.query.filter_by(server_id=server_id).all()

    # Стало:
    instances = ApplicationInstance.query.filter_by(server_id=server_id).all()

    return jsonify([{
        'id': inst.id,
        'name': inst.instance_name,
        'group_name': inst.group.name if inst.group else None,
        'instance_number': inst.instance_number,
        'status': inst.status,
        'server': inst.server.name,
        # ...
    } for inst in instances])

@bp.route('/applications/batch_update', methods=['POST'])
def batch_update_applications():
    app_ids = request.json.get('application_ids', [])

    # Было:
    # apps = Application.query.filter(Application.id.in_(app_ids)).all()

    # Стало:
    instances = ApplicationInstance.query.filter(
        ApplicationInstance.id.in_(app_ids)
    ).all()

    # Группировка по стратегии
    grouped = {}
    for inst in instances:
        if not inst.group:
            continue

        strategy = inst.group.batch_grouping_strategy

        if strategy == 'by_group':
            key = (inst.server_id, inst.group_id, playbook)
        elif strategy == 'by_server':
            key = (inst.server_id, playbook)
        elif strategy == 'by_instance_name':
            key = (inst.server_id, inst.instance_name, playbook)
        else:  # no_grouping
            key = (inst.id,)

        grouped.setdefault(key, []).append(inst)

    # Создание задач
    for group_key, group_instances in grouped.items():
        task = Task(
            type='update',
            instance_ids=[inst.id for inst in group_instances],
            # ...
        )
        task_queue.add_task(task)
```

### 4. Task Queue

#### 4.1 Обновление queue.py
```python
# app/tasks/queue.py

def _process_update_task(self, task):
    """Обрабатывает задачу обновления"""

    # Получаем экземпляры
    if task.params.get('instance_ids'):
        # Было: Application.query.filter(Application.id.in_(app_ids))
        instances = ApplicationInstance.query.filter(
            ApplicationInstance.id.in_(task.params['instance_ids'])
        ).all()
    else:
        # Одиночный экземпляр
        instance = ApplicationInstance.query.get(task.instance_id)
        instances = [instance] if instance else []

    if not instances:
        self._log_event(task, 'failed', 'Экземпляры не найдены')
        return

    # Подготовка параметров для Ansible
    for inst in instances:
        server = inst.server

        # Для orchestrator используем формат server::app
        composite_name = f"{server.name.split('.')[0]}::{inst.instance_name}"

        # Определяем playbook
        playbook = inst.get_effective_playbook_path()

        # ... выполнение playbook ...
```

---

## Оценка рисков

### Критические компоненты

| Компонент | Уровень риска | Причина | Митигация |
|-----------|---------------|---------|-----------|
| Task Queue | **КРИТИЧЕСКИЙ** | Центральная логика обновлений | Тщательное тестирование, постепенный rollout |
| Batch Operations | **КРИТИЧЕСКИЙ** | Массовые операции над приложениями | Создать compatibility layer |
| Agent Discovery | **ВЫСОКИЙ** | Автоматическое обнаружение приложений | Двойная проверка логики создания |
| Event System | **ВЫСОКИЙ** | Внешние ключи на applications | Миграция FK на новую таблицу |
| API Endpoints | **ВЫСОКИЙ** | ~30 эндпоинтов затронуты | Версионирование API |
| Frontend | **СРЕДНИЙ** | JavaScript вызовы API | Обновить после backend |

### Потенциальные проблемы

1. **Простой при миграции**
   - Риск: Длительный простой при переключении таблиц
   - Митигация: Использовать Blue-Green deployment

2. **Несовместимость API**
   - Риск: Сломанные клиенты
   - Митигация: Compatibility layer, версионирование

3. **Производительность**
   - Риск: Новые JOIN'ы могут быть медленнее
   - Митигация: Правильные индексы, анализ запросов

---

## Контрольный список

### Подготовка
- [ ] Тестовое окружение с копией production данных
- [ ] План отката
- [ ] Уведомление пользователей о maintenance window

### База данных
- [ ] Создать таблицу application_catalog
- [ ] Создать таблицу application_instances_new
- [ ] Добавить catalog_id в application_groups
- [ ] Написать и протестировать миграционные скрипты
- [ ] Создать индексы
- [ ] Проверить внешние ключи

### Модели (app/models/)
- [ ] ApplicationCatalog - новая модель
- [ ] ApplicationInstance - переименовать из Application
- [ ] ApplicationGroup - обновить relationships
- [ ] Event - изменить FK на instance_id
- [ ] Server - обновить relationships

### Сервисы (app/services/)
- [ ] ApplicationGroupService - обновить resolve логику
- [ ] AgentService - обновить discovery
- [ ] ApplicationCatalogService - новый сервис
- [ ] SSHAnsibleService - проверить параметры

### API (app/api/)
- [ ] applications_routes.py - все методы (7 функций)
- [ ] app_groups_routes.py - все методы (8 функций)
- [ ] servers_routes.py - методы с app count
- [ ] nexus_routes.py - artifact методы
- [ ] web.py - SSE события

### Task Queue
- [ ] queue.py - _process_update_task()
- [ ] queue.py - _process_start_task()
- [ ] queue.py - _process_stop_task()
- [ ] queue.py - _process_restart_task()
- [ ] monitoring.py - фоновые задачи

### Тестирование
- [ ] Unit тесты для новых моделей
- [ ] Integration тесты для API
- [ ] E2E тесты для критических сценариев
- [ ] Performance тесты
- [ ] Тест миграции на копии production

### Развертывание
- [ ] Обновить CI/CD pipeline
- [ ] Подготовить rollback скрипты
- [ ] Документация для ops команды
- [ ] Monitoring и alerting

### После развертывания
- [ ] Проверить все критические функции
- [ ] Мониторинг производительности
- [ ] Проверить логи на ошибки
- [ ] Собрать feedback от пользователей
- [ ] Удалить старые таблицы (через неделю)

---

## Файлы для изменения

### Критические файлы (первый приоритет)
```
/app/models/application.py → application_instance.py
/app/models/application_group.py
/app/models/application_catalog.py (новый)
/app/services/application_group_service.py
/app/services/agent_service.py
/app/tasks/queue.py
/app/api/applications_routes.py
/app/api/app_groups_routes.py
```

### Важные файлы (второй приоритет)
```
/app/models/event.py
/app/models/server.py
/app/api/servers_routes.py
/app/api/nexus_routes.py
/app/tasks/monitoring.py
/app/api/web.py
```

### Вспомогательные файлы (третий приоритет)
```
/app/services/ssh_ansible_service.py
/app/services/eureka_service.py
/app/services/haproxy_service.py
/app/api/orchestrator_routes.py
/app/api/haproxy_routes.py
/app/api/eureka_routes.py
```

---

## Альтернативный подход (минимальный рефакторинг)

Если полный рефакторинг слишком рискованный, можно использовать минимальный подход:

1. **Оставить таблицу applications как есть** (переименовать в application_instances)
2. **Добавить application_catalog** только для новых фич
3. **Создать compatibility views** для старых запросов
4. **Постепенная миграция** модуль за модулем

### Преимущества минимального подхода
- Меньше риска
- Можно делать постепенно
- Нет большого простоя
- Легче откатить

### Недостатки
- Техдолг остается
- Сложность поддержки двух моделей
- Дольше по времени

---

## Заключение

Рефакторинг необходим для приведения БД к правильной концептуальной модели, но требует тщательной подготовки из-за широкого влияния на кодовую базу.

**Рекомендации:**
1. Начать с тестового окружения
2. Использовать feature flags для постепенного включения
3. Иметь план отката на каждом этапе
4. Рассмотреть минимальный подход если риски неприемлемы

**Ожидаемые преимущества после рефакторинга:**
- Четкая иерархия: Каталог → Группы → Экземпляры
- Устранение дублирования данных
- Упрощение кода и запросов
- Лучшая масштабируемость
- Возможность добавления новых функций

---

*Документ подготовлен: 2025-11-17*
*Версия: 1.0*
*Автор: AI Assistant*
# Карточка-инструкция: Развитие системы тегов

## Быстрый старт: Добавление нового системного тега

### Шаг 1: Добавить определение тега

```python
# app/services/system_tags/definitions.py

SYSTEM_TAGS['new_tag'] = SystemTagDefinition(
    name='new_tag',
    display_name='NEW',                    # Короткое имя для UI
    trigger_type=TriggerType.MANUAL,       # или MAPPING, APP_TYPE, CUSTOM
    config_key='AUTO_TAG_NEW_TAG_ENABLED', # Ключ в конфиге (пустой для ручных)
    show_in_table=False,                   # Показывать в таблице приложений?
    description='Описание тега',
    border_color='#ff0000',                # Цвет рамки
    text_color='#ff0000'                   # Цвет текста
)
```

### Шаг 2: Добавить конфиг (для автоназначаемых)

```python
# app/config.py

AUTO_TAG_NEW_TAG_ENABLED = os.environ.get('AUTO_TAG_NEW_TAG_ENABLED', 'false').lower() == 'true'
```

### Шаг 3: Создать тег в БД (миграция)

```python
# migrations/versions/xxx_add_new_tag.py

op.execute("""
    INSERT INTO tags (name, display_name, is_system, show_in_table, description, border_color, text_color)
    VALUES ('new_tag', 'NEW', true, false, 'Описание', '#ff0000', '#ff0000')
    ON CONFLICT (name) DO NOTHING
""")
```

---

## Типы триггеров

### TriggerType.MANUAL
Только ручное назначение пользователем.

### TriggerType.MAPPING
Автоназначение при создании/удалении маппинга (HAProxy, Eureka).

```python
SystemTagDefinition(
    name='consul',
    trigger_type=TriggerType.MAPPING,
    mapping_entity_type='consul_service',  # Тип маппинга
    ...
)
```

### TriggerType.APP_TYPE
Автоназначение на основе app_type приложения.

```python
SystemTagDefinition(
    name='kubernetes',
    trigger_type=TriggerType.APP_TYPE,
    app_type_value='kubernetes',  # Значение app_type
    ...
)
```

### TriggerType.CUSTOM
Сложная логика через custom handlers.

```python
SystemTagDefinition(
    name='critical',
    trigger_type=TriggerType.CUSTOM,
    custom_should_assign=lambda inst, ctx: inst.status == 'error' and ctx.get('error_count', 0) > 5,
    custom_should_remove=lambda inst, ctx: inst.status != 'error',
    ...
)
```

---

## Добавление нового триггера

### 1. Добавить метод в SystemTagsService

```python
# app/services/system_tags/service.py

@classmethod
def on_new_event(cls, instance: 'ApplicationInstance', context: dict):
    """Вызывается при новом событии"""
    for tag_def in SYSTEM_TAGS.values():
        if tag_def.trigger_type != TriggerType.NEW_TYPE:
            continue
        if not cls.is_tag_enabled(tag_def):
            continue
        # Логика назначения/удаления
```

### 2. Вызвать триггер в нужном месте

```python
# app/services/some_service.py

from app.services.system_tags import SystemTagsService

SystemTagsService.on_new_event(instance, {'key': 'value'})
```

---

## Миграция к Full Handler паттерну

Если система вырастет до 50+ тегов со сложной логикой:

### Структура после миграции

```
app/services/system_tags/
├── __init__.py
├── definitions.py           # Без изменений
├── service.py               # Делегирует handlers
└── handlers/                # НОВАЯ папка
    ├── __init__.py
    ├── base.py              # AbstractTagHandler
    ├── ml_handler.py        # ML-based логика
    └── external_handler.py  # Внешние API
```

### Шаги миграции

1. Создать `handlers/base.py`:
```python
from abc import ABC, abstractmethod

class AbstractTagHandler(ABC):
    tag_name: str

    @abstractmethod
    def should_assign(self, instance, context) -> bool:
        pass

    @abstractmethod
    def should_remove(self, instance, context) -> bool:
        pass
```

2. Вынести сложную логику из `custom_should_assign` в handlers
3. В `service.py` добавить вызов handlers
4. Простые теги остаются декларативными в SYSTEM_TAGS

---

## Чеклист при добавлении тега

- [ ] Добавлено определение в `definitions.py`
- [ ] Добавлен конфиг в `config.py` (если автоназначаемый)
- [ ] Создана миграция для добавления в БД
- [ ] Добавлен триггер в соответствующий сервис (если нужен)
- [ ] Протестировано автоназначение
- [ ] Протестировано переопределение (auto_assign_disabled)
- [ ] Обновлена документация

---

## Полезные команды

```bash
# Применить миграцию
flask db upgrade

# Создать новую миграцию
flask db migrate -m "Add new system tag"

# Запустить миграцию существующих данных
flask shell
>>> from app.services.system_tags import SystemTagsService
>>> SystemTagsService.migrate_existing_data()
```

---

## Конфигурационные параметры

| Параметр | Default | Описание |
|----------|---------|----------|
| `SYSTEM_TAGS_ENABLED` | true | Глобальный выключатель |
| `AUTO_TAG_HAPROXY_ENABLED` | true | H тег |
| `AUTO_TAG_EUREKA_ENABLED` | true | E тег |
| `AUTO_TAG_DOCKER_ENABLED` | true | docker тег |
| `AUTO_TAG_SMF_ENABLED` | false | smf тег |
| `AUTO_TAG_SYSCTL_ENABLED` | false | sysctl тег |

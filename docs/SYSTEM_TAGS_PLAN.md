# План: Система системных тегов с автоназначением

## Обзор

Доработка системы тегов для поддержки системных тегов, которые автоматически назначаются экземплярам приложений на основе их состояния и интеграций.

## Архитектура: Гибридный подход (Декларативный + Handlers)

### Структура (3 файла, ~260 строк)

```
app/services/system_tags/
├── __init__.py              # Экспорт + регистрация
├── definitions.py           # Конфигурация тегов (dataclass + SYSTEM_TAGS)
└── service.py               # SystemTagsService (~150 строк)
```

### Системные теги

| Тег | Display | show_in_table | Автоназначение | Описание |
|-----|---------|---------------|----------------|----------|
| `haproxy` | H | ✅ | При создании маппинга HAProxy | Связь с HAProxy |
| `eureka` | E | ✅ | При создании маппинга Eureka | Регистрация в Eureka |
| `docker` | docker | ✅ | При app_type='docker' | Docker-контейнер |
| `disable` | disable | ❌ | Ручной | Отключенное приложение |
| `system` | SYS | ❌ | Ручной | Системное приложение |
| `smf` | smf | ❌ | Ручной | SMF сервис |
| `sysctl` | sysctl | ❌ | Ручной | Systemctl сервис |
| `ver.lock` | v.lock | ❌ | Ручной | Блокировка обновлений |
| `status.lock` | s.lock | ❌ | Ручной | Блокировка start/stop/restart |

## Глобальные параметры конфигурации

```python
SYSTEM_TAGS_ENABLED = 'true'           # Глобальный выключатель
AUTO_TAG_HAPROXY_ENABLED = 'true'      # Автоназначение H
AUTO_TAG_EUREKA_ENABLED = 'true'       # Автоназначение E
AUTO_TAG_DOCKER_ENABLED = 'true'       # Автоназначение docker
AUTO_TAG_SMF_ENABLED = 'false'         # На будущее
AUTO_TAG_SYSCTL_ENABLED = 'false'      # На будущее
```

## Изменения в модели данных

### Модель Tag
```python
is_system = db.Column(db.Boolean, default=False)      # Системный тег
show_in_table = db.Column(db.Boolean, default=False)  # Показывать в таблице
```

### Модель ApplicationInstanceTag
```python
auto_assign_disabled = db.Column(db.Boolean, default=False)  # Переопределение
```

## Точки интеграции

| Триггер | Метод сервиса | Где вызывать |
|---------|---------------|--------------|
| Создание маппинга | `on_mapping_created()` | `mapping_service.create_mapping()` |
| Удаление маппинга | `on_mapping_deleted()` | `mapping_service.delete_mapping()` |
| Синхронизация приложения | `on_app_synced()` | `monitoring.py` |

## Порядок реализации

### Этап 1: Модель и миграция
1. Обновить модель Tag - добавить `is_system`, `show_in_table`
2. Обновить модель ApplicationInstanceTag - добавить `auto_assign_disabled`
3. Добавить параметры конфигурации в `app/config.py`
4. Создать и применить миграцию
5. Создать системные теги через миграцию

### Этап 2: Сервис системных тегов
6. Создать директорию `app/services/system_tags/`
7. Реализовать `definitions.py` - SystemTagDefinition dataclass + SYSTEM_TAGS реестр
8. Реализовать `service.py` - SystemTagsService с методами триггеров
9. Создать `__init__.py` - экспорт публичного API

### Этап 3: Интеграция с существующим кодом
10. Интегрировать в `mapping_service.py`
11. Интегрировать в `monitoring.py`
12. Обновить API routes для защиты системных тегов
13. Добавить endpoint для управления `auto_assign_disabled`

### Этап 4: Frontend
14. Обновить `tags-renderer.js` для фильтрации по `show_in_table`
15. Обновить `tags-modal.js` для отображения системных тегов
16. Обновить модалку информации для показа всех тегов
17. Добавить CSS стили

### Этап 5: Миграция существующих данных
18. Метод `SystemTagsService.migrate_existing_data()` для batch-назначения
19. Вызвать при старте приложения или вручную через CLI

## Файлы для изменения

| Файл | Изменения |
|------|-----------|
| `app/config.py` | Параметры SYSTEM_TAGS_ENABLED, AUTO_TAG_*_ENABLED |
| `app/models/tag.py` | Поля `is_system`, `show_in_table`, `auto_assign_disabled` |
| `app/services/mapping_service.py` | Вызов SystemTagsService |
| `app/tasks/monitoring.py` | Вызов SystemTagsService |
| `app/api/tags_routes.py` | Защита системных тегов |
| `app/static/js/applications/ui/tags-renderer.js` | Фильтрация по `show_in_table` |
| `app/static/js/applications/modals/tags-modal.js` | UI для системных тегов |
| `app/static/css/styles.css` | Стили для системных тегов |

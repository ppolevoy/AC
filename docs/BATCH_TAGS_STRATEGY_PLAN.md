# План реализации Batch стратегий `by_tags` и `by_tags_and_group`

> **Статус:** Запланировано
> **Дата создания:** 2025-11-26
> **Приоритет:** Низкий (Фаза 7 системы тегов)

---

## Контекст

Система тегов реализована на ~85%. Остались batch стратегии группировки по тегам.

### Текущие стратегии (app/models/application_group.py)

```python
BATCH_GROUPING_STRATEGIES = {
    'by_group': 'по (server, playbook, group_id)',
    'by_server': 'по (server, playbook)',
    'by_instance_name': 'по (server, playbook, original_name)',
    'no_grouping': 'каждый экземпляр отдельно'
}
```

### Логика группировки (app/api/applications_routes.py:277-439)

1. Для каждого приложения определяется стратегия из его группы
2. Формируется `group_key` на основе стратегии
3. Приложения группируются по ключам
4. Для каждой группы создаётся отдельная Task

---

## Новые стратегии

### `by_tags` - Группировка по набору тегов

Приложения с **идентичным набором тегов** попадают в одну задачу.

**Пример:**
| Приложение | Теги | group_key |
|------------|------|-----------|
| jurws_1 | production, critical | (server1, playbook.yml, ('critical', 'production')) |
| jurws_2 | production, critical | (server1, playbook.yml, ('critical', 'production')) |
| mobws_1 | production | (server1, playbook.yml, ('production',)) |

**Результат:** jurws_1 и jurws_2 в одной задаче, mobws_1 отдельно

---

### `by_tags_and_group` - Комбинированная группировка

Группировка по **группе приложений И тегам**. Разделяет приложения одной группы по тегам.

**Пример:**
| Приложение | Группа | Теги | group_key |
|------------|--------|------|-----------|
| jurws_1 | JUR | production | (server1, playbook.yml, 1, ('production',)) |
| jurws_2 | JUR | test | (server1, playbook.yml, 1, ('test',)) |
| mobws_1 | MOB | production | (server1, playbook.yml, 2, ('production',)) |

**Результат:** 3 отдельные задачи

---

## План реализации

### Шаг 1: Добавить константы

**Файл:** `app/models/application_group.py:9-14`

```python
BATCH_GROUPING_STRATEGIES = {
    'by_group': 'Группировать по (server, playbook, group_id) - разные группы в разных задачах',
    'by_server': 'Группировать по (server, playbook) - игнорировать group_id',
    'by_instance_name': 'Группировать по (server, playbook, original_name) - по имени экземпляра',
    'no_grouping': 'Не группировать - каждый экземпляр в отдельной задаче',
    # НОВЫЕ:
    'by_tags': 'Группировать по набору тегов - приложения с одинаковыми тегами вместе',
    'by_tags_and_group': 'Группировать по (group_id, tags) - комбинированная группировка'
}
```

---

### Шаг 2: Оптимизация загрузки (избежать N+1)

**Файл:** `app/api/applications_routes.py` (~строка 320)

**Было:**
```python
applications = Application.query.filter(Application.id.in_(app_ids)).all()
```

**Стало:**
```python
from sqlalchemy.orm import joinedload

applications = Application.query.filter(
    Application.id.in_(app_ids)
).options(
    joinedload(Application.tags),
    joinedload(Application.group).joinedload(ApplicationGroup.tags)
).all()
```

---

### Шаг 3: Логика группировки по тегам

**Файл:** `app/api/applications_routes.py` (после строки 373, перед `else:`)

```python
elif strategy == 'by_tags':
    # Группировка по набору тегов приложения (собственных + унаследованных)
    app_tags = set(t.name for t in app.tags)
    if group:
        app_tags.update(t.name for t in group.tags)
    tags_key = tuple(sorted(app_tags)) if app_tags else ('__no_tags__',)

    if use_orchestrator:
        group_key = (playbook_path, tags_key)
    else:
        group_key = (app.server_id, playbook_path, tags_key)

elif strategy == 'by_tags_and_group':
    # Комбинированная группировка: group_id + набор тегов
    app_tags = set(t.name for t in app.tags)
    if group:
        app_tags.update(t.name for t in group.tags)
    tags_key = tuple(sorted(app_tags)) if app_tags else ('__no_tags__',)

    group_id = group.id if group else None

    if use_orchestrator:
        group_key = (playbook_path, group_id, tags_key)
    else:
        group_key = (app.server_id, playbook_path, group_id, tags_key)
```

---

### Шаг 4: Override стратегии через API (опционально)

**Файл:** `app/api/applications_routes.py` (после строки 306)

```python
# Получаем override стратегии (если передан)
strategy_override = data.get('grouping_strategy_override')
```

**В цикле группировки (строка 338):**
```python
if strategy_override:
    strategy = strategy_override
else:
    strategy = group.get_batch_grouping_strategy() if group else 'by_group'
```

---

### Шаг 5: UI для выбора стратегии (опционально)

**Файл:** `app/static/js/applications/applications.js`

В модальном окне batch update добавить select:

```html
<div class="form-group">
    <label>Стратегия группировки:</label>
    <select id="batch-strategy" class="form-control">
        <option value="">Из настроек группы (по умолчанию)</option>
        <option value="by_group">По группам</option>
        <option value="by_server">По серверам</option>
        <option value="by_tags">По тегам</option>
        <option value="by_tags_and_group">По группам и тегам</option>
        <option value="no_grouping">Без группировки</option>
    </select>
</div>
```

И передавать в API:
```javascript
const strategySelect = document.getElementById('batch-strategy');
const strategyOverride = strategySelect ? strategySelect.value : null;

fetch('/api/applications/batch_update', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        app_ids: selectedAppIds,
        distr_url: distrUrl,
        mode: mode,
        grouping_strategy_override: strategyOverride || undefined
    })
});
```

---

## Файлы для изменения

| Файл | Изменения |
|------|-----------|
| `app/models/application_group.py` | +2 константы в `BATCH_GROUPING_STRATEGIES` |
| `app/api/applications_routes.py` | +joinedload, +2 elif блока, +strategy_override |
| `app/static/js/applications/applications.js` | (опционально) UI select для стратегии |

---

## Тестовые сценарии

### Тест 1: by_tags базовый
1. Создать теги: `production`, `test`, `critical`
2. Присвоить 5 приложениям:
   - app1, app2: `production, critical`
   - app3: `production`
   - app4, app5: `test`
3. Batch update с `grouping_strategy_override: 'by_tags'`
4. **Ожидание:** 3 задачи (2+1+2)

### Тест 2: by_tags с оркестратором
1. Те же приложения на разных серверах
2. Batch update с оркестратором и `by_tags`
3. **Ожидание:** server_id НЕ влияет на группировку

### Тест 3: by_tags_and_group
1. Группа JUR: jurws_1 (prod), jurws_2 (test)
2. Группа MOB: mobws_1 (prod), mobws_2 (prod)
3. Batch update с `by_tags_and_group`
4. **Ожидание:** 3 задачи (JUR+prod, JUR+test, MOB+prod)

### Тест 4: Приложения без тегов
1. app1: без тегов
2. app2: без тегов
3. app3: `production`
4. **Ожидание:** 2 задачи (app1+app2 с `__no_tags__`, app3 отдельно)

### Тест 5: Override vs настройки группы
1. Группа с `batch_grouping_strategy = 'by_server'`
2. Вызов API с `grouping_strategy_override: 'by_tags'`
3. **Ожидание:** Используется override (`by_tags`)

---

## Связанные файлы

- `TAG_SYSTEM_IMPLEMENTATION_PLAN.md` - основной план системы тегов
- `app/models/tag.py` - модели тегов
- `app/api/tags_routes.py` - API тегов
- `BUGFIX_TAGS.md` - исправление бага частичных тегов

---

## Примечания

- Теги приложения включают как собственные теги (`app.tags`), так и унаследованные от группы (`app.group.tags`)
- Используется `tuple(sorted(app_tags))` для консистентного ключа независимо от порядка присвоения тегов
- Приложения без тегов группируются вместе под ключом `('__no_tags__',)`

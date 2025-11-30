# Архитектура процесса обновления приложений

Документ описывает полную логику процесса обновления приложений через Ansible playbooks.

## Общая схема процесса

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (UI)                                        │
│  Пользователь выбирает приложения, указывает артефакт и режим обновления    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  API ENDPOINT                                                                │
│  POST /api/applications/<id>/update       (одиночное)                       │
│  POST /api/applications/batch_update      (групповое)                       │
│  app/api/applications_routes.py:169, 305                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. ОПРЕДЕЛЕНИЕ PLAYBOOK PATH                                               │
│     app/models/application_instance.py:147-169                              │
│                                                                              │
│     Приоритет:                                                               │
│     1. instance.custom_playbook_path                                         │
│     2. group.update_playbook_path                                           │
│     3. catalog.default_playbook_path                                        │
│     4. Config.DEFAULT_UPDATE_PLAYBOOK                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. ГРУППИРОВКА (для batch_update)                                          │
│     app/api/applications_routes.py:356-404                                  │
│                                                                              │
│     Стратегии (group.batch_grouping_strategy):                              │
│     • by_group    → (server, playbook, group_id)                            │
│     • by_server   → (server, playbook)                                      │
│     • by_instance_name → (server, playbook, original_name)                  │
│     • no_grouping → каждое приложение отдельно                              │
│                                                                              │
│     Если orchestrator → server_id убирается из ключа группировки            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. СОЗДАНИЕ TASK                                                           │
│     app/api/applications_routes.py:247-263, 420-436                         │
│                                                                              │
│     Task(                                                                    │
│       task_type='update',                                                   │
│       params={                                                               │
│         'app_ids': [...],              # для групповых                      │
│         'distr_url': '...',            # URL артефакта                      │
│         'mode': 'immediate|deliver|night-restart',                          │
│         'playbook_path': '...',        # путь к playbook                    │
│         'orchestrator_playbook': '...', # путь к оркестратору               │
│         'drain_wait_time': 5           # минуты ожидания drain              │
│       }                                                                      │
│     )                                                                        │
│                                                                              │
│     → task_queue.add_task(task)  # Сохранение в БД + добавление в очередь   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. ОБРАБОТКА ОЧЕРЕДИ (фоновый поток)                                       │
│     app/tasks/queue.py:242-328                                              │
│                                                                              │
│     • Получение task_id из очереди                                          │
│     • Загрузка Task из БД                                                   │
│     • Изменение статуса: pending → processing                               │
│     • Вызов _process_update_task(task_id)                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. _process_update_task()                                                  │
│     app/tasks/queue.py:601-955                                              │
│                                                                              │
│     5.1 Проверка типа задачи:                                               │
│         • is_batch_task = params.app_ids существует и len >= 1              │
│                                                                              │
│     5.2 Загрузка приложений:                                                │
│         • Групповая: ApplicationInstance.query.filter(id.in_(app_ids))      │
│         • Одиночная: ApplicationInstance.query.get(instance_id)             │
│                                                                              │
│     5.3 Извлечение параметров:                                              │
│         • distr_url (обязательный)                                          │
│         • mode (immediate/deliver/night-restart)                            │
│         • playbook_path (обязательный)                                      │
│         • orchestrator_playbook                                             │
│         • drain_wait_time                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌─────────────────────────────┐   ┌─────────────────────────────────────────┐
│  БЕЗ ОРКЕСТРАТОРА           │   │  С ОРКЕСТРАТОРОМ                        │
│  (orchestrator == 'none')   │   │  app/tasks/queue.py:694-871             │
│                              │   │                                         │
│  Используется                │   │  5.4 Подготовка HAProxy mapping:       │
│  playbook_path напрямую     │   │      _prepare_orchestrator_instances_   │
│                              │   │      with_haproxy(apps)                │
│                              │   │      → composite_names:                 │
│                              │   │        ["server::app::haproxy_server"]  │
│                              │   │      → haproxy_api_url                  │
│                              │   │      → haproxy_backend                  │
│                              │   │                                         │
│                              │   │  5.5 Загрузка OrchestratorPlaybook     │
│                              │   │      из БД:                             │
│                              │   │      - required_params                  │
│                              │   │      - optional_params                  │
│                              │   │                                         │
│                              │   │  5.6 Формирование extra_params:        │
│                              │   │      - app_instances                    │
│                              │   │      - drain_delay (секунды)            │
│                              │   │      - update_playbook                  │
│                              │   │      - haproxy_api_url                  │
│                              │   │      - haproxy_backend                  │
│                              │   │      - wait_after_update                │
│                              │   │      + кастомные из playbook_path       │
│                              │   │        (например {unpack=true})         │
│                              │   │                                         │
│                              │   │  5.7 Формирование playbook_path:       │
│                              │   │      "{orchestrator.yml} {params...}"   │
└─────────────────────────────┘   └─────────────────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6. SSH ANSIBLE SERVICE                                                     │
│     app/services/ssh_ansible_service.py:430-624                             │
│                                                                              │
│     ssh_service.update_application(                                         │
│       server_name, app_name, app_id, distr_url,                             │
│       mode, playbook_path, extra_params, task_id                            │
│     )                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6.1 ПАРСИНГ PLAYBOOK CONFIG                                                │
│      parse_playbook_config(playbook_path_with_params)                       │
│      app/services/ssh_ansible_service.py:138-203                            │
│                                                                              │
│      Входная строка: "/path/playbook.yml {server} {app} {unpack=true}"      │
│                                                                              │
│      Результат PlaybookConfig:                                              │
│        path: "/path/playbook.yml"                                           │
│        parameters: [                                                         │
│          PlaybookParameter(name='server', value=None, is_custom=False),     │
│          PlaybookParameter(name='app', value=None, is_custom=False),        │
│          PlaybookParameter(name='unpack', value='true', is_custom=True)     │
│        ]                                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6.2 ВАЛИДАЦИЯ ПАРАМЕТРОВ                                                   │
│      validate_parameters(parameters)                                        │
│      app/services/ssh_ansible_service.py:205-241                            │
│                                                                              │
│      • Динамические параметры → проверка в AVAILABLE_VARIABLES             │
│      • Кастомные параметры → валидация имени и значения (regex)            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6.3 ФОРМИРОВАНИЕ CONTEXT VARS                                              │
│      build_context_vars(...)                                                │
│      app/services/ssh_ansible_service.py:261-341                            │
│                                                                              │
│      Доступные переменные (AVAILABLE_VARIABLES):                            │
│      • server, app, app_name, app_id, server_id                             │
│      • distr_url, image_url, mode                                           │
│      • app_instances (для оркестратора)                                     │
│      • drain_delay, update_playbook, wait_after_update                      │
│      • haproxy_api_url, haproxy_backend                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6.4 ФОРМИРОВАНИЕ EXTRA VARS                                                │
│      build_extra_vars(playbook_config, context_vars)                        │
│      app/services/ssh_ansible_service.py:343-388                            │
│                                                                              │
│      • Кастомные параметры → используют явное значение                      │
│      • Динамические параметры → берут значение из context_vars             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6.5 ФОРМИРОВАНИЕ ANSIBLE КОМАНДЫ                                           │
│      build_ansible_command(playbook_path, extra_vars)                       │
│      app/services/ssh_ansible_service.py:390-428                            │
│                                                                              │
│      Результат:                                                              │
│      cd /etc/ansible && ansible-playbook /path/playbook.yml \               │
│        -e 'server="fdmz01"' \                                               │
│        -e 'app="jurws_1"' \                                                 │
│        -e 'distr_url="http://nexus/.../app-1.2.3.tar.gz"' \                │
│        -e 'unpack="true"' \                                                 │
│        -v                                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6.6 ВЫПОЛНЕНИЕ ЧЕРЕЗ SSH                                                   │
│      _execute_ansible_command(ansible_cmd, ...)                             │
│      app/services/ssh_ansible_service.py:767-869                            │
│                                                                              │
│      • SSH команда формируется через _build_ssh_command()                   │
│      • Процесс регистрируется для возможности отмены (task_id → PID)       │
│      • Чтение stdout/stderr в реальном времени                              │
│      • Парсинг вывода (_parse_ansible_output) для логирования этапов       │
│      • Таймаут: SSH_COMMAND_TIMEOUT (default 300s)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  7. ЗАВЕРШЕНИЕ ЗАДАЧИ                                                       │
│     app/tasks/queue.py:288-327                                              │
│                                                                              │
│     Успех:                                                                   │
│       task.status = 'completed'                                             │
│       task.result = ansible_output                                          │
│       → Обновление ApplicationInstance.distr_path, version                  │
│       → Запись в ApplicationVersionHistory                                  │
│                                                                              │
│     Ошибка:                                                                  │
│       task.status = 'failed'                                                │
│       task.error = error_message                                            │
│                                                                              │
│     События (Event) создаются на каждом этапе:                              │
│       • pending → при создании задачи                                       │
│       • success/failed → при завершении                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Приоритет выбора Playbook

Метод `get_effective_playbook_path()` в `app/models/application_instance.py:147-169`:

```python
def get_effective_playbook_path(self):
    # 1. Индивидуальный путь экземпляра
    if self.custom_playbook_path:
        return self.custom_playbook_path

    # 2. Групповой путь
    if self.group and self.group.update_playbook_path:
        return self.group.update_playbook_path

    # 3. Путь из каталога
    if self.catalog and self.catalog.default_playbook_path:
        return self.catalog.default_playbook_path

    # 4. Дефолтный путь из конфига
    return Config.DEFAULT_UPDATE_PLAYBOOK  # '/etc/ansible/update-app.yml'
```

| Приоритет | Источник | Поле |
|-----------|----------|------|
| 1 | ApplicationInstance | `custom_playbook_path` |
| 2 | ApplicationGroup | `update_playbook_path` |
| 3 | ApplicationCatalog | `default_playbook_path` |
| 4 | Config | `DEFAULT_UPDATE_PLAYBOOK` |

---

## Стратегии группировки (Batch Update)

Определяются в `ApplicationGroup.batch_grouping_strategy`:

| Стратегия | Ключ группировки | Описание |
|-----------|------------------|----------|
| `by_group` | (server, playbook, group_id) | По умолчанию. Разные группы обновляются отдельно |
| `by_server` | (server, playbook) | Игнорирует group_id, объединяет приложения на сервере |
| `by_instance_name` | (server, playbook, original_name) | Группирует по имени экземпляра |
| `no_grouping` | (app.id) | Каждое приложение в отдельной задаче |

**Важно**: При использовании оркестратора `server_id` убирается из ключа группировки, т.к. оркестратор сам управляет серверами.

---

## Формат параметров Playbook

Playbook path может содержать параметры в фигурных скобках:

```
/path/playbook.yml {server} {app} {distr_url} {unpack=true}
```

### Типы параметров

1. **Динамические** `{param}` - значение берется из контекста выполнения
2. **Кастомные** `{param=value}` - явное значение, передается как есть

### Доступные динамические переменные (AVAILABLE_VARIABLES)

| Переменная | Описание |
|------------|----------|
| `server` | Имя сервера |
| `app`, `app_name` | Имя приложения |
| `app_id` | ID приложения в БД |
| `server_id` | ID сервера в БД |
| `distr_url` | URL артефакта/дистрибутива |
| `image_url` | URL docker image (алиас для distr_url) |
| `mode` | Режим обновления (deliver, immediate, night-restart) |
| `app_instances` | Список server::app для оркестратора |
| `drain_delay` | Время ожидания после drain (секунды) |
| `update_playbook` | Имя playbook для обновления |
| `wait_after_update` | Время ожидания после обновления (секунды) |
| `haproxy_api_url` | URL HAProxy API |
| `haproxy_backend` | Имя backend в HAProxy |

---

## Оркестратор

### Workflow оркестратора

1. **Drain** - вывод серверов из HAProxy (`drain` command)
2. **Wait** - ожидание закрытия соединений (`drain_delay`)
3. **Update** - выполнение update playbook на drained серверах
4. **Wait** - ожидание запуска приложения (`wait_after_update`)
5. **Ready** - возврат серверов в HAProxy pool
6. **Repeat** - повтор для следующего batch

### Формат composite names для оркестратора

```
server::app::haproxy_server
```

Пример: `fdmz01::jurws_1::fdmz01_jurws_1`

### HAProxy Mapping

Маппинг берется из таблицы `ApplicationMapping`:
- `application_id` → `entity_id` (HAProxyServer.id)
- `entity_type` = 'haproxy_server'

Если маппинг не найден, используется стандартное именование: `{short_server}_{app_name}`

---

## Ключевые файлы

| Файл | Функция |
|------|---------|
| `app/api/applications_routes.py` | API endpoints для запуска обновлений |
| `app/models/application_instance.py` | `get_effective_playbook_path()` |
| `app/models/task.py` | Модель Task для хранения в БД |
| `app/tasks/queue.py` | TaskQueue + `_process_update_task()` |
| `app/services/ssh_ansible_service.py` | Выполнение Ansible через SSH |
| `app/models/orchestrator_playbook.py` | Метаданные оркестратора |
| `app/models/application_mapping.py` | Маппинг приложений на HAProxy/Eureka |

---

## Параметры обновления

| Параметр | Источник | Описание |
|----------|----------|----------|
| `distr_url` | UI | URL артефакта (Maven/Docker) |
| `mode` | UI | `immediate`, `deliver`, `night-restart` |
| `playbook_path` | Instance/Group/Catalog/Config | Путь к playbook |
| `orchestrator_playbook` | UI | Путь к orchestrator playbook |
| `drain_wait_time` | UI | Время ожидания drain (минуты) |
| `app_ids` | Batch only | ID приложений для группового обновления |

---

## Статусы задач

| Статус | Описание |
|--------|----------|
| `pending` | Задача создана, ожидает обработки |
| `processing` | Задача выполняется |
| `completed` | Задача успешно завершена |
| `failed` | Задача завершилась с ошибкой |

---

## Отмена задачи

Задачу можно отменить через `POST /api/tasks/<task_id>/cancel`:

1. Проверка статуса задачи (должен быть `processing`)
2. Вызов `SSHAnsibleService.cancel_task(task_id)`
3. Отправка SIGTERM процессу Ansible
4. Установка `task.cancelled = True`, `task.status = 'failed'`

---

## События (Events)

При обновлении создаются события в таблице `events`:

| Этап | event_type | status |
|------|------------|--------|
| Создание задачи | `update` | `pending` |
| Успешное завершение | `update` | `success` |
| Ошибка | `update` | `failed` |

---

## История версий

При успешном обновлении записывается в `ApplicationVersionHistory`:

- `old_version` / `new_version`
- `old_distr_path` / `new_distr_path`
- `old_tag` / `new_tag` (для Docker)
- `old_image` / `new_image` (для Docker)
- `changed_by` = 'user'
- `change_source` = 'update_task'
- `task_id`

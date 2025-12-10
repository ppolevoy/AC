# Техническое задание
# Система управления распределёнными приложениями "Application Control" (AC)

**Версия:** 1.0
**Дата:** 10.12.2024

---

## 1. Общие сведения

### 1.1 Назначение системы

**Application Control (AC)** — централизованная платформа управления распределёнными приложениями, обеспечивающая:
- Мониторинг состояния приложений на множестве серверов
- Оркестрацию обновлений с поддержкой zero-downtime через HAProxy
- Управление жизненным циклом приложений (запуск, остановка, перезапуск, обновление)
- Интеграцию с Ansible для автоматизации deployment
- Service discovery через Eureka

### 1.2 Целевая архитектура

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Application Control                              │
├──────────────┬──────────────┬──────────────┬───────────────────────────┤
│   Web UI     │   REST API   │  Task Queue  │   Monitoring Service      │
│  (Jinja2 +   │   (Flask     │  (Threading) │   (Async Polling)         │
│   Vanilla JS)│   Blueprint) │              │                           │
├──────────────┴──────────────┴──────────────┴───────────────────────────┤
│                         Service Layer                                    │
├───────────────────────────────────────────────────────────────────────┤
│  AgentService │ AnsibleService │ HAProxyService │ EurekaService │ ...   │
├───────────────────────────────────────────────────────────────────────┤
│                         Data Layer (SQLAlchemy)                          │
├───────────────────────────────────────────────────────────────────────┤
│                         PostgreSQL Database                              │
└───────────────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   FAgent API  │   │ Ansible Host  │   │   HAProxy/    │
│  (на серверах)│   │   (via SSH)   │   │   Eureka      │
└───────────────┘   └───────────────┘   └───────────────┘
```

### 1.3 Технологический стек

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Backend Framework | Flask | 2.x+ |
| ORM | SQLAlchemy + Flask-SQLAlchemy | 1.4+ |
| Миграции БД | Flask-Migrate (Alembic) | - |
| СУБД | PostgreSQL | 12+ |
| Async HTTP | aiohttp | 3.x |
| Frontend | Vanilla JavaScript (IIFE pattern) | ES6+ |
| CSS | Custom CSS + CSS Variables | - |
| Шаблонизатор | Jinja2 | - |
| Контейнеризация | Docker | - |

---

## 2. Функциональные требования

### 2.1 Модуль управления серверами

#### 2.1.1 Учёт серверов
- CRUD-операции для серверов (создание, просмотр, редактирование, удаление)
- Поля сервера:
  - `name` (уникальное имя, до 64 символов)
  - `ip` (IP-адрес, поддержка IPv4)
  - `port` (порт FAgent API)
  - `status` (online, offline)
  - `is_haproxy_node` (флаг: сервер содержит HAProxy)
  - `is_eureka_node` (флаг: сервер содержит Eureka)
  - `last_check` (время последней проверки)

#### 2.1.2 Мониторинг серверов
- Периодический опрос серверов через FAgent API
- Интервал опроса: конфигурируемый (по умолчанию 60 сек)
- Автоматическое обнаружение приложений на сервере
- Логирование событий подключения/отключения

#### 2.1.3 API серверов

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/servers` | GET | Список серверов |
| `/api/servers` | POST | Создание сервера |
| `/api/servers/<id>` | GET | Детали сервера |
| `/api/servers/<id>` | PUT | Обновление сервера |
| `/api/servers/<id>` | DELETE | Удаление сервера |
| `/api/servers/<id>/refresh` | POST | Принудительное обновление |
| `/api/servers/<id>/discover-haproxy-instances` | POST | Обнаружение HAProxy |

---

### 2.2 Модуль управления приложениями

#### 2.2.1 Каталог приложений (ApplicationCatalog)
Централизованный справочник типов приложений:
- `name` — базовое имя приложения
- `app_type` — тип (docker, eureka, site, service)
- `description` — описание
- `default_playbook_path` — путь к playbook по умолчанию
- `default_artifact_url` — URL артефактов по умолчанию
- `default_artifact_extension` — расширение файлов (jar, war, zip)

#### 2.2.2 Экземпляры приложений (ApplicationInstance)
Реальные запущенные экземпляры на серверах:

**Идентификация:**
- `instance_name` — полное имя (формат: `{base_name}_{instance_number}`)
- `instance_number` — номер экземпляра (парсится из имени)
- `app_type` — тип приложения

**Состояние:**
- `status` — online, offline, unknown, starting, stopping, no_data
- `last_seen` — время последнего online статуса

**Данные от агента:**
- `path` — путь к приложению
- `log_path` — путь к логам
- `version` — текущая версия
- `distr_path` — путь к дистрибутиву

**Docker-специфичные поля:**
- `container_id`, `container_name`
- `compose_project_dir`
- `image`, `tag`
- `eureka_registered`

**Eureka-специфичные поля:**
- `eureka_url`, `eureka_instance_id`
- `eureka_app_name`, `eureka_status`
- `eureka_health_url`, `eureka_vip`

**Сетевые параметры:**
- `ip` (поддержка IPv6), `port`, `pid`

**Кастомизация (переопределение настроек):**
- `custom_playbook_path`
- `custom_artifact_url`
- `custom_artifact_extension`

**Soft delete:**
- `deleted_at` — дата мягкого удаления

#### 2.2.3 Группы приложений (ApplicationGroup)
Логическая группировка экземпляров:
- `name` — уникальное имя группы
- `description` — описание
- `artifact_list_url` — URL для списка артефактов
- `artifact_extension` — расширение артефактов
- `update_playbook_path` — путь к playbook обновления
- `batch_grouping_strategy` — стратегия группировки для batch-операций:
  - `by_group` — по группе (по умолчанию)
  - `by_server` — по серверу
  - `by_instance_name` — по имени экземпляра
  - `no_grouping` — без группировки

#### 2.2.4 Иерархия разрешения настроек
Приоритет (от высшего к низшему):
1. `ApplicationInstance.custom_*` — индивидуальные настройки
2. `ApplicationGroup.*` — групповые настройки
3. `ApplicationCatalog.default_*` — настройки каталога
4. `Config.DEFAULT_*` — глобальные настройки

#### 2.2.5 API приложений

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/applications` | GET | Список приложений (фильтры: server_id, type) |
| `/api/applications/<id>` | GET | Детали приложения |
| `/api/applications/<id>/update` | POST | Обновление приложения |
| `/api/applications/batch_update` | POST | Batch обновление |
| `/api/applications/<id>/manage` | POST | Управление (start/stop/restart) |
| `/api/applications/bulk/manage` | POST | Массовое управление |
| `/api/applications/grouped` | GET | Группировка по имени |
| `/api/application-groups` | GET/POST | Управление группами |
| `/api/application-groups/<id>` | GET/PUT/DELETE | CRUD группы |

---

### 2.3 Система тегов

#### 2.3.1 Модель тега (Tag)
- `name` — уникальный идентификатор
- `display_name` — отображаемое имя
- `description` — описание
- `icon` — иконка (emoji)
- `tag_type` — тип: status, env, version, system, custom
- `css_class`, `border_color`, `text_color` — стилизация
- `is_system` — системный тег (нельзя удалить)
- `show_in_table` — показывать в таблице приложений

#### 2.3.2 Связи тегов
- Many-to-many связь с ApplicationInstance
- Many-to-many связь с ApplicationGroup
- Кэш тегов (`tags_cache`) для быстрой фильтрации
- Автообновление кэша через SQLAlchemy event listeners

#### 2.3.3 История тегов (TagHistory)
Аудит всех операций:
- `entity_type` — instance или group
- `entity_id` — ID сущности
- `tag_id` — ID тега
- `action` — assigned, removed, updated
- `changed_by` — кто изменил
- `changed_at` — когда
- `details` — дополнительные данные (JSON)

#### 2.3.4 Системные теги (автоназначение)
- `haproxy_mapped` — приложение связано с HAProxy
- `eureka_mapped` — приложение зарегистрировано в Eureka
- `pending_removal` — предупреждение об автоудалении
- `docker` — Docker-контейнер

#### 2.3.5 API тегов

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/tags` | GET/POST | Список/создание тегов |
| `/api/tags/<id>` | GET/PUT/DELETE | CRUD тега |
| `/api/applications/<id>/tags` | GET/POST | Теги приложения |
| `/api/tags/bulk-assign` | POST | Массовое назначение |
| `/api/tags/sync` | PUT | Синхронизация тегов |
| `/api/applications/filter/by-tags` | POST | Фильтрация по тегам (OR/AND) |

---

### 2.4 Интеграция с HAProxy

#### 2.4.1 Модели HAProxy

**HAProxyInstance:**
- Представляет HAProxy инстанс на сервере
- `name`, `server_id`, `is_active`
- `socket_path` — путь к unix socket или IP:port
- Статус синхронизации: `last_sync`, `last_sync_status`, `last_sync_error`

**HAProxyBackend:**
- Backend (пул серверов) в HAProxy
- `backend_name`, `enable_polling`
- Error tracking: `last_fetch_status`, `last_fetch_error`
- Soft delete: `removed_at`

**HAProxyServer:**
- Сервер в backend
- `server_name`, `status` (UP, DOWN, MAINT, DRAIN)
- `weight`, `check_status`, `addr`
- Метрики: `last_check_duration`, `downtime`
- Сессии: `scur`, `smax`

**HAProxyServerStatusHistory:**
- История изменений статуса
- `old_status`, `new_status`, `change_reason`

#### 2.4.2 Маппинг HAProxy ↔ Applications
- Автоматический маппинг по IP:port
- Ручной маппинг с защитой от автоперезаписи
- История маппинга (HAProxyMappingHistory)
- Fuzzy matching по имени сервера (threshold 60%)

#### 2.4.3 API HAProxy

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/haproxy/instances` | GET/POST | Список/создание инстансов |
| `/api/haproxy/instances/<id>` | GET/PUT/DELETE | CRUD инстанса |
| `/api/haproxy/instances/<id>/backends` | GET | Backends инстанса |
| `/api/haproxy/backends/<id>/servers` | GET | Серверы backend |
| `/api/haproxy/servers/<id>/map` | POST | Ручной маппинг |
| `/api/haproxy/servers/<id>/unmap` | POST | Удаление маппинга |
| `/api/haproxy/summary` | GET | Сводная статистика |
| `/api/haproxy/mapping/remap` | POST | Перемаппинг всех серверов |

---

### 2.5 Интеграция с Eureka

#### 2.5.1 Модели Eureka

**EurekaServer:**
- Eureka registry сервер
- `eureka_host`, `eureka_port`, `is_active`
- `consecutive_failures` — счётчик последовательных сбоев
- Soft delete поддержка

**EurekaApplication:**
- Приложение в Eureka
- `app_name` — имя сервиса (SERVICE-NAME)
- Статистика: `instances_count`, `instances_up`, `instances_down`, `instances_paused`

**EurekaInstance:**
- Экземпляр сервиса
- `instance_id` (формат: IP:service-name:port)
- `ip_address`, `port`, `service_name`
- `status` — UP, DOWN, PAUSED, STARTING, OUT_OF_SERVICE
- `instance_metadata` (JSON)
- URLs: `health_check_url`, `home_page_url`, `status_page_url`

**EurekaInstanceStatusHistory:**
- История изменений статуса

**EurekaInstanceAction:**
- Журнал действий: health_check, pause, shutdown, log_level_change

#### 2.5.2 Маппинг Eureka ↔ Applications
- Автоматический маппинг по IP:port и eureka_url
- Fuzzy matching по имени сервиса (threshold 60%)
- Ручной маппинг с защитой

#### 2.5.3 API Eureka

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/eureka/servers` | GET/POST | Список/создание серверов |
| `/api/eureka/servers/<id>` | GET/PUT/DELETE | CRUD сервера |
| `/api/eureka/applications` | GET | Приложения в Eureka |
| `/api/eureka/instances` | GET | Экземпляры (с пагинацией) |
| `/api/eureka/instances/<id>/health` | POST | Health check |
| `/api/eureka/instances/<id>/pause` | POST | Пауза экземпляра |
| `/api/eureka/instances/<id>/resume` | POST | Возобновление |
| `/api/eureka/instances/<id>/shutdown` | POST | Остановка |
| `/api/eureka/instances/<id>/loglevel` | POST | Изменение log level |
| `/api/eureka/sync` | POST | Синхронизация всех серверов |

---

### 2.6 Унифицированная система маппинга

#### 2.6.1 ApplicationMapping
Единая таблица для всех типов маппинга:
- `application_id` — FK на ApplicationInstance
- `entity_type` — haproxy_server или eureka_instance
- `entity_id` — ID внешней сущности
- `is_manual` — ручной или автоматический маппинг
- `mapped_by`, `mapped_at`, `notes`
- `is_active` — активность маппинга
- `mapping_metadata` (JSONB) — дополнительные данные

#### 2.6.2 ApplicationMappingHistory
Полный аудит:
- `action` — created, updated, deleted, deactivated, activated
- `old_values`, `new_values` (JSONB)
- `reason` — причина изменения

#### 2.6.3 API маппинга

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/mappings` | GET/POST | Список/создание маппингов |
| `/api/mappings/<id>` | GET/PUT/DELETE | CRUD маппинга |
| `/api/mappings/auto-map` | POST | Автоматический маппинг |
| `/api/mappings/cleanup-orphaned` | POST | Очистка orphan записей |
| `/api/mappings/stats` | GET | Статистика маппинга |

---

### 2.7 Система задач (Task Queue)

#### 2.7.1 Типы задач
| Тип | Описание |
|-----|----------|
| `start` | Запуск приложения |
| `stop` | Остановка приложения |
| `restart` | Перезапуск приложения |
| `update` | Обновление приложения |

#### 2.7.2 Состояния задач
| Состояние | Описание |
|-----------|----------|
| `pending` | Ожидает в очереди |
| `processing` | Выполняется |
| `completed` | Успешно завершена |
| `failed` | Ошибка выполнения |

#### 2.7.3 Модель Task
- `id` (UUID) — уникальный идентификатор
- `task_type` — тип задачи
- `status` — состояние
- `params` (JSON) — параметры (distr_url, playbook_path, app_ids)
- `server_id`, `instance_id` — связи
- `created_at`, `started_at`, `completed_at`
- `result` — результат (Ansible output)
- `error` — сообщение об ошибке
- `progress` (JSON) — прогресс выполнения
- `pid` — PID процесса (для отмены)
- `cancelled` — флаг отмены

#### 2.7.4 Batch-операции
- Группировка приложений по стратегии (by_group, by_server, etc.)
- Одна задача на группу приложений
- `params.app_ids` — массив ID приложений в batch

#### 2.7.5 Отмена задач
- Pending: установка флага cancelled
- Processing: отправка SIGTERM процессу Ansible

#### 2.7.6 Восстановление после сбоя
- При старте приложения: поиск pending/processing задач
- Маркировка как failed: "Прервано перезагрузкой сервера"

#### 2.7.7 API задач

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/tasks` | GET | Список задач (фильтры: status, app_id, server_id) |
| `/api/tasks/<id>` | GET | Детали задачи + parsed Ansible output |
| `/api/tasks/<id>/cancel` | POST | Отмена задачи |

---

### 2.8 Интеграция с Ansible

#### 2.8.1 SSH-режим (основной)
- Выполнение playbook через SSH на удалённом Ansible control host
- Конфигурация:
  - `SSH_HOST`, `SSH_USER`, `SSH_PORT`
  - `SSH_KEY_FILE`, `SSH_KNOWN_HOSTS_FILE`
  - `SSH_CONNECTION_TIMEOUT`, `SSH_COMMAND_TIMEOUT`

#### 2.8.2 Параметры playbook
**Динамические переменные:**
- `{server}` — имя сервера
- `{app}` — имя приложения
- `{distr_url}` — URL дистрибутива
- `{mode}` — режим обновления
- `{hostname}` — hostname сервера

**Кастомные параметры:**
- Формат: `{param_name=value}`
- Валидация имени и значения

#### 2.8.3 Orchestrator Playbooks
Специальные playbook для zero-downtime обновлений:
- Автообнаружение по паттерну (default: `*orchestrator*.yml`)
- Парсинг метаданных из YAML комментариев
- Хранение в БД (OrchestratorPlaybook)

**Поля OrchestratorPlaybook:**
- `file_path` (уникальный)
- `name`, `description`, `version`
- `required_params`, `optional_params` (JSON)
- `is_active`
- `raw_metadata` (JSON)

**Workflow orchestrator:**
1. Drain фаза: вывод серверов из HAProxy (`drain`)
2. Ожидание: `drain_wait_time` (конфигурируемое)
3. Update фаза: выполнение playbook обновления
4. Ожидание: `wait_after_update`
5. Ready фаза: возврат серверов в HAProxy (`ready`)
6. Повтор для следующего batch

**Формат composite names:**
- HAProxy mode: `server1::app_1::haproxy-web-01,server2::app_2::haproxy-web-02`
- Simple mode: `server1::app_1,server2::app_2`

#### 2.8.4 API Ansible

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/ansible/variables` | GET | Доступные переменные |
| `/api/ansible/validate-playbook` | POST | Валидация playbook |
| `/api/applications/<id>/test-playbook` | POST | Dry-run тест |
| `/api/orchestrators` | GET | Список orchestrator playbooks |
| `/api/orchestrators/scan` | POST | Сканирование playbooks |
| `/api/orchestrators/<id>/toggle` | PATCH | Включение/выключение |
| `/api/orchestrators/validate-mappings` | POST | Валидация маппинга для orchestrator |

---

### 2.9 Интеграция с Nexus (артефакты)

#### 2.9.1 Maven артефакты
- Парсинг maven-metadata.xml
- Построение download URL
- Сортировка версий (release > dev > snapshot)
- Поддержка custom расширений

#### 2.9.2 Docker образы
- Docker Registry API v2
- Получение списка тегов
- Получение манифестов
- Сортировка тегов (latest > releases > dev > snapshot)

#### 2.9.3 API артефактов

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/applications/<id>/artifacts` | GET | Артефакты приложения |
| `/api/artifacts/group/<id>` | GET | Артефакты группы |
| `/api/artifacts/latest` | POST | Последний артефакт |
| `/api/artifacts/test-connection` | POST | Тест подключения к Nexus |
| `/api/docker/images/<id>` | GET | Docker образы |
| `/api/docker/test-connection` | POST | Тест Docker registry |

---

### 2.10 Система отчётов

#### 2.10.1 Типы отчётов
- **Current Versions** — текущие версии приложений
- **Version History** — история изменений версий

#### 2.10.2 Функции
- Экспорт в CSV (с UTF-8 BOM для Excel)
- Экспорт в JSON
- Фильтрация по серверам, каталогам, типам, датам
- Статистика по источникам изменений
- Top приложений по изменениям

#### 2.10.3 Email рассылка
- Отправка отчётов на email
- Поддержка групп рассылки
- Резолвинг recipients (email или имя группы)

#### 2.10.4 API отчётов

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/api/reports/current-versions` | GET | Текущие версии |
| `/api/reports/current-versions/export` | GET | Экспорт (csv/json) |
| `/api/reports/version-history` | GET | История версий |
| `/api/reports/version-history/export` | GET | Экспорт истории |
| `/api/reports/filters` | GET | Опции фильтров |
| `/api/reports/send` | POST | Отправка по email |

---

### 2.11 Группы рассылки (MailingGroup)

- `name` — уникальное имя группы
- `description` — описание
- `emails` — список email (comma-separated)
- `is_active` — активность группы
- Валидация email адресов
- Case-insensitive поиск по имени

---

### 2.12 Журнал событий (Event)

- `event_type` — start, stop, restart, update, connect, disconnect
- `status` — success, failed, pending
- `description` — описание события
- `server_id`, `instance_id` — связи
- `timestamp` — время события

---

### 2.13 История версий (ApplicationVersionHistory)

Аудит изменений версий:
- `old_version`, `new_version`
- `old_distr_path`, `new_distr_path`
- `old_tag`, `new_tag` (Docker)
- `old_image`, `new_image` (Docker)
- `changed_by` — user, agent, system
- `change_source` — update_task, polling, manual
- `task_id` — связь с задачей

---

## 3. Нефункциональные требования

### 3.1 Фоновые процессы

#### 3.1.1 Monitoring Thread
- Опрос серверов через FAgent API
- Синхронизация HAProxy (если включено)
- Синхронизация Eureka (если включено)
- Очистка старых событий
- Очистка старых задач
- Автоудаление stale приложений

**Конфигурация:**
| Параметр | Default | Описание |
|----------|---------|----------|
| `POLLING_INTERVAL` | 60s | Интервал опроса серверов |
| `HAPROXY_POLLING_INTERVAL` | 60s | Интервал синхронизации HAProxy |
| `EUREKA_POLLING_INTERVAL` | 60s | Интервал синхронизации Eureka |

#### 3.1.2 Task Queue Thread
- Обработка задач из очереди
- Последовательное выполнение
- Поддержка отмены

### 3.2 Очистка данных

| Тип данных | Retention | Параметр |
|------------|-----------|----------|
| События | 30 дней | `CLEAN_EVENTS_OLDER_THAN` |
| Задачи | 365 дней | `CLEAN_TASKS_OLDER_THAN` |
| Offline apps (soft) | 7 дней | `APP_OFFLINE_REMOVAL_DAYS` |
| Deleted apps (hard) | +30 дней | `APP_HARD_DELETE_DAYS` |

**Защита от удаления:**
- Теги: `ver.lock`, `status.lock`, `disable`

### 3.3 Кэширование

| Сервис | TTL | Описание |
|--------|-----|----------|
| HAProxy | 30s | Кэш backends/servers |
| Eureka | 30s | Кэш applications/instances |
| HAProxy Mapper | - | Кэш результатов маппинга |
| Frontend Artifacts | 5 min | Кэш списка артефактов |

### 3.4 Retry-логика

| Сервис | Max Retries | Backoff |
|--------|-------------|---------|
| HAProxy | 3 | 2^retry_count |
| Eureka | 3 | Exponential |
| Agent | 1 | - |

### 3.5 Безопасность

**Production режим:**
- `SESSION_COOKIE_SECURE = True`
- `SESSION_COOKIE_HTTPONLY = True`
- `REMEMBER_COOKIE_SECURE = True`
- `REMEMBER_COOKIE_HTTPONLY = True`

**SSH:**
- Директория с правами 0o700
- Key-based аутентификация

**XSS Protection:**
- SecurityUtils.escapeHtml()
- textContent вместо innerHTML

---

## 4. Описание процессов и бизнес-логики

### 4.1 Процесс обновления приложения (Update Flow)

**Триггер:** Пользователь нажимает кнопку "Update" в UI или вызывает `/api/applications/<id>/update`

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          UPDATE APPLICATION FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  1. UI/API ─────► POST /api/applications/<id>/update                             │
│                   body: { distr_url, mode, playbook_path?, orchestrator? }        │
│                                                                                   │
│  2. Backend создаёт Task ─────► task_queue.add_task()                            │
│     - id: UUID                                                                    │
│     - task_type: 'update'                                                         │
│     - status: 'pending'                                                           │
│     - params: { distr_url, mode, playbook_path, app_ids }                        │
│     - instance_id, server_id                                                      │
│                                                                                   │
│  3. TaskQueue worker получает задачу из очереди                                  │
│     - Меняет status: 'pending' → 'processing'                                     │
│     - Устанавливает started_at                                                   │
│                                                                                   │
│  4. _process_update_task(task_id):                                               │
│     ├─► UpdateTaskContextProvider.load() - загрузка контекста из БД              │
│     ├─► Проверка: использовать orchestrator или обычный playbook?                │
│     │   └─► Если orchestrator: OrchestratorExecutor.prepare()                    │
│     │       - Формирует composite names: "server1::app_1,server2::app_2"         │
│     │       - Добавляет extra_params: drain_delay, haproxy_backend              │
│     │                                                                             │
│  5. SSHAnsibleService.update_application():                                      │
│     ├─► _prepare_update_context()                                                │
│     │   - parse_playbook_config() - парсинг параметров из пути                   │
│     │   - validate_parameters() - валидация {server}, {app}, {custom=value}      │
│     │   - test_connection() - проверка SSH соединения                            │
│     │   - _remote_file_exists() - проверка наличия playbook                      │
│     │   - build_context_vars() - формирование переменных контекста               │
│     │   - build_extra_vars() - формирование --extra-vars                         │
│     │   - build_ansible_command() - сборка команды ansible-playbook              │
│     │                                                                             │
│     ├─► _execute_ansible_command()                                               │
│     │   - SSH подключение к Ansible host                                         │
│     │   - Запуск: cd /etc/ansible && ansible-playbook <path> -e '...' -v        │
│     │   - Регистрация process в _active_processes для отмены                     │
│     │   - Парсинг stdout для отслеживания прогресса (TASK, HANDLER, RECAP)       │
│     │   - Обновление _task_progress для real-time UI                             │
│     │                                                                             │
│     └─► _finalize_update_result()                                                │
│         - Создание Event (success/failed)                                        │
│         - Возврат ansible_output                                                 │
│                                                                                   │
│  6. Post-processing (только для single task, не batch):                          │
│     └─► _update_app_version_after_success()                                      │
│         - Обновление app.version, app.distr_path                                 │
│         - Создание ApplicationVersionHistory записи                              │
│                                                                                   │
│  7. Завершение задачи:                                                           │
│     - status: 'processing' → 'completed' или 'failed'                            │
│     - completed_at = now()                                                        │
│     - result = ansible_output или error = error_message                          │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Orchestrator режим (zero-downtime update):**
```
1. Drain Phase: HAProxy drain → ожидание drain_delay
2. Update Phase: Выполнение update playbook на drained серверах
3. Ready Phase: HAProxy ready → возврат серверов в pool
4. Repeat: Следующий batch серверов
```

---

### 4.2 Процесс мониторинга серверов (Server Polling)

**Триггер:** MonitoringTasks запускается при старте приложения

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          SERVER POLLING FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  MonitoringTasks._run_monitoring() - основной цикл (каждую секунду)              │
│                                                                                   │
│  ┌─► Каждые POLLING_INTERVAL секунд (default: 60):                               │
│  │   │                                                                            │
│  │   └─► _poll_servers():                                                        │
│  │       │                                                                        │
│  │       ├─► Server.query.all() - получить все серверы                           │
│  │       │                                                                        │
│  │       └─► asyncio.gather() - параллельный опрос всех серверов:                │
│  │           │                                                                    │
│  │           └─► AgentService.update_server_applications(server_id):             │
│  │               │                                                                │
│  │               ├─► check_agent(server):                                        │
│  │               │   - GET http://{server.ip}:{server.port}/ping                 │
│  │               │   - Если OK: server.status = 'online'                         │
│  │               │   - Если fail: server.status = 'offline'                      │
│  │               │   - При изменении статуса: создать Event (connect/disconnect) │
│  │               │                                                                │
│  │               ├─► get_applications(server):                                   │
│  │               │   - GET http://{server.ip}:{server.port}/api/v1/apps          │
│  │               │   - Парсинг JSON: docker-app, site-app, service-app           │
│  │               │                                                                │
│  │               └─► Для каждого приложения от агента:                           │
│  │                   │                                                            │
│  │                   ├─► Поиск ApplicationInstance в БД                          │
│  │                   │   (server_id + instance_name + app_type)                  │
│  │                   │                                                            │
│  │                   ├─► Если не найден: CREATE новый экземпляр                  │
│  │                   │                                                            │
│  │                   ├─► Обновление полей:                                       │
│  │                   │   - container_id, container_name (docker)                 │
│  │                   │   - path, log_path, version, distr_path                   │
│  │                   │   - ip, port, pid, status, last_seen                      │
│  │                   │   - image, tag, eureka_* (docker)                         │
│  │                   │   - artifact_size_bytes, artifact_type                    │
│  │                   │                                                            │
│  │                   ├─► _record_version_change() - история версий               │
│  │                   │   - Если version изменилась: создать                      │
│  │                   │     ApplicationVersionHistory(changed_by='agent')         │
│  │                   │                                                            │
│  │                   ├─► ApplicationGroupService.resolve_application_group()     │
│  │                   │   - Автоопределение group_id и catalog_id                 │
│  │                   │                                                            │
│  │                   ├─► _sync_system_tags()                                     │
│  │                   │   - Автоназначение тегов: docker, haproxy_mapped, etc.    │
│  │                   │                                                            │
│  │                   └─► _restore_if_recovered()                                 │
│  │                       - Снять pending_removal если app вернулся online        │
│  │                       - Очистить deleted_at                                   │
│  │                                                                                │
│  │               ├─► Приложения отсутствующие в ответе агента:                   │
│  │               │   - status = 'offline'                                        │
│  │               │                                                                │
│  │               └─► db.session.commit()                                         │
│  │                                                                                │
│  └─────────────────────────────────────────────────────────────────────────────  │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.3 Жизненный цикл задачи (Task Lifecycle)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           TASK LIFECYCLE                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────┐      ┌────────────┐      ┌───────────┐      ┌─────────┐             │
│  │ CREATED │──────│  PENDING   │──────│PROCESSING │──────│COMPLETED│             │
│  └─────────┘      └────────────┘      └───────────┘      └─────────┘             │
│       │                 │                   │                                     │
│       │                 │                   │                                     │
│       │                 ▼                   ▼                                     │
│       │           ┌──────────┐        ┌──────────┐                               │
│       │           │CANCELLED │        │  FAILED  │                               │
│       │           │(user)    │        │          │                               │
│       │           └──────────┘        └──────────┘                               │
│                                                                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Создание задачи:                                                                │
│  ├─► task_queue.add_task(task_dict or Task object)                              │
│  ├─► Генерация UUID                                                              │
│  ├─► Сохранение в БД (Task model)                                               │
│  └─► Добавление task_id в queue.Queue для обработки                             │
│                                                                                   │
│  Обработка:                                                                       │
│  ├─► Worker берёт task_id из queue с timeout=1s                                  │
│  ├─► Загружает Task из БД                                                        │
│  ├─► Проверка: status == 'pending' && !cancelled                                │
│  ├─► status = 'processing', started_at = now()                                  │
│  ├─► Маршрутизация по task_type:                                                │
│  │   ├─► 'start'   → _process_start_task()                                      │
│  │   ├─► 'stop'    → _process_stop_task()                                       │
│  │   ├─► 'restart' → _process_restart_task()                                    │
│  │   └─► 'update'  → _process_update_task()                                     │
│  └─► Финализация: status = 'completed'/'failed', completed_at = now()           │
│                                                                                   │
│  Отмена pending задачи:                                                          │
│  ├─► cancel_pending_task(task_id)                                               │
│  ├─► task.cancelled = True                                                      │
│  ├─► task.status = 'failed'                                                     │
│  └─► task.error = 'Задача отменена пользователем'                               │
│                                                                                   │
│  Отмена processing задачи:                                                       │
│  ├─► SSHAnsibleService.cancel_task(task_id)                                     │
│  ├─► Получить process из _active_processes                                      │
│  └─► process.terminate() - отправка SIGTERM                                     │
│                                                                                   │
│  Восстановление после сбоя (при старте приложения):                             │
│  ├─► mark_interrupted_tasks()                                                   │
│  ├─► SELECT * FROM tasks WHERE status IN ('pending', 'processing')              │
│  └─► Для каждой: status = 'failed', error = 'Прервано перезагрузкой сервера'    │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.4 Процесс синхронизации HAProxy

**Триггер:** MonitoringTasks каждые HAPROXY_POLLING_INTERVAL секунд

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        HAPROXY SYNC FLOW                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  _sync_haproxy_instances():                                                      │
│  │                                                                                │
│  ├─► HAProxyInstance.query.filter_by(is_active=True).all()                       │
│  │                                                                                │
│  └─► Для каждого HAProxy instance (параллельно через asyncio.gather):           │
│      │                                                                            │
│      └─► HAProxyService.sync_haproxy_instance(instance):                         │
│          │                                                                        │
│          ├─► Запрос к FAgent: GET /api/v1/haproxy/{instance_name}/stats         │
│          │   - Получение backends и servers                                      │
│          │                                                                        │
│          ├─► Для каждого backend:                                                │
│          │   ├─► Найти или создать HAProxyBackend                               │
│          │   └─► Обновить: enable_polling, last_fetch_status                    │
│          │                                                                        │
│          ├─► Для каждого server в backend:                                       │
│          │   ├─► Найти или создать HAProxyServer                                │
│          │   ├─► Обновить: status, weight, check_status, addr                   │
│          │   ├─► Обновить метрики: scur, smax, last_check_duration              │
│          │   │                                                                    │
│          │   └─► Если status изменился:                                         │
│          │       └─► Создать HAProxyServerStatusHistory                         │
│          │                                                                        │
│          └─► instance.last_sync = now(), last_sync_status = 'success'           │
│                                                                                   │
│  После синхронизации - маппинг:                                                  │
│  │                                                                                │
│  └─► HAProxyMapper.remap_all_servers():                                          │
│      │                                                                            │
│      ├─► Для каждого HAProxyServer без маппинга:                                │
│      │   ├─► Поиск ApplicationInstance по IP:port                               │
│      │   ├─► Если не найден: fuzzy matching по имени (threshold 60%)            │
│      │   │                                                                        │
│      │   └─► Если найден:                                                        │
│      │       ├─► Создать ApplicationMapping(entity_type='haproxy_server')       │
│      │       ├─► Создать ApplicationMappingHistory(action='created')            │
│      │       └─► SystemTagsService.assign_tag(app_id, 'haproxy_mapped')         │
│      │                                                                            │
│      └─► Return (mapped_count, total_unmapped)                                  │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.5 Процесс синхронизации Eureka

**Триггер:** MonitoringTasks каждые EUREKA_POLLING_INTERVAL секунд

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        EUREKA SYNC FLOW                                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  _sync_eureka_servers():                                                         │
│  │                                                                                │
│  ├─► EurekaServer.query.filter_by(is_active=True, removed_at=None).all()        │
│  │                                                                                │
│  └─► Для каждого Eureka server (параллельно через asyncio.gather):              │
│      │                                                                            │
│      └─► EurekaService.sync_eureka_server(eureka_server):                        │
│          │                                                                        │
│          ├─► GET http://{eureka_host}:{eureka_port}/eureka/apps                  │
│          │   - Accept: application/json                                          │
│          │                                                                        │
│          ├─► Парсинг ответа Eureka registry                                      │
│          │                                                                        │
│          ├─► Для каждого application:                                            │
│          │   ├─► Найти или создать EurekaApplication                            │
│          │   └─► Обновить статистику: instances_count, instances_up/down        │
│          │                                                                        │
│          ├─► Для каждого instance:                                               │
│          │   ├─► Найти или создать EurekaInstance                               │
│          │   ├─► Обновить: instance_id, ip_address, port, status                │
│          │   ├─► Обновить: health_check_url, metadata                           │
│          │   │                                                                    │
│          │   └─► Если status изменился:                                         │
│          │       └─► Создать EurekaInstanceStatusHistory                        │
│          │                                                                        │
│          └─► eureka_server.last_sync = now()                                    │
│                                                                                   │
│  После синхронизации - маппинг:                                                  │
│  │                                                                                │
│  └─► EurekaMapper.map_instances_to_applications():                               │
│      │                                                                            │
│      ├─► Для каждого EurekaInstance без маппинга:                               │
│      │   ├─► Поиск ApplicationInstance по IP:port                               │
│      │   ├─► Поиск по eureka_url                                                │
│      │   ├─► Если не найден: fuzzy matching по service_name                     │
│      │   │                                                                        │
│      │   └─► Если найден:                                                        │
│      │       ├─► Создать ApplicationMapping(entity_type='eureka_instance')      │
│      │       ├─► Создать ApplicationMappingHistory(action='created')            │
│      │       └─► SystemTagsService.assign_tag(app_id, 'eureka_mapped')          │
│      │                                                                            │
│      └─► Return (mapped_count, total_unmapped)                                  │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.6 Система тегов - процесс работы

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          TAGS SYSTEM FLOW                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  Назначение тега вручную:                                                        │
│  ├─► POST /api/applications/<id>/tags {tag_name}                                │
│  ├─► ApplicationInstance.add_tag(tag_name, user):                               │
│  │   ├─► Tag.query.filter_by(name=tag_name).first()                             │
│  │   ├─► Если нет: CREATE Tag(name, display_name)                               │
│  │   ├─► instance.tags.append(tag)                                              │
│  │   ├─► instance._update_tags_cache() - обновить tags_cache                    │
│  │   └─► CREATE TagHistory(action='assigned', changed_by=user)                  │
│  └─► db.session.commit()                                                        │
│                                                                                   │
│  Автоназначение системных тегов:                                                │
│  ├─► SystemTagsService.on_app_synced(instance):                                 │
│  │   - При polling от агента                                                    │
│  │   ├─► Если app_type == 'docker': assign_tag('docker')                        │
│  │   ├─► Если eureka_registered: assign_tag('eureka')                           │
│  │   └─► И т.д. по AUTO_TAG_* конфигурации                                      │
│  │                                                                                │
│  ├─► При создании маппинга (HAProxy/Eureka):                                    │
│  │   └─► assign_tag('haproxy_mapped') или assign_tag('eureka_mapped')           │
│  │                                                                                │
│  └─► При приближении к удалению:                                                │
│      └─► assign_tag('pending_removal') за 3 дня до soft delete                  │
│                                                                                   │
│  Кэш тегов (tags_cache):                                                        │
│  ├─► Формат: "tag1,tag2,tag3" (sorted, comma-separated)                         │
│  ├─► Обновляется через SQLAlchemy event listeners:                              │
│  │   ├─► @event.listens_for(instance_tags_table, 'after_insert')               │
│  │   └─► @event.listens_for(instance_tags_table, 'after_delete')               │
│  └─► Используется для быстрой фильтрации без JOIN                              │
│                                                                                   │
│  Фильтрация по тегам:                                                            │
│  ├─► POST /api/applications/filter/by-tags                                      │
│  │   body: { tags: ["tag1", "tag2"], mode: "AND" | "OR" }                       │
│  ├─► OR: tags_cache LIKE '%tag1%' OR tags_cache LIKE '%tag2%'                   │
│  └─► AND: tags_cache LIKE '%tag1%' AND tags_cache LIKE '%tag2%'                 │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.7 Автоочистка данных (Cleanup Processes)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        CLEANUP PROCESSES                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  MonitoringTasks запускает cleanup операции каждые POLLING_INTERVAL секунд       │
│                                                                                   │
│  1. Очистка старых событий (_clean_old_events):                                  │
│     ├─► cutoff_date = now() - CLEAN_EVENTS_OLDER_THAN (default: 30 days)        │
│     └─► DELETE FROM events WHERE timestamp < cutoff_date                        │
│                                                                                   │
│  2. Очистка старых задач (_cleanup_old_tasks):                                   │
│     ├─► cutoff_date = now() - CLEAN_TASKS_OLDER_THAN (default: 365 days)        │
│     └─► DELETE FROM tasks WHERE status IN ('completed','failed')                │
│         AND completed_at < cutoff_date                                          │
│                                                                                   │
│  3. Очистка stale приложений (_cleanup_stale_applications):                      │
│                                                                                   │
│     ┌─────────────────────────────────────────────────────────────────────────┐ │
│     │  Timeline для offline приложений:                                        │ │
│     │                                                                          │ │
│     │  Day 0          Day 4              Day 7              Day 37             │ │
│     │    │              │                  │                  │                │ │
│     │    ▼              ▼                  ▼                  ▼                │ │
│     │  offline ──► pending_removal ──► soft delete ──► hard delete            │ │
│     │              тег назначен        deleted_at=now    физическое           │ │
│     │                                  Event created     удаление из БД       │ │
│     │                                                                          │ │
│     │  Защита от удаления: теги ver.lock, status.lock, disable                │ │
│     └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│     ├─► Warning phase (day 4):                                                  │
│     │   - SELECT apps WHERE status='offline' AND last_seen <= now-4d            │
│     │     AND deleted_at IS NULL AND last_seen > now-7d                         │
│     │   - Для каждого (без защитных тегов):                                     │
│     │     └─► SystemTagsService.assign_tag('pending_removal')                   │
│     │                                                                            │
│     ├─► Soft delete phase (day 7):                                              │
│     │   - SELECT apps WHERE status='offline' AND last_seen <= now-7d            │
│     │     AND deleted_at IS NULL                                                │
│     │   - Для каждого (без защитных тегов):                                     │
│     │     ├─► app.deleted_at = now()                                            │
│     │     ├─► remove_tag('pending_removal')                                     │
│     │     └─► CREATE Event(type='auto_removed')                                 │
│     │                                                                            │
│     └─► Hard delete phase (day 37):                                             │
│         - SELECT apps WHERE deleted_at <= now-30d                               │
│         - Для каждого: db.session.delete(app)                                   │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.8 Процесс отправки отчётов по email

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        REPORT EMAIL FLOW                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  POST /api/reports/send                                                          │
│  body: { report_type, recipients, filters?, period? }                            │
│                                                                                   │
│  1. Валидация входных данных:                                                    │
│     ├─► report_type: 'current_versions' или 'version_history'                   │
│     ├─► recipients: строка или массив (email или имена групп рассылки)          │
│     └─► Проверка: REPORT_EMAIL_ENABLED == true                                  │
│                                                                                   │
│  2. ReportMailerService.send_*_report():                                         │
│     │                                                                             │
│     ├─► resolve_recipients(recipients):                                          │
│     │   ├─► Для каждого recipient:                                              │
│     │   │   ├─► Если содержит '@': это email - добавить в список               │
│     │   │   └─► Иначе: поиск MailingGroup по имени (case-insensitive)           │
│     │   │       └─► Добавить все emails группы в список                         │
│     │   └─► Вернуть уникальный список email адресов                             │
│     │                                                                             │
│     ├─► Формирование данных отчёта:                                              │
│     │   ├─► current_versions:                                                   │
│     │   │   - SELECT * FROM application_instances WHERE deleted_at IS NULL      │
│     │   │   - Применение фильтров: server_ids, catalog_ids, app_type            │
│     │   │                                                                        │
│     │   └─► version_history:                                                    │
│     │       - SELECT * FROM application_version_history                         │
│     │       - JOIN application_instances                                        │
│     │       - Применение фильтров + period (date_from, date_to)                 │
│     │                                                                             │
│     ├─► Формирование email:                                                      │
│     │   ├─► Subject: [AC Report] Current Versions - 2024-12-10                  │
│     │   ├─► From: REPORT_EMAIL_FROM (ac-reports@localhost)                      │
│     │   ├─► To: resolved recipients                                             │
│     │   └─► Body: HTML таблица с данными                                        │
│     │                                                                             │
│     └─► Отправка через SMTP:                                                     │
│         ├─► Connect to SMTP_HOST:SMTP_PORT                                      │
│         ├─► Timeout: SMTP_TIMEOUT                                               │
│         ├─► Retry: SMTP_MAX_RETRIES при ошибке                                  │
│         └─► sendmail(from, to, message)                                         │
│                                                                                   │
│  3. Response:                                                                     │
│     └─► { success, recipients_count, resolved_recipients, records_count }       │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.9 Планировщики и фоновые процессы (Schedulers)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        BACKGROUND SCHEDULERS                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  При запуске приложения (app/__init__.py create_app()):                         │
│                                                                                   │
│  1. init_monitoring(app) - запуск MonitoringTasks:                              │
│     ├─► MonitoringTasks(app).start()                                            │
│     ├─► Создание daemon thread для _run_monitoring()                            │
│     ├─► Запуск task_queue.start_processing()                                    │
│     └─► Регистрация atexit handler для graceful shutdown                        │
│                                                                                   │
│  2. Структура MonitoringTasks:                                                   │
│     │                                                                             │
│     │  ┌──────────────────────────────────────────────────────────────────────┐│
│     │  │  Main Loop (каждую секунду проверяет stop_event):                    ││
│     │  │                                                                       ││
│     │  │  ┌─────────────────────┐  Interval: POLLING_INTERVAL (60s)           ││
│     │  │  │ _poll_servers()     │  - Опрос всех серверов через FAgent API     ││
│     │  │  └─────────────────────┘  - Обновление приложений                    ││
│     │  │                                                                       ││
│     │  │  ┌─────────────────────┐  Interval: HAPROXY_POLLING_INTERVAL (60s)   ││
│     │  │  │ _sync_haproxy()     │  - Если HAPROXY_ENABLED                     ││
│     │  │  └─────────────────────┘  - Синхронизация + маппинг                  ││
│     │  │                                                                       ││
│     │  │  ┌─────────────────────┐  Interval: EUREKA_POLLING_INTERVAL (60s)    ││
│     │  │  │ _sync_eureka()      │  - Если EUREKA_ENABLED                      ││
│     │  │  └─────────────────────┘  - Синхронизация + маппинг                  ││
│     │  │                                                                       ││
│     │  │  ┌─────────────────────┐  Interval: POLLING_INTERVAL                 ││
│     │  │  │ _clean_old_events() │  - Удаление событий старше 30 дней          ││
│     │  │  └─────────────────────┘                                              ││
│     │  │                                                                       ││
│     │  │  ┌─────────────────────┐  Interval: POLLING_INTERVAL                 ││
│     │  │  │ _cleanup_old_tasks()│  - Удаление задач старше 365 дней           ││
│     │  │  └─────────────────────┘                                              ││
│     │  │                                                                       ││
│     │  │  ┌─────────────────────┐  Interval: POLLING_INTERVAL                 ││
│     │  │  │ _cleanup_stale_apps │  - Soft/hard delete offline приложений      ││
│     │  │  └─────────────────────┘                                              ││
│     │  │                                                                       ││
│     │  └──────────────────────────────────────────────────────────────────────┘│
│     │                                                                             │
│     │  Изоляция ошибок:                                                          │
│     │  - Каждая операция в отдельном try/except                                 │
│     │  - last_run обновляется только при успехе                                 │
│     │  - При ошибке retry через 1 секунду                                       │
│     │                                                                             │
│  3. TaskQueue Worker (отдельный daemon thread):                                  │
│     ├─► task_queue.start_processing()                                           │
│     ├─► _process_tasks() loop:                                                  │
│     │   ├─► queue.get(timeout=1) - получение task_id                           │
│     │   ├─► Загрузка Task из БД                                                 │
│     │   ├─► Выполнение (start/stop/restart/update)                              │
│     │   └─► Обновление статуса в БД                                             │
│     └─► Graceful shutdown через stop_event                                      │
│                                                                                   │
│  4. Orchestrator Scanner (при старте):                                           │
│     ├─► scan_orchestrator_playbooks()                                           │
│     ├─► SSH to Ansible host                                                     │
│     ├─► ls /etc/ansible/*orchestrator*.yml                                      │
│     ├─► Парсинг метаданных из YAML комментариев                                 │
│     └─► Синхронизация с БД (OrchestratorPlaybook)                              │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.10 Процесс управления приложением (Start/Stop/Restart)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     APPLICATION CONTROL FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  POST /api/applications/<id>/manage                                              │
│  body: { action: "start" | "stop" | "restart" }                                  │
│                                                                                   │
│  1. Валидация:                                                                   │
│     ├─► Проверка существования приложения                                       │
│     └─► Проверка допустимости action                                            │
│                                                                                   │
│  2. Создание задачи:                                                             │
│     └─► task_queue.add_task({                                                   │
│             task_type: action,                                                   │
│             instance_id: app.id,                                                 │
│             server_id: app.server_id                                             │
│         })                                                                       │
│                                                                                   │
│  3. Обработка в TaskQueue:                                                       │
│     └─► _process_{action}_task(task_id):                                        │
│         │                                                                        │
│         ├─► Загрузка данных из БД (app, server)                                 │
│         │                                                                        │
│         └─► SSHAnsibleService.manage_application():                             │
│             │                                                                    │
│             ├─► Playbook: APP_CONTROL_PLAYBOOK (/etc/ansible/app_control.yml)   │
│             │                                                                    │
│             ├─► Extra vars:                                                      │
│             │   - server: server_name                                           │
│             │   - app_name: app.instance_name                                   │
│             │   - action: start | stop | restart                                │
│             │                                                                    │
│             ├─► test_connection() - проверка SSH                                │
│             │                                                                    │
│             ├─► _remote_file_exists() - проверка playbook                       │
│             │                                                                    │
│             ├─► CREATE Event(type=action, status='pending')                     │
│             │                                                                    │
│             ├─► _execute_ansible_command():                                     │
│             │   - cd /etc/ansible && ansible-playbook app_control.yml           │
│             │     -e 'server="fdmz01"' -e 'app_name="jurws_1"'                  │
│             │     -e 'action="restart"' -v                                      │
│             │                                                                    │
│             └─► CREATE Event(type=action, status='success'|'failed')            │
│                                                                                   │
│  4. Обновление статуса приложения:                                              │
│     - Статус обновится автоматически на следующем polling цикле                 │
│     - Или можно принудительно вызвать AgentService.poll_server()               │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Модель данных

### 5.1 ER-диаграмма (основные сущности)

```
┌──────────────┐     1:N     ┌───────────────────────┐
│    Server    │◄────────────│  ApplicationInstance  │
└──────────────┘             └───────────────────────┘
       │                              │    │
       │ 1:N                          │    │ N:1
       ▼                              │    ▼
┌──────────────┐                      │  ┌─────────────────────┐
│    Event     │                      │  │  ApplicationGroup   │
└──────────────┘                      │  └─────────────────────┘
       │                              │           │
       │ 1:N                          │ N:1       │ N:1
       │                              ▼           ▼
       │                        ┌─────────────────────┐
       │                        │ ApplicationCatalog  │
       │                        └─────────────────────┘
       │
       │ 1:N
       ▼
┌──────────────────┐     1:N     ┌─────────────────┐
│ HAProxyInstance  │◄────────────│  HAProxyBackend │
└──────────────────┘             └─────────────────┘
                                        │
                                        │ 1:N
                                        ▼
                                 ┌─────────────────┐
                                 │  HAProxyServer  │
                                 └─────────────────┘
                                        │
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │ ApplicationMapping  │◄───┐
                              └─────────────────────┘    │
                                        │                │
                                        │                │
                                        ▼                │
                              ┌─────────────────┐        │
                              │ EurekaInstance  │────────┘
                              └─────────────────┘
                                        │
                                        │ N:1
                                        ▼
                              ┌──────────────────┐
                              │ EurekaApplication│
                              └──────────────────┘
                                        │
                                        │ N:1
                                        ▼
                              ┌─────────────────┐
                              │  EurekaServer   │
                              └─────────────────┘

┌──────────────────────────────────────────────────┐
│                    Tags System                    │
├──────────────────────────────────────────────────┤
│  Tag ◄──M:N──► ApplicationInstance               │
│  Tag ◄──M:N──► ApplicationGroup                  │
│  TagHistory (аудит)                              │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│                    Task Queue                     │
├──────────────────────────────────────────────────┤
│  Task (pending → processing → completed/failed)  │
└──────────────────────────────────────────────────┘
```

### 4.2 Индексы

**Критичные индексы для производительности:**
- `idx_instance_status` — фильтрация по статусу
- `idx_instance_deleted` — фильтрация soft-deleted
- `idx_instance_server`, `idx_instance_group` — FK lookups
- `idx_tag_history_entity` — аудит по сущности
- `idx_haproxy_server_status` — статус HAProxy серверов
- `idx_eureka_instance_status` — статус Eureka instances

---

## 5. Веб-интерфейс

### 5.1 Страницы

| URL | Назначение |
|-----|------------|
| `/servers` | Список серверов |
| `/server/<id>` | Детали сервера |
| `/applications` | Управление приложениями |
| `/tasks` | Очередь задач |
| `/haproxy` | HAProxy dashboard |
| `/eureka` | Eureka dashboard |
| `/reports` | Отчёты |
| `/settings` | Настройки |

### 5.2 Frontend архитектура

**Модульная структура (IIFE pattern):**
```
static/js/
├── common/
│   ├── base.js (theme, modals)
│   ├── htmlx.js (HTMX library)
│   ├── modal-utils.js
│   ├── notifications.js
│   └── utils.js (date formatting)
├── applications/
│   ├── applications.js (main)
│   ├── core/ (config, api-service, state-manager, ...)
│   ├── handlers/ (checkbox, dropdown, table-actions)
│   ├── modals/ (update, tags, info)
│   └── ui/ (element-factory, pagination, tags-renderer)
├── haproxy/
│   ├── manager.js, api.js, ui.js, filters.js
├── eureka/
│   ├── manager.js, api.js, ui.js, filters.js
└── servers/
    └── servers.js, server-details.js
```

**Ключевые компоненты:**
- `StateManager` — централизованное управление состоянием
- `ApiService` — HTTP-коммуникация с backend
- `ElementFactory` — создание DOM элементов
- `ModalUtils` — универсальная модальная система

### 5.3 UI функционал

- Фильтрация по серверу, статусу, тегам (OR/AND)
- Поиск по имени
- Пагинация (10, 25, 50, 100)
- Группировка приложений
- Batch-операции (start, stop, restart, update)
- Массовое назначение тегов
- Auto-refresh (5s-60s intervals)
- Dark/Light theme

---

## 6. Конфигурация

### 6.1 Переменные окружения

**База данных:**
- `DATABASE_URL` или `POSTGRES_HOST/PORT/USER/PASSWORD/DB`

**Приложение:**
- `SECRET_KEY`, `FLASK_CONFIG`, `LOG_DIR`, `LOG_LEVEL`

**Ansible/SSH:**
- `USE_SSH_ANSIBLE`, `SSH_HOST/USER/PORT/KEY_FILE`
- `ANSIBLE_PATH`, `DEFAULT_UPDATE_PLAYBOOK`

**Интеграции:**
- `HAPROXY_ENABLED`, `HAPROXY_POLLING_INTERVAL`
- `EUREKA_ENABLED`, `EUREKA_POLLING_INTERVAL`

**Автотеги:**
- `AUTO_TAG_HAPROXY_ENABLED`, `AUTO_TAG_EUREKA_ENABLED`, `AUTO_TAG_DOCKER_ENABLED`

**Email:**
- `SMTP_HOST/PORT`, `REPORT_EMAIL_FROM`

---

## 7. Развёртывание

### 7.1 Docker-контейнеры

| Компонент | Контейнер | Внешний порт | Внутренний порт |
|-----------|-----------|--------------|-----------------|
| Приложение | fak-apps | 17071 | 5000 |
| База данных | pg-fak | - | 5432 |

### 7.2 Команды запуска

```bash
# Development
python main.py --config development --debug

# Production
python main.py --config production --host 0.0.0.0 --port 5000

# Инициализация БД
python init-db.py --config development
python init-db.py --config development --demo  # с demo-данными
```

### 7.3 Миграции

```bash
flask db migrate -m "Description"
flask db upgrade
flask db downgrade
```

---

## 8. Критерии приёмки

### 8.1 Функциональные критерии

- [ ] CRUD серверов с мониторингом статуса
- [ ] CRUD приложений с поддержкой 4 типов (docker, eureka, site, service)
- [ ] Иерархия настроек (instance → group → catalog → config)
- [ ] Система тегов с историей и автоназначением
- [ ] HAProxy интеграция (инстансы, backends, серверы, маппинг)
- [ ] Eureka интеграция (серверы, приложения, instances, actions)
- [ ] Унифицированный маппинг с историей
- [ ] Task queue с 4 типами задач и отменой
- [ ] Ansible интеграция (SSH mode, orchestrator playbooks)
- [ ] Nexus интеграция (Maven, Docker)
- [ ] Система отчётов с email-рассылкой
- [ ] Полнофункциональный веб-интерфейс

### 8.2 Нефункциональные критерии

- [ ] Фоновый мониторинг с конфигурируемыми интервалами
- [ ] Автоочистка данных по retention policy
- [ ] Кэширование HAProxy/Eureka данных
- [ ] Retry-логика для внешних сервисов
- [ ] Graceful shutdown background threads
- [ ] Soft delete с возможностью восстановления
- [ ] Полный аудит изменений (теги, маппинг, версии)
- [ ] XSS protection на frontend
- [ ] Secure cookies в production

---

## 9. Глоссарий

| Термин | Определение |
|--------|-------------|
| FAgent | Agent API на серверах для мониторинга приложений |
| Orchestrator | Playbook для zero-downtime обновлений через HAProxy |
| Drain | Вывод сервера из HAProxy пула (отключение новых подключений) |
| Soft Delete | Логическое удаление (установка deleted_at/removed_at) |
| Batch | Группа приложений, обрабатываемых одной задачей |
| Маппинг | Связь между приложением AC и внешней сущностью (HAProxy server, Eureka instance) |

---

**Конец документа**

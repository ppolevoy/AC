# Текущая архитектура HAProxy модуля

## Обзор

HAProxy модуль в AC (Application Control) обеспечивает мониторинг и управление HAProxy инстансами через интеграцию с FAgent API.

## Компоненты системы

### 1. Модели данных (app/models/haproxy.py)

#### HAProxyInstance
- Представляет инстанс HAProxy на сервере
- Поля: `id`, `name`, `server_id`, `is_active`, `socket_path`
- Отношения: принадлежит Server, имеет много Backends
- Статус синхронизации: `last_sync_at`, `last_sync_success`, `last_sync_error`

#### HAProxyBackend
- Представляет backend pool в HAProxy
- Поля: `id`, `haproxy_instance_id`, `backend_name`
- Soft delete: `removed_at` для пометки удаленных
- Отношения: принадлежит HAProxyInstance, имеет много HAProxyServers

#### HAProxyServer
- Отдельные серверы в backend
- Поля: статус, вес, метрики, маппинг приложений
- Поддержка manual и auto маппинга на Application

#### HAProxyAction
- Аудит команд HAProxy
- Логирует все действия: drain, ready, maint

#### HAProxyServerStatusHistory
- История изменения статусов серверов
- Для анализа и отчетности

### 2. Сервисный слой (app/services/haproxy_service.py)

#### Основные методы

**sync_haproxy_instance(instance)**
- Главный метод синхронизации
- Получает данные от FAgent
- Обновляет backends и servers в БД
- Реализует soft delete для отсутствующих

**get_backends(server, instance_name)**
- Получает список backends от FAgent
- Endpoint: `/api/haproxy/{instance_name}/backends`

**get_backend_servers(server, instance_name, backend_name)**
- Получает серверы конкретного backend
- Endpoint: `/api/haproxy/{instance_name}/backends/{backend_name}/servers`

**execute_server_command(command, server, instance_name, backend_name, server_name)**
- Выполнение команд: drain, ready, maint
- Логирование в HAProxyAction

#### Circuit Breaker Pattern
- Защита от сбоев при недоступности FAgent
- Автоматическое отключение после N ошибок
- Восстановление после успешной операции

#### Кэширование
- TTL: 30 секунд (настраивается)
- Кэш для backends и servers
- Автоматическая инвалидация

### 3. API Layer (app/api/haproxy_routes.py)

#### Endpoints

**GET /api/haproxy/summary**
- Глобальная статистика по всем инстансам
- Количество backends, servers, статусы

**GET /api/haproxy/instances**
- Список всех HAProxy инстансов
- Фильтрация по server_id

**GET /api/haproxy/instances/{id}/backends**
- Backends для конкретного инстанса
- Фильтрация removed_at IS NULL

**GET /api/haproxy/backends/{id}/servers**
- Серверы в backend
- Включает информацию о маппинге

**POST /api/haproxy/instances/{id}/sync**
- Ручной запуск синхронизации
- Асинхронное выполнение

**POST /api/haproxy/servers/{id}/command**
- Выполнение команд управления
- drain, ready, maint

**PUT /api/haproxy/servers/{id}/mapping**
- Ручной маппинг сервера на приложение

### 4. Фоновые задачи (app/tasks/monitoring.py)

#### _sync_haproxy_instances()
- Периодическая синхронизация всех активных инстансов
- Интервал: HAPROXY_POLLING_INTERVAL (60 сек)
- Автоматический маппинг после синхронизации
- Circuit breaker для каждого инстанса

#### Автоматический маппинг
- Сопоставление HAProxy серверов с приложениями
- По hostname и имени приложения
- Приоритет manual маппинга над auto

### 5. Frontend

#### 5.1. Страница HAProxy (/haproxy)

**Шаблон:** app/templates/haproxy.html
- Глобальная статистика
- Фильтры: инстанс, статус, поиск
- Аккордеон с backends
- Таблицы серверов в каждом backend
- Авто-обновление (5/15/30/60 сек)

**JavaScript модули:**
- **haproxy/api.js** - API клиент
- **haproxy/manager.js** - Управление данными
- **haproxy/ui.js** - Рендеринг UI
- **haproxy/filters.js** - Клиентская фильтрация

**Функции:**
- Просмотр состояния backends и servers
- Фильтрация по статусу (UP/DOWN/DRAIN/MAINT)
- Поиск по имени backend/server
- Показ маппинга на приложения
- Ручной маппинг/анмаппинг

#### 5.2. Модальное окно на странице сервера

**Расположение:** /server/{id} → кнопка "Настройка HAProxy"

**Файл:** app/static/js/servers/server-details.js

**Функции:**
- showHAProxyManagementModal() - создание модального окна
- loadHAProxyBackends() - загрузка backends при разворачивании
- Аккордеон для каждого HAProxy инстанса
- Показ статистики по backends

**Структура:**
```
Модальное окно
├── Заголовок (количество инстансов)
├── Инстанс 1 (аккордеон)
│   ├── Заголовок (имя, статус, backends count)
│   └── Содержимое (список backends)
│       ├── Backend 1 (имя, статистика)
│       ├── Backend 2 (имя, статистика)
│       └── ...
├── Инстанс 2 (аккордеон)
└── ...
```

### 6. Конфигурация (app/config.py)

```python
HAPROXY_ENABLED = 'true'                    # Включение модуля
HAPROXY_POLLING_INTERVAL = 60               # Интервал опроса (сек)
HAPROXY_CACHE_TTL = 30                     # TTL кэша (сек)
HAPROXY_REQUEST_TIMEOUT = 10                # Таймаут запросов
HAPROXY_MAX_RETRIES = 3                    # Попытки при ошибке
HAPROXY_CIRCUIT_BREAKER_THRESHOLD = 5       # Порог circuit breaker
HAPROXY_CIRCUIT_BREAKER_TIMEOUT = 300       # Таймаут circuit breaker
```

### 7. База данных

#### Таблицы
- `haproxy_instances` - HAProxy инстансы
- `haproxy_backends` - Backend pools
- `haproxy_servers` - Серверы в backends
- `haproxy_actions` - Аудит команд
- `haproxy_server_status_history` - История статусов

#### Индексы
- `haproxy_backends.removed_at` - для фильтрации удаленных
- `haproxy_servers.removed_at` - для фильтрации удаленных
- `haproxy_servers.backend_id` - для JOIN операций
- Композитные индексы для уникальности

### 8. Интеграция с FAgent

#### Endpoints FAgent
```
GET /api/haproxy/{instance}/backends
GET /api/haproxy/{instance}/backends/{backend}/servers
POST /api/haproxy/{instance}/backends/{backend}/servers/{server}/drain
POST /api/haproxy/{instance}/backends/{backend}/servers/{server}/ready
POST /api/haproxy/{instance}/backends/{backend}/servers/{server}/maint
```

#### Формат данных

**Backends response:**
```json
{
  "success": true,
  "backends": ["backend1", "backend2", "backend3"]
}
```

**Servers response:**
```json
{
  "success": true,
  "servers": [
    {
      "name": "server1",
      "address": "10.0.0.1:8080",
      "status": "UP",
      "weight": 100,
      "current_sessions": 5,
      "max_sessions": 1000
    }
  ]
}
```

### 9. Процесс синхронизации

```
1. Background Task запускается каждые 60 сек
   ↓
2. Для каждого активного HAProxy инстанса:
   ↓
3. Получить список backends от FAgent
   ↓
4. Для каждого backend:
   a. Создать/обновить в БД
   b. Получить список серверов
   c. Создать/обновить серверы в БД
   ↓
5. Пометить отсутствующие как removed_at
   ↓
6. Выполнить автоматический маппинг
   ↓
7. Обновить статус синхронизации
```

### 10. Soft Delete механизм

#### Как работает
- При синхронизации backend/server больше не появляется в ответе FAgent
- Устанавливается `removed_at = datetime.utcnow()`
- API endpoints фильтруют по `removed_at IS NULL`
- UI не показывает удаленные элементы

#### Преимущества
- Сохранение исторических данных
- Возможность восстановления
- Аудит изменений

### 11. Маппинг приложений

#### Автоматический маппинг
```python
# Логика в HAProxyService.auto_map_servers()
1. Извлечь hostname из server.address (до первой точки)
2. Найти Application где server.name = hostname
3. Если найдено и нет manual маппинга - создать auto маппинг
```

#### Ручной маппинг
- Через UI кнопка "Link" в таблице серверов
- API: PUT /api/haproxy/servers/{id}/mapping
- Приоритет над автоматическим

### 12. Статусы серверов HAProxy

- **UP** - Сервер работает нормально
- **DOWN** - Сервер недоступен
- **DRAIN** - Сервер не принимает новые соединения
- **MAINT** - Сервер в обслуживании
- **NOLB** - Сервер выведен из балансировки

### 13. Команды управления

#### drain
- Плавный вывод сервера из пула
- Существующие соединения продолжают работать
- Новые соединения не принимаются

#### ready
- Возврат сервера в пул
- Начинает принимать новые соединения

#### maint
- Немедленный вывод в обслуживание
- Разрывает существующие соединения

### 14. Orchestrator интеграция

При выполнении orchestrator playbooks:
1. Определяются затронутые HAProxy backends
2. Выполняется drain для серверов
3. Ждем drain_delay
4. Выполняется обновление
5. Ждем wait_after_update
6. Выполняется ready для серверов

### 15. Безопасность

- Все операции логируются в HAProxyAction
- Проверка прав на уровне API
- Валидация входных данных
- Защита от SQL инъекций через ORM
- Circuit breaker предотвращает DDoS на FAgent

## Проблемы текущей реализации

1. **Нет выборочного опроса backends** - опрашиваются все
2. **Нет визуализации трендов** - только текущее состояние
3. **Нет алертов** - требуется внешний мониторинг
4. **Нет bulk операций** - команды выполняются по одному серверу
5. **Нет истории метрик** - только последние значения

## Планируемые улучшения

1. ✅ Выборочный опрос backends (в разработке)
2. ⏳ Графики и тренды
3. ⏳ Система алертов
4. ⏳ Bulk операции
5. ⏳ Экспорт метрик в Prometheus
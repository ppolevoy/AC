## API Эндпоинты

### 1. Получить список бэкендов

**GET** `/api/v1/haproxy/backends`

**Пример запроса:**
```bash
curl http://localhost:11011/api/v1/haproxy/backends
```

**Пример ответа:**
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "instance": "default",
    "backends": ["myapp", "api", "static"],
    "count": 3
  }
}
```

### 2. Получить серверы в бэкенде

**GET** `/api/v1/haproxy/backends/{backend_name}/servers`

**Пример запроса:**
```bash
curl http://localhost:11011/api/v1/haproxy/backends/myapp/servers
```

**Пример ответа:**
```json
{
  "success": true,
  "status_code": 200,
  "data": {
    "instance": "default",
    "backend": "myapp",
    "servers": [
      {
        "name": "web01",
        "status": "UP",
        "weight": "1",
        "check_status": "L4OK",
        "check_duration": "0",
        "last_chg": "12345",
        "downtime": "0",
        "addr": "192.168.1.10:8080",
        "cookie": ""
      },
      {
        "name": "web02",
        "status": "MAINT",
        "weight": "1",
        "check_status": "L4OK",
        "check_duration": "0",
        "last_chg": "123",
        "downtime": "0",
        "addr": "192.168.1.11:8080",
        "cookie": ""
      }
    ],
    "count": 2
  }
}
```

### 3. Изменить состояние сервера

**POST** `/api/v1/haproxy/backends/{backend_name}/servers/{server_name}/action`

**Body:**
```json
{
  "action": "drain|ready|maint"
}
```

**Допустимые действия:**
- `ready` - Включить сервер (готов принимать трафик)
- `drain` - Graceful shutdown (не принимает новые подключения, завершает текущие)
- `maint` - Режим обслуживания (сервер недоступен)

**Пример запроса (drain):**
```bash
curl -X POST http://localhost:11011/api/v1/haproxy/backends/myapp/servers/web01/action \
  -H "Content-Type: application/json" \
  -d '{"action": "drain"}'
```

**Пример ответа:**
```json
{
  "success": true,
  "status_code": 200,
  "message": "Состояние сервера успешно изменено на 'drain'",
  "data": {
    "instance": "default",
    "backend": "myapp",
    "server": "web01",
    "action": "drain",
    "status": "completed"
  }
}
```

**Пример запроса (ready):**
```bash
curl -X POST http://localhost:11011/api/v1/haproxy/backends/myapp/servers/web01/action \
  -H "Content-Type: application/json" \
  -d '{"action": "ready"}'
```

## Работа с множественными инстансами

При настройке множественных инстансов HAProxy, можно указывать имя инстанса в URL:

### Получить бэкенды конкретного инстанса

**GET** `/api/v1/haproxy/{instance_name}/backends`

```bash
curl http://localhost:11011/api/v1/haproxy/prod/backends
```

### Получить серверы конкретного инстанса

**GET** `/api/v1/haproxy/{instance_name}/backends/{backend_name}/servers`

```bash
curl http://localhost:11011/api/v1/haproxy/prod/backends/myapp/servers
```

### Изменить состояние сервера в конкретном инстансе

**POST** `/api/v1/haproxy/{instance_name}/backends/{backend_name}/servers/{server_name}/action`

```bash
curl -X POST http://localhost:11011/api/v1/haproxy/prod/backends/myapp/servers/web01/action \
  -H "Content-Type: application/json" \
  -d '{"action": "drain"}'
```

## Формат ответов

### Успешный ответ

```json
{
  "success": true,
  "status_code": 200,
  "data": { ... },
  "message": "Optional success message"
}
```

### Ответ с ошибкой

```json
{
  "success": false,
  "status_code": 400|404|500|503,
  "error": "Error message"
}
```

## HTTP коды ответов

- `200` - Успешно
- `400` - Некорректный запрос (невалидные параметры)
- `404` - Ресурс не найден (контроллер, бэкенд, сервер)
- `500` - Внутренняя ошибка сервера
- `502` - Ошибка выполнения команды HAProxy
- `503` - HAProxy недоступен

## Поддерживаемые типы подключений

HAProxy Client Plugin поддерживает три типа подключений:

### 1. Unix Domain Socket
- **Формат**: `/var/run/haproxy.sock` (обычный путь к файлу)
- **Использование**: Локальное подключение на том же сервере
- **Производительность**: Максимальная (без сетевого стека)
- **Безопасность**: Контролируется правами доступа к файлу
- **HAProxy Config**: `stats socket /var/run/haproxy.sock mode 660 level admin`

### 2. TCP Socket IPv4
- **Формат**: `ipv4@192.168.1.15:7777`
- **Использование**: Удаленное подключение или привязка к конкретному IP
- **Производительность**: Хорошая (небольшой overhead TCP)
- **Безопасность**: Требует защиты firewall и/или SSL
- **HAProxy Config**: `stats socket ipv4@192.168.1.15:7777 level admin`

**Примечание**: Unix и TCP сокеты можно комбинировать в конфигурации множественных инстансов.

## Логирование

Все операции логируются с указанием:
- Типа операции (GET/POST)
- Типа подключения (unix/tcp4)
- Параметров запроса
- Результата выполнения
- Ошибок с полным stack trace

Уровни логирования:
- `INFO` - успешные операции
- `WARNING` - валидационные ошибки
- `ERROR` - ошибки подключения и выполнения

## Примеры использования

### Типичный workflow: Graceful restart сервера

1. **Перевести сервер в drain режим:**
```bash
curl -X POST http://localhost:11011/api/v1/haproxy/backends/myapp/servers/web01/action \
  -H "Content-Type: application/json" \
  -d '{"action": "drain"}'
```

2. **Дождаться завершения текущих соединений (мониторинг вне API)**

3. **Выполнить обслуживание сервера**

4. **Вернуть сервер в работу:**
```bash
curl -X POST http://localhost:11011/api/v1/haproxy/backends/myapp/servers/web01/action \
  -H "Content-Type: application/json" \
  -d '{"action": "ready"}'
```

### Проверка статуса всех серверов

```bash
# Получить список бэкендов
curl http://localhost:11011/api/v1/haproxy/backends | jq '.data.backends[]'

# Для каждого бэкенда получить серверы
for backend in $(curl -s http://localhost:11011/api/v1/haproxy/backends | jq -r '.data.backends[]'); do
  echo "Backend: $backend"
  curl -s http://localhost:11011/api/v1/haproxy/backends/$backend/servers | jq '.data.servers[] | {name, status}'
done
```
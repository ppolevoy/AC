# Система отправки отчётов Application Control

## 1. Архитектура

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ИСТОЧНИКИ ЗАПРОСОВ                              │
├─────────────────┬─────────────────┬─────────────────────────────────────────┤
│   Web UI        │   CLI скрипт    │   Внешние системы                       │
│   (reports.js)  │   (send-report  │   (curl, cron, ansible)                 │
│                 │   .sh)          │                                         │
└────────┬────────┴────────┬────────┴────────────────┬────────────────────────┘
         │                 │                         │
         ▼                 ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         REST API                                             │
│  POST /api/reports/send                                                      │
│  POST /api/reports/send/test                                                 │
│  GET  /api/reports/current-versions                                          │
│  GET  /api/reports/version-history                                           │
│  GET  /api/reports/*/export                                                  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ReportMailerService                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  resolve_recipients()  →  MailingGroup.resolve_recipients()          │    │
│  │  send_current_versions_report()                                      │    │
│  │  send_version_history_report()                                       │    │
│  │  _get_current_versions_data()   →  DB Query (ApplicationInstance)   │    │
│  │  _get_version_history_data()    →  DB Query (VersionHistory)        │    │
│  │  _generate_*_html()             →  HTML Template                    │    │
│  │  _generate_*_csv()              →  CSV Generation                   │    │
│  │  _send_email()                  →  smtplib.SMTP                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  MailingGroup   │    │  Application    │    │     SMTP        │
│  (группы        │    │  Instance/      │    │   Server        │
│   рассылки)     │    │  VersionHistory │    │  (localhost:25) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 2. Компоненты системы

### 2.1 API Endpoints (app/api/reports_routes.py)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/reports/send` | Отправка отчёта по email |
| POST | `/api/reports/send/test` | Тестовая отправка |
| GET | `/api/reports/current-versions` | Данные текущих версий |
| GET | `/api/reports/current-versions/export` | Экспорт в CSV/JSON |
| GET | `/api/reports/version-history` | История изменений |
| GET | `/api/reports/version-history/export` | Экспорт истории |
| GET | `/api/reports/filters` | Данные для фильтров |
| GET | `/api/reports/version-history/statistics` | Статистика изменений |

### 2.2 Сервис отправки (app/services/report_mailer.py)

```python
class ReportMailerService:
    # Основные методы
    send_current_versions_report(recipients, filters)  # Отчёт текущих версий
    send_version_history_report(recipients, filters, period)  # История изменений
    resolve_recipients(recipients)  # Резолв групп → email

    # Внутренние методы
    _get_current_versions_data(filters)  # Запрос к БД
    _get_version_history_data(filters, date_from)
    _generate_current_versions_html(data, filters)  # HTML письмо
    _generate_current_versions_csv(data)  # CSV вложение
    _send_email(to, subject, html_body, attachments)  # SMTP отправка
```

### 2.3 Группы рассылки (app/models/mailing_group.py)

```python
class MailingGroup:
    id, name, description
    emails         # Адреса через запятую
    is_active      # Активна ли группа

    # Методы
    get_emails_list()      # Список email из строки
    validate_emails()      # Валидация всех адресов
    find_by_name(name)     # Поиск группы по имени
    resolve_recipients()   # Резолв списка получателей
```

---

## 3. Потоки данных (Flow)

### 3.1 Отправка через Web UI

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Пользователь│     │  EmailModal  │     │    API       │
│  нажимает    │────▶│  (reports.js)│────▶│  /reports/   │
│  "Отправить" │     │  собирает    │     │  send        │
└──────────────┘     │  данные      │     └──────┬───────┘
                     └──────────────┘            │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    SMTP      │◀────│  _send_email │◀────│  Mailer      │
│   Server     │     │  (retry 3x)  │     │  Service     │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Формат запроса:**
```json
{
  "report_type": "current_versions",
  "recipients": "admins,user@example.com",
  "filters": {
    "server_ids": [1, 2],
    "catalog_ids": [5, 10]
  },
  "period": {
    "days": 7
  }
}
```

### 3.2 Резолв получателей

```
Входящий список: ["admins", "devops", "user@example.com"]
                        │
                        ▼
                ┌───────────────┐
                │ Для каждого   │
                │ элемента:     │
                └───────┬───────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   "admins"        "devops"     "user@example.com"
        │               │               │
        ▼               ▼               ▼
   Поиск группы    Поиск группы    Содержит @ и .
   в БД            в БД            → email
        │               │               │
        ▼               ▼               ▼
   [admin1@,       [dev@,          [user@
    admin2@]        ops@]           example.com]
        │               │               │
        └───────────────┼───────────────┘
                        │
                        ▼
           Уникальный набор email:
           [admin1@, admin2@, dev@, ops@, user@example.com]
```

### 3.3 Генерация отчёта

```
┌─────────────────────────────────────────────────────────────┐
│                    ReportMailerService                       │
├─────────────────────────────────────────────────────────────┤
│  1. Получение данных из БД                                   │
│     └─► ApplicationInstance.query.filter(...)                │
│                                                              │
│  2. Генерация HTML письма                                    │
│     └─► render_template_string(EMAIL_TEMPLATE, ...)          │
│         ┌─────────────────────────────────────────┐          │
│         │  <html>                                 │          │
│         │    <head><style>...</style></head>     │          │
│         │    <body>                              │          │
│         │      <h2>Текущие версии</h2>           │          │
│         │      <table>...</table>                │          │
│         │      <footer>Всего: N записей</footer> │          │
│         │    </body>                             │          │
│         │  </html>                               │          │
│         └─────────────────────────────────────────┘          │
│                                                              │
│  3. Генерация CSV вложения                                   │
│     └─► csv.DictWriter + BOM для Excel                       │
│                                                              │
│  4. Формирование MIME сообщения                              │
│     └─► MIMEMultipart('mixed')                               │
│         ├─► MIMEText(html, 'html')                           │
│         └─► MIMEBase('application', 'octet-stream')          │
│                                                              │
│  5. Отправка через SMTP (с retry)                            │
│     └─► smtplib.SMTP(host, port).sendmail()                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.4 Механизм Retry

```
Попытка 1 ──▶ Ошибка ──▶ sleep(2s) ──▶ Попытка 2 ──▶ Ошибка ──▶ sleep(4s) ──▶ Попытка 3
     │                                      │                                      │
     ▼                                      ▼                                      ▼
  Успех?                                 Успех?                                 Успех?
     │                                      │                                      │
     └──▶ return success                    └──▶ return success                    └──▶ return error
```

---

## 4. Конфигурация

### 4.1 Переменные окружения

```bash
# SMTP сервер
SMTP_HOST=localhost          # Хост SMTP сервера
SMTP_PORT=25                 # Порт (25 для relay без TLS)
SMTP_TIMEOUT=30              # Таймаут соединения (сек)
SMTP_MAX_RETRIES=3           # Макс. количество попыток

# Email настройки
REPORT_EMAIL_ENABLED=true    # Включить/выключить рассылку
REPORT_EMAIL_FROM=ac-reports@company.com  # Адрес отправителя
REPORT_EMAIL_SUBJECT_PREFIX=[AC Report]   # Префикс темы письма
```

### 4.2 В config.py

```python
# app/config.py
SMTP_HOST = os.environ.get('SMTP_HOST', 'localhost')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '25'))
SMTP_TIMEOUT = int(os.environ.get('SMTP_TIMEOUT', '30'))
SMTP_MAX_RETRIES = int(os.environ.get('SMTP_MAX_RETRIES', '3'))
REPORT_EMAIL_ENABLED = os.environ.get('REPORT_EMAIL_ENABLED', 'true').lower() == 'true'
REPORT_EMAIL_FROM = os.environ.get('REPORT_EMAIL_FROM', 'ac-reports@localhost')
REPORT_EMAIL_SUBJECT_PREFIX = os.environ.get('REPORT_EMAIL_SUBJECT_PREFIX', '[AC Report]')
```

---

## 5. Типы отчётов

### 5.1 Текущие версии (`current_versions`)

**Содержимое:**
- Имя приложения
- Тип (docker/site/service)
- Сервер
- Текущая версия
- Дата обновления

**Фильтры:**
- `server_ids` — ID серверов
- `catalog_ids` — ID приложений из каталога
- `app_type` — тип приложения

### 5.2 История изменений (`version_history`)

**Содержимое:**
- Имя приложения
- Сервер
- Старая версия → Новая версия
- Дата изменения
- Источник изменения

**Фильтры:**
- `server_ids`, `catalog_ids`
- `period.date_from`, `period.date_to` — период
- `period.days` — последние N дней

---

## 6. CLI скрипт для автоматизации

### 6.1 Использование (scripts/send-report.sh)

```bash
./send-report.sh -t <тип> -r <получатели> [-f <фильтры>] [-p <период>]

# Параметры:
#   -t, --type       Тип: current_versions или version_history
#   -r, --recipients Получатели (email или имена групп)
#   -f, --filters    JSON с фильтрами
#   -p, --period     JSON с периодом
#   -u, --url        URL API (по умолчанию: http://localhost:17071/api/reports/send)
```

### 6.2 Примеры

```bash
# Простая отправка группе admins
./send-report.sh -t current_versions -r admins

# Отправка нескольким получателям
./send-report.sh -t current_versions -r "admin@company.com,devops"

# С фильтрами по серверам
./send-report.sh -t current_versions -r admins -f '{"server_ids":[1,2,3]}'

# История за последние 7 дней
./send-report.sh -t version_history -r devops -p '{"days":7}'

# История за конкретный период
./send-report.sh -t version_history -r admins \
  -p '{"date_from":"2025-12-01","date_to":"2025-12-08"}'

# С кастомным URL API
./send-report.sh -t current_versions -r admins -u http://ac.company.local:17071/api/reports/send
```

---

## 7. Регулярные задания (cron)

### 7.1 Настройка crontab

```bash
# Редактирование crontab
crontab -e

# Или системный crontab
sudo nano /etc/crontab
```

### 7.2 Примеры расписаний

```bash
# ┌───────────── минута (0-59)
# │ ┌───────────── час (0-23)
# │ │ ┌───────────── день месяца (1-31)
# │ │ │ ┌───────────── месяц (1-12)
# │ │ │ │ ┌───────────── день недели (0-7, 0=7=воскресенье)
# │ │ │ │ │
# * * * * * команда

# ═══════════════════════════════════════════════════════════════
# ЕЖЕДНЕВНЫЕ ОТЧЁТЫ
# ═══════════════════════════════════════════════════════════════

# Каждый день в 8:00 — текущие версии всем админам
0 8 * * * /site/app/FAppControl/project/scripts/send-report.sh \
  -t current_versions \
  -r admins \
  >> /var/log/ac-reports.log 2>&1

# Каждый день в 9:00 — история за сутки команде devops
0 9 * * * /site/app/FAppControl/project/scripts/send-report.sh \
  -t version_history \
  -r devops \
  -p '{"days":1}' \
  >> /var/log/ac-reports.log 2>&1

# ═══════════════════════════════════════════════════════════════
# ЕЖЕНЕДЕЛЬНЫЕ ОТЧЁТЫ
# ═══════════════════════════════════════════════════════════════

# Каждый понедельник в 9:00 — сводка за неделю
0 9 * * 1 /site/app/FAppControl/project/scripts/send-report.sh \
  -t version_history \
  -r "admins,managers@company.com" \
  -p '{"days":7}' \
  >> /var/log/ac-reports.log 2>&1

# Каждую пятницу в 17:00 — текущее состояние для руководства
0 17 * * 5 /site/app/FAppControl/project/scripts/send-report.sh \
  -t current_versions \
  -r management \
  >> /var/log/ac-reports.log 2>&1

# ═══════════════════════════════════════════════════════════════
# ОТЧЁТЫ ПО КОНКРЕТНЫМ СЕРВЕРАМ
# ═══════════════════════════════════════════════════════════════

# Production серверы — ежедневно в 7:00
0 7 * * * /site/app/FAppControl/project/scripts/send-report.sh \
  -t current_versions \
  -r prod_admins \
  -f '{"server_ids":[1,2,3,4]}' \
  >> /var/log/ac-reports.log 2>&1

# Development серверы — по рабочим дням в 10:00
0 10 * * 1-5 /site/app/FAppControl/project/scripts/send-report.sh \
  -t current_versions \
  -r dev_team \
  -f '{"server_ids":[10,11,12]}' \
  >> /var/log/ac-reports.log 2>&1

# ═══════════════════════════════════════════════════════════════
# ЕЖЕМЕСЯЧНЫЕ ОТЧЁТЫ
# ═══════════════════════════════════════════════════════════════

# Первого числа месяца — сводка за месяц
0 8 1 * * /site/app/FAppControl/project/scripts/send-report.sh \
  -t version_history \
  -r "cto@company.com,admins" \
  -p '{"days":30}' \
  >> /var/log/ac-reports.log 2>&1
```

### 7.3 Логирование

```bash
# Просмотр логов
tail -f /var/log/ac-reports.log

# Пример вывода:
[2025-12-09 08:00:01] Отправка отчёта: current_versions
[2025-12-09 08:00:01] Получатели: admins
[OK] Отчёт успешно отправлен
  Отправлено получателям: 3
  Записей в отчёте: 47
```

### 7.4 Ротация логов

```bash
# /etc/logrotate.d/ac-reports
/var/log/ac-reports.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

---

## 8. Использование через curl

```bash
# Отправка отчёта текущих версий
curl -X POST http://localhost:17071/api/reports/send \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "current_versions",
    "recipients": "admins,user@example.com"
  }'

# С фильтрами
curl -X POST http://localhost:17071/api/reports/send \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "current_versions",
    "recipients": "devops",
    "filters": {
      "server_ids": [1, 2],
      "app_type": "docker"
    }
  }'

# История изменений за период
curl -X POST http://localhost:17071/api/reports/send \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "version_history",
    "recipients": "managers",
    "period": {
      "date_from": "2025-12-01",
      "date_to": "2025-12-08"
    }
  }'

# Тестовая отправка
curl -X POST http://localhost:17071/api/reports/send/test \
  -H "Content-Type: application/json" \
  -d '{"recipients": "test@example.com"}'
```

---

## 9. Формат писем

### HTML письмо
- Адаптивный дизайн
- Цветовая кодировка типов приложений
- Таблица с результатами
- Информация о фильтрах
- Подвал с количеством записей

### CSV вложение
- UTF-8 с BOM для Excel
- Разделитель `;`
- Имя файла: `current_versions_YYYYMMDD_HHMMSS.csv`

---

## 10. Обработка ошибок

| Код | Ситуация | Решение |
|-----|----------|---------|
| 400 | Не указан тип отчёта | Добавить `report_type` |
| 400 | Не указаны получатели | Добавить `recipients` |
| 400 | Неизвестный тип отчёта | Использовать `current_versions` или `version_history` |
| 500 | Ошибка SMTP | Проверить настройки SMTP, доступность сервера |
| 503 | Рассылка отключена | Установить `REPORT_EMAIL_ENABLED=true` |

---

## 11. Связанные файлы

| Файл | Описание |
|------|----------|
| `app/services/report_mailer.py` | Основной сервис отправки |
| `app/api/reports_routes.py` | API endpoints |
| `app/models/mailing_group.py` | Модель групп рассылки |
| `app/static/js/reports/reports.js` | Фронтенд модуль |
| `app/templates/reports.html` | HTML шаблон страницы |
| `scripts/send-report.sh` | CLI скрипт для cron |
| `app/config.py` | Конфигурация SMTP |

# Database Schema - Инструкция по использованию

## Описание

Файл `database_schema.sql` содержит полную схему базы данных для системы AC (Application Control). Скрипт включает:

- Полную очистку существующей базы данных (DROP tables)
- Создание всех таблиц с правильными типами данных
- Внешние ключи с каскадными действиями
- Индексы для оптимизации запросов
- Ограничения (UNIQUE, CHECK constraints)
- Комментарии к таблицам

## Использование

### 1. Создание новой базы данных с нуля

```bash
# Подключение к PostgreSQL и выполнение скрипта
psql -U <username> -d <database_name> -f database_schema.sql
```

Пример:
```bash
psql -U postgres -d fak_db -f database_schema.sql
```

### 2. Использование через Docker

Если база данных запущена в контейнере:

```bash
# Копирование скрипта в контейнер
docker cp database_schema.sql pg-fak:/tmp/database_schema.sql

# Выполнение скрипта
docker exec -i pg-fak psql -U <username> -d <database_name> -f /tmp/database_schema.sql
```

Пример для проекта:
```bash
docker cp database_schema.sql pg-fak:/tmp/database_schema.sql
docker exec -i pg-fak psql -U fak_user -d fak_db -f /tmp/database_schema.sql
```

### 3. Использование из приложения Python

```python
from app import db
from sqlalchemy import text

# Чтение SQL файла
with open('database_schema.sql', 'r') as f:
    sql_script = f.read()

# Выполнение скрипта
with db.engine.connect() as connection:
    connection.execute(text(sql_script))
    connection.commit()
```

## Предупреждения

⚠️ **ВНИМАНИЕ**: Скрипт содержит команды `DROP TABLE CASCADE`, которые **полностью удаляют все данные**!

### Перед выполнением скрипта:

1. **Создайте резервную копию базы данных**:
   ```bash
   pg_dump -U <username> -d <database_name> > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Убедитесь, что вы работаете с правильной базой данных**:
   ```bash
   psql -U <username> -d <database_name> -c "SELECT current_database();"
   ```

3. **Проверьте, что нет активных подключений**:
   ```bash
   psql -U <username> -d postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname = '<database_name>';"
   ```

## Структура базы данных

### Основные таблицы

#### Серверы и приложения
- `servers` - физические/виртуальные серверы с FAgent
- `application_catalog` - справочник типов приложений
- `application_groups` - группы приложений для управления
- `application_instances` - экземпляры приложений на серверах

#### Теги и события
- `tags` - система тегов для маркировки
- `application_instance_tags` - связь приложений с тегами (M2M)
- `application_group_tags` - связь групп с тегами (M2M)
- `tag_history` - история изменений тегов
- `events` - журнал событий и действий

#### HAProxy интеграция
- `haproxy_instances` - HAProxy инстансы
- `haproxy_backends` - backend пулы
- `haproxy_servers` - серверы в backend пулах
- `haproxy_server_status_history` - история статусов серверов
- `haproxy_mapping_history` - история маппинга на приложения

#### Eureka интеграция
- `eureka_servers` - Eureka registry серверы
- `eureka_applications` - приложения в Eureka
- `eureka_instances` - экземпляры сервисов в Eureka
- `eureka_instance_status_history` - история статусов экземпляров
- `eureka_instance_actions` - журнал действий над экземплярами

#### Маппинг и задачи
- `application_mappings` - унифицированная таблица маппингов
- `application_mapping_history` - история изменений маппингов
- `tasks` - очередь задач для выполнения операций

#### Дополнительные таблицы
- `orchestrator_playbooks` - метаданные orchestrator playbooks
- `mailing_groups` - группы email-рассылки
- `application_version_history` - история изменений версий приложений

### Ключевые связи

```
Server ──┬─→ ApplicationInstance ──→ ApplicationCatalog
         ├─→ Event                    ↓
         ├─→ HAProxyInstance         ApplicationGroup
         └─→ EurekaServer

HAProxyInstance ──→ HAProxyBackend ──→ HAProxyServer
EurekaServer ──→ EurekaApplication ──→ EurekaInstance

ApplicationMapping ──→ ApplicationInstance
                  └─→ (HAProxyServer | EurekaInstance)
```

## Проверка успешности выполнения

После выполнения скрипта проверьте:

```sql
-- Список всех таблиц
\dt

-- Количество таблиц (должно быть 25)
SELECT count(*) FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';

-- Проверка внешних ключей
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name;

-- Проверка индексов
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

## Миграция с Flask-Migrate

Если вы используете Flask-Migrate (Alembic), после создания схемы вручную:

```bash
# Инициализация Alembic (если ещё не сделано)
flask db init

# Создание первой миграции (будет пустой, т.к. схема уже создана)
flask db migrate -m "Initial schema"

# Пометка миграции как выполненной без реального применения
flask db stamp head
```

## Восстановление из резервной копии

Если что-то пошло не так:

```bash
# Полное восстановление
psql -U <username> -d <database_name> < backup_YYYYMMDD_HHMMSS.sql

# Восстановление только данных (без схемы)
pg_restore -U <username> -d <database_name> --data-only backup.dump
```

## Поддержка

При возникновении проблем:

1. Проверьте логи PostgreSQL
2. Убедитесь, что версия PostgreSQL поддерживает JSONB (≥ 9.4)
3. Проверьте права доступа пользователя БД
4. Проверьте наличие достаточного места на диске

## Версионирование

- **Дата создания**: 2025-12-17
- **Версия схемы**: 1.0
- **Совместимость**: PostgreSQL 9.4+
- **Проект**: AC (Application Control)

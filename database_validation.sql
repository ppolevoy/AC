-- ============================================================================
-- Database Validation Script
-- ============================================================================
-- Скрипт для проверки целостности и корректности схемы базы данных
-- ============================================================================

-- Вывод информации о базе данных
SELECT 'Проверка базы данных: ' || current_database() AS info;
SELECT 'Текущий пользователь: ' || current_user AS info;
SELECT 'Версия PostgreSQL: ' || version() AS info;

\echo '\n=== ПРОВЕРКА ТАБЛИЦ ==='

-- Количество таблиц (должно быть 25)
SELECT
    count(*) AS total_tables,
    CASE
        WHEN count(*) = 25 THEN '✓ OK'
        ELSE '✗ ОШИБКА: Ожидается 25 таблиц'
    END AS status
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';

-- Список всех таблиц
SELECT
    table_name,
    (SELECT count(*) FROM information_schema.columns c WHERE c.table_name = t.table_name) AS columns_count
FROM information_schema.tables t
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;

\echo '\n=== ПРОВЕРКА ВНЕШНИХ КЛЮЧЕЙ ==='

-- Количество внешних ключей
SELECT
    count(*) AS total_foreign_keys
FROM information_schema.table_constraints
WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public';

-- Список всех внешних ключей с ON DELETE действиями
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule AS on_delete_action
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
LEFT JOIN information_schema.referential_constraints AS rc
  ON tc.constraint_name = rc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name, kcu.column_name;

\echo '\n=== ПРОВЕРКА ИНДЕКСОВ ==='

-- Количество индексов
SELECT
    count(*) AS total_indexes
FROM pg_indexes
WHERE schemaname = 'public';

-- Таблицы без индексов (кроме primary key)
SELECT
    t.table_name,
    '⚠ WARNING: Таблица без дополнительных индексов' AS warning
FROM information_schema.tables t
WHERE t.table_schema = 'public'
  AND t.table_type = 'BASE TABLE'
  AND NOT EXISTS (
      SELECT 1 FROM pg_indexes i
      WHERE i.schemaname = 'public'
        AND i.tablename = t.table_name
        AND i.indexname NOT LIKE '%_pkey'
  )
ORDER BY t.table_name;

\echo '\n=== ПРОВЕРКА UNIQUE CONSTRAINTS ==='

-- Список всех UNIQUE ограничений
SELECT
    tc.table_name,
    tc.constraint_name,
    string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'UNIQUE' AND tc.table_schema = 'public'
GROUP BY tc.table_name, tc.constraint_name
ORDER BY tc.table_name;

\echo '\n=== ПРОВЕРКА PRIMARY KEYS ==='

-- Все primary keys
SELECT
    tc.table_name,
    kcu.column_name AS primary_key_column,
    col.data_type,
    col.column_default
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.columns AS col
  ON kcu.table_name = col.table_name AND kcu.column_name = col.column_name
WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name;

\echo '\n=== ПРОВЕРКА NULLABLE COLUMNS ==='

-- Обязательные поля (NOT NULL) в каждой таблице
SELECT
    table_name,
    count(*) FILTER (WHERE is_nullable = 'NO') AS not_null_columns,
    count(*) FILTER (WHERE is_nullable = 'YES') AS nullable_columns,
    count(*) AS total_columns
FROM information_schema.columns
WHERE table_schema = 'public'
GROUP BY table_name
ORDER BY table_name;

\echo '\n=== ПРОВЕРКА ТИПОВ ДАННЫХ ==='

-- Использование типов данных
SELECT
    data_type,
    count(*) AS usage_count
FROM information_schema.columns
WHERE table_schema = 'public'
GROUP BY data_type
ORDER BY usage_count DESC;

\echo '\n=== ПРОВЕРКА JSONB ПОЛЕЙ ==='

-- Все JSONB поля (для проверки совместимости)
SELECT
    table_name,
    column_name,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND data_type = 'jsonb'
ORDER BY table_name, column_name;

\echo '\n=== ПРОВЕРКА TIMESTAMP ПОЛЕЙ ==='

-- Все timestamp поля с DEFAULT значениями
SELECT
    table_name,
    column_name,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND data_type LIKE 'timestamp%'
  AND column_default IS NOT NULL
ORDER BY table_name, column_name;

\echo '\n=== ПРОВЕРКА SEQUENCES ==='

-- Все последовательности (для SERIAL полей)
SELECT
    sequence_name,
    data_type,
    numeric_precision,
    start_value,
    minimum_value,
    maximum_value,
    increment
FROM information_schema.sequences
WHERE sequence_schema = 'public'
ORDER BY sequence_name;

\echo '\n=== ПРОВЕРКА КОММЕНТАРИЕВ К ТАБЛИЦАМ ==='

-- Таблицы с комментариями
SELECT
    c.relname AS table_name,
    CASE
        WHEN d.description IS NOT NULL THEN '✓ Есть'
        ELSE '✗ Нет'
    END AS has_comment,
    d.description
FROM pg_class c
LEFT JOIN pg_description d ON c.oid = d.objoid AND d.objsubid = 0
WHERE c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
  AND c.relkind = 'r'
ORDER BY c.relname;

\echo '\n=== РАЗМЕРЫ ТАБЛИЦ ==='

-- Размеры таблиц (полезно для мониторинга)
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS indexes_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

\echo '\n=== ПРОВЕРКА СВЯЗЕЙ MANY-TO-MANY ==='

-- Проверка junction tables (должны быть 2)
SELECT
    table_name,
    (SELECT count(*) FROM information_schema.table_constraints tc
     WHERE tc.table_name = t.table_name AND tc.constraint_type = 'FOREIGN KEY') AS foreign_keys_count,
    CASE
        WHEN table_name IN ('application_instance_tags', 'application_group_tags') THEN '✓ OK'
        ELSE '⚠ Unexpected'
    END AS status
FROM information_schema.tables t
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
  AND table_name LIKE '%_tags'
ORDER BY table_name;

\echo '\n=== ИТОГОВАЯ СВОДКА ==='

-- Финальная статистика
SELECT
    (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE') AS total_tables,
    (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public') AS total_columns,
    (SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public') AS total_foreign_keys,
    (SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type = 'UNIQUE' AND table_schema = 'public') AS total_unique_constraints,
    (SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type = 'PRIMARY KEY' AND table_schema = 'public') AS total_primary_keys,
    (SELECT count(*) FROM pg_indexes WHERE schemaname = 'public') AS total_indexes,
    (SELECT count(*) FROM information_schema.sequences WHERE sequence_schema = 'public') AS total_sequences;

\echo '\n=== ПРОВЕРКА ЗАВЕРШЕНА ==='
\echo 'Для детального анализа используйте:'
\echo '  \\d+ <table_name>  - описание таблицы'
\echo '  \\di - список индексов'
\echo '  \\df - список функций'
\echo '  \\dv - список представлений'

#!/usr/bin/env python3
"""
Миграция: Добавление системных тегов

Добавляет:
- Поля is_system и show_in_table в таблицу tags
- Поле auto_assign_disabled в таблицу application_instance_tags
- Создает системные теги (haproxy, eureka, docker, disable, system, smf, sysctl, ver.lock, status.lock)

Примечание: Определения тегов берутся из app/services/system_tags/definitions.py
для централизации и избежания дублирования.
"""

import psycopg2
import os
import sys

# Добавляем путь к проекту для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_connection():
    """Получить подключение к БД"""
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', '192.168.8.46'),
        port=os.environ.get('POSTGRES_PORT', '5417'),
        database=os.environ.get('POSTGRES_DB', 'appcontrol'),
        user=os.environ.get('POSTGRES_USER', 'fakadm'),
        password=os.environ.get('POSTGRES_PASSWORD', 'fakadm')
    )


def get_system_tags_from_definitions():
    """Получить системные теги из централизованного определения"""
    try:
        from app.services.system_tags.definitions import SYSTEM_TAGS
        return [
            (
                tag_def.name,
                tag_def.display_name,
                tag_def.description,
                True,  # is_system
                tag_def.show_in_table,
                'system',  # tag_type
                tag_def.border_color,
                tag_def.text_color
            )
            for tag_def in SYSTEM_TAGS.values()
        ]
    except ImportError:
        # Fallback на хардкод если импорт не удался
        print("⚠ Не удалось импортировать definitions, используем fallback")
        return [
            ('haproxy', 'H', 'Приложение связано с HAProxy backend', True, True, 'system', '#28a745', '#28a745'),
            ('eureka', 'E', 'Приложение зарегистрировано в Eureka', True, True, 'system', '#007bff', '#007bff'),
            ('docker', 'docker', 'Docker-контейнер', True, True, 'system', '#2496ed', '#2496ed'),
            ('disable', 'disable', 'Отключенное приложение', True, False, 'system', '#6c757d', '#6c757d'),
            ('system', 'SYS', 'Системное приложение', True, False, 'system', '#6f42c1', '#6f42c1'),
            ('smf', 'smf', 'SMF сервис (Solaris)', True, False, 'system', '#fd7e14', '#fd7e14'),
            ('sysctl', 'sysctl', 'Systemctl сервис', True, False, 'system', '#20c997', '#20c997'),
            ('ver.lock', 'v.lock', 'Блокировка обновлений', True, False, 'system', '#dc3545', '#dc3545'),
            ('status.lock', 's.lock', 'Блокировка start/stop/restart', True, False, 'system', '#ffc107', '#856404'),
        ]


def upgrade():
    """Применить миграцию"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Добавление поля is_system в tags
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'tags'
                    AND column_name = 'is_system'
                ) THEN
                    ALTER TABLE tags ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
        """)
        print("✓ Добавлено поле is_system в tags")

        # Добавление поля show_in_table в tags
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'tags'
                    AND column_name = 'show_in_table'
                ) THEN
                    ALTER TABLE tags ADD COLUMN show_in_table BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
        """)
        print("✓ Добавлено поле show_in_table в tags")

        # Добавление поля auto_assign_disabled в application_instance_tags
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'application_instance_tags'
                    AND column_name = 'auto_assign_disabled'
                ) THEN
                    ALTER TABLE application_instance_tags ADD COLUMN auto_assign_disabled BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
        """)
        print("✓ Добавлено поле auto_assign_disabled в application_instance_tags")

        # Получение системных тегов из централизованного определения
        system_tags = get_system_tags_from_definitions()

        for tag in system_tags:
            cursor.execute("""
                INSERT INTO tags (name, display_name, description, is_system, show_in_table, tag_type, border_color, text_color, icon, css_class)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '●', 'tag-system')
                ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    is_system = EXCLUDED.is_system,
                    show_in_table = EXCLUDED.show_in_table,
                    tag_type = EXCLUDED.tag_type,
                    border_color = EXCLUDED.border_color,
                    text_color = EXCLUDED.text_color,
                    css_class = 'tag-system';
            """, tag)
        print(f"✓ Созданы/обновлены {len(system_tags)} системных тегов")

        conn.commit()
        print("\n✅ Миграция успешно применена!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Ошибка миграции: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def downgrade():
    """Откатить миграцию"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Удаление системных тегов
        cursor.execute("""
            DELETE FROM tags WHERE name IN (
                'haproxy', 'eureka', 'docker', 'disable', 'system',
                'smf', 'sysctl', 'ver.lock', 'status.lock'
            );
        """)
        print("✓ Удалены системные теги")

        # Удаление полей
        cursor.execute("""
            ALTER TABLE tags DROP COLUMN IF EXISTS is_system;
            ALTER TABLE tags DROP COLUMN IF EXISTS show_in_table;
            ALTER TABLE application_instance_tags DROP COLUMN IF EXISTS auto_assign_disabled;
        """)
        print("✓ Удалены поля is_system, show_in_table, auto_assign_disabled")

        conn.commit()
        print("✅ Откат миграции выполнен")

    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка отката: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'downgrade':
        downgrade()
    else:
        upgrade()

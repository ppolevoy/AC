#!/usr/bin/env python3
"""
Скрипт для добавления поддержки ручного маппинга HAProxy серверов.
Добавляет:
- Поля is_manual_mapping, mapped_by, mapped_at, mapping_notes в таблицу haproxy_servers
- Новую таблицу haproxy_mapping_history для истории изменений
"""

import os
import sys

# Добавить путь к app в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db

def add_manual_mapping_support():
    """Добавление поддержки ручного маппинга HAProxy серверов"""

    app = create_app()

    with app.app_context():
        print("Adding manual mapping support for HAProxy servers")
        print("=" * 60)

        try:
            # SQL для добавления колонок в haproxy_servers
            sql_add_columns = """
            -- Добавляем поля для ручного маппинга в haproxy_servers
            ALTER TABLE haproxy_servers
            ADD COLUMN IF NOT EXISTS is_manual_mapping BOOLEAN NOT NULL DEFAULT FALSE;

            ALTER TABLE haproxy_servers
            ADD COLUMN IF NOT EXISTS mapped_by VARCHAR(64);

            ALTER TABLE haproxy_servers
            ADD COLUMN IF NOT EXISTS mapped_at TIMESTAMP;

            ALTER TABLE haproxy_servers
            ADD COLUMN IF NOT EXISTS mapping_notes TEXT;
            """

            # SQL для создания таблицы истории маппинга
            sql_create_history_table = """
            -- Создаем таблицу истории изменений маппинга
            CREATE TABLE IF NOT EXISTS haproxy_mapping_history (
                id SERIAL PRIMARY KEY,
                haproxy_server_id INTEGER NOT NULL,
                old_application_id INTEGER,
                new_application_id INTEGER,
                changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                change_reason VARCHAR(32) NOT NULL,
                mapped_by VARCHAR(64),
                notes TEXT,

                CONSTRAINT fk_haproxy_mapping_history_server
                    FOREIGN KEY (haproxy_server_id)
                    REFERENCES haproxy_servers(id)
                    ON DELETE CASCADE,

                CONSTRAINT fk_haproxy_mapping_history_old_app
                    FOREIGN KEY (old_application_id)
                    REFERENCES applications(id)
                    ON DELETE SET NULL,

                CONSTRAINT fk_haproxy_mapping_history_new_app
                    FOREIGN KEY (new_application_id)
                    REFERENCES applications(id)
                    ON DELETE SET NULL
            );

            -- Создаем индексы для таблицы истории
            CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_server
                ON haproxy_mapping_history(haproxy_server_id);

            CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_changed_at
                ON haproxy_mapping_history(changed_at);

            CREATE INDEX IF NOT EXISTS idx_haproxy_mapping_history_reason
                ON haproxy_mapping_history(change_reason);
            """

            print("Adding columns to haproxy_servers table...")
            db.session.execute(db.text(sql_add_columns))

            print("Creating haproxy_mapping_history table...")
            db.session.execute(db.text(sql_create_history_table))

            db.session.commit()
            print("✓ SQL executed successfully!")

            # Проверяем результат
            inspector = db.inspect(db.engine)

            # Проверяем колонки в haproxy_servers
            columns = [col['name'] for col in inspector.get_columns('haproxy_servers')]
            required_columns = ['is_manual_mapping', 'mapped_by', 'mapped_at', 'mapping_notes']
            missing_columns = [col for col in required_columns if col not in columns]

            if not missing_columns:
                print("✓ All columns added to 'haproxy_servers' table")
                for col in required_columns:
                    print(f"  ✓ Column '{col}' verified")
            else:
                print(f"✗ Missing columns in 'haproxy_servers': {missing_columns}")
                return False

            # Проверяем таблицу haproxy_mapping_history
            tables = inspector.get_table_names()
            if 'haproxy_mapping_history' in tables:
                print("✓ Table 'haproxy_mapping_history' created and verified")

                # Проверяем колонки в новой таблице
                history_columns = [col['name'] for col in inspector.get_columns('haproxy_mapping_history')]
                expected_columns = [
                    'id', 'haproxy_server_id', 'old_application_id', 'new_application_id',
                    'changed_at', 'change_reason', 'mapped_by', 'notes'
                ]
                missing_history_columns = [col for col in expected_columns if col not in history_columns]

                if not missing_history_columns:
                    print("  ✓ All columns present in 'haproxy_mapping_history'")
                else:
                    print(f"  ✗ Missing columns in 'haproxy_mapping_history': {missing_history_columns}")
                    return False
            else:
                print("✗ Table 'haproxy_mapping_history' not found")
                return False

            print("=" * 60)
            print("✓ Migration completed successfully!")
            print("\nSummary:")
            print("  - Added 4 columns to haproxy_servers table")
            print("  - Created haproxy_mapping_history table")
            print("  - Created 3 indexes for history table")

            return True

        except Exception as e:
            db.session.rollback()
            print(f"✗ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    success = add_manual_mapping_support()
    sys.exit(0 if success else 1)

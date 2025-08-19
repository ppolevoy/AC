"""Добавление поля custom_vars в ApplicationInstance

Revision ID: add_custom_vars_to_instance
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_custom_vars_to_instance'
down_revision = None  # Укажите актуальную предыдущую миграцию
branch_labels = None
depends_on = None


def upgrade():
    """
    Добавляет поле custom_vars в таблицу application_instances
    """
    # Добавляем новую колонку custom_vars типа JSON
    op.add_column('application_instances', 
        sa.Column('custom_vars', 
                  postgresql.JSON(astext_type=sa.Text()), 
                  nullable=True,
                  server_default='{}')
    )
    
    # Создаем индекс для быстрого поиска по ключам JSON (для PostgreSQL)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_application_instances_custom_vars 
        ON application_instances USING gin (custom_vars);
    """)
    
    # Обновляем существующие записи, устанавливая пустой объект по умолчанию
    op.execute("""
        UPDATE application_instances 
        SET custom_vars = '{}' 
        WHERE custom_vars IS NULL;
    """)


def downgrade():
    """
    Удаляет поле custom_vars из таблицы application_instances
    """
    # Удаляем индекс
    op.execute("DROP INDEX IF EXISTS idx_application_instances_custom_vars;")
    
    # Удаляем колонку
    op.drop_column('application_instances', 'custom_vars')

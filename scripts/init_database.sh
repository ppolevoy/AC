#!/bin/bash
# =============================================================================
# AC (Application Control) - Скрипт инициализации БД
# =============================================================================
# Использование:
#   ./init_database.sh                    # Использует переменные окружения
#   ./init_database.sh -h host -p port -U user -d dbname
#   ./init_database.sh --url "postgresql://user:pass@host:port/db"
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="${SCRIPT_DIR}/init_database.sql"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция вывода справки
show_help() {
    echo "Использование: $0 [ОПЦИИ]"
    echo ""
    echo "Опции:"
    echo "  -h, --host HOST       Хост PostgreSQL (по умолчанию: \$POSTGRES_HOST или localhost)"
    echo "  -p, --port PORT       Порт PostgreSQL (по умолчанию: \$POSTGRES_PORT или 5432)"
    echo "  -U, --user USER       Пользователь PostgreSQL (по умолчанию: \$POSTGRES_USER или postgres)"
    echo "  -d, --dbname DB       Имя базы данных (по умолчанию: \$POSTGRES_DB или ac)"
    echo "  -W, --password PASS   Пароль (по умолчанию: \$POSTGRES_PASSWORD)"
    echo "  --url URL             Полный URL подключения (переопределяет другие опции)"
    echo "  --create-db           Создать базу данных, если не существует"
    echo "  --drop-db             Удалить и пересоздать базу данных"
    echo "  --help                Показать эту справку"
    echo ""
    echo "Переменные окружения:"
    echo "  DATABASE_URL          Полный URL подключения"
    echo "  POSTGRES_HOST         Хост PostgreSQL"
    echo "  POSTGRES_PORT         Порт PostgreSQL"
    echo "  POSTGRES_USER         Пользователь PostgreSQL"
    echo "  POSTGRES_PASSWORD     Пароль PostgreSQL"
    echo "  POSTGRES_DB           Имя базы данных"
    echo ""
    echo "Примеры:"
    echo "  $0                                    # Использовать переменные окружения"
    echo "  $0 -h localhost -U postgres -d ac    # Указать параметры явно"
    echo "  $0 --url 'postgresql://user:pass@host:5432/ac'"
    echo "  $0 --create-db                       # Создать БД если не существует"
}

# Значения по умолчанию из окружения
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:-}"
DB_NAME="${POSTGRES_DB:-ac}"
DB_URL="${DATABASE_URL:-}"
CREATE_DB=false
DROP_DB=false

# Парсинг аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            DB_HOST="$2"
            shift 2
            ;;
        -p|--port)
            DB_PORT="$2"
            shift 2
            ;;
        -U|--user)
            DB_USER="$2"
            shift 2
            ;;
        -d|--dbname)
            DB_NAME="$2"
            shift 2
            ;;
        -W|--password)
            DB_PASSWORD="$2"
            shift 2
            ;;
        --url)
            DB_URL="$2"
            shift 2
            ;;
        --create-db)
            CREATE_DB=true
            shift
            ;;
        --drop-db)
            DROP_DB=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Неизвестная опция: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Проверка наличия SQL файла
if [[ ! -f "$SQL_FILE" ]]; then
    echo -e "${RED}Ошибка: SQL файл не найден: $SQL_FILE${NC}"
    exit 1
fi

# Формирование параметров подключения
if [[ -n "$DB_URL" ]]; then
    echo -e "${YELLOW}Используется DATABASE_URL${NC}"
    PSQL_CONN="$DB_URL"
else
    if [[ -n "$DB_PASSWORD" ]]; then
        export PGPASSWORD="$DB_PASSWORD"
    fi
    PSQL_CONN="-h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME"
    PSQL_CONN_ADMIN="-h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres"
fi

echo -e "${GREEN}=== AC Database Initialization ===${NC}"
echo "Host: $DB_HOST"
echo "Port: $DB_PORT"
echo "User: $DB_USER"
echo "Database: $DB_NAME"
echo ""

# Создание/пересоздание БД
if [[ "$DROP_DB" == true ]]; then
    echo -e "${YELLOW}Удаление базы данных $DB_NAME...${NC}"
    psql $PSQL_CONN_ADMIN -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || true
    echo -e "${YELLOW}Создание базы данных $DB_NAME...${NC}"
    psql $PSQL_CONN_ADMIN -c "CREATE DATABASE $DB_NAME;"
elif [[ "$CREATE_DB" == true ]]; then
    echo -e "${YELLOW}Проверка/создание базы данных $DB_NAME...${NC}"
    psql $PSQL_CONN_ADMIN -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
        psql $PSQL_CONN_ADMIN -c "CREATE DATABASE $DB_NAME;"
fi

# Выполнение SQL скрипта
echo -e "${YELLOW}Выполнение SQL скрипта...${NC}"
echo ""

if [[ -n "$DB_URL" ]]; then
    psql "$DB_URL" -f "$SQL_FILE"
else
    psql $PSQL_CONN -f "$SQL_FILE"
fi

echo ""
echo -e "${GREEN}=== Инициализация завершена успешно ===${NC}"

# Вывод статистики
echo ""
echo "Созданные таблицы:"
if [[ -n "$DB_URL" ]]; then
    psql "$DB_URL" -c "\dt" 2>/dev/null | grep -E "^\s+public" | wc -l | xargs echo "  Всего таблиц:"
else
    psql $PSQL_CONN -c "\dt" 2>/dev/null | grep -E "^\s+public" | wc -l | xargs echo "  Всего таблиц:"
fi

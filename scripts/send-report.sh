#!/bin/bash
# send-report.sh - Скрипт отправки отчётов через API
# Предназначен для использования в cron или ручного запуска
#
# Использование:
#   ./send-report.sh -t <report_type> -r <recipients> [-f <filters>] [-p <period>]
#
# Параметры:
#   -t, --type       Тип отчёта: current_versions или version_history
#   -r, --recipients Получатели через запятую (email или имена групп)
#   -f, --filters    JSON с фильтрами (опционально)
#   -p, --period     JSON с периодом для version_history (опционально)
#   -u, --url        URL API (по умолчанию: http://localhost:17071/api/reports/send)
#   -h, --help       Показать справку
#
# Примеры:
#   # Отправить отчёт текущих версий группе admins
#   ./send-report.sh -t current_versions -r admins
#
#   # Отправить отчёт истории на несколько адресов
#   ./send-report.sh -t version_history -r "user@example.com,devops_team"
#
#   # С фильтрами по серверам
#   ./send-report.sh -t current_versions -r admins -f '{"server_ids":[1,2,3]}'
#
#   # История за последние 7 дней
#   ./send-report.sh -t version_history -r admins -p '{"days":7}'
#
# Для cron (ежедневно в 8:00):
#   0 8 * * * /path/to/send-report.sh -t current_versions -r admins >> /var/log/ac-reports.log 2>&1
#

set -e

# Значения по умолчанию
API_URL="${AC_REPORT_API_URL:-http://localhost:17071/api/reports/send}"
REPORT_TYPE=""
RECIPIENTS=""
FILTERS="{}"
PERIOD="{}"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция вывода справки
show_help() {
    head -40 "$0" | tail -38 | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Парсинг аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            REPORT_TYPE="$2"
            shift 2
            ;;
        -r|--recipients)
            RECIPIENTS="$2"
            shift 2
            ;;
        -f|--filters)
            FILTERS="$2"
            shift 2
            ;;
        -p|--period)
            PERIOD="$2"
            shift 2
            ;;
        -u|--url)
            API_URL="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            ;;
        *)
            log_error "Неизвестный параметр: $1"
            echo "Используйте -h для справки"
            exit 1
            ;;
    esac
done

# Проверка обязательных параметров
if [ -z "$REPORT_TYPE" ]; then
    log_error "Не указан тип отчёта (-t)"
    echo "Используйте -h для справки"
    exit 1
fi

if [ -z "$RECIPIENTS" ]; then
    log_error "Не указаны получатели (-r)"
    echo "Используйте -h для справки"
    exit 1
fi

# Валидация типа отчёта
if [ "$REPORT_TYPE" != "current_versions" ] && [ "$REPORT_TYPE" != "version_history" ]; then
    log_error "Неверный тип отчёта: $REPORT_TYPE"
    echo "Допустимые значения: current_versions, version_history"
    exit 1
fi

# Проверка доступности curl
if ! command -v curl &> /dev/null; then
    log_error "curl не установлен"
    exit 1
fi

# Проверка валидности JSON фильтров
if [ "$FILTERS" != "{}" ]; then
    if ! echo "$FILTERS" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        log_error "Невалидный JSON в параметре filters"
        exit 1
    fi
fi

# Проверка валидности JSON периода
if [ "$PERIOD" != "{}" ]; then
    if ! echo "$PERIOD" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        log_error "Невалидный JSON в параметре period"
        exit 1
    fi
fi

log "Отправка отчёта: $REPORT_TYPE"
log "Получатели: $RECIPIENTS"

# Формирование JSON тела запроса
JSON_BODY=$(cat <<EOF
{
    "report_type": "$REPORT_TYPE",
    "recipients": "$RECIPIENTS",
    "filters": $FILTERS,
    "period": $PERIOD
}
EOF
)

# Отправка запроса
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "$JSON_BODY" \
    --connect-timeout 10 \
    --max-time 120)

# Разделение ответа и HTTP кода
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$RESPONSE" | sed '$d')

# Проверка результата
if [ "$HTTP_CODE" -eq 200 ]; then
    log_success "Отчёт успешно отправлен"

    # Извлечение деталей из ответа
    if command -v python3 &> /dev/null; then
        RECIPIENTS_COUNT=$(echo "$RESPONSE_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('details',{}).get('recipients_count',0))" 2>/dev/null || echo "?")
        RECORDS_COUNT=$(echo "$RESPONSE_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('details',{}).get('records_count',0))" 2>/dev/null || echo "?")
        log "  Отправлено получателям: $RECIPIENTS_COUNT"
        log "  Записей в отчёте: $RECORDS_COUNT"
    fi
    exit 0
else
    log_error "Ошибка отправки (HTTP $HTTP_CODE)"

    # Попытка извлечь сообщение об ошибке
    if command -v python3 &> /dev/null; then
        ERROR_MSG=$(echo "$RESPONSE_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error','Неизвестная ошибка'))" 2>/dev/null || echo "$RESPONSE_BODY")
        log_error "$ERROR_MSG"
    else
        log_error "$RESPONSE_BODY"
    fi
    exit 1
fi

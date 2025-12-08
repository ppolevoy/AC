/**
 * Faktura Apps - Утилиты и общие функции
 */

/**
 * Форматирование даты
 * @param {Date} date - Дата для форматирования
 * @returns {string} Отформатированная дата
 */
function formatDate(date) {
    if (!(date instanceof Date) || isNaN(date)) {
        return '-';
    }

    return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

/**
 * Парсинг ISO 8601 строки (UTC) и форматирование в локальное время
 * @param {string} isoString - ISO строка даты (например '2024-12-08T10:30:00Z')
 * @param {object} options - Опции форматирования
 * @param {boolean} options.dateOnly - Только дата без времени
 * @param {boolean} options.timeOnly - Только время без даты
 * @returns {string} Отформатированная дата в локальном времени
 */
function formatDateTimeLocal(isoString, options = {}) {
    if (!isoString) {
        return '-';
    }

    const date = new Date(isoString);
    if (isNaN(date.getTime())) {
        return '-';
    }

    if (options.dateOnly) {
        return date.toLocaleDateString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    }

    if (options.timeOnly) {
        return date.toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    return date.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

/**
 * Форматирование относительного времени ("5 минут назад")
 * @param {string} isoString - ISO строка даты
 * @returns {string} Относительное время
 */
function formatRelativeTime(isoString) {
    if (!isoString) {
        return '-';
    }

    const date = new Date(isoString);
    if (isNaN(date.getTime())) {
        return '-';
    }

    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) {
        return 'только что';
    } else if (diffMin < 60) {
        return `${diffMin} мин. назад`;
    } else if (diffHour < 24) {
        return `${diffHour} ч. назад`;
    } else if (diffDay < 7) {
        return `${diffDay} дн. назад`;
    } else {
        return formatDateTimeLocal(isoString, { dateOnly: true });
    }
}

/**
 * Форматирование типа задачи
 * @param {string} type - Тип задачи
 * @returns {string} Отформатированный тип задачи
 */
function formatTaskType(type) {
    const types = {
        'start': 'Запуск',
        'stop': 'Остановка',
        'restart': 'Перезапуск',
        'update': 'Обновление'
    };
    
    return types[type] || type;
}

/**
 * Получение названия действия (для модальных окон подтверждения)
 * @param {string} action - Код действия
 * @returns {string} Название действия
 */
function getActionName(action) {
    const actionNames = {
        'start': 'запустить',
        'stop': 'остановить',
        'restart': 'перезапустить'
    };
    
    return actionNames[action] || action;
}

// Экспортируем функции, чтобы они были доступны глобально
window.formatDate = formatDate;
window.formatDateTimeLocal = formatDateTimeLocal;
window.formatRelativeTime = formatRelativeTime;
window.formatTaskType = formatTaskType;
window.getActionName = getActionName;

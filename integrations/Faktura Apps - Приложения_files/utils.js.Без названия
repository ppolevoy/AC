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
window.formatTaskType = formatTaskType;
window.getActionName = getActionName;

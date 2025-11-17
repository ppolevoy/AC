/**
 * Faktura Apps - Модуль уведомлений
 * Содержит функции для отображения уведомлений и сообщений об ошибках
 */

// Инициализация контейнера для уведомлений
let notificationContainer = null;

function getNotificationContainer() {
    if (!notificationContainer) {
        notificationContainer = document.createElement('div');
        notificationContainer.className = 'notification-container';
        document.body.appendChild(notificationContainer);
    }
    return notificationContainer;
}

/**
 * Создает и отображает уведомление
 * @param {string} message - Текст уведомления
 * @param {string} type - Тип уведомления (success, error, или info)
 * @param {number} duration - Продолжительность отображения в миллисекундах
 */
function createNotification(message, type, duration) {
    // Удаляем предыдущие уведомления
    const existingNotifications = document.querySelectorAll('.notification-toast');
    existingNotifications.forEach(n => n.remove());

    // Создаем новое уведомление
    const notification = document.createElement('div');
    notification.className = `notification-toast notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            ${message}
        </div>
        <button class="notification-close">×</button>
    `;

    // Добавляем в body
    document.body.appendChild(notification);

    // Показываем с анимацией
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);

    // Автоматически скрываем через заданное время
    const hideTimeout = setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, duration);

    // Обработчик закрытия
    notification.querySelector('.notification-close').addEventListener('click', () => {
        clearTimeout(hideTimeout);
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    });
}

/**
 * Отображает уведомление
 * @param {string} message - Текст уведомления
 * @param {string} type - Тип уведомления (success, error, info, warning) (по умолчанию 'success')
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 5000)
 */
function showNotification(message, type = 'success', duration = 5000) {
    createNotification(message, type, duration);
}

/**
 * Отображает сообщение об ошибке
 * @param {string} message - Текст сообщения об ошибке
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 5000)
 */
function showError(message, duration = 5000) {
    createNotification(message, 'error', duration);
}

/**
 * Отображает сообщение об успехе
 * @param {string} message - Текст сообщения об успехе
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 5000)
 */
function showSuccess(message, duration = 5000) {
    createNotification(message, 'success', duration);
}

/**
 * Отображает предупреждающее сообщение
 * @param {string} message - Текст предупреждающего сообщения
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 5000)
 */
function showWarning(message, duration = 5000) {
    createNotification(message, 'warning', duration);
}

// Экспортируем функции, чтобы они были доступны глобально
window.showNotification = showNotification;
window.showSuccess = showSuccess;
window.showError = showError;
window.showWarning = showWarning;

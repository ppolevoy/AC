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
 * @param {string} type - Тип уведомления (success или error)
 * @param {number} duration - Продолжительность отображения в миллисекундах
 */
function createNotification(message, type, duration) {
    const container = getNotificationContainer();

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    // Добавляем уведомление в начало контейнера (новые уведомления появляются снизу)
    container.appendChild(notification);

    // Анимация появления
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);

    // Удаление уведомления
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            if (notification.parentNode) {
                container.removeChild(notification);
            }
            // Удаляем контейнер, если он пуст
            if (container.children.length === 0 && container.parentNode) {
                document.body.removeChild(container);
                notificationContainer = null;
            }
        }, 500);
    }, duration);
}

/**
 * Отображает уведомление об успешном действии
 * @param {string} message - Текст уведомления
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 3000)
 */
function showNotification(message, duration = 3000) {
    createNotification(message, 'success', duration);
}

/**
 * Отображает сообщение об ошибке
 * @param {string} message - Текст сообщения об ошибке
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 5000)
 */
function showError(message, duration = 5000) {
    createNotification(message, 'error', duration);
}

// Экспортируем функции, чтобы они были доступны глобально
window.showNotification = showNotification;
window.showError = showError;

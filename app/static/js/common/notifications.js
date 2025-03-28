/**
 * Faktura Apps - Модуль уведомлений
 * Содержит функции для отображения уведомлений и сообщений об ошибках
 */

/**
 * Отображает уведомление об успешном действии
 * @param {string} message - Текст уведомления
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 3000)
 */
function showNotification(message, duration = 3000) {
    const notification = document.createElement('div');
    notification.className = 'notification success';
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 500);
    }, duration);
}

/**
 * Отображает сообщение об ошибке
 * @param {string} message - Текст сообщения об ошибке
 * @param {number} duration - Продолжительность отображения в миллисекундах (по умолчанию 5000)
 */
function showError(message, duration = 5000) {
    const notification = document.createElement('div');
    notification.className = 'notification error';
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 500);
    }, duration);
}

// Экспортируем функции, чтобы они были доступны глобально
window.showNotification = showNotification;
window.showError = showError;

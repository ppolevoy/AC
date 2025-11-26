/**
 * dom-utils.js
 * Утилиты для работы с DOM
 */
(function() {
    'use strict';

    const DOMUtils = {
        /**
         * Получает контекст таблицы приложений
         * @returns {HTMLElement|null}
         */
        getTableContext() {
            return document.getElementById('applications-list-body');
        },

        /**
         * Выполняет querySelectorAll в контексте таблицы
         * @param {string} selector - CSS селектор
         * @returns {NodeList}
         */
        querySelectorInTable(selector) {
            const listBody = this.getTableContext();
            return listBody ? listBody.querySelectorAll(selector) : [];
        },

        /**
         * Возвращает количество колонок таблицы
         * @returns {number}
         */
        getTableColumnCount() {
            // Теперь используем div-структуру, но оставляем для совместимости
            return 6;
        },

        /**
         * Создает debounce-обертку для функции
         * @param {Function} func - функция для оборачивания
         * @param {number} wait - задержка в миллисекундах
         * @returns {Function}
         */
        debounce(func, wait = 300) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }
    };

    // Экспорт в глобальную область
    window.DOMUtils = DOMUtils;
})();

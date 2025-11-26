/**
 * security-utils.js
 * Утилиты безопасности для предотвращения XSS
 */
(function() {
    'use strict';

    const SecurityUtils = {
        /**
         * Экранирует HTML символы для предотвращения XSS
         * @param {string} text - текст для экранирования
         * @returns {string}
         */
        escapeHtml(text) {
            if (text == null) return '';
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;',
                '/': '&#x2F;'
            };
            return String(text).replace(/[&<>"'\/]/g, char => map[char]);
        },

        /**
         * Создает безопасный DOM элемент
         * @param {string} tag - имя тега
         * @param {Object} attrs - атрибуты элемента
         * @param {string} content - текстовое содержимое
         * @returns {HTMLElement}
         */
        createSafeElement(tag, attrs = {}, content = '') {
            const element = document.createElement(tag);

            Object.keys(attrs).forEach(key => {
                if (key === 'className') {
                    element.className = attrs.className;
                } else if (key === 'dataset') {
                    Object.assign(element.dataset, attrs.dataset);
                } else if (key === 'innerHTML' && attrs.trustHtml) {
                    element.innerHTML = attrs.innerHTML;
                } else {
                    element.setAttribute(key, attrs[key]);
                }
            });

            if (typeof content === 'string') {
                element.textContent = content;
            }

            return element;
        }
    };

    // Экспорт в глобальную область
    window.SecurityUtils = SecurityUtils;
})();

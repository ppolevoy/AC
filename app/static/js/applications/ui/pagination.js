/**
 * pagination.js
 * Модуль для управления пагинацией таблицы приложений
 * Извлечено из UIRenderer для улучшения поддержки кода
 */
(function() {
    'use strict';

    const Pagination = {
        /**
         * Возвращает срез данных для текущей страницы
         * @param {Array} data - массив данных
         * @param {number} currentPage - текущая страница
         * @param {number} pageSize - размер страницы
         * @returns {Array} срез данных
         */
        paginateData(data, currentPage, pageSize) {
            const startIndex = (currentPage - 1) * pageSize;
            const endIndex = startIndex + pageSize;
            return data.slice(startIndex, endIndex);
        },

        /**
         * Обновляет состояние элементов пагинации
         * @param {number} totalItems - общее количество элементов
         * @param {number} currentPage - текущая страница
         * @param {number} pageSize - размер страницы
         */
        updatePagination(totalItems, currentPage, pageSize) {
            const totalPages = Math.ceil(totalItems / pageSize);
            const paginationControls = document.getElementById('pagination-controls');
            if (!paginationControls) return;

            // Обновляем номер текущей страницы
            const pageNumberElement = paginationControls.querySelector('.page-number');
            if (pageNumberElement) {
                pageNumberElement.textContent = totalPages > 0 ? currentPage : '0';
            }

            // Обновляем состояние кнопок (только disabled, не обработчики!)
            const prevButton = paginationControls.querySelector('.prev-page');
            const nextButton = paginationControls.querySelector('.next-page');

            if (prevButton) {
                prevButton.disabled = currentPage <= 1 || totalPages === 0;
            }

            if (nextButton) {
                nextButton.disabled = currentPage >= totalPages || totalPages === 0;
            }

            // Сохраняем информацию о страницах в data-атрибутах для отладки
            paginationControls.setAttribute('data-current-page', currentPage);
            paginationControls.setAttribute('data-total-pages', totalPages);
            paginationControls.setAttribute('data-total-items', totalItems);
        },

        /**
         * Вычисляет общее количество страниц
         * @param {number} totalItems - общее количество элементов
         * @param {number} pageSize - размер страницы
         * @returns {number} количество страниц
         */
        getTotalPages(totalItems, pageSize) {
            return Math.ceil(totalItems / pageSize);
        }
    };

    // Экспорт в глобальную область
    window.Pagination = Pagination;
})();

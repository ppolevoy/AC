/**
 * HAProxy Filters Module
 * Модуль для фильтрации и поиска данных HAProxy
 */

const HAProxyFilters = {
    /**
     * Текущие активные фильтры
     */
    activeFilters: {
        instance: '',
        status: '',
        search: ''
    },

    /**
     * Инициализация обработчиков фильтров
     */
    init() {
        // Фильтр по инстансу
        document.getElementById('instance-filter').addEventListener('change', (e) => {
            this.activeFilters.instance = e.target.value;
            this.applyFilters();
        });

        // Фильтр по статусу
        document.getElementById('status-filter').addEventListener('change', (e) => {
            this.activeFilters.status = e.target.value;
            this.applyFilters();
        });

        // Поиск
        const searchInput = document.getElementById('search-input');
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.activeFilters.search = e.target.value.toLowerCase().trim();
                this.applyFilters();
            }, 300); // Debounce 300ms
        });
    },

    /**
     * Применить все активные фильтры
     */
    applyFilters() {
        const backends = document.querySelectorAll('.backend-accordion-item');

        backends.forEach(backend => {
            const shouldShowBackend = this.filterBackend(backend);
            backend.style.display = shouldShowBackend ? '' : 'none';
        });

        // Проверяем, есть ли видимые бэкенды
        const visibleBackends = document.querySelectorAll('.backend-accordion-item:not([style*="display: none"])');
        if (visibleBackends.length === 0) {
            document.getElementById('empty-message').style.display = 'block';
        } else {
            document.getElementById('empty-message').style.display = 'none';
        }
    },

    /**
     * Фильтровать backend
     * @param {HTMLElement} backendElement - DOM элемент backend
     * @returns {boolean} Показывать ли backend
     */
    filterBackend(backendElement) {
        const rows = backendElement.querySelectorAll('.server-row');
        let hasVisibleServers = false;

        rows.forEach(row => {
            const shouldShowRow = this.filterServerRow(row);
            row.style.display = shouldShowRow ? '' : 'none';

            if (shouldShowRow) {
                hasVisibleServers = true;
            }
        });

        return hasVisibleServers;
    },

    /**
     * Фильтровать строку сервера
     * @param {HTMLElement} rowElement - DOM элемент строки сервера
     * @returns {boolean} Показывать ли строку
     */
    filterServerRow(rowElement) {
        // Фильтр по статусу
        if (this.activeFilters.status) {
            const statusElement = rowElement.querySelector('.status-text');
            const status = statusElement ? statusElement.textContent.trim() : '';

            if (status !== this.activeFilters.status) {
                return false;
            }
        }

        // Фильтр по поиску
        if (this.activeFilters.search) {
            const serverName = rowElement.querySelector('.col-server')?.textContent.toLowerCase() || '';
            const address = rowElement.querySelector('.col-address')?.textContent.toLowerCase() || '';

            if (!serverName.includes(this.activeFilters.search) &&
                !address.includes(this.activeFilters.search)) {
                return false;
            }
        }

        // Фильтр по инстансу (применяется на уровне загрузки данных в manager)
        // Здесь не проверяем, так как данные уже отфильтрованы

        return true;
    },

    /**
     * Сбросить все фильтры
     */
    reset() {
        document.getElementById('instance-filter').value = '';
        document.getElementById('status-filter').value = '';
        document.getElementById('search-input').value = '';

        this.activeFilters = {
            instance: '',
            status: '',
            search: ''
        };

        this.applyFilters();
    },

    /**
     * Получить текущее значение фильтра инстанса
     * @returns {string}
     */
    getInstanceFilter() {
        return this.activeFilters.instance;
    }
};

// Экспортируем для использования в других модулях
window.HAProxyFilters = HAProxyFilters;

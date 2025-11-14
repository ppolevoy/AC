/**
 * Eureka Filters Module
 * Модуль для фильтрации данных Eureka dashboard
 */

const EurekaFilters = {
    /**
     * Текущие фильтры
     */
    currentFilters: {
        serverId: '',
        appName: '',
        status: '',
        searchText: ''
    },

    /**
     * Все instances (без фильтрации)
     */
    allInstances: [],

    /**
     * Инициализация фильтров
     */
    init() {
        // Обработчики для select фильтров
        document.getElementById('server-filter')?.addEventListener('change', (e) => {
            this.currentFilters.serverId = e.target.value;
            this.applyFilters();
        });

        document.getElementById('app-filter')?.addEventListener('change', (e) => {
            this.currentFilters.appName = e.target.value;
            this.applyFilters();
        });

        document.getElementById('status-filter')?.addEventListener('change', (e) => {
            this.currentFilters.status = e.target.value;
            this.applyFilters();
        });

        // Обработчик для поиска
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.currentFilters.searchText = e.target.value.toLowerCase();
                this.applyFilters();
            });
        }
    },

    /**
     * Установить все instances
     * @param {Array} instances - Массив instances
     */
    setInstances(instances) {
        this.allInstances = instances || [];
        this.applyFilters();
    },

    /**
     * Применить фильтры
     */
    applyFilters() {
        let filtered = [...this.allInstances];

        // Фильтр по серверу
        if (this.currentFilters.serverId) {
            const serverId = parseInt(this.currentFilters.serverId);
            filtered = filtered.filter(inst => inst.eureka_server_id === serverId);
        }

        // Фильтр по приложению
        if (this.currentFilters.appName) {
            filtered = filtered.filter(inst => inst.service_name === this.currentFilters.appName);
        }

        // Фильтр по статусу
        if (this.currentFilters.status) {
            filtered = filtered.filter(inst => inst.status === this.currentFilters.status);
        }

        // Фильтр по поисковому запросу
        if (this.currentFilters.searchText) {
            const searchText = this.currentFilters.searchText;
            filtered = filtered.filter(inst => {
                return (
                    inst.instance_id.toLowerCase().includes(searchText) ||
                    inst.service_name.toLowerCase().includes(searchText) ||
                    inst.ip_address.includes(searchText)
                );
            });
        }

        // Отрисовать отфильтрованные данные
        if (window.EurekaUI) {
            EurekaUI.renderInstancesTable(filtered);
        }

        // Обновить статистику для отфильтрованных данных
        this.updateFilteredStats(filtered);
    },

    /**
     * Обновить статистику для отфильтрованных данных
     * @param {Array} instances - Отфильтрованные instances
     */
    updateFilteredStats(instances) {
        // Подсчитать уникальные приложения
        const uniqueApps = new Set(instances.map(inst => inst.service_name));

        const stats = {
            total_apps: uniqueApps.size,
            total_instances: instances.length,
            up_count: instances.filter(inst => inst.status === 'UP').length,
            paused_count: instances.filter(inst => inst.status === 'PAUSED').length,
            down_count: instances.filter(inst => inst.status === 'DOWN').length,
            starting_count: instances.filter(inst => inst.status === 'STARTING').length
        };

        if (window.EurekaUI) {
            EurekaUI.renderStats(stats);
        }
    },

    /**
     * Сбросить фильтры
     */
    resetFilters() {
        this.currentFilters = {
            serverId: '',
            appName: '',
            status: '',
            searchText: ''
        };

        // Сбросить значения в UI
        const serverFilter = document.getElementById('server-filter');
        if (serverFilter) serverFilter.value = '';

        const appFilter = document.getElementById('app-filter');
        if (appFilter) appFilter.value = '';

        const statusFilter = document.getElementById('status-filter');
        if (statusFilter) statusFilter.value = '';

        const searchInput = document.getElementById('search-input');
        if (searchInput) searchInput.value = '';

        this.applyFilters();
    }
};

// Экспортируем EurekaFilters в глобальную область
window.EurekaFilters = EurekaFilters;

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
        console.log('Applying filters:', this.currentFilters);
        console.log('Total instances before filtering:', this.allInstances.length);

        let filtered = [...this.allInstances];

        // Фильтр по серверу
        if (this.currentFilters.serverId) {
            const serverId = parseInt(this.currentFilters.serverId);
            console.log('Filtering by server ID:', serverId);
            filtered = filtered.filter(inst =>
                inst != null && inst.eureka_server_id != null && inst.eureka_server_id === serverId
            );
            console.log('After server filter:', filtered.length);
        }

        // Фильтр по приложению
        if (this.currentFilters.appName) {
            console.log('Filtering by app name:', this.currentFilters.appName);
            console.log('Sample instance service_name:', filtered.length > 0 ? filtered[0].service_name : 'N/A');
            const appNameLower = this.currentFilters.appName.toLowerCase();
            filtered = filtered.filter(inst =>
                inst != null && inst.service_name != null && inst.service_name.toLowerCase() === appNameLower
            );
            console.log('After app filter:', filtered.length);
        }

        // Фильтр по статусу
        if (this.currentFilters.status) {
            console.log('Filtering by status:', this.currentFilters.status);
            filtered = filtered.filter(inst =>
                inst != null && inst.status != null && inst.status === this.currentFilters.status
            );
            console.log('After status filter:', filtered.length);
        }

        // Фильтр по поисковому запросу
        if (this.currentFilters.searchText) {
            const searchText = this.currentFilters.searchText;
            console.log('Filtering by search text:', searchText);
            filtered = filtered.filter(inst => {
                if (inst == null) return false;

                const instanceId = inst.instance_id ? inst.instance_id.toLowerCase() : '';
                const serviceName = inst.service_name ? inst.service_name.toLowerCase() : '';
                const ipAddress = inst.ip_address ? inst.ip_address : '';

                return (
                    instanceId.includes(searchText) ||
                    serviceName.includes(searchText) ||
                    ipAddress.includes(searchText)
                );
            });
            console.log('After search filter:', filtered.length);
        }

        console.log('Final filtered count:', filtered.length);

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
        // Подсчитать уникальные приложения (с проверкой на null)
        const uniqueApps = new Set(
            instances
                .filter(inst => inst != null && inst.service_name != null)
                .map(inst => inst.service_name)
        );

        const stats = {
            total_apps: uniqueApps.size,
            total_instances: instances.length,
            up_count: instances.filter(inst => inst != null && inst.status === 'UP').length,
            paused_count: instances.filter(inst => inst != null && inst.status === 'PAUSED').length,
            down_count: instances.filter(inst => inst != null && inst.status === 'DOWN').length,
            starting_count: instances.filter(inst => inst != null && inst.status === 'STARTING').length
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

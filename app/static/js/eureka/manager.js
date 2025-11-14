/**
 * Eureka Manager Module
 * Главный модуль управления Eureka dashboard
 */

const EurekaManager = {
    /**
     * Интервал автообновления
     */
    refreshInterval: null,

    /**
     * Текущий интервал обновления (в мс)
     */
    currentRefreshRate: 30000, // 30 секунд по умолчанию

    /**
     * Инициализация менеджера
     */
    async init() {
        // Инициализация фильтров
        EurekaFilters.init();

        // Привязать обработчики событий
        this.attachEventHandlers();

        // Загрузить данные
        await this.loadData();

        // Запустить автообновление
        this.startAutoRefresh();
    },

    /**
     * Привязать обработчики событий
     */
    attachEventHandlers() {
        // Кнопка обновления
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadData();
            });
        }

        // Селект интервала автообновления
        const refreshIntervalSelect = document.getElementById('refresh-interval-select');
        if (refreshIntervalSelect) {
            refreshIntervalSelect.addEventListener('change', (e) => {
                this.currentRefreshRate = parseInt(e.target.value);
                this.restartAutoRefresh();
            });
        }

        // Обработчик закрытия модального окна по overlay
        const modal = document.getElementById('loglevel-modal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal || e.target.classList.contains('modal-overlay')) {
                    closeLoglevelModal();
                }
            });
        }
    },

    /**
     * Загрузить данные
     */
    async loadData() {
        try {
            EurekaUI.showLoading();

            // Загрузить серверы для фильтров
            const serversResult = await EurekaAPI.getServers(true);
            if (serversResult.success && serversResult.data) {
                EurekaUI.populateServerFilter(serversResult.data);
            }

            // Загрузить приложения для фильтров
            const appsResult = await EurekaAPI.getApplications();
            if (appsResult.success && appsResult.data) {
                EurekaUI.populateAppFilter(appsResult.data);
            }

            // Загрузить instances
            const instancesResult = await EurekaAPI.getInstances();
            if (instancesResult.success && instancesResult.data) {
                // Установить instances в фильтры
                EurekaFilters.setInstances(instancesResult.data);
            } else {
                // Показать пустое сообщение
                EurekaFilters.setInstances([]);
                EurekaUI.showError(instancesResult.error || 'Не удалось загрузить данные');
            }
        } catch (error) {
            console.error('Error loading Eureka data:', error);
            EurekaUI.showError('Ошибка при загрузке данных: ' + error.message);
            EurekaFilters.setInstances([]);
        }
    },

    /**
     * Запустить автообновление
     */
    startAutoRefresh() {
        // Остановить существующий интервал если есть
        this.stopAutoRefresh();

        if (this.currentRefreshRate > 0) {
            this.refreshInterval = setInterval(() => {
                this.loadData();
            }, this.currentRefreshRate);
        }
    },

    /**
     * Остановить автообновление
     */
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    },

    /**
     * Перезапустить автообновление
     */
    restartAutoRefresh() {
        this.stopAutoRefresh();
        this.startAutoRefresh();
    }
};

// Экспортируем EurekaManager в глобальную область
window.EurekaManager = EurekaManager;

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    // Проверяем, что мы на странице Eureka
    if (document.querySelector('.eureka-container')) {
        EurekaManager.init();
    }
});

// Очистка при выгрузке страницы
window.addEventListener('beforeunload', () => {
    if (window.EurekaManager) {
        EurekaManager.stopAutoRefresh();
    }
});

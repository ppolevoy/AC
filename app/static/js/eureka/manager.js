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
     * Отслеживание приложений с ошибками (для уведомлений о новых ошибках)
     */
    applicationsWithErrors: new Set(),

    /**
     * Отслеживание серверов с ошибками (для уведомлений о новых ошибках)
     */
    serversWithErrors: new Set(),

    /**
     * Инициализация менеджера
     */
    async init() {
        // Инициализация UI модуля
        EurekaUI.init();

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

        // Обработчик изменения фильтра серверов - обновляем баннер ошибки
        const serverFilter = document.getElementById('server-filter');
        if (serverFilter) {
            serverFilter.addEventListener('change', () => {
                EurekaUI.updateServerErrorBanner();
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

                // Проверяем наличие новых ошибок серверов
                this.checkForNewServerErrors(serversResult.data);
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

                // Проверяем наличие новых ошибок
                this.checkForNewApplicationErrors(instancesResult.data);
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
     * Проверка наличия новых ошибок приложений и показ уведомлений
     * @param {Array} instances - Массив instances
     */
    checkForNewApplicationErrors(instances) {
        if (!instances || instances.length === 0) {
            return;
        }

        // Собираем уникальные приложения с ошибками
        const currentErrorApps = new Map(); // app_id -> {app_name, error}
        const newErrors = [];

        instances.forEach(instance => {
            if (instance.eureka_application && instance.eureka_application.last_fetch_status === 'failed') {
                const appId = instance.eureka_application.id;
                const appName = instance.eureka_application.app_name;
                const error = instance.eureka_application.last_fetch_error || 'Неизвестная ошибка';

                currentErrorApps.set(appId, { appName, error });

                // Если это новая ошибка (не была в предыдущей проверке)
                if (!this.applicationsWithErrors.has(appId)) {
                    newErrors.push({ appId, appName, error });
                }
            }
        });

        // Показываем уведомление о новых ошибках
        if (newErrors.length > 0) {
            const message = newErrors.length === 1
                ? `⚠️ Ошибка получения данных от агента для приложения "${newErrors[0].appName}"`
                : `⚠️ Обнаружено ${newErrors.length} приложений с ошибками получения данных`;

            if (window.showNotification) {
                window.showNotification(message, 'warning');
            } else {
                console.warn(message);
            }
        }

        // Обновляем список отслеживаемых ошибок
        this.applicationsWithErrors = new Set(currentErrorApps.keys());
    },

    /**
     * Проверка наличия новых ошибок серверов Eureka и показ уведомлений
     * @param {Array} servers - Массив серверов
     */
    checkForNewServerErrors(servers) {
        if (!servers || servers.length === 0) {
            return;
        }

        // Находим серверы с ошибками
        const currentErrorServers = new Set();
        const newErrors = [];

        servers.forEach(server => {
            if (server.last_error || server.consecutive_failures > 0) {
                currentErrorServers.add(server.id);

                // Если это новая ошибка (не была в предыдущей проверке)
                if (!this.serversWithErrors.has(server.id)) {
                    newErrors.push({
                        id: server.id,
                        name: `${server.eureka_host}:${server.eureka_port}`,
                        error: server.last_error || `${server.consecutive_failures} последовательных сбоев`
                    });
                }
            }
        });

        // Показываем уведомление о новых ошибках
        if (newErrors.length > 0) {
            const message = newErrors.length === 1
                ? `⚠️ Ошибка синхронизации сервера Eureka "${newErrors[0].name}": ${newErrors[0].error}`
                : `⚠️ Обнаружено ${newErrors.length} серверов Eureka с ошибками синхронизации`;

            if (window.showNotification) {
                window.showNotification(message, 'warning');
            } else {
                console.warn(message);
            }
        }

        // Обновляем список отслеживаемых ошибок
        this.serversWithErrors = currentErrorServers;
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

/**
 * HAProxy Manager Module
 * Главный модуль для координации работы HAProxy UI
 */

const HAProxyManager = {
    /**
     * Флаг инициализации
     */
    initialized: false,

    /**
     * Интервал автообновления
     */
    refreshInterval: null,

    /**
     * Отслеживание бэкендов с ошибками (для уведомлений о новых ошибках)
     */
    backendsWithErrors: new Set(),

    /**
     * Отслеживание инстансов с ошибками (для уведомлений о новых ошибках)
     */
    instancesWithErrors: new Set(),

    /**
     * Инициализация менеджера
     */
    async init() {
        if (this.initialized) {
            return;
        }

        // Инициализируем фильтры
        HAProxyFilters.init();

        // Инициализируем обработчики кнопок
        this.initButtonHandlers();

        // Загружаем данные
        await this.loadData();

        // Автообновление - читаем интервал из select
        const intervalSelect = document.getElementById('refresh-interval-select');
        const interval = parseInt(intervalSelect.value, 10);
        if (interval > 0) {
            this.startAutoRefresh(interval);
        }

        this.initialized = true;
    },

    /**
     * Инициализация обработчиков кнопок
     */
    initButtonHandlers() {
        // Кнопка обновления
        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.loadData();
        });

        // Кнопка "Развернуть все"
        document.getElementById('expand-all-btn').addEventListener('click', () => {
            HAProxyUI.expandAll();
        });

        // Кнопка "Свернуть все"
        document.getElementById('collapse-all-btn').addEventListener('click', () => {
            HAProxyUI.collapseAll();
        });

        // Кнопка "Сбросить выбор"
        document.getElementById('clear-selection-btn').addEventListener('click', () => {
            HAProxyUI.clearSelection();
        });

        // Quick Action buttons (disabled в Фазе 1)
        document.querySelectorAll('.quick-action-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (!btn.disabled) {
                    const action = btn.dataset.action;
                    this.handleBulkAction(action);
                }
            });
        });

        // Обработчик изменения интервала автообновления
        document.getElementById('refresh-interval-select').addEventListener('change', (e) => {
            const interval = parseInt(e.target.value, 10);
            this.setRefreshInterval(interval);
        });

        // Обработчик изменения фильтра инстансов - обновляем баннер ошибки
        document.getElementById('instance-filter').addEventListener('change', () => {
            HAProxyUI.updateInstanceErrorBanner();
        });
    },

    /**
     * Загрузка данных с сервера
     */
    async loadData() {
        try {
            HAProxyUI.showLoading();

            // Загружаем сводную статистику
            const summary = await HAProxyAPI.getSummary();

            if (!summary.success) {
                throw new Error(summary.error || 'Failed to load HAProxy summary');
            }

            // Обновляем глобальную статистику
            HAProxyUI.updateGlobalStats(summary);

            // Обновляем фильтр инстансов
            HAProxyUI.renderInstanceFilter(summary.instances || []);

            // Проверяем наличие новых ошибок инстансов
            this.checkForNewInstanceErrors(summary.instances || []);

            // Загружаем backends для выбранного инстанса или всех
            await this.loadBackends();

        } catch (error) {
            console.error('Error loading HAProxy data:', error);
            this.showError('Ошибка при загрузке данных HAProxy. Проверьте консоль для деталей.');
        }
    },

    /**
     * Загрузка backends
     */
    async loadBackends() {
        try {
            const instanceFilter = HAProxyFilters.getInstanceFilter();

            if (instanceFilter) {
                // Загружаем backends для конкретного инстанса
                const result = await HAProxyAPI.getInstanceBackends(instanceFilter);

                if (!result.success) {
                    throw new Error(result.error || 'Failed to load backends');
                }

                // Загружаем серверы для каждого backend
                const backendsWithServers = await Promise.all(
                    result.backends.map(async (backend) => {
                        try {
                            const serversResult = await HAProxyAPI.getBackendServers(backend.id);
                            return {
                                ...backend,
                                servers: serversResult.success ? serversResult.servers : []
                            };
                        } catch (error) {
                            console.error(`Error loading servers for backend ${backend.id}:`, error);
                            return {
                                ...backend,
                                servers: []
                            };
                        }
                    })
                );

                HAProxyUI.renderBackends(backendsWithServers);

                // Проверяем наличие новых ошибок
                this.checkForNewBackendErrors(backendsWithServers);

            } else {
                // Загружаем все backends для всех инстансов
                const summary = await HAProxyAPI.getSummary();

                if (!summary.success) {
                    throw new Error(summary.error || 'Failed to load summary');
                }

                const instances = summary.instances || [];

                // Собираем все backends со всех инстансов
                const allBackends = [];

                for (const instance of instances) {
                    try {
                        const result = await HAProxyAPI.getInstanceBackends(instance.id);

                        if (result.success && result.backends) {
                            // Загружаем серверы для каждого backend
                            const backendsWithServers = await Promise.all(
                                result.backends.map(async (backend) => {
                                    try {
                                        const serversResult = await HAProxyAPI.getBackendServers(backend.id);
                                        return {
                                            ...backend,
                                            servers: serversResult.success ? serversResult.servers : []
                                        };
                                    } catch (error) {
                                        console.error(`Error loading servers for backend ${backend.id}:`, error);
                                        return {
                                            ...backend,
                                            servers: []
                                        };
                                    }
                                })
                            );

                            allBackends.push(...backendsWithServers);
                        }
                    } catch (error) {
                        console.error(`Error loading backends for instance ${instance.id}:`, error);
                    }
                }

                HAProxyUI.renderBackends(allBackends);

                // Проверяем наличие новых ошибок
                this.checkForNewBackendErrors(allBackends);
            }

            // Применяем фильтры после загрузки
            HAProxyFilters.applyFilters();

        } catch (error) {
            console.error('Error loading backends:', error);
            throw error;
        }
    },

    /**
     * Проверка наличия новых ошибок бэкендов и показ уведомлений
     * @param {Array} backends - Массив backends
     */
    checkForNewBackendErrors(backends) {
        if (!backends || backends.length === 0) {
            return;
        }

        // Находим бэкенды с ошибками
        const currentErrorBackends = new Set();
        const newErrors = [];

        backends.forEach(backend => {
            if (backend.last_fetch_status === 'failed') {
                currentErrorBackends.add(backend.id);

                // Если это новая ошибка (не была в предыдущей проверке)
                if (!this.backendsWithErrors.has(backend.id)) {
                    newErrors.push({
                        id: backend.id,
                        name: backend.backend_name,
                        error: backend.last_fetch_error || 'Неизвестная ошибка'
                    });
                }
            }
        });

        // Показываем уведомление о новых ошибках
        if (newErrors.length > 0) {
            const message = newErrors.length === 1
                ? `⚠️ Ошибка получения данных от агента для бэкенда "${newErrors[0].name}"`
                : `⚠️ Обнаружено ${newErrors.length} бэкендов с ошибками получения данных`;

            if (window.showNotification) {
                window.showNotification(message, 'warning');
            } else {
                console.warn(message);
            }
        }

        // Обновляем список отслеживаемых ошибок
        this.backendsWithErrors = currentErrorBackends;
    },

    /**
     * Обработка массового действия над серверами
     * (В Фазе 1 не используется, так как кнопки disabled)
     * @param {string} action - Действие (ready/drain/maint)
     */
    handleBulkAction(action) {
        const selected = [];
        document.querySelectorAll('.server-checkbox:checked').forEach(cb => {
            const serverId = cb.dataset.serverId;
            const backendId = cb.dataset.backend;
            selected.push({ serverId, backendId });
        });

        if (selected.length === 0) {
            return;
        }

        alert(`Действие "${action}" будет доступно в Фазе 2.\nВыбрано серверов: ${selected.length}`);
    },

    /**
     * Запустить автообновление
     * @param {number} interval - Интервал в миллисекундах
     */
    startAutoRefresh(interval) {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }

        this.refreshInterval = setInterval(() => {
            this.loadData();
        }, interval);
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
     * Установить интервал автообновления
     * @param {number} interval - Интервал в миллисекундах (0 = отключено)
     */
    setRefreshInterval(interval) {
        // Останавливаем текущее автообновление
        this.stopAutoRefresh();

        // Если интервал > 0, запускаем новое автообновление
        if (interval > 0) {
            this.startAutoRefresh(interval);
            console.log(`Auto-refresh enabled: ${interval / 1000}s`);
        } else {
            console.log('Auto-refresh disabled');
        }
    },

    /**
     * Показать сообщение об ошибке
     * @param {string} message - Текст ошибки
     */
    showError(message) {
        // Используем существующую систему уведомлений, если она доступна
        if (window.showNotification) {
            window.showNotification(message, 'error');
        } else {
            alert(message);
        }
    },

    /**
     * Проверка наличия новых ошибок инстансов и показ уведомлений
     * @param {Array} instances - Массив инстансов
     */
    checkForNewInstanceErrors(instances) {
        if (!instances || instances.length === 0) {
            return;
        }

        // Находим инстансы с ошибками
        const currentErrorInstances = new Set();
        const newErrors = [];

        instances.forEach(instance => {
            if (instance.last_sync_status === 'failed') {
                currentErrorInstances.add(instance.id);

                // Если это новая ошибка (не была в предыдущей проверке)
                if (!this.instancesWithErrors.has(instance.id)) {
                    newErrors.push({
                        id: instance.id,
                        name: instance.name,
                        error: instance.last_sync_error || 'Неизвестная ошибка'
                    });
                }
            }
        });

        // Показываем уведомление о новых ошибках
        if (newErrors.length > 0) {
            const message = newErrors.length === 1
                ? `⚠️ Ошибка синхронизации инстанса "${newErrors[0].name}": ${newErrors[0].error}`
                : `⚠️ Обнаружено ${newErrors.length} инстансов с ошибками синхронизации`;

            if (window.showNotification) {
                window.showNotification(message, 'warning');
            } else {
                console.warn(message);
            }
        }

        // Обновляем список отслеживаемых ошибок
        this.instancesWithErrors = currentErrorInstances;
    },

    /**
     * Принудительная синхронизация инстанса
     * @param {number} instanceId - ID инстанса
     */
    async syncInstance(instanceId) {
        try {
            if (window.showNotification) {
                window.showNotification('Запуск синхронизации...', 'info');
            }

            const result = await HAProxyAPI.syncInstance(instanceId);

            if (result.success) {
                if (window.showNotification) {
                    window.showNotification('Синхронизация выполнена успешно', 'success');
                }
            } else {
                // Показываем ошибку от сервера
                const errorMsg = result.error || 'Синхронизация не удалась';
                if (window.showNotification) {
                    window.showNotification(`Ошибка: ${errorMsg}`, 'error');
                }
            }

            // Перезагружаем данные в любом случае для обновления статуса
            await this.loadData();
        } catch (error) {
            console.error('Error syncing instance:', error);
            this.showError(`Ошибка синхронизации: ${error.message}`);
        }
    }
};

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    HAProxyManager.init();
});

// Остановка автообновления при уходе со страницы
window.addEventListener('beforeunload', () => {
    HAProxyManager.stopAutoRefresh();
});

// Экспортируем для использования в других модулях
window.HAProxyManager = HAProxyManager;

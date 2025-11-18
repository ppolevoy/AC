/**
 * Eureka UI Module
 * Модуль для управления интерфейсом Eureka dashboard
 */

const EurekaUI = {
    /**
     * Кэш DOM элементов
     */
    elements: {},

    /**
     * Текущий instance ID для модального окна
     */
    currentInstanceId: null,

    /**
     * Инициализация UI модуля
     */
    init() {
        // Кэшируем DOM элементы
        this.elements.serverFilter = document.getElementById('server-filter');
        this.elements.appFilter = document.getElementById('app-filter');
        this.elements.tbody = document.getElementById('instances-tbody');
        this.elements.emptyMessage = document.getElementById('empty-message');
        this.elements.tableContainer = document.getElementById('table-container');
        this.elements.loglevelModal = document.getElementById('loglevel-modal');
        this.elements.loggerNameInput = document.getElementById('logger-name');
        this.elements.logLevelSelect = document.getElementById('log-level-select');
        this.elements.durationInput = document.getElementById('duration');

        // Статистика
        this.elements.totalApps = document.getElementById('total-apps');
        this.elements.totalInstances = document.getElementById('total-instances');
        this.elements.upCount = document.getElementById('up-count');
        this.elements.pausedCount = document.getElementById('paused-count');
        this.elements.downCount = document.getElementById('down-count');
        this.elements.startingCount = document.getElementById('starting-count');

        // Привязать обработчик закрытия модального окна
        this.attachModalHandlers();
    },

    /**
     * Привязать обработчики для модального окна
     */
    attachModalHandlers() {
        if (this.elements.loglevelModal) {
            this.elements.loglevelModal.addEventListener('click', (e) => {
                if (e.target === this.elements.loglevelModal || e.target.classList.contains('modal-overlay')) {
                    this.closeLogLevelModal();
                }
            });
        }
    },

    /**
     * Отрисовать статистику
     * @param {Object} stats - Статистика
     */
    renderStats(stats) {
        if (this.elements.totalApps) this.elements.totalApps.textContent = stats.total_apps || 0;
        if (this.elements.totalInstances) this.elements.totalInstances.textContent = stats.total_instances || 0;
        if (this.elements.upCount) this.elements.upCount.textContent = stats.up_count || 0;
        if (this.elements.pausedCount) this.elements.pausedCount.textContent = stats.paused_count || 0;
        if (this.elements.downCount) this.elements.downCount.textContent = stats.down_count || 0;
        if (this.elements.startingCount) this.elements.startingCount.textContent = stats.starting_count || 0;
    },

    /**
     * Отрисовать таблицу instances
     * @param {Array} instances - Массив instances
     */
    renderInstancesTable(instances) {
        const tbody = this.elements.tbody;
        const emptyMessage = this.elements.emptyMessage;
        const tableContainer = this.elements.tableContainer;

        if (!instances || instances.length === 0) {
            if (tbody) tbody.innerHTML = '';
            if (tableContainer) tableContainer.style.display = 'block';
            if (emptyMessage) emptyMessage.style.display = 'block';
            return;
        }

        if (emptyMessage) emptyMessage.style.display = 'none';
        if (tableContainer) tableContainer.style.display = 'block';

        const rows = instances.map(instance => this.createInstanceRow(instance));
        if (tbody) tbody.innerHTML = rows.join('');

        // Привязать обработчики событий для кнопок действий
        this.attachActionHandlers();
    },

    /**
     * Создать строку таблицы для instance
     * @param {Object} instance - Данные instance
     * @returns {string} HTML строка
     */
    createInstanceRow(instance) {
        const statusClass = this.getStatusClass(instance.status);
        const mappingBadge = this.createMappingBadge(instance);
        const heartbeat = instance.last_heartbeat
            ? this.formatTimestamp(instance.last_heartbeat)
            : '<span style="color: #6b7280;">N/A</span>';

        return `
            <tr data-instance-id="${instance.id}">
                <td>
                    <span class="instance-id">${this.escapeHtml(instance.instance_id)}</span>
                </td>
                <td>
                    <span class="app-name">${this.escapeHtml(instance.service_name)}</span>
                </td>
                <td>
                    <span class="ip-address">${this.escapeHtml(instance.ip_address)}</span>
                </td>
                <td>${instance.port}</td>
                <td>
                    <span class="status-badge ${statusClass}">
                        <span class="status-dot ${statusClass}"></span>
                        ${instance.status}
                    </span>
                </td>
                <td>${mappingBadge}</td>
                <td><span class="timestamp">${heartbeat}</span></td>
                <td>
                    <div class="table-actions">
                        ${this.createActionButtons(instance)}
                    </div>
                </td>
            </tr>
        `;
    },

    /**
     * Создать кнопки действий для instance
     * @param {Object} instance - Данные instance
     * @returns {string} HTML кнопок
     */
    createActionButtons(instance) {
        const buttons = [];

        // Health check
        buttons.push(`
            <button class="table-action-btn success"
                    data-action="health"
                    data-instance-id="${instance.id}"
                    title="Health Check">
                ✓
            </button>
        `);

        // Pause (всегда показываем кнопку Pause, т.к. реализация кастомная)
        buttons.push(`
            <button class="table-action-btn warning"
                    data-action="pause"
                    data-instance-id="${instance.id}"
                    title="Pause">
                ⏸
            </button>
        `);

        // Log Level
        buttons.push(`
            <button class="table-action-btn primary"
                    data-action="loglevel"
                    data-instance-id="${instance.id}"
                    title="Log Level">
                📝
            </button>
        `);

        // Shutdown
        buttons.push(`
            <button class="table-action-btn danger"
                    data-action="shutdown"
                    data-instance-id="${instance.id}"
                    title="Shutdown">
                ⏹
            </button>
        `);

        return buttons.join('');
    },

    /**
     * Создать badge для отображения статуса маппинга
     * @param {Object} instance - Данные instance
     * @returns {string} HTML badge
     */
    createMappingBadge(instance) {
        if (instance.application_id) {
            const badgeClass = instance.is_manual_mapping ? 'manual' : 'mapped';
            const icon = instance.is_manual_mapping ? '🔗' : '🤖';
            const title = instance.is_manual_mapping ? 'Manual mapping' : 'Auto mapping';
            return `<span class="mapping-badge ${badgeClass}" title="${title}">${icon} Mapped</span>`;
        } else {
            return `<span class="mapping-badge unmapped">Unmapped</span>`;
        }
    },

    /**
     * Получить CSS класс для статуса
     * @param {string} status - Статус
     * @returns {string} CSS класс
     */
    getStatusClass(status) {
        const statusMap = {
            'UP': 'status-up',
            'DOWN': 'status-down',
            'PAUSED': 'status-paused',
            'STARTING': 'status-starting',
            'OUT_OF_SERVICE': 'status-out_of_service'
        };
        return statusMap[status] || 'status-unknown';
    },

    /**
     * Форматировать timestamp
     * @param {string} timestamp - ISO timestamp
     * @returns {string} Форматированная дата
     */
    formatTimestamp(timestamp) {
        if (!timestamp) return 'N/A';
        const date = new Date(timestamp);
        const now = new Date();
        const diff = Math.floor((now - date) / 1000); // разница в секундах

        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;

        // Для старых дат показываем полную дату
        return date.toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    /**
     * Экранировать HTML
     * @param {string} text - Текст
     * @returns {string} Экранированный текст
     */
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return String(text).replace(/[&<>"']/g, m => map[m]);
    },

    /**
     * Показать сообщение об ошибке
     * @param {string} message - Текст сообщения
     */
    showError(message) {
        if (window.showNotification) {
            window.showNotification(message, 'error');
        } else {
            alert('Ошибка: ' + message);
        }
    },

    /**
     * Показать успешное сообщение
     * @param {string} message - Текст сообщения
     */
    showSuccess(message) {
        if (window.showNotification) {
            window.showNotification(message, 'success');
        } else {
            console.log('Успех: ' + message);
        }
    },

    /**
     * Показать индикатор загрузки
     */
    showLoading() {
        // Убираем анимацию загрузки - просто очищаем таблицу
        if (this.elements.tbody) this.elements.tbody.innerHTML = '';

        // Показываем таблицу (с заголовком), скрываем сообщение
        if (this.elements.tableContainer) this.elements.tableContainer.style.display = 'block';
        if (this.elements.emptyMessage) this.elements.emptyMessage.style.display = 'none';
    },

    /**
     * Заполнить фильтры серверов
     * @param {Array} servers - Список серверов
     */
    populateServerFilter(servers) {
        if (!this.elements.serverFilter) return;

        this.elements.serverFilter.innerHTML = '<option value="">Все серверы</option>';

        servers.forEach(server => {
            const option = document.createElement('option');
            option.value = server.id;
            option.textContent = `${server.eureka_host}:${server.eureka_port}`;
            this.elements.serverFilter.appendChild(option);
        });
    },

    /**
     * Заполнить фильтры приложений
     * @param {Array} apps - Список приложений
     */
    populateAppFilter(apps) {
        if (!this.elements.appFilter) return;

        this.elements.appFilter.innerHTML = '<option value="">Все приложения</option>';

        // Получаем уникальные имена приложений из instances
        const uniqueApps = new Set();
        apps.forEach(app => {
            if (app && app.app_name) {
                uniqueApps.add(app.app_name);
            }
        });

        Array.from(uniqueApps).sort().forEach(appName => {
            const option = document.createElement('option');
            option.value = appName;
            option.textContent = appName;
            this.elements.appFilter.appendChild(option);
        });
    },

    /**
     * Привязать обработчики событий для кнопок действий
     */
    attachActionHandlers() {
        // Обработчики для кнопок в таблице
        document.querySelectorAll('.table-action-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const action = e.currentTarget.dataset.action;
                const instanceId = parseInt(e.currentTarget.dataset.instanceId);

                if (action === 'health') {
                    await this.handleHealthCheck(instanceId);
                } else if (action === 'pause') {
                    await this.handlePause(instanceId);
                } else if (action === 'resume') {
                    await this.handleResume(instanceId);
                } else if (action === 'shutdown') {
                    await this.handleShutdown(instanceId);
                } else if (action === 'loglevel') {
                    this.handleLogLevel(instanceId);
                }
            });
        });
    },

    /**
     * Обработать health check
     * @param {number} instanceId - ID instance
     */
    async handleHealthCheck(instanceId) {
        try {
            const result = await EurekaAPI.getHealth(instanceId);
            if (result.success) {
                this.showSuccess(`Health check: ${result.data.status || 'OK'}`);
            } else {
                this.showError(result.error || 'Health check failed');
            }
        } catch (error) {
            this.showError('Ошибка при выполнении health check: ' + error.message);
        }
    },

    /**
     * Обработать pause
     * @param {number} instanceId - ID instance
     */
    async handlePause(instanceId) {
        if (!confirm('Вы уверены, что хотите приостановить этот instance?')) {
            return;
        }

        try {
            const result = await EurekaAPI.pauseInstance(instanceId);
            if (result.success) {
                this.showSuccess('Instance успешно приостановлен');
                // Обновить данные
                if (window.EurekaManager) {
                    EurekaManager.loadData();
                }
            } else {
                this.showError(result.error || 'Не удалось приостановить instance');
            }
        } catch (error) {
            this.showError('Ошибка при приостановке instance: ' + error.message);
        }
    },

    /**
     * Обработать resume
     * @param {number} instanceId - ID instance
     */
    async handleResume(instanceId) {
        try {
            const result = await EurekaAPI.resumeInstance(instanceId);
            if (result.success) {
                this.showSuccess('Instance успешно возобновлен');
                // Обновить данные
                if (window.EurekaManager) {
                    EurekaManager.loadData();
                }
            } else {
                this.showError(result.error || 'Не удалось возобновить instance');
            }
        } catch (error) {
            this.showError('Ошибка при возобновлении instance: ' + error.message);
        }
    },

    /**
     * Обработать shutdown
     * @param {number} instanceId - ID instance
     */
    async handleShutdown(instanceId) {
        if (!confirm('Вы уверены, что хотите выключить этот instance? Это действие нельзя отменить из интерфейса!')) {
            return;
        }

        try {
            const result = await EurekaAPI.shutdownInstance(instanceId);
            if (result.success) {
                this.showSuccess('Instance успешно выключен');
                // Обновить данные
                if (window.EurekaManager) {
                    EurekaManager.loadData();
                }
            } else {
                this.showError(result.error || 'Не удалось выключить instance');
            }
        } catch (error) {
            this.showError('Ошибка при выключении instance: ' + error.message);
        }
    },

    /**
     * Обработать изменение log level
     * @param {number} instanceId - ID instance
     */
    handleLogLevel(instanceId) {
        // Сохранить instanceId в свойстве модуля
        this.currentInstanceId = instanceId;

        // Показать модальное окно
        if (this.elements.loglevelModal) {
            this.elements.loglevelModal.classList.add('active');
            this.elements.loglevelModal.style.display = 'flex';
        }
    },

    /**
     * Закрыть модальное окно log level
     */
    closeLogLevelModal() {
        if (this.elements.loglevelModal) {
            this.elements.loglevelModal.classList.remove('active');
            this.elements.loglevelModal.style.display = 'none';
        }

        // Очистить форму
        if (this.elements.loggerNameInput) this.elements.loggerNameInput.value = '';
        if (this.elements.logLevelSelect) this.elements.logLevelSelect.value = 'INFO';
        if (this.elements.durationInput) this.elements.durationInput.value = '';
    },

    /**
     * Применить изменение log level
     */
    async applyLogLevel() {
        const instanceId = this.currentInstanceId;
        const loggerName = this.elements.loggerNameInput ? this.elements.loggerNameInput.value.trim() : '';
        const level = this.elements.logLevelSelect ? this.elements.logLevelSelect.value : 'INFO';
        const duration = this.elements.durationInput ? this.elements.durationInput.value : '';

        if (!loggerName) {
            this.showError('Укажите имя logger');
            return;
        }

        try {
            const result = await EurekaAPI.setLogLevel(
                instanceId,
                loggerName,
                level,
                duration ? parseInt(duration) : null
            );

            if (result.success) {
                this.showSuccess('Log level успешно изменен');
                this.closeLogLevelModal();
            } else {
                this.showError(result.error || 'Не удалось изменить log level');
            }
        } catch (error) {
            this.showError('Ошибка при изменении log level: ' + error.message);
        }
    }
};

// Экспортируем EurekaUI в глобальную область
window.EurekaUI = EurekaUI;

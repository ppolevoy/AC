/**
 * Eureka UI Module
 * Модуль для управления интерфейсом Eureka dashboard
 */

const EurekaUI = {
    /**
     * Отрисовать статистику
     * @param {Object} stats - Статистика
     */
    renderStats(stats) {
        document.getElementById('total-apps').textContent = stats.total_apps || 0;
        document.getElementById('total-instances').textContent = stats.total_instances || 0;
        document.getElementById('up-count').textContent = stats.up_count || 0;
        document.getElementById('paused-count').textContent = stats.paused_count || 0;
        document.getElementById('down-count').textContent = stats.down_count || 0;
        document.getElementById('starting-count').textContent = stats.starting_count || 0;
    },

    /**
     * Отрисовать таблицу instances
     * @param {Array} instances - Массив instances
     */
    renderInstancesTable(instances) {
        const tbody = document.getElementById('instances-tbody');
        const emptyMessage = document.getElementById('empty-message');
        const tableContainer = document.getElementById('table-container');

        if (!instances || instances.length === 0) {
            if (tbody) tbody.innerHTML = '';
            if (tableContainer) tableContainer.style.display = 'block';
            if (emptyMessage) emptyMessage.style.display = 'block';
            return;
        }

        if (emptyMessage) emptyMessage.style.display = 'none';
        if (tableContainer) tableContainer.style.display = 'block';

        const rows = instances.map(instance => this.createInstanceRow(instance));
        tbody.innerHTML = rows.join('');

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

        // Pause/Resume
        if (instance.status === 'PAUSED') {
            buttons.push(`
                <button class="table-action-btn primary"
                        data-action="resume"
                        data-instance-id="${instance.id}"
                        title="Resume">
                    ▶
                </button>
            `);
        } else {
            buttons.push(`
                <button class="table-action-btn warning"
                        data-action="pause"
                        data-instance-id="${instance.id}"
                        title="Pause">
                    ⏸
                </button>
            `);
        }

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
        const tbody = document.getElementById('instances-tbody');
        if (tbody) tbody.innerHTML = '';

        // Показываем таблицу (с заголовком), скрываем сообщение
        const tableContainer = document.getElementById('table-container');
        if (tableContainer) tableContainer.style.display = 'block';

        const emptyMessage = document.getElementById('empty-message');
        if (emptyMessage) emptyMessage.style.display = 'none';
    },

    /**
     * Заполнить фильтры серверов
     * @param {Array} servers - Список серверов
     */
    populateServerFilter(servers) {
        const select = document.getElementById('server-filter');
        select.innerHTML = '<option value="">Все серверы</option>';

        servers.forEach(server => {
            const option = document.createElement('option');
            option.value = server.id;
            option.textContent = `${server.eureka_host}:${server.eureka_port}`;
            select.appendChild(option);
        });
    },

    /**
     * Заполнить фильтры приложений
     * @param {Array} apps - Список приложений
     */
    populateAppFilter(apps) {
        const select = document.getElementById('app-filter');
        select.innerHTML = '<option value="">Все приложения</option>';

        // Получаем уникальные имена приложений из instances
        const uniqueApps = new Set();
        apps.forEach(app => {
            uniqueApps.add(app.app_name);
        });

        Array.from(uniqueApps).sort().forEach(appName => {
            const option = document.createElement('option');
            option.value = appName;
            option.textContent = appName;
            select.appendChild(option);
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
        // Сохранить instanceId для модального окна
        window.currentInstanceId = instanceId;

        // Показать модальное окно
        const modal = document.getElementById('loglevel-modal');
        if (modal) {
            modal.classList.add('active');
            modal.style.display = 'flex';
        }
    }
};

// Экспортируем EurekaUI в глобальную область
window.EurekaUI = EurekaUI;

/**
 * Закрыть модальное окно log level
 */
function closeLoglevelModal() {
    const modal = document.getElementById('loglevel-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }

    // Очистить форму
    document.getElementById('logger-name').value = '';
    document.getElementById('log-level-select').value = 'INFO';
    document.getElementById('duration').value = '';
}

/**
 * Применить изменение log level
 */
async function applyLoglevel() {
    const instanceId = window.currentInstanceId;
    const loggerName = document.getElementById('logger-name').value.trim();
    const level = document.getElementById('log-level-select').value;
    const duration = document.getElementById('duration').value;

    if (!loggerName) {
        EurekaUI.showError('Укажите имя logger');
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
            EurekaUI.showSuccess('Log level успешно изменен');
            closeLoglevelModal();
        } else {
            EurekaUI.showError(result.error || 'Не удалось изменить log level');
        }
    } catch (error) {
        EurekaUI.showError('Ошибка при изменении log level: ' + error.message);
    }
}

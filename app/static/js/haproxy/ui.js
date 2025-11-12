/**
 * HAProxy UI Module
 * Модуль для управления UI элементами HAProxy страницы
 */

const HAProxyUI = {
    /**
     * Обновить глобальную статистику
     * @param {Object} summary - Данные статистики из API
     */
    updateGlobalStats(summary) {
        document.getElementById('total-backends').textContent = summary.backends_count || 0;
        document.getElementById('total-servers').textContent = summary.servers_count || 0;
        document.getElementById('up-count').textContent = summary.status_stats?.UP || 0;
        document.getElementById('drain-count').textContent = summary.status_stats?.DRAIN || 0;
        document.getElementById('maint-count').textContent = summary.status_stats?.MAINT || 0;
        document.getElementById('down-count').textContent = summary.status_stats?.DOWN || 0;
    },

    /**
     * Отрисовать список инстансов в фильтре
     * @param {Array} instances - Массив инстансов
     */
    renderInstanceFilter(instances) {
        const filter = document.getElementById('instance-filter');
        const currentValue = filter.value;

        // Сохраняем опцию "Все инстансы"
        filter.innerHTML = '<option value="">Все инстансы</option>';

        instances.forEach(instance => {
            const option = document.createElement('option');
            option.value = instance.id;
            option.textContent = `${instance.name} (${instance.server_name})`;
            filter.appendChild(option);
        });

        // Восстанавливаем выбранное значение, если оно было
        if (currentValue) {
            filter.value = currentValue;
        }
    },

    /**
     * Отрисовать аккордеоны бэкендов
     * @param {Array} backends - Массив backends с серверами
     */
    renderBackends(backends) {
        const container = document.getElementById('backends-container');

        if (!backends || backends.length === 0) {
            container.innerHTML = '';
            document.getElementById('empty-message').style.display = 'block';
            return;
        }

        document.getElementById('empty-message').style.display = 'none';
        container.innerHTML = '';

        backends.forEach(backend => {
            const servers = backend.servers || [];
            const statusCounts = this.countStatusInServers(servers);

            const backendDiv = document.createElement('div');
            backendDiv.className = 'backend-accordion-item';
            backendDiv.dataset.backendId = backend.id;
            backendDiv.innerHTML = `
                <div class="backend-header" onclick="HAProxyUI.toggleBackend(this)">
                    <div class="backend-header-left">
                        <button class="accordion-toggle">
                            <span class="toggle-icon">▶</span>
                        </button>
                        <h3 class="backend-name">${backend.backend_name}</h3>
                        <span class="backend-server-count">${servers.length} серверов</span>
                    </div>
                    <div class="backend-header-right">
                        <div class="backend-status-indicators">
                            <span class="status-indicator">
                                <span class="status-dot status-up"></span>
                                <span>${statusCounts.UP}</span>
                            </span>
                            <span class="status-indicator">
                                <span class="status-dot status-drain"></span>
                                <span>${statusCounts.DRAIN}</span>
                            </span>
                            <span class="status-indicator">
                                <span class="status-dot status-maint"></span>
                                <span>${statusCounts.MAINT}</span>
                            </span>
                            <span class="status-indicator">
                                <span class="status-dot status-down"></span>
                                <span>${statusCounts.DOWN}</span>
                            </span>
                        </div>
                    </div>
                </div>

                <div class="backend-content">
                    <div class="data-table-container">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th class="col-checkbox">
                                        <input type="checkbox" class="select-all-in-backend" data-backend="${backend.id}" onchange="HAProxyUI.toggleBackendTableSelection(this)">
                                    </th>
                                    <th class="col-server">Сервер</th>
                                    <th class="col-status">Статус</th>
                                    <th class="col-address">Адрес</th>
                                    <th class="col-weight">Вес</th>
                                    <th class="col-connections">Текущие подключения</th>
                                    <th class="col-check">Health Check</th>
                                    <th class="col-uptime">Last Change</th>
                                    <th class="col-actions">Действия</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${servers.map((server, idx) => this.renderServerRow(server, backend.id, idx)).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            container.appendChild(backendDiv);
        });
    },

    /**
     * Отрисовать строку сервера в таблице
     * @param {Object} server - Данные сервера
     * @param {number} backendId - ID backend
     * @param {number} index - Индекс сервера
     * @returns {string} HTML код строки
     */
    renderServerRow(server, backendId, index) {
        const statusClass = server.status ? server.status.toLowerCase() : 'unknown';
        const connectionsHtml = this.formatConnections(server);

        return `
            <tr class="server-row" data-backend="${backendId}" data-server-id="${server.id}">
                <td class="col-checkbox">
                    <input type="checkbox" class="server-checkbox" data-backend="${backendId}" data-server-id="${server.id}" onchange="HAProxyUI.updateSelectedCount()">
                </td>
                <td class="col-server">${server.server_name}</td>
                <td class="col-status">
                    <span class="status-badge status-${statusClass}">
                        <span class="status-dot status-${statusClass}"></span>
                        <span class="status-text">${server.status || 'UNKNOWN'}</span>
                    </span>
                </td>
                <td class="col-address">${server.addr || 'N/A'}</td>
                <td class="col-weight">${server.weight || 1}</td>
                <td class="col-connections">${connectionsHtml}</td>
                <td class="col-check">${server.check_status || 'N/A'}</td>
                <td class="col-uptime">${this.formatLastChange(server.last_state_change)}</td>
                <td class="col-actions">
                    <div class="action-menu">
                        <button class="action-btn-small action-ready" disabled title="Будет доступно в Фазе 2">✓</button>
                        <button class="action-btn-small action-drain" disabled title="Будет доступно в Фазе 2">⏸</button>
                        <button class="action-btn-small action-maint" disabled title="Будет доступно в Фазе 2">🔧</button>
                    </div>
                </td>
            </tr>
        `;
    },

    /**
     * Форматировать отображение текущих подключений
     * @param {Object} server - Данные сервера
     * @returns {string} HTML код
     */
    formatConnections(server) {
        const scur = server.scur || 0;
        const smax = server.smax || 0;
        const isDrain = server.status === 'DRAIN';
        const isZero = scur === 0;

        let className = 'current-connections ';
        if (isDrain && isZero) {
            className += 'connections-zero';
        } else if (isDrain) {
            className += 'connections-drain-warning';
        } else {
            className += 'connections-active';
        }

        let html = '<div class="connections-info">';
        html += `<span class="${className}">${scur}</span>`;
        html += `<span class="connections-meta">max: ${smax}</span>`;

        if (isDrain && isZero) {
            html += '<span class="connections-drain-warning">✓ Готов к выводу</span>';
        } else if (isDrain && scur > 0) {
            html += '<span class="connections-drain-warning">⚠ Ожидание</span>';
        }

        html += '</div>';
        return html;
    },

    /**
     * Форматировать время последнего изменения состояния
     * @param {number} seconds - Секунды с последнего изменения
     * @returns {string} Отформатированное время
     */
    formatLastChange(seconds) {
        if (!seconds || seconds < 0) {
            return 'N/A';
        }

        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);

        if (days > 0) {
            return `${days}d ${hours}h`;
        } else if (hours > 0) {
            return `${hours}h`;
        } else {
            const minutes = Math.floor(seconds / 60);
            return `${minutes}m`;
        }
    },

    /**
     * Подсчитать количество серверов по статусам
     * @param {Array} servers - Массив серверов
     * @returns {Object} Объект с подсчетом по статусам
     */
    countStatusInServers(servers) {
        const counts = { UP: 0, DOWN: 0, MAINT: 0, DRAIN: 0 };

        servers.forEach(server => {
            const status = server.status || 'DOWN';
            if (counts.hasOwnProperty(status)) {
                counts[status]++;
            }
        });

        return counts;
    },

    /**
     * Переключить состояние аккордеона backend
     * @param {HTMLElement} headerElement - Элемент заголовка
     */
    toggleBackend(headerElement) {
        const item = headerElement.closest('.backend-accordion-item');
        item.classList.toggle('expanded');
    },

    /**
     * Переключить выбор всех серверов в backend
     * @param {HTMLInputElement} checkbox - Checkbox элемент
     */
    toggleBackendTableSelection(checkbox) {
        const backend = checkbox.dataset.backend;
        const checkboxes = document.querySelectorAll(`.server-checkbox[data-backend="${backend}"]`);
        checkboxes.forEach(cb => cb.checked = checkbox.checked);
        this.updateSelectedCount();
    },

    /**
     * Обновить счетчик выбранных серверов
     */
    updateSelectedCount() {
        const checked = document.querySelectorAll('.server-checkbox:checked').length;
        document.getElementById('selected-count').textContent = checked;
        document.getElementById('quick-actions').style.display = checked > 0 ? 'flex' : 'none';
    },

    /**
     * Показать сообщение о загрузке
     */
    showLoading() {
        const container = document.getElementById('backends-container');
        container.innerHTML = `
            <div class="loading-message">
                <span class="loading-spinner">⟳</span>
                Загрузка данных HAProxy...
            </div>
        `;
        document.getElementById('empty-message').style.display = 'none';
    },

    /**
     * Развернуть все аккордеоны
     */
    expandAll() {
        document.querySelectorAll('.backend-accordion-item').forEach(item => {
            item.classList.add('expanded');
        });
    },

    /**
     * Свернуть все аккордеоны
     */
    collapseAll() {
        document.querySelectorAll('.backend-accordion-item').forEach(item => {
            item.classList.remove('expanded');
        });
    },

    /**
     * Очистить выбор всех серверов
     */
    clearSelection() {
        document.querySelectorAll('.server-checkbox, .select-all-in-backend').forEach(cb => {
            cb.checked = false;
        });
        this.updateSelectedCount();
    }
};

// Экспортируем для использования в других модулях
window.HAProxyUI = HAProxyUI;

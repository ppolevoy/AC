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

            // Check for backend fetch errors
            const hasError = backend.last_fetch_status === 'failed';
            const errorIndicator = hasError ? '<span class="backend-error-indicator" title="' + (backend.last_fetch_error || 'Ошибка получения данных от агента') + '">⚠️</span>' : '';
            const errorClass = hasError ? 'has-error' : '';

            // Format last fetch time
            let lastFetchInfo = '';
            if (backend.last_fetch_at) {
                const fetchTime = new Date(backend.last_fetch_at);
                const now = new Date();
                const diffMinutes = Math.floor((now - fetchTime) / 60000);
                let timeAgo = '';
                if (diffMinutes < 1) {
                    timeAgo = 'только что';
                } else if (diffMinutes < 60) {
                    timeAgo = `${diffMinutes} мин. назад`;
                } else {
                    const diffHours = Math.floor(diffMinutes / 60);
                    timeAgo = `${diffHours} ч. назад`;
                }

                if (hasError) {
                    lastFetchInfo = `<div class="backend-error-message">
                        <strong>Ошибка:</strong> ${backend.last_fetch_error || 'Не удалось получить данные от агента'}
                        <div class="backend-error-time">Последняя попытка: ${timeAgo}</div>
                    </div>`;
                }
            }

            const backendDiv = document.createElement('div');
            backendDiv.className = 'backend-accordion-item ' + errorClass;
            backendDiv.dataset.backendId = backend.id;
            backendDiv.innerHTML = `
                <div class="backend-header" onclick="HAProxyUI.toggleBackend(this)">
                    <div class="backend-header-left">
                        <button class="accordion-toggle">
                            <span class="toggle-icon">▶</span>
                        </button>
                        <h3 class="backend-name">${backend.backend_name}${errorIndicator}</h3>
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
                ${lastFetchInfo}

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
                                    <th class="col-connections">Подключения</th>
                                    <th class="col-check">Health Check</th>
                                    <th class="col-uptime">Last Change</th>
                                    <th class="col-mapping">Маппинг</th>
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

        // Восстанавливаем состояние аккордеонов после рендеринга
        this.restoreAccordionState();
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
        const mappingHtml = this.formatMappingCell(server);

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
                <td class="col-mapping">${mappingHtml}</td>
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

        // Сохраняем состояние аккордеона
        this.saveAccordionState();
    },

    /**
     * Сохранить состояние всех аккордеонов в localStorage
     */
    saveAccordionState() {
        const expandedBackends = [];
        document.querySelectorAll('.backend-accordion-item.expanded').forEach(item => {
            const backendId = item.dataset.backendId;
            if (backendId) {
                expandedBackends.push(backendId);
            }
        });
        localStorage.setItem('haproxy_expanded_backends', JSON.stringify(expandedBackends));
    },

    /**
     * Восстановить состояние аккордеонов из localStorage
     */
    restoreAccordionState() {
        try {
            const savedState = localStorage.getItem('haproxy_expanded_backends');
            if (!savedState) {
                return;
            }

            const expandedBackends = JSON.parse(savedState);
            if (!Array.isArray(expandedBackends)) {
                return;
            }

            // Применяем сохраненное состояние
            expandedBackends.forEach(backendId => {
                const item = document.querySelector(`.backend-accordion-item[data-backend-id="${backendId}"]`);
                if (item) {
                    item.classList.add('expanded');
                }
            });
        } catch (error) {
            console.error('Error restoring accordion state:', error);
        }
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
        container.innerHTML = '';
        document.getElementById('empty-message').style.display = 'none';
    },

    /**
     * Развернуть все аккордеоны
     */
    expandAll() {
        document.querySelectorAll('.backend-accordion-item').forEach(item => {
            item.classList.add('expanded');
        });
        // Сохраняем состояние
        this.saveAccordionState();
    },

    /**
     * Свернуть все аккордеоны
     */
    collapseAll() {
        document.querySelectorAll('.backend-accordion-item').forEach(item => {
            item.classList.remove('expanded');
        });
        // Сохраняем состояние
        this.saveAccordionState();
    },

    /**
     * Очистить выбор всех серверов
     */
    clearSelection() {
        document.querySelectorAll('.server-checkbox, .select-all-in-backend').forEach(cb => {
            cb.checked = false;
        });
        this.updateSelectedCount();
    },

    // ==================== Mapping UI Methods ====================

    /**
     * Форматировать ячейку маппинга
     * @param {Object} server - Данные сервера
     * @returns {string} HTML код
     */
    formatMappingCell(server) {
        const hasMappedApp = server.application_id && server.application;
        const isManual = server.is_manual_mapping;

        if (hasMappedApp) {
            const badgeClass = isManual ? 'mapping-badge-manual' : 'mapping-badge-auto';
            const badgeIcon = isManual ? '🔗' : '⚙';
            const badgeTitle = isManual ? 'Ручной маппинг' : 'Автоматический маппинг';
            const appName = this.escapeHtml(server.application.name || '');
            const serverName = this.escapeHtml(server.server_name || '');

            // Извлекаем короткое имя хоста из FQDN (до первой точки)
            let hostname = '';
            if (server.application.server_name) {
                hostname = server.application.server_name.split('.')[0];
            }

            // Формируем отображаемое имя с hostname
            const displayName = hostname ? `${hostname}-${appName}` : appName;

            return `
                <div class="mapping-cell">
                    <span class="${badgeClass}" title="${badgeTitle}">
                        ${badgeIcon} ${displayName}
                    </span>
                    <button class="mapping-btn-unmap" data-server-id="${server.id}" data-server-name="${serverName}" onclick="HAProxyUI.unmapServerHandler(this)" title="Удалить связь">✖</button>
                </div>
            `;
        } else {
            return `
                <div class="mapping-cell">
                    <span class="mapping-badge-unmapped">Не связан</span>
                    <button class="mapping-btn-map" data-server-id="${server.id}" onclick="HAProxyUI.openMappingModalHandler(this)" title="Связать с приложением">🔗</button>
                </div>
            `;
        }
    },

    /**
     * Экранировать HTML специальные символы
     * @param {string} text - Текст для экранирования
     * @returns {string} Экранированный текст
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Обработчик для кнопки открытия модального окна (через data-атрибуты)
     * @param {HTMLElement} button - Кнопка
     */
    openMappingModalHandler(button) {
        const serverId = parseInt(button.dataset.serverId);
        this.openMappingModal(serverId);
    },

    /**
     * Обработчик для кнопки удаления маппинга (через data-атрибуты)
     * @param {HTMLElement} button - Кнопка
     */
    unmapServerHandler(button) {
        const serverId = parseInt(button.dataset.serverId);
        const serverName = button.dataset.serverName;
        this.unmapServer(serverId, serverName);
    },

    /**
     * Открыть модальное окно маппинга
     * @param {number} serverId - ID сервера
     */
    async openMappingModal(serverId) {
        try {
            // Показываем модальное окно с индикатором загрузки
            this.showMappingModal(serverId, null, []);

            // Загружаем список приложений
            const data = await HAProxyAPI.searchApplications(serverId);

            // Обновляем модальное окно с данными
            this.showMappingModal(serverId, data, data.applications || []);
        } catch (error) {
            console.error('Error opening mapping modal:', error);
            alert('Ошибка при загрузке списка приложений: ' + error.message);
        }
    },

    /**
     * Показать модальное окно маппинга
     * @param {number} serverId - ID сервера
     * @param {Object} serverData - Данные сервера из API
     * @param {Array} applications - Список приложений
     */
    showMappingModal(serverId, serverData, applications) {
        // Удаляем предыдущее модальное окно если есть
        const existingModal = document.getElementById('mapping-modal');
        if (existingModal) {
            existingModal.remove();
        }

        const loading = !serverData;
        const serverName = serverData ? serverData.server_name : 'Загрузка...';
        const serverIp = serverData ? serverData.server_ip : '';

        const modalHtml = `
            <div class="modal-overlay" id="mapping-modal" onclick="HAProxyUI.closeMappingModal(event)">
                <div class="modal-content mapping-modal-content" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <h3>Маппинг сервера: ${serverName}</h3>
                        <button class="modal-close" onclick="HAProxyUI.closeMappingModal()">×</button>
                    </div>
                    <div class="modal-body">
                        ${loading ? `` : `
                            <div class="mapping-info">
                                <p><strong>IP сервера:</strong> ${serverIp}</p>
                                <p class="mapping-hint">Показаны только приложения с IP ${serverIp}</p>
                            </div>

                            <div class="mapping-search">
                                <input type="text" id="mapping-search-input" class="search-input" placeholder="Поиск по имени приложения..." onkeyup="HAProxyUI.filterApplications(this.value)">
                            </div>

                            <div class="applications-list" id="applications-list">
                                ${applications.length > 0 ? applications.map(app => `
                                    <div class="application-item" data-app-name="${app.name.toLowerCase()}">
                                        <div class="application-info">
                                            <div class="application-name">${app.name}</div>
                                            <div class="application-details">
                                                ${app.ip}:${app.port || 'N/A'} • ${app.server_name || 'Unknown'}
                                                ${app.status ? `• <span class="app-status app-status-${app.status.toLowerCase()}">${app.status}</span>` : ''}
                                            </div>
                                        </div>
                                        <button class="btn-select-app" onclick="HAProxyUI.selectApplication(${serverId}, ${app.id}, '${app.name}')">Выбрать</button>
                                    </div>
                                `).join('') : `
                                    <div class="empty-message-small">
                                        <p>Приложений с IP ${serverIp} не найдено</p>
                                    </div>
                                `}
                            </div>

                            <div class="mapping-notes">
                                <label for="mapping-notes-input">Заметки (опционально):</label>
                                <textarea id="mapping-notes-input" class="mapping-notes-input" placeholder="Причина ручного маппинга..." rows="2"></textarea>
                            </div>
                        `}
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    /**
     * Закрыть модальное окно маппинга
     * @param {Event} event - Event object (optional)
     */
    closeMappingModal(event) {
        if (event && event.target.className !== 'modal-overlay') {
            return;
        }

        const modal = document.getElementById('mapping-modal');
        if (modal) {
            modal.remove();
        }
    },

    /**
     * Фильтровать приложения в модальном окне
     * @param {string} query - Поисковый запрос
     */
    filterApplications(query) {
        const lowerQuery = query.toLowerCase();
        const appItems = document.querySelectorAll('.application-item');

        appItems.forEach(item => {
            const appName = item.dataset.appName;
            if (appName.includes(lowerQuery)) {
                item.style.display = '';
            } else {
                item.style.display = 'none';
            }
        });
    },

    /**
     * Выбрать приложение для маппинга
     * @param {number} serverId - ID сервера
     * @param {number} appId - ID приложения
     * @param {string} appName - Имя приложения
     */
    async selectApplication(serverId, appId, appName) {
        const notes = document.getElementById('mapping-notes-input')?.value || '';

        if (!confirm(`Связать сервер с приложением "${appName}"?`)) {
            return;
        }

        try {
            const result = await HAProxyAPI.mapServer(serverId, appId, notes);

            if (result.success) {
                alert('Маппинг установлен успешно');
                this.closeMappingModal();

                // Обновляем строку в таблице с новыми данными
                await this.updateServerRow(serverId, result.server);
            } else {
                alert('Ошибка: ' + (result.error || 'Неизвестная ошибка'));
            }
        } catch (error) {
            console.error('Error mapping server:', error);
            alert('Ошибка при установке маппинга: ' + error.message);
        }
    },

    /**
     * Удалить маппинг сервера
     * @param {number} serverId - ID сервера
     * @param {string} serverName - Имя сервера
     */
    async unmapServer(serverId, serverName) {
        if (!confirm(`Удалить связь для сервера "${serverName}"?`)) {
            return;
        }

        try {
            const result = await HAProxyAPI.unmapServer(serverId);

            if (result.success) {
                alert('Маппинг удален успешно');

                // Обновляем строку в таблице с новыми данными
                await this.updateServerRow(serverId, result.server);
            } else {
                alert('Ошибка: ' + (result.error || 'Неизвестная ошибка'));
            }
        } catch (error) {
            console.error('Error unmapping server:', error);
            alert('Ошибка при удалении маппинга: ' + error.message);
        }
    },

    /**
     * Обновить строку сервера в таблице
     * @param {number} serverId - ID сервера
     * @param {Object} serverData - Обновленные данные сервера
     */
    async updateServerRow(serverId, serverData) {
        // Находим строку сервера в таблице
        const serverRow = document.querySelector(`tr.server-row[data-server-id="${serverId}"]`);
        if (!serverRow) {
            console.warn(`Server row with id ${serverId} not found`);
            return;
        }

        // Получаем backend_id из атрибута строки
        const backendId = serverRow.dataset.backend;

        // Создаем новую строку с обновленными данными
        const newRowHtml = this.renderServerRow(serverData, backendId, 0);

        // ВАЖНО: Используем tbody вместо div для корректного парсинга <tr>
        const tempTbody = document.createElement('tbody');
        tempTbody.innerHTML = newRowHtml;
        const newRow = tempTbody.firstElementChild;

        // Заменяем старую строку на новую
        serverRow.replaceWith(newRow);

        // Добавляем анимацию для визуального подтверждения
        newRow.classList.add('row-updated');
        setTimeout(() => {
            newRow.classList.remove('row-updated');
        }, 1000);
    }
};

// Экспортируем для использования в других модулях
window.HAProxyUI = HAProxyUI;

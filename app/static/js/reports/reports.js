/**
 * Faktura Apps - Модуль отчётов о версиях приложений
 */

(function() {
    'use strict';

    // ========================================
    // СОСТОЯНИЕ
    // ========================================
    const state = {
        activeTab: 'current-versions',
        filters: {
            serverIds: [],
            catalogIds: [],
            dateFrom: null,
            dateTo: null
        },
        sorting: {
            currentVersions: { field: 'name', order: 'asc' },
            versionHistory: { field: 'changed_at', order: 'desc' }
        },
        groupByServer: false,
        expandedServers: new Set(),
        filtersData: {
            servers: [],
            catalogs: []
        }
    };

    // ========================================
    // API СЕРВИС
    // ========================================
    const API = {
        async getFilters() {
            try {
                const response = await fetch('/api/reports/filters');
                return await response.json();
            } catch (error) {
                console.error('Error loading filters:', error);
                return { success: false };
            }
        },

        async getCurrentVersions(params = {}) {
            try {
                const queryParams = new URLSearchParams();
                if (params.serverIds?.length) queryParams.set('server_ids', params.serverIds.join(','));
                if (params.catalogIds?.length) queryParams.set('catalog_ids', params.catalogIds.join(','));
                if (params.sortBy) queryParams.set('sort_by', params.sortBy);
                if (params.sortOrder) queryParams.set('sort_order', params.sortOrder);

                const response = await fetch(`/api/reports/current-versions?${queryParams}`);
                return await response.json();
            } catch (error) {
                console.error('Error loading current versions:', error);
                return { success: false, data: [] };
            }
        },

        async getVersionHistory(params = {}) {
            try {
                const queryParams = new URLSearchParams();
                if (params.serverIds?.length) queryParams.set('server_ids', params.serverIds.join(','));
                if (params.catalogIds?.length) queryParams.set('catalog_ids', params.catalogIds.join(','));
                if (params.dateFrom) queryParams.set('date_from', params.dateFrom);
                if (params.dateTo) queryParams.set('date_to', params.dateTo);
                if (params.sortBy) queryParams.set('sort_by', params.sortBy);
                if (params.sortOrder) queryParams.set('sort_order', params.sortOrder);

                const response = await fetch(`/api/reports/version-history?${queryParams}`);
                return await response.json();
            } catch (error) {
                console.error('Error loading version history:', error);
                return { success: false, data: [] };
            }
        },

        getExportUrl(reportType, format) {
            const params = new URLSearchParams();
            params.set('format', format);

            if (state.filters.serverIds?.length) {
                params.set('server_ids', state.filters.serverIds.join(','));
            }
            if (state.filters.catalogIds?.length) {
                params.set('catalog_ids', state.filters.catalogIds.join(','));
            }
            if (reportType === 'version-history') {
                if (state.filters.dateFrom) params.set('date_from', state.filters.dateFrom);
                if (state.filters.dateTo) params.set('date_to', state.filters.dateTo);
                return `/api/reports/version-history/export?${params}`;
            }
            return `/api/reports/current-versions/export?${params}`;
        }
    };

    // ========================================
    // UI РЕНДЕРИНГ
    // ========================================
    const UI = {
        escapeHtml(text) {
            if (text == null) return '';
            const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
            return String(text).replace(/[&<>"']/g, char => map[char]);
        },

        formatDate(isoString) {
            if (!isoString) return '-';
            try {
                const date = new Date(isoString);
                return date.toLocaleString('ru-RU', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {
                return isoString;
            }
        },

        getStatusClass(status) {
            const classes = {
                'online': 'status-online',
                'offline': 'status-offline',
                'unknown': 'status-unknown',
                'no_data': 'status-unknown'
            };
            return classes[status] || 'status-unknown';
        },

        getStatusText(status) {
            const texts = {
                'online': 'Online',
                'offline': 'Offline',
                'unknown': 'Unknown',
                'no_data': 'No Data'
            };
            return texts[status] || status || 'Unknown';
        },

        getSourceText(source) {
            const texts = {
                'user': 'Пользователь',
                'agent': 'Агент',
                'system': 'Система',
                'update_task': 'Обновление',
                'polling': 'Polling'
            };
            return texts[source] || source || '-';
        },

        showLoading() {
            document.getElementById('loading-indicator').style.display = 'flex';
            document.getElementById('no-data-message').style.display = 'none';
        },

        hideLoading() {
            document.getElementById('loading-indicator').style.display = 'none';
        },

        showNoData() {
            document.getElementById('no-data-message').style.display = 'flex';
        },

        hideNoData() {
            document.getElementById('no-data-message').style.display = 'none';
        },

        updateSortIndicators(tableId, sortField, sortOrder) {
            const table = document.getElementById(tableId);
            if (!table) return;

            // Сбрасываем все индикаторы
            table.querySelectorAll('th.sortable').forEach(th => {
                th.classList.remove('sort-asc', 'sort-desc');
            });

            // Устанавливаем текущий
            const currentTh = table.querySelector(`th[data-sort="${sortField}"]`);
            if (currentTh) {
                currentTh.classList.add(sortOrder === 'asc' ? 'sort-asc' : 'sort-desc');
            }
        },

        renderTableInfo(containerId, total) {
            const container = document.getElementById(containerId);
            if (container) {
                container.textContent = `Всего: ${total}`;
            }
        },

        renderCurrentVersionsTable(data) {
            const tbody = document.getElementById('current-versions-body');
            this.hideNoData();

            if (!data || data.length === 0) {
                tbody.innerHTML = '';
                this.showNoData();
                this.renderTableInfo('current-versions-info', 0);
                return;
            }

            if (state.groupByServer) {
                this.renderGroupedByServer(tbody, data);
            } else {
                this.renderFlatTable(tbody, data);
            }

            this.renderTableInfo('current-versions-info', data.length);
            this.updateSortIndicators('current-versions-table', state.sorting.currentVersions.field, state.sorting.currentVersions.order);
        },

        renderFlatTable(tbody, data) {
            tbody.innerHTML = data.map(app => `
                <tr>
                    <td class="col-name">${this.escapeHtml(app.instance_name)}</td>
                    <td class="col-type"><span class="app-type-badge type-${app.app_type}">${this.escapeHtml(app.app_type)}</span></td>
                    <td class="col-server">${this.escapeHtml(app.server_name || '-')}</td>
                    <td class="col-version"><code>${this.escapeHtml(app.version || app.tag || '-')}</code></td>
                    <td class="col-date">${this.formatDate(app.updated_at)}</td>
                </tr>
            `).join('');
        },

        renderGroupedByServer(tbody, data) {
            // Группируем данные по серверам
            const grouped = {};
            data.forEach(app => {
                const serverKey = app.server_id || 0;
                const serverName = app.server_name || 'Без сервера';
                if (!grouped[serverKey]) {
                    grouped[serverKey] = {
                        name: serverName,
                        apps: []
                    };
                }
                grouped[serverKey].apps.push(app);
            });

            let html = '';
            Object.entries(grouped).forEach(([serverId, server]) => {
                const isExpanded = state.expandedServers.has(serverId);
                const expandIcon = isExpanded ? '▼' : '▶';

                html += `
                    <tr class="server-group-header" data-server-id="${serverId}">
                        <td colspan="5">
                            <div class="server-group-title">
                                <span class="expand-icon">${expandIcon}</span>
                                <span class="server-name">${this.escapeHtml(server.name)}</span>
                                <span class="app-count">(${server.apps.length} приложений)</span>
                            </div>
                        </td>
                    </tr>
                `;

                if (isExpanded) {
                    server.apps.forEach(app => {
                        html += `
                            <tr class="server-group-item" data-server-id="${serverId}">
                                <td class="col-name">${this.escapeHtml(app.instance_name)}</td>
                                <td class="col-type"><span class="app-type-badge type-${app.app_type}">${this.escapeHtml(app.app_type)}</span></td>
                                <td class="col-server">${this.escapeHtml(app.server_name || '-')}</td>
                                <td class="col-version"><code>${this.escapeHtml(app.version || app.tag || '-')}</code></td>
                                <td class="col-date">${this.formatDate(app.updated_at)}</td>
                            </tr>
                        `;
                    });
                }
            });

            tbody.innerHTML = html;

            // Добавляем обработчики для сворачивания/разворачивания
            tbody.querySelectorAll('.server-group-header').forEach(header => {
                header.addEventListener('click', () => {
                    const serverId = header.dataset.serverId;
                    if (state.expandedServers.has(serverId)) {
                        state.expandedServers.delete(serverId);
                    } else {
                        state.expandedServers.add(serverId);
                    }
                    this.renderCurrentVersionsTable(data);
                });
            });
        },

        renderVersionHistoryTable(data) {
            const tbody = document.getElementById('version-history-body');
            this.hideNoData();

            if (!data || data.length === 0) {
                tbody.innerHTML = '';
                this.showNoData();
                this.renderTableInfo('version-history-info', 0);
                return;
            }

            tbody.innerHTML = data.map(history => `
                <tr>
                    <td class="col-name">${this.escapeHtml(history.instance?.instance_name || '-')}</td>
                    <td class="col-server">${this.escapeHtml(history.instance?.server_name || '-')}</td>
                    <td class="col-version"><code>${this.escapeHtml(history.old_version || '-')}</code></td>
                    <td class="col-version"><code class="version-new">${this.escapeHtml(history.new_version || '-')}</code></td>
                    <td class="col-date">${this.formatDate(history.changed_at)}</td>
                    <td class="col-source"><span class="source-badge source-${history.changed_by}">${this.getSourceText(history.changed_by)}</span></td>
                </tr>
            `).join('');

            this.renderTableInfo('version-history-info', data.length);
            this.updateSortIndicators('version-history-table', state.sorting.versionHistory.field, state.sorting.versionHistory.order);
        },

        async loadFilters() {
            const result = await API.getFilters();
            if (result.success) {
                state.filtersData.servers = result.servers || [];
                state.filtersData.catalogs = result.catalogs || [];

                const serverSelect = document.getElementById('server-filter');
                serverSelect.innerHTML = state.filtersData.servers.map(s =>
                    `<option value="${s.id}">${this.escapeHtml(s.name)}</option>`
                ).join('');

                const catalogSelect = document.getElementById('catalog-filter');
                catalogSelect.innerHTML = state.filtersData.catalogs.map(c =>
                    `<option value="${c.id}">${this.escapeHtml(c.name)}</option>`
                ).join('');
            }
        }
    };

    // ========================================
    // КОНТРОЛЛЕР
    // ========================================
    const Controller = {
        currentData: [],

        async loadCurrentVersions() {
            UI.showLoading();
            try {
                const result = await API.getCurrentVersions({
                    serverIds: state.filters.serverIds,
                    catalogIds: state.filters.catalogIds,
                    sortBy: state.sorting.currentVersions.field,
                    sortOrder: state.sorting.currentVersions.order
                });

                if (result.success) {
                    this.currentData = result.data;
                    UI.renderCurrentVersionsTable(result.data);
                }
            } catch (error) {
                console.error('Error:', error);
            } finally {
                UI.hideLoading();
            }
        },

        async loadVersionHistory() {
            UI.showLoading();
            try {
                const result = await API.getVersionHistory({
                    serverIds: state.filters.serverIds,
                    catalogIds: state.filters.catalogIds,
                    dateFrom: state.filters.dateFrom,
                    dateTo: state.filters.dateTo,
                    sortBy: state.sorting.versionHistory.field,
                    sortOrder: state.sorting.versionHistory.order
                });

                if (result.success) {
                    UI.renderVersionHistoryTable(result.data);
                }
            } catch (error) {
                console.error('Error:', error);
            } finally {
                UI.hideLoading();
            }
        },

        switchTab(tabName) {
            state.activeTab = tabName;

            // Переключение кнопок табов
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tabName);
            });

            // Переключение контента
            document.querySelectorAll('.tab-content').forEach(content => {
                content.style.display = 'none';
            });
            document.getElementById(`${tabName}-tab`).style.display = 'block';

            // Показ/скрытие фильтра по датам
            const dateFilterGroup = document.getElementById('date-filter-group');
            dateFilterGroup.style.display = tabName === 'version-history' ? 'flex' : 'none';

            // Загрузка данных
            if (tabName === 'current-versions') {
                this.loadCurrentVersions();
            } else {
                this.loadVersionHistory();
            }
        },

        applyFilters() {
            const serverSelect = document.getElementById('server-filter');
            const catalogSelect = document.getElementById('catalog-filter');
            const dateFrom = document.getElementById('date-from');
            const dateTo = document.getElementById('date-to');

            state.filters.serverIds = Array.from(serverSelect.selectedOptions).map(o => parseInt(o.value));
            state.filters.catalogIds = Array.from(catalogSelect.selectedOptions).map(o => parseInt(o.value));
            state.filters.dateFrom = dateFrom.value || null;
            state.filters.dateTo = dateTo.value || null;

            // Перезагрузка данных текущего таба
            if (state.activeTab === 'current-versions') {
                this.loadCurrentVersions();
            } else {
                this.loadVersionHistory();
            }
        },

        clearFilters() {
            document.getElementById('server-filter').selectedIndex = -1;
            document.getElementById('catalog-filter').selectedIndex = -1;
            document.getElementById('date-from').value = '';
            document.getElementById('date-to').value = '';

            state.filters = { serverIds: [], catalogIds: [], dateFrom: null, dateTo: null };
            this.applyFilters();
        },

        toggleGroupByServer() {
            state.groupByServer = document.getElementById('group-by-server').checked;
            // Перерисовываем таблицу с текущими данными
            if (state.activeTab === 'current-versions' && this.currentData.length > 0) {
                UI.renderCurrentVersionsTable(this.currentData);
            }
        },

        handleSort(field) {
            const sortKey = state.activeTab === 'current-versions' ? 'currentVersions' : 'versionHistory';

            // Переключаем направление если то же поле, иначе asc
            if (state.sorting[sortKey].field === field) {
                state.sorting[sortKey].order = state.sorting[sortKey].order === 'asc' ? 'desc' : 'asc';
            } else {
                state.sorting[sortKey].field = field;
                state.sorting[sortKey].order = 'asc';
            }

            // Перезагрузка данных
            if (state.activeTab === 'current-versions') {
                this.loadCurrentVersions();
            } else {
                this.loadVersionHistory();
            }
        },

        exportReport(format) {
            const url = API.getExportUrl(state.activeTab, format);
            window.location.href = url;
        }
    };

    // ========================================
    // ИНИЦИАЛИЗАЦИЯ
    // ========================================
    function init() {
        // Загрузка фильтров
        UI.loadFilters();

        // Обработчики табов
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => Controller.switchTab(btn.dataset.tab));
        });

        // Обработчики фильтров
        document.getElementById('apply-filters-btn').addEventListener('click',
            () => Controller.applyFilters());
        document.getElementById('clear-filters-btn').addEventListener('click',
            () => Controller.clearFilters());

        // Обработчик группировки
        document.getElementById('group-by-server').addEventListener('change',
            () => Controller.toggleGroupByServer());

        // Обработчики сортировки
        document.querySelectorAll('.report-table th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const sortField = th.dataset.sort;
                if (sortField) {
                    Controller.handleSort(sortField);
                }
            });
        });

        // Обработчики экспорта
        document.getElementById('export-csv-btn').addEventListener('click',
            () => Controller.exportReport('csv'));
        document.getElementById('export-json-btn').addEventListener('click',
            () => Controller.exportReport('json'));

        // Начальная загрузка данных
        Controller.loadCurrentVersions();
    }

    // Запуск при загрузке DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();

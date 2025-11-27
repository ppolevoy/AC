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
        },

        async sendReport(data) {
            try {
                const response = await fetch('/api/reports/send', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                return await response.json();
            } catch (error) {
                console.error('Error sending report:', error);
                return { success: false, error: error.message };
            }
        },

        async getMailingGroups() {
            try {
                const response = await fetch('/api/mailing-groups');
                return await response.json();
            } catch (error) {
                console.error('Error loading mailing groups:', error);
                return { success: false, groups: [] };
            }
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
                serverSelect.innerHTML = '<option value="">Все серверы</option>' +
                    state.filtersData.servers.map(s =>
                        `<option value="${s.id}">${this.escapeHtml(s.name)}</option>`
                    ).join('');

                const catalogSelect = document.getElementById('catalog-filter');
                catalogSelect.innerHTML = '<option value="">Все приложения</option>' +
                    state.filtersData.catalogs.map(c =>
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

            // Фильтруем пустые значения (опция "Все")
            state.filters.serverIds = Array.from(serverSelect.selectedOptions)
                .map(o => o.value)
                .filter(v => v !== '')
                .map(v => parseInt(v));
            state.filters.catalogIds = Array.from(catalogSelect.selectedOptions)
                .map(o => o.value)
                .filter(v => v !== '')
                .map(v => parseInt(v));
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
            document.getElementById('server-filter').selectedIndex = 0;
            document.getElementById('catalog-filter').selectedIndex = 0;
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
    // МОДАЛЬНОЕ ОКНО ОТПРАВКИ EMAIL
    // ========================================
    const EmailModal = {
        modal: null,
        sending: false,

        init() {
            this.modal = document.getElementById('send-email-modal');
            if (!this.modal) return;

            // Обработчики закрытия модалки
            document.getElementById('close-email-modal').addEventListener('click', () => this.close());
            document.getElementById('cancel-email-btn').addEventListener('click', () => this.close());
            this.modal.querySelector('.modal-overlay').addEventListener('click', () => this.close());

            // Обработчик отправки
            document.getElementById('confirm-send-btn').addEventListener('click', () => this.send());

            // Переключение типа отчёта
            document.querySelectorAll('input[name="report-type"]').forEach(radio => {
                radio.addEventListener('change', (e) => {
                    const periodGroup = document.getElementById('email-period-group');
                    periodGroup.style.display = e.target.value === 'version_history' ? 'flex' : 'none';
                });
            });

            // Клавиша Escape
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.isOpen()) {
                    this.close();
                }
            });
        },

        open() {
            if (!this.modal) return;

            // Синхронизируем тип отчёта с активной вкладкой
            const reportType = state.activeTab === 'version-history' ? 'version_history' : 'current_versions';
            const radio = this.modal.querySelector(`input[name="report-type"][value="${reportType}"]`);
            if (radio) radio.checked = true;

            // Показываем/скрываем период
            const periodGroup = document.getElementById('email-period-group');
            periodGroup.style.display = reportType === 'version_history' ? 'flex' : 'none';

            // Копируем даты из основных фильтров
            if (state.filters.dateFrom) {
                document.getElementById('email-date-from').value = state.filters.dateFrom;
            }
            if (state.filters.dateTo) {
                document.getElementById('email-date-to').value = state.filters.dateTo;
            }

            // Очищаем сообщения
            this.hideError();
            this.hideSuccess();

            // Показываем модалку
            this.modal.style.display = 'flex';
            document.getElementById('email-recipients').focus();
        },

        close() {
            if (this.modal) {
                this.modal.style.display = 'none';
            }
        },

        isOpen() {
            return this.modal && this.modal.style.display === 'flex';
        },

        showError(message) {
            const errorEl = document.getElementById('email-error');
            errorEl.textContent = message;
            errorEl.style.display = 'block';
            document.getElementById('email-success').style.display = 'none';
        },

        hideError() {
            document.getElementById('email-error').style.display = 'none';
        },

        showSuccess(message) {
            const successEl = document.getElementById('email-success');
            successEl.textContent = message;
            successEl.style.display = 'block';
            document.getElementById('email-error').style.display = 'none';
        },

        hideSuccess() {
            document.getElementById('email-success').style.display = 'none';
        },

        setLoading(loading) {
            this.sending = loading;
            const btn = document.getElementById('confirm-send-btn');
            btn.disabled = loading;
            btn.textContent = loading ? 'Отправка...' : 'Отправить';
        },

        async send() {
            if (this.sending) return;

            // Получаем получателей
            const recipients = document.getElementById('email-recipients').value.trim();
            if (!recipients) {
                this.showError('Укажите хотя бы одного получателя');
                return;
            }

            // Получаем тип отчёта
            const reportType = this.modal.querySelector('input[name="report-type"]:checked').value;

            // Формируем данные для отправки
            const data = {
                report_type: reportType,
                recipients: recipients
            };

            // Добавляем фильтры если включено
            if (document.getElementById('email-use-filters').checked) {
                data.filters = {};
                if (state.filters.serverIds?.length) {
                    data.filters.server_ids = state.filters.serverIds;
                }
                if (state.filters.catalogIds?.length) {
                    data.filters.catalog_ids = state.filters.catalogIds;
                }
            }

            // Добавляем период для истории
            if (reportType === 'version_history') {
                const dateFrom = document.getElementById('email-date-from').value;
                const dateTo = document.getElementById('email-date-to').value;
                if (dateFrom || dateTo) {
                    data.period = {};
                    if (dateFrom) data.period.date_from = dateFrom;
                    if (dateTo) data.period.date_to = dateTo;
                }
            }

            this.setLoading(true);
            this.hideError();
            this.hideSuccess();

            try {
                const result = await API.sendReport(data);

                if (result.success) {
                    const count = result.details?.recipients_count || 0;
                    this.showSuccess(`Отчёт успешно отправлен ${count} получателям`);
                    // Закрываем через 2 секунды
                    setTimeout(() => this.close(), 2000);
                } else {
                    this.showError(result.error || 'Ошибка отправки отчёта');
                }
            } catch (error) {
                this.showError('Ошибка при отправке: ' + error.message);
            } finally {
                this.setLoading(false);
            }
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

        // Обработчик отправки по email
        const sendEmailBtn = document.getElementById('send-email-btn');
        if (sendEmailBtn) {
            sendEmailBtn.addEventListener('click', () => EmailModal.open());
        }

        // Инициализация модалки email
        EmailModal.init();

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

/**
 * Mapping Management - компонент для управления унифицированными маппингами
 */

class MappingsManagement {
    constructor() {
        this.mappings = [];
        this.stats = null;
        this.filters = {
            entityType: '',
            activeOnly: true
        };
        this.selectedEntityType = '';
        this.selectedEntityId = null;
        this.unmappedEntities = [];
        this.availableApplications = [];
    }

    /**
     * Инициализация компонента
     */
    init() {
        this.loadStats();
        this.loadMappings();
        this.setupEventHandlers();
    }

    /**
     * Загрузка статистики маппингов
     */
    async loadStats() {
        try {
            const response = await fetch('/api/mappings/stats');
            const data = await response.json();

            if (data.success) {
                this.stats = data.stats;
                this.renderStats();
            }
        } catch (error) {
            console.error('Error loading mapping stats:', error);
        }
    }

    /**
     * Загрузка списка маппингов
     */
    async loadMappings() {
        try {
            const params = new URLSearchParams();
            if (this.filters.entityType) {
                params.append('entity_type', this.filters.entityType);
            }
            params.append('active_only', this.filters.activeOnly);

            const response = await fetch(`/api/mappings?${params}`);
            const data = await response.json();

            if (data.success) {
                this.mappings = data.mappings;
                this.renderMappings();
            }
        } catch (error) {
            console.error('Error loading mappings:', error);
        }
    }

    /**
     * Отрисовка статистики
     */
    renderStats() {
        const container = document.getElementById('mappings-statistics');
        if (!container || !this.stats) return;

        container.innerHTML = `
            <div class="stat-item">
                <div class="stat-label">Всего маппингов</div>
                <div class="stat-value">${this.stats.total}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Активных</div>
                <div class="stat-value">${this.stats.active}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Ручных</div>
                <div class="stat-value">${this.stats.manual}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Автоматических</div>
                <div class="stat-value">${this.stats.automatic}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">HAProxy</div>
                <div class="stat-value">${this.stats.by_type?.haproxy_server?.active || 0}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Eureka</div>
                <div class="stat-value">${this.stats.by_type?.eureka_instance?.active || 0}</div>
            </div>
        `;
    }

    /**
     * Отрисовка списка маппингов
     */
    renderMappings() {
        const container = document.getElementById('mappings-list-container');
        if (!container) return;

        if (this.mappings.length === 0) {
            container.innerHTML = '<div class="info-loading">Нет маппингов</div>';
            return;
        }

        let html = '<div class="mappings-table-container"><table class="mappings-table"><thead><tr>';
        html += '<th>Приложение</th>';
        html += '<th>Тип</th>';
        html += '<th>ID сущности</th>';
        html += '<th>Маппинг</th>';
        html += '<th>Создан</th>';
        html += '<th>Действия</th>';
        html += '</tr></thead><tbody>';

        this.mappings.slice(0, 50).forEach(mapping => {
            const typeIcon = mapping.entity_type === 'haproxy_server' ? '🔄' : '🌐';
            const manualBadge = mapping.is_manual
                ? '<span class="badge badge-manual">Ручной</span>'
                : '<span class="badge badge-auto">Авто</span>';

            const appName = mapping.application?.instance_name || `ID: ${mapping.application_id}`;
            const mappedAt = mapping.mapped_at
                ? new Date(mapping.mapped_at).toLocaleDateString()
                : '-';

            html += `
                <tr class="${!mapping.is_active ? 'inactive' : ''}">
                    <td>${appName}</td>
                    <td>${typeIcon} ${mapping.entity_type}</td>
                    <td>${mapping.entity_id}</td>
                    <td>${manualBadge}</td>
                    <td>${mappedAt}</td>
                    <td>
                        <button class="btn-small btn-info" onclick="mappingsManagement.showHistory(${mapping.id})">
                            📋
                        </button>
                        ${mapping.is_active ? `
                            <button class="btn-small btn-danger" onclick="mappingsManagement.deactivateMapping(${mapping.id})">
                                ❌
                            </button>
                        ` : ''}
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table></div>';

        if (this.mappings.length > 50) {
            html += `<div class="mappings-more">Показано 50 из ${this.mappings.length} маппингов</div>`;
        }

        container.innerHTML = html;
    }

    /**
     * Настройка обработчиков событий
     */
    setupEventHandlers() {
        // Фильтр по типу
        const typeFilter = document.getElementById('mapping-type-filter');
        if (typeFilter) {
            typeFilter.addEventListener('change', (e) => {
                this.filters.entityType = e.target.value;
                this.loadMappings();
            });
        }

        // Фильтр по активности
        const activeFilter = document.getElementById('mapping-active-filter');
        if (activeFilter) {
            activeFilter.addEventListener('change', (e) => {
                this.filters.activeOnly = e.target.value === 'active';
                this.loadMappings();
            });
        }
    }

    /**
     * Запуск автоматического маппинга
     */
    async autoMap(entityType) {
        try {
            const btn = event.target;
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Выполняется...';

            const response = await fetch(`/api/mappings/auto-map?entity_type=${entityType}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                showNotification(`Автоматический маппинг выполнен: ${JSON.stringify(data.result)}`);
                this.loadStats();
                this.loadMappings();
            } else {
                showError(`Ошибка: ${data.error}`);
            }

            btn.disabled = false;
            btn.textContent = originalText;
        } catch (error) {
            console.error('Error during auto-mapping:', error);
            showError('Ошибка автоматического маппинга');
        }
    }

    /**
     * Показать историю маппинга
     */
    async showHistory(mappingId) {
        try {
            const response = await fetch(`/api/mappings/${mappingId}/history`);
            const data = await response.json();

            if (data.success) {
                this.renderHistoryModal(data.history);
            }
        } catch (error) {
            console.error('Error loading history:', error);
        }
    }

    /**
     * Отрисовка модального окна с историей
     */
    renderHistoryModal(history) {
        // Создаем модальное окно
        let modal = document.getElementById('mapping-history-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'mapping-history-modal';
            modal.className = 'modal-overlay';
            document.body.appendChild(modal);
        }

        let content = '<div class="modal-content"><h3>История маппинга</h3>';

        if (history.length === 0) {
            content += '<p>История пуста</p>';
        } else {
            content += '<div class="history-list">';
            history.forEach(item => {
                const date = new Date(item.changed_at).toLocaleString();
                content += `
                    <div class="history-item">
                        <div class="history-action">${item.action}</div>
                        <div class="history-date">${date}</div>
                        <div class="history-by">${item.changed_by || 'system'}</div>
                        ${item.reason ? `<div class="history-reason">${item.reason}</div>` : ''}
                    </div>
                `;
            });
            content += '</div>';
        }

        content += '<button class="action-btn" onclick="mappingsManagement.closeHistoryModal()">Закрыть</button>';
        content += '</div>';

        modal.innerHTML = content;
        modal.style.display = 'flex';
    }

    /**
     * Закрыть модальное окно истории
     */
    closeHistoryModal() {
        const modal = document.getElementById('mapping-history-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    /**
     * Деактивировать маппинг
     */
    async deactivateMapping(mappingId) {
        if (!confirm('Вы уверены, что хотите деактивировать этот маппинг?')) {
            return;
        }

        try {
            const response = await fetch(`/api/mappings/${mappingId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({is_active: false, mapped_by: 'user'})
            });
            const data = await response.json();

            if (data.success) {
                showNotification('Маппинг деактивирован');
                this.loadStats();
                this.loadMappings();
            } else {
                showError(`Ошибка: ${data.error}`);
            }
        } catch (error) {
            console.error('Error deactivating mapping:', error);
            showError('Ошибка деактивации маппинга');
        }
    }

    // ==================== Ручной маппинг ====================

    /**
     * Обработчик изменения типа сущности
     */
    async onEntityTypeChange() {
        const typeSelect = document.getElementById('manual-mapping-type');
        const entityGroup = document.getElementById('entity-select-group');
        const appGroup = document.getElementById('app-select-group');
        const notesGroup = document.getElementById('mapping-notes-group');
        const createBtn = document.getElementById('create-manual-mapping-btn');

        this.selectedEntityType = typeSelect.value;
        this.selectedEntityId = null;

        // Сброс и скрытие зависимых элементов
        appGroup.style.display = 'none';
        notesGroup.style.display = 'none';
        createBtn.style.display = 'none';

        if (!this.selectedEntityType) {
            entityGroup.style.display = 'none';
            return;
        }

        entityGroup.style.display = 'block';
        await this.loadUnmappedEntities();
    }

    /**
     * Загрузка несопоставленных сущностей
     */
    async loadUnmappedEntities() {
        const entitySelect = document.getElementById('manual-mapping-entity');
        entitySelect.innerHTML = '<option value="">Загрузка...</option>';

        try {
            let url;
            if (this.selectedEntityType === 'haproxy_server') {
                url = '/api/haproxy/servers/unmapped';
            } else if (this.selectedEntityType === 'eureka_instance') {
                url = '/api/eureka/instances/unmapped';
            } else {
                return;
            }

            const response = await fetch(url);
            const data = await response.json();

            if (data.success) {
                this.unmappedEntities = this.selectedEntityType === 'haproxy_server'
                    ? data.servers
                    : (data.instances || data.data);

                entitySelect.innerHTML = '<option value="">-- Выберите сущность --</option>';

                if (this.unmappedEntities.length === 0) {
                    entitySelect.innerHTML = '<option value="">Все сущности уже сопоставлены</option>';
                    return;
                }

                this.unmappedEntities.forEach(entity => {
                    const option = document.createElement('option');
                    option.value = entity.id;

                    if (this.selectedEntityType === 'haproxy_server') {
                        const backendName = entity.backend?.backend_name || entity.backend_name || '';
                        option.textContent = `${entity.server_name} (${entity.addr || 'no addr'}) - ${backendName}`;
                    } else {
                        option.textContent = `${entity.instance_id} (${entity.ip_address}:${entity.port})`;
                    }

                    entitySelect.appendChild(option);
                });
            } else {
                entitySelect.innerHTML = `<option value="">Ошибка: ${data.error}</option>`;
            }
        } catch (error) {
            console.error('Error loading unmapped entities:', error);
            entitySelect.innerHTML = '<option value="">Ошибка загрузки</option>';
        }
    }

    /**
     * Обработчик выбора сущности
     */
    async onEntitySelect() {
        const entitySelect = document.getElementById('manual-mapping-entity');
        const appGroup = document.getElementById('app-select-group');
        const notesGroup = document.getElementById('mapping-notes-group');
        const createBtn = document.getElementById('create-manual-mapping-btn');

        this.selectedEntityId = entitySelect.value ? parseInt(entitySelect.value) : null;

        if (!this.selectedEntityId) {
            appGroup.style.display = 'none';
            notesGroup.style.display = 'none';
            createBtn.style.display = 'none';
            return;
        }

        appGroup.style.display = 'block';
        notesGroup.style.display = 'block';
        await this.loadApplicationsForEntity();
    }

    /**
     * Загрузка приложений для выбранной сущности
     */
    async loadApplicationsForEntity() {
        const appSelect = document.getElementById('manual-mapping-app');
        const createBtn = document.getElementById('create-manual-mapping-btn');

        appSelect.innerHTML = '<option value="">Загрузка...</option>';
        createBtn.style.display = 'none';

        try {
            let url;
            if (this.selectedEntityType === 'haproxy_server') {
                url = `/api/haproxy/applications/search?server_id=${this.selectedEntityId}`;
            } else if (this.selectedEntityType === 'eureka_instance') {
                url = `/api/eureka/applications/search?instance_id=${this.selectedEntityId}`;
            } else {
                return;
            }

            const response = await fetch(url);
            const data = await response.json();

            if (data.success) {
                this.availableApplications = data.applications;

                appSelect.innerHTML = '<option value="">-- Выберите приложение --</option>';

                if (this.availableApplications.length === 0) {
                    appSelect.innerHTML = '<option value="">Нет доступных приложений</option>';
                    return;
                }

                this.availableApplications.forEach(app => {
                    const option = document.createElement('option');
                    option.value = app.id;
                    option.textContent = `${app.name} (${app.ip}:${app.port}) - ${app.server_name || 'unknown'}`;
                    appSelect.appendChild(option);
                });

                createBtn.style.display = 'block';
            } else {
                appSelect.innerHTML = `<option value="">Ошибка: ${data.error}</option>`;
            }
        } catch (error) {
            console.error('Error loading applications:', error);
            appSelect.innerHTML = '<option value="">Ошибка загрузки</option>';
        }
    }

    /**
     * Создание ручного маппинга
     */
    async createManualMapping() {
        const appSelect = document.getElementById('manual-mapping-app');
        const notesInput = document.getElementById('manual-mapping-notes');
        const createBtn = document.getElementById('create-manual-mapping-btn');

        const applicationId = appSelect.value ? parseInt(appSelect.value) : null;
        const notes = notesInput.value.trim();

        if (!applicationId) {
            showError('Выберите приложение для маппинга');
            return;
        }

        if (!this.selectedEntityId) {
            showError('Сущность не выбрана');
            return;
        }

        createBtn.disabled = true;
        createBtn.textContent = 'Создание...';

        try {
            let url;
            let body;

            if (this.selectedEntityType === 'haproxy_server') {
                url = `/api/haproxy/servers/${this.selectedEntityId}/map`;
                body = {
                    application_id: applicationId,
                    notes: notes
                };
            } else if (this.selectedEntityType === 'eureka_instance') {
                url = `/api/eureka/instances/${this.selectedEntityId}/map`;
                body = {
                    application_id: applicationId,
                    mapped_by: 'admin',
                    notes: notes
                };
            } else {
                showError('Неизвестный тип сущности');
                return;
            }

            const response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });

            const data = await response.json();

            if (data.success) {
                showNotification(data.message || 'Ручной маппинг создан успешно');

                // Сброс формы
                this.resetManualMappingForm();

                // Обновление данных
                this.loadStats();
                this.loadMappings();
            } else {
                showError(`Ошибка: ${data.error}`);
            }
        } catch (error) {
            console.error('Error creating manual mapping:', error);
            showError('Ошибка создания маппинга');
        } finally {
            createBtn.disabled = false;
            createBtn.textContent = '✅ Создать маппинг';
        }
    }

    /**
     * Сброс формы ручного маппинга
     */
    resetManualMappingForm() {
        document.getElementById('manual-mapping-type').value = '';
        document.getElementById('manual-mapping-entity').innerHTML = '<option value="">-- Выберите сущность --</option>';
        document.getElementById('manual-mapping-app').innerHTML = '<option value="">-- Выберите приложение --</option>';
        document.getElementById('manual-mapping-notes').value = '';

        document.getElementById('entity-select-group').style.display = 'none';
        document.getElementById('app-select-group').style.display = 'none';
        document.getElementById('mapping-notes-group').style.display = 'none';
        document.getElementById('create-manual-mapping-btn').style.display = 'none';

        this.selectedEntityType = '';
        this.selectedEntityId = null;
        this.unmappedEntities = [];
        this.availableApplications = [];
    }
}

// Глобальный экземпляр
window.mappingsManagement = new MappingsManagement();

/**
 * Faktura Apps - Управление приложениями
 *
 */

(function() {
    'use strict';

    // ========================================
    // КОНСТАНТЫ И КОНФИГУРАЦИЯ
    // ========================================    

    // Утилиты безопасности для предотвращения XSS
    const SecurityUtils = {
        escapeHtml(text) {
            if (text == null) return '';
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;',
                '/': '&#x2F;'
            };
            return String(text).replace(/[&<>"'\/]/g, char => map[char]);
        },
        
        createSafeElement(tag, attrs = {}, content = '') {
            const element = document.createElement(tag);
            
            Object.keys(attrs).forEach(key => {
                if (key === 'className') {
                    element.className = attrs.className;
                } else if (key === 'dataset') {
                    Object.assign(element.dataset, attrs.dataset);
                } else if (key === 'innerHTML' && attrs.trustHtml) {
                    element.innerHTML = attrs.innerHTML;
                } else {
                    element.setAttribute(key, attrs[key]);
                }
            });
            
            if (typeof content === 'string') {
                element.textContent = content;
            }
            
            return element;
        }
    };
    
    // Утилиты для работы с DOM
    const DOMUtils = {
        getTableContext() {
            return document.getElementById('applications-table-body');
        },
        
        querySelectorInTable(selector) {
            const tableBody = this.getTableContext();
            return tableBody ? tableBody.querySelectorAll(selector) : [];
        },
        
        getTableColumnCount() {
            const headers = document.querySelectorAll('#applications-table thead th');
            return headers.length || 6;
        },
        
        debounce(func, wait = 300) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }
    };    
   
    const CONFIG = {
        PROGRESS: {
            START: 10,
            FETCH_COMPLETE: 70,
            PARSE_COMPLETE: 100
        },
        CACHE_LIFETIME: 5 * 60 * 1000, // 5 минут
        ANIMATION_DELAYS: {
            FADE_IN: 100,
            FIELD_STAGGER: 100,
            MIN_LOADER_TIME: 600
        },
        MAX_ARTIFACTS_DISPLAY: 20,
        PAGE_SIZE: 10
    };

    // ========================================
    // МОДУЛЬ УПРАВЛЕНИЯ СОСТОЯНИЕМ
    // ========================================
    const StateManager = {
        // Основное состояние приложения
        state: {
            allApplications: [],
            selectedItems: {
                applications: new Set(),
                groups: new Set()
            },
            expandedGroups: [],
            selectedServerId: 'all',
            currentPage: 1,
            pageSize: CONFIG.PAGE_SIZE,
            sortColumn: 'name',
            sortDirection: 'asc',
            searchQuery: '',
            groupingEnabled: false,
            selectedTags: [],
            tagOperator: 'OR',
            availableTags: []
        },

        // Кэш артефактов
        artifactsCache: {},

        // Активное выпадающее меню
        activeDropdown: null,

        // Методы работы с состоянием
        clearSelection() {
            this.state.selectedItems.applications.clear();
            this.state.selectedItems.groups.clear();
        },

        addSelectedApp(appId) {
            this.state.selectedItems.applications.add(appId);
        },

        removeSelectedApp(appId) {
            this.state.selectedItems.applications.delete(appId);
        },

        isAppSelected(appId) {
            return this.state.selectedItems.applications.has(appId);
        },

        getSelectedAppIds() {
            return Array.from(this.state.selectedItems.applications);
        },

        getAppById(appId) {
            return this.state.allApplications.find(app => app.id == appId);
        },

        clearArtifactsCache(appId = null) {
            if (appId) {
                delete this.artifactsCache[`app_${appId}`];
            } else {
                this.artifactsCache = {};
            }
        },

        getArtifactsCacheAge(appId) {
            const cacheKey = `app_${appId}`;
            if (this.artifactsCache[cacheKey]) {
                return (Date.now() - this.artifactsCache[cacheKey].timestamp) / 1000;
            }
            return Infinity;
        },

        saveTableState() {
            this.state.expandedGroups = [];
            document.querySelectorAll('.group-row.expanded').forEach(row => {
                const groupName = row.getAttribute('data-group');
                if (groupName) {
                    this.state.expandedGroups.push(groupName);
                }
            });
        }
    };

    // ========================================
    // МОДУЛЬ РАБОТЫ С API
    // ========================================
    const ApiService = {
        async loadServers() {
            try {
                const response = await fetch('/api/servers');
                const data = await response.json();
                return data.success ? data.servers : [];
            } catch (error) {
                console.error('Ошибка загрузки серверов:', error);
                showError('Не удалось загрузить список серверов');
                return [];
            }
        },

        async loadApplications(serverId = null) {
            try {
                let url = '/api/applications';
                if (serverId && serverId !== 'all') {
                    url += `?server_id=${serverId}`;
                }
                const response = await fetch(url);
                const data = await response.json();
                return data.success ? data.applications : [];
            } catch (error) {
                console.error('Ошибка загрузки приложений:', error);
                showError('Не удалось загрузить список приложений');
                return [];
            }
        },

        async loadTags() {
            try {
                const response = await fetch('/api/tags');
                const data = await response.json();
                return data.success ? data.tags : [];
            } catch (error) {
                console.error('Ошибка загрузки тегов:', error);
                return [];
            }
        },

        async loadArtifacts(appId, limit = CONFIG.MAX_ARTIFACTS_DISPLAY, showProgress = false) {
            try {
                if (showProgress) {
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) {
                        progressBar.style.width = '30%';
                    }
                }

                const response = await fetch(`/api/applications/${appId}/artifacts?limit=${limit}`);
                
                if (showProgress) {
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) {
                        progressBar.style.width = '70%';
                    }
                }

                const data = await response.json();
                
                if (showProgress) {
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) {
                        progressBar.style.width = '100%';
                    }
                }

                if (data.success && data.versions && data.versions.length > 0) {
                    // Сортируем версии только по номеру (от большего к меньшему)
                    const sortedVersions = data.versions.sort((a, b) => {
                        // Функция для извлечения числовых частей версии
                        const extractVersion = (versionObj) => {
                            // Удаляем префиксы типа 'v' и суффиксы типа '-SNAPSHOT', '-dev'
                            const cleanVersion = versionObj.version
                                .replace(/^v/i, '')
                                .replace(/[-_](snapshot|dev|alpha|beta|rc).*$/i, '');
                            
                            // Разбиваем на числовые части
                            const parts = cleanVersion.split(/[.-]/).map(part => {
                                const num = parseInt(part, 10);
                                return isNaN(num) ? 0 : num;
                            });
                            
                            // Дополняем нулями до 4 частей для корректного сравнения
                            while (parts.length < 4) parts.push(0);
                            
                            return parts;
                        };
                        
                        const aParts = extractVersion(a);
                        const bParts = extractVersion(b);
                        
                        // Сравниваем по частям (от большего к меньшему)
                        for (let i = 0; i < 4; i++) {
                            if (bParts[i] !== aParts[i]) {
                                return bParts[i] - aParts[i];
                            }
                        }
                        
                        // Если версии одинаковые, release версии приоритетнее
                        if (a.is_release && !b.is_release) return -1;
                        if (!a.is_release && b.is_release) return 1;
                        
                        return 0;
                    });

                    return sortedVersions.slice(0, limit);
                }
                
                return null;
            } catch (error) {
                console.error('Ошибка загрузки артефактов:', error);
                return null;
            }
        },

        async executeAction(appIds, action) {
            try {
                const response = await fetch('/api/applications/batch_action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ app_ids: appIds, action })
                });
                return await response.json();
            } catch (error) {
                console.error('Ошибка выполнения действия:', error);
                showError(`Не удалось выполнить действие "${action}"`);
                return { success: false, error: error.message };
            }
        },

        async updateApplication(appId, updateParams) {
            try {
                const response = await fetch(`/api/applications/${appId}/update`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updateParams)
                });
                return await response.json();
            } catch (error) {
                console.error('Ошибка обновления приложения:', error);
                return { success: false, error: error.message };
            }
        },

        async getApplicationInfo(appId) {
            try {
                const response = await fetch(`/api/applications/${appId}`);
                const data = await response.json();
                return data.success ? data.application : null;
            } catch (error) {
                console.error('Ошибка получения информации:', error);
                showError('Не удалось получить информацию о приложении');
                return null;
            }
        },

        async loadOrchestrators(activeOnly = true) {
            try {
                const url = `/api/orchestrators${activeOnly ? '?active_only=true' : ''}`;
                const response = await fetch(url);
                const data = await response.json();
                return data.success ? data.orchestrators : [];
            } catch (error) {
                console.error('Ошибка загрузки оркестраторов:', error);
                showError('Не удалось загрузить список оркестраторов');
                return [];
            }
        }
    };

    // ========================================
    // МОДУЛЬ РАБОТЫ С АРТЕФАКТАМИ
    // ========================================
    const ArtifactsManager = {
        async loadWithCache(appId, showProgress = false) {
            const now = Date.now();
            const cacheKey = `app_${appId}`;
            const cache = StateManager.artifactsCache[cacheKey];

            // Проверяем кэш
            if (cache && (now - cache.timestamp) < CONFIG.CACHE_LIFETIME) {
                return cache.data;
            }

            // Загружаем свежие данные
            const artifacts = await ApiService.loadArtifacts(appId, CONFIG.MAX_ARTIFACTS_DISPLAY, showProgress);
            if (artifacts && artifacts.length > 0) {
                StateManager.artifactsCache[cacheKey] = {
                    timestamp: now,
                    data: artifacts
                };
                return artifacts;
            }

            return null;
        },

        createVersionSelect(artifacts, currentValue) {
            if (!artifacts || artifacts.length === 0) {
                return '<option value="">Нет доступных версий</option>';
            }

            const options = artifacts.map(version => {
                let label = version.version;
                let className = '';
                const versionLower = version.version.toLowerCase();

                if (versionLower.includes('snapshot')) {
                    className = 'version-snapshot';
                } else if (versionLower.includes('dev')) {
                    className = 'version-dev';
                } else if (version.is_release) {
                    className = 'version-release';
                }

                const selected = version.url === currentValue ? 'selected' : '';
                return `<option value="${version.url}" class="${className}" ${selected}>${label}</option>`;
            }).join('');

            return options + '<option value="custom" class="custom-option">➕ Указать вручную...</option>';
        }
    };

    // ========================================
    // МОДУЛЬ РАБОТЫ С UI
    // ========================================
    const UIRenderer = {
        elements: {
            applicationsTableBody: null,
            selectAllCheckbox: null,
            serverDropdown: null,
            searchInput: null,
            sortSelects: null,
            groupToggleBtn: null,
            actionButtons: {}
        },

        init() {
            this.elements.applicationsTableBody = document.getElementById('applications-table-body');
            this.elements.selectAllCheckbox = document.getElementById('select-all');
            this.elements.serverDropdown = document.getElementById('server-dropdown');
            this.elements.searchInput = document.getElementById('search-input');
            this.elements.groupToggleBtn = document.getElementById('group-toggle-btn');
            
            // Кнопки действий
            this.elements.actionButtons = {
                start: document.getElementById('start-btn'),
                restart: document.getElementById('restart-btn'),
                stop: document.getElementById('stop-btn'),
                update: document.getElementById('update-btn'),
                unload: document.getElementById('unload-btn')
            };
        },

        renderServers(servers) {
            const serverList = document.getElementById('server-list');
            if (!serverList) return;

            serverList.innerHTML = '<li data-server-id="all">Все серверы</li>';
            servers.forEach(server => {
                const li = document.createElement('li');
                li.setAttribute('data-server-id', server.id);
                li.textContent = server.name;
                serverList.appendChild(li);
            });
        },

        renderApplications(applications) {
            const tbody = this.elements.applicationsTableBody;
            if (!tbody) return;

            // Сохраняем состояние перед обновлением
            StateManager.saveTableState();

            tbody.innerHTML = '';
            
            if (applications.length === 0) {
                const colspan = DOMUtils.getTableColumnCount();
                tbody.innerHTML = `<tr><td colspan="${colspan}" class="table-loading">Нет приложений</td></tr>`;
                this.updatePagination(0);
                return;
            }

            if (StateManager.state.groupingEnabled) {
                this.renderGroupedApplications(applications);
            } else {
                this.renderFlatApplications(applications);
            }

            // Восстанавливаем состояние после рендеринга
            this.restoreTableState();
            this.setupTableEventHandlers();
            this.restoreCheckboxState();
            
            // Обновляем состояние "выбрать все" после рендеринга
            this.updateSelectAllState();
        },

        renderFlatApplications(applications) {
            const totalPages = Math.ceil(applications.length / StateManager.state.pageSize);
            
            // Корректируем текущую страницу если она выходит за пределы
            if (StateManager.state.currentPage > totalPages && totalPages > 0) {
                StateManager.state.currentPage = totalPages;
            }
            
            const paginatedApps = this.paginateData(applications);
            paginatedApps.forEach(app => {
                const row = this.createApplicationRow(app, false);
                if (row && this.elements.applicationsTableBody) {
                    this.elements.applicationsTableBody.appendChild(row);
                }
            });
            this.updatePagination(applications.length);
        },

        renderGroupedApplications(applications) {
            const groups = this.groupApplications(applications);
            const totalPages = Math.ceil(groups.length / StateManager.state.pageSize);
            
            // Корректируем текущую страницу если она выходит за пределы
            if (StateManager.state.currentPage > totalPages && totalPages > 0) {
                StateManager.state.currentPage = totalPages;
            }
            
            const paginatedGroups = this.paginateData(groups);

            paginatedGroups.forEach(group => {
                this.renderApplicationGroup(group);
            });

            this.updatePagination(groups.length);
        },

        renderApplicationGroup(group) {
            const tbody = this.elements.applicationsTableBody;
            if (!tbody) return;
            
            // Создаем строку группы
            const groupRow = this.createGroupRow(group.name, group.apps);
            tbody.appendChild(groupRow);

            // Создаем контейнер для дочерних элементов
            const wrapperRow = document.createElement('tr');
            wrapperRow.className = 'child-wrapper';
            wrapperRow.setAttribute('data-group', group.name);
            
            // По умолчанию скрываем дочерние элементы
            wrapperRow.style.display = 'none';

            const wrapperCell = document.createElement('td');
            wrapperCell.setAttribute('colspan', '6');

            const childContainer = document.createElement('div');
            childContainer.className = 'child-container';

            const childTable = document.createElement('table');
            childTable.className = 'child-table';

            const childTableBody = document.createElement('tbody');
            
            // Добавляем приложения группы
            group.apps.forEach(app => {
                const childRow = this.createChildApplicationRow(app, group.name);
                childTableBody.appendChild(childRow);
            });

            childTable.appendChild(childTableBody);
            childContainer.appendChild(childTable);
            wrapperCell.appendChild(childContainer);
            wrapperRow.appendChild(wrapperCell);
            tbody.appendChild(wrapperRow);
        },

        // Рендеринг тегов с унаследованными
        renderTagsWithInherited(ownTags, groupTags) {
            const allTags = [];
            const ownTagIds = new Set((ownTags || []).map(t => t.id));

            // Добавляем собственные теги
            (ownTags || []).forEach(tag => {
                allTags.push({ ...tag, inherited: false });
            });

            // Добавляем унаследованные теги (если их нет в собственных)
            (groupTags || []).forEach(tag => {
                if (!ownTagIds.has(tag.id)) {
                    allTags.push({ ...tag, inherited: true });
                }
            });

            if (allTags.length === 0) {
                return '<span class="no-tags">—</span>';
            }

            const container = document.createElement('div');
            container.className = 'table-tags-container';

            const maxVisible = 3;
            const visibleTags = allTags.slice(0, maxVisible);
            const hiddenCount = allTags.length - maxVisible;

            visibleTags.forEach(tag => {
                const span = document.createElement('span');
                span.className = `tag ${tag.css_class || ''}${tag.inherited ? ' tag-inherited' : ''}`;
                span.title = tag.inherited ? 'Унаследован от группы' : '';

                const icon = document.createElement('span');
                icon.className = 'tag-icon';
                icon.textContent = tag.icon || '';

                const text = document.createTextNode(' ' + (tag.display_name || tag.name));

                span.appendChild(icon);
                span.appendChild(text);
                container.appendChild(span);
            });

            if (hiddenCount > 0) {
                const more = document.createElement('span');
                more.className = 'tags-more';
                more.textContent = `+${hiddenCount}`;
                more.title = allTags.slice(maxVisible).map(t => t.display_name || t.name).join(', ');
                more.setAttribute('onclick', 'event.stopPropagation()');
                container.appendChild(more);
            }

            return container.outerHTML;
        },

        // Рендеринг тегов
        renderTags(tags) {
            if (!tags || tags.length === 0) {
                return '<span class="no-tags">—</span>';
            }

            const container = document.createElement('div');
            container.className = 'table-tags-container';

            const maxVisible = 3;
            const visibleTags = tags.slice(0, maxVisible);
            const hiddenCount = tags.length - maxVisible;

            visibleTags.forEach(tag => {
                const span = document.createElement('span');
                span.className = `tag ${tag.css_class || ''}`;

                const icon = document.createElement('span');
                icon.className = 'tag-icon';
                icon.textContent = tag.icon || '';

                const text = document.createTextNode(' ' + (tag.display_name || tag.name));

                span.appendChild(icon);
                span.appendChild(text);
                container.appendChild(span);
            });

            if (hiddenCount > 0) {
                const more = document.createElement('span');
                more.className = 'tags-more';
                more.textContent = `+${hiddenCount}`;
                more.title = tags.slice(maxVisible).map(t => t.display_name || t.name).join(', ');
                more.setAttribute('onclick', 'event.stopPropagation()');
                container.appendChild(more);
            }

            return container.outerHTML;
        },

        createApplicationRow(app, isChild) {
            const row = document.createElement('tr');
            row.className = isChild ? 'app-row child-row' : 'app-row';
            row.setAttribute('data-app-id', app.id);
            row.setAttribute('data-app-name', (app.name || '').toLowerCase());

            // Создаем ячейки безопасно

            // 1. Чекбокс
            const checkboxTd = document.createElement('td');
            const checkboxContainer = document.createElement('div');
            checkboxContainer.className = 'checkbox-container';

            const checkboxLabel = document.createElement('label');
            checkboxLabel.className = 'custom-checkbox';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'app-checkbox';
            checkbox.setAttribute('data-app-id', app.id);

            const checkmark = document.createElement('span');
            checkmark.className = 'checkmark';

            checkboxLabel.appendChild(checkbox);
            checkboxLabel.appendChild(checkmark);
            checkboxContainer.appendChild(checkboxLabel);
            checkboxTd.appendChild(checkboxContainer);

            // 2. Имя сервиса
            const nameTd = document.createElement('td');
            nameTd.className = isChild ? 'service-name child-indent' : 'service-name';

            const nameText = document.createTextNode(app.name || '');
            nameTd.appendChild(nameText);

            const details = document.createElement('div');
            details.className = 'dist-details';

            const startTimeDiv = document.createElement('div');
            startTimeDiv.textContent = `Время запуска: ${app.start_time ? new Date(app.start_time).toLocaleString() : 'Н/Д'}`;

            const pathDiv = document.createElement('div');
            pathDiv.textContent = `Путь приложения: ${app.path || 'Н/Д'}`;

            details.appendChild(startTimeDiv);
            details.appendChild(pathDiv);
            nameTd.appendChild(details);

            // 3. Теги (свои + унаследованные от группы)
            const tagsTd = document.createElement('td');
            tagsTd.innerHTML = this.renderTagsWithInherited(app.tags || [], app.group_tags || []);

            // 4. Версия (безопасно через textContent)
            const versionTd = document.createElement('td');
            versionTd.textContent = app.version || 'Н/Д';

            // 5. Статус (иконка безопасна, текст через textContent)
            const statusTd = document.createElement('td');
            const statusDot = document.createElement('span');

            let statusText;
            if (app.status === 'no_data' || app.status === 'unknown') {
                statusDot.className = 'service-dot no-data';
                statusText = 'Н/Д';
            } else if (app.status === 'online') {
                statusDot.className = 'service-dot';
                statusText = app.status;
            } else {
                statusDot.className = 'service-dot offline';
                statusText = app.status || 'offline';
            }

            statusTd.appendChild(statusDot);
            const statusTextNode = document.createTextNode(` ${statusText}`);
            statusTd.appendChild(statusTextNode);

            // 6. Сервер (безопасно через textContent)
            const serverTd = document.createElement('td');
            serverTd.textContent = app.server_name || 'Н/Д';

            // 7. Действия (временно используем innerHTML для меню, но без пользовательских данных)
            const actionsTd = document.createElement('td');
            // createActionsMenu должен возвращать безопасный HTML без пользовательских данных
            actionsTd.innerHTML = this.createActionsMenu(app);

            // Собираем строку
            row.appendChild(checkboxTd);
            row.appendChild(nameTd);
            row.appendChild(tagsTd);
            row.appendChild(versionTd);
            row.appendChild(statusTd);
            row.appendChild(serverTd);
            row.appendChild(actionsTd);

            return row;
        },

        createGroupRow(groupName, apps) {
            const row = document.createElement('tr');
            row.className = 'group-row';
            row.setAttribute('data-group', groupName);

            // Безопасное создание ячеек
            // Чекбокс
            const checkboxTd = document.createElement('td');
            const checkboxContainer = SecurityUtils.createSafeElement('div', {className: 'checkbox-container'});
            const checkboxLabel = SecurityUtils.createSafeElement('label', {className: 'custom-checkbox'});
            const checkbox = SecurityUtils.createSafeElement('input', {
                type: 'checkbox',
                className: 'group-checkbox',
                dataset: {group: groupName}
            });
            const checkmark = SecurityUtils.createSafeElement('span', {className: 'checkmark'});
            checkboxLabel.appendChild(checkbox);
            checkboxLabel.appendChild(checkmark);
            checkboxContainer.appendChild(checkboxLabel);
            checkboxTd.appendChild(checkboxContainer);

            // Имя группы
            const nameTd = document.createElement('td');
            nameTd.className = 'service-name';
            const nameContainer = SecurityUtils.createSafeElement('div', {className: 'group-name-container'});
            const toggle = SecurityUtils.createSafeElement('span', {
                className: 'group-toggle',
                innerHTML: '▶',
                trustHtml: true
            });
            const nameSpan = document.createElement('span');
            nameSpan.className = 'group-name';
            nameSpan.textContent = `${groupName} (${apps.length})`;
            nameContainer.appendChild(toggle);
            nameContainer.appendChild(nameSpan);
            nameTd.appendChild(nameContainer);

            // Теги группы (берем из первого приложения, т.к. они одинаковые для всей группы)
            const tagsTd = document.createElement('td');
            const groupTags = apps[0]?.group_tags || [];
            tagsTd.innerHTML = this.renderTags(groupTags);

            // Версии
            const versionTd = document.createElement('td');
            const versions = new Set(apps.map(app => app.version || 'Н/Д'));
            if (versions.size === 1) {
                versionTd.textContent = apps[0].version || 'Н/Д';
            } else {
                versionTd.innerHTML = '<span class="version-different">*</span>';
            }

            // Статус
            const statusTd = document.createElement('td');
            const hasOffline = apps.some(app => app.status === 'offline');
            const hasNoData = apps.some(app => app.status === 'no_data' || app.status === 'unknown');
            const hasProblems = hasOffline || hasNoData;

            const statusDot = SecurityUtils.createSafeElement('span', {
                className: hasProblems ? 'service-dot warning' : 'service-dot'  // warning для оранжевой точки
            });
            statusTd.appendChild(statusDot);

            // Сервер
            const serverTd = document.createElement('td');
            serverTd.textContent = '—';

            // Действия
            const actionsTd = document.createElement('td');
            actionsTd.innerHTML = this.createGroupActionsMenu(groupName, apps);

            // Собираем строку
            row.appendChild(checkboxTd);
            row.appendChild(nameTd);
            row.appendChild(tagsTd);
            row.appendChild(versionTd);
            row.appendChild(statusTd);
            row.appendChild(serverTd);
            row.appendChild(actionsTd);

            return row;
        },

        createChildApplicationRow(app, groupName) {
            const row = document.createElement('tr');
            row.className = 'app-child-row';
            row.setAttribute('data-app-id', app.id);
            row.setAttribute('data-parent', groupName);

            // ОБНОВЛЯЕМ только логику определения statusDot
            let statusDot, statusText;
            if (app.status === 'no_data' || app.status === 'unknown') {
                statusDot = '<span class="service-dot no-data"></span>';
                statusText = 'Н/Д';
            } else if (app.status === 'online') {
                statusDot = '<span class="service-dot"></span>';
                statusText = app.status;
            } else {
                statusDot = '<span class="service-dot offline"></span>';
                statusText = app.status || 'offline';
            }

            row.innerHTML = `
                <td>
                    <div class="checkbox-container">
                        <label class="custom-checkbox">
                            <input type="checkbox" class="app-checkbox" data-app-id="${app.id}">
                            <span class="checkmark"></span>
                        </label>
                    </div>
                </td>
                <td class="service-name">
                    ${app.name}
                    <div class="dist-details">
                        <div>Время запуска: ${app.start_time ? new Date(app.start_time).toLocaleString() : 'Н/Д'}</div>
                        <div>Путь приложения: ${app.path || 'Н/Д'}</div>
                    </div>
                </td>
                <td>${this.renderTagsWithInherited(app.tags || [], app.group_tags || [])}</td>
                <td>${app.version || 'Н/Д'}</td>
                <td>${statusDot} ${statusText}</td>
                <td>${app.server_name || 'Н/Д'}</td>
                <td>${this.createActionsMenu(app)}</td>
            `;

            return row;
        },

        createActionsMenu(app) {
            const appId = parseInt(app.id, 10); // Дополнительная защита - приводим к числу
            
            return `
                <div class="actions-menu">
                    <button class="actions-button">...</button>
                    <div class="actions-dropdown">
                        <a href="#" class="app-info-btn" data-app-id="${appId}">Информация</a>
                        <a href="#" class="app-start-btn ${app.status === 'online' ? 'disabled' : ''}" data-app-id="${appId}">Запустить</a>
                        <a href="#" class="app-stop-btn ${app.status !== 'online' ? 'disabled' : ''}" data-app-id="${appId}">Остановить</a>
                        <a href="#" class="app-restart-btn ${app.status !== 'online' ? 'disabled' : ''}" data-app-id="${appId}">Перезапустить</a>
                        <a href="#" class="app-update-btn" data-app-id="${appId}">Обновить</a>
                    </div>
                </div>
            `;
        },

        createGroupActionsMenu(groupName, apps) {
            const hasOnline = apps.some(app => app.status === 'online');
            const hasOffline = apps.some(app => app.status !== 'online');
            
            return `
                <div class="actions-menu">
                    <button class="actions-button">...</button>
                    <div class="actions-dropdown">
                        <a href="#" class="group-info-btn" data-group="${groupName}">Информация</a>
                        <a href="#" class="group-start-btn ${!hasOffline ? 'disabled' : ''}" data-group="${groupName}">Запустить все</a>
                        <a href="#" class="group-stop-btn ${!hasOnline ? 'disabled' : ''}" data-group="${groupName}">Остановить все</a>
                        <a href="#" class="group-restart-btn ${!hasOnline ? 'disabled' : ''}" data-group="${groupName}">Перезапустить все</a>
                        <a href="#" class="group-update-btn" data-group="${groupName}">Обновить все</a>
                    </div>
                </div>
            `;
        },

        groupApplications(applications) {
            const groups = {};
            applications.forEach(app => {
                const groupName = app.group_name || app.name;
                if (!groups[groupName]) {
                    groups[groupName] = { name: groupName, apps: [] };
                }
                groups[groupName].apps.push(app);
            });
            return Object.values(groups).sort((a, b) => a.name.localeCompare(b.name));
        },

        paginateData(data) {
            const { currentPage, pageSize } = StateManager.state;
            const startIndex = (currentPage - 1) * pageSize;
            const endIndex = startIndex + pageSize;
            return data.slice(startIndex, endIndex);
        },

        // обработка пагинации
        updatePagination(totalItems) {
            const totalPages = Math.ceil(totalItems / StateManager.state.pageSize);
            const paginationControls = document.getElementById('pagination-controls');
            if (!paginationControls) return;

            const { currentPage } = StateManager.state;
                    
            // Обновляем номер текущей страницы
            const pageNumberElement = paginationControls.querySelector('.page-number');
            if (pageNumberElement) {
                pageNumberElement.textContent = totalPages > 0 ? currentPage : '0';
            }
            
            // Обновляем состояние кнопок (только disabled, не обработчики!)
            const prevButton = paginationControls.querySelector('.prev-page');
            const nextButton = paginationControls.querySelector('.next-page');
            
            if (prevButton) {
                prevButton.disabled = currentPage <= 1 || totalPages === 0;
            }
            
            if (nextButton) {
                nextButton.disabled = currentPage >= totalPages || totalPages === 0;
            }
            
            // Сохраняем информацию о страницах в data-атрибутах для отладки
            if (paginationControls) {
                paginationControls.setAttribute('data-current-page', currentPage);
                paginationControls.setAttribute('data-total-pages', totalPages);
                paginationControls.setAttribute('data-total-items', totalItems);
            }
        },

        updateActionButtonsState(hasSelection) {
            const actionButtons = {
                start: document.getElementById('start-btn'),
                restart: document.getElementById('restart-btn'),
                stop: document.getElementById('stop-btn'),
                update: document.getElementById('update-btn'),
                unload: document.getElementById('unload-btn')
            };
            
            Object.values(actionButtons).forEach(btn => {
                if (!btn) return;
                btn.disabled = !hasSelection;
                btn.classList.toggle('disabled', !hasSelection);
            });
        },

        setupTableEventHandlers() {
            // Обработчики для строк приложений - раскрытие деталей
            document.querySelectorAll('.app-row').forEach(row => {
                row.addEventListener('click', function(e) {
                    if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                        return;
                    }
                    this.classList.toggle('expanded');
                });
            });

            // Обработчики для дочерних строк приложений в группах
            document.querySelectorAll('.app-child-row').forEach(row => {
                row.addEventListener('click', function(e) {
                    if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                        return;
                    }
                    this.classList.toggle('expanded');
                });
            });

            // Обработчики для строк групп - раскрытие/сворачивание
            document.querySelectorAll('.group-row').forEach(row => {
                row.addEventListener('click', function(e) {
                    if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                        return;
                    }
                    
                    const groupName = this.getAttribute('data-group');
                    const toggle = this.querySelector('.group-toggle');
                    const wrapperRow = document.querySelector(`.child-wrapper[data-group="${groupName}"]`);
                    
                    if (this.classList.contains('expanded')) {
                        // Сворачиваем
                        this.classList.remove('expanded');
                        if (toggle) {
                            toggle.style.transform = 'rotate(0deg)';
                        }
                        if (wrapperRow) {
                            wrapperRow.style.display = 'none';
                        }
                    } else {
                        // Раскрываем
                        this.classList.add('expanded');
                        if (toggle) {
                            toggle.style.transform = 'rotate(90deg)';
                        }
                        if (wrapperRow) {
                            wrapperRow.style.display = 'table-row';
                        }
                    }
                });
            });
        },

        restoreTableState() {
            // Восстанавливаем развернутые группы
            StateManager.state.expandedGroups.forEach(groupName => {
                const groupRow = document.querySelector(`.group-row[data-group="${groupName}"]`);
                const childWrapper = document.querySelector(`.child-wrapper[data-group="${groupName}"]`);
                const groupToggle = groupRow?.querySelector('.group-toggle');
                
                if (groupRow && childWrapper) {
                    groupRow.classList.add('expanded');
                    childWrapper.style.display = 'table-row';
                    if (groupToggle) {
                        groupToggle.style.transform = 'rotate(90deg)';
                    }
                }
            });
        },

        restoreCheckboxState() {
            StateManager.state.selectedItems.applications.forEach(appId => {
                const checkbox = document.querySelector(`.app-checkbox[data-app-id="${appId}"]`);
                if (checkbox) {
                    checkbox.checked = true;
                }
            });
            
            // Обновляем групповые чекбоксы
            document.querySelectorAll('.group-checkbox').forEach(groupCheckbox => {
                const groupName = groupCheckbox.dataset.group;
                this.updateGroupCheckbox(groupName);
            });
            
            // Обновляем состояние "выбрать все"
            this.updateSelectAllState();
            
            const hasSelection = StateManager.state.selectedItems.applications.size > 0;
            this.updateActionButtonsState(hasSelection);
        },

        updateGroupCheckbox(groupName) {
            const groupCheckbox = document.querySelector(`.group-checkbox[data-group="${groupName}"]`);
            if (!groupCheckbox) return;
            
            const childCheckboxes = document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`);
            const checkedCount = Array.from(childCheckboxes).filter(cb => cb.checked).length;
            
            if (checkedCount === 0) {
                groupCheckbox.checked = false;
                groupCheckbox.indeterminate = false;
            } else if (checkedCount === childCheckboxes.length) {
                groupCheckbox.checked = true;
                groupCheckbox.indeterminate = false;
            } else {
                groupCheckbox.checked = false;
                groupCheckbox.indeterminate = true;
            }
        },

        updateSelectAllState() {
            const selectAllCheckbox = document.getElementById('select-all');
            if (!selectAllCheckbox) return;
            
            // Используем контекст таблицы вместо всего документа
            const allCheckboxes = DOMUtils.querySelectorInTable('.app-checkbox');
            const checkedCheckboxes = DOMUtils.querySelectorInTable('.app-checkbox:checked');
            
            if (checkedCheckboxes.length === 0) {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = false;
            } else if (checkedCheckboxes.length === allCheckboxes.length) {
                selectAllCheckbox.checked = true;
                selectAllCheckbox.indeterminate = false;
            } else {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = true;
            }
        }     
    };

    // ========================================
    // МОДУЛЬ МОДАЛЬНЫХ ОКОН
    // ========================================
    const ModalManager = {
        // Кэш содержимого групп
        groupContentCache: {},
        groupContentLoaded: {},

        showUpdateModal(appIds) {
            if (!appIds || appIds.length === 0) {
                showError('Не выбрано ни одного приложения');
                return;
            }

            // Группируем приложения
            const appGroups = {};
            appIds.forEach(appId => {
                const app = StateManager.getAppById(appId);
                if (app) {
                    const groupName = app.group_name || app.name;
                    if (!appGroups[groupName]) {
                        appGroups[groupName] = [];
                    }
                    appGroups[groupName].push(app);
                }
            });

            // Определяем тип модального окна
            if (Object.keys(appGroups).length === 1) {
                const groupName = Object.keys(appGroups)[0];
                const apps = appGroups[groupName];
                this.showSimpleUpdateModal(apps, apps.length === 1 ? 
                    `Обновление приложения: ${apps[0].name}` : 
                    `Обновление группы: ${groupName}`);
            } else {
                this.showTabsUpdateModal(appGroups, `Обновление ${appIds.length} приложений`);
            }
        },

        async showSimpleUpdateModal(apps, title) {
            const appIds = apps.map(app => app.id);
            const firstApp = apps[0];

            // Создаем содержимое модального окна с анимированным загрузчиком
            const modalContent = document.createElement('div');
            modalContent.className = 'update-modal-content';

            // Загружаем оркестраторы
            const orchestrators = await ApiService.loadOrchestrators(true);

            // Функция для извлечения имени плейбука - всегда используем имя файла
            const getPlaybookDisplayName = (orch) => {
                // Извлекаем имя файла из пути
                const fileName = orch.file_path.split('/').pop();
                // Убираем расширение (.yml, .yaml)
                return fileName.replace(/\.(yml|yaml)$/i, '');
            };

            modalContent.innerHTML = `
                <form id="update-form" class="modal-form">
                    <input type="hidden" name="app_ids" value="${appIds.join(',')}">
                    <input type="hidden" id="current-app-id" value="${firstApp.id}">

                    <div class="artifact-loading-container">
                        <label>Версия дистрибутива:</label>
                        <div class="artifact-loader">
                            <div class="skeleton-select">
                                <div class="skeleton-text">Загрузка списка версий...</div>
                                <div class="skeleton-arrow">▼</div>
                            </div>
                            <div class="loading-spinner">
                                <div class="spinner-ring"></div>
                            </div>
                            <div class="loading-progress">
                                <div class="progress-bar"></div>
                            </div>
                        </div>
                    </div>

                    <div class="form-group" id="custom-url-group" style="display: none;">
                        <label for="custom-distr-url">URL дистрибутива:</label>
                        <input type="text" id="custom-distr-url" name="custom_distr_url" class="form-control">
                    </div>

                    <div class="form-group">
                        <label>Режим обновления:</label>
                        <div class="radio-group">
                            <label class="radio-label">
                                <input type="radio" name="mode" value="deliver" checked> Доставить
                            </label>
                            <label class="radio-label">
                                <input type="radio" name="mode" value="immediate"> Сейчас
                            </label>
                            <label class="radio-label">
                                <input type="radio" name="mode" value="night-restart"> В рестарт
                            </label>
                        </div>
                    </div>

                    <div id="immediate-mode-fields" style="display: none;">
                        <div class="form-group">
                            <label for="orchestrator-playbook">Orchestrator playbook:</label>
                            <select id="orchestrator-playbook" name="orchestrator_playbook" class="form-control">
                                <option value="none" ${orchestrators.length === 0 ? 'selected' : ''}>Без оркестрации</option>
                                ${orchestrators.length > 0 ?
                                    orchestrators.map((orch, index) => {
                                        const displayName = getPlaybookDisplayName(orch);
                                        const selected = index === 0 ? 'selected' : '';
                                        return `<option value="${orch.file_path}" ${selected}>${displayName}</option>`;
                                    }).join('') :
                                    ''
                                }
                            </select>
                        </div>

                        <div class="form-group">
                            <label for="drain-wait-time">Время ожидания после drain:</label>
                            <div class="drain-wait-container">
                                <input type="number" id="drain-wait-time" name="drain_wait_time"
                                       class="form-control" min="0" max="60" value="5">
                                <span class="unit-label">минут</span>
                            </div>
                            <div class="quick-select-buttons">
                                <a href="#" class="quick-time-link" data-time="10">10</a>
                                <a href="#" class="quick-time-link" data-time="20">20</a>
                                <a href="#" class="quick-time-link" data-time="30">30</a>
                            </div>
                            <small class="form-help-text">Время ожидания после вывода инстанса из балансировки (0-60 минут)</small>
                        </div>
                    </div>

                    <div class="form-actions">
                        <button type="button" class="cancel-btn" onclick="closeModal()">Отмена</button>
                        <button type="submit" class="submit-btn">Обновить</button>
                    </div>
                </form>
            `;

            // Показываем модальное окно
            window.showModal(title, modalContent);

            // Обработчики для режимов обновления
            const modeRadios = document.querySelectorAll('input[name="mode"]');
            const immediateModeFields = document.getElementById('immediate-mode-fields');

            modeRadios.forEach(radio => {
                radio.addEventListener('change', function() {
                    if (this.value === 'immediate') {
                        immediateModeFields.style.display = 'block';
                        immediateModeFields.classList.add('animated-slide-down');
                    } else {
                        immediateModeFields.style.display = 'none';
                    }
                });
            });

            // Обработчики для ссылок быстрого выбора времени
            document.querySelectorAll('.quick-time-link').forEach(link => {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    const time = this.dataset.time;
                    document.getElementById('drain-wait-time').value = time;

                    // Визуальная обратная связь
                    document.querySelectorAll('.quick-time-link').forEach(l => l.classList.remove('active'));
                    this.classList.add('active');
                });
            });

            // Загружаем артефакты с анимацией
            setTimeout(async () => {
                const startTime = Date.now();
                const artifacts = await ArtifactsManager.loadWithCache(firstApp.id, true);

                // Минимальное время показа загрузчика
                const elapsedTime = Date.now() - startTime;
                if (elapsedTime < 800) {
                    await new Promise(resolve => setTimeout(resolve, 800 - elapsedTime));
                }

                this.updateVersionSelector(artifacts, firstApp.distr_path, firstApp.id);
            }, 100);

            // Обработчик отправки формы
            document.getElementById('update-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                await this.processUpdateForm(formData);
            });
        },

        async showTabsUpdateModal(appGroups, title) {
            const modalContent = document.createElement('div');

            // Загружаем оркестраторы заранее
            const orchestrators = await ApiService.loadOrchestrators(true);

            // Создаем вкладки
            const tabsContainer = document.createElement('div');
            tabsContainer.className = 'modal-tabs';

            const form = document.createElement('form');
            form.id = 'update-form';
            form.className = 'modal-form';

            const dynamicContent = document.createElement('div');
            dynamicContent.id = 'dynamic-group-content';

            // Состояния групп
            const groupStates = {};
            const groupArtifacts = {};
            const excludedGroups = new Set(); // Исключенные группы

            // Очищаем кэши при открытии нового модального окна
            this.groupContentCache = {};
            this.groupContentLoaded = {};

            // Функция создания вкладки
            const createTab = (groupName, index, isActive) => {
                const tab = document.createElement('div');
                tab.className = `modal-tab ${isActive ? 'active' : ''}`;
                tab.setAttribute('data-group', groupName);
                
                const tabContent = document.createElement('span');
                tabContent.className = 'tab-content';
                tabContent.innerHTML = `${groupName} <span class="app-count">(${appGroups[groupName].length})</span>`;
                tab.appendChild(tabContent);
                
                // Кнопка удаления группы
                const removeBtn = document.createElement('button');
                removeBtn.className = 'tab-remove-btn';
                removeBtn.innerHTML = '×';
                removeBtn.title = 'Исключить группу из обновления';
                removeBtn.onclick = (e) => {
                    e.stopPropagation();
                    
                    // Добавляем в исключенные
                    excludedGroups.add(groupName);
                    
                    // Удаляем вкладку
                    tab.remove();
                    
                    // Проверяем оставшиеся вкладки
                    const remainingTabs = tabsContainer.querySelectorAll('.modal-tab');
                    
                    if (remainingTabs.length === 0) {
                        // Если вкладок не осталось, закрываем модальное окно
                        closeModal();
                    } else if (tab.classList.contains('active')) {
                        // Если это была активная вкладка, переключаемся на первую оставшуюся
                        remainingTabs[0].click();
                    }
                    
                    // Удаляем из состояний
                    delete groupStates[groupName];
                    delete groupArtifacts[groupName];
                    delete this.groupContentCache[groupName];
                    delete this.groupContentLoaded[groupName];
                };
                tab.appendChild(removeBtn);
                
                return tab;
            };
            
            // Создаем вкладки для каждой группы
            Object.keys(appGroups).forEach((groupName, index) => {
                const tab = createTab(groupName, index, index === 0);
                tabsContainer.appendChild(tab);
                
                const apps = appGroups[groupName];
                const firstApp = apps[0];
                
                
                groupStates[groupName] = {
                    appIds: apps.map(app => app.id),
                    distrUrl: firstApp?.distr_path || '',
                    restartMode: 'deliver',
                    artifactsLoaded: false,
                    customUrl: '',
                    isCustom: false,
                    orchestratorPlaybook: orchestrators.length > 0 ? orchestrators[0].file_path : '',
                    drainWaitTime: 5
                };
                
                this.groupContentLoaded[groupName] = false;
            });
            
            modalContent.appendChild(tabsContainer);
            form.appendChild(dynamicContent);
            
            // Функция обновления содержимого вкладки
            const updateFormContent = async (groupName, force = false) => {
                const state = groupStates[groupName];
                const apps = appGroups[groupName];
                const firstApp = apps[0];
                
                // Проверяем кэш и восстанавливаем состояние
                if (!force && this.groupContentLoaded[groupName] && this.groupContentCache[groupName]) {
                    dynamicContent.innerHTML = this.groupContentCache[groupName];
                    
                    // Восстанавливаем значения из сохраненного состояния
                    const distrUrlElement = document.getElementById('distr-url');
                    const customUrlElement = document.getElementById('custom-distr-url');
                    const customGroup = document.getElementById('custom-url-group');
                    
                    if (state.isCustom && customUrlElement) {
                        if (distrUrlElement && distrUrlElement.tagName === 'SELECT') {
                            distrUrlElement.value = 'custom';
                        }
                        customUrlElement.value = state.customUrl || '';
                        if (customGroup) {
                            customGroup.style.display = 'block';
                        }
                    } else if (distrUrlElement) {
                        if (distrUrlElement.tagName === 'SELECT') {
                            distrUrlElement.value = state.distrUrl || '';
                        } else {
                            distrUrlElement.value = state.distrUrl || '';
                        }
                    }
                    
                    // Восстанавливаем режим обновления
                    const modeRadio = document.querySelector(`input[name="mode"][value="${state.restartMode}"]`);
                    if (modeRadio) {
                        modeRadio.checked = true;
                    }

                    // Восстанавливаем поля для режима "Сейчас"
                    const immediateModeFields = document.getElementById('immediate-mode-fields');
                    if (immediateModeFields) {
                        if (state.restartMode === 'immediate') {
                            immediateModeFields.style.display = 'block';
                        }

                        const orchestratorSelect = document.getElementById('orchestrator-playbook');
                        const drainWaitInput = document.getElementById('drain-wait-time');

                        if (orchestratorSelect) {
                            orchestratorSelect.value = state.orchestratorPlaybook || '';
                        }
                        if (drainWaitInput) {
                            drainWaitInput.value = state.drainWaitTime || 5;
                        }
                    }

                    // Восстанавливаем обработчики
                    this.attachFormEventHandlers(groupName, groupStates, groupArtifacts, updateFormContent, orchestrators);
                    return;
                }
                
                // Показываем красивый загрузчик
                dynamicContent.innerHTML = `
                    <div class="loading-indicator">
                        <div class="spinner"></div>
                        <div>Загрузка данных группы ${groupName}...</div>
                    </div>
                `;
                
                const startTime = Date.now();
                
                // Загружаем артефакты если нужно
                let artifacts = groupArtifacts[groupName];
                let loadingError = false;
                
                if (!artifacts || force) {
                    artifacts = await ArtifactsManager.loadWithCache(firstApp.id, true);
                    if (artifacts) {
                        groupArtifacts[groupName] = artifacts;
                        state.artifactsLoaded = true;
                    } else {
                        loadingError = true;
                        console.error(`❌ Не удалось загрузить версии для группы "${groupName}"`);
                    }
                }
                
                // Минимальное время показа загрузчика
                const elapsedTime = Date.now() - startTime;
                if (!this.groupContentLoaded[groupName] && elapsedTime < 600) {
                    await new Promise(resolve => setTimeout(resolve, 600 - elapsedTime));
                }
                
                // Создаем HTML содержимое
                let formHTML = `<div class="form-content-animated">`;
                formHTML += `<input type="hidden" id="app-ids" name="app_ids" value="${state.appIds.join(',')}">`;
                
                // Показываем кнопку обновления и при ошибке
                if (!artifacts || artifacts.length === 0) {
                    const errorClass = loadingError ? 'field-with-error' : '';
                    formHTML += `
                        <div class="form-group animated-fade-in ${errorClass}" style="animation-delay: 0.1s">
                            <div class="artifact-selector-wrapper">
                                <div class="artifact-selector-header">
                                    <label for="distr-url">URL дистрибутива:</label>
                                    <button type="button" class="refresh-artifacts-btn" data-group="${groupName}" title="Попробовать загрузить версии снова">
                                        <span class="refresh-icon">🔄</span>
                                    </button>
                                </div>
                                <input type="text" id="distr-url" name="distr_url" class="form-control" value="${state.distrUrl}" required>
                                ${loadingError ? `
                                    <div class="field-error-message">
                                        <span class="error-icon">⚠</span>
                                        Не удалось загрузить список версий. Введите URL вручную.
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                    `;
                } else {
                    formHTML += `
                        <div class="form-group animated-fade-in" style="animation-delay: 0.1s">
                            <div class="artifact-selector-wrapper">
                                <div class="artifact-selector-header">
                                    <label for="distr-url">
                                        Версия дистрибутива:
                                        <span class="version-count">(${artifacts.length} версий)</span>
                                    </label>
                                    <button type="button" class="refresh-artifacts-btn" data-group="${groupName}" title="Обновить список версий">
                                        <span class="refresh-icon">🔄</span>
                                    </button>
                                </div>
                                <select id="distr-url" name="distr_url" class="form-control artifact-select" required>
                                    ${ArtifactsManager.createVersionSelect(artifacts, state.distrUrl)}
                                </select>
                                ${StateManager.getArtifactsCacheAge(firstApp.id) < 60 ? 
                                    '<div class="cache-status"><span class="cache-fresh">✔ Данные актуальны</span></div>' : 
                                    '<div class="cache-status"><span class="cache-old">Обновлено ' + Math.round(StateManager.getArtifactsCacheAge(firstApp.id) / 60) + ' мин. назад</span></div>'
                                }
                            </div>
                        </div>
                        <div class="form-group animated-fade-in" id="custom-url-group" style="display: none; animation-delay: 0.2s">
                            <label for="custom-distr-url">URL дистрибутива:</label>
                            <input type="text" id="custom-distr-url" name="custom_distr_url" class="form-control">
                        </div>
                    `;
                }
                
                formHTML += `
                    <div class="form-group animated-fade-in" style="animation-delay: 0.3s">
                        <label>Режим обновления:</label>
                        <div class="radio-group">
                            <label class="radio-label">
                                <input type="radio" name="mode" value="deliver" ${state.restartMode === 'deliver' ? 'checked' : ''}> Доставить
                            </label>
                            <label class="radio-label">
                                <input type="radio" name="mode" value="immediate" ${state.restartMode === 'immediate' ? 'checked' : ''}> Сейчас
                            </label>
                            <label class="radio-label">
                                <input type="radio" name="mode" value="night-restart" ${state.restartMode === 'night-restart' ? 'checked' : ''}> В рестарт
                            </label>
                        </div>
                    </div>

                    <div id="immediate-mode-fields" style="display: ${state.restartMode === 'immediate' ? 'block' : 'none'}; animation-delay: 0.35s" class="animated-fade-in">
                        <div class="form-group">
                            <label for="orchestrator-playbook">Orchestrator playbook:</label>
                            <select id="orchestrator-playbook" name="orchestrator_playbook" class="form-control">
                                <option value="none" ${(!state.orchestratorPlaybook || state.orchestratorPlaybook === 'none') && orchestrators.length === 0 ? 'selected' : ''}>Без оркестрации</option>
                                ${orchestrators.length > 0 ?
                                    orchestrators.map((orch, index) => {
                                        // Всегда используем имя файла без расширения
                                        const displayName = orch.file_path.split('/').pop().replace(/\.(yml|yaml)$/i, '');
                                        // Selected если: 1) явно выбран в state, 2) ИЛИ это первый и state не задан/none
                                        const selected = (orch.file_path === state.orchestratorPlaybook) ||
                                                        (index === 0 && (!state.orchestratorPlaybook || state.orchestratorPlaybook === 'none'))
                                                        ? 'selected' : '';
                                        return `<option value="${orch.file_path}" ${selected}>${displayName}</option>`;
                                    }).join('') :
                                    ''
                                }
                            </select>
                        </div>

                        <div class="form-group">
                            <label for="drain-wait-time">Время ожидания после drain:</label>
                            <div class="drain-wait-container">
                                <input type="number" id="drain-wait-time" name="drain_wait_time"
                                       class="form-control" min="0" max="60" value="${state.drainWaitTime || 5}">
                                <span class="unit-label">минут</span>
                            </div>
                            <div class="quick-select-buttons">
                                <a href="#" class="quick-time-link" data-time="10">10</a>
                                <a href="#" class="quick-time-link" data-time="20">20</a>
                                <a href="#" class="quick-time-link" data-time="30">30</a>
                            </div>
                            <small class="form-help-text">Время ожидания после вывода инстанса из балансировки (0-60 минут)</small>
                        </div>
                    </div>

                    <div class="group-apps-info animated-fade-in" style="animation-delay: 0.4s">
                        <label>Приложения в группе:</label>
                        <div class="apps-list">
                            ${apps.map(app => `<span class="app-badge">${app.name}</span>`).join('')}
                        </div>
                    </div>
                </div>`;
                
                // Сохраняем в кэш
                this.groupContentCache[groupName] = formHTML;
                this.groupContentLoaded[groupName] = true;
                
                // Обновляем содержимое с анимацией
                dynamicContent.style.opacity = '0';
                setTimeout(() => {
                    dynamicContent.innerHTML = formHTML;
                    dynamicContent.style.opacity = '1';

                    // Обработчики событий
                    this.attachFormEventHandlers(groupName, groupStates, groupArtifacts, updateFormContent, orchestrators);
                }, 200);
            };
            
            // Обработчики вкладок
            tabsContainer.addEventListener('click', async (e) => {
                const tab = e.target.closest('.modal-tab');
                if (!tab || tab.classList.contains('active')) return;
                
                // Игнорируем клики по кнопке удаления
                if (e.target.classList.contains('tab-remove-btn')) return;
                
                // Сохраняем текущее состояние
                const activeTab = tabsContainer.querySelector('.modal-tab.active');
                if (activeTab) {
                    this.saveGroupState(activeTab.dataset.group, groupStates);
                }
                
                // Переключаем вкладку
                tabsContainer.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                // Загружаем содержимое (используем кэш если есть)
                await updateFormContent(tab.dataset.group);
            });
            
            // Кнопки действий формы
            const formActions = document.createElement('div');
            formActions.className = 'form-actions';
            formActions.innerHTML = `
                <button type="button" class="cancel-btn" onclick="closeModal()">Отмена</button>
                <button type="submit" class="submit-btn">Обновить</button>
            `;
            form.appendChild(formActions);
            
            modalContent.appendChild(form);
            
            // Обработчик отправки формы
            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                // Сохраняем текущее состояние
                const activeTab = tabsContainer.querySelector('.modal-tab.active');
                if (activeTab) {
                    this.saveGroupState(activeTab.dataset.group, groupStates);
                }

                // Отправляем batch запрос для каждой вкладки отдельно
                try {
                    let totalGroups = 0;
                    let totalApps = 0;
                    let hasErrors = false;

                    for (const groupName of Object.keys(groupStates)) {
                        if (excludedGroups.has(groupName)) continue; // Пропускаем исключенные группы

                        const state = groupStates[groupName];
                        if (!state.distrUrl || state.distrUrl.trim() === '' || state.distrUrl === 'custom') {
                            continue; // Пропускаем вкладки без URL
                        }

                        // Формируем тело запроса
                        const requestBody = {
                            app_ids: state.appIds,
                            distr_url: state.distrUrl,
                            mode: state.restartMode
                        };

                        // Добавляем параметры для режима "Сейчас"
                        if (state.restartMode === 'immediate') {
                            if (state.orchestratorPlaybook) {
                                requestBody.orchestrator_playbook = state.orchestratorPlaybook;
                            }
                            if (state.drainWaitTime !== undefined) {
                                requestBody.drain_wait_time = state.drainWaitTime;
                            }
                        }

                        // Отправляем batch запрос для этой вкладки
                        const response = await fetch('/api/applications/batch_update', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(requestBody)
                        });

                        const result = await response.json();

                        if (result.success) {
                            totalGroups += result.groups_count;
                            totalApps += state.appIds.length;
                        } else {
                            hasErrors = true;
                            console.error(`Ошибка обновления группы ${groupName}:`, result.error);
                        }
                    }

                    if (totalApps === 0) {
                        showError('Укажите URL дистрибутива хотя бы для одной группы');
                        return;
                    }

                    if (!hasErrors) {
                        showNotification(`✅ Создано задач: ${totalGroups} для ${totalApps} приложений`, 'success');
                    } else {
                        showNotification(`⚠️ Обновление запущено с ошибками. Проверьте логи.`, 'warning');
                    }

                    // Снимаем чекбоксы с приложений
                    StateManager.clearSelection();
                    DOMUtils.querySelectorInTable('.app-checkbox').forEach(checkbox => {
                        checkbox.checked = false;
                    });
                    DOMUtils.querySelectorInTable('.group-checkbox').forEach(checkbox => {
                        checkbox.checked = false;
                        checkbox.indeterminate = false;
                    });
                    const selectAllCheckbox = document.getElementById('select-all');
                    if (selectAllCheckbox) {
                        selectAllCheckbox.checked = false;
                    }
                    UIRenderer.updateActionButtonsState(false);

                    await EventHandlers.loadApplications();
                    closeModal();
                } catch (error) {
                    console.error('Ошибка при обновлении:', error);
                    showError('Произошла ошибка при обновлении');
                }
            });
            
            // Показываем модальное окно
            window.showModal(title, modalContent);
            
            // Загружаем первую вкладку
            const firstGroup = Object.keys(appGroups)[0];
            await updateFormContent(firstGroup);
        },

        // Обновленная функция updateVersionSelector
        updateVersionSelector(artifacts, currentValue, appId = null) {
            const container = document.querySelector('.artifact-loading-container');
            if (!container) return;

            if (!artifacts) {
                // Показываем поле ввода с кнопкой обновления при ошибке
                container.innerHTML = `
                    <div class="artifact-selector-wrapper">
                        <div class="artifact-selector-header">
                            <label for="distr-url">URL дистрибутива:</label>
                            <button type="button" class="refresh-artifacts-btn" ${appId ? `data-app-id="${appId}"` : ''} title="Попробовать загрузить версии снова">
                                <span class="refresh-icon">🔄</span>
                            </button>
                        </div>
                        <input type="text" id="distr-url" name="distr_url" class="form-control" value="${currentValue || ''}" required>
                        <div class="error-message">Не удалось загрузить список версий</div>
                    </div>
                `;
            } else if (artifacts.length > 0) {
                container.innerHTML = `
                    <div class="artifact-selector-wrapper">
                        <div class="artifact-selector-header">
                            <label for="distr-url">
                                Версия дистрибутива:
                                <span class="version-count">(${artifacts.length} версий)</span>
                            </label>
                            <button type="button" class="refresh-artifacts-btn" ${appId ? `data-app-id="${appId}"` : ''} title="Обновить список версий">
                                <span class="refresh-icon">🔄</span>
                            </button>
                        </div>
                        <select id="distr-url" name="distr_url" class="form-control artifact-select" required>
                            ${ArtifactsManager.createVersionSelect(artifacts, currentValue)}
                        </select>
                    </div>
                `;
            }

            this.attachVersionSelectorHandlers(appId);
        },

        attachVersionSelectorHandlers(appId = null) {
            const select = document.getElementById('distr-url');
            const customGroup = document.getElementById('custom-url-group');
            
            if (select && select.tagName === 'SELECT' && customGroup) {
                select.addEventListener('change', function() {
                    if (this.value === 'custom') {
                        customGroup.style.display = 'block';
                        customGroup.classList.add('animated-slide-down');
                        document.getElementById('custom-distr-url').required = true;
                    } else {
                        customGroup.style.display = 'none';
                        document.getElementById('custom-distr-url').required = false;
                    }
                });
            }
            
            const refreshBtn = document.querySelector('.refresh-artifacts-btn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', async function() {
                    this.disabled = true;

                    // Используем переданный appId или берем из скрытого поля
                    const targetAppId = this.dataset.appId ||
                                       document.getElementById('current-app-id')?.value ||
                                       StateManager.state.allApplications[0]?.id;

                    if (targetAppId) {
                        StateManager.clearArtifactsCache(targetAppId);
                        const artifacts = await ArtifactsManager.loadWithCache(targetAppId, true);
                        ModalManager.updateVersionSelector(artifacts, '', targetAppId);

                        if (artifacts) {
                            showNotification('Список версий обновлен', 'success');
                        }
                    }

                    this.disabled = false;
                });
            }
        },

        attachFormEventHandlers(groupName, groupStates, groupArtifacts, updateFormContent, orchestrators) {
            // Обработчик селектора версий
            const select = document.getElementById('distr-url');
            const customGroup = document.getElementById('custom-url-group');

            if (select && select.tagName === 'SELECT') {
                select.addEventListener('change', function() {
                    if (this.value === 'custom') {
                        customGroup.style.display = 'block';
                        customGroup.classList.add('animated-slide-down');
                        document.getElementById('custom-distr-url').required = true;
                    } else {
                        customGroup.style.display = 'none';
                        document.getElementById('custom-distr-url').required = false;
                    }
                });
            }

            // Обработчики для режимов обновления
            const modeRadios = document.querySelectorAll('input[name="mode"]');
            const immediateModeFields = document.getElementById('immediate-mode-fields');

            modeRadios.forEach(radio => {
                radio.addEventListener('change', function() {
                    if (this.value === 'immediate') {
                        immediateModeFields.style.display = 'block';
                        immediateModeFields.classList.add('animated-slide-down');
                    } else {
                        immediateModeFields.style.display = 'none';
                    }
                });
            });

            // Обработчики для ссылок быстрого выбора времени
            document.querySelectorAll('.quick-time-link').forEach(link => {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    const time = this.dataset.time;
                    const drainWaitInput = document.getElementById('drain-wait-time');
                    if (drainWaitInput) {
                        drainWaitInput.value = time;
                    }

                    // Визуальная обратная связь
                    document.querySelectorAll('.quick-time-link').forEach(l => l.classList.remove('active'));
                    this.classList.add('active');
                });
            });

            // Обработчик кнопки обновления артефактов
            const refreshBtn = document.querySelector('.refresh-artifacts-btn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', async function() {
                    this.disabled = true;

                    const group = this.dataset.group;
                    const apps = StateManager.state.allApplications.filter(app =>
                        (app.group_name || app.name) === group
                    );

                    if (apps.length > 0) {
                        StateManager.clearArtifactsCache(apps[0].id);
                        delete groupArtifacts[group];
                        delete ModalManager.groupContentCache[group];
                        ModalManager.groupContentLoaded[group] = false;

                        // Перезагружаем содержимое с force=true
                        await updateFormContent(group, true);
                    }

                    this.disabled = false;
                });
            }
        },

        // функция сохранения состояния группы
        saveGroupState(groupName, groupStates) {
            if (!groupStates[groupName]) return;

            const distrUrlElement = document.getElementById('distr-url');
            const customUrlElement = document.getElementById('custom-distr-url');

            let distrUrl = '';
            let isCustom = false;
            let customUrl = '';

            if (distrUrlElement) {
                if (distrUrlElement.tagName === 'SELECT') {
                    if (distrUrlElement.value === 'custom') {
                        isCustom = true;
                        customUrl = customUrlElement?.value || '';
                        distrUrl = customUrl;
                    } else {
                        distrUrl = distrUrlElement.value;
                    }
                } else {
                    distrUrl = distrUrlElement.value;
                }
            }

            groupStates[groupName].distrUrl = distrUrl;
            groupStates[groupName].restartMode = document.querySelector('input[name="mode"]:checked')?.value || 'deliver';
            groupStates[groupName].customUrl = customUrl;
            groupStates[groupName].isCustom = isCustom;

            // Сохраняем поля для режима "Сейчас"
            const orchestratorSelect = document.getElementById('orchestrator-playbook');
            const drainWaitInput = document.getElementById('drain-wait-time');

            if (orchestratorSelect) {
                groupStates[groupName].orchestratorPlaybook = orchestratorSelect.value || '';
            }

            if (drainWaitInput) {
                groupStates[groupName].drainWaitTime = parseInt(drainWaitInput.value, 10) || 5;
            }
        },

        async processUpdateForm(formData) {
            try {
                const appIds = formData.get('app_ids').split(',').filter(id => id).map(id => parseInt(id));
                const distrUrl = formData.get('distr_url') === 'custom' ?
                    formData.get('custom_distr_url') : formData.get('distr_url');
                const mode = formData.get('mode');

                if (!distrUrl || distrUrl === 'custom') {
                    showError('Укажите URL дистрибутива');
                    return;
                }

                // Формируем тело запроса
                const requestBody = {
                    app_ids: appIds,
                    distr_url: distrUrl,
                    mode: mode
                };

                // Добавляем параметры для режима "Сейчас"
                if (mode === 'immediate') {
                    const orchestratorPlaybook = formData.get('orchestrator_playbook');
                    const drainWaitTime = formData.get('drain_wait_time');

                    if (orchestratorPlaybook) {
                        requestBody.orchestrator_playbook = orchestratorPlaybook;
                    }

                    if (drainWaitTime) {
                        requestBody.drain_wait_time = parseInt(drainWaitTime, 10);
                    }
                }

                showNotification(`Запуск обновления для ${appIds.length} приложений...`, 'info');

                // Используем новый batch_update endpoint
                const response = await fetch('/api/applications/batch_update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                const result = await response.json();

                if (result.success) {
                    showNotification(`Создано задач: ${result.groups_count} для ${appIds.length} приложений`, 'success');

                    // Снимаем чекбоксы с приложений
                    StateManager.clearSelection();
                    DOMUtils.querySelectorInTable('.app-checkbox').forEach(checkbox => {
                        checkbox.checked = false;
                    });
                    DOMUtils.querySelectorInTable('.group-checkbox').forEach(checkbox => {
                        checkbox.checked = false;
                        checkbox.indeterminate = false;
                    });
                    const selectAllCheckbox = document.getElementById('select-all');
                    if (selectAllCheckbox) {
                        selectAllCheckbox.checked = false;
                    }
                    UIRenderer.updateActionButtonsState(false);
                } else {
                    showError(`Ошибка: ${result.error}`);
                }

                await EventHandlers.loadApplications();
                closeModal();
            } catch (error) {
                console.error('Ошибка при обработке формы обновления:', error);
                showError('Произошла ошибка при обновлении');
            }
        },

        async processMultipleUpdates(updates) {
            try {
                showNotification(`Запуск обновления ${updates.length} приложений...`, 'info');

                // Группируем приложения по (distr_url, mode) для batch запросов
                const batches = {};
                updates.forEach(update => {
                    const key = `${update.distr_url}|${update.mode}`;
                    if (!batches[key]) {
                        batches[key] = {
                            app_ids: [],
                            distr_url: update.distr_url,
                            mode: update.mode
                        };
                    }
                    batches[key].app_ids.push(update.appId);
                });

                // Отправляем batch запросы
                let totalGroups = 0;
                let hasErrors = false;

                for (const batch of Object.values(batches)) {
                    const response = await fetch('/api/applications/batch_update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(batch)
                    });

                    const result = await response.json();

                    if (result.success) {
                        totalGroups += result.groups_count;
                    } else {
                        hasErrors = true;
                        console.error('Ошибка batch update:', result.error);
                    }
                }

                if (!hasErrors) {
                    showNotification(`✅ Создано задач: ${totalGroups} для ${updates.length} приложений`, 'success');
                } else {
                    showNotification(`⚠️ Обновление запущено, но возникли ошибки. Проверьте логи.`, 'warning');
                }

                await EventHandlers.loadApplications();
                closeModal();
            } catch (error) {
                console.error('Ошибка при массовом обновлении:', error);
                showError('Произошла ошибка при обновлении приложений');
            }
        }
    };

    // ========================================
    // МОДУЛЬ ОБРАБОТЧИКОВ СОБЫТИЙ
    // ========================================
    const EventHandlers = {
        init() {
            this.initDropdownHandlers();
            this.initServerSelection();
            this.initSearch();
            this.initSorting();
            this.initGrouping();
            this.initCheckboxHandlers();
            this.initActionButtons();
            this.initPagination();
            this.initTableActions();
            this.initRefreshButton();
            this.initTagFilter();
        },

        initRefreshButton() {
            const refreshBtn = document.getElementById('refresh-btn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', function() {
                    EventHandlers.loadApplications();
                });
            }
        },

        async initTagFilter() {
            const toggleBtn = document.getElementById('tag-filter-toggle');
            const filterSection = document.getElementById('tag-filter-section');
            const checkboxesContainer = document.getElementById('tag-filter-checkboxes');
            const applyBtn = document.getElementById('apply-tag-filter');
            const clearBtn = document.getElementById('clear-tag-filter');

            if (!toggleBtn || !filterSection) return;

            // Загрузка тегов
            const tags = await ApiService.loadTags();
            StateManager.state.availableTags = tags;

            // Создаем чекбоксы для тегов
            if (checkboxesContainer && tags.length > 0) {
                checkboxesContainer.innerHTML = tags.map(tag => `
                    <label class="tag-checkbox-label">
                        <input type="checkbox" value="${tag.name}" class="tag-filter-checkbox">
                        <span class="tag ${tag.css_class || ''}">${tag.icon || ''} ${tag.display_name || tag.name}</span>
                    </label>
                `).join('');
            } else if (checkboxesContainer) {
                checkboxesContainer.innerHTML = '<span style="color: #999;">Нет доступных тегов</span>';
            }

            // Переключение панели фильтра
            toggleBtn.addEventListener('click', () => {
                const isVisible = filterSection.style.display !== 'none';
                filterSection.style.display = isVisible ? 'none' : 'block';
                toggleBtn.classList.toggle('active', !isVisible);
            });

            // Применение фильтра
            if (applyBtn) {
                applyBtn.addEventListener('click', () => {
                    const selectedCheckboxes = checkboxesContainer.querySelectorAll('.tag-filter-checkbox:checked');
                    StateManager.state.selectedTags = Array.from(selectedCheckboxes).map(cb => cb.value);

                    const operatorRadio = document.querySelector('input[name="tag-operator"]:checked');
                    StateManager.state.tagOperator = operatorRadio ? operatorRadio.value : 'OR';

                    StateManager.state.currentPage = 1;
                    this.filterAndDisplayApplications();

                    // Обновляем визуальное состояние кнопки
                    toggleBtn.classList.toggle('active', StateManager.state.selectedTags.length > 0);
                });
            }

            // Очистка фильтра
            if (clearBtn) {
                clearBtn.addEventListener('click', () => {
                    checkboxesContainer.querySelectorAll('.tag-filter-checkbox').forEach(cb => cb.checked = false);
                    StateManager.state.selectedTags = [];
                    StateManager.state.currentPage = 1;
                    this.filterAndDisplayApplications();
                    toggleBtn.classList.remove('active');
                });
            }
        },

        initDropdownHandlers() {
            // Создаем оверлей для выпадающих меню
            let dropdownOverlay = document.querySelector('.dropdown-overlay');
            if (!dropdownOverlay) {
                dropdownOverlay = document.createElement('div');
                dropdownOverlay.className = 'dropdown-overlay';
                document.body.appendChild(dropdownOverlay);
            }
            
            // Обработчик клика по кнопке меню
            document.body.addEventListener('click', (e) => {
                const actionButton = e.target.closest('.actions-button');
                if (actionButton) {
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggleDropdown(actionButton);
                }
            });
            
            // Закрытие меню при клике на оверлей
            dropdownOverlay.addEventListener('click', () => {
                this.closeAllDropdowns();
            });
        },

        toggleDropdown(actionButton) {
            const dropdown = actionButton.nextElementSibling;
            const dropdownOverlay = document.querySelector('.dropdown-overlay');
            
            if (dropdown.classList.contains('show')) {
                this.closeAllDropdowns();
                return;
            }
            
            this.closeAllDropdowns();
            
            // Показываем оверлей и меню
            dropdownOverlay.style.display = 'block';
            this.positionDropdown(dropdown, actionButton);
            StateManager.activeDropdown = dropdown;
        },

        positionDropdown(dropdown, actionButton) {
            const buttonRect = actionButton.getBoundingClientRect();
            const spaceBelow = window.innerHeight - buttonRect.bottom;
            const showUpwards = spaceBelow < 200;
            
            // Сначала сбрасываем все позиции
            dropdown.style.top = '';
            dropdown.style.bottom = '';
            dropdown.style.display = 'block';
            dropdown.style.opacity = '0';
            dropdown.classList.remove('dropdown-up');
            
            if (showUpwards) {
                dropdown.classList.add('dropdown-up');
                dropdown.style.bottom = (window.innerHeight - buttonRect.top) + 'px';
                dropdown.style.top = 'auto'; // Явно убираем top
            } else {
                dropdown.style.top = buttonRect.bottom + 'px';
                dropdown.style.bottom = 'auto'; // Явно убираем bottom
            }
            
            dropdown.style.right = (window.innerWidth - buttonRect.right) + 'px';
            dropdown.classList.add('show');
            dropdown.style.opacity = '1';
            actionButton.classList.add('active');
        },

        closeAllDropdowns() {
            const dropdownOverlay = document.querySelector('.dropdown-overlay');
            if (dropdownOverlay) {
                dropdownOverlay.style.display = 'none';
            }
            
            document.querySelectorAll('.actions-dropdown.show').forEach(dropdown => {
                dropdown.classList.remove('show');
                dropdown.style.display = '';
                
                const actionButton = dropdown.previousElementSibling;
                if (actionButton) {
                    actionButton.classList.remove('active');
                }
            });
            
            StateManager.activeDropdown = null;
        },

        async initServerSelection() {
            const servers = await ApiService.loadServers();
            UIRenderer.renderServers(servers);
            
            // Обработчик клика по dropdown серверов
            const serverDropdown = document.querySelector('.server-dropdown');
            const serverButton = document.getElementById('server-selected');
            const serverList = document.getElementById('server-list');

            if (serverButton && serverDropdown) {
                serverButton.addEventListener('click', (e) => {
                    e.stopPropagation();
                    serverDropdown.classList.toggle('open');
                });
            }

            // Обработчик выбора сервера
            if (serverList) {
                serverList.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const serverItem = e.target.closest('li');
                    if (serverItem) {
                        const serverId = serverItem.dataset.serverId;
                        const serverName = serverItem.textContent;
                        this.selectServer(serverId, serverName);
                        serverDropdown?.classList.remove('open');
                    }
                });
            }

            // Закрытие dropdown при клике вне его
            document.addEventListener('click', () => {
                serverDropdown?.classList.remove('open');
            });
        },

        selectServer(serverId, serverName) {
            StateManager.state.selectedServerId = serverId;
            const button = document.getElementById('server-selected');
            if (button) {
                button.innerHTML = `${serverName} <span>▾</span>`;
            }
            StateManager.state.currentPage = 1;
            this.loadApplications();
        },

        initSearch() {
            const searchInput = document.getElementById('search-input');
            if (searchInput) {
                // Создаем debounced версию функции поиска
                const debouncedSearch = DOMUtils.debounce((value) => {
                    StateManager.state.searchQuery = value.trim().toLowerCase();
                    StateManager.state.currentPage = 1;
                    this.filterAndDisplayApplications();
                }, 250); // 250ms задержка
                
                searchInput.addEventListener('input', (e) => {
                    debouncedSearch(e.target.value);
                });
            }
        },

        initSorting() {
            // Обработчики сортировки по клику на заголовки
            document.querySelectorAll('th.sortable').forEach(th => {
                th.addEventListener('click', function() {
                    const currentSortColumn = StateManager.state.sortColumn;
                    StateManager.state.sortColumn = this.getAttribute('data-sort');
                    
                    if (currentSortColumn === StateManager.state.sortColumn) {
                        StateManager.state.sortDirection = StateManager.state.sortDirection === 'asc' ? 'desc' : 'asc';
                    } else {
                        StateManager.state.sortDirection = 'asc';
                    }
                    
                    // Обновляем классы для отображения направления
                    document.querySelectorAll('th.sortable').forEach(header => {
                        header.classList.remove('sorted-asc', 'sorted-desc');
                    });
                    
                    this.classList.add(`sorted-${StateManager.state.sortDirection}`);
                    
                    EventHandlers.filterAndDisplayApplications();
                });
            });
        },

        initGrouping() {
            const groupToggleBtn = document.getElementById('group-toggle-btn');
            if (groupToggleBtn) {
                StateManager.state.groupingEnabled = groupToggleBtn.classList.contains('active');
                
                groupToggleBtn.addEventListener('click', () => {
                    groupToggleBtn.classList.toggle('active');
                    StateManager.state.groupingEnabled = groupToggleBtn.classList.contains('active');
                    StateManager.state.currentPage = 1;
                    this.filterAndDisplayApplications();
                });
            }
        },

        // обработка чекбокса "выбрать все"
        initCheckboxHandlers() {
            const selectAllCheckbox = document.getElementById('select-all');
            if (selectAllCheckbox) {
                selectAllCheckbox.addEventListener('change', function(e) {
                    const isChecked = this.checked;
                    
                    // Используем контекст таблицы
                    DOMUtils.querySelectorInTable('.app-checkbox').forEach(checkbox => {
                        checkbox.checked = isChecked;
                        const appId = checkbox.dataset.appId;
                        if (appId) {
                            if (isChecked) {
                                StateManager.addSelectedApp(appId);
                            } else {
                                StateManager.removeSelectedApp(appId);
                            }
                        }
                    });
                    
                    // Обновляем групповые чекбоксы тоже в контексте таблицы
                    DOMUtils.querySelectorInTable('.group-checkbox').forEach(checkbox => {
                        checkbox.checked = isChecked;
                        checkbox.indeterminate = false;
                    });
                    
                    UIRenderer.updateActionButtonsState(StateManager.state.selectedItems.applications.size > 0);
                });
            }
            
            // Делегирование событий для чекбоксов
            document.addEventListener('change', (e) => {
                if (e.target.classList.contains('app-checkbox')) {
                    const appId = e.target.dataset.appId;
                    if (e.target.checked) {
                        StateManager.addSelectedApp(appId);
                    } else {
                        StateManager.removeSelectedApp(appId);
                    }
                    
                    const hasSelection = StateManager.state.selectedItems.applications.size > 0;
                    UIRenderer.updateActionButtonsState(hasSelection);
                    
                    // Обновляем состояние "выбрать все"
                    UIRenderer.updateSelectAllState();
                    
                    // Обновляем состояние группового чекбокса
                    const parentGroup = e.target.closest('.child-wrapper')?.dataset.group;
                    if (parentGroup) {
                        UIRenderer.updateGroupCheckbox(parentGroup);
                    }
                }
                
                if (e.target.classList.contains('group-checkbox')) {
                    const groupName = e.target.dataset.group;
                    const isChecked = e.target.checked;
                    
                    // Выбираем/снимаем выбор со всех приложений группы
                    document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`).forEach(checkbox => {
                        checkbox.checked = isChecked;
                        const appId = checkbox.dataset.appId;
                        if (isChecked) {
                            StateManager.addSelectedApp(appId);
                        } else {
                            StateManager.removeSelectedApp(appId);
                        }
                    });
                    
                    // Обновляем состояние "выбрать все"
                    UIRenderer.updateSelectAllState();
                    
                    const hasSelection = StateManager.state.selectedItems.applications.size > 0;
                    UIRenderer.updateActionButtonsState(hasSelection);
                }
            });
        },

        initActionButtons() {
            // Обработчики для кнопок действий
            const actionButtons = {
                start: document.getElementById('start-btn'),
                restart: document.getElementById('restart-btn'),
                stop: document.getElementById('stop-btn'),
                update: document.getElementById('update-btn'),
                unload: document.getElementById('unload-btn')
            };
            
            Object.entries(actionButtons).forEach(([action, button]) => {
                if (button) {
                    button.addEventListener('click', () => {
                        const selectedIds = StateManager.getSelectedAppIds();
                        if (selectedIds.length === 0) {
                            showError('Не выбрано ни одного приложения');
                            return;
                        }

                        if (action === 'update') {
                            ModalManager.showUpdateModal(selectedIds);
                        } else {
                            this.handleBatchAction(selectedIds, action);
                        }
                    });
                }
            });

            // Batch tags button handler
            const batchTagsBtn = document.getElementById('batch-tags-btn');
            if (batchTagsBtn) {
                batchTagsBtn.addEventListener('click', () => {
                    const selectedIds = StateManager.getSelectedAppIds();
                    if (selectedIds.length === 0) {
                        showError('Не выбрано ни одного приложения');
                        return;
                    }
                    this.showBatchTagsModal(selectedIds);
                });
            }
        },

        async showBatchTagsModal(appIds) {
            const template = document.getElementById('batch-tags-modal-template');
            if (!template) return;

            const content = template.content.cloneNode(true);

            // Set selected count
            content.querySelector('.selected-count').textContent = appIds.length;

            // Load tags for checkboxes
            const tags = await ApiService.loadTags();
            const checkboxesContainer = content.querySelector('.batch-tags-checkboxes');

            if (tags.length > 0) {
                checkboxesContainer.innerHTML = tags.map(tag => `
                    <label class="tag-checkbox-label" style="display: block; margin: 5px 0;">
                        <input type="checkbox" value="${tag.name}" class="batch-tag-checkbox">
                        <span class="tag ${tag.css_class || ''}">${tag.icon || ''} ${tag.display_name || tag.name}</span>
                    </label>
                `).join('');
            } else {
                checkboxesContainer.innerHTML = '<span style="color: #999;">Нет доступных тегов</span>';
            }

            // Show modal
            window.showModal('Управление тегами', content);

            // Apply button handler
            document.getElementById('apply-batch-tags').addEventListener('click', async () => {
                const operation = document.querySelector('input[name="tag-operation"]:checked').value;
                const selectedTags = Array.from(document.querySelectorAll('.batch-tag-checkbox:checked')).map(cb => cb.value);

                if (selectedTags.length === 0) {
                    showError('Выберите хотя бы один тег');
                    return;
                }

                try {
                    const response = await fetch('/api/tags/bulk-assign', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            app_ids: appIds,
                            tag_names: selectedTags,
                            action: operation
                        })
                    });

                    const data = await response.json();

                    if (data.success) {
                        showNotification(`Теги успешно ${operation === 'add' ? 'добавлены' : 'удалены'}`);
                        closeModal();
                        await this.loadApplications();
                    } else {
                        showError(data.error || 'Ошибка операции с тегами');
                    }
                } catch (error) {
                    console.error('Error in batch tags operation:', error);
                    showError('Ошибка операции с тегами');
                }
            });
        },

        async handleBatchAction(appIds, action) {
            const apps = appIds.map(id => StateManager.getAppById(id)).filter(app => app);
            
            // Фильтруем приложения по доступности действия
            const availableApps = apps.filter(app => {
                if (action === 'start') return app.status !== 'online';
                if (action === 'stop' || action === 'restart') return app.status === 'online';
                return true;
            });
            
            if (availableApps.length === 0) {
                showError(`Действие "${action}" недоступно для выбранных приложений`);
                return;
            }
            
            const availableIds = availableApps.map(app => app.id);
            
            // Подтверждение действия
            const actionNames = {
                'start': 'запустить',
                'stop': 'остановить',
                'restart': 'перезапустить'
            };
            
            const actionName = actionNames[action] || action;
            const appItems = availableApps.map(app => app.name);
            
            ModalUtils.showConfirmModal(
                `${actionName.charAt(0).toUpperCase() + actionName.slice(1)} приложения`,
                `Вы уверены, что хотите <span class="action-name">${actionName}</span> выбранные приложения?`,
                appItems,
                async () => {
                    const result = await ApiService.executeAction(availableIds, action);
                    
                    if (result.success) {
                        const successCount = result.results?.filter(r => r.success).length || 0;
                        const errorCount = result.results?.filter(r => !r.success).length || 0;
                        
                        if (errorCount === 0) {
                            showNotification(`Действие "${actionName}" успешно выполнено`, 'success');
                        } else if (successCount > 0) {
                            showNotification(`Действие выполнено для ${successCount} из ${availableIds.length} приложений`, 'success');
                        } else {
                            showError(`Не удалось выполнить действие "${actionName}"`);
                        }
                    } else {
                        showError(result.error || `Не удалось выполнить действие "${actionName}"`);
                    }
                    
                    await this.loadApplications();
                },
                `Подтвердить (${availableIds.length})`
            );
        },

        initPagination() {
            // Устанавливаем обработчики ОДИН РАЗ при инициализации
            
            // Обработчик для кнопки "Предыдущая"
            const prevButton = document.querySelector('.prev-page');
            if (prevButton) {
                prevButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Берем актуальное состояние из StateManager
                    if (!prevButton.disabled && StateManager.state.currentPage > 1) {
                        StateManager.state.currentPage--;
                        this.filterAndDisplayApplications();
                    }
                });
            }

            // Обработчик для кнопки "Следующая"
            const nextButton = document.querySelector('.next-page');
            if (nextButton) {
                nextButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    if (!nextButton.disabled) {
                        // Вычисляем актуальное количество страниц
                        const filtered = this.getFilteredApplications();
                        const totalPages = Math.ceil(filtered.length / StateManager.state.pageSize);

                        if (StateManager.state.currentPage < totalPages) {
                            StateManager.state.currentPage++;
                            this.filterAndDisplayApplications();
                        }
                    }
                });
            }

            // Обработчик изменения размера страницы
            const pageSizeSelect = document.getElementById('page-size-select');
            if (pageSizeSelect) {
                pageSizeSelect.addEventListener('change', (e) => {
                    const newSize = parseInt(e.target.value);

                    if (!isNaN(newSize) && newSize > 0) {
                        StateManager.state.pageSize = newSize;
                        StateManager.state.currentPage = 1; // Сброс на первую страницу
                        this.filterAndDisplayApplications();
                    }
                });
            }
        },

        getFilteredApplications() {
            let filtered = [...StateManager.state.allApplications];

            // Применяем поиск
            if (StateManager.state.searchQuery) {
                filtered = filtered.filter(app =>
                    app.name.toLowerCase().includes(StateManager.state.searchQuery) ||
                    app.status?.toLowerCase().includes(StateManager.state.searchQuery) ||
                    app.server_name?.toLowerCase().includes(StateManager.state.searchQuery)
                );
            }

            // Применяем фильтр по тегам
            if (StateManager.state.selectedTags.length > 0) {
                filtered = filtered.filter(app => {
                    const appTagNames = (app.tags || []).map(t => t.name);
                    if (StateManager.state.tagOperator === 'AND') {
                        return StateManager.state.selectedTags.every(tagName => appTagNames.includes(tagName));
                    } else {
                        return StateManager.state.selectedTags.some(tagName => appTagNames.includes(tagName));
                    }
                });
            }
            
            // Применяем сортировку
            filtered.sort((a, b) => {
                let valueA, valueB;
                const field = StateManager.state.sortColumn;
                
                if (field === 'name') {
                    valueA = a.name?.toLowerCase() || '';
                    valueB = b.name?.toLowerCase() || '';
                } else if (field === 'status') {
                    valueA = a.status?.toLowerCase() || '';
                    valueB = b.status?.toLowerCase() || '';
                } else if (field === 'version') {
                    valueA = a.version?.toLowerCase() || '';
                    valueB = b.version?.toLowerCase() || '';
                } else if (field === 'server') {
                    valueA = a.server_name?.toLowerCase() || '';
                    valueB = b.server_name?.toLowerCase() || '';
                }
                
                const direction = StateManager.state.sortDirection === 'asc' ? 1 : -1;
                if (valueA < valueB) return -direction;
                if (valueA > valueB) return direction;
                return 0;
            });
            
            return filtered;
        },        

        initTableActions() {
            // Делегирование событий для действий в таблице
            document.addEventListener('click', (e) => {
                // Флаг для определения, был ли клик по элементу меню
                const isMenuAction = e.target.closest('.actions-dropdown a');    
                            
                // Обработчики действий для приложений
                if (e.target.classList.contains('app-info-btn')) {
                    e.preventDefault();
                    const appId = e.target.dataset.appId;
                    this.showAppInfo(appId);
                }
                
                if (e.target.classList.contains('app-update-btn')) {
                    e.preventDefault();
                    const appId = e.target.dataset.appId;
                    ModalManager.showUpdateModal([appId]);
                }
                
                // Обработчики действий для групп
                if (e.target.classList.contains('group-update-btn')) {
                    e.preventDefault();
                    const groupName = e.target.dataset.group;
                    this.handleGroupUpdate(groupName);
                }
                
                // Другие действия
                ['start', 'stop', 'restart'].forEach(action => {
                    if (e.target.classList.contains(`app-${action}-btn`)) {
                        e.preventDefault();
                        if (!e.target.classList.contains('disabled')) {
                            const appId = e.target.dataset.appId;
                            this.handleBatchAction([appId], action);
                        }
                    }
                    
                    if (e.target.classList.contains(`group-${action}-btn`)) {
                        e.preventDefault();
                        if (!e.target.classList.contains('disabled')) {
                            const groupName = e.target.dataset.group;
                            this.handleGroupAction(groupName, action);
                        }
                    }
                });
                // Закрываем меню после клика на любой пункт
                if (isMenuAction) {
                    setTimeout(() => this.closeAllDropdowns(), 100);
                }                
            });
        },

        handleGroupUpdate(groupName) {
            const appIds = [];
            document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`).forEach(checkbox => {
                appIds.push(checkbox.dataset.appId);
            });
            
            if (appIds.length > 0) {
                ModalManager.showUpdateModal(appIds);
            }
        },

        handleGroupAction(groupName, action) {
            const appIds = [];
            document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`).forEach(checkbox => {
                appIds.push(checkbox.dataset.appId);
            });
            
            if (appIds.length > 0) {
                this.handleBatchAction(appIds, action);
            }
        },

        async showAppInfo(appId) {
            const app = await ApiService.getApplicationInfo(appId);
            if (!app) {
                showError('Не удалось получить информацию о приложении');
                return;
            }
            
            const sections = [
                {
                    title: 'Основная информация',
                    type: 'table',
                    rows: [
                        { label: 'Имя:', value: app.name },
                        { label: 'Тип:', value: app.app_type || 'Не указан' },
                        { label: 'Статус:', value: `<span class="status-badge ${app.status === 'online' ? 'status-completed' : 'status-failed'}">${app.status || 'Неизвестно'}</span>` },
                        { label: 'Версия:', value: app.version || 'Не указана' },
                        { label: 'Сервер:', value: app.server_name || 'Не указан' },
                        { label: 'IP:', value: app.ip || 'Не указан' },
                        { label: 'Порт:', value: app.port || 'Не указан' }
                    ]
                },
                {
                    title: 'Пути и расположение',
                    type: 'table',
                    rows: [
                        { label: 'Путь приложения:', value: app.path || 'Не указан' },
                        { label: 'Путь к логам:', value: app.log_path || 'Не указан' },
                        { label: 'Путь к дистрибутиву:', value: app.distr_path || 'Не указан' }
                    ]
                }
            ];
            
            if (app.events && app.events.length > 0) {
                let eventsHtml = '<table class="events-table"><thead><tr><th>Дата</th><th>Тип</th><th>Статус</th></tr></thead><tbody>';
                app.events.forEach(event => {
                    const eventDate = new Date(event.timestamp);
                    eventsHtml += `
                        <tr class="event-row ${event.status}">
                            <td>${eventDate.toLocaleString()}</td>
                            <td>${event.event_type}</td>
                            <td>${event.status}</td>
                        </tr>
                    `;
                });
                eventsHtml += '</tbody></table>';
                
                sections.push({
                    title: 'Последние события',
                    type: 'html',
                    content: eventsHtml
                });
            }
            
            ModalUtils.showInfoModal(`Информация о приложении: ${app.name}`, sections);
        },

        async loadApplications() {
            const tbody = document.getElementById('applications-table-body');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="6" class="table-loading">Загрузка приложений...</td></tr>';
            }
            
            const applications = await ApiService.loadApplications(StateManager.state.selectedServerId);
            StateManager.state.allApplications = applications;
            
            this.filterAndDisplayApplications();
        },

        filterAndDisplayApplications() {
            // Получаем отфильтрованные данные
            const filtered = this.getFilteredApplications();
            
            // Проверяем и корректируем текущую страницу
            const totalPages = Math.ceil(filtered.length / StateManager.state.pageSize);
            
            // Если текущая страница больше общего числа страниц, возвращаемся на последнюю
            if (StateManager.state.currentPage > totalPages && totalPages > 0) {
                StateManager.state.currentPage = totalPages;
            }
            
            // Если текущая страница меньше 1, устанавливаем 1
            if (StateManager.state.currentPage < 1 && filtered.length > 0) {
                StateManager.state.currentPage = 1;
            }
            
            // Если нет данных, сбрасываем на 1
            if (filtered.length === 0) {
                StateManager.state.currentPage = 1;
            }

            // Вызываем рендеринг
            UIRenderer.renderApplications(filtered);
            
            // Состояние "выбрать все" уже обновлено внутри renderApplications
        }       
    };

    // ========================================
    // ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
    // ========================================
    document.addEventListener('DOMContentLoaded', () => {
        // Инициализация UI элементов
        UIRenderer.init();
        
        // Инициализация обработчиков событий
        EventHandlers.init();
        
        // Загрузка начальных данных
        EventHandlers.loadApplications();
        
        // Добавляем стили для анимаций
        if (!document.getElementById('applications-animations')) {
            const style = document.createElement('style');
            style.id = 'applications-animations';
            style.textContent = `
                .rotating {
                    animation: rotate 1s linear infinite;
                }
                @keyframes rotate {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
                .animated-fade-in {
                    animation: fadeIn 0.3s ease-in;
                }
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .animated-slide-down {
                    animation: slideDown 0.3s ease-out;
                }
                @keyframes slideDown {
                    from { 
                        opacity: 0; 
                        max-height: 0;
                        transform: translateY(-10px);
                    }
                    to { 
                        opacity: 1; 
                        max-height: 200px;
                        transform: translateY(0);
                    }
                }
                .form-content-animated > .form-group {
                    opacity: 0;
                    animation: fadeIn 0.4s ease-out forwards;
                }
                .form-content-animated > .form-group:nth-child(1) { animation-delay: 0.1s; }
                .form-content-animated > .form-group:nth-child(2) { animation-delay: 0.2s; }
                .form-content-animated > .form-group:nth-child(3) { animation-delay: 0.3s; }
                .form-content-animated > .form-group:nth-child(4) { animation-delay: 0.4s; }
                
                /* Стили для группы */
                .group-toggle {
                    transition: transform 0.3s ease;
                }
                
                /* Стили для кнопки удаления вкладки */
                .modal-tab {
                    position: relative;
                    padding-right: 25px;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                }
                
                .tab-content {
                    flex: 1;
                }
                
                .tab-remove-btn {
                    position: absolute;
                    right: 5px;
                    top: 50%;
                    transform: translateY(-50%);
                    background: none;
                    border: none;
                    color: #999;
                    font-size: 18px;
                    line-height: 1;
                    cursor: pointer;
                    width: 20px;
                    height: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 50%;
                    transition: all 0.2s;
                    opacity: 0.6;
                }
                
                .tab-remove-btn:hover {
                    opacity: 1;
                    background-color: rgba(231, 76, 60, 0.1);
                    color: #e74c3c;
                }
                
                .modal-tab:hover .tab-remove-btn {
                    opacity: 1;
                }
                
                .no-groups-message {
                    text-align: center;
                    padding: 40px;
                    color: #999;
                    font-size: 16px;
                }

                /* Стили для полей режима "Сейчас" */
                #immediate-mode-fields {
                    margin-top: 15px;
                    padding: 15px;
                    background-color: rgba(52, 152, 219, 0.05);
                    border-left: 3px solid #3498db;
                    border-radius: 4px;
                }

                /* Стиль для select оркестратора - темный фон */
                #immediate-mode-fields select#orchestrator-playbook {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    border: 1px solid #34495e;
                }

                #immediate-mode-fields select#orchestrator-playbook option {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                }

                .drain-wait-container {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }

                .drain-wait-container input[type="number"] {
                    flex: 0 0 120px;
                    text-align: center;
                }

                /* Убираем стрелки spinner у input[type="number"] */
                #immediate-mode-fields input[type="number"]::-webkit-inner-spin-button,
                #immediate-mode-fields input[type="number"]::-webkit-outer-spin-button {
                    -webkit-appearance: none;
                    margin: 0;
                }

                #immediate-mode-fields input[type="number"] {
                    -moz-appearance: textfield;
                }

                .unit-label {
                    color: #666;
                    font-size: 14px;
                }

                .quick-select-buttons {
                    display: flex;
                    gap: 12px;
                    margin-top: 10px;
                    align-items: center;
                }

                .quick-time-link {
                    color: #3498db;
                    text-decoration: none;
                    font-size: 14px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: color 0.2s;
                    padding: 2px 4px;
                }

                .quick-time-link:hover {
                    color: #2980b9;
                    text-decoration: underline;
                }

                .quick-time-link.active {
                    color: #27ae60;
                    font-weight: 600;
                }

                .form-help-text {
                    display: block;
                    margin-top: 8px;
                    font-size: 12px;
                    color: #7f8c8d;
                    font-style: italic;
                }
            `;
            document.head.appendChild(style);
        }
    });

    // Экспорт модулей в глобальную область для доступа извне
    window.ApplicationsDebug = {
        getState: () => StateManager.state,
        getCache: () => StateManager.artifactsCache,
        clearCache: () => StateManager.clearArtifactsCache(),
        debugArtifactsCache: () => {
            const result = {};
            Object.keys(StateManager.artifactsCache).forEach(key => {
                const cache = StateManager.artifactsCache[key];
                const age = Math.round((Date.now() - cache.timestamp) / 1000);
                result[key] = { versions: cache.data.length, age: `${age}s` };
            });
            return result;
        }
    };
    
    // Экспорт обработчиков событий для доступа из обработчиков
    window.SecurityUtils = SecurityUtils;
    window.DOMUtils = DOMUtils;   
    window.EventHandlers = EventHandlers;
    window.StateManager = StateManager;
    window.UIRenderer = UIRenderer;
    window.ModalManager = ModalManager;
    window.ApiService = ApiService;
    window.ArtifactsManager = ArtifactsManager;

})();

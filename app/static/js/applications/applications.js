/**
 * Faktura Apps - Управление приложениями
 * Главный модуль страницы приложений
 */

(function() {
    'use strict';

    // ========================================
    // ССЫЛКИ НА ВНЕШНИЕ МОДУЛИ
    // ========================================
    // Core модули загружаются из отдельных файлов:
    // - CONFIG (core/config.js)
    // - SecurityUtils (core/security-utils.js)
    // - DOMUtils (core/dom-utils.js)
    // - StateManager (core/state-manager.js)
    // - ApiService (core/api-service.js)
    // - ArtifactsManager (core/artifacts-manager.js)

    const CONFIG = window.CONFIG;
    const SecurityUtils = window.SecurityUtils;
    const DOMUtils = window.DOMUtils;
    const StateManager = window.StateManager;
    const ApiService = window.ApiService;
    const ArtifactsManager = window.ArtifactsManager;

    // ========================================
    // МОДУЛЬ РАБОТЫ С UI
    // ========================================
    const UIRenderer = {
        elements: {
            applicationsListBody: null,
            selectAllCheckbox: null,
            serverDropdown: null,
            searchInput: null,
            sortSelects: null,
            groupToggleBtn: null,
            actionButtons: {}
        },

        init() {
            this.elements.applicationsListBody = document.getElementById('applications-list-body');
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
            const listBody = this.elements.applicationsListBody;
            if (!listBody) return;

            // Сохраняем состояние перед обновлением
            StateManager.saveTableState();

            listBody.innerHTML = '';

            if (applications.length === 0) {
                listBody.innerHTML = '<div class="apps-list-empty">Нет приложений</div>';
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
                const row = this.createAppElement(app);
                if (row && this.elements.applicationsListBody) {
                    this.elements.applicationsListBody.appendChild(row);
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
            const listBody = this.elements.applicationsListBody;
            if (!listBody) return;

            // Создаем контейнер группы
            const groupContainer = document.createElement('div');
            groupContainer.className = 'apps-group';
            groupContainer.setAttribute('data-group', group.name);

            // Создаем заголовок группы
            const groupHeader = this.createGroupElement(group.name, group.apps);
            groupContainer.appendChild(groupHeader);

            // Создаем контейнер для дочерних элементов
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'apps-group-children';

            // Добавляем приложения группы
            group.apps.forEach(app => {
                const appElement = this.createAppElement(app, group.name);
                childrenContainer.appendChild(appElement);
            });

            groupContainer.appendChild(childrenContainer);
            listBody.appendChild(groupContainer);
        },

        // Рендеринг тегов с унаследованными - делегирование к TagsRenderer
        renderTagsWithInherited(ownTags, groupTags) {
            return window.TagsRenderer.render(ownTags, { groupTags });
        },

        // Рендеринг тегов - делегирование к TagsRenderer
        renderTags(tags) {
            return window.TagsRenderer.render(tags);
        },

        /**
         * Создает элемент строки приложения - делегирование к ElementFactory
         */
        createAppElement(app, groupName = null) {
            return window.ElementFactory.createAppElement(app, groupName, {
                renderTagsWithInherited: this.renderTagsWithInherited.bind(this)
            });
        },

        /**
         * Создает элемент заголовка группы - делегирование к ElementFactory
         */
        createGroupElement(groupName, apps) {
            return window.ElementFactory.createGroupElement(groupName, apps, {
                renderTags: this.renderTags.bind(this)
            });
        },

        /**
         * Создает меню действий для приложения - делегирование к ElementFactory
         */
        createActionsMenu(app) {
            return window.ElementFactory.createActionsMenu(app);
        },

        /**
         * Создает меню действий для группы - делегирование к ElementFactory
         */
        createGroupActionsMenu(groupName, apps) {
            return window.ElementFactory.createGroupActionsMenu(groupName, apps);
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

        /**
         * Пагинация данных - делегирование к Pagination
         */
        paginateData(data) {
            const { currentPage, pageSize } = StateManager.state;
            return window.Pagination.paginateData(data, currentPage, pageSize);
        },

        /**
         * Обновление пагинации - делегирование к Pagination
         */
        updatePagination(totalItems) {
            const { currentPage, pageSize } = StateManager.state;
            window.Pagination.updatePagination(totalItems, currentPage, pageSize);
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
            document.querySelectorAll('.apps-row').forEach(row => {
                row.addEventListener('click', function(e) {
                    if (e.target.closest('.apps-checkbox-container') || e.target.closest('.apps-actions-menu') || e.target.closest('.actions-menu')) {
                        return;
                    }
                    this.classList.toggle('expanded');
                });
            });

            // Обработчики для заголовков групп - раскрытие/сворачивание
            document.querySelectorAll('.apps-group-header').forEach(header => {
                header.addEventListener('click', function(e) {
                    if (e.target.closest('.apps-checkbox-container') || e.target.closest('.apps-actions-menu') || e.target.closest('.actions-menu')) {
                        return;
                    }

                    const groupContainer = this.closest('.apps-group');
                    if (!groupContainer) return;

                    groupContainer.classList.toggle('expanded');
                });
            });
        },

        restoreTableState() {
            // Восстанавливаем развернутые группы
            StateManager.state.expandedGroups.forEach(groupName => {
                const groupContainer = document.querySelector(`.apps-group[data-group="${groupName}"]`);
                if (groupContainer) {
                    groupContainer.classList.add('expanded');
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

            const groupContainer = document.querySelector(`.apps-group[data-group="${groupName}"]`);
            const childCheckboxes = groupContainer ? groupContainer.querySelectorAll('.apps-group-children .app-checkbox') : [];
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
                            ${[...apps].sort((a, b) => `${a.server_name}_${a.name}`.localeCompare(`${b.server_name}_${b.name}`)).map(app => `<span class="app-badge">${app.server_name}_${app.name}</span>`).join('')}
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
                checkboxesContainer.innerHTML = tags.map(tag => {
                    const tagStyle = [];
                    if (tag.border_color) tagStyle.push(`border-color: ${tag.border_color}`);
                    if (tag.text_color) tagStyle.push(`color: ${tag.text_color}`);
                    const styleAttr = tagStyle.length ? `style="${tagStyle.join('; ')}"` : '';
                    return `
                    <label class="tag-checkbox-label">
                        <input type="checkbox" value="${tag.name}" class="tag-filter-checkbox">
                        <span class="tag ${tag.css_class || ''}" ${styleAttr}>${tag.display_name || tag.name}</span>
                    </label>
                `;
                }).join('');
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

        /**
         * Инициализация обработчиков выпадающих меню - делегирование к DropdownHandlers
         */
        initDropdownHandlers() {
            window.DropdownHandlers.init();
        },

        /**
         * Закрывает все выпадающие меню - делегирование к DropdownHandlers
         */
        closeAllDropdowns() {
            window.DropdownHandlers.closeAll();
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

        /**
         * Инициализация обработчиков чекбоксов - делегирование к CheckboxHandlers
         */
        initCheckboxHandlers() {
            window.CheckboxHandlers.init({
                StateManager,
                DOMUtils,
                UIRenderer
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

        /**
         * Показывает модальное окно управления тегами - делегирование к TagsModal
         */
        async showBatchTagsModal(appIds) {
            await window.TagsModal.showBatchTagsModal(appIds, {
                loadApplications: () => this.loadApplications()
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

            // Применяем фильтр по тегам (включая унаследованные от группы)
            if (StateManager.state.selectedTags.length > 0) {
                filtered = filtered.filter(app => {
                    const ownTagNames = (app.tags || []).map(t => t.name);
                    const groupTagNames = (app.group_tags || []).map(t => t.name);
                    const allTagNames = [...ownTagNames, ...groupTagNames];

                    if (StateManager.state.tagOperator === 'AND') {
                        return StateManager.state.selectedTags.every(tagName => allTagNames.includes(tagName));
                    } else {
                        return StateManager.state.selectedTags.some(tagName => allTagNames.includes(tagName));
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

        /**
         * Инициализация обработчиков действий в таблице - делегирование к TableActions
         */
        initTableActions() {
            window.TableActions.init({
                ModalManager,
                DropdownHandlers: window.DropdownHandlers,
                showError
            });
            window.TableActions.setCallbacks({
                showAppInfo: (appId) => this.showAppInfo(appId),
                showGroupTagsModal: (groupId, groupName) => this.showGroupTagsModal(groupId, groupName),
                handleBatchAction: (appIds, action) => this.handleBatchAction(appIds, action),
                handleGroupUpdate: (groupName) => this.handleGroupUpdate(groupName),
                handleGroupAction: (groupName, action) => this.handleGroupAction(groupName, action)
            });
        },

        handleGroupUpdate(groupName) {
            const appIds = [];
            document.querySelectorAll(`.apps-group[data-group="${groupName}"] .apps-group-children .app-checkbox`).forEach(checkbox => {
                appIds.push(checkbox.dataset.appId);
            });
            
            if (appIds.length > 0) {
                ModalManager.showUpdateModal(appIds);
            }
        },

        handleGroupAction(groupName, action) {
            const appIds = [];
            document.querySelectorAll(`.apps-group[data-group="${groupName}"] .apps-group-children .app-checkbox`).forEach(checkbox => {
                appIds.push(checkbox.dataset.appId);
            });

            if (appIds.length > 0) {
                this.handleBatchAction(appIds, action);
            }
        },

        /**
         * Показывает модальное окно тегов группы - делегирование к TagsModal
         */
        async showGroupTagsModal(groupId, groupName) {
            await window.TagsModal.showGroupTagsModal(groupId, groupName, {
                loadApplications: () => this.loadApplications()
            });
        },

        /**
         * Показывает информацию о приложении - делегирование к InfoModal
         */
        async showAppInfo(appId) {
            await window.InfoModal.show(appId);
        },

        async loadApplications() {
            const listBody = document.getElementById('applications-list-body');
            if (listBody) {
                listBody.innerHTML = '<div class="apps-list-loading">Загрузка приложений...</div>';
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
        // Инициализация core модулей
        StateManager.init({ pageSize: CONFIG.PAGE_SIZE });
        ApiService.init({ showError, config: CONFIG });
        ArtifactsManager.init({ StateManager, ApiService, config: CONFIG });

        // Инициализация UI элементов
        UIRenderer.init();

        // Инициализация обработчиков событий
        EventHandlers.init();

        // Загрузка начальных данных
        EventHandlers.loadApplications();
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

    // Экспорт модулей (core модули уже экспортированы из своих файлов)
    window.EventHandlers = EventHandlers;
    window.UIRenderer = UIRenderer;
    window.ModalManager = ModalManager;

})();

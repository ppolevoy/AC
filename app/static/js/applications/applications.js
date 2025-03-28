/**
 * Faktura Apps - Модуль для страницы управления приложениями
 */

document.addEventListener('DOMContentLoaded', function() {
    // Глобальные переменные для хранения данных
    let allApplications = [];
    let filteredApplications = [];
    let currentPage = 1;
    let pageSize = 10;
    let selectedServerId = 'all';
    let sortColumn = 'name';
    let sortDirection = 'asc';
    let searchQuery = '';
    
    // DOM-элементы
    const serverDropdown = document.getElementById('server-selected');
    const serverList = document.getElementById('server-list');
    const searchInput = document.getElementById('search-input');
    const refreshBtn = document.getElementById('refresh-btn');
    const selectAllCheckbox = document.getElementById('select-all');
    const applicationsTableBody = document.getElementById('applications-table-body');
    const pageSizeSelect = document.getElementById('page-size-select');
    const paginationControls = document.getElementById('pagination-controls');
    
    // Кнопки действий
    const startBtn = document.getElementById('start-btn');
    const restartBtn = document.getElementById('restart-btn');
    const stopBtn = document.getElementById('stop-btn');
    const updateBtn = document.getElementById('update-btn');
    const unloadBtn = document.getElementById('unload-btn');
    
    // Инициализация страницы
    init();

    /**
     * Инициализация обработчиков событий
     */
    function init() {
        // Загружаем список серверов для выпадающего меню
        loadServers();
        
        // Загружаем список приложений
        loadApplications();
        
        // Обработчик выбора всех приложений
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', function() {
                const appCheckboxes = document.querySelectorAll('.app-checkbox');
                appCheckboxes.forEach(checkbox => {
                    checkbox.checked = this.checked;
                });
                updateActionButtonsState(this.checked);
            });
        }
        
        // Обработчик поиска
        if (searchInput) {
            searchInput.addEventListener('input', function() {
                searchQuery = this.value.trim();
                currentPage = 1;
                filterAndDisplayApplications();
            });
        }
        
        // Обработчик изменения размера страницы
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', function() {
                pageSize = parseInt(this.value);
                currentPage = 1;
                filterAndDisplayApplications();
            });
        }
        
        // Обработчик кнопки обновления
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function() {
                this.classList.add('rotating');
                loadApplications().finally(() => {
                    this.classList.remove('rotating');
                });
            });
        }
        
        // Обработчики сортировки
        document.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', function() {
                const currentSortColumn = sortColumn;
                sortColumn = this.getAttribute('data-sort');
                
                if (currentSortColumn === sortColumn) {
                    // Меняем направление сортировки
                    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    // По умолчанию сортируем по возрастанию
                    sortDirection = 'asc';
                }
                
                // Обновляем классы для отображения направления сортировки
                document.querySelectorAll('th.sortable').forEach(header => {
                    header.classList.remove('sorted-asc', 'sorted-desc');
                });
                
                this.classList.add(`sorted-${sortDirection}`);
                
                // Обновляем отображение приложений
                filterAndDisplayApplications();
            });
        });
        
        // Обработчики кнопок действий
        if (startBtn) {
            startBtn.addEventListener('click', function() {
                const selectedAppIds = getSelectedAppIds();
                if (selectedAppIds.length > 0) {
                    showConfirmActionModal(selectedAppIds, 'start');
                }
            });
        }
        
        if (restartBtn) {
            restartBtn.addEventListener('click', function() {
                const selectedAppIds = getSelectedAppIds();
                if (selectedAppIds.length > 0) {
                    showConfirmActionModal(selectedAppIds, 'restart');
                }
            });
        }
        
        if (stopBtn) {
            stopBtn.addEventListener('click', function() {
                const selectedAppIds = getSelectedAppIds();
                if (selectedAppIds.length > 0) {
                    showConfirmActionModal(selectedAppIds, 'stop');
                }
            });
        }
        
        if (updateBtn) {
            updateBtn.addEventListener('click', function() {
                const selectedAppIds = getSelectedAppIds();
                if (selectedAppIds.length > 0) {
                    showUpdateModal(selectedAppIds);
                }
            });
        }
        
        if (unloadBtn) {
            unloadBtn.addEventListener('click', function() {
                showNotification('Функция "Снять нагрузку" находится в разработке');
            });
        }
        
        // Деактивируем кнопки действий при загрузке страницы
        updateActionButtonsState(false);
    }
    
    /**
     * Загрузка списка серверов для выпадающего списка
     */
    async function loadServers() {
        try {
            const response = await fetch('/api/servers');
            const data = await response.json();
            
            if (data.success) {
                // Очищаем текущий список серверов
                while (serverList.children.length > 1) {
                    serverList.removeChild(serverList.lastChild);
                }
                
                // Добавляем серверы в выпадающий список
                data.servers.forEach(server => {
                    const serverItem = document.createElement('a');
                    serverItem.setAttribute('href', '#');
                    serverItem.setAttribute('data-server-id', server.id);
                    serverItem.textContent = server.name;
                    
                    serverItem.addEventListener('click', function(e) {
                        e.preventDefault();
                        selectServer(server.id, server.name);
                    });
                    
                    serverList.appendChild(serverItem);
                });
            } else {
                console.error('Ошибка при загрузке серверов:', data.error);
                showError('Не удалось загрузить список серверов');
            }
        } catch (error) {
            console.error('Ошибка при загрузке серверов:', error);
            showError('Не удалось загрузить список серверов');
        }
    }
    
    /**
     * Выбор сервера из выпадающего списка
     * @param {string} serverId - ID сервера
     * @param {string} serverName - Имя сервера
     */
    function selectServer(serverId, serverName) {
        selectedServerId = serverId;
        serverDropdown.innerHTML = `${serverName || 'Все серверы'} <span>▾</span>`;
        currentPage = 1;
        loadApplications();
    }
    
    /**
     * Загрузка списка приложений
     */
    async function loadApplications() {
        try {
            applicationsTableBody.innerHTML = '<tr><td colspan="6" class="table-loading">Загрузка приложений...</td></tr>';
            
            // Формирование URL с параметрами
            let url = '/api/applications';
            const params = new URLSearchParams();
            
            if (selectedServerId !== 'all') {
                params.append('server_id', selectedServerId);
            }
            
            if (params.toString()) {
                url += '?' + params.toString();
            }
            
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.success) {
                allApplications = data.applications;
                filterAndDisplayApplications();
            } else {
                console.error('Ошибка при загрузке приложений:', data.error);
                showError('Не удалось загрузить список приложений');
                applicationsTableBody.innerHTML = '<tr><td colspan="6" class="table-loading error">Ошибка загрузки приложений</td></tr>';
            }
        } catch (error) {
            console.error('Ошибка при загрузке приложений:', error);
            showError('Не удалось загрузить список приложений');
            applicationsTableBody.innerHTML = '<tr><td colspan="6" class="table-loading error">Ошибка загрузки приложений</td></tr>';
        }
    }
    
    /**
     * Фильтрация и отображение приложений
     */
    function filterAndDisplayApplications() {
        // Фильтрация по поисковому запросу
        if (searchQuery) {
            const query = searchQuery.toLowerCase();
            filteredApplications = allApplications.filter(app => 
                app.name.toLowerCase().includes(query) || 
                (app.version && app.version.toLowerCase().includes(query)) ||
                (app.server_name && app.server_name.toLowerCase().includes(query))
            );
        } else {
            filteredApplications = [...allApplications];
        }
        
        // Сортировка
        filteredApplications.sort((a, b) => {
            let valueA, valueB;
            
            if (sortColumn === 'name') {
                valueA = a.name.toLowerCase();
                valueB = b.name.toLowerCase();
            } else if (sortColumn === 'state') {
                valueA = a.status ? a.status.toLowerCase() : '';
                valueB = b.status ? b.status.toLowerCase() : '';
            }
            
            if (valueA < valueB) return sortDirection === 'asc' ? -1 : 1;
            if (valueA > valueB) return sortDirection === 'asc' ? 1 : -1;
            return 0;
        });
        
        // Пагинация
        const totalPages = Math.ceil(filteredApplications.length / pageSize);
        if (currentPage > totalPages && totalPages > 0) {
            currentPage = totalPages;
        }
        
        const startIndex = (currentPage - 1) * pageSize;
        const endIndex = Math.min(startIndex + pageSize, filteredApplications.length);
        const displayedApplications = filteredApplications.slice(startIndex, endIndex);
        
        // Очищаем текущую таблицу
        applicationsTableBody.innerHTML = '';
        
        if (displayedApplications.length === 0) {
            applicationsTableBody.innerHTML = '<tr><td colspan="6" class="table-loading">Нет приложений, соответствующих критериям поиска</td></tr>';
            updatePagination(0);
            return;
        }
        
        // Заполняем таблицу приложений
        displayedApplications.forEach(app => {
            const row = document.createElement('tr');
            
            // Статус приложения
            const statusDot = app.status === 'online' ? 
                '<span class="service-dot"></span>' : 
                '<span class="service-dot offline"></span>';
            
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
                        <div>Тип: ${app.type || 'Н/Д'}</div>
                    </div>
                </td>
                <td>${app.version || 'Н/Д'}</td>
                <td>${statusDot}</td>
                <td>${app.server_name || 'Н/Д'}</td>
                <td>
                    <div class="actions-menu">
                        <button class="actions-button">...</button>
                        <div class="actions-dropdown">
                            <a href="#" class="app-info-btn" data-app-id="${app.id}">Информация</a>
                            <a href="#" class="app-start-btn" data-app-id="${app.id}">Запустить</a>
                            <a href="#" class="app-stop-btn" data-app-id="${app.id}">Остановить</a>
                            <a href="#" class="app-restart-btn" data-app-id="${app.id}">Перезапустить</a>
                            <a href="#" class="app-update-btn" data-app-id="${app.id}">Обновить</a>
                        </div>
                    </div>
                </td>
            `;
            
            applicationsTableBody.appendChild(row);
        });
        
        // Обновляем пагинацию
        updatePagination(totalPages);
        
        // Добавляем обработчики событий для элементов таблицы
        setupTableEventHandlers();
    }
    
    /**
     * Обновление элементов пагинации
     * @param {number} totalPages - Общее количество страниц
     */
    function updatePagination(totalPages) {
        const pageNumberElement = paginationControls.querySelector('.page-number');
        const prevButton = paginationControls.querySelector('.prev-page');
        const nextButton = paginationControls.querySelector('.next-page');
        
        if (totalPages === 0) {
            pageNumberElement.textContent = '0';
            prevButton.disabled = true;
            nextButton.disabled = true;
            return;
        }
        
        pageNumberElement.textContent = currentPage;
        prevButton.disabled = currentPage === 1;
        nextButton.disabled = currentPage === totalPages;
        
        // Обработчики кнопок пагинации
        prevButton.onclick = function() {
            if (currentPage > 1) {
                currentPage--;
                filterAndDisplayApplications();
            }
        };
        
        nextButton.onclick = function() {
            if (currentPage < totalPages) {
                currentPage++;
                filterAndDisplayApplications();
            }
        };
    }
    
    /**
     * Обработчики событий для элементов таблицы
     */
    function setupTableEventHandlers() {
        // Раскрытие/скрытие детальной информации о приложении
        document.querySelectorAll('tbody tr').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                    return;
                }
                this.classList.toggle('expanded');
            });
        });
        
        // Обработчики чекбоксов
        const appCheckboxes = document.querySelectorAll('.app-checkbox');
        appCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', updateSelectAllState);
        });
        
        // Обработчики кнопок действий в выпадающем меню
        document.querySelectorAll('.app-info-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const appId = this.getAttribute('data-app-id');
                showAppInfoModal(appId);
            });
        });
        
        document.querySelectorAll('.app-start-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const appId = this.getAttribute('data-app-id');
                showConfirmActionModal([appId], 'start');
            });
        });
        
        document.querySelectorAll('.app-stop-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const appId = this.getAttribute('data-app-id');
                showConfirmActionModal([appId], 'stop');
            });
        });
        
        document.querySelectorAll('.app-restart-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const appId = this.getAttribute('data-app-id');
                showConfirmActionModal([appId], 'restart');
            });
        });
        
        document.querySelectorAll('.app-update-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const appId = this.getAttribute('data-app-id');
                showUpdateModal([appId]);
            });
        });
    }
    
    /**
     * Обновление состояния чекбокса "Выбрать все"
     */
    function updateSelectAllState() {
        const appCheckboxes = document.querySelectorAll('.app-checkbox');
        const checkedCount = document.querySelectorAll('.app-checkbox:checked').length;
        
        if (checkedCount === 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCount === appCheckboxes.length) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        }
        
        // Активация/деактивация кнопок действий в зависимости от выбранных приложений
        updateActionButtonsState(checkedCount > 0);
    }
    
    /**
     * Активация/деактивация кнопок действий
     * @param {boolean} hasSelection - Есть ли выбранные приложения
     */
    function updateActionButtonsState(hasSelection) {
        if (startBtn) startBtn.disabled = !hasSelection;
        if (restartBtn) restartBtn.disabled = !hasSelection;
        if (stopBtn) stopBtn.disabled = !hasSelection;
        if (updateBtn) updateBtn.disabled = !hasSelection;
        if (unloadBtn) unloadBtn.disabled = !hasSelection;
        
        // Добавляем/удаляем класс для визуального отображения неактивных кнопок
        [startBtn, restartBtn, stopBtn, updateBtn, unloadBtn].forEach(btn => {
            if (!btn) return;
            
            if (hasSelection) {
                btn.classList.remove('disabled');
            } else {
                btn.classList.add('disabled');
            }
        });
    }
    
    /**
     * Получение списка выбранных приложений
     * @returns {Array} Массив ID выбранных приложений
     */
    function getSelectedAppIds() {
        const selectedCheckboxes = document.querySelectorAll('.app-checkbox:checked');
        return Array.from(selectedCheckboxes).map(checkbox => checkbox.getAttribute('data-app-id'));
    }
    
    /**
     * Получение информации о приложении по ID
     * @param {string} appId - ID приложения
     * @returns {Object} Объект приложения
     */
    function getAppById(appId) {
        return allApplications.find(app => app.id == appId);
    }
    
    /**
     * Модальное окно с информацией о приложении
     * @param {string} appId - ID приложения
     */
    async function showAppInfoModal(appId) {
        try {
            const response = await fetch(`/api/applications/${appId}`);
            const data = await response.json();
            
            if (!data.success) {
                console.error('Ошибка при получении информации о приложении:', data.error);
                showError('Не удалось получить информацию о приложении');
                return;
            }
            
            const app = data.application;
            
            // Клонируем шаблон модального окна
            const modalTemplate = document.getElementById('app-info-modal-template');
            if (!modalTemplate) {
                console.error('Шаблон модального окна не найден');
                return;
            }
            
            const modalContent = document.importNode(modalTemplate.content, true);
            
            // Заполняем информацию о приложении
            modalContent.querySelector('.app-name').textContent = app.name;
            modalContent.querySelector('.app-type').textContent = app.app_type || 'Не указан';
            modalContent.querySelector('.app-status').textContent = app.status || 'Неизвестно';
            modalContent.querySelector('.app-version').textContent = app.version || 'Не указана';
            modalContent.querySelector('.app-server').textContent = app.server_name || 'Не указан';
            modalContent.querySelector('.app-ip').textContent = app.ip || 'Не указан';
            modalContent.querySelector('.app-port').textContent = app.port || 'Не указан';
            modalContent.querySelector('.app-path').textContent = app.path || 'Не указан';
            modalContent.querySelector('.app-log-path').textContent = app.log_path || 'Не указан';
            modalContent.querySelector('.app-distr-path').textContent = app.distr_path || 'Не указан';
            
            // Путь к playbook для обновления
            const playbookInput = modalContent.querySelector('.app-playbook-path');
            if (playbookInput) {
                playbookInput.value = app.update_playbook_path || '';
            }
            
            // Заполняем список событий
            const eventsList = modalContent.querySelector('.events-list');
            if (eventsList) {
                if (app.events && app.events.length > 0) {
                    const eventsTable = document.createElement('table');
                    eventsTable.className = 'events-table';
                    
                    // Заголовок таблицы
                    const headerRow = document.createElement('tr');
                    headerRow.innerHTML = `
                        <th>Дата</th>
                        <th>Тип</th>
                        <th>Статус</th>
                    `;
                    eventsTable.appendChild(headerRow);
                    
                    // Строки с событиями
                    app.events.forEach(event => {
                        const eventRow = document.createElement('tr');
                        eventRow.className = `event-row ${event.status}`;
                        
                        const eventDate = new Date(event.timestamp);
                        
                        eventRow.innerHTML = `
                            <td>${eventDate.toLocaleString()}</td>
                            <td>${event.event_type}</td>
                            <td>${event.status}</td>
                        `;
                        
                        eventRow.setAttribute('title', event.description || '');
                        eventsTable.appendChild(eventRow);
                    });
                    
                    eventsList.appendChild(eventsTable);
                } else {
                    eventsList.innerHTML = '<p>Нет записей о событиях</p>';
                }
            }
            
            // Обработчик сохранения пути к playbook
            const savePlaybookBtn = modalContent.querySelector('#save-playbook-path');
            if (savePlaybookBtn && playbookInput) {
                savePlaybookBtn.addEventListener('click', async function() {
                    const playbookPath = playbookInput.value.trim();
                    
                    try {
                        const response = await fetch(`/api/applications/${appId}/update_playbook`, {
                            method: 'PUT',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                playbook_path: playbookPath
                            })
                        });
                        
                        const data = await response.json();
                        
                        if (data.success) {
                            showNotification('Путь к плейбуку успешно сохранен');
                        } else {
                            console.error('Ошибка при сохранении пути к плейбуку:', data.error);
                            showError(data.error || 'Не удалось сохранить путь к плейбуку');
                        }
                    } catch (error) {
                        console.error('Ошибка при сохранении пути к плейбуку:', error);
                        showError('Не удалось сохранить путь к плейбуку');
                    }
                });
            }
            
            // Отображаем модальное окно
            window.showModal(`Информация о приложении: ${app.name}`, modalContent);
            
        } catch (error) {
            console.error('Ошибка при получении информации о приложении:', error);
            showError('Не удалось получить информацию о приложении');
        }
    }
    
    /**
     * Модальное окно подтверждения действия
     * @param {Array} appIds - Массив ID приложений
     * @param {string} action - Действие (start, stop, restart)
     */
    function showConfirmActionModal(appIds, action) {
        if (!appIds || appIds.length === 0) {
            showError('Не выбрано ни одного приложения');
            return;
        }
        
        // Получаем название действия с помощью функции из utils.js
        const actionName = getActionName(action);
        
        // Клонируем шаблон модального окна
        const modalTemplate = document.getElementById('confirm-action-modal-template');
        if (!modalTemplate) {
            console.error('Шаблон модального окна не найден');
            return;
        }
        
        const modalContent = document.importNode(modalTemplate.content, true);
        
        // Устанавливаем название действия
        const actionNameElem = modalContent.querySelector('.action-name');
        if (actionNameElem) {
            actionNameElem.textContent = actionName;
        }
        
        // Заполняем список приложений
        const appList = modalContent.querySelector('.app-list');
        if (appList) {
            const appListUl = document.createElement('ul');
            
            appIds.forEach(appId => {
                const app = getAppById(appId);
                if (app) {
                    const li = document.createElement('li');
                    li.textContent = `${app.name} (${app.server_name || 'Неизвестный сервер'})`;
                    appListUl.appendChild(li);
                }
            });
            
            appList.appendChild(appListUl);
        }
        
        // Обработчик для кнопки подтверждения
        const confirmBtn = modalContent.querySelector('.confirm-btn');
        if (confirmBtn) {
            confirmBtn.textContent = `Подтвердить (${appIds.length})`;
            
            confirmBtn.addEventListener('click', async function() {
                try {
                    const response = await fetch('/api/applications/bulk/manage', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            action: action,
                            app_ids: appIds
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        window.closeModal();
                        
                        // Анализируем результаты
                        const successCount = data.results.filter(r => r.success).length;
                        const errorCount = data.results.length - successCount;
                        
                        if (errorCount === 0) {
                            showNotification(`Действие "${actionName}" успешно выполнено для всех выбранных приложений`);
                        } else if (successCount === 0) {
                            showError(`Не удалось выполнить действие "${actionName}" ни для одного из выбранных приложений`);
                        } else {
                            showNotification(`Действие "${actionName}" выполнено для ${successCount} из ${data.results.length} приложений`);
                        }
                        
                        // Обновляем список приложений
                        loadApplications();
                    } else {
                        console.error('Ошибка при выполнении действия:', data.error);
                        showError(data.error || `Не удалось выполнить действие "${actionName}"`);
                    }
                } catch (error) {
                    console.error('Ошибка при выполнении действия:', error);
                    showError(`Не удалось выполнить действие "${actionName}"`);
                }
            });
        }
        
        // Отображаем модальное окно
        window.showModal(`${actionName.charAt(0).toUpperCase() + actionName.slice(1)} приложения`, modalContent);
    }
    
    /**
     * Модальное окно обновления приложения
     * @param {Array} appIds - Массив ID приложений
     */
    function showUpdateModal(appIds) {
        if (!appIds || appIds.length === 0) {
            showError('Не выбрано ни одного приложения');
            return;
        }
        
        // Клонируем шаблон модального окна
        const modalTemplate = document.getElementById('update-modal-template');
        if (!modalTemplate) {
            console.error('Шаблон модального окна не найден');
            return;
        }
        
        const modalContent = document.importNode(modalTemplate.content, true);
        
        const updateForm = modalContent.querySelector('#update-form');
        const tabsContainer = modalContent.querySelector('#update-tabs');
        
        // Если выбрано несколько приложений, которые не относятся к одной группе,
        // создаем вкладки для каждого приложения
        if (appIds.length > 1) {
            const appGroups = {};
            
            // Группируем приложения по имени группы
            appIds.forEach(appId => {
                const app = getAppById(appId);
                if (app) {
                    const groupName = app.group_name || app.name;
                    if (!appGroups[groupName]) {
                        appGroups[groupName] = [];
                    }
                    appGroups[groupName].push(app);
                }
            });
            
            // Если есть несколько групп, создаем вкладки
            if (Object.keys(appGroups).length > 1) {
                // Показываем контейнер с вкладками
                if (tabsContainer) {
                    tabsContainer.style.display = 'flex';
                }
                
                // Создаем вкладки
                Object.keys(appGroups).forEach((groupName, index) => {
                    const tab = document.createElement('div');
                    tab.className = `modal-tab ${index === 0 ? 'active' : ''}`;
                    tab.textContent = groupName;
                    tab.setAttribute('data-group', groupName);
                    tabsContainer.appendChild(tab);
                    
                    // Обработчик клика по вкладке
                    tab.addEventListener('click', function() {
                        const activeTab = tabsContainer.querySelector('.modal-tab.active');
                        if (activeTab) {
                            activeTab.classList.remove('active');
                        }
                        tab.classList.add('active');
                        
                        // Обновляем форму для выбранной группы
                        updateFormForGroup(groupName);
                    });
                });
                
                // Функция для обновления формы в зависимости от выбранной группы
                function updateFormForGroup(groupName) {
                    const apps = appGroups[groupName];
                    const appIds = apps.map(app => app.id);
                    
                    // Обновляем скрытое поле с ID приложений
                    let appIdsInput = updateForm.querySelector('input[name="app-ids"]');
                    if (!appIdsInput) {
                        appIdsInput = document.createElement('input');
                        appIdsInput.type = 'hidden';
                        appIdsInput.name = 'app-ids';
                        updateForm.appendChild(appIdsInput);
                    }
                    appIdsInput.value = appIds.join(',');
                    
                    // Обновляем заголовок формы
                    const formTitle = updateForm.querySelector('.form-title');
                    if (formTitle) {
                        formTitle.textContent = `Обновление ${apps.length} приложений группы "${groupName}"`;
                    }
                    
                    // Если приложения одного типа, предлагаем путь к дистрибутиву по умолчанию
                    const firstApp = apps[0];
                    if (firstApp && firstApp.distr_path) {
                        const distrUrlInput = updateForm.querySelector('#distr-url');
                        if (distrUrlInput) {
                            distrUrlInput.value = firstApp.distr_path;
                            distrUrlInput.placeholder = 'URL или путь к дистрибутиву';
                        }
                    }
                }
                
                // Инициализируем форму для первой группы
                updateFormForGroup(Object.keys(appGroups)[0]);
            } else {
                // Если все приложения одной группы, создаем простую форму
                setupSingleUpdateForm(appIds);
            }
        } else {
            // Если выбрано только одно приложение, создаем простую форму
            setupSingleUpdateForm(appIds);
        }
        
        // Настройка формы для одного приложения или одной группы
        function setupSingleUpdateForm(appIds) {
            // Скрываем контейнер с вкладками
            if (tabsContainer) {
                tabsContainer.style.display = 'none';
            }
            
            // Добавляем скрытое поле с ID приложений
            const appIdsInput = document.createElement('input');
            appIdsInput.type = 'hidden';
            appIdsInput.name = 'app-ids';
            appIdsInput.value = appIds.join(',');
            updateForm.appendChild(appIdsInput);
            
            // Если это одно приложение, предлагаем путь к дистрибутиву по умолчанию
            if (appIds.length === 1) {
                const app = getAppById(appIds[0]);
                if (app && app.distr_path) {
                    const distrUrlInput = updateForm.querySelector('#distr-url');
                    if (distrUrlInput) {
                        distrUrlInput.value = app.distr_path;
                        distrUrlInput.placeholder = 'URL или путь к дистрибутиву';
                    }
                }
            }
        }
        
        // Обработчик отправки формы
        if (updateForm) {
            updateForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const appIdsInput = updateForm.querySelector('input[name="app-ids"]');
                const distrUrlInput = updateForm.querySelector('#distr-url');
                const restartModeInputs = updateForm.querySelectorAll('input[name="restart-mode"]');
                
                if (!appIdsInput || !distrUrlInput) {
                    showError('Ошибка в форме обновления');
                    return;
                }
                
                const appIds = appIdsInput.value.split(',').map(id => parseInt(id.trim()));
                const distrUrl = distrUrlInput.value.trim();
                
                let restartMode = 'restart'; // По умолчанию
                for (const input of restartModeInputs) {
                    if (input.checked) {
                        restartMode = input.value;
                        break;
                    }
                }
                
                if (!distrUrl) {
                    showError('Укажите URL дистрибутива');
                    return;
                }
                
                try {
                    // Создаем массив запросов для всех приложений
                    const updatePromises = appIds.map(appId => 
                        fetch(`/api/applications/${appId}/update`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                distr_url: distrUrl,
                                restart_mode: restartMode
                            })
                        }).then(response => response.json())
                    );
                    
                    // Ждем выполнения всех запросов
                    const results = await Promise.all(updatePromises);
                    
                    // Анализируем результаты
                    const successCount = results.filter(result => result.success).length;
                    const errorCount = results.length - successCount;
                    
                    // Закрываем модальное окно
                    window.closeModal();
                    
                    if (errorCount === 0) {
                        showNotification(`Обновление успешно запущено для всех выбранных приложений`);
                    } else if (successCount === 0) {
                        showError(`Не удалось запустить обновление ни для одного из выбранных приложений`);
                    } else {
                        showNotification(`Обновление запущено для ${successCount} из ${results.length} приложений`);
                    }
                    
                    // Обновляем список приложений
                    loadApplications();
                    
                } catch (error) {
                    console.error('Ошибка при обновлении приложений:', error);
                    showError('Не удалось запустить обновление приложений');
                }
            });
        }
        
        // Отображаем модальное окно
        const title = appIds.length === 1 ? 
            `Обновление приложения: ${getAppById(appIds[0])?.name || 'Приложение'}` : 
            `Обновление ${appIds.length} приложений`;
        
        window.showModal(title, modalContent);
    }
});
        
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
	let groupingEnabled = true;	
	let activeDropdown = null;
	let dropdownOverlay = null;    
	
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
    
    // Глобальный кэш артефактов с временными метками
    const artifactsCache = {};
    const CACHE_LIFETIME = 5 * 60 * 1000; // 5 минут в миллисекундах

    // Настройка времени анимаций
    const LOADING_CONFIG = {
        MIN_LOADING_TIME: 800,      // Минимальное время показа загрузчика (ms)
        PROGRESS_STEPS: {
            FETCH_START: 30,         // Прогресс при начале загрузки (%)
            FETCH_COMPLETE: 70,      // Прогресс после получения данных (%)
            PARSE_COMPLETE: 100      // Прогресс после обработки (%)
        },
        CACHE_LIFETIME: 5 * 60 * 1000, // Время жизни кэша (5 минут)
        ANIMATION_DELAYS: {
            FADE_IN: 100,            // Задержка fade-in (ms)
            FIELD_STAGGER: 100       // Задержка между полями (ms)
        }
    };
    

    // Инициализация страницы
    init();
    initClickDropdowns();
    /**
     * Инициализация обработчиков событий
     */
    function init() {
        // Загружаем список серверов для выпадающего меню
        loadServers();
        
        // Загружаем список приложений
        loadApplications();

		// Инициализируем обработчики выпадающих меню
		initDropdownHandlers();		

		const groupToggleBtn = document.getElementById('group-toggle-btn');
		if (groupToggleBtn) {
			groupingEnabled = groupToggleBtn.classList.contains('active');
			
			groupToggleBtn.addEventListener('click', function() {
				this.classList.toggle('active');
				groupingEnabled = this.classList.contains('active');
				
				// Сбрасываем страницу при изменении группировки
				currentPage = 1;
				filterAndDisplayApplications();
			});
		}
        
        // Обработчик выбора всех приложений
		if (selectAllCheckbox) {
			selectAllCheckbox.addEventListener('change', function() {
				const isChecked = this.checked;
				
				// Обновляем все видимые чекбоксы приложений
				const appCheckboxes = document.querySelectorAll('.app-checkbox:not(.hidden .app-checkbox)');
				appCheckboxes.forEach(checkbox => {
					if (!checkbox.closest('tr.hidden')) {
						checkbox.checked = isChecked;
					}
				});
				
				// Обновляем все видимые чекбоксы групп
				const groupCheckboxes = document.querySelectorAll('.group-checkbox');
				groupCheckboxes.forEach(checkbox => {
					if (!checkbox.closest('tr.hidden')) {
						checkbox.checked = isChecked;
						checkbox.indeterminate = false;
						
						// Также обновляем все дочерние чекбоксы
						const groupName = checkbox.getAttribute('data-group');
						const childCheckboxes = document.querySelectorAll(`.child-row[data-parent="${groupName}"] .app-checkbox`);
						childCheckboxes.forEach(childBox => {
							childBox.checked = isChecked;
						});
					}
				});
				
				updateActionButtonsState(isChecked);
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
            // Сохраняем текущее состояние развернутых групп перед обновлением
            saveTableState();
            
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
                
                // Восстанавливаем состояние таблицы после отображения данных
                restoreTableState();
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
		
		// Очищаем текущую таблицу
		applicationsTableBody.innerHTML = '';
		
		if (filteredApplications.length === 0) {
			applicationsTableBody.innerHTML = '<tr><td colspan="6" class="table-loading">Нет приложений, соответствующих критериям поиска</td></tr>';
			updatePagination(0);
			return;
		}
		
		// Если группировка включена, отображаем сгруппированные приложения
		if (groupingEnabled) {
			displayGroupedApplications(filteredApplications);
		} else {
			displayFlatApplications(filteredApplications);
		}
		
		// Добавляем обработчики событий для элементов таблицы
		setupTableEventHandlers();
	}
	
	// Функция для отображения приложений без группировки
	function displayFlatApplications(applications) {
		// Пагинация
		const totalPages = Math.ceil(applications.length / pageSize);
		if (currentPage > totalPages && totalPages > 0) {
			currentPage = totalPages;
		}
		
		const startIndex = (currentPage - 1) * pageSize;
		const endIndex = Math.min(startIndex + pageSize, applications.length);
		const displayedApplications = applications.slice(startIndex, endIndex);
		
		// Отображаем приложения
		displayedApplications.forEach(app => {
			const row = createApplicationRow(app, false);
			applicationsTableBody.appendChild(row);
		});
		
		// Обновляем пагинацию
		updatePagination(totalPages);
	}

	/**
	 * Отображение сгруппированных приложений
	 * @param {Array} applications - массив приложений для отображения
	 */
	function displayGroupedApplications(applications) {
		// Группируем приложения по имени группы
		const groups = {};
		
		applications.forEach(app => {
			const groupName = app.group_name || app.name;
			if (!groups[groupName]) {
				groups[groupName] = [];
			}
			groups[groupName].push(app);
		});
		
		// Convert groups to array for sorting
		const groupEntries = Object.entries(groups).map(([name, apps]) => ({
			name,
			apps,
			count: apps.length
		}));
		
		// Sort groups by name
		groupEntries.sort((a, b) => a.name.localeCompare(b.name));
		
		// Pagination
		const totalGroups = groupEntries.length;
		const totalPages = Math.ceil(totalGroups / pageSize);
		
		if (currentPage > totalPages && totalPages > 0) {
			currentPage = totalPages;
		}
		
		const startIndex = (currentPage - 1) * pageSize;
		const endIndex = Math.min(startIndex + pageSize, totalGroups);
		const displayedGroups = groupEntries.slice(startIndex, endIndex);
		
		// Display the groups
		displayedGroups.forEach(group => {
			// If only one application in group, show as regular row
			if (group.count === 1) {
				const appRow = createApplicationRow(group.apps[0], false);
				applicationsTableBody.appendChild(appRow);
				return;
			}
			
			// Create the group row
			const groupRow = createGroupRow(group.name, group.apps);
			applicationsTableBody.appendChild(groupRow);
			
			// Create the wrapper row for child elements
			const wrapperRow = document.createElement('tr');
			wrapperRow.className = 'child-wrapper';
			wrapperRow.setAttribute('data-group', group.name);
			
			// Create a cell that spans all columns
			const wrapperCell = document.createElement('td');
			wrapperCell.setAttribute('colspan', '6'); // Adjust based on your table columns
			
			// Create the container for the nested table
			const childContainer = document.createElement('div');
			childContainer.className = 'child-container';
			
			// Create the nested table
			const childTable = document.createElement('table');
			childTable.className = 'child-table';
			
			// Create table body
			const childTableBody = document.createElement('tbody');
			
			// Create rows for each application in the group
            group.apps.forEach(app => {
                const childRow = document.createElement('tr');
                childRow.className = 'app-child-row';
                childRow.setAttribute('data-app-id', app.id);
                childRow.setAttribute('data-parent', group.name);
                
                const statusDot = app.status === 'online' ? 
                    '<span class="service-dot"></span>' : 
                    '<span class="service-dot offline"></span>';
                
                childRow.innerHTML = `
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
                            <div>Путь к дистрибутиву: ${app.distr_path || 'Н/Д'}</div>
                        </div>
                    </td>
                    <td>${app.version || 'Н/Д'}</td>
                    <td>${statusDot} ${app.status}</td>
                    <td>${app.server_name || 'Н/Д'}</td>
                    <td>
                        <div class="actions-menu">
                            <button class="actions-button">...</button>
                            <div class="actions-dropdown">
                                ${createActionMenuItems(app)}
                            </div>
                        </div>
                    </td>
                `;
				
				// Добавляем обработчик клика непосредственно для этой строки
                childRow.addEventListener('click', function(e) {
                    if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                        return;
                    }
                    this.classList.toggle('expanded');
                });
                
                childTableBody.appendChild(childRow);
            });
			
			// Assemble the nested structure
			childTable.appendChild(childTableBody);
			childContainer.appendChild(childTable);
			wrapperCell.appendChild(childContainer);
			wrapperRow.appendChild(wrapperCell);
			
			// Add wrapper row to the table
			applicationsTableBody.appendChild(wrapperRow);
		});
		
    setupAppActionButtons();
    setupGroupActionButtons();
    
    // Обновляем пагинацию
    updatePagination(totalPages);
	}

	// Создание строки группы
	function createGroupRow(groupName, groupApps) {
		const row = document.createElement('tr');
		row.className = 'group-row';
		row.setAttribute('data-group', groupName);
		
		// Проверяем версии в группе
		const versions = new Set(groupApps.map(app => app.version || '*'));
		const versionText = versions.size === 1 ? 
			(groupApps[0].version || '*') : 
			'<span class="version-different">*</span>';
		
		// Проверяем статус всех приложений в группе
		const hasOffline = groupApps.some(app => app.status !== 'online');
		const statusDot = hasOffline ? 
			'<span class="service-dot offline"></span>' : 
			'<span class="service-dot"></span>';
		
		// Сервер для группы (берем из первого приложения)
		const serverName = groupApps[0].server_name || 'Н/Д';
		
		row.innerHTML = `
			<td>
				<div class="checkbox-container">
					<label class="custom-checkbox">
						<input type="checkbox" class="group-checkbox" data-group="${groupName}">
						<span class="checkmark"></span>
					</label>
				</div>
			</td>
			<td class="service-name">
				<div class="group-name-container">
					<span class="group-toggle">▶</span>
					<span class="group-name">${groupName} (${groupApps.length})</span>
				</div>
			</td>
			<td>${versionText}</td>
			<td>${statusDot}</td>
			<td>${serverName}</td>
			<td>
				<div class="actions-menu">
					<button class="actions-button">...</button>
					<div class="actions-dropdown">
						<a href="#" class="group-info-btn" data-group="${groupName}">Информация</a>
						<a href="#" class="group-start-btn" data-group="${groupName}">Запустить все</a>
						<a href="#" class="group-stop-btn" data-group="${groupName}">Остановить все</a>
						<a href="#" class="group-restart-btn" data-group="${groupName}">Перезапустить все</a>
						<a href="#" class="group-update-btn" data-group="${groupName}">Обновить все</a>
					</div>
				</div>
			</td>
		`;
		
		return row;
	}

	// Создание строки приложения
	function createApplicationRow(app, isChild) {
		const row = document.createElement('tr');
		row.className = isChild ? 'app-row child-row' : 'app-row';
		row.setAttribute('data-app-id', app.id);
		row.setAttribute('data-app-name', app.name.toLowerCase());
		
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
            <td class="service-name ${isChild ? 'child-indent' : ''}">
                ${app.name}
                <div class="dist-details">
                    <div>Время запуска: ${app.start_time ? new Date(app.start_time).toLocaleString() : 'Н/Д'}</div>
                    <div>Путь приложения: ${app.path || 'Н/Д'}</div>
                    <div>Путь к дистрибутиву: ${app.distr_path || 'Н/Д'}</div>
                </div>
            </td>
            <td>${app.version || 'Н/Д'}</td>
            <td>${statusDot} ${app.status || 'Н/Д'}</td>
            <td>${app.server_name || 'Н/Д'}</td>
            <td>
                <div class="actions-menu">
                    <button class="actions-button">...</button>
                    <div class="actions-dropdown">
                        ${createActionMenuItems(app)}
                    </div>
                </div>
            </td>
        `;
		
		return row;
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
        // Добавляем функцию для привязки обработчиков к дочерним строкам
        function addChildRowHandlers() {
            document.querySelectorAll('.app-child-row').forEach(row => {
                // Сначала удаляем все существующие обработчики клика
                const newRow = row.cloneNode(true);
                row.parentNode.replaceChild(newRow, row);
                
                // Теперь добавляем новый обработчик
                newRow.addEventListener('click', function(e) {
                    if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                        return;
                    }
                    this.classList.toggle('expanded');
                });
            });
        }
        
        // Вызываем эту функцию при инициализации
        addChildRowHandlers();
        // Раскрытие/скрытие детальной информации о приложении
        document.querySelectorAll('tbody tr').forEach(row => {
            if (row.classList.contains('child-wrapper') || row.classList.contains('group-row')) {
                return;
            }
            
            row.addEventListener('click', function(e) {
                if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                    return;
                }
                this.classList.toggle('expanded');
            });
        });
        
        // Добавляем обработчики для строк внутри дочерних таблиц
        document.querySelectorAll('.child-table tbody tr').forEach(row => {
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
        
        // Раскрытие/скрытие группы
        document.querySelectorAll('.group-row').forEach(row => {
            row.addEventListener('click', function(e) {
                // Игнорируем клики на чекбоксы и кнопки действий
                if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
                    return;
                }
                
                const groupName = this.getAttribute('data-group');
                
                // Переключаем класс для анимации стрелки
                this.classList.toggle('expanded');
                
                // Обновляем отображение стрелки явно
                const toggle = this.querySelector('.group-toggle');
                if (toggle) {
                    if (this.classList.contains('expanded')) {
                        toggle.style.transform = 'rotate(90deg)';
                    } else {
                        toggle.style.transform = 'rotate(0deg)';
                    }
                }
                
                // Находим и переключаем видимость строки-обертки с дочерними элементами
                const wrapperRow = document.querySelector(`.child-wrapper[data-group="${groupName}"]`);
                if (wrapperRow) {
                    wrapperRow.style.display = (wrapperRow.style.display === 'none' || wrapperRow.style.display === '') ? 'table-row' : 'none';
                }
            });
        });
        
        // Чекбокс группы выбирает/снимает все дочерние элементы
        document.querySelectorAll('.group-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                const groupName = this.getAttribute('data-group');
                const isChecked = this.checked;
                
                // Выбираем/снимаем все дочерние чекбоксы в nested table
                const childCheckboxes = document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`);
                childCheckboxes.forEach(childBox => {
                    childBox.checked = isChecked;
                });
                
                // Обновляем состояние "Выбрать все"
                updateSelectAllState();
            });
        });
        
        // Чекбокс приложения обновляет состояние чекбокса группы
        document.querySelectorAll('.child-wrapper .app-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                const parentGroup = this.closest('.child-wrapper').getAttribute('data-group');
                updateGroupCheckboxState(parentGroup);
                updateSelectAllState();
            });
        });
        
        setupAppActionButtons();
        
        setupGroupActionButtons();
    }

    /**
     * Устанавливает обработчики для кнопок действий приложений
     */
    function setupAppActionButtons() {
        // Обработчики для кнопок в выпадающем меню приложений как в основной таблице, так и в дочерней
        document.querySelectorAll('.app-info-btn, .app-start-btn, .app-stop-btn, .app-restart-btn, .app-update-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                
                if (this.classList.contains('disabled')) {
                    return;
                }
                
                const appId = this.getAttribute('data-app-id');
                const action = this.getAttribute('data-action') || 
                            (this.className.includes('info') ? 'info' :
                            this.className.includes('start') ? 'start' :
                            this.className.includes('stop') ? 'stop' :
                            this.className.includes('restart') ? 'restart' :
                            this.className.includes('update') ? 'update' : null);
                
                const app = getAppById(appId);
                if (!app) {
                    console.error(`Не удалось найти приложение с ID: ${appId}`);
                    return;
                }
                
                if (action !== 'info' && action !== 'update' && !isActionAvailable(app, action)) {
                    const statusMsg = app.status === 'online' ? 'уже запущено' : 'не запущено';
                    showError(`Невозможно выполнить действие "${action}" для приложения, которое ${statusMsg}`);
                    return;
                }
                
                switch(action) {
                    case 'info':
                        showAppInfoModal(appId);
                        break;
                    case 'start':
                    case 'stop':
                    case 'restart':
                        showConfirmActionModal([appId], action);
                        break;
                    case 'update':
                        showUpdateModal([appId]);
                        break;
                }
            });
        });
    }

    /**
     * Устанавливает обработчики для кнопок действий групп
     */
    function setupGroupActionButtons() {
        // ОБРАБОТЧИКИ ДЛЯ ГРУППОВЫХ ДЕЙСТВИЙ
        document.querySelectorAll('.group-info-btn, .group-start-btn, .group-stop-btn, .group-restart-btn, .group-update-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                
                if (this.classList.contains('disabled')) {
                    return;
                }
                
                const groupName = this.getAttribute('data-group');
                const action = this.getAttribute('data-action') || 
                            (this.className.includes('info') ? 'info' :
                            this.className.includes('start') ? 'start' :
                            this.className.includes('stop') ? 'stop' :
                            this.className.includes('restart') ? 'restart' :
                            this.className.includes('update') ? 'update' : null);
                
                handleGroupAction(groupName, action);
            });
        });
    }
    
    /**
     * Обновление состояния чекбокса "Выбрать все"
     */
    function updateSelectAllState() {
        // Учитываем и групповые, и обычные чекбоксы
        const appCheckboxes = document.querySelectorAll('.app-checkbox:not(.hidden .app-checkbox)');
        const groupCheckboxes = document.querySelectorAll('.group-checkbox');
        
        // Теперь нужно учитывать чекбоксы в обычных строках и в nested table
        const allVisibleCheckboxes = [...appCheckboxes, ...groupCheckboxes].filter(
            checkbox => !checkbox.closest('tr.hidden') && 
                    (!checkbox.closest('.child-wrapper') || 
                    checkbox.closest('.child-wrapper').style.display !== 'none')
        );
        
        const checkedCount = allVisibleCheckboxes.filter(checkbox => 
            checkbox.checked || checkbox.indeterminate
        ).length;
        
        if (checkedCount === 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        } else if (checkedCount === allVisibleCheckboxes.length) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        }
        
        // Активация/деактивация кнопок действий
        updateActionButtonsState(checkedCount > 0);
    }
	
    /**
     * Обновление состояния чекбокса группы
     * @param {string} groupName - имя группы
     */
    function updateGroupCheckboxState(groupName) {
        const groupCheckbox = document.querySelector(`.group-checkbox[data-group="${groupName}"]`);
        if (!groupCheckbox) return;
        
        const childCheckboxes = document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`);
        const checkedCount = document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox:checked`).length;
        
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
    }


    /**
     * Обработка действий над группой
     * @param {string} groupName - имя группы
     * @param {string} action - действие (info, start, stop, restart, update)
     */
    function handleGroupAction(groupName, action) {
        const appIds = [];
        document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`).forEach(checkbox => {
            appIds.push(checkbox.getAttribute('data-app-id'));
        });
        
        if (appIds.length === 0) {
            showError('Не найдены приложения в группе');
            return;
        }
        
        const appsInGroup = appIds.map(id => getAppById(id)).filter(app => app);
        
        if (action !== 'info' && action !== 'update' && !isGroupActionAvailable(appsInGroup, action)) {
            let errorMsg = 'Это действие недоступно для текущего состояния приложений в группе.';
            
            switch(action) {
                case 'start':
                    errorMsg = 'Невозможно запустить: все приложения в группе уже запущены.';
                    break;
                case 'stop':
                case 'restart':
                    errorMsg = 'Невозможно выполнить: в группе нет запущенных приложений.';
                    break;
            }
            
            showError(errorMsg);
            return;
        }
        
        if (action === 'info') {
            showNotification('Информация о группе пока не реализована');
        } else if (action === 'update') {
            showUpdateModal(appIds);
        } else {
            const filteredAppIds = appsInGroup
                .filter(app => isActionAvailable(app, action))
                .map(app => app.id);
            
            if (filteredAppIds.length === 0) {
                showError(`Нет приложений в группе, для которых доступно действие "${action}"`);
                return;
            }
            
            const extraMessage = filteredAppIds.length !== appIds.length ? 
                `Будет выполнено только для приложений с подходящим статусом (${filteredAppIds.length} из ${appIds.length})` : null;
            
            showConfirmActionModal(filteredAppIds, action, extraMessage);
        }
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
		// Теперь нужно искать чекбоксы как в основной таблице, так и во вложенных таблицах
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
			
			// Создаем секции для модального окна
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
			
			// Добавляем секцию с настройками обновления
			const settingsSection = {
				title: 'Настройки обновления',
				type: 'html',
				content: `
					<div class="form-group">
						<label for="update-playbook-path">Путь к Ansible playbook:</label>
						<div class="input-with-button">
							<input type="text" id="update-playbook-path" class="form-control" value="${app.update_playbook_path || ''}">
							<button type="button" id="save-playbook-path" class="action-btn">Сохранить</button>
						</div>
					</div>
				`
			};
			sections.push(settingsSection);
			
			// Добавляем секцию с событиями, если они есть
			if (app.events && app.events.length > 0) {
				let eventsHtml = '<table class="events-table"><thead><tr><th>Дата</th><th>Тип</th><th>Статус</th></tr></thead><tbody>';
				
				app.events.forEach(event => {
					const eventDate = new Date(event.timestamp);
					eventsHtml += `
						<tr class="event-row ${event.status}" title="${event.description || ''}">
							<td>${eventDate.toLocaleString()}</td>
							<td>${event.event_type}</td>
							<td>${event.status}</td>
						</tr>
					`;
				});
				
				eventsHtml += '</tbody></table>';
				
				const eventsSection = {
					title: 'Последние события',
					type: 'html',
					content: eventsHtml
				};
				sections.push(eventsSection);
			} else {
				const eventsSection = {
					title: 'Последние события',
					type: 'html',
					content: '<p>Нет записей о событиях</p>'
				};
				sections.push(eventsSection);
			}
			
			// Отображаем модальное окно
			ModalUtils.showInfoModal(`Информация о приложении: ${app.name}`, sections);
			
			// Добавляем обработчик для кнопки сохранения пути к playbook
			document.getElementById('save-playbook-path').addEventListener('click', async function() {
				const playbookPath = document.getElementById('update-playbook-path').value.trim();
				
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
        
        // Получаем названия действий
        const actionNames = {
            'start': 'запустить',
            'stop': 'остановить',
            'restart': 'перезапустить'
        };
        
        const actionName = actionNames[action] || action;
        
        // Получаем информацию о приложениях
        const appItems = appIds.map(appId => {
            const app = getAppById(appId);
            return app ? `${app.name} (${app.server_name || 'Неизвестный сервер'})` : `App ID: ${appId}`;
        });
        
        // Функция, которая будет выполнена при подтверждении
        const confirmAction = async function() {
            try {
                // Сохраняем состояние таблицы
                saveTableState();
                
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
                    await loadApplications();
                    // Восстановление состояния происходит внутри loadApplications()
                    
                } else {
                    console.error('Ошибка при выполнении действия:', data.error);
                    showError(data.error || `Не удалось выполнить действие "${actionName}"`);
                }
            } catch (error) {
                console.error('Ошибка при выполнении действия:', error);
                showError(`Не удалось выполнить действие "${actionName}"`);
            }
        };
    
        // Отображаем модальное окно подтверждения
        ModalUtils.showConfirmModal(
            `${actionName.charAt(0).toUpperCase() + actionName.slice(1)} приложения`, // Заголовок
            `Вы уверены, что хотите <span class="action-name">${actionName}</span> выбранные приложения?`, // Сообщение
            appItems, // Список элементов
            confirmAction, // Функция подтверждения
            `Подтвердить (${appIds.length})`, // Текст кнопки
            'confirm-btn' // Класс кнопки
        );
    }
    
    /**
     * Показывает модальное окно для обновления приложений
     * @param {Array} appIds - Массив ID приложений
     */
    function showUpdateModal(appIds) {
        if (!appIds || appIds.length === 0) {
            showError('Не выбрано ни одного приложения');
            return;
        }
        
        // Определяем заголовок модального окна
        let title = '';
        if (appIds.length === 1) {
            const app = getAppById(appIds[0]);
            title = `Обновление приложения: ${app ? app.name : 'Приложение'}`;
        } else {
            title = `Обновление ${appIds.length} приложений`;
        }
        
        // Для обычного случая (одно приложение или одна группа) используем стандартную форму
        if (appIds.length === 1) {
            showSimpleUpdateModal(appIds[0], title);
            return;
        }
        
        // Группируем приложения по имени группы
        const appGroups = {};
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
        
        // Если есть только одна группа, показываем простую форму
        if (Object.keys(appGroups).length === 1) {
            const groupName = Object.keys(appGroups)[0];
            const groupApps = appGroups[groupName];
            const groupAppIds = groupApps.map(app => app.id);
            
            showSimpleUpdateModal(groupAppIds, `Обновление группы: ${groupName}`);
            return;
        }
        
        // Если есть несколько групп, создаем модальное окно с вкладками
        showTabsUpdateModal(appGroups, title);
    }

    /**
     * Показывает простое модальное окно обновления для одного приложения или группы
     * @param {number|Array} appIds - ID приложения или массив ID
     * @param {string} title - Заголовок модального окна
     */
async function showSimpleUpdateModal(appIds, title) {
    const appIdsArray = Array.isArray(appIds) ? appIds : [appIds];
    
    // Определяем значение дистрибутива по умолчанию
    let defaultDistrPath = '';
    let artifactVersions = null;
    let currentAppId = null;
    let isLoadingArtifacts = false;
    
    // Если обновляем одно приложение, показываем загрузчик сразу
    //if (appIdsArray.length === 1) {
        currentAppId = appIdsArray[0];
        const app = getAppById(currentAppId);
        if (app && app.distr_path) {
            defaultDistrPath = app.distr_path;
        }
        isLoadingArtifacts = true; // Устанавливаем флаг загрузки
    //}
    
    // Определяем начальные поля формы с загрузчиком
    const formFields = [];
    
    // Показываем загрузчик если загружаем артефакты
    if (isLoadingArtifacts) {
        formFields.push({
            id: 'artifact-loader-container',
            name: 'artifact_loader',
            type: 'custom',
            html: `
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
            `
        });
    } else {
        // Обычное поле URL если не загружаем артефакты
        formFields.push({
            id: 'distr-url',
            name: 'distr_url',
            label: 'URL дистрибутива:',
            type: 'text',
            value: defaultDistrPath,
            required: true
        });
    }
    
    // Добавляем остальные поля формы
    formFields.push({
        id: 'restart-mode',
        name: 'restart_mode',
        label: 'Режим обновления:',
        type: 'radio',
        value: 'restart',
        options: [
            { value: 'restart', text: 'В рестарт' },
            { value: 'immediate', text: 'Сейчас' }
        ]
    });
    
    formFields.push({
        id: 'app-ids',
        name: 'app_ids',
        type: 'hidden',
        value: appIdsArray.join(',')
    });
    
    // Функция отправки формы
    const submitAction = function(formData) {
        if (formData.distr_url === 'custom' && formData.custom_distr_url) {
            formData.distr_url = formData.custom_distr_url;
        }
        delete formData.custom_distr_url;
        processUpdateForm(formData);
    };
    
    // Отображаем модальное окно с загрузчиком
    ModalUtils.showFormModal(title, formFields, submitAction, 'Обновить');
    
/**
 * Универсальная функция загрузки версий (Docker образов или Maven артефактов)
 * @param {boolean} showProgress - Показывать ли прогресс загрузки
 * @returns {Promise<boolean>} - Успешность загрузки
 */
async function loadArtifacts(showProgress = true) {
    try {
        if (!currentAppId) {
            console.error('Не указан ID приложения для загрузки версий');
            return false;
        }
        
        const app = getAppById(currentAppId);
        if (!app) {
            console.error(`Приложение с ID ${currentAppId} не найдено`);
            return false;
        }
        
        console.log(`Загрузка версий для приложения ${app.name} (тип: ${app.app_type})`);
        
        if (showProgress) {
            // Анимируем прогресс-бар
            const progressBar = document.querySelector('.progress-bar');
            if (progressBar) {
                progressBar.style.width = '30%';
            }
        }
        
        const maxVersions = window.APP_CONFIG?.MAX_ARTIFACTS_DISPLAY || 20;
        
        // Используем универсальный endpoint, который сам определит тип
        const response = await fetch(`/api/applications/${currentAppId}/artifacts?limit=${maxVersions}`);
        
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
            artifactVersions = data.versions.slice(0, maxVersions);
            
            // Логируем тип загруженных версий
            console.log(`Загружено ${artifactVersions.length} ${data.app_type === 'docker' ? 'Docker образов' : 'Maven артефактов'} для приложения ${app.name}`);
            
            // Сохраняем тип для последующего использования
            if (window.loadedVersionsType) {
                window.loadedVersionsType = data.app_type;
            }
            
            return true;
        } else {
            console.log('Не удалось получить список версий:', data.error || 'Список пуст');
            return false;
        }
    } catch (error) {
        console.error('Ошибка при загрузке списка версий:', error);
        return false;
    }
}
    
    // Функция замены загрузчика на реальный контент
/**
 * Обновленная функция создания селектора версий
 * @param {Array} artifacts - Массив версий
 * @param {boolean} success - Успешность загрузки
 * @returns {string} - HTML код селектора
 */
function replaceLoaderWithContent(artifacts, success = true) {
    const loaderContainer = document.getElementById('artifact-loader-container');
    if (!loaderContainer) return;
    
    let newContent = '';
    
    if (success && artifacts && artifacts.length > 0) {
        // Определяем тип версий по наличию специфичных полей
        const isDocker = artifacts[0].display_name && artifacts[0].display_name.includes(':');
        const labelText = isDocker ? 'Docker образ:' : 'Версия артефакта:';
        
        // Создаем выпадающий список с анимацией появления
        newContent = `
            <div class="artifact-selector-wrapper animated-fade-in">
                <div class="artifact-selector-header">
                    <label for="distr-url">${labelText}</label>
                    <button type="button" id="refresh-artifacts-btn" class="refresh-artifacts-btn" title="Обновить список версий">
                        <span class="refresh-icon">⟳</span>
                    </button>
                </div>
                <select id="distr-url" name="distr_url" class="form-control artifact-select" required>
                    ${artifacts.map(version => {
                        let label = version.display_name || version.version;
                        let className = '';
                        let icon = '';
                        
                        // Определяем тип версии
                        if (version.is_snapshot) {
                            icon = ' 🔸';
                            className = 'version-snapshot';
                        } else if (version.is_dev) {
                            icon = ' 🔹';
                            className = 'version-dev';
                        } else if (version.is_release) {
                            icon = ' ✅';
                            className = 'version-release';
                        }
                        
                        return `<option value="${version.url}" class="${className}">${label}${icon}</option>`;
                    }).join('')}
                    <option value="custom" class="custom-option">➕ Указать вручную...</option>
                </select>
                <div id="custom-url-group" class="form-group" style="display: none;">
                    <label for="custom-distr-url">
                        ${isDocker ? 'Docker образ (registry/image:tag):' : 'URL артефакта:'}
                    </label>
                    <input type="text" id="custom-distr-url" name="custom_distr_url" class="form-control" 
                           placeholder="${isDocker ? 'nexus.bankplus.ru/docker-prod-local/app:1.0.0' : 'https://nexus.bankplus.ru/artifact.jar'}">
                </div>
            </div>
        `;
    } else {
        // Показываем сообщение об ошибке
        newContent = `


                <div class="distr-url-wrapper animated-fade-in">
                    <div class="distr-url-header">
                        <label for="distr-url">URL дистрибутива:</label>
                    <button type="button" id="retry-load-btn" class="retry-btn">
                        <span class="refresh-icon">⟳</span> Повторить
                    </button> 
                    </div>
                    <input type="text" id="distr-url" name="distr_url" class="form-control" value="${defaultDistrPath}" required>
                    ${!success ? '<div class="error-message">Не удалось загрузить список версий</div>' : ''}
                </div>                

        `;
    }
    
    // Заменяем загрузчик на реальный контент
    loaderContainer.innerHTML = newContent;
    
    // Добавляем обработчики событий
    setupVersionSelectorEventHandlers();
}

/**
 * Настройка обработчиков событий для селектора версий
 */
function setupVersionSelectorEventHandlers() {
    // Обработчик для селектора версий
    const distrSelect = document.getElementById('distr-url');
    if (distrSelect) {
        distrSelect.addEventListener('change', function() {
            const customGroup = document.getElementById('custom-url-group');
            if (customGroup) {
                if (this.value === 'custom') {
                    customGroup.style.display = 'block';
                    document.getElementById('custom-distr-url').required = true;
                } else {
                    customGroup.style.display = 'none';
                    document.getElementById('custom-distr-url').required = false;
                }
            }
        });
    }
    
    // Обработчик для кнопки обновления
    const refreshBtn = document.getElementById('refresh-artifacts-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async function() {
            this.classList.add('rotating');
            this.disabled = true;
            
            const success = await loadArtifacts(false);
            
            if (success) {
                const select = document.getElementById('distr-url');
                if (select) {
                    select.style.opacity = '0';
                    
                    // Пересоздаем опции
                    select.innerHTML = artifactVersions.map(version => {
                        let label = version.display_name || version.version;
                        let className = '';
                        let icon = '';
                        
                        if (version.is_snapshot) {
                            icon = ' 🔸';
                            className = 'version-snapshot';
                        } else if (version.is_dev) {
                            icon = ' 🔹';
                            className = 'version-dev';
                        } else if (version.is_release) {
                            icon = ' ✅';
                            className = 'version-release';
                        }
                        
                        return `<option value="${version.url}" class="${className}">${label}${icon}</option>`;
                    }).join('');
                    
                    // Добавляем опцию для ручного ввода
                    select.innerHTML += '<option value="custom" class="custom-option">➕ Указать вручную...</option>';
                    
                    setTimeout(() => {
                        select.style.opacity = '1';
                    }, 200);
                }
                showNotification('Список версий обновлен');
            } else {
                showError('Не удалось обновить список версий');
            }
            
            this.classList.remove('rotating');
            this.disabled = false;
        });
    }
    
    // Обработчик для кнопки повторной попытки
    const retryBtn = document.getElementById('retry-load-btn');
    if (retryBtn) {
        retryBtn.addEventListener('click', async function() {
            // Показываем загрузчик снова
            const container = this.closest('.distr-url-wrapper').parentElement;
            container.innerHTML = `
                <div class="artifact-loading-container">
                    <label>Загрузка версий:</label>
                    <div class="artifact-loader">
                        <div class="skeleton-select">
                            <div class="skeleton-text">Повторная загрузка...</div>
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
            `;
            
            // Загружаем артефакты заново
            const success = await loadArtifacts(true);
            artifactVersions = success ? artifactVersions : null;
            
            // Задержка для визуального эффекта
            setTimeout(() => {
                replaceLoaderWithContent(artifactVersions, success);
            }, 500);
        });
    }
}

// Добавим CSS стили для анимации вращения
if (!document.getElementById('version-loader-styles')) {
    const style = document.createElement('style');
    style.id = 'version-loader-styles';
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
            from { opacity: 0; }
            to { opacity: 1; }
        }
    `;
    document.head.appendChild(style);
}
    
    // Функция инициализации обработчиков
    function initializeHandlers(artifacts) {
        // Обработчик для выпадающего списка
        const selectElement = document.getElementById('distr-url');
        const customUrlGroup = document.getElementById('custom-url-group');
        
        if (selectElement && selectElement.tagName === 'SELECT' && customUrlGroup) {
            selectElement.addEventListener('change', function() {
                if (this.value === 'custom') {
                    customUrlGroup.style.display = 'block';
                    customUrlGroup.classList.add('animated-slide-down');
                    document.getElementById('custom-distr-url').required = true;
                } else {
                    customUrlGroup.style.display = 'none';
                    document.getElementById('custom-distr-url').required = false;
                }
            });
        }
        
        // Обработчик для кнопки обновления
        const refreshBtn = document.getElementById('refresh-artifacts-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', async function() {
                this.classList.add('rotating');
                this.disabled = true;
                
                // Очищаем кэш
                if (currentAppId && window.artifactsCache) {
                    delete window.artifactsCache[`app_${currentAppId}`];
                }
                
                const success = await loadArtifacts(false);
                
                if (success && artifactVersions) {
                    const select = document.getElementById('distr-url');
                    if (select) {
                        const currentValue = select.value;
                        
                        // Анимация обновления списка
                        select.style.opacity = '0.5';
                        
                        setTimeout(() => {
                            select.innerHTML = artifactVersions.map(version => {
                                let label = version.version;
                                let className = '';
                                
                                const versionLower = version.version.toLowerCase();
                                if (versionLower.includes('snapshot')) {
                                    label += ' 🔸';
                                    className = 'version-snapshot';
                                } else if (versionLower.includes('dev')) {
                                    label += ' 🔶';
                                    className = 'version-dev';
                                } else if (version.is_release) {
                                    label += ' ✅';
                                    className = 'version-release';
                                }
                                
                                return `<option value="${version.url}" class="${className}">${label}</option>`;
                            }).join('') + '<option value="custom">-- Указать URL вручную --</option>';
                            
                            if ([...select.options].some(opt => opt.value === currentValue)) {
                                select.value = currentValue;
                            }
                            
                            select.style.opacity = '1';
                        }, 200);
                    }
                    showNotification('Список версий обновлен');
                } else {
                    showError('Не удалось обновить список версий');
                }
                
                this.classList.remove('rotating');
                this.disabled = false;
            });
        }
        
        // Обработчик для кнопки повторной попытки
        const retryBtn = document.getElementById('retry-load-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', async function() {
                // Показываем загрузчик снова
                const container = this.closest('.distr-url-wrapper').parentElement;
                container.innerHTML = `
                    <div class="artifact-loading-container">
                        <label>Версия дистрибутива:</label>
                        <div class="artifact-loader">
                            <div class="skeleton-select">
                                <div class="skeleton-text">Повторная загрузка...</div>
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
                `;
                
                // Загружаем артефакты заново
                const success = await loadArtifacts(true);
                artifactVersions = success ? artifactVersions : null;
                
                // Замедляем для визуального эффекта
                setTimeout(() => {
                    replaceLoaderWithContent(artifactVersions, success);
                }, 500);
            });
        }
    }
    
    // Если нужно загрузить артефакты, делаем это после отображения модального окна
    if (isLoadingArtifacts && currentAppId) {
        // Даем время на отрисовку загрузчика
        setTimeout(async () => {
            const success = await loadArtifacts(true);
            
            // Небольшая задержка для визуального эффекта (минимум 800ms загрузки)
            setTimeout(() => {
                replaceLoaderWithContent(artifactVersions, success);
            }, Math.max(0, 800 - (Date.now() % 1000)));
        }, 100);
    }
}

    /**
     * Загрузка артефактов с кэшированием
     */
    async function loadArtifactsWithCache(appId) {
        const now = Date.now();
        const cacheKey = `app_${appId}`;
        
        // Проверяем кэш
        if (artifactsCache[cacheKey]) {
            const cacheEntry = artifactsCache[cacheKey];
            const age = now - cacheEntry.timestamp;
            
            // Если кэш свежий, используем его
            if (age < CACHE_LIFETIME) {
                console.log(`Используем кэш артефактов для приложения ${appId} (возраст: ${Math.round(age/1000)}с)`);
                return cacheEntry.data;
            }
        }
        
        // Загружаем свежие данные
        try {
            const maxVersions = window.APP_CONFIG?.MAX_ARTIFACTS_DISPLAY || 20;
            const response = await fetch(`/api/applications/${appId}/artifacts?limit=${maxVersions}`);
            const data = await response.json();
            
            if (data.success && data.versions && data.versions.length > 0) {
                const artifacts = data.versions.slice(0, maxVersions);
                
                // Сохраняем в кэш
                artifactsCache[cacheKey] = {
                    timestamp: now,
                    data: artifacts
                };
                
                console.log(`Загружено ${artifacts.length} версий для приложения ${appId}`);
                return artifacts;
            }
        } catch (error) {
            console.error(`Ошибка при загрузке артефактов для приложения ${appId}:`, error);
        }
        
        return null;
    }

    /**
     * Показывает модальное окно обновления с вкладками для групп приложений
     * @param {Object} appGroups - Объект групп приложений
     * @param {string} title - Заголовок модального окна
     */
    function showTabsUpdateModal(appGroups, title) {
        // Создаем контейнер с содержимым модального окна
        const modalContent = document.createElement('div');
        
        // Создаем контейнер для вкладок
        const tabsContainer = document.createElement('div');
        tabsContainer.className = 'modal-tabs';
        modalContent.appendChild(tabsContainer);
        
        // Создаем форму
        const form = document.createElement('form');
        form.id = 'update-form';
        form.className = 'modal-form';
        modalContent.appendChild(form);
        
        // Создаем хранилище состояний и артефактов для каждой группы
        const groupStates = {};
        const groupArtifacts = {};
        
        // Создаем вкладки
        Object.keys(appGroups).forEach((groupName, index) => {
            const tab = document.createElement('div');
            tab.className = `modal-tab ${index === 0 ? 'active' : ''}`;
            tab.innerHTML = `${groupName} <span class="app-count">(${appGroups[groupName].length})</span>`;
            tab.setAttribute('data-group', groupName);
            tabsContainer.appendChild(tab);
            
            // Инициализируем состояние группы
            const apps = appGroups[groupName];
            const firstApp = apps[0];
            
            groupStates[groupName] = {
                appIds: apps.map(app => app.id),
                distrUrl: firstApp && firstApp.distr_path ? firstApp.distr_path : '',
                restartMode: 'restart',
                artifactsLoaded: false
            };
        });
        
        // Создаем контейнер для динамического содержимого
        const dynamicContent = document.createElement('div');
        dynamicContent.id = 'dynamic-group-content';
        form.appendChild(dynamicContent);
        
        // Функция создания выпадающего списка версий с подсветкой
        function createVersionSelect(artifacts, currentValue) {
            const options = artifacts.map(version => {
                let label = version.version;
                let className = '';
                
                // Проверяем на dev/snapshot и добавляем визуальные индикаторы
                const versionLower = version.version.toLowerCase();
                if (versionLower.includes('snapshot')) {
                    label += ' 🔸'; // Оранжевый ромб для snapshot
                    className = 'version-snapshot';
                } else if (versionLower.includes('dev')) {
                    label += ' 🔸'; // Оранжевый ромб для dev
                    className = 'version-dev';
                } else if (version.is_release) {
                    label += ''; // release
                    className = 'version-release';
                }
                
                return `<option value="${version.url}" class="${className}">${label}</option>`;
            }).join('');
            
            return options + '<option value="custom">-- Указать URL вручную --</option>';
        }
        
        // Функция обновления содержимого формы для группы
async function updateFormContent(groupName) {
    const state = groupStates[groupName];
    const apps = appGroups[groupName];
    
    // Показываем красивый загрузчик
    dynamicContent.innerHTML = `
        <div class="group-content-loader">
            <div class="loader-icon">
                <div class="loader-rings">
                    <div class="ring ring-1"></div>
                    <div class="ring ring-2"></div>
                    <div class="ring ring-3"></div>
                </div>
            </div>
            <div class="loader-text">
                <span class="loading-label">Загрузка настроек группы</span>
                <span class="loading-dots"></span>
            </div>
            <div class="loader-details">${groupName}</div>
        </div>
    `;
    
    // Минимальная задержка для визуального эффекта
    const startTime = Date.now();
    
    // Проверяем, нужно ли загружать артефакты
    let artifacts = null;
    let loadingError = false;
    
    if (apps.length === 1) {
        const appId = apps[0].id;
        
        // Обновляем текст загрузчика
        setTimeout(() => {
            const loaderText = document.querySelector('.loading-label');
            if (loaderText) {
                loaderText.textContent = 'Получение списка версий';
            }
        }, 300);
        
        // Проверяем, загружены ли уже артефакты для этой группы
        if (!groupArtifacts[groupName] || !state.artifactsLoaded) {
            artifacts = await loadArtifactsWithCache(appId);
            if (artifacts) {
                groupArtifacts[groupName] = artifacts;
                state.artifactsLoaded = true;
            } else {
                loadingError = true;
            }
        } else {
            artifacts = groupArtifacts[groupName];
        }
    }
    
    // Обеспечиваем минимальное время показа загрузчика (600ms)
    const elapsedTime = Date.now() - startTime;
    if (elapsedTime < 600) {
        await new Promise(resolve => setTimeout(resolve, 600 - elapsedTime));
    }
    
    // Создаем HTML содержимое формы с анимацией появления
    let formHTML = '<div class="form-content-animated">';
    
    // Скрытое поле с ID приложений
    formHTML += `<input type="hidden" id="app-ids" name="app_ids" value="${state.appIds.join(',')}">`;
    
    // Поле URL дистрибутива или выпадающий список
    if (artifacts && artifacts.length > 0) {
        formHTML += `
            <div class="form-group animated-fade-in" style="animation-delay: 0.1s">
                <div class="artifact-selector-wrapper">
                    <div class="artifact-selector-header">
                        <label for="distr-url">
                            Версия дистрибутива:
                            <span class="version-count">(${artifacts.length} версий)</span>
                        </label>
                        <button type="button" class="refresh-artifacts-btn" data-group="${groupName}" title="Обновить список версий">
                            <span class="refresh-icon">⟳</span>
                        </button>
                    </div>
                    <select id="distr-url" name="distr_url" class="form-control artifact-select" required>
                        ${createVersionSelect(artifacts, state.distrUrl)}
                    </select>
                    ${state.artifactsLoaded && getArtifactsCacheAge ? `
                        <div class="cache-status">
                            ${getArtifactsCacheAge(apps[0].id) < 60 ? 
                                '<span class="cache-fresh">✓ Данные актуальны</span>' : 
                                '<span class="cache-old">Обновлено ' + Math.round(getArtifactsCacheAge(apps[0].id) / 60) + ' мин. назад</span>'
                            }
                        </div>
                    ` : ''}
                </div>
            </div>
            <div class="form-group animated-fade-in" id="custom-url-group" style="display: none; animation-delay: 0.2s">
                <label for="custom-distr-url">URL дистрибутива:</label>
                <input type="text" id="custom-distr-url" name="custom_distr_url" class="form-control" value="${state.distrUrl}">
            </div>
        `;
    } else {
        // Обычное текстовое поле с возможностью загрузки артефактов
        const errorClass = loadingError ? 'field-with-error' : '';
        formHTML += `
            <div class="form-group animated-fade-in ${errorClass}" style="animation-delay: 0.1s">
                <div class="distr-url-wrapper">
                    <div class="distr-url-header">
                        <label for="distr-url">URL дистрибутива:</label>
                        ${apps.length === 1 ? `
                            <button type="button" class="load-artifacts-btn" data-group="${groupName}" data-app-id="${apps[0].id}" title="Загрузить список версий">
                                Загрузить версии
                            </button>
                        ` : ''}
                    </div>
                    <input type="text" id="distr-url" name="distr_url" class="form-control" value="${state.distrUrl}" required>
                    ${loadingError ? `
                        <div class="field-hint error">
                            Не удалось загрузить список версий. Введите URL вручную или попробуйте загрузить снова.
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    // Режим обновления
    formHTML += `
        <div class="form-group animated-fade-in" style="animation-delay: 0.3s">
            <label>Режим обновления:</label>
            <div class="radio-group">
                <label class="radio-label">
                    <input type="radio" name="restart_mode" value="restart" ${state.restartMode === 'restart' ? 'checked' : ''}>
                    В рестарт
                </label>
                <label class="radio-label">
                    <input type="radio" name="restart_mode" value="immediate" ${state.restartMode === 'immediate' ? 'checked' : ''}>
                    Сейчас
                </label>
            </div>
        </div>
    `;
    
    // Информация о приложениях в группе
    if (apps.length > 1) {
        formHTML += `
            <div class="group-apps-info animated-fade-in" style="animation-delay: 0.4s">
                <label>Приложения в группе (${apps.length}):</label>
                <div class="apps-list">
                    ${apps.map((app, index) => `
                        <span class="app-badge" style="animation-delay: ${0.5 + index * 0.05}s">
                            ${app.name}
                            ${app.status === 'online' ? '<span class="status-indicator online">●</span>' : ''}
                        </span>
                    `).join(' ')}
                </div>
            </div>
        `;
    }
    
    formHTML += '</div>';
    
    // Заменяем содержимое с анимацией
    dynamicContent.style.opacity = '0';
    setTimeout(() => {
        dynamicContent.innerHTML = formHTML;
        dynamicContent.style.opacity = '1';
        
        // Добавляем обработчики после рендеринга
        attachFormHandlers(groupName);
    }, 200);
}
        
        // Функция для добавления обработчиков к элементам формы
        function attachFormHandlers(groupName) {
            // Обработчик для выпадающего списка версий
            const selectElement = document.getElementById('distr-url');
            const customUrlGroup = document.getElementById('custom-url-group');
            
            if (selectElement && selectElement.tagName === 'SELECT' && customUrlGroup) {
                selectElement.addEventListener('change', function() {
                    if (this.value === 'custom') {
                        customUrlGroup.style.display = 'block';
                        document.getElementById('custom-distr-url').required = true;
                    } else {
                        customUrlGroup.style.display = 'none';
                        document.getElementById('custom-distr-url').required = false;
                    }
                });
            }
            
            // Обработчик для кнопки обновления артефактов
            const refreshBtn = document.querySelector('.refresh-artifacts-btn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', async function() {
                    this.classList.add('rotating');
                    this.disabled = true;
                    
                    const group = this.getAttribute('data-group');
                    const apps = appGroups[group];
                    
                    if (apps.length === 1) {
                        const appId = apps[0].id;
                        
                        // Очищаем кэш для принудительного обновления
                        delete artifactsCache[`app_${appId}`];
                        
                        const artifacts = await loadArtifactsWithCache(appId);
                        if (artifacts) {
                            groupArtifacts[group] = artifacts;
                            groupStates[group].artifactsLoaded = true;
                            
                            // Обновляем выпадающий список
                            const select = document.getElementById('distr-url');
                            if (select) {
                                const currentValue = select.value;
                                select.innerHTML = createVersionSelect(artifacts, currentValue);
                                
                                // Восстанавливаем значение если возможно
                                if ([...select.options].some(opt => opt.value === currentValue)) {
                                    select.value = currentValue;
                                }
                            }
                            
                            showNotification('Список версий обновлен');
                        } else {
                            showError('Не удалось обновить список версий');
                        }
                    }
                    
                    this.classList.remove('rotating');
                    this.disabled = false;
                });
            }
            
            // Обработчик для кнопки загрузки артефактов
            const loadBtn = document.querySelector('.load-artifacts-btn');
            if (loadBtn) {
                loadBtn.addEventListener('click', async function() {
                    this.classList.add('rotating');
                    this.disabled = true;
                    
                    const group = this.getAttribute('data-group');
                    const appId = this.getAttribute('data-app-id');
                    
                    const artifacts = await loadArtifactsWithCache(appId);
                    if (artifacts) {
                        groupArtifacts[group] = artifacts;
                        groupStates[group].artifactsLoaded = true;
                        
                        // Перерисовываем форму с артефактами
                        await updateFormContent(group);
                        
                        showNotification('Список версий загружен');
                    } else {
                        showError('Не удалось загрузить список версий');
                    }
                    
                    this.classList.remove('rotating');
                    this.disabled = false;
                });
            }
        }
        
        // Функция сохранения текущего состояния группы
        function saveCurrentGroupState() {
            const currentGroup = tabsContainer.querySelector('.modal-tab.active');
            if (currentGroup) {
                const groupName = currentGroup.getAttribute('data-group');
                const distrUrlElement = document.getElementById('distr-url');
                const restartModeElement = document.querySelector('input[name="restart_mode"]:checked');
                
                if (distrUrlElement) {
                    let distrUrl = distrUrlElement.value;
                    
                    // Если выбран custom, берем значение из custom поля
                    if (distrUrl === 'custom') {
                        const customUrlElement = document.getElementById('custom-distr-url');
                        if (customUrlElement) {
                            distrUrl = customUrlElement.value;
                        }
                    }
                    
                    groupStates[groupName].distrUrl = distrUrl;
                }
                
                if (restartModeElement) {
                    groupStates[groupName].restartMode = restartModeElement.value;
                }
            }
        }
        
        // Кнопки действий формы
        const formActions = document.createElement('div');
        formActions.className = 'form-actions';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'cancel-btn';
        cancelBtn.textContent = 'Отмена';
        cancelBtn.onclick = window.closeModal;
        formActions.appendChild(cancelBtn);
        
        const submitBtn = document.createElement('button');
        submitBtn.type = 'submit';
        submitBtn.className = 'submit-btn';
        submitBtn.textContent = 'Обновить';
        formActions.appendChild(submitBtn);
        
        form.appendChild(formActions);
        
        // Отображаем модальное окно
        window.showModal(title, modalContent);
        
        // Загружаем содержимое для первой группы
        const firstGroup = Object.keys(appGroups)[0];
        updateFormContent(firstGroup);
        
        // Обработчики для вкладок
        tabsContainer.querySelectorAll('.modal-tab').forEach(tab => {
            tab.addEventListener('click', async function() {
                // Сохраняем текущее состояние
                saveCurrentGroupState();
                
                // Переключаем активную вкладку
                tabsContainer.querySelectorAll('.modal-tab').forEach(t => {
                    t.classList.remove('active');
                });
                this.classList.add('active');
                
                // Загружаем состояние для выбранной группы
                const groupName = this.getAttribute('data-group');
                await updateFormContent(groupName);
            });
        });
        
        // Обработчик отправки формы
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Сохраняем текущее состояние
            saveCurrentGroupState();
            
            // Собираем данные из всех групп
            const formDataArray = Object.keys(groupStates).map(groupName => {
                const state = groupStates[groupName];
                
                // Пропускаем группы без URL
                if (!state.distrUrl || state.distrUrl === 'custom') {
                    return null;
                }
                
                return {
                    app_ids: state.appIds.join(','),
                    distr_url: state.distrUrl,
                    restart_mode: state.restartMode
                };
            }).filter(data => data !== null);
            
            // Проверяем, заполнены ли группы
            if (formDataArray.length === 0) {
                showError('Укажите URL дистрибутива хотя бы для одной группы');
                return;
            }
            
            // Обрабатываем все группы
            processUpdateForm(formDataArray, true);
        });
}

/**
 * Определение типа загрузчика версий на основе типа приложения
 * @param {Object} app - Объект приложения
 * @returns {string} - Тип загрузчика ('docker' или 'maven')
 */
function getVersionLoaderType(app) {
    // Проверяем тип приложения
    if (app && app.app_type === 'docker') {
        return 'docker';
    }
    return 'maven';
}

/**
 * Загрузка версий для приложения (Docker или Maven)
 * @param {number} appId - ID приложения  
 * @param {boolean} forceReload - Принудительная перезагрузка
 * @returns {Promise<Array>} - Массив версий
 */
async function loadApplicationVersions(appId, forceReload = false) {
    const app = getAppById(appId);
    if (!app) {
        console.error(`Приложение с ID ${appId} не найдено`);
        return null;
    }
    
    const loaderType = getVersionLoaderType(app);
    console.log(`Загрузка версий для приложения ${app.name}, тип: ${loaderType}`);
    
    try {
        let response;
        
        if (loaderType === 'docker') {
            // Загружаем Docker образы
            response = await fetch(`/api/docker/images/${appId}?limit=${window.APP_CONFIG.MAX_ARTIFACTS_DISPLAY}`);
        } else {
            // Загружаем Maven артефакты
            response = await fetch(`/api/applications/${appId}/versions?limit=${window.APP_CONFIG.MAX_ARTIFACTS_DISPLAY}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.versions) {
            console.log(`Загружено ${data.versions.length} версий для ${app.name}`);
            return {
                type: loaderType,
                versions: data.versions
            };
        } else {
            console.error('Не удалось получить список версий:', data.error);
            return null;
        }
    } catch (error) {
        console.error('Ошибка при загрузке версий:', error);
        return null;
    }
}

/**
 * Создание HTML для селектора версий
 * @param {Object} versionData - Данные о версиях
 * @returns {string} - HTML код селектора
 */
function createVersionSelector(versionData) {
    if (!versionData || !versionData.versions || versionData.versions.length === 0) {
        return `
            <div class="error-message">
                <p>Не удалось загрузить список версий</p>
                <button type="button" id="retry-load-btn" class="retry-btn">
                    Повторить попытку
                </button>
            </div>
        `;
    }
    
    const isDocker = versionData.type === 'docker';
    const labelText = isDocker ? 'Docker образ:' : 'Версия артефакта:';
    
    let optionsHtml = '';
    
    versionData.versions.forEach(version => {
        let label = version.version;
        let className = '';
        let icon = '';
        
        // Определяем тип версии и добавляем метки
        if (version.is_snapshot) {
            icon = ' 🔸';
            className = 'version-snapshot';
        } else if (version.is_dev) {
            icon = ' 🔹';
            className = 'version-dev';
        } else if (version.is_release) {
            icon = ' ✅';
            className = 'version-release';
        }
        
        // Для Docker образов показываем display_name
        if (isDocker && version.display_name) {
            label = version.display_name;
        }
        
        optionsHtml += `
            <option value="${version.url}" class="${className}">
                ${label}${icon}
            </option>
        `;
    });
    
    // Добавляем опцию для ручного ввода
    optionsHtml += `
        <option value="custom" class="custom-option">
            ➕ Указать вручную...
        </option>
    `;
    
    return `
        <div class="version-selector-wrapper animated-fade-in">
            <div class="version-selector-header">
                <label for="version-select">${labelText}</label>
                <button type="button" id="refresh-versions-btn" class="refresh-artifacts-btn" title="Обновить список">
                    <span class="refresh-icon">⟳</span>
                </button>
            </div>
            <select id="version-select" name="version_url" class="form-control artifact-select" required>
                ${optionsHtml}
            </select>
            <div id="custom-url-group" class="form-group" style="display: none;">
                <label for="custom-url">URL ${isDocker ? 'образа' : 'артефакта'}:</label>
                <input type="text" id="custom-url" class="form-control" 
                       placeholder="${isDocker ? 'registry.com/image:tag' : 'https://nexus.com/artifact.jar'}">
            </div>
        </div>
    `;
}

/**
 * Обновленная функция показа простого модального окна обновления
 * с поддержкой Docker образов
 */
async function showSimpleUpdateModalEnhanced(appIds, title) {
    const appIdsArray = Array.isArray(appIds) ? appIds : [appIds];
    
    // Определяем тип приложения для выбора загрузчика
    let app = null;
    let versionLoaderType = 'maven';
    
    if (appIdsArray.length === 1) {
        app = getAppById(appIdsArray[0]);
        if (app) {
            versionLoaderType = getVersionLoaderType(app);
        }
    }
    
    // Создаем начальные поля формы
    const formFields = [];
    
    // Показываем загрузчик версий
    formFields.push({
        id: 'version-loader-container',
        name: 'version_loader',
        type: 'custom',
        html: `
            <div class="version-loading-container">
                <label>${versionLoaderType === 'docker' ? 'Docker образ' : 'Версия'}:</label>
                <div class="artifact-loader">
                    <div class="skeleton-select">
                        <div class="skeleton-text">
                            Загрузка списка ${versionLoaderType === 'docker' ? 'образов' : 'версий'}...
                        </div>
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
        `
    });
    
    // Добавляем поле выбора режима обновления
    formFields.push({
        id: 'restart-mode',
        name: 'restart_mode',
        label: 'Режим обновления:',
        type: 'radio',
        options: [
            { value: 'restart', label: 'В рестарт', checked: true },
            { value: 'immediate', label: 'Сейчас' }
        ]
    });
    
    // Создаем функцию отправки формы
    const submitAction = async (formData) => {
        try {
            // Подготавливаем данные для отправки
            const updateData = {
                distr_url: formData.version_url || formData.custom_url,
                restart_mode: formData.restart_mode
            };
            
            // Для Docker приложений передаем параметр как image_name
            if (versionLoaderType === 'docker') {
                updateData.image_name = updateData.distr_url;
            }
            
            // Выполняем обновление для каждого приложения
            const results = [];
            for (const appId of appIdsArray) {
                const response = await fetch(`/api/applications/${appId}/update`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(updateData)
                });
                
                const data = await response.json();
                results.push({
                    appId: appId,
                    success: data.success,
                    message: data.message || data.error
                });
            }
            
            // Показываем результаты
            const successCount = results.filter(r => r.success).length;
            if (successCount === results.length) {
                showNotification('Обновление успешно запущено');
            } else if (successCount > 0) {
                showNotification(`Обновление запущено для ${successCount} из ${results.length} приложений`);
            } else {
                showError('Не удалось запустить обновление');
            }
            
            // Обновляем список приложений
            await loadApplications();
            
        } catch (error) {
            console.error('Ошибка при обновлении:', error);
            showError('Произошла ошибка при обновлении');
        }
    };
    
    // Отображаем модальное окно
    ModalUtils.showFormModal(title, formFields, submitAction, 'Обновить');
    
    // Загружаем версии после отображения модального окна
    if (app) {
        setTimeout(async () => {
            const versionData = await loadApplicationVersions(app.id, true);
            
            // Заменяем загрузчик на реальный селектор
            const loaderContainer = document.getElementById('version-loader-container');
            if (loaderContainer && versionData) {
                loaderContainer.innerHTML = createVersionSelector(versionData);
                
                // Добавляем обработчики событий
                setupVersionSelectorHandlers(app.id);
            } else if (loaderContainer) {
                loaderContainer.innerHTML = createVersionSelector(null);
            }
        }, 100);
    }
}

/**
 * Настройка обработчиков для селектора версий
 */
function setupVersionSelectorHandlers(appId) {
    // Обработчик изменения селектора версий
    const versionSelect = document.getElementById('version-select');
    const customUrlGroup = document.getElementById('custom-url-group');
    
    if (versionSelect) {
        versionSelect.addEventListener('change', function() {
            if (this.value === 'custom') {
                customUrlGroup.style.display = 'block';
                document.getElementById('custom-url').required = true;
            } else {
                customUrlGroup.style.display = 'none';
                document.getElementById('custom-url').required = false;
            }
        });
    }
    
    // Обработчик кнопки обновления списка
    const refreshBtn = document.getElementById('refresh-versions-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async function() {
            this.classList.add('rotating');
            this.disabled = true;
            
            const versionData = await loadApplicationVersions(appId, true);
            
            if (versionData) {
                // Обновляем опции в селекторе
                const select = document.getElementById('version-select');
                if (select) {
                    const currentValue = select.value;
                    select.innerHTML = '';
                    
                    versionData.versions.forEach(version => {
                        const option = document.createElement('option');
                        option.value = version.url;
                        option.textContent = version.display_name || version.version;
                        
                        if (version.is_snapshot) {
                            option.className = 'version-snapshot';
                            option.textContent += ' 🔸';
                        } else if (version.is_dev) {
                            option.className = 'version-dev';
                            option.textContent += ' 🔹';
                        } else if (version.is_release) {
                            option.className = 'version-release';
                            option.textContent += ' ✅';
                        }
                        
                        select.appendChild(option);
                    });
                    
                    // Добавляем опцию для ручного ввода
                    const customOption = document.createElement('option');
                    customOption.value = 'custom';
                    customOption.textContent = '➕ Указать вручную...';
                    customOption.className = 'custom-option';
                    select.appendChild(customOption);
                    
                    // Восстанавливаем выбранное значение если возможно
                    if (currentValue && select.querySelector(`option[value="${currentValue}"]`)) {
                        select.value = currentValue;
                    }
                }
                
                showNotification('Список версий обновлен');
            } else {
                showError('Не удалось обновить список версий');
            }
            
            this.classList.remove('rotating');
            this.disabled = false;
        });
    }
}

// Переопределяем существующую функцию showSimpleUpdateModal
window.showSimpleUpdateModal = showSimpleUpdateModalEnhanced;

/**
 * Обработка формы обновления приложений (поддержка как одиночных, так и групповых обновлений)
 * @param {Object|Array} formData - Данные формы или массив данных для нескольких групп
 * @param {boolean} closeAfterSubmit - Закрыть модальное окно после отправки
 */
async function processUpdateForm(formData) {
    const appIds = formData.app_ids ? formData.app_ids.split(',').map(id => parseInt(id)) : [];
    
    if (appIds.length === 0) {
        showError('Не выбраны приложения для обновления');
        return;
    }
    
    const updateRequests = [];
    
    for (const appId of appIds) {
        const app = getAppById(appId);
        
        if (!app) {
            console.error(`Приложение с ID ${appId} не найдено`);
            continue;
        }
        
        // Подготавливаем параметры обновления в зависимости от типа приложения
        const updateParams = {
            restart_mode: formData.restart_mode || 'restart'
        };
        
        // ВАЖНО: Для Docker приложений передаем image_name
        if (app.app_type === 'docker') {
            // Для Docker используем image_name
            updateParams.image_name = formData.distr_url;
            // Также передаем как distr_url для обратной совместимости
            updateParams.distr_url = formData.distr_url;
            
            console.log(`Обновление Docker приложения ${app.name} с образом: ${updateParams.image_name}`);
        } else {
            // Для Maven/других типов используем distr_url
            updateParams.distr_url = formData.distr_url;
            
            console.log(`Обновление ${app.app_type} приложения ${app.name} с URL: ${updateParams.distr_url}`);
        }
        
        // Добавляем дополнительные параметры если есть
        if (formData.additional_vars) {
            updateParams.additional_vars = formData.additional_vars;
        }
        
        // Создаем запрос на обновление
        updateRequests.push(
            fetch(`/api/applications/${appId}/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(updateParams)
            })
            .then(response => response.json())
            .then(result => ({
                appId: appId,
                appName: app.name,
                appType: app.app_type,
                success: result.success,
                message: result.message,
                error: result.error,
                taskId: result.task_id
            }))
            .catch(error => ({
                appId: appId,
                appName: app.name,
                appType: app.app_type,
                success: false,
                error: error.message
            }))
        );
    }
    
    try {
        // Выполняем все запросы параллельно
        const results = await Promise.all(updateRequests);
        
        // Анализируем результаты
        const successCount = results.filter(r => r.success).length;
        const failedCount = results.filter(r => !r.success).length;
        
        // Формируем сообщение
        if (successCount === results.length) {
            showNotification(`Успешно запущено обновление для ${successCount} приложений`);
        } else if (successCount > 0) {
            showNotification(`Обновление запущено для ${successCount} из ${results.length} приложений`);
            
            // Показываем детали ошибок
            const failedApps = results.filter(r => !r.success);
            failedApps.forEach(app => {
                console.error(`Ошибка обновления ${app.appName}: ${app.error}`);
            });
        } else {
            showError('Не удалось запустить обновление ни для одного приложения');
            
            // Показываем детали ошибок
            results.forEach(app => {
                if (!app.success) {
                    console.error(`Ошибка обновления ${app.appName}: ${app.error}`);
                }
            });
        }
        
        // Обновляем список приложений
        await loadApplications();
        
        // Закрываем модальное окно
        closeModal();
        
    } catch (error) {
        console.error('Ошибка при обработке обновления:', error);
        showError('Произошла ошибка при обновлении приложений');
    }
}

// Обновляем обработчик отправки формы в модальном окне
document.addEventListener('submit', async function(e) {
    if (e.target && e.target.id === 'update-form') {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const data = {};
        
        // Собираем данные формы
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        // Проверяем, если выбран custom вариант
        const distrSelect = document.getElementById('distr-url');
        const customInput = document.getElementById('custom-distr-url');
        
        if (distrSelect && distrSelect.value === 'custom' && customInput && customInput.value) {
            data.distr_url = customInput.value;
        }
        
        // Обрабатываем форму
        await processUpdateForm(data);
    }
})
	
/**
 * Сохраняет текущее состояние развернутых групп
 */
function saveTableState() {
    expandedGroups = [];
    
    // Находим все развёрнутые группы и сохраняем их имена
    document.querySelectorAll('.group-row.expanded').forEach(row => {
        const groupName = row.getAttribute('data-group');
        if (groupName) {
            expandedGroups.push(groupName);
        }
    });
    
    console.log('Сохранено состояние групп:', expandedGroups);
}

/**
 * Восстанавливает сохраненное состояние развернутых групп
 */
function restoreTableState() {
    if (!expandedGroups || expandedGroups.length === 0) return;
    
    console.log('Восстановление состояния групп:', expandedGroups);
    
    expandedGroups.forEach(groupName => {
        const groupRow = document.querySelector(`.group-row[data-group="${groupName}"]`);
        if (groupRow) {
            groupRow.classList.add('expanded');
            
            const toggle = groupRow.querySelector('.group-toggle');
            if (toggle) {
                toggle.style.transform = 'rotate(90deg)';
            }
            
            const wrapperRow = document.querySelector(`.child-wrapper[data-group="${groupName}"]`);
            if (wrapperRow) {
                wrapperRow.style.display = 'table-row';
            }
        }
    });
    
    // Обновляем обработчики кнопок после восстановления групп
    setupAppActionButtons();
    setupGroupActionButtons();
}

/**
 * Создает строку для дочернего элемента группы
 * @param {Object} app - данные приложения
 * @returns {HTMLElement} - DOM элемент строки таблицы
 */
function createChildRow(app) {
    const childRow = document.createElement('tr');
    childRow.setAttribute('data-app-id', app.id);
    childRow.className = 'app-child-row'; // Добавляем класс для стилизации
    
    // Статус приложения
    const statusDot = app.status === 'online' ? 
        '<span class="service-dot"></span>' : 
        '<span class="service-dot offline"></span>';
    
    // Создаем ячейки для дочерней строки
    childRow.innerHTML = `
        <td>
            <div class="checkbox-container">
                <label class="custom-checkbox">
                    <input type="checkbox" class="app-checkbox" data-app-id="${app.id}">
                    <span class="checkmark"></span>
                </label>
            </div>
        </td>
        <td class="service-name">${app.name}</td>
        <td>${app.version || 'Н/Д'}</td>
        <td>${statusDot} ${app.status}</td>
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
    
    return childRow;
}

/**
 * Создает строку группы с правильной стилизацией стрелки
 * @param {string} groupName - имя группы
 * @param {Array} groupApps - приложения в группе
 * @returns {HTMLElement} - DOM элемент строки таблицы
 */
function createGroupRow(groupName, groupApps) {
    const row = document.createElement('tr');
    row.className = 'group-row';
    row.setAttribute('data-group', groupName);
    
    // Проверяем версии в группе
    const versions = new Set(groupApps.map(app => app.version || 'Н/Д'));
    const versionText = versions.size === 1 ? 
        (groupApps[0].version || 'Н/Д') : 
        '<span class="version-different">*</span>';
    
    // Проверяем статус всех приложений в группе
    const hasOffline = groupApps.some(app => app.status !== 'online');
    const statusDot = hasOffline ? 
        '<span class="service-dot offline"></span>' : 
        '<span class="service-dot"></span>';
    
    // Сервер для группы (берем из первого приложения)
    const serverName = groupApps[0].server_name || 'Н/Д';
    
    row.innerHTML = `
        <td>
            <div class="checkbox-container">
                <label class="custom-checkbox">
                    <input type="checkbox" class="group-checkbox" data-group="${groupName}">
                    <span class="checkmark"></span>
                </label>
            </div>
        </td>
        <td class="service-name">
            <div class="group-name-container">
                <span class="group-toggle">▶</span>
                <span class="group-name">${groupName} (${groupApps.length})</span>
            </div>
        </td>
        <td>${versionText}</td>
        <td>${statusDot} ${hasOffline ? 'Частично офлайн' : 'Онлайн'}</td>
        <td>${serverName}</td>
        <td>
            <div class="actions-menu">
                <button class="actions-button">...</button>
                <div class="actions-dropdown">
                    ${createGroupActionMenu(groupName, groupApps)}
                </div>
            </div>
        </td>
    `;
    
    return row;
}

function initDropdownHandlers() {
    // Создаем оверлей для закрытия меню при клике вне его
    if (!dropdownOverlay) {
        dropdownOverlay = document.createElement('div');
        dropdownOverlay.className = 'dropdown-overlay';
        document.body.appendChild(dropdownOverlay);
        
        // Обработчик клика на оверлей (закрывает меню)
        dropdownOverlay.addEventListener('click', closeAllDropdowns);
    }
    
    // Обработчик для кнопок меню действий
    document.body.addEventListener('click', function(e) {
        const actionButton = e.target.closest('.actions-button');
        if (actionButton) {
            e.preventDefault();
            e.stopPropagation();
            
            // Закрываем другие открытые меню
            if (activeDropdown && activeDropdown !== actionButton.nextElementSibling) {
                closeAllDropdowns();
            }
            
            // Открываем/закрываем текущее меню
            toggleDropdown(actionButton);
        }
    });
}

// Функция для переключения состояния выпадающего меню
function toggleDropdown(actionButton) {
    const dropdown = actionButton.nextElementSibling;
    
    if (dropdown.classList.contains('show')) {
        // Если меню уже открыто, закрываем его
        closeAllDropdowns();
    } else {
        // Закрываем все другие меню
        closeAllDropdowns();
        
        // Показываем оверлей
        dropdownOverlay.style.display = 'block';
        
        // Позиционируем и показываем меню
        positionDropdown(dropdown, actionButton);
        
        // Сохраняем ссылку на активное меню
        activeDropdown = dropdown;
    }
}

// Функция для правильного позиционирования выпадающего меню
function positionDropdown(dropdown, actionButton) {
    // Получаем координаты кнопки относительно viewport
    const buttonRect = actionButton.getBoundingClientRect();
    
    // Определяем, есть ли место под кнопкой для выпадающего меню
    // Обычно проверяем, хватает ли 200px вниз (примерная высота меню)
    const spaceBelow = window.innerHeight - buttonRect.bottom;
    const showUpwards = spaceBelow < 200;
    
    // Устанавливаем начальные свойства для расчета размеров
    dropdown.style.display = 'block';
    dropdown.style.opacity = '0';  // Скрываем, пока позиционируем
    
    // Сбрасываем предыдущие классы направления
    dropdown.classList.remove('dropdown-up');
    
    // Устанавливаем позицию
    if (showUpwards) {
        // Показываем меню вверх от кнопки
        dropdown.classList.add('dropdown-up');
        dropdown.style.bottom = (window.innerHeight - buttonRect.top) + 'px';
    } else {
        // Показываем меню вниз от кнопки
        dropdown.style.top = buttonRect.bottom + 'px';
    }
    
    // Устанавливаем горизонтальное положение (справа от кнопки)
    dropdown.style.right = (window.innerWidth - buttonRect.right) + 'px';
    
    // Показываем меню с анимацией
    dropdown.classList.add('show');
    dropdown.style.opacity = '1';
	
    // Добавляем класс активной кнопке для визуальной индикации
    actionButton.classList.add('active');	
}

// Функция для закрытия всех выпадающих меню
function closeAllDropdowns() {
    // Скрываем оверлей
    if (dropdownOverlay) {
        dropdownOverlay.style.display = 'none';
    }
    
    // Скрываем все выпадающие меню
    document.querySelectorAll('.actions-dropdown.show').forEach(dropdown => {
        dropdown.classList.remove('show');
        dropdown.style.display = '';
        dropdown.style.top = '';
        dropdown.style.right = '';
        dropdown.style.bottom = '';
		
       // Убираем активное состояние с кнопки
        const parentMenu = dropdown.closest('.actions-menu');
        if (parentMenu) {
            const actionButton = parentMenu.querySelector('.actions-button');
            if (actionButton) {
                actionButton.classList.remove('active');
            }
        }
    });
    
    // Сбрасываем ссылку на активное меню
    activeDropdown = null;
}

/**
 * Проверяет, доступно ли действие для приложения с определенным статусом
 */
function isActionAvailable(app, action) {
    const status = (app.status || '').toLowerCase();
    
    switch(action) {
        case 'start':
            return status !== 'online';
        case 'stop':
        case 'restart':
            return status === 'online';
        case 'update':
            return true;
        default:
            return true;
    }
}

/**
 * Проверяет доступность группового действия
 */
function isGroupActionAvailable(apps, action) {
    if (!apps || apps.length === 0) {
        return false;
    }
    
    switch(action) {
        case 'start':
            return apps.some(app => (app.status || '').toLowerCase() !== 'online');
        case 'stop':
        case 'restart':
            return apps.some(app => (app.status || '').toLowerCase() === 'online');
        case 'update':
            return true;
        default:
            return true;
    }
}

/**
 * Создает пункты меню с учетом статуса приложения
 */
function createActionMenuItems(app) {
    return `
        <a href="#" class="app-info-btn" data-app-id="${app.id}">Информация</a>
        <a href="#" class="app-start-btn ${!isActionAvailable(app, 'start') ? 'disabled' : ''}" 
           data-app-id="${app.id}" data-action="start">Запустить</a>
        <a href="#" class="app-stop-btn ${!isActionAvailable(app, 'stop') ? 'disabled' : ''}" 
           data-app-id="${app.id}" data-action="stop">Остановить</a>
        <a href="#" class="app-restart-btn ${!isActionAvailable(app, 'restart') ? 'disabled' : ''}" 
           data-app-id="${app.id}" data-action="restart">Перезапустить</a>
        <a href="#" class="app-update-btn" data-app-id="${app.id}">Обновить</a>
    `;
}

/**
 * Создает меню групповых действий
 */
function createGroupActionMenu(group, apps) {
    return `
        <a href="#" class="group-info-btn" data-group="${group}">Информация</a>
        <a href="#" class="group-start-btn ${!isGroupActionAvailable(apps, 'start') ? 'disabled' : ''}" 
           data-group="${group}" data-action="start">Запустить все</a>
        <a href="#" class="group-stop-btn ${!isGroupActionAvailable(apps, 'stop') ? 'disabled' : ''}" 
           data-group="${group}" data-action="stop">Остановить все</a>
        <a href="#" class="group-restart-btn ${!isGroupActionAvailable(apps, 'restart') ? 'disabled' : ''}" 
           data-group="${group}" data-action="restart">Перезапустить все</a>
        <a href="#" class="group-update-btn" 
           data-group="${group}" data-action="update">Обновить все</a>
    `;
}


// === ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ ВЫПАДАЮЩИМИ МЕНЮ ===

/**
 * Инициализация обработчиков меню
 */
function initClickDropdowns() {
    console.log('Инициализация меню...'); // Для отладки
    if (!dropdownOverlay) {
        dropdownOverlay = document.createElement('div');
        dropdownOverlay.className = 'dropdown-overlay';
        document.body.appendChild(dropdownOverlay);
        dropdownOverlay.addEventListener('click', closeAllDropdowns);
    }
    
    document.body.addEventListener('click', function(e) {
        const actionButton = e.target.closest('.actions-button');
        if (actionButton) {
            e.preventDefault();
            e.stopPropagation();
            toggleClickDropdown(actionButton);
        }
    });
}

/**
 * Переключение состояния выпадающего меню
 */
function toggleClickDropdown(actionButton) {
    const dropdown = actionButton.nextElementSibling;
    
    // Проверяем, открыто ли уже это меню (по CSS классу, а не по переменной)
    if (dropdown.classList.contains('show')) {
        console.log('меню уже открыто...'); // Для отладки
        // Если меню уже открыто - закрываем его
        //closeAllDropdowns();
        return;
    }
    
    // Закрываем все другие меню
    closeAllDropdowns();
    
    // Показываем оверлей
    dropdownOverlay.style.display = 'block';
    
    // Позиционируем и показываем меню
    positionClickDropdown(dropdown, actionButton);
    
    // Сохраняем ссылку на активное меню
    activeDropdown = dropdown;
}

/**
 * Позиционирование выпадающего меню
 */
function positionClickDropdown(dropdown, actionButton) {
    const buttonRect = actionButton.getBoundingClientRect();
    const spaceBelow = window.innerHeight - buttonRect.bottom;
    const showUpwards = spaceBelow < 200;
    
    dropdown.style.display = 'block';
    dropdown.style.opacity = '0';
    dropdown.classList.remove('dropdown-up');
    
    if (showUpwards) {
        dropdown.classList.add('dropdown-up');
        dropdown.style.bottom = (window.innerHeight - buttonRect.top) + 'px';
    } else {
        dropdown.style.top = buttonRect.bottom + 'px';
    }
    
    dropdown.style.right = (window.innerWidth - buttonRect.right) + 'px';
    dropdown.classList.add('show');
    dropdown.style.opacity = '1';
    actionButton.classList.add('active');
}

/**
 * Закрытие всех выпадающих меню
 */
function closeAllDropdowns() {
    if (dropdownOverlay) {
        dropdownOverlay.style.display = 'none';
    }
    
    document.querySelectorAll('.actions-dropdown.show').forEach(dropdown => {
        dropdown.classList.remove('show');
        dropdown.style.display = '';
        dropdown.style.top = '';
        dropdown.style.right = '';
        dropdown.style.bottom = '';
        
        const parentMenu = dropdown.closest('.actions-menu');
        if (parentMenu) {
            const actionButton = parentMenu.querySelector('.actions-button');
            if (actionButton) {
                actionButton.classList.remove('active');
            }
        }
    });
    
    activeDropdown = null;
}

/**
 * Функция очистки кэша артефактов (вызывается при необходимости)
 */
function clearArtifactsCache(appId = null) {
    if (appId) {
        // Очищаем кэш для конкретного приложения
        delete artifactsCache[`app_${appId}`];
        console.log(`Кэш артефактов очищен для приложения ${appId}`);
    } else {
        // Очищаем весь кэш
        Object.keys(artifactsCache).forEach(key => {
            delete artifactsCache[key];
        });
        console.log('Весь кэш артефактов очищен');
    }
}

/**
 * Функция проверки возраста кэша
 */
function getArtifactsCacheAge(appId) {
    const cacheKey = `app_${appId}`;
    if (artifactsCache[cacheKey]) {
        const age = Date.now() - artifactsCache[cacheKey].timestamp;
        return Math.round(age / 1000); // возвращаем в секундах
    }
    return null;
}

// Добавляем глобальную функцию для отладки кэша
window.debugArtifactsCache = function() {
    console.log('=== Artifacts Cache Debug ===');
    Object.keys(artifactsCache).forEach(key => {
        const cache = artifactsCache[key];
        const age = Math.round((Date.now() - cache.timestamp) / 1000);
        console.log(`${key}: ${cache.data.length} versions, age: ${age}s`);
    });
    console.log('===========================');
};



});
        
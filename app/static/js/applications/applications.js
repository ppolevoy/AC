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
				childRow.className = 'app-child-row'; // Добавляем класс для стилизации
				childRow.setAttribute('data-app-id', app.id);
				childRow.setAttribute('data-parent', group.name);
				
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
					<td class="service-name">
						${app.name}
						<div class="dist-details">
							<div>Время запуска: ${app.start_time ? new Date(app.start_time).toLocaleString() : 'Н/Д'}</div>
							<div>Тип: ${app.type || 'Н/Д'}</div>
						</div>
					</td>
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
				
				// Добавляем обработчик клика непосредственно для этой строки
				childRow.addEventListener('click', function(e) {
					// Игнорируем клики на чекбоксы и меню действий
					if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
						return;
					}
					// Переключаем класс expanded для текущей строки
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
        // Пропускаем строки-обертки и группы
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
        // Удаляем существующие обработчики через клонирование
        const newBtn = btn.cloneNode(true);
        if (btn.parentNode) {
            btn.parentNode.replaceChild(newBtn, btn);
        }
        
        // Добавляем новый обработчик
        newBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation(); // Предотвращаем всплытие
            
            // Выделяем действие из имени класса
            const className = this.className;
            let action;
            
            if (className.includes('info-btn')) action = 'info';
            else if (className.includes('start-btn')) action = 'start';
            else if (className.includes('stop-btn')) action = 'stop';
            else if (className.includes('restart-btn')) action = 'restart';
            else if (className.includes('update-btn')) action = 'update';
            else {
                console.error('Неизвестное действие из класса:', className);
                return;
            }
            
            const appId = this.getAttribute('data-app-id');
            console.log(`Клик на кнопке ${action} для приложения ${appId}`);
            
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
                default:
                    console.error('Неизвестное действие:', action);
                    break;
            }
        });
    });
}

/**
 * Устанавливает обработчики для кнопок действий групп
 */
function setupGroupActionButtons() {
    // Обработчики для кнопок в выпадающем меню групп
    document.querySelectorAll('.group-info-btn, .group-start-btn, .group-stop-btn, .group-restart-btn, .group-update-btn').forEach(btn => {
        // Удаляем существующие обработчики через клонирование
        const newBtn = btn.cloneNode(true);
        if (btn.parentNode) {
            btn.parentNode.replaceChild(newBtn, btn);
        }
        
        // Добавляем новый обработчик
        newBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation(); // Предотвращаем всплытие
            
            // Выделяем действие из имени класса
            const className = this.className;
            let action;
            
            if (className.includes('start-btn')) action = 'start';
            else if (className.includes('stop-btn')) action = 'stop';
            else if (className.includes('restart-btn')) action = 'restart';
            else if (className.includes('update-btn')) action = 'update';
            else {
                console.error('Неизвестное действие из класса:', className);
                return;
            }
            
            const groupName = this.getAttribute('data-group');
            console.log(`Клик на кнопке ${action} для группы ${groupName}`);
            
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
    // Собираем ID всех приложений в группе
    const appIds = [];
    document.querySelectorAll(`.child-wrapper[data-group="${groupName}"] .app-checkbox`).forEach(checkbox => {
        const appId = checkbox.getAttribute('data-app-id');
        if (appId) {
            appIds.push(appId);
        }
    });
    
    if (appIds.length === 0) {
        showError('Не найдены приложения в группе');
        return;
    }
    
    console.log(`Действие ${action} для группы ${groupName}, приложения:`, appIds);
    
    // Обрабатываем действие
    switch(action) {
        case 'update':
            showUpdateModal(appIds);
            break;
        case 'start':
        case 'stop':
        case 'restart':
            showConfirmActionModal(appIds, action);
            break;
        default:
            showError(`Неподдерживаемое действие для группы: ${action}`);
            break;
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
function showSimpleUpdateModal(appIds, title) {
    const appIdsArray = Array.isArray(appIds) ? appIds : [appIds];
    
    // Определяем значение дистрибутива по умолчанию
    let defaultDistrPath = '';
    if (appIdsArray.length === 1) {
        const app = getAppById(appIdsArray[0]);
        if (app && app.distr_path) {
            defaultDistrPath = app.distr_path;
        }
    }
    
    // Определяем поля формы
    const formFields = [
        {
            id: 'distr-url',
            name: 'distr_url',
            label: 'URL дистрибутива:',
            type: 'text',
            value: defaultDistrPath,
            required: true
        },
        {
            id: 'restart-mode',
            name: 'restart_mode',
            label: 'Режим обновления:',
            type: 'radio',
            value: 'restart',
            options: [
                { value: 'restart', text: 'В рестарт' },
                { value: 'immediate', text: 'Сейчас' }
            ]
        },
        {
            id: 'app-ids',
            name: 'app_ids',
            type: 'hidden',
            value: appIdsArray.join(',')
        }
    ];
    
    // Функция, которая будет выполнена при отправке формы
    const submitAction = processUpdateForm;
    
    // Отображаем модальное окно с формой
    ModalUtils.showFormModal(title, formFields, submitAction, 'Обновить');
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
    
    // Создаем вкладки
    Object.keys(appGroups).forEach((groupName, index) => {
        const tab = document.createElement('div');
        tab.className = `modal-tab ${index === 0 ? 'active' : ''}`;
        tab.textContent = groupName;
        tab.setAttribute('data-group', groupName);
        tabsContainer.appendChild(tab);
    });
    
    // Создаем скрытое поле для хранения ID приложений
    const appIdsInput = document.createElement('input');
    appIdsInput.type = 'hidden';
    appIdsInput.id = 'app-ids';
    appIdsInput.name = 'app_ids';
    form.appendChild(appIdsInput);
    
    // Создаем поле для URL дистрибутива
    const distrUrlGroup = document.createElement('div');
    distrUrlGroup.className = 'form-group';
    
    const distrUrlLabel = document.createElement('label');
    distrUrlLabel.setAttribute('for', 'distr-url');
    distrUrlLabel.textContent = 'URL дистрибутива:';
    distrUrlGroup.appendChild(distrUrlLabel);
    
    const distrUrlInput = document.createElement('input');
    distrUrlInput.type = 'text';
    distrUrlInput.id = 'distr-url';
    distrUrlInput.name = 'distr_url';
    distrUrlInput.className = 'form-control';
    distrUrlInput.required = true;
    distrUrlGroup.appendChild(distrUrlInput);
    
    form.appendChild(distrUrlGroup);
    
    // Создаем поле для режима обновления
    const restartModeGroup = document.createElement('div');
    restartModeGroup.className = 'form-group';
    
    const restartModeLabel = document.createElement('label');
    restartModeLabel.textContent = 'Режим обновления:';
    restartModeGroup.appendChild(restartModeLabel);
    
    const radioGroup = document.createElement('div');
    radioGroup.className = 'radio-group';
    
    const restartLabel = document.createElement('label');
    restartLabel.className = 'radio-label';
    
    const restartInput = document.createElement('input');
    restartInput.type = 'radio';
    restartInput.id = 'restart-mode-restart';
    restartInput.name = 'restart_mode';
    restartInput.value = 'restart';
    restartInput.checked = true;
    restartLabel.appendChild(restartInput);
    restartLabel.appendChild(document.createTextNode(' В рестарт'));
    
    radioGroup.appendChild(restartLabel);
    
    const immediateLabel = document.createElement('label');
    immediateLabel.className = 'radio-label';
    
    const immediateInput = document.createElement('input');
    immediateInput.type = 'radio';
    immediateInput.id = 'restart-mode-immediate';
    immediateInput.name = 'restart_mode';
    immediateInput.value = 'immediate';
    immediateLabel.appendChild(immediateInput);
    immediateLabel.appendChild(document.createTextNode(' Сейчас'));
    
    radioGroup.appendChild(immediateLabel);
    
    restartModeGroup.appendChild(radioGroup);
    
    form.appendChild(restartModeGroup);
    
    // Создаем кнопки действий
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
    
    // Создаем хранилище состояний для каждой группы
    const groupStates = {};
    
    // Инициализируем состояния для каждой группы
    Object.keys(appGroups).forEach(groupName => {
        const apps = appGroups[groupName];
        const firstApp = apps[0];
        
        // Индивидуальное начальное состояние для каждой группы
        groupStates[groupName] = {
            appIds: apps.map(app => app.id),
            distrUrl: firstApp && firstApp.distr_path ? firstApp.distr_path : '',
            restartMode: 'restart' // По умолчанию "В рестарт"
        };
    });
    
    // Функция для сохранения текущего состояния группы
    function saveCurrentGroupState() {
        const currentGroup = tabsContainer.querySelector('.modal-tab.active');
        if (currentGroup) {
            const groupName = currentGroup.getAttribute('data-group');
            groupStates[groupName] = {
                appIds: groupStates[groupName].appIds, // ID приложений не меняются
                distrUrl: distrUrlInput.value,
                restartMode: form.querySelector('input[name="restart_mode"]:checked').value
            };
        }
    }
    
    // Функция для загрузки состояния для указанной группы
    function loadGroupState(groupName) {
        const state = groupStates[groupName];
        
        // Устанавливаем ID приложений
        appIdsInput.value = state.appIds.join(',');
        
        // Устанавливаем URL дистрибутива
        distrUrlInput.value = state.distrUrl;
        
        // Устанавливаем режим обновления (безопасным способом)
        const restartRadio = form.querySelector('input[name="restart_mode"][value="restart"]');
        const immediateRadio = form.querySelector('input[name="restart_mode"][value="immediate"]');
        
        if (state.restartMode === 'immediate' && immediateRadio) {
            immediateRadio.checked = true;
            if (restartRadio) restartRadio.checked = false;
        } else if (restartRadio) {
            restartRadio.checked = true;
            if (immediateRadio) immediateRadio.checked = false;
        }
    }
    
    // Отображаем модальное окно ПЕРЕД инициализацией состояния
    window.showModal(title, modalContent);
    
    // После добавления элементов в DOM, загружаем состояние для первой группы
    const firstGroup = Object.keys(appGroups)[0];
    loadGroupState(firstGroup);
    
    // Добавляем обработчики для вкладок
    tabsContainer.querySelectorAll('.modal-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            // Сохраняем текущее состояние перед переключением
            saveCurrentGroupState();
            
            // Убираем активный класс со всех вкладок
            tabsContainer.querySelectorAll('.modal-tab').forEach(t => {
                t.classList.remove('active');
            });
            
            // Делаем текущую вкладку активной
            this.classList.add('active');
            
            // Загружаем состояние для выбранной группы
            const groupName = this.getAttribute('data-group');
            loadGroupState(groupName);
        });
    });
    
	form.addEventListener('submit', function(e) {
		e.preventDefault();
		
		// Сохраняем текущее состояние перед отправкой
		saveCurrentGroupState();
		
		// Собираем данные из всех групп
		const formDataArray = Object.keys(groupStates).map(groupName => {
			const state = groupStates[groupName];
			
			// Пропускаем группы без URL
			if (!state.distrUrl) {
				return null;
			}
			
			return {
				app_ids: state.appIds.join(','),
				distr_url: state.distrUrl,
				restart_mode: state.restartMode
			};
		}).filter(data => data !== null); // Удаляем пустые элементы
		
		// Проверяем, заполнены ли все группы
		if (formDataArray.length === 0) {
			showError('Укажите URL дистрибутива хотя бы для одной группы');
			return;
		}
		
		// Обрабатываем все группы
		processUpdateForm(formDataArray, true); // true означает закрыть окно после обработки
	});
}

	/**
	 * Обрабатывает данные формы обновления
	 * @param {Object|Array} formData - Данные формы или массив данных форм
	 * @param {boolean} closeAfterSubmit - Закрыть модальное окно после отправки
	 */
	async function processUpdateForm(formData, closeAfterSubmit = true) {
		try {
			let successCount = 0;
			let totalCount = 0;
			
			// Проверяем, является ли formData массивом
			if (Array.isArray(formData)) {
				// Обрабатываем массив данных форм
				const allPromises = [];
				
				formData.forEach(data => {
					if (data.app_ids && data.distr_url) {
						const appIds = data.app_ids.split(',').map(id => parseInt(id.trim()));
						
						// Создаем запросы для всех приложений в этой группе
						appIds.forEach(appId => {
							const promise = fetch(`/api/applications/${appId}/update`, {
								method: 'POST',
								headers: {
									'Content-Type': 'application/json'
								},
								body: JSON.stringify({
									distr_url: data.distr_url,
									restart_mode: data.restart_mode
								})
							}).then(response => response.json());
							
							allPromises.push(promise);
							totalCount++;
						});
					}
				});
				
				// Ждем выполнения всех запросов
				const results = await Promise.all(allPromises);
				
				// Подсчитываем успешные запросы
				successCount = results.filter(result => result.success).length;
			} else {
				// Обрабатываем одиночную форму
				const appIds = formData.app_ids.split(',').map(id => parseInt(id.trim()));
				
				// Создаем массив запросов для всех приложений
				const updatePromises = appIds.map(appId => 
					fetch(`/api/applications/${appId}/update`, {
						method: 'POST',
						headers: {
							'Content-Type': 'application/json'
						},
						body: JSON.stringify({
							distr_url: formData.distr_url,
							restart_mode: formData.restart_mode
						})
					}).then(response => response.json())
				);
				
				// Ждем выполнения всех запросов
				const results = await Promise.all(updatePromises);
				
				// Подсчитываем успешные запросы
				successCount = results.filter(result => result.success).length;
				totalCount = results.length;
			}
			
			// Закрываем модальное окно, если нужно
			if (closeAfterSubmit) {
				window.closeModal();
			}
			
			// Анализируем результаты
			if (successCount === totalCount) {
				showNotification(`Обновление успешно запущено для всех выбранных приложений`);
			} else if (successCount === 0) {
				showError(`Не удалось запустить обновление ни для одного из выбранных приложений`);
			} else {
				showNotification(`Обновление запущено для ${successCount} из ${totalCount} приложений`);
			}
			
			// Обновляем список приложений
			loadApplications();
		} catch (error) {
			console.error('Ошибка при обновлении приложений:', error);
			showError('Не удалось запустить обновление приложений');
			
			// Закрываем модальное окно, если нужно
			if (closeAfterSubmit) {
				window.closeModal();
			}
		}
	}
	
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



	
});
        
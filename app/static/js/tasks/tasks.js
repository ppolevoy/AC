/**
 * Faktura Apps - Модуль для страницы задач
 */

document.addEventListener('DOMContentLoaded', function() {
    // DOM-элементы
    const statusFilter = document.getElementById('status-filter');
    const autoRefreshSelect = document.getElementById('auto-refresh');
    const refreshBtn = document.getElementById('refresh-tasks-btn');
    const tasksTableBody = document.getElementById('tasks-table-body');
    const pageSizeSelect = document.getElementById('page-size');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const currentPageSpan = document.getElementById('current-page');
    const lastUpdatedSpan = document.getElementById('last-updated-time');
    
    // Переменные для пагинации и авто-обновления
    let currentPage = 1;
    let pageSize = 10;
    let totalTasks = 0;
    let refreshInterval = null;
    let refreshTime = 5; // Секунды
    
    // Инициализация страницы
    init();
    
    /**
     * Инициализация обработчиков событий
     */
    function init() {
        // Фильтр по статусу
        if (statusFilter) {
            statusFilter.addEventListener('change', loadTasks);
        }
        
        // Настройка автообновления
        if (autoRefreshSelect) {
            autoRefreshSelect.addEventListener('change', function() {
                refreshTime = parseInt(this.value);
                setupAutoRefresh();
            });
        }
        
        // Кнопка обновления
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadTasks);
        }
        
        // Размер страницы
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', function() {
                pageSize = parseInt(this.value);
                currentPage = 1;
                loadTasks();
            });
        }
        
        // Пагинация
        if (prevPageBtn) {
            prevPageBtn.addEventListener('click', function() {
                if (currentPage > 1) {
                    currentPage--;
                    loadTasks();
                }
            });
        }
        
        if (nextPageBtn) {
            nextPageBtn.addEventListener('click', function() {
                const totalPages = Math.ceil(totalTasks / pageSize);
                if (currentPage < totalPages) {
                    currentPage++;
                    loadTasks();
                }
            });
        }
        
        // Загружаем список задач при загрузке страницы
        loadTasks();
        
        // Устанавливаем автообновление
        setupAutoRefresh();
    }
    
    /**
     * Загрузка списка задач
     */
    async function loadTasks() {
        try {
            // Получаем выбранный статус фильтра
            const status = statusFilter && statusFilter.value !== 'all' ? statusFilter.value : null;

            // Формируем URL с параметрами
            let url = '/api/tasks';
            const params = new URLSearchParams();

            if (status) {
                params.append('status', status);
            }

            if (params.toString()) {
                url += '?' + params.toString();
            }

            const response = await fetch(url);
            const data = await response.json();

            if (data.success) {
                renderTasks(data.tasks);
                updateLastUpdatedTime();
            } else {
                console.error('Ошибка при загрузке задач:', data.error);
                showError('Не удалось загрузить список задач');
                if (tasksTableBody) {
                    tasksTableBody.innerHTML = '<tr><td colspan="7" class="table-loading error">Ошибка загрузки задач</td></tr>';
                }
            }
        } catch (error) {
            console.error('Ошибка при загрузке задач:', error);
            showError('Не удалось загрузить список задач');
            if (tasksTableBody) {
                tasksTableBody.innerHTML = '<tr><td colspan="7" class="table-loading error">Ошибка загрузки задач</td></tr>';
            }
        }
    }
    
    /**
     * Отображение задач в таблице
     * @param {Array} tasks - Массив объектов задач
     */
    function renderTasks(tasks) {
        if (!tasksTableBody) return;
        
        tasksTableBody.innerHTML = '';
        
        if (tasks.length === 0) {
            tasksTableBody.innerHTML = '<tr><td colspan="7" class="table-loading">Нет задач, соответствующих критериям фильтра</td></tr>';
            totalTasks = 0;
            updatePagination();
            return;
        }
        
        totalTasks = tasks.length;
        
        // Применяем пагинацию
        const startIndex = (currentPage - 1) * pageSize;
        const endIndex = Math.min(startIndex + pageSize, tasks.length);
        const displayedTasks = tasks.slice(startIndex, endIndex);
        
        displayedTasks.forEach(task => {
            const row = document.createElement('tr');
            
            // Определяем класс для статуса
            let statusClass = '';
            let statusText = task.status;
            
            if (task.status === 'pending') {
                statusClass = 'status-pending';
                statusText = 'Ожидает';
            } else if (task.status === 'processing') {
                statusClass = 'status-processing';
                statusText = 'Выполняется';
            } else if (task.status === 'completed') {
                statusClass = 'status-completed';
                statusText = 'Завершена';
            } else if (task.status === 'failed') {
                statusClass = 'status-failed';
                statusText = 'Ошибка';
            }
            
            // Форматируем дату создания
            const createdDate = new Date(task.created_at);
            const createdDateStr = formatDate(createdDate);
            
            // Получаем сокращенный ID задачи для отображения
            const shortId = task.id.substring(0, 8) + '...';
            
            row.innerHTML = `
                <td class="col-id task-id-cell">${shortId}</td>
                <td class="col-type">${formatTaskType(task.task_type)}</td>
                <td class="col-app">${task.application_name || '-'}</td>
                <td class="col-server">${task.server_name || '-'}</td>
                <td class="col-status"><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td class="col-created">${createdDateStr}</td>
                <td class="col-actions">
                    <button class="task-action-btn view-task-btn" data-task-id="${task.id}" title="Посмотреть детали">
                        <i class="action-icon">ℹ</i>
                    </button>
                </td>
            `;
            
            tasksTableBody.appendChild(row);
        });
        
        // Обновляем пагинацию
        updatePagination();
        
        // Добавляем обработчики для кнопок просмотра деталей задачи
        document.querySelectorAll('.view-task-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const taskId = this.getAttribute('data-task-id');
                showTaskDetails(taskId);
            });
        });
    }
    
    /**
     * Обновление пагинации
     */
    function updatePagination() {
        if (!currentPageSpan || !prevPageBtn || !nextPageBtn) return;
        
        const totalPages = Math.ceil(totalTasks / pageSize);
        
        currentPageSpan.textContent = totalPages > 0 ? currentPage : 0;
        prevPageBtn.disabled = currentPage <= 1;
        nextPageBtn.disabled = currentPage >= totalPages;
    }
    
    // Используем функции formatDate и formatTaskType из utils.js
    
    /**
     * Обновление времени последнего обновления
     */
    function updateLastUpdatedTime() {
        if (!lastUpdatedSpan) return;
        
        const now = new Date();
        lastUpdatedSpan.textContent = formatDate(now);
    }
    
    /**
     * Функция для настройки интервала автообновления
     */
    function setupAutoRefresh() {
        // Сначала очищаем существующий интервал
        if (refreshInterval) {
            clearInterval(refreshInterval);
            refreshInterval = null;
        }
        
        // Устанавливаем новый интервал, если выбрано значение больше 0
        if (refreshTime > 0) {
            refreshInterval = setInterval(loadTasks, refreshTime * 1000);
        }
    }
    
    /**
     * Отображение деталей задачи в модальном окне
     * @param {string} taskId - ID задачи
     */
	async function showTaskDetails(taskId) {
		try {
			const response = await fetch(`/api/tasks/${taskId}`);
			const data = await response.json();
			
			if (!data.success) {
				console.error('Ошибка при получении информации о задаче:', data.error);
				showError('Не удалось получить информацию о задаче');
				return;
			}
			
			const task = data.task;
			
			// Создаем секции для модального окна
			const sections = [
				{
					title: 'Основная информация',
					type: 'table',
					rows: [
						{ label: 'ID:', value: task.id },
						{ label: 'Тип:', value: formatTaskType(task.task_type) },
						{ 
							label: 'Статус:', 
							value: `<span class="status-badge ${getStatusClass(task.status)}">${formatTaskStatus(task.status)}</span>` 
						},
						{ label: 'Приложение:', value: task.application_name || '-' },
						{ label: 'Сервер:', value: task.server_name || '-' }
					]
				},
				{
					title: 'Временные метки',
					type: 'table',
					rows: [
						{ label: 'Создана:', value: task.created_at ? formatDate(new Date(task.created_at)) : '-' },
						{ label: 'Начата:', value: task.started_at ? formatDate(new Date(task.started_at)) : '-' },
						{ label: 'Завершена:', value: task.completed_at ? formatDate(new Date(task.completed_at)) : '-' }
					]
				}
			];
			
			// Добавляем секцию с параметрами задачи
			const paramsSection = {
				title: 'Параметры',
				type: 'html',
				content: `<pre class="task-params">${JSON.stringify(task.params, null, 2) || '{}'}</pre>`
			};
			sections.push(paramsSection);
			
			// Добавляем секцию с результатом выполнения
			const resultSection = {
				title: 'Результат',
				type: 'html',
				content: `<div class="task-result">${task.result || 'Нет данных'}</div>`
			};
			sections.push(resultSection);
			
			// Добавляем секцию с ошибкой, если она есть
			if (task.error) {
				const errorSection = {
					title: 'Ошибка',
					type: 'html',
					content: `<div class="task-error">${task.error}</div>`
				};
				sections.push(errorSection);
			}
			
			// Отображаем модальное окно
			ModalUtils.showInfoModal(`Детали задачи: ${formatTaskType(task.task_type)}`, sections);
		} catch (error) {
			console.error('Ошибка при получении информации о задаче:', error);
			showError('Не удалось получить информацию о задаче');
		}
	}
	
	// Вспомогательные функции для форматирования данных
	function formatTaskType(type) {
		const types = {
			'start': 'Запуск',
			'stop': 'Остановка',
			'restart': 'Перезапуск',
			'update': 'Обновление'
		};
		
		return types[type] || type;
	}

	function formatTaskStatus(status) {
		const statuses = {
			'pending': 'Ожидает',
			'processing': 'Выполняется',
			'completed': 'Завершена',
			'failed': 'Ошибка'
		};
		
		return statuses[status] || status;
	}

	function getStatusClass(status) {
		const classes = {
			'pending': 'status-pending',
			'processing': 'status-processing',
			'completed': 'status-completed',
			'failed': 'status-failed'
		};
		
		return classes[status] || '';
	}

	function formatDate(date) {
		if (!(date instanceof Date) || isNaN(date)) {
			return '-';
		}
		
		return date.toLocaleString('ru-RU', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}	
});
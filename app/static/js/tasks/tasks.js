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
                // Пересчитываем интервал (ускоренный для processing задач)
                setupAutoRefresh();
            } else {
                console.error('Ошибка при загрузке задач:', data.error);
                showError('Не удалось загрузить список задач');
                if (tasksTableBody) {
                    tasksTableBody.innerHTML = '<tr><td colspan="8" class="table-loading error">Ошибка загрузки задач</td></tr>';
                }
            }
        } catch (error) {
            console.error('Ошибка при загрузке задач:', error);
            showError('Не удалось загрузить список задач');
            if (tasksTableBody) {
                tasksTableBody.innerHTML = '<tr><td colspan="8" class="table-loading error">Ошибка загрузки задач</td></tr>';
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
            tasksTableBody.innerHTML = '<tr><td colspan="8" class="table-loading">Нет задач, соответствующих критериям фильтра</td></tr>';
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
            
            // Определяем, можно ли отменить задачу
            // can_cancel = true для pending задач и для processing задач с PID
            const canCancel = task.can_cancel;
            const cancelBtn = canCancel
                ? `<button class="task-action-btn cancel-task-btn" data-task-id="${task.id}" title="Отменить задачу">×</button>`
                : '';

            // Форматируем текущий этап для processing задач
            const currentTask = task.status === 'processing' && task.current_task
                ? `<span class="current-task">${escapeHtml(task.current_task)}</span>`
                : '-';

            row.innerHTML = `
                <td class="col-id task-id-cell">${shortId}</td>
                <td class="col-type">${formatTaskType(task.task_type, task.orchestrator_playbook)}</td>
                <td class="col-app">${task.application_name || '-'}</td>
                <td class="col-server">${task.server_name || '-'}</td>
                <td class="col-status"><span class="status-badge ${statusClass}">${statusText}${task.cancelled ? ' (отменена)' : ''}</span></td>
                <td class="col-progress">${currentTask}</td>
                <td class="col-created">${createdDateStr}</td>
                <td class="col-actions">
                    <button class="task-action-btn view-task-btn" data-task-id="${task.id}" title="Посмотреть детали">i</button>
                    ${cancelBtn}
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

        // Добавляем обработчики для кнопок отмены задачи
        document.querySelectorAll('.cancel-task-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const taskId = this.getAttribute('data-task-id');
                cancelTask(taskId);
            });
        });
    }

    /**
     * Отмена задачи
     * @param {string} taskId - ID задачи
     */
    async function cancelTask(taskId) {
        if (!confirm('Вы уверены, что хотите отменить эту задачу?')) {
            return;
        }

        try {
            const response = await fetch(`/api/tasks/${taskId}/cancel`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();

            if (data.success) {
                showSuccess('Задача отменена');
                loadTasks(); // Перезагружаем список задач
            } else {
                showError(data.error || 'Не удалось отменить задачу');
            }
        } catch (error) {
            console.error('Ошибка при отмене задачи:', error);
            showError('Не удалось отменить задачу');
        }
    }

    /**
     * Показать сообщение об успехе
     */
    function showSuccess(message) {
        if (typeof NotificationUtils !== 'undefined' && NotificationUtils.showSuccess) {
            NotificationUtils.showSuccess(message);
        } else {
            alert(message);
        }
    }

    /**
     * Показать сообщение об ошибке
     */
    function showError(message) {
        if (typeof NotificationUtils !== 'undefined' && NotificationUtils.showError) {
            NotificationUtils.showError(message);
        } else {
            alert('Ошибка: ' + message);
        }
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
     * Проверяет наличие задач в статусе processing
     */
    function hasProcessingTasks() {
        return document.querySelectorAll('.status-processing').length > 0;
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

        // Если есть processing задачи - обновляем каждую секунду
        // Иначе используем выбранный интервал
        const hasProcessing = hasProcessingTasks();
        const interval = hasProcessing ? 1000 : refreshTime * 1000;

        // Устанавливаем новый интервал, если выбрано значение больше 0
        if (interval > 0) {
            refreshInterval = setInterval(loadTasks, interval);
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
						{ label: 'Тип:', value: formatTaskType(task.task_type, task.orchestrator_playbook) },
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
						{ label: 'Создана:', value: formatDateTimeLocal(task.created_at) },
						{ label: 'Начата:', value: formatDateTimeLocal(task.started_at) },
						{ label: 'Завершена:', value: formatDateTimeLocal(task.completed_at) }
					]
				}
			];
			
			// Добавляем секцию с Display Summary из плейбуков (если есть)
			if (task.display_summaries && task.display_summaries.length > 0) {
				const displaySummaryHtml = formatDisplaySummaries(task.display_summaries);
				const displaySummarySection = {
					title: 'Результат выполнения',
					type: 'html',
					content: displaySummaryHtml
				};
				sections.push(displaySummarySection);
			} else if (task.result && task.status === 'completed') {
				// Fallback: показываем raw result если нет распарсенных summaries
				const resultSection = {
					title: 'Вывод Ansible',
					type: 'html',
					content: `<pre class="task-result">${escapeHtml(task.result)}</pre>`
				};
				sections.push(resultSection);
			}

			// Добавляем секцию с PLAY RECAP (если есть)
			if (task.ansible_summary && task.ansible_summary.length > 0) {
				const summaryHtml = formatAnsibleSummary(task.ansible_summary);
				const summarySection = {
					title: 'PLAY RECAP',
					type: 'html',
					content: summaryHtml
				};
				sections.push(summarySection);
			}

			// Добавляем секцию с параметрами задачи
			const paramsSection = {
				title: 'Параметры',
				type: 'html',
				content: `<pre class="task-params">${JSON.stringify(task.params, null, 2) || '{}'}</pre>`
			};
			sections.push(paramsSection);
			
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
			ModalUtils.showInfoModal(`Детали задачи: ${formatTaskType(task.task_type, task.orchestrator_playbook)}`, sections);
		} catch (error) {
			console.error('Ошибка при получении информации о задаче:', error);
			showError('Не удалось получить информацию о задаче');
		}
	}
	
	// Вспомогательные функции для форматирования данных
	function formatTaskType(type, orchestratorPlaybook) {
		const types = {
			'start': 'Запуск',
			'stop': 'Остановка',
			'restart': 'Перезапуск',
			'update': 'Обновление'
		};

		let result = types[type] || type;

		// Если это обновление через оркестратор - добавляем режим в скобках
		if (type === 'update' && orchestratorPlaybook) {
			// Извлекаем короткое имя: "/etc/ansible/orchestrator-50-50.yml" -> "50-50"
			const shortName = orchestratorPlaybook
				.replace(/^.*\//, '')           // убираем путь
				.replace(/^orchestrator[-_]?/, '') // убираем префикс orchestrator
				.replace(/\.ya?ml$/, '');       // убираем расширение

			if (shortName) {
				result += ` (${shortName})`;
			}
		}

		return result;
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

	/**
	 * Форматирование Display Summary из плейбуков
	 * @param {Array} summaries - Массив объектов {task_name, content}
	 * @returns {string} HTML строка
	 */
	function formatDisplaySummaries(summaries) {
		if (!summaries || summaries.length === 0) {
			return '<p>Нет данных</p>';
		}

		let html = '<div class="display-summaries">';

		for (const s of summaries) {
			html += '<div class="display-summary-block">';
			if (summaries.length > 1) {
				html += `<div class="display-summary-title">${escapeHtml(s.task_name)}</div>`;
			}
			html += `<pre class="display-summary-content">${escapeHtml(s.content)}</pre>`;
			html += '</div>';
		}

		html += '</div>';
		return html;
	}

	/**
	 * Форматирование Ansible Summary в HTML таблицу
	 * @param {Array} summaries - Массив объектов с результатами
	 * @returns {string} HTML строка
	 */
	function formatAnsibleSummary(summaries) {
		if (!summaries || summaries.length === 0) {
			return '<p>Нет данных</p>';
		}

		let html = '<table class="ansible-summary-table">';
		html += '<thead><tr>';
		html += '<th>Хост</th>';
		html += '<th class="col-ok">OK</th>';
		html += '<th class="col-changed">Changed</th>';
		html += '<th class="col-unreachable">Unreachable</th>';
		html += '<th class="col-failed">Failed</th>';
		html += '<th class="col-skipped">Skipped</th>';
		html += '</tr></thead>';
		html += '<tbody>';

		for (const s of summaries) {
			const hasErrors = s.failed > 0 || s.unreachable > 0;
			const rowClass = hasErrors ? 'summary-row-error' : 'summary-row-ok';

			html += `<tr class="${rowClass}">`;
			html += `<td class="col-host">${escapeHtml(s.host)}</td>`;
			html += `<td class="col-ok">${s.ok}</td>`;
			html += `<td class="col-changed">${s.changed > 0 ? `<span class="changed-value">${s.changed}</span>` : s.changed}</td>`;
			html += `<td class="col-unreachable">${s.unreachable > 0 ? `<span class="error-value">${s.unreachable}</span>` : s.unreachable}</td>`;
			html += `<td class="col-failed">${s.failed > 0 ? `<span class="error-value">${s.failed}</span>` : s.failed}</td>`;
			html += `<td class="col-skipped">${s.skipped}</td>`;
			html += '</tr>';
		}

		html += '</tbody></table>';
		return html;
	}

	/**
	 * Экранирование HTML для безопасного отображения
	 * @param {string} text - Исходный текст
	 * @returns {string} Экранированный текст
	 */
	function escapeHtml(text) {
		if (!text) return '';
		const div = document.createElement('div');
		div.textContent = text;
		return div.innerHTML;
	}
});
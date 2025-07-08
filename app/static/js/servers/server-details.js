/**
 * Faktura Apps - Модуль для страницы деталей сервера
 */

document.addEventListener('DOMContentLoaded', function() {
    // Получаем ID сервера из URL
    const pathParts = window.location.pathname.split('/');
    const serverId = pathParts[pathParts.length - 1];
    
    if (!serverId || isNaN(parseInt(serverId))) {
        showError('Некорректный ID сервера');
        return;
    }
    
    // Загружаем информацию о сервере
    loadServerDetails(serverId);
    
    // Обработчик для поиска приложений
    const appSearchInput = document.getElementById('app-search');
    if (appSearchInput) {
        appSearchInput.addEventListener('input', function() {
            filterApplications(this.value.toLowerCase());
        });
    }
});

/**
 * Загрузка информации о сервере
 * @param {string} serverId - ID сервера
 */
async function loadServerDetails(serverId) {
    try {
        const response = await fetch(`/api/servers/${serverId}`);
        const data = await response.json();
        
        if (data.success) {
            renderServerDetails(data.server);
        } else {
            console.error('Ошибка при загрузке информации о сервере:', data.error);
            showError('Не удалось загрузить информацию о сервере');
        }
    } catch (error) {
        console.error('Ошибка при загрузке информации о сервере:', error);
        showError('Не удалось загрузить информацию о сервере');
    }
}

/**
 * Отображение информации о сервере
 * @param {Object} server - Объект сервера с информацией о сервере и его приложениях
 */
function renderServerDetails(server) {
    // Обновляем заголовок страницы
    document.getElementById('server-name-display').textContent = server.name;
    
    // Отображаем статус сервера
    const statusContainer = document.getElementById('server-status');
    const statusClass = server.status === 'online' ? 'status-online' : 'status-offline';
    const statusText = server.status === 'online' ? 'Online' : 'Offline';
    
    statusContainer.innerHTML = `
        <div class="status-indicator ${statusClass}">
            <div class="status-dot"></div>
            <span>${statusText}</span>
        </div>
    `;
    
    // Отображаем основную информацию о сервере
    const infoContainer = document.getElementById('server-info-content');
    infoContainer.innerHTML = `
        <div class="info-grid">
            <div class="info-row">
                <div class="info-label">IP-адрес:</div>
                <div class="info-value">${server.ip}</div>
            </div>
            <div class="info-row">
                <div class="info-label">Порт:</div>
                <div class="info-value">${server.port}</div>
            </div>
            <div class="info-row">
                <div class="info-label">Последняя проверка:</div>
                <div class="info-value">${server.last_check ? new Date(server.last_check).toLocaleString() : 'Нет данных'}</div>
            </div>
            <div class="info-row">
                <div class="info-label">Количество приложений:</div>
                <div class="info-value">${server.applications ? server.applications.length : 0}</div>
            </div>
        </div>
        
        <div class="server-actions-panel">
            <button class="action-btn" id="refresh-server-btn">Обновить информацию</button>
            <button class="action-btn edit" id="edit-server-btn">Редактировать</button>
        </div>
    `;
    
    // Отображаем список приложений на сервере
    const appsContainer = document.getElementById('server-apps-content');
    
    if (!server.applications || server.applications.length === 0) {
        appsContainer.innerHTML = '<div class="no-data">На сервере нет приложений</div>';
        return;
    }
    
    // Сортируем приложения по статусу и имени
    const sortedApps = [...server.applications].sort((a, b) => {
        // Сначала по статусу (online наверху)
        if (a.status !== b.status) {
            return a.status === 'online' ? -1 : 1;
        }
        // Затем по имени
        return a.name.localeCompare(b.name);
    });
    
    // Создаем таблицу приложений
    let appsHtml = `
        <table class="apps-table">
            <thead>
                <tr>
                    <th>Имя</th>
                    <th>Версия</th>
                    <th>Статус</th>
                    <th>Тип</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    sortedApps.forEach(app => {
        const statusDot = app.status === 'online' ? 
            '<span class="service-dot"></span>' : 
            '<span class="service-dot offline"></span>';
        
        appsHtml += `
            <tr data-app-id="${app.id}" class="app-row" data-app-name="${app.name.toLowerCase()}">
                <td>${app.name}</td>
                <td>${app.version || 'Н/Д'}</td>
                <td>${statusDot} ${app.status}</td>
                <td>${app.type || 'Н/Д'}</td>
                <td>
                    <div class="row-actions">
                        <button class="app-action-btn" title="Информация" data-action="info">ℹ️</button>
                        <button class="app-action-btn" title="Запустить" data-action="start">▶️</button>
                        <button class="app-action-btn" title="Остановить" data-action="stop">⏹️</button>
                    </div>
                </td>
            </tr>
        `;
    });
    
    appsHtml += `
            </tbody>
        </table>
    `;
    
    appsContainer.innerHTML = appsHtml;
    
    // Добавляем обработчики событий для кнопок
    
    // Кнопка обновления информации о сервере
    document.getElementById('refresh-server-btn').addEventListener('click', function() {
        loadServerDetails(server.id);
    });
    
    // Кнопка редактирования сервера
    document.getElementById('edit-server-btn').addEventListener('click', function() {
        showEditServerModal(server.id);
    });
    
    // Кнопки действий с приложениями
    document.querySelectorAll('.app-action-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const action = this.getAttribute('data-action');
            const appId = this.closest('tr').getAttribute('data-app-id');
            
            handleAppAction(appId, action);
        });
    });
}

/**
 * Фильтрация приложений по поисковому запросу
 * @param {string} query - Поисковый запрос (имя приложения)
 */
function filterApplications(query) {
    const appRows = document.querySelectorAll('.app-row');
    
    appRows.forEach(row => {
        const appName = row.getAttribute('data-app-name');
        
        if (appName.includes(query)) {
            row.style.display = 'table-row';
        } else {
            row.style.display = 'none';
        }
    });
}

/**
 * Обработка действий с приложениями
 * @param {string} appId - ID приложения
 * @param {string} action - Действие (info, start, stop)
 */
function handleAppAction(appId, action) {
    switch (action) {
        case 'info':
            window.location.href = `/application/${appId}`;
            break;
        case 'start':
            // Реализация запуска приложения
            showConfirmActionModal([appId], 'start');
            break;
        case 'stop':
            // Реализация остановки приложения
            showConfirmActionModal([appId], 'stop');
            break;
        default:
            console.warn(`Неизвестное действие: ${action}`);
    }
}

/**
 * Отображение модального окна редактирования сервера
 * @param {string} serverId - ID сервера
 */
async function showEditServerModal(serverId) {
    try {
        const response = await fetch(`/api/servers/${serverId}`);
        const data = await response.json();
        
        if (!data.success) {
            console.error('Ошибка при получении информации о сервере:', data.error);
            showError('Не удалось получить информацию о сервере');
            return;
        }
        
        const server = data.server;
        
        // Определяем поля формы
        const formFields = [
            {
                id: 'server-name',
                name: 'name',
                label: 'Имя сервера:',
                type: 'text',
                value: server.name,
                required: true
            },
            {
                id: 'server-ip',
                name: 'ip',
                label: 'IP-адрес:',
                type: 'text',
                value: server.ip,
                pattern: '^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
                required: true
            },
            {
                id: 'server-port',
                name: 'port',
                label: 'Порт:',
                type: 'number',
                value: server.port,
                min: 1,
                max: 65535,
                required: true
            }
        ];
        
        // Функция, которая будет выполнена при отправке формы
        const submitAction = async function(formData) {
            try {
                const response = await fetch(`/api/servers/${serverId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: formData.name,
                        ip: formData.ip,
                        port: parseInt(formData.port)
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // Закрываем модальное окно и обновляем информацию о сервере
                    window.closeModal();
                    loadServerDetails(serverId);
                    showNotification('Сервер успешно обновлен');
                } else {
                    console.error('Ошибка при обновлении сервера:', data.error);
                    showError(data.error || 'Не удалось обновить сервер');
                }
            } catch (error) {
                console.error('Ошибка при обновлении сервера:', error);
                showError('Не удалось обновить сервер');
            }
        };
        
        // Отображаем модальное окно с формой
        ModalUtils.showFormModal('Редактирование сервера', formFields, submitAction, 'Сохранить');
    } catch (error) {
        console.error('Ошибка при получении информации о сервере:', error);
        showError('Не удалось получить информацию о сервере');
    }
}

/**
 * Отображение модального окна подтверждения действия
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
    const appItems = [];
    appIds.forEach(appId => {
        const row = document.querySelector(`tr[data-app-id="${appId}"]`);
        if (row) {
            const appName = row.cells[0].textContent;
            appItems.push(appName);
        }
    });
    
    // Функция, которая будет выполнена при подтверждении
    const confirmAction = async function() {
        try {
            // Здесь нужно реализовать действие с выбранными приложениями
            // Например, отправить запрос на сервер для запуска/остановки/перезапуска
            console.log(`Выполняем действие ${action} для приложений:`, appIds);
            
            // Пример запроса:
            const response = await fetch(`/api/applications/${appIds[0]}/manage`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    action: action
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showNotification(`Действие "${actionName}" успешно выполнено`);
                // После успешного действия можно обновить информацию о сервере
                loadServerDetails(currentServerId);
            } else {
                showError(data.error || `Не удалось выполнить действие "${actionName}"`);
            }
        } catch (error) {
            console.error(`Ошибка при выполнении действия ${action}:`, error);
            showError(`Не удалось выполнить действие "${actionName}"`);
        }
    };
    
    // Отображаем модальное окно подтверждения
    ModalUtils.showConfirmModal(
        `${actionName.charAt(0).toUpperCase() + actionName.slice(1)} приложения`, // Заголовок
        `Вы уверены, что хотите <span class="action-name">${actionName}</span> выбранные приложения?`, // Сообщение
        appItems, // Список элементов
        confirmAction, // Функция подтверждения
        `Подтвердить`, // Текст кнопки
        'confirm-btn' // Класс кнопки
    );
}

/**
 * Отправка запроса на выполнение действия с приложением
 * @param {string} appId - ID приложения
 * @param {string} action - Действие (start, stop, restart)
 */
async function sendAppAction(appId, action) {
    try {
        const response = await fetch(`/api/applications/${appId}/manage`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: action
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(`Действие "${action}" для приложения поставлено в очередь`);
            
            // Обновляем информацию о сервере через некоторое время
            setTimeout(() => {
                const pathParts = window.location.pathname.split('/');
                const serverId = pathParts[pathParts.length - 1];
                loadServerDetails(serverId);
            }, 2000);
        } else {
            console.error(`Ошибка при выполнении действия ${action}:`, data.error);
            showError(data.error || `Не удалось выполнить действие "${action}"`);
        }
    } catch (error) {
        console.error(`Ошибка при выполнении действия ${action}:`, error);
        showError(`Не удалось выполнить действие "${action}"`);
    }
}
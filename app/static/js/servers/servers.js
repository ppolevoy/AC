/**
 * Faktura Apps - Модуль для страницы управления серверами
 */

document.addEventListener('DOMContentLoaded', function() {
    const serversContainer = document.getElementById('servers-container');
    const emptyState = document.getElementById('empty-state');
    
    // Добавляем обработчики событий для кнопок добавления сервера
    const addServerBtn = document.getElementById('add-server-btn');
    const addServerEmptyBtn = document.getElementById('add-server-empty-btn');
    
    if (addServerBtn) {
        addServerBtn.addEventListener('click', showAddServerModal);
    }
    
    if (addServerEmptyBtn) {
        addServerEmptyBtn.addEventListener('click', showAddServerModal);
    }
    
    // Загружаем список серверов при загрузке страницы
    loadServers();
    
    // Обновляем список серверов каждые 60 секунд
    setInterval(loadServers, 60000);
});

/**
 * Загрузка списка серверов
 */
async function loadServers() {
    try {
        const serversContainer = document.getElementById('servers-container');
        const emptyState = document.getElementById('empty-state');
        
        const response = await fetch('/api/servers');
        const data = await response.json();
        
        if (data.success) {
            renderServers(data.servers);
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
 * Отображение списка серверов
 * @param {Array} servers - Массив объектов серверов
 */
function renderServers(servers) {
    const serversContainer = document.getElementById('servers-container');
    const emptyState = document.getElementById('empty-state');
    
    serversContainer.innerHTML = '';
    
    if (servers.length === 0) {
        // Если серверов нет, показываем пустое состояние
        serversContainer.style.display = 'none';
        emptyState.style.display = 'flex';
        return;
    }
    
    // Если серверы есть, скрываем пустое состояние
    serversContainer.style.display = 'grid';
    emptyState.style.display = 'none';
    
    // Создаем карточки для каждого сервера
    servers.forEach(server => {
        const statusClass = server.status === 'online' ? 'online' : 'offline';
        const statusText = server.status === 'online' ? 'Online' : 'Offline';
        
        const serverCard = document.createElement('div');
        serverCard.className = 'server-card';
        serverCard.innerHTML = `
            <div class="server-header">
                <div class="server-name">${server.name}</div>
                <div class="server-status">
                    <div class="status-dot ${statusClass}"></div>
                    <span class="status-text ${statusClass}">${statusText}</span>
                </div>
            </div>
            <div class="server-info">
                <div class="info-row">
                    <span class="info-label">IP:</span>
                    <span>${server.ip}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Порт:</span>
                    <span>${server.port}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Приложений:</span>
                    <span>${server.app_count || 0}</span>
                </div>
            </div>
            <div class="server-actions">
                <button class="server-btn refresh-btn" title="Проверить" data-server-id="${server.id}">⟳</button>
                <button class="server-btn edit" title="Изменить" data-server-id="${server.id}">✎</button>
                <button class="server-btn delete" title="Удалить" data-server-id="${server.id}">✕</button>
            </div>
        `;
        
        // Добавляем обработчик клика для перехода на страницу сервера
        serverCard.addEventListener('click', function(e) {
            // Игнорируем клик, если он был по кнопкам действий
            if (!e.target.closest('.server-btn')) {
                // Правильный URL для страницы с деталями сервера
                window.location.href = `/server/${server.id}`;
            }
        });
        
        serversContainer.appendChild(serverCard);
    });
    
    // Добавляем обработчики событий для кнопок действий
    setupActionButtons();
}

/**
 * Добавление обработчиков событий для кнопок действий
 */
function setupActionButtons() {
    // Кнопки обновления
    document.querySelectorAll('.refresh-btn').forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.stopPropagation();
            const serverId = this.getAttribute('data-server-id');
            await refreshServer(serverId);
        });
    });
    
    // Кнопки редактирования
    document.querySelectorAll('.server-btn.edit').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const serverId = this.getAttribute('data-server-id');
            showEditServerModal(serverId);
        });
    });
    
    // Кнопки удаления
    document.querySelectorAll('.server-btn.delete').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const serverId = this.getAttribute('data-server-id');
            showDeleteServerModal(serverId);
        });
    });
}

/**
 * Обновление информации о сервере
 * @param {string} serverId - ID сервера
 */
async function refreshServer(serverId) {
    try {
        const btn = document.querySelector(`.refresh-btn[data-server-id="${serverId}"]`);
        if (btn) {
            // Добавляем класс для анимации вращения кнопки
            btn.classList.add('rotating');
        }
        
        const response = await fetch(`/api/servers/${serverId}/refresh`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            // Обновляем список серверов после успешного обновления
            loadServers();
            showNotification('Сервер успешно обновлен');
        } else {
            console.error('Ошибка при обновлении сервера:', data.error);
            showError('Не удалось обновить сервер');
        }
    } catch (error) {
        console.error('Ошибка при обновлении сервера:', error);
        showError('Не удалось обновить сервер');
    } finally {
        // Убираем анимацию вращения
        const btn = document.querySelector(`.refresh-btn[data-server-id="${serverId}"]`);
        if (btn) {
            btn.classList.remove('rotating');
        }
    }
}

/**
 * Отображение модального окна добавления сервера
 */
function showAddServerModal() {
    // Определяем поля формы
    const formFields = [
        {
            id: 'server-name',
            name: 'name',
            label: 'Имя сервера:',
            type: 'text',
            required: true
        },
        {
            id: 'server-ip',
            name: 'ip',
            label: 'IP-адрес:',
            type: 'text',
            pattern: '^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
            required: true
        },
        {
            id: 'server-port',
            name: 'port',
            label: 'Порт:',
            type: 'number',
            min: 1,
            max: 65535,
            required: true
        }
    ];
    
    // Функция, которая будет выполнена при отправке формы
    const submitAction = async function(formData) {
        try {
            const response = await fetch('/api/servers', {
                method: 'POST',
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
                // Обновляем список серверов
                loadServers();
                showNotification('Сервер успешно добавлен');
            } else {
                console.error('Ошибка при добавлении сервера:', data.error);
                showError(data.error || 'Не удалось добавить сервер');
            }
        } catch (error) {
            console.error('Ошибка при добавлении сервера:', error);
            showError('Не удалось добавить сервер');
        }
    };
    
    // Отображаем модальное окно с формой
    ModalUtils.showFormModal('Добавление сервера', formFields, submitAction, 'Добавить');
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
                    // Закрываем модальное окно и обновляем список серверов
                    window.closeModal();
                    loadServers();
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
 * Отображение модального окна удаления сервера
 * @param {string} serverId - ID сервера
 */
function showDeleteServerModal(serverId) {
    // Функция, которая будет выполнена при подтверждении
    const confirmAction = async function() {
        try {
            const response = await fetch(`/api/servers/${serverId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Закрываем модальное окно и обновляем список серверов
                window.closeModal();
                loadServers();
                showNotification('Сервер успешно удален');
            } else {
                console.error('Ошибка при удалении сервера:', data.error);
                showError(data.error || 'Не удалось удалить сервер');
            }
        } catch (error) {
            console.error('Ошибка при удалении сервера:', error);
            showError('Не удалось удалить сервер');
        }
    };
    
    // Отображаем модальное окно подтверждения
    ModalUtils.showConfirmModal(
        'Удаление сервера', // Заголовок
        '<p>Вы уверены, что хотите удалить этот сервер?</p><p>Вместе с сервером будут удалены все связанные с ним приложения и события.</p>', // Сообщение
        [], // Список элементов (пустой)
        confirmAction, // Функция подтверждения
        'Удалить', // Текст кнопки
        'delete-btn' // Класс кнопки
    );
}

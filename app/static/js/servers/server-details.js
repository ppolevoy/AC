/**
 * Faktura Apps - Модуль для страницы деталей сервера (Modern Design)
 */

let currentServerId = null;
let currentServerData = null;

// ==================== Theme Toggle ====================

/**
 * Инициализация темы при загрузке страницы
 */
function initTheme() {
    // Проверяем сохраненную тему в localStorage
    const savedTheme = localStorage.getItem('theme');

    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        updateThemeIcon(true);
    } else {
        document.body.classList.remove('light-theme');
        updateThemeIcon(false);
    }
}

/**
 * Переключение темы
 */
function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');

    // Сохраняем тему в localStorage
    localStorage.setItem('theme', isLight ? 'light' : 'dark');

    // Обновляем иконку
    updateThemeIcon(isLight);
}

/**
 * Обновление иконки темы
 */
function updateThemeIcon(isLight) {
    const themeIcon = document.getElementById('theme-icon');
    if (!themeIcon) return;

    if (isLight) {
        // Иконка луны для светлой темы
        themeIcon.innerHTML = `
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        `;
    } else {
        // Иконка солнца для темной темы
        themeIcon.innerHTML = `
            <circle cx="12" cy="12" r="5"></circle>
            <line x1="12" y1="1" x2="12" y2="3"></line>
            <line x1="12" y1="21" x2="12" y2="23"></line>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
            <line x1="1" y1="12" x2="3" y2="12"></line>
            <line x1="21" y1="12" x2="23" y2="12"></line>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        `;
    }
}

// ==================== Инициализация ====================

document.addEventListener('DOMContentLoaded', function() {
    // Инициализация темы
    initTheme();

    // Функция для инициализации кнопки темы с повтором
    function initThemeButton(attempts = 0) {
        const themeToggleBtn = document.getElementById('theme-toggle-btn');

        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', toggleTheme);
        } else if (attempts < 5) {
            // Пробуем еще раз через 100ms (максимум 5 попыток)
            setTimeout(() => initThemeButton(attempts + 1), 100);
        }
    }

    // Запускаем инициализацию кнопки темы
    initThemeButton();

    // Получаем ID сервера из URL
    const pathParts = window.location.pathname.split('/');
    currentServerId = pathParts[pathParts.length - 1];

    if (!currentServerId || isNaN(parseInt(currentServerId))) {
        showError('Некорректный ID сервера');
        return;
    }

    // Загружаем информацию о сервере
    loadServerDetails(currentServerId);

    // Обработчик для кнопки настройки HAProxy
    const haproxyBtn = document.getElementById('haproxy-settings-btn');
    if (haproxyBtn) {
        haproxyBtn.addEventListener('click', openHAProxySidebar);
    }
});

/**
 * Загрузка информации о сервере
 */
async function loadServerDetails(serverId) {
    try {
        const response = await fetch(`/api/servers/${serverId}`);
        const data = await response.json();

        if (data.success) {
            currentServerData = data.server;
            renderServerInfo(data.server);
            renderApplications(data.server.applications || []);
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
 * Отображение информации о сервере в header
 */
function renderServerInfo(server) {
    // Обновляем заголовок с кнопкой обновления
    const serverNameDisplay = document.getElementById('server-name-display');
    serverNameDisplay.innerHTML = `
        ${server.name}
        <button id="refresh-server-btn" style="margin-left: 12px; padding: 6px; width: 32px; height: 32px; border-radius: 4px; cursor: pointer; font-size: 16px; line-height: 1; background: #1f1f1f; border: 1px solid #374151; display: inline-flex; align-items: center; justify-content: center; vertical-align: middle;"
                title="Обновить список приложений">
            🔄
        </button>
    `;

    // Формируем карточки информации
    const infoGrid = document.getElementById('server-info-grid');

    const lastCheck = server.last_check ?
        new Date(server.last_check).toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }) : 'Нет данных';

    const appsCount = server.applications ? server.applications.length : 0;
    const appsOnline = server.applications ?
        server.applications.filter(app => app.status === 'online').length : 0;

    infoGrid.innerHTML = `
        <div class="info-card">
            <svg class="info-icon icon-blue" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
                <path d="M1.42 9a16 16 0 0 1 21.16 0"></path>
            </svg>
            <div class="info-text">
                <span class="info-label">IP-адрес</span>
                <span class="info-value">${server.ip}</span>
            </div>
        </div>
        <div class="info-card">
            <svg class="info-icon icon-green" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="4" y1="9" x2="20" y2="9"></line>
                <line x1="4" y1="15" x2="20" y2="15"></line>
            </svg>
            <div class="info-text">
                <span class="info-label">Порт</span>
                <span class="info-value">${server.port}</span>
            </div>
        </div>
        <div class="info-card">
            <svg class="info-icon icon-yellow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <div class="info-text">
                <span class="info-label">Последняя проверка</span>
                <span class="info-value">${lastCheck}</span>
            </div>
        </div>
        <div class="info-card">
            <div style="width: 20px; height: 20px; background-color: #a855f7; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold;">
                ${appsCount}
            </div>
            <div class="info-text">
                <span class="info-label">Приложений</span>
                <span class="info-value">${appsOnline} активных</span>
            </div>
        </div>
        <div class="info-card haproxy-checkbox-card">
            <label class="haproxy-checkbox-wrapper" style="display: flex; align-items: center; gap: 10px; cursor: pointer; width: 100%;">
                <input type="checkbox" id="is-haproxy-node-checkbox" ${server.is_haproxy_node ? 'checked' : ''}
                       style="width: 18px; height: 18px; cursor: pointer; accent-color: #2563eb;">
                <div class="info-text">
                    <span class="info-label">HAProxy узел</span>
                    <span class="info-value">${server.is_haproxy_node ? 'Активен' : 'Неактивен'}</span>
                </div>
            </label>
        </div>
    `;

    // Добавляем обработчик на checkbox HAProxy узел
    const haproxyCheckbox = document.getElementById('is-haproxy-node-checkbox');
    if (haproxyCheckbox) {
        haproxyCheckbox.addEventListener('change', function(e) {
            e.stopPropagation();
            toggleHAProxyNode(server.id, this.checked);
        });
    }

    // Добавляем обработчик на кнопку обновления
    const refreshBtn = document.getElementById('refresh-server-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            refreshServerApplications(server.id);
        });

        // Добавляем hover эффект
        refreshBtn.addEventListener('mouseover', function() {
            this.style.backgroundColor = '#2a2a2c';
        });
        refreshBtn.addEventListener('mouseout', function() {
            this.style.backgroundColor = '#1f1f1f';
        });
    }
}

/**
 * Обновление списка приложений на сервере
 */
async function refreshServerApplications(serverId) {
    try {
        showNotification('Запрос списка приложений у FAgent...');

        const response = await fetch(`/api/servers/${serverId}/refresh`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showNotification('✓ Список приложений обновлен');
            // Перезагружаем данные сервера
            loadServerDetails(serverId);
        } else {
            showError(data.error || 'Не удалось обновить список приложений');
        }
    } catch (error) {
        console.error('Ошибка при обновлении приложений:', error);
        showError('Не удалось обновить список приложений');
    }
}

/**
 * Переключение статуса HAProxy узла
 */
async function toggleHAProxyNode(serverId, isEnabled) {
    try {
        const response = await fetch(`/api/servers/${serverId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ is_haproxy_node: isEnabled })
        });

        const data = await response.json();

        if (data.success) {
            if (isEnabled) {
                showNotification('✓ HAProxy узел активирован. Нажмите "Обнаружить instances" для поиска instances.');
            } else {
                showNotification('Статус HAProxy узла снят');
            }

            currentServerData.is_haproxy_node = isEnabled;

            // Обновляем текст в info card
            const infoValue = document.querySelector('.haproxy-checkbox-card .info-value');
            if (infoValue) {
                infoValue.textContent = isEnabled ? 'Активен' : 'Неактивен';
            }

            // Перезагружаем информацию о сервере, чтобы показать/скрыть кнопку
            loadServerDetails(serverId);
        } else {
            showError(data.error || 'Не удалось обновить настройки');

            // Возвращаем checkbox в предыдущее состояние
            document.getElementById('is-haproxy-node-checkbox').checked = !isEnabled;

            // Обновляем текст обратно
            const infoValue = document.querySelector('.haproxy-checkbox-card .info-value');
            if (infoValue) {
                infoValue.textContent = !isEnabled ? 'Активен' : 'Неактивен';
            }
        }
    } catch (error) {
        console.error('Ошибка при сохранении настроек:', error);
        showError('Ошибка соединения с сервером');

        // Возвращаем checkbox в предыдущее состояние
        document.getElementById('is-haproxy-node-checkbox').checked = !isEnabled;

        // Обновляем текст обратно
        const infoValue = document.querySelector('.haproxy-checkbox-card .info-value');
        if (infoValue) {
            infoValue.textContent = !isEnabled ? 'Активен' : 'Неактивен';
        }
    }
}

/**
 * Отображение приложений с группировкой по имени
 */
function renderApplications(applications) {
    const container = document.getElementById('apps-container');

    if (!applications || applications.length === 0) {
        container.innerHTML = '<div class="no-data"><p>На сервере нет приложений</p></div>';
        return;
    }

    // Группируем приложения по original_name (извлекаем базовое имя без номера)
    const groupedApps = {};

    applications.forEach(app => {
        // Извлекаем базовое имя (до последнего _ или полное имя)
        const baseName = extractBaseName(app.name);

        if (!groupedApps[baseName]) {
            groupedApps[baseName] = {
                baseName: baseName,
                type: app.type,
                version: app.version,
                instances: []
            };
        }

        groupedApps[baseName].instances.push(app);
    });

    // Обновляем subtitle
    document.getElementById('apps-subtitle').textContent =
        `Группировка по имени (${Object.keys(groupedApps).length} групп)`;

    // Сортируем группы по имени
    const sortedGroups = Object.values(groupedApps).sort((a, b) =>
        a.baseName.localeCompare(b.baseName)
    );

    // Генерируем HTML
    let html = '';
    sortedGroups.forEach((group, index) => {
        const groupId = `group-${index}`;
        const instancesCount = group.instances.length;

        // Определяем общий статус группы (если хотя бы один online - то online)
        const hasOnline = group.instances.some(inst => inst.status === 'online');
        const allOffline = group.instances.every(inst => inst.status === 'offline' || !inst.status);

        let statusClass = 'unknown';
        let statusText = 'unknown';

        if (hasOnline) {
            statusClass = '';
            statusText = 'online';
        } else if (allOffline) {
            statusClass = 'offline';
            statusText = 'offline';
        }

        html += `
            <div class="app-card">
                <button class="app-button" onclick="toggleAppGroup('${groupId}')">
                    <div class="app-left">
                        <div class="chevron-box">
                            <svg id="icon-${groupId}" class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="9 18 15 12 9 6"></polyline>
                            </svg>
                        </div>
                        <div class="app-info">
                            <div class="app-name">${group.baseName}</div>
                            <div class="app-meta">${group.type || 'N/A'} • Версия ${group.version || 'Н/Д'}</div>
                        </div>
                    </div>
                    <div class="app-right">
                        <div class="instances-count">${instancesCount} ${instancesCount === 1 ? 'экземпляр' : 'экземпляров'}</div>
                        <div class="status-badge ${statusClass}">
                            <span class="status-dot"></span>
                            <span class="status-text">${statusText}</span>
                        </div>
                    </div>
                </button>
                <div id="details-${groupId}" class="app-details">
                    <div class="details-list">
        `;

        // Сортируем instances по имени
        group.instances.sort((a, b) => a.name.localeCompare(b.name));

        group.instances.forEach(instance => {
            const instStatus = instance.status || 'unknown';
            let dotClass = '';
            if (instStatus === 'offline') dotClass = 'offline';
            else if (instStatus !== 'online') dotClass = 'unknown';

            html += `
                <div class="detail-item" onclick="goToApp(${instance.id})">
                    <span class="detail-name">${instance.name}</span>
                    <div class="detail-status">
                        <span class="mini-dot ${dotClass}"></span>
                        <span class="detail-status-text">${instStatus}</span>
                    </div>
                </div>
            `;
        });

        html += `
                    </div>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

/**
 * Извлечение базового имени приложения
 */
function extractBaseName(fullName) {
    // Пытаемся найти паттерн: name_number
    const match = fullName.match(/^(.+?)_(\d+)$/);
    if (match) {
        return match[1]; // Возвращаем имя без номера
    }
    return fullName; // Если не подходит паттерн, возвращаем полное имя
}

/**
 * Переключение раскрытия группы приложений
 */
function toggleAppGroup(groupId) {
    const details = document.getElementById(`details-${groupId}`);
    const icon = document.getElementById(`icon-${groupId}`);

    if (details.classList.contains('show')) {
        details.classList.remove('show');
        icon.innerHTML = '<polyline points="9 18 15 12 9 6"></polyline>';
    } else {
        details.classList.add('show');
        icon.innerHTML = '<polyline points="6 9 12 15 18 9"></polyline>';
    }
}

/**
 * Переход на страницу приложения
 */
function goToApp(appId) {
    window.location.href = `/application/${appId}`;
}

/**
 * Открытие модального окна управления HAProxy
 */
async function openHAProxySidebar() {
    // Проверяем, включен ли HAProxy на этом сервере
    if (!currentServerData.is_haproxy_node) {
        showError('Сначала включите чекбокс "HAProxy узел" в информации о сервере');
        return;
    }

    // Загружаем список instances
    try {
        const response = await fetch(`/api/haproxy/instances`);
        const data = await response.json();

        if (data.success) {
            const serverInstances = data.instances.filter(inst =>
                inst.server_id === parseInt(currentServerId)
            );
            showHAProxyManagementModal(serverInstances);
        } else {
            console.error('Ошибка при загрузке HAProxy instances:', data.error);
            showError('Не удалось загрузить HAProxy instances');
        }
    } catch (error) {
        console.error('Ошибка при загрузке HAProxy instances:', error);
        showError('Не удалось загрузить HAProxy instances');
    }
}

/**
 * Показать модальное окно управления HAProxy instances
 */
function showHAProxyManagementModal(instances) {
    let modalHtml = `
        <div style="max-height: 600px; overflow-y: auto; position: relative;">
            <div style="position: relative; margin-bottom: 20px;">
                <p style="color: #888; font-size: 14px; margin: 0;">Всего instances: ${instances.length}</p>
                <button class="btn btn-secondary" style="position: absolute; top: 0; right: 0; padding: 6px; width: 32px; height: 32px; border-radius: 4px; cursor: pointer; font-size: 16px; line-height: 1; background: #1f1f1f; border: 1px solid #374151; display: flex; align-items: center; justify-content: center;"
                        onclick="syncAllHAProxyInstances()"
                        onmouseover="this.style.backgroundColor=document.body.classList.contains('light-theme')?'#e0e0e0':'#2a2a2c'"
                        onmouseout="this.style.backgroundColor=document.body.classList.contains('light-theme')?'#f0f0f0':'#1f1f1f'"
                        title="Синхронизация всех instances">
                    🔄
                </button>
            </div>
    `;

    if (instances.length === 0) {
        modalHtml += `
            <div class="no-data">
                <p>На этом сервере нет HAProxy instances</p>
                <p style="font-size: 14px; color: #888;">Instances будут обнаружены автоматически при опросе FAgent</p>
            </div>
        `;
    } else {
        modalHtml += `
            <div style="display: flex; flex-direction: column;">
        `;

        instances.forEach((instance, index) => {
            const lastSync = instance.last_sync_at ?
                new Date(instance.last_sync_at).toLocaleString('ru-RU', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                }) :
                'Нет данных';
            const statusBadge = instance.is_active ?
                '<span class="status-badge active" style="padding: 4px 10px; border-radius: 4px; font-size: 11px; background: rgba(76, 175, 80, 0.2); color: #4CAF50; font-weight: 500; text-transform: uppercase;">Активен</span>' :
                '<span class="status-badge inactive" style="padding: 4px 10px; border-radius: 4px; font-size: 11px; background: rgba(158, 158, 158, 0.2); color: #9e9e9e; font-weight: 500; text-transform: uppercase;">Неактивен</span>';

            modalHtml += `
                <div style="border: 1px solid #374151; border-radius: 6px; overflow: hidden; background: #252525; margin-bottom: 8px;">
                    <!-- Заголовок аккордеона -->
                    <div class="haproxy-accordion-header" onclick="toggleHAProxyInstanceAccordion(${index})"
                         style="padding: 12px 14px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; transition: background-color 0.2s;"
                         onmouseover="this.style.backgroundColor=document.body.classList.contains('light-theme')?'#f5f5f5':'#2a2a2c'"
                         onmouseout="this.style.backgroundColor=''">
                        <div style="display: flex; align-items: center; gap: 10px; flex: 1;">
                            <svg id="haproxy-chevron-${index}" style="width: 12px; height: 12px; transition: transform 0.3s; flex-shrink: 0; color: #888;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="9 18 15 12 9 6"></polyline>
                            </svg>
                            <div style="display: flex; flex-direction: column; gap: 4px; flex: 1;">
                                <div style="display: flex; align-items: center; gap: 10px;">
                                    <span style="font-size: 15px; font-weight: 500; color: #fff;">${instance.name}</span>
                                    ${statusBadge}
                                </div>
                                <div style="font-size: 12px; color: #888;">Backends: <span style="color: #fff; font-weight: 500;">${instance.backends_count || 0}</span></div>
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 11px; color: #888; margin-bottom: 2px;">Последняя синхронизация</div>
                            <div id="sync-time-${index}" style="font-size: 12px; color: #fff;">${lastSync}</div>
                        </div>
                    </div>

                    <!-- Раскрывающееся содержимое с backends -->
                    <div id="haproxy-instance-details-${index}" style="display: none; border-top: 1px solid #374151; background: #1f1f1f;">
                        <div id="haproxy-backends-${instance.id}">
                            <div style="text-align: center; color: #888; padding: 20px;">
                                Загрузка backends...
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        modalHtml += `
            </div>
        `;
    }

    modalHtml += `
        </div>
        <div style="margin-top: 20px; display: flex; gap: 12px; border-top: 1px solid #374151; padding-top: 20px;">
            <button class="btn btn-secondary" style="flex: 1;" onclick="closeModal();">Закрыть</button>
        </div>
    `;

    showModal('HAProxy Instances', modalHtml);

    // Сохраняем instances для использования в toggleHAProxyInstanceAccordion
    window.currentHAProxyInstances = instances;
}

/**
 * Переключение аккордеона HAProxy instance
 */
function toggleHAProxyInstanceAccordion(index) {
    const detailsDiv = document.getElementById(`haproxy-instance-details-${index}`);
    const chevron = document.getElementById(`haproxy-chevron-${index}`);

    if (detailsDiv.style.display === 'none') {
        // Раскрываем аккордеон
        detailsDiv.style.display = 'block';
        chevron.style.transform = 'rotate(90deg)';

        // Загружаем backends, если еще не загружены
        const instance = window.currentHAProxyInstances[index];
        if (instance) {
            loadHAProxyBackends(instance.id, index);
        }
    } else {
        // Скрываем аккордеон
        detailsDiv.style.display = 'none';
        chevron.style.transform = 'rotate(0deg)';
    }
}

/**
 * Синхронизация всех HAProxy instances
 */
async function syncAllHAProxyInstances() {
    try {
        if (!window.currentHAProxyInstances || window.currentHAProxyInstances.length === 0) {
            showNotification('Нет instances для синхронизации');
            return;
        }

        showNotification(`Запуск синхронизации ${window.currentHAProxyInstances.length} instance(s)...`);

        let successCount = 0;
        let failCount = 0;

        // Синхронизируем каждый instance последовательно
        for (let i = 0; i < window.currentHAProxyInstances.length; i++) {
            const instance = window.currentHAProxyInstances[i];

            try {
                const response = await fetch(`/api/haproxy/instances/${instance.id}/sync`, {
                    method: 'POST'
                });

                const data = await response.json();

                if (data.success) {
                    successCount++;

                    // Обновляем количество backends
                    if (data.instance && data.instance.backends_count !== undefined) {
                        const headerDiv = document.querySelector(`#haproxy-instance-details-${i}`).previousElementSibling;
                        if (headerDiv) {
                            const backendsSpan = headerDiv.querySelector('[style*="Backends"]');
                            if (backendsSpan) {
                                const countSpan = backendsSpan.querySelector('span');
                                if (countSpan) {
                                    countSpan.textContent = data.instance.backends_count;
                                }
                            }
                        }
                    }

                    // Обновляем время последней синхронизации
                    if (data.instance && data.instance.last_sync) {
                        const syncTimeElement = document.getElementById(`sync-time-${i}`);
                        if (syncTimeElement) {
                            const lastSyncText = new Date(data.instance.last_sync).toLocaleString('ru-RU', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                                second: '2-digit'
                            });
                            syncTimeElement.textContent = lastSyncText;
                        }
                    }

                    // Если аккордеон открыт, перезагружаем backends
                    const detailsDiv = document.getElementById(`haproxy-instance-details-${i}`);
                    if (detailsDiv && detailsDiv.style.display !== 'none') {
                        await loadHAProxyBackends(instance.id, i);
                    }
                } else {
                    failCount++;
                    console.error(`Ошибка синхронизации instance ${instance.name}:`, data.error);
                }
            } catch (error) {
                failCount++;
                console.error(`Ошибка синхронизации instance ${instance.name}:`, error);
            }
        }

        if (failCount === 0) {
            showNotification(`✓ Все instances синхронизированы успешно (${successCount})`);
        } else {
            showNotification(`⚠ Синхронизация завершена: успешно ${successCount}, ошибок ${failCount}`);
        }
    } catch (error) {
        console.error('Ошибка при синхронизации instances:', error);
        showError('Не удалось выполнить синхронизацию');
    }
}

/**
 * Синхронизация HAProxy instance и перезагрузка backends
 */
async function syncHAProxyInstanceAndReload(instanceId, index) {
    try {
        showNotification('Запуск синхронизации...');

        const response = await fetch(`/api/haproxy/instances/${instanceId}/sync`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showNotification('✓ Синхронизация завершена успешно');

            // Обновляем количество backends
            if (data.instance && data.instance.backends_count !== undefined) {
                const headerDiv = document.querySelector(`#haproxy-instance-details-${index}`).previousElementSibling;
                if (headerDiv) {
                    const backendsSpan = headerDiv.querySelector('[style*="Backends"]');
                    if (backendsSpan) {
                        const countSpan = backendsSpan.querySelector('span');
                        if (countSpan) {
                            countSpan.textContent = data.instance.backends_count;
                        }
                    }
                }
            }

            // Обновляем время последней синхронизации
            if (data.instance && data.instance.last_sync) {
                const syncTimeElement = document.getElementById(`sync-time-${index}`);
                if (syncTimeElement) {
                    const lastSyncText = new Date(data.instance.last_sync).toLocaleString('ru-RU', {
                        day: '2-digit',
                        month: '2-digit',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    });
                    syncTimeElement.textContent = lastSyncText;
                }
            }

            // Если аккордеон открыт, перезагружаем backends
            const detailsDiv = document.getElementById(`haproxy-instance-details-${index}`);
            if (detailsDiv && detailsDiv.style.display !== 'none') {
                loadHAProxyBackends(instanceId, index);
            }
        } else {
            console.error('Ошибка при синхронизации:', data.error);
            showError(data.error || 'Не удалось выполнить синхронизацию');
        }
    } catch (error) {
        console.error('Ошибка при синхронизации:', error);
        showError('Не удалось выполнить синхронизацию');
    }
}

/**
 * Загрузка списка backends для HAProxy instance
 */
async function loadHAProxyBackends(instanceId, instanceIndex) {
    const container = document.getElementById(`haproxy-backends-${instanceId}`);

    if (!container) {
        console.error('Container not found for instance:', instanceId);
        return;
    }

    try {
        container.innerHTML = '<div style="text-align: center; color: #888; padding: 20px;">Загрузка backends...</div>';

        const response = await fetch(`/api/haproxy/instances/${instanceId}/backends`);
        const data = await response.json();

        if (data.success && data.backends) {
            let backendsHtml = '';

            if (data.backends.length === 0) {
                backendsHtml += `
                    <div style="text-align: center; color: #888; padding: 20px;">
                        <p>Backends не найдены</p>
                        <p style="font-size: 12px; margin-top: 8px;">Запустите синхронизацию для загрузки данных из HAProxy</p>
                    </div>
                `;
            } else {
                backendsHtml += '<div style="display: flex; flex-direction: column; gap: 6px; padding: 12px 16px;">';

                data.backends.forEach(backend => {
                    const serversCount = backend.servers_count || 0;
                    const stats = backend.status_stats || {};
                    const upCount = stats.UP || 0;
                    const downCount = stats.DOWN || 0;
                    const drainCount = stats.DRAIN || 0;
                    const maintCount = stats.MAINT || 0;

                    backendsHtml += `
                        <div style="padding: 10px 12px; background: #252525; border: 1px solid #374151; border-radius: 4px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="font-size: 14px; font-weight: 500; color: #fff;">${backend.backend_name}</div>
                                <div style="display: flex; gap: 12px; font-size: 12px; align-items: center;">
                                    <div style="display: flex; align-items: center; gap: 4px;">
                                        <span style="width: 8px; height: 8px; border-radius: 50%; background: #4CAF50;"></span>
                                        <span style="color: #4CAF50;">${upCount}</span>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 4px;">
                                        <span style="width: 8px; height: 8px; border-radius: 50%; background: #f44336;"></span>
                                        <span style="color: #f44336;">${downCount}</span>
                                    </div>
                                    ${drainCount > 0 ? `
                                    <div style="display: flex; align-items: center; gap: 4px;">
                                        <span style="width: 8px; height: 8px; border-radius: 50%; background: #ff9800;"></span>
                                        <span style="color: #ff9800;">${drainCount}</span>
                                    </div>
                                    ` : ''}
                                    ${maintCount > 0 ? `
                                    <div style="display: flex; align-items: center; gap: 4px;">
                                        <span style="width: 8px; height: 8px; border-radius: 50%; background: #9e9e9e;"></span>
                                        <span style="color: #9e9e9e;">${maintCount}</span>
                                    </div>
                                    ` : ''}
                                    <div style="color: #888; margin-left: 4px;">всего: ${serversCount}</div>
                                </div>
                            </div>
                        </div>
                    `;
                });

                backendsHtml += '</div>';
            }

            container.innerHTML = backendsHtml;
        } else {
            container.innerHTML = `
                <div style="text-align: center; color: #f44336; padding: 20px;">
                    Ошибка загрузки: ${data.error || 'Неизвестная ошибка'}
                </div>
            `;
        }
    } catch (error) {
        console.error('Ошибка при загрузке backends:', error);
        container.innerHTML = `
            <div style="text-align: center; color: #f44336; padding: 20px;">
                Ошибка соединения с сервером
            </div>
        `;
    }
}

// ==================== HAProxy Instance Management ====================

/**
 * Отображение модального окна создания HAProxy instance
 */
async function showCreateHAProxyInstanceModal(serverId) {
    const formFields = [
        {
            id: 'instance-name',
            name: 'name',
            label: 'Имя instance (например, "default", "prod"):',
            type: 'text',
            value: '',
            required: true
        },
        {
            id: 'socket-path',
            name: 'socket_path',
            label: 'Socket Path (опционально):',
            type: 'text',
            value: '',
            placeholder: '/var/run/haproxy/admin.sock',
            required: false
        },
        {
            id: 'is-active',
            name: 'is_active',
            label: 'Активен:',
            type: 'checkbox',
            value: true,
            required: false
        }
    ];

    const submitAction = async function(formData) {
        try {
            const response = await fetch('/api/haproxy/instances', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: formData.name,
                    server_id: parseInt(serverId),
                    socket_path: formData.socket_path || null,
                    is_active: formData.is_active === 'on' || formData.is_active === true
                })
            });

            const data = await response.json();

            if (data.success) {
                window.closeModal();
                showNotification('HAProxy instance успешно создан');
                loadServerDetails(serverId);
            } else {
                console.error('Ошибка при создании HAProxy instance:', data.error);
                showError(data.error || 'Не удалось создать HAProxy instance');
            }
        } catch (error) {
            console.error('Ошибка при создании HAProxy instance:', error);
            showError('Не удалось создать HAProxy instance');
        }
    };

    ModalUtils.showFormModal('Создание HAProxy Instance', formFields, submitAction, 'Создать');
}

/**
 * Отображение модального окна редактирования HAProxy instance
 */
async function showEditHAProxyInstanceModal(instanceId) {
    try {
        const response = await fetch(`/api/haproxy/instances/${instanceId}`);
        const data = await response.json();

        if (!data.success) {
            console.error('Ошибка при получении информации об instance:', data.error);
            showError('Не удалось получить информацию об instance');
            return;
        }

        const instance = data.instance;

        const formFields = [
            {
                id: 'instance-name',
                name: 'name',
                label: 'Имя instance:',
                type: 'text',
                value: instance.name,
                required: true
            },
            {
                id: 'socket-path',
                name: 'socket_path',
                label: 'Socket Path (опционально):',
                type: 'text',
                value: instance.socket_path || '',
                placeholder: '/var/run/haproxy/admin.sock',
                required: false
            },
            {
                id: 'is-active',
                name: 'is_active',
                label: 'Активен:',
                type: 'checkbox',
                value: instance.is_active,
                required: false
            }
        ];

        const submitAction = async function(formData) {
            try {
                const response = await fetch(`/api/haproxy/instances/${instanceId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: formData.name,
                        socket_path: formData.socket_path || null,
                        is_active: formData.is_active === 'on' || formData.is_active === true
                    })
                });

                const data = await response.json();

                if (data.success) {
                    window.closeModal();
                    showNotification('HAProxy instance успешно обновлен');
                    loadServerDetails(currentServerId);
                } else {
                    console.error('Ошибка при обновлении HAProxy instance:', data.error);
                    showError(data.error || 'Не удалось обновить HAProxy instance');
                }
            } catch (error) {
                console.error('Ошибка при обновлении HAProxy instance:', error);
                showError('Не удалось обновить HAProxy instance');
            }
        };

        ModalUtils.showFormModal('Редактирование HAProxy Instance', formFields, submitAction, 'Сохранить');
    } catch (error) {
        console.error('Ошибка при получении информации об instance:', error);
        showError('Не удалось получить информацию об instance');
    }
}

/**
 * Удаление HAProxy instance
 */
async function deleteHAProxyInstance(instanceId) {
    try {
        const response = await fetch(`/api/haproxy/instances/${instanceId}`);
        const data = await response.json();

        if (!data.success) {
            console.error('Ошибка при получении информации об instance:', data.error);
            showError('Не удалось получить информацию об instance');
            return;
        }

        const instance = data.instance;

        const confirmAction = async function() {
            try {
                const response = await fetch(`/api/haproxy/instances/${instanceId}`, {
                    method: 'DELETE'
                });

                const data = await response.json();

                if (data.success) {
                    showNotification('HAProxy instance успешно удален');
                    loadServerDetails(currentServerId);
                } else {
                    console.error('Ошибка при удалении HAProxy instance:', data.error);
                    showError(data.error || 'Не удалось удалить HAProxy instance');
                }
            } catch (error) {
                console.error('Ошибка при удалении HAProxy instance:', error);
                showError('Не удалось удалить HAProxy instance');
            }
        };

        ModalUtils.showConfirmModal(
            'Удаление HAProxy Instance',
            `Вы уверены, что хотите удалить HAProxy instance <strong>${instance.name}</strong>?<br>
             Это также удалит все связанные backends и серверы.`,
            [],
            confirmAction,
            'Удалить',
            'delete-btn'
        );
    } catch (error) {
        console.error('Ошибка при получении информации об instance:', error);
        showError('Не удалось получить информацию об instance');
    }
}

/**
 * Синхронизация HAProxy instance
 */
async function syncHAProxyInstance(instanceId) {
    try {
        showNotification('Запуск синхронизации...');

        const response = await fetch(`/api/haproxy/instances/${instanceId}/sync`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showNotification('Синхронизация завершена успешно');
        } else {
            console.error('Ошибка при синхронизации:', data.error);
            showError(data.error || 'Не удалось выполнить синхронизацию');
        }
    } catch (error) {
        console.error('Ошибка при синхронизации:', error);
        showError('Не удалось выполнить синхронизацию');
    }
}

/**
 * Отображение модального окна со списком backends
 */
async function showBackendsModal(instanceId, instanceName) {
    try {
        const response = await fetch(`/api/haproxy/instances/${instanceId}/backends`);
        const data = await response.json();

        if (!data.success) {
            console.error('Ошибка при загрузке backends:', data.error);
            showError(data.error || 'Не удалось загрузить backends');
            return;
        }

        const backends = data.backends || [];

        let backendsHtml = `
            <div class="backends-modal-content">
                <h4>Backends в instance "${instanceName}"</h4>
                <p style="color: #888; margin-bottom: 20px;">Всего backends: ${backends.length}</p>
        `;

        if (backends.length === 0) {
            backendsHtml += `
                <div class="no-data">
                    <p>Backends не найдены</p>
                    <p style="font-size: 14px; color: #888;">Запустите синхронизацию для обновления данных</p>
                </div>
            `;
        } else {
            backendsHtml += `
                <div class="backends-list">
                    <table class="backends-table" style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Имя Backend</th>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Серверов</th>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Действия</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            backends.forEach(backend => {
                const serversCount = backend.servers_count || 0;

                backendsHtml += `
                    <tr>
                        <td style="padding: 10px;"><strong>${backend.backend_name}</strong></td>
                        <td style="padding: 10px;">${serversCount} серв.</td>
                        <td style="padding: 10px;">
                            <button class="btn-primary" style="padding: 4px 10px; border-radius: 3px; cursor: pointer;" onclick="viewBackendServers(${backend.id}, '${backend.backend_name}')">
                                Серверы →
                            </button>
                        </td>
                    </tr>
                `;
            });

            backendsHtml += `
                        </tbody>
                    </table>
                </div>
            `;
        }

        backendsHtml += `
            </div>
            <div class="modal-actions" style="margin-top: 20px; display: flex; gap: 12px;">
                <button type="button" class="btn btn-secondary" onclick="closeModal()">Закрыть</button>
                <button type="button" class="btn btn-primary" onclick="syncHAProxyInstance(${instanceId}); closeModal();">
                    🔄 Синхронизировать
                </button>
            </div>
        `;

        showModal(`Backends - ${instanceName}`, backendsHtml);

    } catch (error) {
        console.error('Ошибка при загрузке backends:', error);
        showError('Не удалось загрузить список backends');
    }
}

/**
 * Просмотр серверов в backend
 */
async function viewBackendServers(backendId, backendName) {
    try {
        const response = await fetch(`/api/haproxy/backends/${backendId}/servers`);
        const data = await response.json();

        if (!data.success) {
            console.error('Ошибка при загрузке серверов:', data.error);
            showError(data.error || 'Не удалось загрузить серверы');
            return;
        }

        const servers = data.servers || [];

        let serversHtml = `
            <div class="servers-modal-content">
                <h4>Серверы в backend "${backendName}"</h4>
                <p style="color: #888; margin-bottom: 20px;">Всего серверов: ${servers.length}</p>
        `;

        if (servers.length === 0) {
            serversHtml += `
                <div class="no-data">
                    <p>Серверы не найдены</p>
                </div>
            `;
        } else {
            serversHtml += `
                <div class="servers-list">
                    <table class="servers-table" style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Имя сервера</th>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Адрес</th>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Статус</th>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Вес</th>
                                <th style="text-align: left; padding: 10px; background: #2a2a2d;">Подключения</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            servers.forEach(server => {
                let statusClass = 'unknown';
                if (server.status === 'UP') statusClass = 'active';
                else if (server.status === 'DOWN') statusClass = 'inactive';

                const appLink = server.application ?
                    `<br><small style="color: #888;">→ ${server.application.name || 'N/A'}</small>` :
                    '';

                serversHtml += `
                    <tr>
                        <td style="padding: 10px;"><strong>${server.server_name}</strong>${appLink}</td>
                        <td style="padding: 10px;">${server.addr || 'N/A'}</td>
                        <td style="padding: 10px;"><span class="status-badge ${statusClass}">${server.status || 'N/A'}</span></td>
                        <td style="padding: 10px;">${server.weight || 'N/A'}</td>
                        <td style="padding: 10px;">${server.scur || 0} / ${server.smax || 0}</td>
                    </tr>
                `;
            });

            serversHtml += `
                        </tbody>
                    </table>
                </div>
            `;
        }

        serversHtml += `
            </div>
            <div class="modal-actions" style="margin-top: 20px; display: flex; gap: 12px;">
                <button type="button" class="btn btn-secondary" onclick="showBackendsModal(${backendId}, '${backendName}')">← Назад</button>
                <button type="button" class="btn btn-primary" onclick="closeModal()">Закрыть</button>
            </div>
        `;

        showModal(`Серверы - ${backendName}`, serversHtml);

    } catch (error) {
        console.error('Ошибка при загрузке серверов:', error);
        showError('Не удалось загрузить список серверов');
    }
}


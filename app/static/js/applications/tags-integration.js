/**
 * Интеграция системы тегов в интерфейс приложений
 */

// Проверяем доступность функций уведомлений
(function() {
    // Если showError не определена, создаем безопасную обертку
    if (typeof showError === 'undefined') {
        window.showError = function(message, duration) {
            if (typeof showNotification === 'function') {
                showNotification('❌ ' + message, duration || 5000);
            } else {
                console.error(message);
                alert('Ошибка: ' + message);
            }
        };
    }
})();

// Глобальный кеш тегов для оптимизации
const tagsCache = new Map();

/**
 * Загрузить теги для приложения
 * @param {number} appId - ID приложения
 * @returns {Promise<Array>} Массив тегов
 */
async function loadApplicationTags(appId) {
    // Проверяем кеш
    if (tagsCache.has(appId)) {
        return tagsCache.get(appId);
    }
    
    try {
        const response = await fetch(`/api/applications/${appId}/tags`);
        const data = await response.json();
        
        if (data.success) {
            // Кешируем результат
            tagsCache.set(appId, data.tags);
            return data.tags;
        }
        
        return [];
    } catch (error) {
        console.error(`Error loading tags for app ${appId}:`, error);
        return [];
    }
}

/**
 * Загрузить теги для всех приложений пакетно
 * @param {Array} appIds - Массив ID приложений
 */
async function batchLoadApplicationTags(appIds) {
    const promises = appIds.map(id => loadApplicationTags(id));
    await Promise.all(promises);
}

/**
 * Создать HTML для badge-тегов
 * @param {Array} tags - Массив тегов
 * @param {boolean} compact - Компактный режим отображения
 * @returns {string} HTML строка с тегами
 */
function createTagsBadgeHtml(tags, compact = false) {
    if (!tags || tags.length === 0) {
        return '';
    }
    
    // Сортируем теги по категории и имени
    const sortedTags = [...tags].sort((a, b) => {
        if (a.category !== b.category) {
            // Приоритет категорий
            const categoryOrder = ['environment', 'priority', 'status', 'service_type', 'custom'];
            return categoryOrder.indexOf(a.category) - categoryOrder.indexOf(b.category);
        }
        return a.name.localeCompare(b.name);
    });
    
    // В компактном режиме показываем только первые 3 тега
    const displayTags = compact && sortedTags.length > 3 
        ? sortedTags.slice(0, 3) 
        : sortedTags;
    
    let html = '<span class="tags-container">';
    
    displayTags.forEach(tag => {
        const tooltip = tag.description || tag.name;
        html += `<span class="tag-badge tag-${tag.category}" 
                       style="background-color: ${tag.color};" 
                       title="${tooltip}"
                       data-tag-name="${tag.name}"
                       data-tag-id="${tag.id}">
                    ${tag.name}
                 </span>`;
    });
    
    // Если есть скрытые теги в компактном режиме
    if (compact && sortedTags.length > 3) {
        const hiddenCount = sortedTags.length - 3;
        html += `<span class="tag-badge tag-more" title="И еще ${hiddenCount} тег(ов)">
                    +${hiddenCount}
                 </span>`;
    }
    
    html += '</span>';
    return html;
}

/**
 * Модифицированная функция создания строки приложения с тегами
 * Эта функция должна заменить или дополнить существующую createApplicationRow
 */
function createApplicationRowWithTags(app, isChild = false) {
    const row = document.createElement('tr');
    row.className = isChild ? 'app-child-row' : 'app-row';
    row.setAttribute('data-app-id', app.id);
    
    const statusDot = app.status === 'online' ?
        '<span class="service-dot"></span>' : 
        '<span class="service-dot offline"></span>';
    
    // Загружаем теги асинхронно
    let tagsHtml = '<span class="tags-loading">...</span>';
    
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
            <div class="service-name-with-tags">
                <span class="service-name-text">${app.name}</span>
                <span class="service-tags" data-app-id="${app.id}">${tagsHtml}</span>
            </div>
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
                    <div class="dropdown-divider"></div>
                    <a href="#" class="dropdown-item" onclick="openTagsModal(${app.id}); return false;">
                        <i class="dropdown-icon">🏷️</i> Управление тегами
                    </a>
                </div>
            </div>
        </td>
    `;
    
    // Асинхронно загружаем и отображаем теги
    loadApplicationTags(app.id).then(tags => {
        const tagsContainer = row.querySelector('.service-tags');
        if (tagsContainer) {
            tagsContainer.innerHTML = createTagsBadgeHtml(tags, true);
            
            // Добавляем обработчик для показа всех тегов
            const moreTag = tagsContainer.querySelector('.tag-more');
            if (moreTag) {
                moreTag.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showAllTagsPopup(app.id, tags, e.target);
                });
            }
        }
    });
    
    // Добавляем обработчик клика для строки
    row.addEventListener('click', function(e) {
        if (e.target.closest('.checkbox-container') || 
            e.target.closest('.actions-menu') ||
            e.target.closest('.tag-badge')) {
            return;
        }
        this.classList.toggle('expanded');
    });
    
    return row;
}

/**
 * Показать попап со всеми тегами
 */
function showAllTagsPopup(appId, tags, targetElement) {
    // Удаляем существующий попап если есть
    const existingPopup = document.querySelector('.tags-popup');
    if (existingPopup) {
        existingPopup.remove();
    }
    
    // Создаем новый попап
    const popup = document.createElement('div');
    popup.className = 'tags-popup';
    popup.innerHTML = `
        <div class="tags-popup-header">
            Все теги приложения
            <button class="tags-popup-close">&times;</button>
        </div>
        <div class="tags-popup-content">
            ${createTagsBadgeHtml(tags, false)}
        </div>
    `;
    
    // Позиционируем относительно элемента
    const rect = targetElement.getBoundingClientRect();
    popup.style.position = 'absolute';
    popup.style.left = rect.left + 'px';
    popup.style.top = (rect.bottom + 5) + 'px';
    
    document.body.appendChild(popup);
    
    // Обработчики закрытия
    popup.querySelector('.tags-popup-close').addEventListener('click', () => {
        popup.remove();
    });
    
    // Закрытие при клике вне попапа
    setTimeout(() => {
        document.addEventListener('click', function closePopup(e) {
            if (!popup.contains(e.target)) {
                popup.remove();
                document.removeEventListener('click', closePopup);
            }
        });
    }, 100);
}

/**
 * Открыть модальное окно управления тегами
 */
async function openTagsModal(appId) {
    try {
        // Загружаем данные о приложении и доступных тегах
        const [appTagsResponse, allTagsResponse] = await Promise.all([
            fetch(`/api/applications/${appId}/tags`),
            fetch('/api/tags')
        ]);
        
        const appTagsData = await appTagsResponse.json();
        const allTagsData = await allTagsResponse.json();
        
        if (!appTagsData.success || !allTagsData.success) {
            showError('Не удалось загрузить данные о тегах');
            return;
        }
        
        // Создаем содержимое модального окна
        const modalContent = createTagsModalContent(
            appId,
            appTagsData.own_tags,
            appTagsData.inherited_tags,
            allTagsData.by_category
        );
        
        // Показываем модальное окно
        showModal('Управление тегами', modalContent);
        
        // Инициализируем обработчики
        initializeTagsModalHandlers(appId);
        
    } catch (error) {
        console.error('Error opening tags modal:', error);
        showError('Ошибка при открытии окна управления тегами');
    }
}

/**
 * Создать содержимое модального окна управления тегами
 */
function createTagsModalContent(appId, ownTags, inheritedTags, allTagsByCategory) {
    const ownTagsHtml = ownTags.length > 0 
        ? createTagsBadgeHtml(ownTags, false)
        : '<span class="no-tags">Нет собственных тегов</span>';
    
    const inheritedTagsHtml = inheritedTags.length > 0
        ? createTagsBadgeHtml(inheritedTags, false)
        : '<span class="no-tags">Нет унаследованных тегов</span>';
    
    // Создаем список доступных тегов по категориям
    let availableTagsHtml = '';
    for (const [category, tags] of Object.entries(allTagsByCategory)) {
        if (tags.length === 0) continue;
        
        const categoryTitle = {
            'environment': 'Окружение',
            'service_type': 'Тип сервиса',
            'priority': 'Приоритет',
            'status': 'Статус',
            'custom': 'Пользовательские'
        }[category] || category;
        
        availableTagsHtml += `
            <div class="tag-category">
                <h5>${categoryTitle}</h5>
                <div class="available-tags">
                    ${tags.map(tag => `
                        <span class="tag-badge tag-selectable tag-${tag.category}"
                              style="background-color: ${tag.color};"
                              data-tag-name="${tag.name}"
                              data-tag-id="${tag.id}"
                              title="${tag.description || tag.name}">
                            ${tag.name}
                        </span>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    return `
        <div class="tags-modal-container">
            <div class="tags-section">
                <h4>Собственные теги</h4>
                <div class="current-tags">
                    ${ownTagsHtml}
                </div>
            </div>
            
            <div class="tags-section">
                <h4>Унаследованные от группы</h4>
                <div class="inherited-tags">
                    ${inheritedTagsHtml}
                </div>
            </div>
            
            <div class="tags-section">
                <h4>Доступные теги</h4>
                <div class="tags-help">
                    Кликните на тег чтобы добавить или удалить его
                </div>
                ${availableTagsHtml}
            </div>
            
            <div class="tags-section">
                <h4>Создать новый тег</h4>
                <div class="new-tag-form">
                    <input type="text" id="new-tag-name" placeholder="Имя тега" class="form-control">
                    <input type="color" id="new-tag-color" value="#6c757d" class="color-picker">
                    <select id="new-tag-category" class="form-control">
                        <option value="custom">Пользовательский</option>
                        <option value="environment">Окружение</option>
                        <option value="service_type">Тип сервиса</option>
                        <option value="priority">Приоритет</option>
                        <option value="status">Статус</option>
                    </select>
                    <button id="create-tag-btn" class="action-btn">Создать</button>
                </div>
            </div>
        </div>
    `;
}

/**
 * Инициализировать обработчики для модального окна тегов
 */
function initializeTagsModalHandlers(appId) {
    // Обработчик для выбираемых тегов
    document.querySelectorAll('.tag-selectable').forEach(tag => {
        tag.addEventListener('click', async () => {
            const tagName = tag.getAttribute('data-tag-name');
            
            // Проверяем, есть ли уже этот тег
            const currentTags = document.querySelector('.current-tags');
            const hasTag = currentTags.querySelector(`[data-tag-name="${tagName}"]`);
            
            if (hasTag) {
                // Удаляем тег
                await removeTagFromApplication(appId, tagName);
            } else {
                // Добавляем тег
                await addTagToApplication(appId, tagName);
            }
            
            // Перезагружаем модальное окно
            openTagsModal(appId);
        });
    });
    
    // Обработчик создания нового тега
    document.getElementById('create-tag-btn').addEventListener('click', async () => {
        const name = document.getElementById('new-tag-name').value.trim();
        const color = document.getElementById('new-tag-color').value;
        const category = document.getElementById('new-tag-category').value;
        
        if (!name) {
            showError('Введите имя тега');
            return;
        }
        
        try {
            const response = await fetch('/api/tags', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, color, category})
            });
            
            const data = await response.json();
            
            if (data.success) {
                showNotification(`Тег "${name}" создан`);
                // Добавляем новый тег к приложению
                await addTagToApplication(appId, name);
                // Перезагружаем модальное окно
                openTagsModal(appId);
            } else {
                showError(data.error || 'Не удалось создать тег');
            }
        } catch (error) {
            console.error('Error creating tag:', error);
            showError('Ошибка при создании тега');
        }
    });
}

/**
 * Добавить тег к приложению
 */
async function addTagToApplication(appId, tagName) {
    try {
        const response = await fetch(`/api/applications/${appId}/tags`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tag_name: tagName})
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Очищаем кеш
            tagsCache.delete(appId);
            showNotification(`Тег "${tagName}" добавлен`);
            return true;
        } else {
            showError(data.error || 'Не удалось добавить тег');
            return false;
        }
    } catch (error) {
        console.error('Error adding tag:', error);
        showError('Ошибка при добавлении тега');
        return false;
    }
}

/**
 * Удалить тег у приложения
 */
async function removeTagFromApplication(appId, tagName) {
    try {
        const response = await fetch(`/api/applications/${appId}/tags/${tagName}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Очищаем кеш
            tagsCache.delete(appId);
            showNotification(`Тег "${tagName}" удален`);
            return true;
        } else {
            showError(data.error || 'Не удалось удалить тег');
            return false;
        }
    } catch (error) {
        console.error('Error removing tag:', error);
        showError('Ошибка при удалении тега');
        return false;
    }
}

/**
 * Пакетное добавление тегов к выбранным приложениям
 */
async function batchAddTags(applicationIds, tagName) {
    try {
        const response = await fetch('/api/applications/batch-tag', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                application_ids: applicationIds,
                tag_name: tagName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(`Тег добавлен к ${data.processed} приложениям`);
            // Очищаем кеш для обновленных приложений
            applicationIds.forEach(id => tagsCache.delete(id));
            // Обновляем отображение
            if (typeof filterAndDisplayApplications === 'function') {
                filterAndDisplayApplications();
            }
        } else {
            showError(data.error || 'Ошибка при добавлении тегов');
        }
    } catch (error) {
        console.error('Error in batch tag operation:', error);
        showError('Ошибка при пакетном добавлении тегов');
    }
}

/**
 * Загрузить теги для группы приложений
 * @param {number} groupId - ID группы
 * @returns {Promise<Array>} Массив тегов
 */
async function loadGroupTags(groupId) {
    // Проверяем кеш
    const cacheKey = `group_${groupId}`;
    if (tagsCache.has(cacheKey)) {
        return tagsCache.get(cacheKey);
    }
    
    try {
        const response = await fetch(`/api/groups/${groupId}/tags`);
        const data = await response.json();
        
        if (data.success) {
            // Кешируем результат
            tagsCache.set(cacheKey, data.tags);
            return data.tags;
        }
        
        return [];
    } catch (error) {
        console.error(`Error loading tags for group ${groupId}:`, error);
        return [];
    }
}

/**
 * Создать строку группы с тегами
 */
function createGroupRowWithTags(groupName, groupApps, groupId) {
    const row = document.createElement('tr');
    row.className = 'group-row';
    row.setAttribute('data-group', groupName);
    if (groupId) {
        row.setAttribute('data-group-id', groupId);
    }
    
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
    
    // Создаем место для тегов
    let tagsHtml = '';
    if (groupId) {
        tagsHtml = '<span class="group-tags" data-group-id="' + groupId + '"><span class="tags-loading">...</span></span>';
    }
    
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
                ${tagsHtml}
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
                    ${groupId ? `
                    <div class="dropdown-divider"></div>
                    <a href="#" class="dropdown-item manage-group-tags" 
                       onclick="openGroupTagsModal(${groupId}, '${groupName.replace(/'/g, "\\'")}'); return false;">
                        <i class="dropdown-icon">🏷️</i> Управление тегами группы
                    </a>
                    <a href="#" class="dropdown-item sync-group-tags" 
                       onclick="syncGroupTagsToInstances(${groupId}); return false;">
                        <i class="dropdown-icon">🔄</i> Синхронизировать теги
                    </a>` : ''}
                </div>
            </div>
        </td>
    `;
    
    // Асинхронно загружаем теги группы
    if (groupId) {
        loadGroupTags(groupId).then(tags => {
            const tagsContainer = row.querySelector('.group-tags');
            if (tagsContainer && tags && tags.length > 0) {
                // Фильтруем только наследуемые теги для отображения
                const displayTags = tags.filter(t => t.inheritable !== false);
                if (displayTags.length > 0) {
                    tagsContainer.innerHTML = createTagsBadgeHtml(displayTags, true);
                    
                    // Добавляем обработчик для показа всех тегов
                    const moreTag = tagsContainer.querySelector('.tag-more');
                    if (moreTag) {
                        moreTag.addEventListener('click', (e) => {
                            e.stopPropagation();
                            showAllTagsPopup(groupId, tags, e.target, 'group');
                        });
                    }
                } else {
                    tagsContainer.innerHTML = '';
                }
            }
        }).catch(err => {
            console.warn('Failed to load tags for group', groupId, err);
            const tagsContainer = row.querySelector('.group-tags');
            if (tagsContainer) {
                tagsContainer.innerHTML = '';
            }
        });
    }
    
    return row;
}

/**
 * Создать строку дочернего приложения с тегами
 */
function createChildRowWithTags(app, groupName) {
    const childRow = document.createElement('tr');
    childRow.className = 'app-child-row';
    childRow.setAttribute('data-app-id', app.id);
    childRow.setAttribute('data-parent', groupName);
    
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
            <div class="service-name-with-tags">
                <span class="service-name-text">${app.name}</span>
                <span class="app-tags" data-app-id="${app.id}"></span>
            </div>
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
                    ${window.createActionMenuItems ? window.createActionMenuItems(app) : `
                        <a href="#" class="app-info-btn" data-app-id="${app.id}">Информация</a>
                        <a href="#" class="app-start-btn" data-app-id="${app.id}">Запустить</a>
                        <a href="#" class="app-stop-btn" data-app-id="${app.id}">Остановить</a>
                        <a href="#" class="app-restart-btn" data-app-id="${app.id}">Перезапустить</a>
                        <a href="#" class="app-update-btn" data-app-id="${app.id}">Обновить</a>
                    `}
                    <div class="dropdown-divider"></div>
                    <a href="#" class="dropdown-item" onclick="openTagsModal(${app.id}); return false;">
                        <i class="dropdown-icon">🏷️</i> Управление тегами
                    </a>
                </div>
            </div>
        </td>
    `;
    
    // Добавляем обработчик клика
    childRow.addEventListener('click', function(e) {
        if (e.target.closest('.checkbox-container') || e.target.closest('.actions-menu')) {
            return;
        }
        this.classList.toggle('expanded');
    });
    
    // Асинхронно загружаем теги приложения
    loadApplicationTags(app.id).then(tags => {
        const tagsContainer = childRow.querySelector('.app-tags');
        if (tagsContainer && tags && tags.length > 0) {
            tagsContainer.innerHTML = createTagsBadgeHtml(tags, true);
        }
    }).catch(err => {
        console.warn('Failed to load tags for app', app.id, err);
    });
    
    return childRow;
}

/**
 * Открыть модальное окно управления тегами группы
 * @param {number} groupId - ID группы
 * @param {string} groupName - Имя группы (опционально)
 */
async function openGroupTagsModal(groupId, groupName) {
    try {
        // Загружаем теги группы
        const groupTags = await loadGroupTags(groupId);
        
        // Загружаем все доступные теги
        const allTagsResponse = await fetch('/api/tags');
        const allTagsData = await allTagsResponse.json();
        const allTags = allTagsData.success ? allTagsData.tags : [];
        
        // Получаем имя группы если не передано
        if (!groupName) {
            const groupRow = document.querySelector(`[data-group-id="${groupId}"]`);
            groupName = groupRow ? groupRow.getAttribute('data-group') : `Группа ${groupId}`;
        }
        
        // Создаем модальное окно
        const modalHtml = createGroupTagsModalHtml(groupId, groupName, groupTags, allTags);
        showGroupTagsModal(modalHtml, groupId);
        
    } catch (error) {
        console.error('Error opening group tags modal:', error);
        showError('Ошибка при открытии окна управления тегами');
    }
}

/**
 * Создать HTML для модального окна тегов группы
 */
function createGroupTagsModalHtml(groupId, groupName, currentTags, allTags) {
    // Группируем теги по категориям
    const tagsByCategory = {
        'environment': [],
        'service_type': [],
        'priority': [],
        'status': [],
        'custom': []
    };
    
    allTags.forEach(tag => {
        const category = tag.category || 'custom';
        if (tagsByCategory[category]) {
            tagsByCategory[category].push(tag);
        }
    });
    
    // Создаем Set текущих тегов для быстрой проверки
    const currentTagIds = new Set(currentTags.map(t => t.id));
    
    let html = `
        <div class="group-tags-modal-content">
            <h3>Управление тегами группы: ${groupName}</h3>
            
            <div class="tags-section">
                <h4>Текущие теги группы</h4>
                <div class="current-group-tags" id="current-group-tags-${groupId}">
                    ${currentTags.length > 0 ? 
                        currentTags.map(tag => `
                            <span class="tag-badge tag-${tag.category} tag-removable" 
                                  style="background-color: ${tag.color};"
                                  data-tag-id="${tag.id}"
                                  data-tag-name="${tag.name}"
                                  title="Кликните для удаления">
                                ${tag.name}
                                ${tag.inheritable !== false ? 
                                    '<span class="tag-inheritable" title="Наследуется экземплярами">↓</span>' : ''}
                                <span class="tag-remove">×</span>
                            </span>
                        `).join('') 
                        : '<span class="no-tags">Нет тегов</span>'}
                </div>
            </div>
            
            <div class="tags-section">
                <h4>Доступные теги</h4>
                <div class="inheritable-toggle">
                    <label>
                        <input type="checkbox" id="make-inheritable-${groupId}" checked>
                        Сделать теги наследуемыми для экземпляров
                    </label>
                </div>
                <div class="available-tags-container">`;
    
    // Добавляем теги по категориям
    for (const [category, tags] of Object.entries(tagsByCategory)) {
        if (tags.length === 0) continue;
        
        const categoryTitle = {
            'environment': 'Окружение',
            'service_type': 'Тип сервиса',
            'priority': 'Приоритет',
            'status': 'Статус',
            'custom': 'Пользовательские'
        }[category] || category;
        
        html += `
            <div class="tag-category">
                <h5>${categoryTitle}</h5>
                <div class="available-tags">
                    ${tags.map(tag => {
                        const isActive = currentTagIds.has(tag.id);
                        return `
                            <span class="tag-badge tag-selectable ${isActive ? 'tag-active' : ''} tag-${tag.category}"
                                  style="background-color: ${tag.color};"
                                  data-tag-id="${tag.id}"
                                  data-tag-name="${tag.name}"
                                  title="${tag.description || tag.name}">
                                ${tag.name}
                            </span>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }
    
    html += `
                </div>
            </div>
            
            <div class="tags-section">
                <h4>Создать новый тег</h4>
                <div class="new-tag-form">
                    <input type="text" id="new-tag-name-${groupId}" 
                           placeholder="Название тега" maxlength="50">
                    <select id="new-tag-category-${groupId}">
                        <option value="custom">Пользовательский</option>
                        <option value="environment">Окружение</option>
                        <option value="service_type">Тип сервиса</option>
                        <option value="priority">Приоритет</option>
                        <option value="status">Статус</option>
                    </select>
                    <button onclick="addNewTagToGroup(${groupId})">Добавить новый тег</button>
                </div>
            </div>
            
            <div class="modal-actions">
                <button onclick="syncGroupTagsToInstances(${groupId})" class="btn-sync">
                    Синхронизировать с экземплярами
                </button>
                <button onclick="closeGroupTagsModal()" class="btn-close">Закрыть</button>
            </div>
        </div>
    `;
    
    return html;
}

/**
 * Показать модальное окно тегов группы
 */
function showGroupTagsModal(htmlContent, groupId) {
    // Удаляем существующее модальное окно если есть
    const existingModal = document.getElementById('group-tags-modal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Создаем новое модальное окно
    const modal = document.createElement('div');
    modal.id = 'group-tags-modal';
    modal.className = 'tags-modal';
    modal.innerHTML = `
        <div class="tags-modal-overlay" onclick="closeGroupTagsModal()"></div>
        <div class="tags-modal-container">
            ${htmlContent}
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Добавляем обработчики событий
    setupGroupTagsEventHandlers(groupId);
}

/**
 * Настроить обработчики событий для модального окна
 */
function setupGroupTagsEventHandlers(groupId) {
    const modal = document.getElementById('group-tags-modal');
    if (!modal) return;
    
    // Обработчики для добавления/удаления тегов
    modal.querySelectorAll('.tag-selectable').forEach(tag => {
        tag.addEventListener('click', async function() {
            const tagName = this.getAttribute('data-tag-name');
            const tagId = this.getAttribute('data-tag-id');
            const isActive = this.classList.contains('tag-active');
            
            if (isActive) {
                await removeTagFromGroup(groupId, tagName);
            } else {
                const inheritable = document.getElementById(`make-inheritable-${groupId}`).checked;
                await addTagToGroup(groupId, tagName, inheritable);
            }
        });
    });
    
    // Обработчики для удаления текущих тегов
    modal.querySelectorAll('.tag-removable').forEach(tag => {
        tag.addEventListener('click', async function() {
            const tagName = this.getAttribute('data-tag-name');
            await removeTagFromGroup(groupId, tagName);
        });
    });
}

/**
 * Добавить тег к группе
 */
async function addTagToGroup(groupId, tagName, inheritable = true) {
    try {
        const response = await fetch(`/api/groups/${groupId}/tags`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tag_name: tagName,
                inheritable: inheritable,
                assigned_by: 'manual'
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Очищаем кеш
            tagsCache.delete(`group_${groupId}`);
            
            // Обновляем модальное окно
            await refreshGroupTagsModal(groupId);
            
            // Обновляем отображение в таблице
            updateGroupTagsDisplay(groupId);
            
            showNotification(`Тег "${tagName}" добавлен к группе`);
        } else {
            showError(data.error || 'Не удалось добавить тег');
        }
    } catch (error) {
        console.error('Error adding tag to group:', error);
        showError('Ошибка при добавлении тега');
    }
}

/**
 * Удалить тег у группы
 */
async function removeTagFromGroup(groupId, tagName) {
    try {
        const response = await fetch(`/api/groups/${groupId}/tags/${tagName}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Очищаем кеш
            tagsCache.delete(`group_${groupId}`);
            
            // Обновляем модальное окно
            await refreshGroupTagsModal(groupId);
            
            // Обновляем отображение в таблице
            updateGroupTagsDisplay(groupId);
            
            showNotification(`Тег "${tagName}" удален из группы`);
        } else {
            showError(data.error || 'Не удалось удалить тег');
        }
    } catch (error) {
        console.error('Error removing tag from group:', error);
        showError('Ошибка при удалении тега');
    }
}

/**
 * Добавить новый тег и назначить его группе
 */
async function addNewTagToGroup(groupId) {
    const nameInput = document.getElementById(`new-tag-name-${groupId}`);
    const categorySelect = document.getElementById(`new-tag-category-${groupId}`);
    const inheritableCheck = document.getElementById(`make-inheritable-${groupId}`);
    
    const tagName = nameInput.value.trim();
    const category = categorySelect.value;
    const inheritable = inheritableCheck.checked;
    
    if (!tagName) {
        showError('Введите название тега');
        return;
    }
    
    try {
        // Сначала создаем тег
        const createResponse = await fetch('/api/tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: tagName,
                category: category,
                color: generateTagColor(category),
                description: `Создан для группы ${groupId}`
            })
        });
        
        const createData = await createResponse.json();
        
        if (createData.success || createResponse.status === 409) { // 409 = тег уже существует
            // Добавляем тег к группе
            await addTagToGroup(groupId, tagName, inheritable);
            
            // Очищаем форму
            nameInput.value = '';
            categorySelect.value = 'custom';
        } else {
            showError(createData.error || 'Не удалось создать тег');
        }
    } catch (error) {
        console.error('Error creating new tag:', error);
        showError('Ошибка при создании тега');
    }
}

/**
 * Синхронизировать теги группы с экземплярами
 */
async function syncGroupTagsToInstances(groupId) {
    try {
        const response = await fetch(`/api/groups/${groupId}/sync-tags`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(`Теги синхронизированы с ${data.message}`);
            
            // Обновляем отображение приложений в группе
            if (window.loadApplications) {
                window.loadApplications();
            }
        } else {
            showError(data.error || 'Ошибка синхронизации');
        }
    } catch (error) {
        console.error('Error syncing group tags:', error);
        showError('Ошибка при синхронизации тегов');
    }
}

/**
 * Обновить модальное окно тегов группы
 */
async function refreshGroupTagsModal(groupId) {
    const modal = document.getElementById('group-tags-modal');
    if (!modal) return;
    
    // Получаем имя группы из текущего заголовка
    const titleElement = modal.querySelector('h3');
    const groupName = titleElement ? 
        titleElement.textContent.replace('Управление тегами группы: ', '') : 
        `Группа ${groupId}`;
    
    // Перезагружаем модальное окно
    await openGroupTagsModal(groupId, groupName);
}

/**
 * Обновить отображение тегов группы в таблице
 */
async function updateGroupTagsDisplay(groupId) {
    const groupRow = document.querySelector(`[data-group-id="${groupId}"]`);
    if (!groupRow) return;
    
    const tagsContainer = groupRow.querySelector('.group-tags');
    if (!tagsContainer) return;
    
    try {
        const tags = await loadGroupTags(groupId);
        
        if (tags && tags.length > 0) {
            const displayTags = tags.filter(t => t.inheritable !== false);
            if (displayTags.length > 0) {
                tagsContainer.innerHTML = createTagsBadgeHtml(displayTags, true);
            } else {
                tagsContainer.innerHTML = '';
            }
        } else {
            tagsContainer.innerHTML = '';
        }
    } catch (error) {
        console.error('Error updating group tags display:', error);
    }
}

/**
 * Закрыть модальное окно тегов группы
 */
function closeGroupTagsModal() {
    const modal = document.getElementById('group-tags-modal');
    if (modal) {
        modal.remove();
    }
}

/**
 * Генерировать цвет для тега на основе категории
 */
function generateTagColor(category) {
    const colors = {
        'environment': '#dc3545',
        'service_type': '#007bff',
        'priority': '#ffc107',
        'status': '#28a745',
        'custom': '#6c757d'
    };
    return colors[category] || colors['custom'];
}

/**
 * Получить ID группы по имени
 * @param {string} groupName - Имя группы
 * @returns {Promise<number|null>} ID группы или null
 */
async function getGroupIdByName(groupName) {
    try {
        const response = await fetch('/api/application-groups');
        const data = await response.json();
        
        if (data.success && data.groups) {
            const group = data.groups.find(g => g.name === groupName);
            return group ? group.id : null;
        }
        
        return null;
    } catch (error) {
        console.error('Error fetching group ID:', error);
        return null;
    }
}

/**
 * Открыть модальное окно тегов группы по имени (если ID неизвестен)
 * @param {string} groupName - Имя группы
 */
async function openGroupTagsModalByName(groupName) {
    const groupId = await getGroupIdByName(groupName);
    
    if (groupId) {
        openGroupTagsModal(groupId, groupName);
    } else {
        showError(`Не удалось найти группу "${groupName}"`);
    }
}

/**
 * Добавить кнопку управления тегами к существующим группам
 * Эта функция может быть вызвана после загрузки страницы
 */
function addTagsButtonToGroups() {
    document.querySelectorAll('.group-row').forEach(async row => {
        const groupName = row.getAttribute('data-group');
        let groupId = row.getAttribute('data-group-id');
        
        // Если нет ID, пытаемся получить
        if (!groupId && groupName) {
            groupId = await getGroupIdByName(groupName);
            if (groupId) {
                row.setAttribute('data-group-id', groupId);
            }
        }
        
        if (groupId) {
            // Проверяем, есть ли уже кнопка
            const actionsDropdown = row.querySelector('.actions-dropdown');
            if (actionsDropdown && !actionsDropdown.querySelector('.manage-group-tags')) {
                // Добавляем разделитель и кнопки
                const divider = document.createElement('div');
                divider.className = 'dropdown-divider';
                actionsDropdown.appendChild(divider);
                
                const manageTagsLink = document.createElement('a');
                manageTagsLink.href = '#';
                manageTagsLink.className = 'dropdown-item manage-group-tags';
                manageTagsLink.innerHTML = '<i class="dropdown-icon">🏷️</i> Управление тегами группы';
                manageTagsLink.onclick = function(e) {
                    e.preventDefault();
                    openGroupTagsModal(groupId, groupName);
                    return false;
                };
                actionsDropdown.appendChild(manageTagsLink);
                
                const syncTagsLink = document.createElement('a');
                syncTagsLink.href = '#';
                syncTagsLink.className = 'dropdown-item sync-group-tags';
                syncTagsLink.innerHTML = '<i class="dropdown-icon">🔄</i> Синхронизировать теги';
                syncTagsLink.onclick = function(e) {
                    e.preventDefault();
                    syncGroupTagsToInstances(groupId);
                    return false;
                };
                actionsDropdown.appendChild(syncTagsLink);
            }
        }
    });
}

window.openGroupTagsModal = openGroupTagsModal;
window.addNewTagToGroup = addNewTagToGroup;
window.syncGroupTagsToInstances = syncGroupTagsToInstances;
window.closeGroupTagsModal = closeGroupTagsModal;
window.getGroupIdByName = getGroupIdByName;
window.openGroupTagsModalByName = openGroupTagsModalByName;
window.addTagsButtonToGroups = addTagsButtonToGroups;


// Добавляем новые функции в глобальный объект TagsIntegration
window.TagsIntegration = window.TagsIntegration || {};
Object.assign(window.TagsIntegration, {
    loadApplicationTags,
    batchLoadApplicationTags,
    createTagsBadgeHtml,
    createApplicationRowWithTags,
    openTagsModal,
    addTagToApplication,
    removeTagFromApplication,
    batchAddTags,
    // Новые функции для групп
    loadGroupTags,
    createGroupRowWithTags,
    createChildRowWithTags,
    openGroupTagsModal,
    addTagToGroup,
    removeTagFromGroup,
    syncGroupTagsToInstances,
    updateGroupTagsDisplay,
    getGroupIdByName,
    openGroupTagsModalByName,
    addTagsButtonToGroups    
});



/**
 * Интеграция системы тегов в интерфейс приложений
 */

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
                showSuccess(`Тег "${name}" создан`);
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
            showSuccess(`Тег "${tagName}" добавлен`);
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
            showSuccess(`Тег "${tagName}" удален`);
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
            showSuccess(`Тег добавлен к ${data.processed} приложениям`);
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

// Экспортируем функции для использования в основном коде
window.TagsIntegration = {
    loadApplicationTags,
    batchLoadApplicationTags,
    createTagsBadgeHtml,
    createApplicationRowWithTags,
    openTagsModal,
    addTagToApplication,
    removeTagFromApplication,
    batchAddTags
};
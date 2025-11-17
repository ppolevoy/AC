// Глобальные переменные для управления состоянием
let allApplications = [];
let selectedApp = null;
let selectedInstance = null;
let selectedGroup = null;
let applicationGroups = [];
let ungroupedApps = [];

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    initializeAppGroupsManagement();
});

function initializeAppGroupsManagement() {
    // Обработчик раскрытия/сворачивания блока
    const statusLine = document.getElementById('app-groups-status-line');
    const detailsSection = document.getElementById('app-groups-details');
    const expandArrow = document.getElementById('app-groups-expand-arrow');
    
    if (statusLine) {
        statusLine.addEventListener('click', function() {
            const isExpanded = detailsSection.style.display !== 'none';
            
            if (isExpanded) {
                detailsSection.style.display = 'none';
                expandArrow.textContent = '▼';
            } else {
                detailsSection.style.display = 'block';
                expandArrow.textContent = '▲';
                // Загружаем данные при раскрытии
                loadAppGroupsData();
            }
        });
    }
    
    // Обработчик фильтра приложений
    const filterInput = document.getElementById('app-filter-input');
    if (filterInput) {
        filterInput.addEventListener('input', function() {
            filterApplicationsList(this.value);
        });
    }
    
    // Обработчики кнопок сохранения
    const saveGroupBtn = document.getElementById('save-group-settings-btn');
    if (saveGroupBtn) {
        saveGroupBtn.addEventListener('click', saveGroupSettings);
    }
    
    const saveInstanceBtn = document.getElementById('save-instance-settings-btn');
    if (saveInstanceBtn) {
        saveInstanceBtn.addEventListener('click', saveInstanceSettings);
    }
    
    const assignGroupBtn = document.getElementById('assign-group-btn');
    if (assignGroupBtn) {
        assignGroupBtn.addEventListener('click', assignGroupManually);
    }
    
    // Загружаем начальный статус
    updateAppGroupsStatus();
}

// Обновление статуса приложений и групп
async function updateAppGroupsStatus() {
    try {
        const response = await fetch('/api/application-groups/statistics');
        const data = await response.json();
        
        if (data.success) {
            const statusText = document.querySelector('#app-groups-status-indicator .status-text');
            const statusDot = document.querySelector('#app-groups-status-indicator .status-dot');
            
            statusText.textContent = `${data.total_groups} групп, ${data.total_instances} экземпляров`;
            
            if (data.unresolved_instances > 0) {
                statusDot.className = 'status-dot warning';
                statusText.textContent += ` (${data.unresolved_instances} без группы)`;
            } else {
                statusDot.className = 'status-dot connected';
            }
        }
    } catch (error) {
        console.error('Error updating app groups status:', error);
        const statusText = document.querySelector('#app-groups-status-indicator .status-text');
        const statusDot = document.querySelector('#app-groups-status-indicator .status-dot');
        statusDot.className = 'status-dot error';
        statusText.textContent = 'Ошибка загрузки';
    }
}

// Загрузка данных приложений и групп
async function loadAppGroupsData() {
    try {
        // Загружаем список всех приложений с информацией о группах
        const appsResponse = await fetch('/api/applications/with-groups');
        const appsData = await appsResponse.json();
        
        if (appsData.success) {
            allApplications = appsData.applications;
            displayApplicationsList(allApplications);
        }
        
        // Загружаем список групп
        const groupsResponse = await fetch('/api/application-groups');
        const groupsData = await groupsResponse.json();
        
        if (groupsData.success) {
            applicationGroups = groupsData.groups;
        }
        
        // Загружаем приложения без группы
        await loadUngroupedApplications();
        
        // Загружаем статистику
        await loadStatistics();
        
    } catch (error) {
        console.error('Error loading app groups data:', error);
        showNotification('Ошибка загрузки данных', 'error');
    }
}

// Отображение списка групп (только группы, без экземпляров)
function displayApplicationsList(applications) {
    const container = document.getElementById('apps-list-container');
    
    if (!applications || applications.length === 0) {
        container.innerHTML = '<div class="no-data">Группы не найдены</div>';
        return;
    }
    
    // Группируем приложения по группам для подсчета
    const grouped = {};
    applications.forEach(app => {
        const groupName = app.group_name || 'Без группы';
        if (!grouped[groupName]) {
            grouped[groupName] = {
                groupId: app.group_id,
                count: 0,
                apps: []
            };
        }
        grouped[groupName].count++;
        grouped[groupName].apps.push(app);
    });
    
    // Создаем HTML только для групп
    let html = '<div class="groups-list">';
    
    Object.keys(grouped).sort().forEach(groupName => {
        const groupInfo = grouped[groupName];
        
        if (groupName !== 'Без группы') {
            html += `
                <div class="group-item clickable" data-group-id="${groupInfo.groupId}" data-group-name="${groupName}">
                    <span class="group-icon">📁</span>
                    <span class="group-name">${groupName}</span>
                    <span class="group-count">(${groupInfo.count} экз.)</span>
                </div>
            `;
        }
    });
    
    // Добавляем группу "Без группы" в конец, если есть
    if (grouped['Без группы']) {
        html += `
            <div class="group-item no-group">
                <span class="group-icon">⚠️</span>
                <span class="group-name">Без группы</span>
                <span class="group-count">(${grouped['Без группы'].count} экз.)</span>
            </div>
        `;
    }
    
    html += '</div>';
    container.innerHTML = html;
    
    // Добавляем обработчики клика на группы
    container.querySelectorAll('.group-item.clickable').forEach(item => {
        item.addEventListener('click', function() {
            selectGroup(this.dataset.groupId, this.dataset.groupName);
        });
    });
}

// Фильтрация списка групп
function filterApplicationsList(filterText) {
    const lowerFilter = filterText.toLowerCase();
    
    // Фильтруем приложения по имени группы
    const filtered = allApplications.filter(app => {
        const groupName = app.group_name || 'Без группы';
        return groupName.toLowerCase().includes(lowerFilter);
    });
    
    // Отображаем отфильтрованные группы
    displayApplicationsList(filtered);
}

// Выбор группы для редактирования
async function selectGroup(groupId, groupName) {
    try {
        // Убираем выделение с групп
        document.querySelectorAll('.group-item').forEach(item => {
            item.classList.remove('selected');
        });
        
        // Выделяем текущую группу
        const groupItem = document.querySelector(`.group-item[data-group-id="${groupId}"]`);
        if (groupItem) {
            groupItem.classList.add('selected');
        }
        
        selectedGroup = groupId;
        selectedApp = null;
        selectedInstance = null;
        
        // Показываем настройки группы
        await displayGroupSettings(groupId, groupName);
        
    } catch (error) {
        console.error('Error selecting group:', error);
        showNotification('Ошибка загрузки настроек группы', 'error');
    }
}

// Отображение настроек группы
async function displayGroupSettings(groupId, groupName) {
    const detailsSection = document.getElementById('app-details-section');
    const appNameSpan = document.getElementById('selected-app-name');
    const instanceForm = document.getElementById('instance-settings-form');
    
    detailsSection.style.display = 'block';
    instanceForm.style.display = 'none'; // Скрываем форму экземпляра при выборе группы
    appNameSpan.textContent = `Группа: ${groupName}`;
    
    try {
        // Загружаем информацию о группе
        const response = await fetch(`/api/application-groups/${groupId}`);
        const data = await response.json();
        
        if (data.success) {
            // Отображаем экземпляры группы
            displayGroupInstances(data.group);
            
            // Заполняем форму настроек группы
            document.getElementById('group-artifact-url').value = data.group.artifact_list_url || '';
            document.getElementById('group-artifact-extension').value = data.group.artifact_extension || '';
            document.getElementById('group-playbook-path').value = data.group.update_playbook_path || '';
            
            // Показываем форму группы и скрываем форму экземпляра
            const groupForm = document.querySelector('.app-settings-form');
            if (groupForm) {
                groupForm.style.display = 'block';
            }
        }
    } catch (error) {
        console.error('Error loading group settings:', error);
        showNotification('Ошибка загрузки настроек группы', 'error');
    }
}

// Выбор приложения (экземпляра) для редактирования
async function selectApplication(appId) {
    try {
        // Убираем выделение с групп
        document.querySelectorAll('.group-item').forEach(item => {
            item.classList.remove('selected');
        });
        
        // Убираем выделение с других экземпляров
        document.querySelectorAll('.instance-item').forEach(item => {
            item.classList.remove('selected');
        });
        
        // Выделяем текущий экземпляр
        const instanceItem = document.querySelector(`.instance-item[data-instance-id="${appId}"]`);
        if (instanceItem) {
            instanceItem.classList.add('selected');
        }
        
        selectedApp = appId;
        selectedInstance = appId; // Для экземпляра используем ID приложения
        selectedGroup = null;
        
        // Загружаем детали приложения
        const response = await fetch(`/api/applications/${appId}/with-group`);
        const data = await response.json();
        
        if (data.success) {
            await displayApplicationDetails(data.application);
        }
        
    } catch (error) {
        console.error('Error selecting application:', error);
        showNotification('Ошибка загрузки деталей приложения', 'error');
    }
}

// Отображение деталей приложения (экземпляра)
async function displayApplicationDetails(app) {
    const detailsSection = document.getElementById('app-details-section');
    const appNameSpan = document.getElementById('selected-app-name');
    
    detailsSection.style.display = 'block';
    appNameSpan.textContent = `Экземпляр: ${app.name}`;
    
    // Если приложение принадлежит группе
    if (app.group_id && app.group_name) {
        // Загружаем информацию о группе для отображения других экземпляров
        const response = await fetch(`/api/application-groups/${app.group_id}`);
        const data = await response.json();
        
        if (data.success) {
            displayGroupInstances(data.group);
            
            // Заполняем форму настроек группы (для справки, но делаем её неактивной)
            document.getElementById('group-artifact-url').value = data.group.artifact_list_url || '';
            document.getElementById('group-artifact-extension').value = data.group.artifact_extension || '';
            document.getElementById('group-playbook-path').value = data.group.update_playbook_path || '';
            
            // Скрываем форму группы при выборе экземпляра
            const groupForm = document.querySelector('.app-settings-form');
            if (groupForm) {
                groupForm.style.display = 'none';
            }
        }
        
        // Загружаем настройки экземпляра
        await loadInstanceSettings(app.id);
        
    } else {
        // Приложение без группы
        const container = document.getElementById('app-instances-container');
        container.innerHTML = '<div class="warning">Приложение не принадлежит группе</div>';
        
        // Скрываем формы настроек
        document.getElementById('instance-settings-form').style.display = 'none';
        const groupForm = document.querySelector('.app-settings-form');
        if (groupForm) {
            groupForm.style.display = 'none';
        }
        
        // Показываем форму для назначения группы
        showManualGroupAssignment(app);
    }
}

// Отображение экземпляров группы
function displayGroupInstances(group) {
    const container = document.getElementById('app-instances-container');
    
    if (!group.applications || group.applications.length === 0) {
        container.innerHTML = '<div class="no-data">Нет экземпляров в группе</div>';
        return;
    }
    
    let html = '<div class="instances-list">';
    
    group.applications.forEach(app => {
        const isSelected = selectedInstance == app.id;
        html += `
            <div class="instance-item ${isSelected ? 'selected' : ''}" data-instance-id="${app.id}">
                <div class="instance-main">
                    <div class="instance-name">
                        <span class="instance-icon">📄</span> ${app.name}
                    </div>
                    <div class="instance-info">
                        Сервер: ${app.server ? app.server.name : 'Unknown'} | 
                        Экземпляр #${app.instance_number || 0} | 
                        Статус: <span class="status-badge ${app.status}">${app.status}</span>
                    </div>
                </div>
                ${app.has_custom_settings ? '<span class="custom-badge">Кастомные настройки</span>' : ''}
            </div>
        `;
    });
    html += '</div>';
    
    container.innerHTML = html;
    
    // Добавляем обработчики для выбора экземпляра
    container.querySelectorAll('.instance-item').forEach(item => {
        item.addEventListener('click', function(e) {
            e.stopPropagation(); // Предотвращаем всплытие события
            selectApplication(this.dataset.instanceId);
        });
    });
}

// Загрузка настроек экземпляра
async function loadInstanceSettings(appId) {
    try {
        const response = await fetch(`/api/applications/${appId}/instance-settings`);
        const data = await response.json();

        if (data.success) {
            const form = document.getElementById('instance-settings-form');
            const nameSpan = document.getElementById('selected-instance-name');

            form.style.display = 'block';
            nameSpan.textContent = `${data.application} #${data.instance_number}`;

            // Заполняем форму
            document.getElementById('instance-artifact-url').value =
                data.individual_settings.custom_artifact_list_url || '';
            document.getElementById('instance-artifact-extension').value =
                data.individual_settings.custom_artifact_extension || '';

            // Отображаем эффективный playbook path (групповой, если нет кастомного)
            const playbookInput = document.getElementById('instance-playbook-path');
            const customPlaybook = data.individual_settings.custom_playbook_path;
            const effectivePlaybook = data.effective_settings.playbook_path;
            const groupPlaybook = data.group_settings?.update_playbook_path;

            // Показываем эффективное значение
            playbookInput.value = effectivePlaybook || '';

            // Если используется групповой playbook (нет кастомного), добавляем визуальную индикацию
            if (!customPlaybook && effectivePlaybook) {
                playbookInput.style.fontStyle = 'italic';
                playbookInput.style.color = '#888';
                playbookInput.title = 'Используется playbook из настроек группы';
                playbookInput.setAttribute('data-from-group', 'true');
                playbookInput.setAttribute('data-group-playbook', groupPlaybook || '');
            } else {
                playbookInput.style.fontStyle = 'normal';
                playbookInput.style.color = '';
                playbookInput.title = '';
                playbookInput.removeAttribute('data-from-group');
                playbookInput.removeAttribute('data-group-playbook');
            }

            // Добавляем обработчик изменения поля для сброса визуальной индикации
            playbookInput.addEventListener('input', function() {
                if (this.getAttribute('data-from-group') === 'true') {
                    this.style.fontStyle = 'normal';
                    this.style.color = '';
                    this.title = 'Устанавливается кастомный playbook для экземпляра';
                }
            }, { once: true });
        }
    } catch (error) {
        console.error('Error loading instance settings:', error);
        // Если нет настроек экземпляра, показываем пустую форму
        const form = document.getElementById('instance-settings-form');
        form.style.display = 'block';
        document.getElementById('instance-artifact-url').value = '';
        document.getElementById('instance-artifact-extension').value = '';
        document.getElementById('instance-playbook-path').value = '';
    }
}

// Показать форму ручного назначения группы
function showManualGroupAssignment(app) {
    const assignmentSection = document.getElementById('manual-group-assignment');
    assignmentSection.style.display = 'block';
    
    // Заполняем форму данными приложения
    quickAssignGroup(app.id, app.name);
}

// Сохранение настроек группы
async function saveGroupSettings() {
    if (!selectedGroup) {
        showNotification('Выберите группу для редактирования', 'error');
        return;
    }
    
    const data = {
        artifact_list_url: document.getElementById('group-artifact-url').value || null,
        artifact_extension: document.getElementById('group-artifact-extension').value || null,
        update_playbook_path: document.getElementById('group-playbook-path').value || null
    };
    
    try {
        const response = await fetch(`/api/application-groups/${selectedGroup}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            let message = 'Настройки группы сохранены';
            if (result.updated_instances > 0) {
                message += `. Обновлено экземпляров: ${result.updated_instances}`;
            }
            showNotification(message, 'success');
            await loadAppGroupsData();
        } else {
            showNotification(result.error || 'Ошибка сохранения', 'error');
        }
    } catch (error) {
        console.error('Error saving group settings:', error);
        showNotification('Ошибка сохранения настроек', 'error');
    }
}

// Сохранение настроек экземпляра
async function saveInstanceSettings() {
    if (!selectedInstance) {
        showNotification('Выберите экземпляр приложения', 'error');
        return;
    }
    
    const data = {
        custom_artifact_list_url: document.getElementById('instance-artifact-url').value || null,
        custom_artifact_extension: document.getElementById('instance-artifact-extension').value || null,
        custom_playbook_path: document.getElementById('instance-playbook-path').value || null
    };
    
    try {
        const response = await fetch(`/api/applications/${selectedInstance}/instance-settings`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Настройки экземпляра сохранены', 'success');
            await loadAppGroupsData();
        } else {
            showNotification(result.error || 'Ошибка сохранения', 'error');
        }
    } catch (error) {
        console.error('Error saving instance settings:', error);
        showNotification('Ошибка сохранения настроек', 'error');
    }
}

// Загрузка приложений без группы
async function loadUngroupedApplications() {
    try {
        const response = await fetch('/api/applications/ungrouped');
        const data = await response.json();
        
        if (data.success) {
            ungroupedApps = data.applications;
            displayUngroupedApplications(ungroupedApps);
            
            // Обновляем список для ручного назначения
            updateManualAppSelect(ungroupedApps);
        }
    } catch (error) {
        console.error('Error loading ungrouped applications:', error);
    }
}

// Отображение приложений без группы
function displayUngroupedApplications(apps) {
    const container = document.getElementById('ungrouped-apps-container');
    const section = container.parentElement; // detail-section
    
    if (!apps || apps.length === 0) {
        // Скрываем весь раздел если нет приложений без группы
        section.style.display = 'none';
        document.getElementById('manual-group-assignment').style.display = 'none';
        return;
    }
    
    // Показываем раздел
    section.style.display = 'block';
    document.getElementById('manual-group-assignment').style.display = 'block';
    
    let html = '<div class="ungrouped-list">';
    apps.forEach(app => {
        html += `
            <div class="ungrouped-app-item">
                <div>
                    <div class="app-name">${app.name}</div>
                    <div class="app-info">Сервер: ${app.server_name}</div>
                </div>
                <button class="fix-group-btn" onclick="quickAssignGroup(${app.id}, '${app.name}')">
                    Назначить группу
                </button>
            </div>
        `;
    });
    html += '</div>';
    
    container.innerHTML = html;
}

// Обновление списка приложений для ручного назначения
function updateManualAppSelect(apps) {
    const select = document.getElementById('manual-app-select');
    
    let html = '<option value="">-- Выберите приложение --</option>';
    apps.forEach(app => {
        html += `<option value="${app.id}">${app.name} (${app.server_name})</option>`;
    });
    
    select.innerHTML = html;
}

// Быстрое назначение группы
function quickAssignGroup(appId, appName) {
    // Парсим имя для определения возможной группы
    const match = appName.match(/^(.+?)_(\d+)$/);
    let groupName = appName;
    let instanceNumber = 0;
    
    if (match) {
        groupName = match[1];
        instanceNumber = parseInt(match[2]);
    }
    
    // Заполняем форму
    document.getElementById('manual-app-select').value = appId;
    document.getElementById('manual-group-name').value = groupName;
    document.getElementById('manual-instance-number').value = instanceNumber;
    
    // Прокручиваем к форме
    document.getElementById('manual-group-assignment').scrollIntoView({ behavior: 'smooth' });
}

// Ручное назначение группы
async function assignGroupManually() {
    const appId = document.getElementById('manual-app-select').value;
    const groupName = document.getElementById('manual-group-name').value;
    const instanceNumber = parseInt(document.getElementById('manual-instance-number').value) || 0;
    
    if (!appId || !groupName) {
        showNotification('Выберите приложение и укажите группу', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/applications/${appId}/reassign-group`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                group_name: groupName,
                instance_number: instanceNumber,
                manual_assignment: true  // Флаг для предотвращения автоматической замены
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(result.message, 'success');
            
            // Очищаем форму
            document.getElementById('manual-app-select').value = '';
            document.getElementById('manual-group-name').value = '';
            document.getElementById('manual-instance-number').value = '0';
            
            // Перезагружаем данные
            await loadAppGroupsData();
        } else {
            showNotification(result.error || 'Ошибка назначения группы', 'error');
        }
    } catch (error) {
        console.error('Error assigning group:', error);
        showNotification('Ошибка назначения группы', 'error');
    }
}

// Загрузка статистики
async function loadStatistics() {
    try {
        const response = await fetch('/api/application-groups/statistics');
        const data = await response.json();
        
        if (data.success) {
            displayStatistics(data);
        }
    } catch (error) {
        console.error('Error loading statistics:', error);
    }
}

// Отображение статистики (упрощенная версия)
function displayStatistics(stats) {
    const container = document.getElementById('groups-statistics');
    
    let html = `
        <div class="stat-item">
            <div class="stat-label">Групп с настройками</div>
            <div class="stat-value">${stats.configured_groups}</div>
        </div>
        <div class="stat-item">
            <div class="stat-label">Кастомных настроек</div>
            <div class="stat-value">${stats.custom_artifacts_count}</div>
        </div>
        <div class="stat-item">
            <div class="stat-label">Без группы</div>
            <div class="stat-value ${stats.unresolved_instances > 0 ? 'warning' : ''}">${stats.unresolved_instances}</div>
        </div>
    `;
    
    container.innerHTML = html;
}

// Инициализация экземпляров для всех приложений
async function initializeInstances() {
    if (!confirm('Это создаст экземпляры для всех приложений, у которых их еще нет. Продолжить?')) {
        return;
    }
    
    const button = document.getElementById('init-instances-btn');
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Инициализация...';
    
    try {
        const response = await fetch('/api/application-groups/init-instances', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(
                `Инициализация завершена. Создано ${result.created_count} экземпляров из ${result.total_apps} приложений`, 
                'success'
            );
            
            // Перезагружаем данные
            await loadAppGroupsData();
            await updateAppGroupsStatus();
        } else {
            showNotification(result.error || 'Ошибка инициализации', 'error');
        }
    } catch (error) {
        console.error('Error initializing instances:', error);
        showNotification('Ошибка при инициализации экземпляров', 'error');
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
}

// Функция показа уведомлений
function showNotification(message, type = 'info') {
    // Удаляем предыдущие уведомления
    const existingNotifications = document.querySelectorAll('.notification-toast');
    existingNotifications.forEach(n => n.remove());
    
    // Создаем новое уведомление
    const notification = document.createElement('div');
    notification.className = `notification-toast notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            ${message}
        </div>
        <button class="notification-close">×</button>
    `;
    
    // Добавляем в body
    document.body.appendChild(notification);
    
    // Показываем с анимацией
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    // Автоматически скрываем через 5 секунд
    const hideTimeout = setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
    
    // Обработчик закрытия
    notification.querySelector('.notification-close').addEventListener('click', () => {
        clearTimeout(hideTimeout);
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    });
}

// Добавляем стили
const style = document.createElement('style');
style.textContent = `
    .status-dot.warning {
        background-color: #f39c12;
    }
    
    .status-dot.error {
        background-color: #e74c3c;
    }
    
    .custom-badge {
        background-color: #5ca5e1;
        color: white;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 11px;
        margin-left: 10px;
    }
    
    .groups-list {
        display: flex;
        flex-direction: column;
        gap: 5px;
    }
    
    .group-item {
        padding: 12px 15px;
        border-radius: 6px;
        border: 1px solid #333336;
        background-color: #2a2a2b;
        display: flex;
        align-items: center;
        gap: 10px;
        transition: all 0.2s;
    }
    
    body.light-theme .group-item {
        background-color: #f9f9f9;
        border-color: #ddd;
    }
    
    .group-item.clickable {
        cursor: pointer;
    }
    
    .group-item.clickable:hover {
        background-color: #3a3a3c;
        border-color: #5ca5e1;
    }
    
    body.light-theme .group-item.clickable:hover {
        background-color: #f0f0f0;
        border-color: #5ca5e1;
    }
    
    .group-item.selected {
        background-color: #3a3a3c;
        border-color: #5ca5e1;
        box-shadow: 0 0 0 2px rgba(92, 165, 225, 0.2);
    }
    
    body.light-theme .group-item.selected {
        background-color: #e8f4fd;
        border-color: #5ca5e1;
    }
    
    .group-item.no-group {
        background-color: rgba(243, 156, 18, 0.1);
        border-color: #f39c12;
    }
    
    .group-icon {
        font-size: 18px;
    }
    
    .group-name {
        flex: 1;
        font-weight: 500;
    }
    
    .group-count {
        color: #888;
        font-size: 14px;
    }
    
    .instance-item {
        padding: 10px 12px;
        margin-bottom: 5px;
        border-radius: 4px;
        border: 1px solid #333336;
        background-color: #252528;
        cursor: pointer;
        transition: all 0.2s;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    body.light-theme .instance-item {
        background-color: #fff;
        border-color: #e0e0e0;
    }
    
    .instance-item:hover {
        background-color: #2e2e30;
        border-color: #5ca5e1;
    }
    
    body.light-theme .instance-item:hover {
        background-color: #f5f5f5;
    }
    
    .instance-item.selected {
        background-color: #3a3a3c;
        border-color: #5ca5e1;
        box-shadow: 0 0 0 2px rgba(92, 165, 225, 0.2);
    }
    
    body.light-theme .instance-item.selected {
        background-color: #e8f4fd;
        border-color: #5ca5e1;
    }
    
    .instance-main {
        flex: 1;
    }
    
    .instance-name {
        font-weight: 500;
        margin-bottom: 4px;
    }
    
    .instance-info {
        font-size: 12px;
        color: #888;
    }
    
    body.light-theme .instance-info {
        color: #666;
    }
    
    .instance-icon {
        margin-right: 5px;
    }
    
    .status-badge {
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 11px;
        text-transform: uppercase;
    }
    
    .status-badge.online {
        background-color: rgba(46, 204, 113, 0.2);
        color: #2ecc71;
    }
    
    .status-badge.offline {
        background-color: rgba(231, 76, 60, 0.2);
        color: #e74c3c;
    }
    
    .detail-subsection {
        margin-bottom: 20px;
    }
    
    .detail-subsection h6 {
        margin-bottom: 10px;
        color: #aaa;
        font-size: 13px;
        text-transform: uppercase;
    }
    
    body.light-theme .detail-subsection h6 {
        color: #666;
    }
    
    .warning {
        color: #f39c12;
        padding: 10px;
        background-color: rgba(243, 156, 18, 0.1);
        border-radius: 4px;
    }
    
    .success {
        color: #2ecc71;
        padding: 10px;
        background-color: rgba(46, 204, 113, 0.1);
        border-radius: 4px;
    }
    
    .no-data {
        color: #888;
        padding: 20px;
        text-align: center;
    }
    
    .stat-value.warning {
        color: #f39c12;
    }
`;
document.head.appendChild(style);
/**
 * element-factory.js
 * Фабрика для создания DOM элементов таблицы приложений
 * Извлечено из UIRenderer для улучшения поддержки кода
 */
(function() {
    'use strict';

    const ElementFactory = {
        /**
         * Создает элемент строки приложения
         * @param {Object} app - данные приложения
         * @param {string|null} groupName - имя группы (если приложение в группе)
         * @param {Object} callbacks - колбэки для рендеринга (renderTagsWithInherited)
         */
        createAppElement(app, groupName = null, callbacks = {}) {
            const { renderTagsWithInherited = () => '' } = callbacks;

            // Контейнер строки
            const row = document.createElement('div');
            row.className = 'apps-row';
            row.setAttribute('data-app-id', app.id);
            row.setAttribute('data-app-name', (app.name || '').toLowerCase());
            if (groupName) {
                row.setAttribute('data-parent', groupName);
            }

            // Header (grid с колонками)
            const header = document.createElement('div');
            header.className = 'apps-row-header';

            // 1. Колонка чекбокса
            const checkboxCol = this._createCheckboxColumn(app.id, 'app-checkbox');

            // 2. Колонка имени
            const nameCol = document.createElement('div');
            nameCol.className = 'apps-col apps-col-name';
            const nameContainer = document.createElement('div');
            nameContainer.className = 'apps-name-with-tags';
            const nameText = document.createElement('span');
            nameText.textContent = app.name || '';
            nameContainer.appendChild(nameText);

            // Теги рядом с именем
            const tagsContainer = document.createElement('span');
            tagsContainer.className = 'apps-inline-tags';
            tagsContainer.innerHTML = renderTagsWithInherited(app.tags || [], app.group_tags || []);
            nameContainer.appendChild(tagsContainer);
            nameCol.appendChild(nameContainer);

            // 3. Колонка версии
            const versionCol = document.createElement('div');
            versionCol.className = 'apps-col apps-col-version';
            versionCol.textContent = app.version || 'Н/Д';

            // 4. Колонка статуса
            const statusCol = this._createStatusColumn(app.status);

            // 5. Колонка сервера
            const serverCol = document.createElement('div');
            serverCol.className = 'apps-col apps-col-server';
            serverCol.textContent = app.server_name || 'Н/Д';

            // 6. Колонка действий
            const actionsCol = document.createElement('div');
            actionsCol.className = 'apps-col apps-col-actions';
            actionsCol.innerHTML = this.createActionsMenu(app);

            // Собираем header (grid)
            header.appendChild(checkboxCol);
            header.appendChild(nameCol);
            header.appendChild(versionCol);
            header.appendChild(statusCol);
            header.appendChild(serverCol);
            header.appendChild(actionsCol);

            // Детали (сворачиваемые) - под header
            const details = document.createElement('div');
            details.className = 'apps-details';
            details.innerHTML = `
                <div class="apps-details-content">
                    <div>Время запуска: ${app.start_time ? new Date(app.start_time).toLocaleString() : 'Н/Д'}</div>
                    <div>Путь приложения: ${app.path || 'Н/Д'}</div>
                </div>
            `;

            // Собираем строку (контейнер)
            row.appendChild(header);
            row.appendChild(details);

            return row;
        },

        /**
         * Создает элемент заголовка группы
         * @param {string} groupName - имя группы
         * @param {Array} apps - приложения в группе
         * @param {Object} callbacks - колбэки для рендеринга (renderTags)
         */
        createGroupElement(groupName, apps, callbacks = {}) {
            const { renderTags = () => '' } = callbacks;

            const header = document.createElement('div');
            header.className = 'apps-group-header';

            // Колонка чекбокса
            const checkboxCol = this._createGroupCheckboxColumn(groupName);

            // Колонка имени группы
            const nameCol = document.createElement('div');
            nameCol.className = 'apps-col apps-col-name';
            const nameContainer = document.createElement('div');
            nameContainer.className = 'apps-group-name-container';
            const toggle = document.createElement('span');
            toggle.className = 'apps-group-toggle';
            toggle.textContent = '▶';
            const nameSpan = document.createElement('span');
            nameSpan.className = 'apps-group-name';
            nameSpan.textContent = `${groupName} (${apps.length})`;
            nameContainer.appendChild(toggle);
            nameContainer.appendChild(nameSpan);

            // Теги группы рядом с именем
            const groupTags = apps[0]?.group_tags || [];
            if (groupTags.length > 0) {
                const tagsContainer = document.createElement('span');
                tagsContainer.className = 'apps-inline-tags';
                tagsContainer.innerHTML = renderTags(groupTags);
                nameContainer.appendChild(tagsContainer);
            }
            nameCol.appendChild(nameContainer);

            // Колонка версии
            const versionCol = document.createElement('div');
            versionCol.className = 'apps-col apps-col-version';
            const versions = new Set(apps.map(app => app.version || 'Н/Д'));
            if (versions.size === 1) {
                versionCol.textContent = apps[0].version || 'Н/Д';
            } else {
                versionCol.innerHTML = '<span class="apps-version-different">*</span>';
            }

            // Колонка статуса
            const statusCol = document.createElement('div');
            statusCol.className = 'apps-col apps-col-status';
            const hasOffline = apps.some(app => app.status === 'offline');
            const hasNoData = apps.some(app => app.status === 'no_data' || app.status === 'unknown');
            const hasProblems = hasOffline || hasNoData;
            const statusDot = document.createElement('span');
            statusDot.className = hasProblems ? 'apps-status-dot warning' : 'apps-status-dot';
            statusCol.appendChild(statusDot);

            // Колонка сервера
            const serverCol = document.createElement('div');
            serverCol.className = 'apps-col apps-col-server';
            serverCol.textContent = '—';

            // Колонка действий
            const actionsCol = document.createElement('div');
            actionsCol.className = 'apps-col apps-col-actions';
            actionsCol.innerHTML = this.createGroupActionsMenu(groupName, apps);

            // Собираем header
            header.appendChild(checkboxCol);
            header.appendChild(nameCol);
            header.appendChild(versionCol);
            header.appendChild(statusCol);
            header.appendChild(serverCol);
            header.appendChild(actionsCol);

            return header;
        },

        /**
         * Создает меню действий для приложения
         */
        createActionsMenu(app) {
            const appId = parseInt(app.id, 10);

            return `
                <div class="actions-menu">
                    <button class="actions-button">...</button>
                    <div class="actions-dropdown">
                        <a href="#" class="app-info-btn" data-app-id="${appId}">Информация</a>
                        <a href="#" class="app-start-btn ${app.status === 'online' ? 'disabled' : ''}" data-app-id="${appId}">Запустить</a>
                        <a href="#" class="app-stop-btn ${app.status !== 'online' ? 'disabled' : ''}" data-app-id="${appId}">Остановить</a>
                        <a href="#" class="app-restart-btn ${app.status !== 'online' ? 'disabled' : ''}" data-app-id="${appId}">Перезапустить</a>
                        <a href="#" class="app-update-btn" data-app-id="${appId}">Обновить</a>
                    </div>
                </div>
            `;
        },

        /**
         * Создает меню действий для группы
         */
        createGroupActionsMenu(groupName, apps) {
            const hasOnline = apps.some(app => app.status === 'online');
            const hasOffline = apps.some(app => app.status !== 'online');
            const groupId = apps[0]?.group_id || '';

            return `
                <div class="actions-menu">
                    <button class="actions-button">...</button>
                    <div class="actions-dropdown">
                        <a href="#" class="group-info-btn" data-group="${groupName}">Информация</a>
                        <a href="#" class="group-tags-btn" data-group="${groupName}" data-group-id="${groupId}">Теги</a>
                        <a href="#" class="group-start-btn ${!hasOffline ? 'disabled' : ''}" data-group="${groupName}">Запустить все</a>
                        <a href="#" class="group-stop-btn ${!hasOnline ? 'disabled' : ''}" data-group="${groupName}">Остановить все</a>
                        <a href="#" class="group-restart-btn ${!hasOnline ? 'disabled' : ''}" data-group="${groupName}">Перезапустить все</a>
                        <a href="#" class="group-update-btn" data-group="${groupName}">Обновить все</a>
                    </div>
                </div>
            `;
        },

        /**
         * Создает колонку чекбокса для приложения
         * @private
         */
        _createCheckboxColumn(appId, className) {
            const checkboxCol = document.createElement('div');
            checkboxCol.className = 'apps-col apps-col-checkbox';
            const checkboxContainer = document.createElement('div');
            checkboxContainer.className = 'apps-checkbox-container';
            const checkboxLabel = document.createElement('label');
            checkboxLabel.className = 'apps-custom-checkbox';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = className;
            checkbox.setAttribute('data-app-id', appId);
            const checkmark = document.createElement('span');
            checkmark.className = 'apps-checkmark';
            checkboxLabel.appendChild(checkbox);
            checkboxLabel.appendChild(checkmark);
            checkboxContainer.appendChild(checkboxLabel);
            checkboxCol.appendChild(checkboxContainer);
            return checkboxCol;
        },

        /**
         * Создает колонку чекбокса для группы
         * @private
         */
        _createGroupCheckboxColumn(groupName) {
            const checkboxCol = document.createElement('div');
            checkboxCol.className = 'apps-col apps-col-checkbox';
            const checkboxContainer = document.createElement('div');
            checkboxContainer.className = 'apps-checkbox-container';
            const checkboxLabel = document.createElement('label');
            checkboxLabel.className = 'apps-custom-checkbox';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'group-checkbox';
            checkbox.dataset.group = groupName;
            const checkmark = document.createElement('span');
            checkmark.className = 'apps-checkmark';
            checkboxLabel.appendChild(checkbox);
            checkboxLabel.appendChild(checkmark);
            checkboxContainer.appendChild(checkboxLabel);
            checkboxCol.appendChild(checkboxContainer);
            return checkboxCol;
        },

        /**
         * Создает колонку статуса
         * @private
         */
        _createStatusColumn(status) {
            const statusCol = document.createElement('div');
            statusCol.className = 'apps-col apps-col-status';
            const statusDot = document.createElement('span');
            let statusText;

            if (status === 'no_data' || status === 'unknown') {
                statusDot.className = 'apps-status-dot no-data';
                statusText = 'Н/Д';
            } else if (status === 'online') {
                statusDot.className = 'apps-status-dot';
                statusText = status;
            } else {
                statusDot.className = 'apps-status-dot offline';
                statusText = status || 'offline';
            }

            statusCol.appendChild(statusDot);
            const statusTextNode = document.createTextNode(` ${statusText}`);
            statusCol.appendChild(statusTextNode);

            return statusCol;
        }
    };

    // Экспорт в глобальную область
    window.ElementFactory = ElementFactory;
})();

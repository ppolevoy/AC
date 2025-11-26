/**
 * info-modal.js
 * Модуль для отображения информации о приложении
 * Компактная версия с вкладками
 */
(function() {
    'use strict';

    const InfoModal = {
        /**
         * Показывает модальное окно с информацией о приложении
         * @param {number} appId - ID приложения
         * @param {Object} deps - зависимости
         */
        async show(appId, deps = {}) {
            const {
                ApiService = window.ApiService,
                showError = window.showError,
                showModal = window.showModal
            } = deps;

            const app = await ApiService.getApplicationInfo(appId);
            if (!app) {
                showError('Не удалось получить информацию о приложении');
                return;
            }

            const content = this._buildModalContent(app);
            showModal(`Информация о приложении: ${app.name}`, content);

            // Инициализируем переключение вкладок после показа модала
            this._initTabs();
        },

        /**
         * Строит содержимое модального окна
         * @private
         */
        _buildModalContent(app) {
            const container = document.createElement('div');
            container.className = 'app-info-modal';

            // Вкладки
            container.innerHTML = `
                <div class="info-tabs">
                    <div class="info-tab active" data-tab="info">Основная информация</div>
                    <div class="info-tab" data-tab="events">Последние события</div>
                    <div class="info-tab" data-tab="tags">Теги</div>
                </div>
                <div class="info-tab-contents">
                    ${this._buildInfoTab(app)}
                    ${this._buildEventsTab(app)}
                    ${this._buildTagsTab(app)}
                </div>
            `;

            return container;
        },

        /**
         * Вкладка основной информации
         * @private
         */
        _buildInfoTab(app) {
            const statusClass = this._getStatusClass(app.status);
            const statusText = app.status || 'Неизвестно';

            // Форматируем время запуска
            const startTime = app.start_time
                ? new Date(app.start_time).toLocaleString('ru-RU')
                : 'Не указано';

            // Проверяем, запущено ли в Docker
            const isDocker = app.container_id || app.container_name || app.app_type === 'docker';

            return `
                <div class="info-tab-content active" data-content="info">
                    <div class="info-columns">
                        <div class="info-column">
                            <div class="info-field">
                                <div class="info-label">Имя</div>
                                <div class="info-value">${this._escape(app.name)}</div>
                            </div>
                            <div class="info-field">
                                <div class="info-label">Статус</div>
                                <div class="info-value">
                                    <span class="status-badge ${statusClass}">${statusText}</span>
                                </div>
                            </div>
                            <div class="info-field">
                                <div class="info-label">Версия</div>
                                <div class="info-value">${this._escape(app.version) || 'Не указана'}</div>
                            </div>
                            <div class="info-field">
                                <div class="info-label">Тип</div>
                                <div class="info-value">${this._escape(app.app_type) || 'Не указан'}</div>
                            </div>
                        </div>
                        <div class="info-column">
                            <div class="info-field">
                                <div class="info-label">Время запуска</div>
                                <div class="info-value">${startTime}</div>
                            </div>
                            <div class="info-field">
                                <div class="info-label">Сервер</div>
                                <div class="info-value">${this._escape(app.server_name) || 'Не указан'}</div>
                            </div>
                            <div class="info-field">
                                <div class="info-label">IP:Port</div>
                                <div class="info-value">${this._escape(app.ip) || '—'}:${app.port || '—'}</div>
                            </div>
                        </div>
                    </div>

                    ${isDocker ? this._buildDockerSection(app) : ''}

                    <div class="paths-section">
                        <div class="paths-title">
                            <span>📁</span>
                            Пути и расположение
                        </div>
                        <div class="paths-grid">
                            ${this._buildPathItem('Путь приложения', app.path)}
                            ${this._buildPathItem('Путь к логам', app.log_path)}
                            ${this._buildPathItem('Путь к дистрибутиву', app.distr_path)}
                        </div>
                    </div>
                </div>
            `;
        },

        /**
         * Строит секцию Docker информации
         * @private
         */
        _buildDockerSection(app) {
            // Сокращаем Container ID до 12 символов (как в Docker CLI)
            const shortContainerId = app.container_id
                ? app.container_id.substring(0, 12)
                : null;
            const fullContainerId = app.container_id || '';

            return `
                <div class="docker-section">
                    <div class="docker-title">
                        <span>🐳</span>
                        Docker контейнер
                    </div>
                    <div class="docker-grid">
                        <div class="docker-field">
                            <div class="docker-label">Имя контейнера</div>
                            <div class="docker-value">${this._escape(app.container_name) || 'Не указано'}</div>
                        </div>
                        <div class="docker-field">
                            <div class="docker-label">Container ID</div>
                            ${shortContainerId ? `
                            <div class="docker-id-container">
                                <span class="docker-id" title="${this._escape(fullContainerId)}">${shortContainerId}</span>
                                <button class="copy-btn" onclick="InfoModal.copyToClipboard('${this._escape(fullContainerId)}')">📋</button>
                            </div>
                            ` : '<div class="docker-value">Не указан</div>'}
                        </div>
                        ${app.compose_project_dir ? `
                        <div class="docker-field docker-field-wide">
                            <div class="docker-label">Docker Compose проект</div>
                            <div class="path-container">
                                <span class="path-text" title="${this._escape(app.compose_project_dir)}">${this._escape(app.compose_project_dir)}</span>
                                <button class="copy-btn" onclick="InfoModal.copyToClipboard('${this._escape(app.compose_project_dir)}')">📋</button>
                            </div>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
        },

        /**
         * Строит элемент пути с кнопкой копирования
         * @private
         */
        _buildPathItem(label, path) {
            const value = path || 'Не указан';
            const escaped = this._escape(value);

            return `
                <div class="path-item">
                    <div class="path-label">${label}</div>
                    <div class="path-container">
                        <span class="path-text" title="${escaped}">${escaped}</span>
                        ${path ? `<button class="copy-btn" onclick="InfoModal.copyToClipboard('${escaped}')">📋</button>` : ''}
                    </div>
                </div>
            `;
        },

        /**
         * Вкладка событий
         * @private
         */
        _buildEventsTab(app) {
            const events = app.events || [];

            if (events.length === 0) {
                return `
                    <div class="info-tab-content" data-content="events">
                        <div class="no-data">Нет событий</div>
                    </div>
                `;
            }

            const rows = events.map(event => {
                const eventDate = new Date(event.timestamp).toLocaleString('ru-RU');
                const statusClass = this._getEventStatusClass(event.status);

                return `
                    <tr>
                        <td>${eventDate}</td>
                        <td>${this._escape(event.event_type)}</td>
                        <td><span class="event-status ${statusClass}">${this._escape(event.status)}</span></td>
                    </tr>
                `;
            }).join('');

            return `
                <div class="info-tab-content" data-content="events">
                    <table class="events-table">
                        <thead>
                            <tr>
                                <th style="width: 160px;">Дата</th>
                                <th style="width: 100px;">Тип</th>
                                <th style="width: 100px;">Статус</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows}
                        </tbody>
                    </table>
                </div>
            `;
        },

        /**
         * Вкладка тегов
         * @private
         */
        _buildTagsTab(app) {
            const ownTags = app.tags || [];
            const groupTags = app.group_tags || [];

            if (ownTags.length === 0 && groupTags.length === 0) {
                return `
                    <div class="info-tab-content" data-content="tags">
                        <div class="no-data">Нет тегов</div>
                    </div>
                `;
            }

            let content = '<div class="info-tab-content" data-content="tags">';

            // Собственные теги
            if (ownTags.length > 0) {
                content += `
                    <div class="tags-section-title">Собственные теги</div>
                    <div class="tags-container">
                        ${ownTags.map(tag => this._buildTagItem(tag)).join('')}
                    </div>
                `;
            }

            // Унаследованные теги от группы
            if (groupTags.length > 0) {
                content += `
                    <div class="tags-section-title" style="margin-top: 16px;">Унаследованные от группы</div>
                    <div class="tags-container">
                        ${groupTags.map(tag => this._buildTagItem(tag, true)).join('')}
                    </div>
                `;
            }

            content += '</div>';
            return content;
        },

        /**
         * Строит элемент тега
         * @private
         */
        _buildTagItem(tag, inherited = false) {
            const style = [];
            if (tag.border_color) style.push(`border-color: ${tag.border_color}`);
            if (tag.text_color) style.push(`color: ${tag.text_color}`);
            const styleAttr = style.length ? `style="${style.join('; ')}"` : '';
            const inheritedClass = inherited ? 'tag-inherited' : '';

            return `
                <div class="tag-item ${inheritedClass}" ${styleAttr}>
                    <span class="tag-name">${this._escape(tag.display_name || tag.name)}</span>
                </div>
            `;
        },

        /**
         * Инициализация переключения вкладок
         * @private
         */
        _initTabs() {
            const tabs = document.querySelectorAll('.info-tab');
            const contents = document.querySelectorAll('.info-tab-content');

            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    const targetTab = tab.dataset.tab;

                    tabs.forEach(t => t.classList.remove('active'));
                    contents.forEach(c => c.classList.remove('active'));

                    tab.classList.add('active');
                    document.querySelector(`.info-tab-content[data-content="${targetTab}"]`)?.classList.add('active');
                });
            });
        },

        /**
         * Копирование в буфер обмена
         */
        copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                window.showNotification?.('Скопировано в буфер обмена', 'success') ||
                    console.log('Скопировано:', text);
            }).catch(err => {
                console.error('Ошибка копирования:', err);
            });
        },

        /**
         * Получает CSS класс для статуса приложения
         * @private
         */
        _getStatusClass(status) {
            switch (status?.toLowerCase()) {
                case 'online':
                    return 'status-online';
                case 'offline':
                case 'stopped':
                    return 'status-offline';
                case 'no_data':
                case 'unknown':
                default:
                    return 'status-no-data';
            }
        },

        /**
         * Получает CSS класс для статуса события
         * @private
         */
        _getEventStatusClass(status) {
            switch (status?.toLowerCase()) {
                case 'completed':
                case 'done':
                case 'success':
                    return 'completed';
                case 'failed':
                case 'error':
                    return 'failed';
                case 'pending':
                case 'running':
                case 'in_progress':
                default:
                    return 'pending';
            }
        },

        /**
         * Экранирование HTML
         * @private
         */
        _escape(text) {
            if (text == null) return '';
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return String(text).replace(/[&<>"']/g, char => map[char]);
        }
    };

    // Экспорт в глобальную область
    window.InfoModal = InfoModal;
})();

/**
 * table-actions.js
 * Модуль для обработки действий в таблице приложений
 * Извлечено из EventHandlers для улучшения поддержки кода
 */
(function() {
    'use strict';

    const TableActions = {
        /**
         * Инициализация обработчиков действий в таблице
         * @param {Object} deps - зависимости
         */
        init(deps = {}) {
            const {
                ModalManager = window.ModalManager,
                DropdownHandlers = window.DropdownHandlers,
                showError = window.showError
            } = deps;

            this.ModalManager = ModalManager;
            this.DropdownHandlers = DropdownHandlers;
            this.showError = showError;

            this._initClickHandlers();
        },

        /**
         * Устанавливает колбэки для действий
         * @param {Object} callbacks
         */
        setCallbacks(callbacks = {}) {
            this.onShowAppInfo = callbacks.showAppInfo || (() => {});
            this.onShowGroupTagsModal = callbacks.showGroupTagsModal || (() => {});
            this.onHandleBatchAction = callbacks.handleBatchAction || (() => {});
            this.onHandleGroupUpdate = callbacks.handleGroupUpdate || (() => {});
            this.onHandleGroupAction = callbacks.handleGroupAction || (() => {});
        },

        /**
         * Инициализация обработчиков кликов (делегирование)
         * @private
         */
        _initClickHandlers() {
            document.addEventListener('click', (e) => {
                const isMenuAction = e.target.closest('.actions-dropdown a');

                // Обработчики действий для приложений
                if (e.target.classList.contains('app-info-btn')) {
                    e.preventDefault();
                    const appId = e.target.dataset.appId;
                    this.onShowAppInfo(appId);
                }

                if (e.target.classList.contains('app-update-btn')) {
                    e.preventDefault();
                    const appId = e.target.dataset.appId;
                    this.ModalManager.showUpdateModal([appId]);
                }

                // Обработчики действий для групп
                if (e.target.classList.contains('group-update-btn')) {
                    e.preventDefault();
                    const groupName = e.target.dataset.group;
                    this.onHandleGroupUpdate(groupName);
                }

                if (e.target.classList.contains('group-tags-btn')) {
                    e.preventDefault();
                    const groupId = e.target.dataset.groupId;
                    const groupName = e.target.dataset.group;
                    if (groupId) {
                        this.onShowGroupTagsModal(groupId, groupName);
                    } else {
                        this.showError('Группа не найдена');
                    }
                }

                // Действия start/stop/restart
                ['start', 'stop', 'restart'].forEach(action => {
                    if (e.target.classList.contains(`app-${action}-btn`)) {
                        e.preventDefault();
                        if (!e.target.classList.contains('disabled')) {
                            const appId = e.target.dataset.appId;
                            this.onHandleBatchAction([appId], action);
                        }
                    }

                    if (e.target.classList.contains(`group-${action}-btn`)) {
                        e.preventDefault();
                        if (!e.target.classList.contains('disabled')) {
                            const groupName = e.target.dataset.group;
                            this.onHandleGroupAction(groupName, action);
                        }
                    }
                });

                // Закрываем меню после клика на любой пункт
                if (isMenuAction) {
                    setTimeout(() => this.DropdownHandlers.closeAll(), 100);
                }
            });
        },

        /**
         * Получает ID приложений из группы
         */
        getGroupAppIds(groupName) {
            const appIds = [];
            document.querySelectorAll(`.apps-group[data-group="${groupName}"] .apps-group-children .app-checkbox`).forEach(checkbox => {
                appIds.push(checkbox.dataset.appId);
            });
            return appIds;
        }
    };

    // Экспорт в глобальную область
    window.TableActions = TableActions;
})();

/**
 * checkbox-handlers.js
 * Модуль для управления чекбоксами выбора приложений
 * Извлечено из EventHandlers для улучшения поддержки кода
 */
(function() {
    'use strict';

    const CheckboxHandlers = {
        /**
         * Инициализация обработчиков чекбоксов
         * @param {Object} deps - зависимости
         */
        init(deps = {}) {
            const {
                StateManager = window.StateManager,
                DOMUtils = window.DOMUtils,
                UIRenderer = window.UIRenderer
            } = deps;

            this._initSelectAll(StateManager, DOMUtils, UIRenderer);
            this._initAppCheckboxes(StateManager, UIRenderer);
            this._initGroupCheckboxes(StateManager, UIRenderer);
        },

        /**
         * Инициализация чекбокса "выбрать все"
         * @private
         */
        _initSelectAll(StateManager, DOMUtils, UIRenderer) {
            const selectAllCheckbox = document.getElementById('select-all');
            if (!selectAllCheckbox) return;

            selectAllCheckbox.addEventListener('change', function() {
                const isChecked = this.checked;

                // Используем контекст таблицы
                DOMUtils.querySelectorInTable('.app-checkbox').forEach(checkbox => {
                    checkbox.checked = isChecked;
                    const appId = checkbox.dataset.appId;
                    if (appId) {
                        if (isChecked) {
                            StateManager.addSelectedApp(appId);
                        } else {
                            StateManager.removeSelectedApp(appId);
                        }
                    }
                });

                // Обновляем групповые чекбоксы
                DOMUtils.querySelectorInTable('.group-checkbox').forEach(checkbox => {
                    checkbox.checked = isChecked;
                    checkbox.indeterminate = false;
                });

                UIRenderer.updateActionButtonsState(StateManager.state.selectedItems.applications.size > 0);
            });
        },

        /**
         * Инициализация чекбоксов приложений (делегирование)
         * @private
         */
        _initAppCheckboxes(StateManager, UIRenderer) {
            document.addEventListener('change', (e) => {
                if (!e.target.classList.contains('app-checkbox')) return;

                const appId = e.target.dataset.appId;
                if (e.target.checked) {
                    StateManager.addSelectedApp(appId);
                } else {
                    StateManager.removeSelectedApp(appId);
                }

                const hasSelection = StateManager.state.selectedItems.applications.size > 0;
                UIRenderer.updateActionButtonsState(hasSelection);

                // Обновляем состояние "выбрать все"
                UIRenderer.updateSelectAllState();

                // Обновляем состояние группового чекбокса
                const parentGroup = e.target.closest('.apps-group')?.dataset.group;
                if (parentGroup) {
                    UIRenderer.updateGroupCheckbox(parentGroup);
                }
            });
        },

        /**
         * Инициализация групповых чекбоксов (делегирование)
         * @private
         */
        _initGroupCheckboxes(StateManager, UIRenderer) {
            document.addEventListener('change', (e) => {
                if (!e.target.classList.contains('group-checkbox')) return;

                const groupName = e.target.dataset.group;
                const isChecked = e.target.checked;

                // Выбираем/снимаем выбор со всех приложений группы
                document.querySelectorAll(`.apps-group[data-group="${groupName}"] .apps-group-children .app-checkbox`).forEach(checkbox => {
                    checkbox.checked = isChecked;
                    const appId = checkbox.dataset.appId;
                    if (isChecked) {
                        StateManager.addSelectedApp(appId);
                    } else {
                        StateManager.removeSelectedApp(appId);
                    }
                });

                // Обновляем состояние "выбрать все"
                UIRenderer.updateSelectAllState();

                const hasSelection = StateManager.state.selectedItems.applications.size > 0;
                UIRenderer.updateActionButtonsState(hasSelection);
            });
        }
    };

    // Экспорт в глобальную область
    window.CheckboxHandlers = CheckboxHandlers;
})();

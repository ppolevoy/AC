/**
 * state-manager.js
 * Модуль управления состоянием приложения
 */
(function() {
    'use strict';

    const StateManager = {
        /**
         * Инициализация с конфигурацией
         * @param {Object} config - конфигурация
         */
        init(config = {}) {
            const pageSize = config.pageSize || window.CONFIG?.PAGE_SIZE || 10;
            this.state.pageSize = pageSize;
        },

        // Основное состояние приложения
        state: {
            allApplications: [],
            selectedItems: {
                applications: new Set(),
                groups: new Set()
            },
            expandedGroups: [],
            selectedServerId: 'all',
            currentPage: 1,
            pageSize: 10, // default, будет обновлено в init()
            sortColumn: 'name',
            sortDirection: 'asc',
            searchQuery: '',
            groupingEnabled: false,
            selectedTags: [],
            tagOperator: 'OR',
            availableTags: [],
            statusFilter: 'all' // Фильтр по статусу: all, online, offline, disabled, candidates
        },

        // Кэш артефактов
        artifactsCache: {},

        // Активное выпадающее меню
        activeDropdown: null,

        /**
         * Очищает выбранные элементы
         */
        clearSelection() {
            this.state.selectedItems.applications.clear();
            this.state.selectedItems.groups.clear();
        },

        /**
         * Добавляет приложение в выбранные
         * @param {string|number} appId
         */
        addSelectedApp(appId) {
            this.state.selectedItems.applications.add(appId);
        },

        /**
         * Удаляет приложение из выбранных
         * @param {string|number} appId
         */
        removeSelectedApp(appId) {
            this.state.selectedItems.applications.delete(appId);
        },

        /**
         * Проверяет, выбрано ли приложение
         * @param {string|number} appId
         * @returns {boolean}
         */
        isAppSelected(appId) {
            return this.state.selectedItems.applications.has(appId);
        },

        /**
         * Возвращает массив ID выбранных приложений
         * @returns {Array}
         */
        getSelectedAppIds() {
            return Array.from(this.state.selectedItems.applications);
        },

        /**
         * Находит приложение по ID
         * @param {string|number} appId
         * @returns {Object|undefined}
         */
        getAppById(appId) {
            return this.state.allApplications.find(app => app.id == appId);
        },

        /**
         * Очищает кэш артефактов
         * @param {string|number|null} appId - ID приложения или null для очистки всего кэша
         */
        clearArtifactsCache(appId = null) {
            if (appId) {
                delete this.artifactsCache[`app_${appId}`];
            } else {
                this.artifactsCache = {};
            }
        },

        /**
         * Получает возраст кэша артефактов в секундах
         * @param {string|number} appId
         * @returns {number}
         */
        getArtifactsCacheAge(appId) {
            const cacheKey = `app_${appId}`;
            if (this.artifactsCache[cacheKey]) {
                return (Date.now() - this.artifactsCache[cacheKey].timestamp) / 1000;
            }
            return Infinity;
        },

        /**
         * Сохраняет состояние развернутых групп
         */
        saveTableState() {
            this.state.expandedGroups = [];
            document.querySelectorAll('.apps-group.expanded').forEach(group => {
                const groupName = group.getAttribute('data-group');
                if (groupName) {
                    this.state.expandedGroups.push(groupName);
                }
            });
        }
    };

    // Экспорт в глобальную область
    window.StateManager = StateManager;
})();

/**
 * artifacts-manager.js
 * Модуль для работы с артефактами приложений
 */
(function() {
    'use strict';

    const ArtifactsManager = {
        /**
         * Инициализация с зависимостями
         * @param {Object} deps - зависимости
         */
        init(deps = {}) {
            this._StateManager = deps.StateManager || window.StateManager;
            this._ApiService = deps.ApiService || window.ApiService;
            this._config = deps.config || window.CONFIG || {
                CACHE_LIFETIME: 5 * 60 * 1000,
                MAX_ARTIFACTS_DISPLAY: 20
            };
        },

        /**
         * Загружает артефакты с кэшированием
         * @param {string|number} appId - ID приложения
         * @param {boolean} showProgress - показывать прогресс
         * @returns {Promise<Array|null>}
         */
        async loadWithCache(appId, showProgress = false) {
            const stateManager = this._StateManager || window.StateManager;
            const apiService = this._ApiService || window.ApiService;
            const config = this._config || window.CONFIG;

            const now = Date.now();
            const cacheKey = `app_${appId}`;
            const cache = stateManager.artifactsCache[cacheKey];

            // Проверяем кэш
            if (cache && (now - cache.timestamp) < config.CACHE_LIFETIME) {
                return cache.data;
            }

            // Загружаем свежие данные
            const artifacts = await apiService.loadArtifacts(appId, config.MAX_ARTIFACTS_DISPLAY, showProgress);
            if (artifacts && artifacts.length > 0) {
                stateManager.artifactsCache[cacheKey] = {
                    timestamp: now,
                    data: artifacts
                };
                return artifacts;
            }

            return null;
        },

        /**
         * Создает HTML-опции для селекта версий
         * @param {Array} artifacts - массив артефактов
         * @param {string} currentValue - текущее значение
         * @returns {string} HTML строка с options
         */
        createVersionSelect(artifacts, currentValue) {
            if (!artifacts || artifacts.length === 0) {
                return '<option value="">Нет доступных версий</option>';
            }

            const options = artifacts.map(version => {
                let label = version.version;
                let className = '';
                const versionLower = version.version.toLowerCase();

                if (versionLower.includes('snapshot')) {
                    className = 'version-snapshot';
                } else if (versionLower.includes('dev')) {
                    className = 'version-dev';
                } else if (version.is_release) {
                    className = 'version-release';
                }

                const selected = version.url === currentValue ? 'selected' : '';
                return `<option value="${version.url}" class="${className}" ${selected}>${label}</option>`;
            }).join('');

            return options + '<option value="custom" class="custom-option">➕ Указать вручную...</option>';
        }
    };

    // Экспорт в глобальную область
    window.ArtifactsManager = ArtifactsManager;
})();

/**
 * api-service.js
 * Модуль для работы с API
 */
(function() {
    'use strict';

    const ApiService = {
        /**
         * Инициализация с зависимостями
         * @param {Object} deps - зависимости
         */
        init(deps = {}) {
            this._showError = deps.showError || window.showError || console.error;
            this._config = deps.config || window.CONFIG || { MAX_ARTIFACTS_DISPLAY: 20 };
        },

        /**
         * Загружает список серверов
         * @returns {Promise<Array>}
         */
        async loadServers() {
            try {
                const response = await fetch('/api/servers');
                const data = await response.json();
                return data.success ? data.servers : [];
            } catch (error) {
                console.error('Ошибка загрузки серверов:', error);
                this._showError('Не удалось загрузить список серверов');
                return [];
            }
        },

        /**
         * Загружает список приложений
         * @param {string|number|null} serverId - ID сервера
         * @returns {Promise<Array>}
         */
        async loadApplications(serverId = null) {
            try {
                let url = '/api/applications';
                if (serverId && serverId !== 'all') {
                    url += `?server_id=${serverId}`;
                }
                const response = await fetch(url);
                const data = await response.json();
                return data.success ? data.applications : [];
            } catch (error) {
                console.error('Ошибка загрузки приложений:', error);
                this._showError('Не удалось загрузить список приложений');
                return [];
            }
        },

        /**
         * Загружает список тегов
         * @returns {Promise<Array>}
         */
        async loadTags() {
            try {
                const response = await fetch('/api/tags');
                const data = await response.json();
                return data.success ? data.tags : [];
            } catch (error) {
                console.error('Ошибка загрузки тегов:', error);
                return [];
            }
        },

        /**
         * Загружает артефакты приложения
         * @param {string|number} appId - ID приложения
         * @param {number} limit - максимальное количество
         * @param {boolean} showProgress - показывать прогресс
         * @returns {Promise<Array|null>}
         */
        async loadArtifacts(appId, limit = null, showProgress = false) {
            const maxDisplay = limit || this._config?.MAX_ARTIFACTS_DISPLAY || 20;

            try {
                if (showProgress) {
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) progressBar.style.width = '30%';
                }

                const response = await fetch(`/api/applications/${appId}/artifacts?limit=${maxDisplay}`);

                if (showProgress) {
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) progressBar.style.width = '70%';
                }

                const data = await response.json();

                if (showProgress) {
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) progressBar.style.width = '100%';
                }

                if (data.success && data.versions && data.versions.length > 0) {
                    // Сортируем версии только по номеру (от большего к меньшему)
                    const sortedVersions = data.versions.sort((a, b) => {
                        const extractVersion = (versionObj) => {
                            const cleanVersion = versionObj.version
                                .replace(/^v/i, '')
                                .replace(/[-_](snapshot|dev|alpha|beta|rc).*$/i, '');

                            const parts = cleanVersion.split(/[.-]/).map(part => {
                                const num = parseInt(part, 10);
                                return isNaN(num) ? 0 : num;
                            });

                            while (parts.length < 4) parts.push(0);
                            return parts;
                        };

                        const aParts = extractVersion(a);
                        const bParts = extractVersion(b);

                        for (let i = 0; i < 4; i++) {
                            if (bParts[i] !== aParts[i]) {
                                return bParts[i] - aParts[i];
                            }
                        }

                        if (a.is_release && !b.is_release) return -1;
                        if (!a.is_release && b.is_release) return 1;

                        return 0;
                    });

                    return sortedVersions.slice(0, maxDisplay);
                }

                return null;
            } catch (error) {
                console.error('Ошибка загрузки артефактов:', error);
                return null;
            }
        },

        /**
         * Выполняет действие над приложениями
         * @param {Array} appIds - массив ID приложений
         * @param {string} action - действие (start, stop, restart)
         * @returns {Promise<Object>}
         */
        async executeAction(appIds, action) {
            try {
                const response = await fetch('/api/applications/bulk/manage', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ app_ids: appIds, action })
                });
                return await response.json();
            } catch (error) {
                console.error('Ошибка выполнения действия:', error);
                this._showError(`Не удалось выполнить действие "${action}"`);
                return { success: false, error: error.message };
            }
        },

        /**
         * Обновляет приложение
         * @param {string|number} appId - ID приложения
         * @param {Object} updateParams - параметры обновления
         * @returns {Promise<Object>}
         */
        async updateApplication(appId, updateParams) {
            try {
                const response = await fetch(`/api/applications/${appId}/update`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updateParams)
                });
                return await response.json();
            } catch (error) {
                console.error('Ошибка обновления приложения:', error);
                return { success: false, error: error.message };
            }
        },

        /**
         * Получает информацию о приложении
         * @param {string|number} appId - ID приложения
         * @returns {Promise<Object|null>}
         */
        async getApplicationInfo(appId) {
            try {
                const response = await fetch(`/api/applications/${appId}`);
                const data = await response.json();
                return data.success ? data.application : null;
            } catch (error) {
                console.error('Ошибка получения информации:', error);
                this._showError('Не удалось получить информацию о приложении');
                return null;
            }
        },

        /**
         * Загружает список оркестраторов
         * @param {boolean} activeOnly - только активные
         * @returns {Promise<Array>}
         */
        async loadOrchestrators(activeOnly = true) {
            try {
                const url = `/api/orchestrators${activeOnly ? '?active_only=true' : ''}`;
                const response = await fetch(url);
                const data = await response.json();
                return data.success ? data.orchestrators : [];
            } catch (error) {
                console.error('Ошибка загрузки оркестраторов:', error);
                this._showError('Не удалось загрузить список оркестраторов');
                return [];
            }
        },

        /**
         * Проверяет наличие маппингов (HAProxy/Eureka) для приложений.
         * Используется для определения значения оркестратора по умолчанию.
         *
         * @param {Array<number>} appIds - массив ID приложений
         * @returns {Promise<{canOrchestrate: boolean, total: number, haproxyMapped: number, eurekaMapped: number}>}
         */
        async checkMappings(appIds) {
            try {
                const response = await fetch('/api/orchestrators/validate-mappings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ application_ids: appIds })
                });

                if (!response.ok) {
                    console.error('Ошибка проверки маппингов:', response.status);
                    return { canOrchestrate: false, total: appIds.length, haproxyMapped: 0, eurekaMapped: 0 };
                }

                const data = await response.json();
                return {
                    canOrchestrate: data.can_orchestrate,
                    total: data.total,
                    haproxyMapped: data.haproxy_mapped,
                    eurekaMapped: data.eureka_mapped
                };
            } catch (error) {
                console.error('Ошибка проверки маппингов:', error);
                return { canOrchestrate: false, total: appIds.length, haproxyMapped: 0, eurekaMapped: 0 };
            }
        }
    };

    // Экспорт в глобальную область
    window.ApiService = ApiService;
})();

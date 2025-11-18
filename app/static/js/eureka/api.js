/**
 * Eureka API Module
 * Модуль для взаимодействия с Eureka API endpoints
 */

const EurekaAPI = {
    /**
     * Базовый URL для Eureka API
     */
    baseUrl: '/api/eureka',

    /**
     * Обобщенный метод для выполнения API запросов с обработкой ошибок
     * @param {string} url - URL для запроса
     * @param {Object} options - Опции fetch
     * @param {string} errorContext - Контекст для логирования ошибок
     * @returns {Promise<Object>}
     */
    async _fetchWithErrorHandling(url, options = {}, errorContext = 'API request') {
        try {
            const response = await fetch(url, options);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`${errorContext}:`, error);
            throw error;
        }
    },

    /**
     * Валидация ID
     * @param {*} id - ID для проверки
     * @param {string} paramName - Имя параметра для сообщения об ошибке
     */
    _validateId(id, paramName = 'id') {
        if (id == null || (typeof id !== 'number' && typeof id !== 'string')) {
            throw new Error(`Invalid ${paramName}: must be a number or string`);
        }
        const numId = typeof id === 'string' ? parseInt(id) : id;
        if (isNaN(numId) || numId <= 0) {
            throw new Error(`Invalid ${paramName}: must be a positive number`);
        }
        return numId;
    },

    /**
     * Получить список всех Eureka серверов
     * @param {boolean} activeOnly - Только активные серверы
     * @returns {Promise<Object>}
     */
    async getServers(activeOnly = false) {
        const url = `${this.baseUrl}/servers${activeOnly ? '?is_active=true' : ''}`;
        return await this._fetchWithErrorHandling(url, {}, 'Error fetching Eureka servers');
    },

    /**
     * Получить детали конкретного Eureka сервера
     * @param {number} serverId - ID сервера
     * @returns {Promise<Object>}
     */
    async getServer(serverId) {
        const id = this._validateId(serverId, 'serverId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/servers/${id}`,
            {},
            `Error fetching Eureka server ${id}`
        );
    },

    /**
     * Получить список приложений для Eureka сервера
     * @param {number} serverId - ID сервера (optional)
     * @returns {Promise<Object>}
     */
    async getApplications(serverId = null) {
        let url = `${this.baseUrl}/applications`;
        if (serverId != null) {
            const id = this._validateId(serverId, 'serverId');
            url = `${this.baseUrl}/servers/${id}/applications`;
        }
        return await this._fetchWithErrorHandling(url, {}, 'Error fetching Eureka applications');
    },

    /**
     * Получить список instances
     * @param {Object} filters - Фильтры (serverId, appName, status)
     * @returns {Promise<Object>}
     */
    async getInstances(filters = {}) {
        const params = new URLSearchParams();
        if (filters.serverId) params.append('server_id', filters.serverId);
        if (filters.appName) params.append('app_name', filters.appName);
        if (filters.status) params.append('status', filters.status);

        const url = `${this.baseUrl}/instances${params.toString() ? '?' + params.toString() : ''}`;
        return await this._fetchWithErrorHandling(url, {}, 'Error fetching Eureka instances');
    },

    /**
     * Получить детали конкретного instance
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async getInstance(instanceId) {
        const id = this._validateId(instanceId, 'instanceId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${id}`,
            {},
            `Error fetching Eureka instance ${id}`
        );
    },

    /**
     * Получить health статус instance
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async getHealth(instanceId) {
        const id = this._validateId(instanceId, 'instanceId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${id}/health`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            },
            `Error fetching health for instance ${id}`
        );
    },

    /**
     * Приостановить instance (pause)
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async pauseInstance(instanceId) {
        const id = this._validateId(instanceId, 'instanceId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${id}/pause`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            },
            `Error pausing instance ${id}`
        );
    },

    /**
     * Возобновить instance (resume - отменить pause)
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async resumeInstance(instanceId) {
        const id = this._validateId(instanceId, 'instanceId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${id}/resume`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            },
            `Error resuming instance ${id}`
        );
    },

    /**
     * Выключить instance (shutdown)
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async shutdownInstance(instanceId) {
        const id = this._validateId(instanceId, 'instanceId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${id}/shutdown`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            },
            `Error shutting down instance ${id}`
        );
    },

    /**
     * Изменить уровень логирования
     * @param {number} instanceId - ID instance
     * @param {string} loggerName - Имя logger
     * @param {string} level - Уровень (TRACE, DEBUG, INFO, WARN, ERROR)
     * @param {number} duration - Длительность в минутах (optional)
     * @returns {Promise<Object>}
     */
    async setLogLevel(instanceId, loggerName, level, duration = null) {
        const id = this._validateId(instanceId, 'instanceId');

        if (!loggerName || typeof loggerName !== 'string') {
            throw new Error('Invalid loggerName: must be a non-empty string');
        }

        const validLevels = ['TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR'];
        if (!validLevels.includes(level)) {
            throw new Error(`Invalid level: must be one of ${validLevels.join(', ')}`);
        }

        const body = {
            logger_name: loggerName,
            level: level
        };
        if (duration != null) {
            const numDuration = parseInt(duration);
            if (isNaN(numDuration) || numDuration <= 0) {
                throw new Error('Invalid duration: must be a positive number');
            }
            body.duration = numDuration;
        }

        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${id}/loglevel`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            },
            `Error setting log level for instance ${id}`
        );
    },

    /**
     * Привязать instance к приложению
     * @param {number} instanceId - ID instance
     * @param {number} applicationId - ID приложения
     * @param {string} notes - Примечания (optional)
     * @returns {Promise<Object>}
     */
    async mapInstance(instanceId, applicationId, notes = null) {
        const instId = this._validateId(instanceId, 'instanceId');
        const appId = this._validateId(applicationId, 'applicationId');

        const body = { application_id: appId };
        if (notes) {
            body.notes = notes;
        }

        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${instId}/map`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            },
            `Error mapping instance ${instId}`
        );
    },

    /**
     * Отвязать instance от приложения
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async unmapInstance(instanceId) {
        const id = this._validateId(instanceId, 'instanceId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/${id}/map`,
            { method: 'DELETE' },
            `Error unmapping instance ${id}`
        );
    },

    /**
     * Синхронизировать Eureka сервер
     * @param {number} serverId - ID сервера
     * @returns {Promise<Object>}
     */
    async syncServer(serverId) {
        const id = this._validateId(serverId, 'serverId');
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/servers/${id}/sync`,
            { method: 'POST' },
            `Error syncing Eureka server ${id}`
        );
    },

    /**
     * Выполнить автоматический маппинг
     * @returns {Promise<Object>}
     */
    async autoMap() {
        return await this._fetchWithErrorHandling(
            `${this.baseUrl}/instances/auto-map`,
            { method: 'POST' },
            'Error performing auto-mapping'
        );
    }
};

// Экспортируем EurekaAPI в глобальную область
window.EurekaAPI = EurekaAPI;

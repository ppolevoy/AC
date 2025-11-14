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
     * Получить список всех Eureka серверов
     * @param {boolean} activeOnly - Только активные серверы
     * @returns {Promise<Object>}
     */
    async getServers(activeOnly = false) {
        try {
            const url = `${this.baseUrl}/servers${activeOnly ? '?active_only=true' : ''}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error fetching Eureka servers:', error);
            throw error;
        }
    },

    /**
     * Получить детали конкретного Eureka сервера
     * @param {number} serverId - ID сервера
     * @returns {Promise<Object>}
     */
    async getServer(serverId) {
        try {
            const response = await fetch(`${this.baseUrl}/servers/${serverId}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching Eureka server ${serverId}:`, error);
            throw error;
        }
    },

    /**
     * Получить список приложений для Eureka сервера
     * @param {number} serverId - ID сервера (optional)
     * @returns {Promise<Object>}
     */
    async getApplications(serverId = null) {
        try {
            const url = serverId
                ? `${this.baseUrl}/servers/${serverId}/applications`
                : `${this.baseUrl}/applications`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error fetching Eureka applications:', error);
            throw error;
        }
    },

    /**
     * Получить список instances
     * @param {Object} filters - Фильтры (serverId, appName, status)
     * @returns {Promise<Object>}
     */
    async getInstances(filters = {}) {
        try {
            const params = new URLSearchParams();
            if (filters.serverId) params.append('server_id', filters.serverId);
            if (filters.appName) params.append('app_name', filters.appName);
            if (filters.status) params.append('status', filters.status);

            const url = `${this.baseUrl}/instances${params.toString() ? '?' + params.toString() : ''}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error fetching Eureka instances:', error);
            throw error;
        }
    },

    /**
     * Получить детали конкретного instance
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async getInstance(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching Eureka instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Получить health статус instance
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async getHealth(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/health`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching health for instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Приостановить instance (pause)
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async pauseInstance(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/pause`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error pausing instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Возобновить instance (resume - отменить pause)
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async resumeInstance(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/resume`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error resuming instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Выключить instance (shutdown)
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async shutdownInstance(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/shutdown`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error shutting down instance ${instanceId}:`, error);
            throw error;
        }
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
        try {
            const body = {
                logger_name: loggerName,
                level: level
            };
            if (duration) {
                body.duration = duration;
            }

            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/loglevel`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error setting log level for instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Привязать instance к приложению
     * @param {number} instanceId - ID instance
     * @param {number} applicationId - ID приложения
     * @param {string} notes - Примечания (optional)
     * @returns {Promise<Object>}
     */
    async mapInstance(instanceId, applicationId, notes = null) {
        try {
            const body = {
                application_id: applicationId
            };
            if (notes) {
                body.notes = notes;
            }

            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/map`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error mapping instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Отвязать instance от приложения
     * @param {number} instanceId - ID instance
     * @returns {Promise<Object>}
     */
    async unmapInstance(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/map`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error unmapping instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Синхронизировать Eureka сервер
     * @param {number} serverId - ID сервера
     * @returns {Promise<Object>}
     */
    async syncServer(serverId) {
        try {
            const response = await fetch(`${this.baseUrl}/servers/${serverId}/sync`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error syncing Eureka server ${serverId}:`, error);
            throw error;
        }
    },

    /**
     * Выполнить автоматический маппинг
     * @returns {Promise<Object>}
     */
    async autoMap() {
        try {
            const response = await fetch(`${this.baseUrl}/instances/auto-map`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error performing auto-mapping:', error);
            throw error;
        }
    }
};

// Экспортируем EurekaAPI в глобальную область
window.EurekaAPI = EurekaAPI;

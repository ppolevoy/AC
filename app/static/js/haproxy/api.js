/**
 * HAProxy API Module
 * Модуль для взаимодействия с HAProxy API endpoints
 */

const HAProxyAPI = {
    /**
     * Базовый URL для HAProxy API
     */
    baseUrl: '/api/haproxy',

    /**
     * Получить список всех HAProxy инстансов
     * @param {boolean} activeOnly - Только активные инстансы
     * @returns {Promise<Object>}
     */
    async getInstances(activeOnly = false) {
        try {
            const url = `${this.baseUrl}/instances${activeOnly ? '?active_only=true' : ''}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error fetching HAProxy instances:', error);
            throw error;
        }
    },

    /**
     * Получить детали конкретного HAProxy инстанса
     * @param {number} instanceId - ID инстанса
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
            console.error(`Error fetching HAProxy instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Получить список backends для HAProxy инстанса
     * @param {number} instanceId - ID инстанса
     * @returns {Promise<Object>}
     */
    async getInstanceBackends(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/backends`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching backends for instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Получить список серверов в backend
     * @param {number} backendId - ID backend
     * @returns {Promise<Object>}
     */
    async getBackendServers(backendId) {
        try {
            const response = await fetch(`${this.baseUrl}/backends/${backendId}/servers`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching servers for backend ${backendId}:`, error);
            throw error;
        }
    },

    /**
     * Получить сводную статистику по всем HAProxy инстансам
     * @returns {Promise<Object>}
     */
    async getSummary() {
        try {
            const response = await fetch(`${this.baseUrl}/summary`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error fetching HAProxy summary:', error);
            throw error;
        }
    },

    /**
     * Принудительная синхронизация HAProxy инстанса
     * @param {number} instanceId - ID инстанса
     * @returns {Promise<Object>}
     */
    async syncInstance(instanceId) {
        try {
            const response = await fetch(`${this.baseUrl}/instances/${instanceId}/sync`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error syncing HAProxy instance ${instanceId}:`, error);
            throw error;
        }
    },

    /**
     * Получить историю изменений статуса сервера
     * @param {number} serverId - ID сервера
     * @param {number} limit - Максимальное количество записей
     * @returns {Promise<Object>}
     */
    async getServerHistory(serverId, limit = 50) {
        try {
            const response = await fetch(`${this.baseUrl}/servers/${serverId}/history?limit=${limit}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching history for server ${serverId}:`, error);
            throw error;
        }
    },

    /**
     * Повторный маппинг всех HAProxy серверов на приложения
     * @returns {Promise<Object>}
     */
    async remapServers() {
        try {
            const response = await fetch(`${this.baseUrl}/mapping/remap`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error remapping servers:', error);
            throw error;
        }
    },

    /**
     * Очистка кэша HAProxy сервиса
     * @returns {Promise<Object>}
     */
    async clearCache() {
        try {
            const response = await fetch(`${this.baseUrl}/cache/clear`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error clearing cache:', error);
            throw error;
        }
    }
};

// Экспортируем для использования в других модулях
window.HAProxyAPI = HAProxyAPI;

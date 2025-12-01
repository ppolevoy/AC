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

            const data = await response.json();

            // Даже при HTTP 500 возвращаем данные с ошибкой из backend
            if (!response.ok && !data.error) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

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
    },

    // ==================== Manual Mapping Operations ====================

    /**
     * Установить ручной маппинг HAProxy сервера на приложение
     * @param {number} serverId - ID HAProxy сервера
     * @param {number} applicationId - ID приложения
     * @param {string} notes - Заметки о маппинге
     * @returns {Promise<Object>}
     */
    async mapServer(serverId, applicationId, notes = '') {
        try {
            const response = await fetch(`${this.baseUrl}/servers/${serverId}/map`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    application_id: applicationId,
                    notes: notes
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error mapping server ${serverId}:`, error);
            throw error;
        }
    },

    /**
     * Удалить маппинг HAProxy сервера
     * @param {number} serverId - ID HAProxy сервера
     * @param {string} notes - Причина удаления
     * @returns {Promise<Object>}
     */
    async unmapServer(serverId, notes = 'Маппинг удален вручную') {
        try {
            const response = await fetch(`${this.baseUrl}/servers/${serverId}/unmap`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    notes: notes
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error unmapping server ${serverId}:`, error);
            throw error;
        }
    },

    /**
     * Получить список несвязанных HAProxy серверов
     * @param {number} backendId - Фильтр по backend (optional)
     * @param {number} instanceId - Фильтр по instance (optional)
     * @returns {Promise<Object>}
     */
    async getUnmappedServers(backendId = null, instanceId = null) {
        try {
            let url = `${this.baseUrl}/servers/unmapped`;
            const params = new URLSearchParams();

            if (backendId) params.append('backend_id', backendId);
            if (instanceId) params.append('instance_id', instanceId);

            if (params.toString()) {
                url += '?' + params.toString();
            }

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error fetching unmapped servers:', error);
            throw error;
        }
    },

    /**
     * Получить историю изменений маппинга сервера
     * @param {number} serverId - ID HAProxy сервера
     * @param {number} limit - Максимальное количество записей
     * @returns {Promise<Object>}
     */
    async getMappingHistory(serverId, limit = 50) {
        try {
            const response = await fetch(`${this.baseUrl}/servers/${serverId}/mapping-history?limit=${limit}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching mapping history for server ${serverId}:`, error);
            throw error;
        }
    },

    /**
     * Поиск приложений для маппинга HAProxy сервера
     * @param {number} serverId - ID HAProxy сервера
     * @param {string} query - Поисковый запрос (optional)
     * @returns {Promise<Object>}
     */
    async searchApplications(serverId, query = '') {
        try {
            let url = `${this.baseUrl}/applications/search?server_id=${serverId}`;
            if (query) {
                url += `&query=${encodeURIComponent(query)}`;
            }

            const response = await fetch(url);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error searching applications for server ${serverId}:`, error);
            throw error;
        }
    }
};

// Экспортируем для использования в других модулях
window.HAProxyAPI = HAProxyAPI;

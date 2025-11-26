/**
 * config.js
 * Константы и конфигурация приложения
 */
(function() {
    'use strict';

    const CONFIG = {
        PROGRESS: {
            START: 10,
            FETCH_COMPLETE: 70,
            PARSE_COMPLETE: 100
        },
        CACHE_LIFETIME: 5 * 60 * 1000, // 5 минут
        ANIMATION_DELAYS: {
            FADE_IN: 100,
            FIELD_STAGGER: 100,
            MIN_LOADER_TIME: 600
        },
        MAX_ARTIFACTS_DISPLAY: 20,
        PAGE_SIZE: 10
    };

    // Экспорт в глобальную область
    window.CONFIG = CONFIG;
})();

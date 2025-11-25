/**
 * Faktura Apps - Базовый JavaScript файл
 * Содержит общие функции, используемые во всем приложении
 */

document.addEventListener('DOMContentLoaded', function() {
    // Инициализация элементов интерфейса
    initThemeToggle();
    initModalFunctions();
});

/**
 * Инициализация переключателя темы
 */
function initThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');

    // Если кнопка не найдена (например, на странице с кастомным header), выходим
    if (!themeToggle) {
        return;
    }

    const body = document.body;
    const themeIcon = document.getElementById('theme-icon-base');

    // Функция обновления иконки
    function updateThemeIcon(isLight) {
        if (!themeIcon) return;

        if (isLight) {
            // Иконка луны для светлой темы
            themeIcon.innerHTML = `
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            `;
        } else {
            // Иконка солнца для темной темы
            themeIcon.innerHTML = `
                <circle cx="12" cy="12" r="5"></circle>
                <line x1="12" y1="1" x2="12" y2="3"></line>
                <line x1="12" y1="21" x2="12" y2="23"></line>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                <line x1="1" y1="12" x2="3" y2="12"></line>
                <line x1="21" y1="12" x2="23" y2="12"></line>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            `;
        }
    }

    // Проверяем сохраненную тему
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        body.classList.add('light-theme');
        updateThemeIcon(true);
    } else {
        updateThemeIcon(false);
    }

    themeToggle.addEventListener('click', function() {
        const isLight = body.classList.toggle('light-theme');

        if (isLight) {
            localStorage.setItem('theme', 'light');
            updateThemeIcon(true);
        } else {
            localStorage.setItem('theme', 'dark');
            updateThemeIcon(false);
        }
    });
}

/**
 * Инициализация функций для работы с модальными окнами
 */
function initModalFunctions() {
    const modalContainer = document.getElementById('modal-container');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const modalClose = document.querySelector('.modal-close');
    const modalOverlay = document.querySelector('.modal-overlay');
    
    window.showModal = function(title, content) {
        // Устанавливаем заголовок
        modalTitle.textContent = title;
        
        // Очищаем текущее содержимое модального окна
        modalBody.innerHTML = '';
        
        // Проверяем тип содержимого и добавляем его в модальное окно
        if (content instanceof DocumentFragment) {
            // Если content - DocumentFragment (например, клонированный шаблон)
            modalBody.appendChild(content);
        } else if (content instanceof Element) {
            // Если content - DOM-элемент
            modalBody.appendChild(content);
        } else if (typeof content === 'string') {
            // Если content - строка HTML
            modalBody.innerHTML = content;
        } else {
            // Для любых других типов преобразуем в строку
            modalBody.textContent = String(content);
        }
        
        // Показываем модальное окно
        modalContainer.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // Блокируем прокрутку страницы
    };
    
    window.closeModal = function() {
        modalContainer.style.display = 'none';
        document.body.style.overflow = ''; // Разрешаем прокрутку страницы
    };
    
    // Обработчики для закрытия модального окна
    modalClose.addEventListener('click', window.closeModal);
    modalOverlay.addEventListener('click', window.closeModal);
    
    // Предотвращаем закрытие модального окна при клике на его содержимое
    document.querySelector('.modal-content').addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

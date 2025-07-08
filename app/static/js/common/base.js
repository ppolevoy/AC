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
    const body = document.body;
    
    // Проверяем сохраненную тему
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        body.classList.add('light-theme');
        themeToggle.textContent = 'Темная тема';
    }
    
    themeToggle.addEventListener('click', function() {
        body.classList.toggle('light-theme');
        
        if (body.classList.contains('light-theme')) {
            themeToggle.textContent = 'Темная тема';
            localStorage.setItem('theme', 'light');
        } else {
            themeToggle.textContent = 'Светлая тема';
            localStorage.setItem('theme', 'dark');
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

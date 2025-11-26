/**
 * dropdown-handlers.js
 * Модуль для управления выпадающими меню действий
 * Извлечено из EventHandlers для улучшения поддержки кода
 */
(function() {
    'use strict';

    const DropdownHandlers = {
        activeDropdown: null,

        /**
         * Инициализация обработчиков выпадающих меню
         */
        init() {
            // Создаем оверлей для выпадающих меню
            let dropdownOverlay = document.querySelector('.dropdown-overlay');
            if (!dropdownOverlay) {
                dropdownOverlay = document.createElement('div');
                dropdownOverlay.className = 'dropdown-overlay';
                document.body.appendChild(dropdownOverlay);
            }

            // Обработчик клика по кнопке меню
            document.body.addEventListener('click', (e) => {
                const actionButton = e.target.closest('.actions-button');
                if (actionButton) {
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggle(actionButton);
                }
            });

            // Закрытие меню при клике на оверлей
            dropdownOverlay.addEventListener('click', () => {
                this.closeAll();
            });
        },

        /**
         * Переключает состояние выпадающего меню
         */
        toggle(actionButton) {
            const dropdown = actionButton.nextElementSibling;
            const dropdownOverlay = document.querySelector('.dropdown-overlay');

            if (dropdown.classList.contains('show')) {
                this.closeAll();
                return;
            }

            this.closeAll();

            // Показываем оверлей и меню
            dropdownOverlay.style.display = 'block';
            this.position(dropdown, actionButton);
            this.activeDropdown = dropdown;
        },

        /**
         * Позиционирует выпадающее меню
         */
        position(dropdown, actionButton) {
            const buttonRect = actionButton.getBoundingClientRect();
            const spaceBelow = window.innerHeight - buttonRect.bottom;
            const showUpwards = spaceBelow < 200;

            // Сначала сбрасываем все позиции
            dropdown.style.top = '';
            dropdown.style.bottom = '';
            dropdown.style.display = 'block';
            dropdown.style.opacity = '0';
            dropdown.classList.remove('dropdown-up');

            if (showUpwards) {
                dropdown.classList.add('dropdown-up');
                dropdown.style.bottom = (window.innerHeight - buttonRect.top) + 'px';
                dropdown.style.top = 'auto';
            } else {
                dropdown.style.top = buttonRect.bottom + 'px';
                dropdown.style.bottom = 'auto';
            }

            dropdown.style.right = (window.innerWidth - buttonRect.right) + 'px';
            dropdown.classList.add('show');
            dropdown.style.opacity = '1';
            actionButton.classList.add('active');
        },

        /**
         * Закрывает все выпадающие меню
         */
        closeAll() {
            const dropdownOverlay = document.querySelector('.dropdown-overlay');
            if (dropdownOverlay) {
                dropdownOverlay.style.display = 'none';
            }

            document.querySelectorAll('.actions-dropdown.show').forEach(dropdown => {
                dropdown.classList.remove('show');
                dropdown.style.display = '';

                const actionButton = dropdown.previousElementSibling;
                if (actionButton) {
                    actionButton.classList.remove('active');
                }
            });

            this.activeDropdown = null;
        }
    };

    // Экспорт в глобальную область
    window.DropdownHandlers = DropdownHandlers;
})();

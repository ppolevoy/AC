/**
 * Утилиты для работы с модальными окнами
 */
const ModalUtils = {
    /**
     * Показать информационное модальное окно
     * @param {string} title - Заголовок модального окна
     * @param {Array} sections - Массив секций с информацией
     * [
     *   {
     *     title: 'Заголовок секции',
     *     type: 'table|html|list',
     *     rows: [{ label: 'Метка', value: 'Значение' }], // для type='table'
     *     content: 'HTML содержимое', // для type='html'
     *     items: ['Элемент 1', 'Элемент 2'], // для type='list'
     *   }
     * ]
     */
    showInfoModal: function(title, sections) {
        const content = this.createInfoModalContent(sections);
        window.showModal(title, content);
    },
    
    /**
     * Создает содержимое информационного модального окна
     * @param {Array} sections - Массив секций с информацией
     * @returns {HTMLElement} Контейнер с содержимым
     */
    createInfoModalContent: function(sections) {
        const container = document.createElement('div');
        container.className = 'info-modal-container';
        
        sections.forEach(section => {
            const sectionDiv = document.createElement('div');
            sectionDiv.className = 'app-info-section';
            
            const sectionTitle = document.createElement('h4');
            sectionTitle.textContent = section.title;
            sectionDiv.appendChild(sectionTitle);
            
            if (section.type === 'table') {
                const table = document.createElement('table');
                table.className = 'info-table';
                
                section.rows.forEach(row => {
                    const tr = document.createElement('tr');
                    
                    const labelTd = document.createElement('td');
                    labelTd.className = 'info-label';
                    labelTd.textContent = row.label;
                    tr.appendChild(labelTd);
                    
                    const valueTd = document.createElement('td');
                    valueTd.innerHTML = row.value;
                    tr.appendChild(valueTd);
                    
                    table.appendChild(tr);
                });
                
                sectionDiv.appendChild(table);
            } else if (section.type === 'html') {
                const contentDiv = document.createElement('div');
                contentDiv.className = 'section-content';
                contentDiv.innerHTML = section.content;
                sectionDiv.appendChild(contentDiv);
            } else if (section.type === 'list') {
                const list = document.createElement('ul');
                list.className = 'app-list';
                
                section.items.forEach(item => {
                    const li = document.createElement('li');
                    li.innerHTML = item;
                    list.appendChild(li);
                });
                
                sectionDiv.appendChild(list);
            }
            
            container.appendChild(sectionDiv);
        });
        
        return container;
    },
    
    /**
     * Показать модальное окно подтверждения
     * @param {string} title - Заголовок модального окна
     * @param {string} message - Сообщение подтверждения
     * @param {Array} items - Массив элементов для отображения в списке
     * @param {function} confirmAction - Функция, которая выполнится при подтверждении
     * @param {string} confirmButtonText - Текст кнопки подтверждения
     * @param {string} confirmButtonClass - Класс кнопки подтверждения
     */
    showConfirmModal: function(title, message, items, confirmAction, confirmButtonText = "Подтвердить", confirmButtonClass = "confirm-btn") {
        const content = this.createConfirmModalContent(message, items, confirmButtonText, confirmButtonClass);
        window.showModal(title, content);
        
        // Установка обработчика для кнопки подтверждения
        document.querySelector(`.${confirmButtonClass}`).addEventListener('click', function() {
            confirmAction();
            window.closeModal();
        });
    },
    
    /**
     * Создает содержимое модального окна подтверждения
     * @param {string} message - Сообщение подтверждения
     * @param {Array} items - Массив элементов для отображения в списке
     * @param {string} confirmButtonText - Текст кнопки подтверждения
     * @param {string} confirmButtonClass - Класс кнопки подтверждения
     * @returns {HTMLElement} Контейнер с содержимым
     */
    createConfirmModalContent: function(message, items, confirmButtonText, confirmButtonClass) {
        const container = document.createElement('div');
        
        const messageP = document.createElement('p');
        messageP.className = 'confirmation-text';
        messageP.innerHTML = message;
        container.appendChild(messageP);
        
        if (items && items.length > 0) {
            const listContainer = document.createElement('div');
            listContainer.className = 'app-list';
            
            const list = document.createElement('ul');
            items.forEach(item => {
                const li = document.createElement('li');
                li.textContent = item;
                list.appendChild(li);
            });
            
            listContainer.appendChild(list);
            container.appendChild(listContainer);
        }
        
        const actions = document.createElement('div');
        actions.className = 'form-actions';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'cancel-btn';
        cancelBtn.textContent = 'Отмена';
        cancelBtn.onclick = window.closeModal;
        actions.appendChild(cancelBtn);
        
        const confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.className = confirmButtonClass;
        confirmBtn.textContent = confirmButtonText;
        actions.appendChild(confirmBtn);
        
        container.appendChild(actions);
        
        return container;
    },
    
    /**
     * Показать модальное окно с формой
     * @param {string} title - Заголовок модального окна
     * @param {Array} formFields - Массив полей формы
     * [
     *   {
     *     id: 'field-id',
     *     name: 'field-name',
     *     label: 'Метка поля',
     *     type: 'text|number|email|password|textarea|select|radio|hidden',
     *     value: 'Значение',
     *     required: true|false,
     *     pattern: 'Регулярное выражение', // для валидации
     *     min: 0, // для number
     *     max: 100, // для number
     *     options: [{ value: 'Значение', text: 'Текст' }] // для select и radio
     *   }
     * ]
     * @param {function} submitAction - Функция, которая выполнится при отправке формы
     * @param {string} submitButtonText - Текст кнопки отправки
     */
    showFormModal: function(title, formFields, submitAction, submitButtonText = "Сохранить") {
        const content = this.createFormModalContent(formFields, submitButtonText);
        window.showModal(title, content);
        
        // Установка обработчика для отправки формы
        document.querySelector('#modal-form').addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Формируем объект с данными формы
            const formData = {};
            formFields.forEach(field => {
                if (field.type === 'radio') {
                    const checkedRadio = document.querySelector(`input[name="${field.name}"]:checked`);
                    formData[field.name] = checkedRadio ? checkedRadio.value : null;
                } else {
                    const input = document.querySelector(`#${field.id}`);
                    formData[field.name] = input ? input.value : null;
                }
            });
            
            // Выполняем действие
            submitAction(formData);
			window.closeModal();
        });
    },
    
    /**
     * Создает содержимое модального окна с формой
     * @param {Array} formFields - Массив полей формы
     * @param {string} submitButtonText - Текст кнопки отправки
     * @returns {HTMLElement} Форма с полями
     */
    createFormModalContent: function(formFields, submitButtonText) {
        const form = document.createElement('form');
        form.id = 'modal-form';
        form.className = 'modal-form';
        
        formFields.forEach(field => {
            const formGroup = document.createElement('div');
            formGroup.className = 'form-group';
            
            if (field.type !== 'hidden') {
                const label = document.createElement('label');
                label.setAttribute('for', field.id);
                label.textContent = field.label;
                formGroup.appendChild(label);
            }
            
            if (field.type === 'text' || field.type === 'number' || field.type === 'email' || field.type === 'password' || field.type === 'hidden') {
                const input = document.createElement('input');
                input.type = field.type;
                input.id = field.id;
                input.name = field.name;
                input.className = 'form-control';
                
                if (field.value !== undefined) input.value = field.value;
                if (field.required) input.required = true;
                if (field.pattern) input.pattern = field.pattern;
                if (field.min !== undefined) input.min = field.min;
                if (field.max !== undefined) input.max = field.max;
                
                formGroup.appendChild(input);
            } else if (field.type === 'textarea') {
                const textarea = document.createElement('textarea');
                textarea.id = field.id;
                textarea.name = field.name;
                textarea.className = 'form-control';
                
                if (field.value !== undefined) textarea.value = field.value;
                if (field.required) textarea.required = true;
                
                formGroup.appendChild(textarea);
            } else if (field.type === 'select') {
                const select = document.createElement('select');
                select.id = field.id;
                select.name = field.name;
                select.className = 'form-control';
                
                if (field.required) select.required = true;
                
                field.options.forEach(option => {
                    const opt = document.createElement('option');
                    opt.value = option.value;
                    opt.textContent = option.text;
                    
                    if (option.value === field.value) opt.selected = true;
                    
                    select.appendChild(opt);
                });
                
                formGroup.appendChild(select);
            } else if (field.type === 'radio') {
                const radioGroup = document.createElement('div');
                radioGroup.className = 'radio-group';
                
                field.options.forEach(option => {
                    const label = document.createElement('label');
                    label.className = 'radio-label';
                    
                    const input = document.createElement('input');
                    input.type = 'radio';
                    input.name = field.name;
                    input.value = option.value;
                    
                    if (option.value === field.value) input.checked = true;
                    
                    label.appendChild(input);
                    label.appendChild(document.createTextNode(' ' + option.text));
                    
                    radioGroup.appendChild(label);
                });
                
                formGroup.appendChild(radioGroup);
            }
            
            form.appendChild(formGroup);
        });
        
        const actions = document.createElement('div');
        actions.className = 'form-actions';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'cancel-btn';
        cancelBtn.textContent = 'Отмена';
        cancelBtn.onclick = window.closeModal;
        actions.appendChild(cancelBtn);
        
        const submitBtn = document.createElement('button');
        submitBtn.type = 'submit';
        submitBtn.className = 'submit-btn';
        submitBtn.textContent = submitButtonText;
        actions.appendChild(submitBtn);
        
        form.appendChild(actions);
        
        return form;
    }
};
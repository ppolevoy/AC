/**
 * tags-renderer.js
 * Объединённый модуль для рендеринга тегов (собственных и унаследованных)
 * Заменяет дублирующиеся функции renderTags и renderTagsWithInherited
 */
(function() {
    'use strict';

    const TagsRenderer = {
        /**
         * Рендеринг тегов с опциональной поддержкой унаследованных тегов
         * @param {Array} ownTags - Собственные теги
         * @param {Object} options - Опции
         * @param {Array} options.groupTags - Унаследованные теги от группы
         * @param {number} options.maxVisible - Максимальное количество видимых тегов (по умолчанию 4)
         * @param {boolean} options.tableMode - Если true, показывать только теги с show_in_table=true
         * @returns {string} HTML строка с тегами
         */
        render(ownTags, options = {}) {
            const { groupTags = null, maxVisible = 4, tableMode = true } = options;

            let allTags = this._mergeTags(ownTags, groupTags);

            // В режиме таблицы показываем только теги с show_in_table=true
            // (для системных тегов) или все кастомные теги
            if (tableMode) {
                allTags = allTags.filter(tag => {
                    // Если это системный тег - проверяем show_in_table
                    if (tag.is_system) {
                        return tag.show_in_table === true;
                    }
                    // Кастомные теги показываем всегда
                    return true;
                });
            }

            if (allTags.length === 0) {
                return '<span class="no-tags">—</span>';
            }

            return this._buildContainer(allTags, maxVisible);
        },

        /**
         * Объединяет собственные и унаследованные теги
         * @private
         */
        _mergeTags(ownTags, groupTags) {
            const allTags = [];
            const ownTagIds = new Set((ownTags || []).map(t => t.id));

            // Добавляем собственные теги
            (ownTags || []).forEach(tag => {
                allTags.push({ ...tag, inherited: false });
            });

            // Добавляем унаследованные теги (если их нет в собственных)
            if (groupTags) {
                groupTags.forEach(tag => {
                    if (!ownTagIds.has(tag.id)) {
                        allTags.push({ ...tag, inherited: true });
                    }
                });
            }

            return allTags;
        },

        /**
         * Строит контейнер с тегами
         * @private
         */
        _buildContainer(tags, maxVisible) {
            const container = document.createElement('div');
            container.className = 'table-tags-container';

            const visibleTags = tags.slice(0, maxVisible);
            const hiddenCount = tags.length - maxVisible;

            visibleTags.forEach(tag => {
                container.appendChild(this._createTagElement(tag));
            });

            if (hiddenCount > 0) {
                const more = document.createElement('span');
                more.className = 'tags-more';
                more.textContent = `+${hiddenCount}`;
                more.title = tags.slice(maxVisible).map(t => t.display_name || t.name).join(', ');
                more.setAttribute('onclick', 'event.stopPropagation()');
                container.appendChild(more);
            }

            return container.outerHTML;
        },

        /**
         * Создаёт элемент тега
         * @private
         */
        _createTagElement(tag) {
            const span = document.createElement('span');

            // Формируем классы
            let classes = ['tag'];
            if (tag.css_class) classes.push(tag.css_class);
            if (tag.inherited) classes.push('tag-inherited');
            if (tag.is_system) classes.push('tag-system');

            span.className = classes.join(' ');

            // Формируем title
            let title = tag.description || '';
            if (tag.inherited) {
                title = title ? `${title} (Унаследован от группы)` : 'Унаследован от группы';
            }
            if (title) {
                span.title = title;
            }

            // Применяем цвета из настроек тега
            if (tag.border_color) {
                span.style.borderColor = tag.border_color;
            }
            if (tag.text_color) {
                span.style.color = tag.text_color;
            }

            span.textContent = tag.display_name || tag.name;
            return span;
        }
    };

    // Экспорт в глобальную область
    window.TagsRenderer = TagsRenderer;
})();

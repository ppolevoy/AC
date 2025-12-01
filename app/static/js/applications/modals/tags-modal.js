/**
 * tags-modal.js
 * Модуль для управления тегами приложений и групп
 * Извлечено из ModalManager для улучшения поддержки кода
 */
(function() {
    'use strict';

    const TagsModal = {
        /**
         * Показывает модальное окно управления тегами для выбранных приложений
         * @param {Array} appIds - массив ID приложений
         * @param {Object} deps - зависимости
         */
        async showBatchTagsModal(appIds, deps = {}) {
            const {
                ApiService = window.ApiService,
                StateManager = window.StateManager,
                DOMUtils = window.DOMUtils,
                showModal = window.showModal,
                closeModal = window.closeModal,
                showNotification = window.showNotification,
                showError = window.showError,
                loadApplications = null
            } = deps;

            const template = document.getElementById('batch-tags-modal-template');
            if (!template) return;

            const content = template.content.cloneNode(true);
            content.querySelector('.selected-count').textContent = appIds.length;

            const tags = await ApiService.loadTags();
            const checkboxesContainer = content.querySelector('.batch-tags-checkboxes');

            // Получаем данные о тегах выбранных приложений
            const selectedApps = appIds.map(id => StateManager.getAppById(id)).filter(app => app);

            // Собираем теги: собственные и унаследованные
            const ownTagCounts = {};
            const inheritedTags = new Set();

            selectedApps.forEach(app => {
                (app.tags || []).forEach(tag => {
                    ownTagCounts[tag.name] = (ownTagCounts[tag.name] || 0) + 1;
                });
                (app.group_tags || []).forEach(tag => {
                    inheritedTags.add(tag.name);
                });
            });

            // Сохраняем начальное состояние
            const initialState = {};

            if (tags.length > 0) {
                checkboxesContainer.innerHTML = this._renderTagCheckboxes(tags, selectedApps, ownTagCounts, inheritedTags, initialState);
                this._setupPartialCheckboxes(checkboxesContainer);
            } else {
                checkboxesContainer.innerHTML = '';
            }

            showModal('Управление тегами', content);

            // Apply button handler
            document.getElementById('apply-batch-tags').addEventListener('click', async () => {
                await this._handleBatchTagsApply(appIds, initialState, {
                    StateManager, DOMUtils, showNotification, showError, closeModal, loadApplications
                });
            });
        },

        /**
         * Показывает модальное окно управления тегами группы
         * @param {number} groupId - ID группы
         * @param {string} groupName - название группы
         * @param {Object} deps - зависимости
         */
        async showGroupTagsModal(groupId, groupName, deps = {}) {
            const {
                ApiService = window.ApiService,
                showModal = window.showModal,
                closeModal = window.closeModal,
                showNotification = window.showNotification,
                showError = window.showError,
                loadApplications = null
            } = deps;

            const [allTags, groupTagsResponse] = await Promise.all([
                ApiService.loadTags(),
                fetch(`/api/app-groups/${groupId}/tags`).then(r => r.json())
            ]);

            const groupTags = groupTagsResponse.success ? groupTagsResponse.tags : [];
            const groupTagNames = new Set(groupTags.map(t => t.name));

            const tagNameToId = {};
            allTags.forEach(t => tagNameToId[t.name] = t.id);
            groupTags.forEach(t => tagNameToId[t.name] = t.id);

            const content = document.createElement('div');
            content.className = 'group-tags-container';

            if (allTags.length === 0) {
                content.innerHTML = '<p style="color: #999;">Нет доступных тегов. Создайте теги в настройках.</p>';
            } else {
                content.innerHTML = this._renderGroupTagsContent(allTags, groupTagNames);
            }

            showModal(`Теги группы: ${groupName}`, content);

            const saveBtn = document.getElementById('save-group-tags');
            if (saveBtn) {
                saveBtn.addEventListener('click', async () => {
                    await this._handleGroupTagsSave(groupId, groupTagNames, tagNameToId, {
                        showNotification, showError, closeModal, loadApplications
                    });
                });
            }
        },

        /**
         * Рендерит чекбоксы тегов для batch операции
         * @private
         */
        _renderTagCheckboxes(tags, selectedApps, ownTagCounts, inheritedTags, initialState) {
            // Разделяем теги на системные и кастомные
            const systemTags = tags.filter(t => t.is_system);
            const customTags = tags.filter(t => !t.is_system);

            let html = '';

            // Сначала кастомные теги
            if (customTags.length > 0) {
                html += customTags.map(tag => this._renderTagCheckbox(tag, selectedApps, ownTagCounts, inheritedTags, initialState)).join('');
            }

            // Затем системные теги с разделителем
            if (systemTags.length > 0) {
                html += '<div class="tags-section-divider"><span>Системные теги</span></div>';
                html += systemTags.map(tag => this._renderTagCheckbox(tag, selectedApps, ownTagCounts, inheritedTags, initialState, true)).join('');
            }

            return html;
        },

        /**
         * Рендерит один чекбокс тега
         * @private
         */
        _renderTagCheckbox(tag, selectedApps, ownTagCounts, inheritedTags, initialState, isSystemSection = false) {
            const tagStyle = [];
            if (tag.border_color) tagStyle.push(`border-color: ${tag.border_color}`);
            if (tag.text_color) tagStyle.push(`color: ${tag.text_color}`);
            const styleAttr = tagStyle.length ? `style="${tagStyle.join('; ')}"` : '';

            const count = ownTagCounts[tag.name] || 0;
            const isOwned = count === selectedApps.length;
            const isPartial = count > 0 && count < selectedApps.length;
            const isInherited = inheritedTags.has(tag.name);

            if (isOwned) {
                initialState[tag.name] = 'all';
            } else if (isPartial) {
                initialState[tag.name] = 'partial';
            } else {
                initialState[tag.name] = 'none';
            }

            const checked = isOwned || isInherited ? 'checked' : '';
            // Унаследованные теги нельзя изменять (управляются на уровне группы)
            // Системные теги можно назначать/снимать вручную
            const disabled = isInherited ? 'disabled' : '';
            const inheritedLabel = isInherited ? ' <span class="tag-status">(от группы)</span>' : '';
            const partialLabel = isPartial && !isInherited ? ` <span class="tag-status">(${count}/${selectedApps.length})</span>` : '';
            // Метка "(авто)" только для системных тегов с авто-назначением (не manual)
            const isAutoAssigned = tag.is_system && tag.trigger_type && tag.trigger_type !== 'manual';
            const systemLabel = isAutoAssigned && !isInherited ? ' <span class="tag-status tag-status-system">(авто)</span>' : '';

            const shortDescription = tag.description
                ? (tag.description.length > 40 ? tag.description.substring(0, 40) + '...' : tag.description)
                : '';
            const descriptionHtml = shortDescription
                ? `<span class="tag-modal-description" title="${tag.description || ''}">${shortDescription}</span>`
                : '';

            const tagClass = tag.is_system ? 'tag tag-system' : `tag ${tag.css_class || ''}`;

            return `
                <label class="tag-checkbox-label${tag.is_system ? ' system-tag-label' : ''}">
                    <input type="checkbox" value="${tag.name}" class="batch-tag-checkbox" ${checked} ${disabled}
                           data-initial="${initialState[tag.name]}" data-changed="false" data-is-system="${tag.is_system || false}">
                    <span class="${tagClass}" ${styleAttr}>${tag.display_name || tag.name}</span>${inheritedLabel}${partialLabel}${systemLabel}
                    ${descriptionHtml}
                </label>
            `;
        },

        /**
         * Настраивает partial чекбоксы
         * @private
         */
        _setupPartialCheckboxes(container) {
            container.querySelectorAll('.batch-tag-checkbox').forEach(cb => {
                const initial = cb.dataset.initial;
                if (initial === 'partial') {
                    cb.indeterminate = true;
                    cb.checked = false;
                }
                cb.addEventListener('change', () => {
                    cb.dataset.changed = 'true';
                    cb.indeterminate = false;
                });
            });
        },

        /**
         * Обработчик применения batch тегов
         * @private
         */
        async _handleBatchTagsApply(appIds, initialState, deps) {
            const { StateManager, DOMUtils, showNotification, showError, closeModal, loadApplications } = deps;

            const tagsToAdd = [];
            const tagsToRemove = [];

            document.querySelectorAll('.batch-tag-checkbox:not(:disabled)').forEach(cb => {
                const tagName = cb.value;
                const initial = cb.dataset.initial;
                const changed = cb.dataset.changed === 'true';
                const isChecked = cb.checked;

                if (initial === 'partial') {
                    if (changed) {
                        if (isChecked) {
                            tagsToAdd.push(tagName);
                        } else {
                            tagsToRemove.push(tagName);
                        }
                    }
                } else if (initial === 'all') {
                    if (!isChecked) {
                        tagsToRemove.push(tagName);
                    }
                } else {
                    if (isChecked) {
                        tagsToAdd.push(tagName);
                    }
                }
            });

            try {
                let addedCount = 0;
                let removedCount = 0;

                if (tagsToAdd.length > 0) {
                    const addResponse = await fetch('/api/tags/bulk-assign', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            tag_names: tagsToAdd,
                            target_type: 'instances',
                            target_ids: appIds,
                            action: 'add'
                        })
                    });
                    const addResult = await addResponse.json();
                    if (addResult.success) addedCount = addResult.count;
                }

                if (tagsToRemove.length > 0) {
                    const removeResponse = await fetch('/api/tags/bulk-assign', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            tag_names: tagsToRemove,
                            target_type: 'instances',
                            target_ids: appIds,
                            action: 'remove'
                        })
                    });
                    const removeResult = await removeResponse.json();
                    if (removeResult.success) removedCount = removeResult.count;
                }

                if (addedCount > 0 || removedCount > 0) {
                    showNotification(`Теги обновлены (добавлено: ${addedCount}, удалено: ${removedCount})`);
                } else {
                    showNotification('Изменений не было');
                }

                closeModal();

                StateManager.clearSelection();
                DOMUtils.querySelectorInTable('.app-checkbox').forEach(checkbox => {
                    checkbox.checked = false;
                });
                const selectAllCheckbox = document.getElementById('select-all');
                if (selectAllCheckbox) selectAllCheckbox.checked = false;

                if (loadApplications) await loadApplications();
            } catch (error) {
                console.error('Error in batch tags operation:', error);
                showError(error.message || 'Ошибка операции с тегами');
            }
        },

        /**
         * Рендерит контент модального окна тегов группы
         * @private
         */
        _renderGroupTagsContent(allTags, groupTagNames) {
            const checkboxesHtml = allTags.map(tag => {
                const tagStyle = [];
                if (tag.border_color) tagStyle.push(`border-color: ${tag.border_color}`);
                if (tag.text_color) tagStyle.push(`color: ${tag.text_color}`);
                const styleAttr = tagStyle.length ? `style="${tagStyle.join('; ')}"` : '';
                const checked = groupTagNames.has(tag.name) ? 'checked' : '';
                return `
                    <label class="tag-checkbox-label" style="display: block; margin: 5px 0;">
                        <input type="checkbox" value="${tag.name}" class="group-tag-checkbox" data-tag-id="${tag.id}" ${checked}>
                        <span class="tag ${tag.css_class || ''}" ${styleAttr}>${tag.display_name || tag.name}</span>
                    </label>
                `;
            }).join('');

            return `
                <div class="form-group">
                    <div class="group-tags-checkboxes">${checkboxesHtml}</div>
                </div>
                <div class="form-actions">
                    <button type="button" class="cancel-btn" onclick="closeModal()">Отмена</button>
                    <button type="button" class="submit-btn" id="save-group-tags">Сохранить</button>
                </div>
            `;
        },

        /**
         * Обработчик сохранения тегов группы
         * @private
         */
        async _handleGroupTagsSave(groupId, groupTagNames, tagNameToId, deps) {
            const { showNotification, showError, closeModal, loadApplications } = deps;

            const selectedTagNames = Array.from(document.querySelectorAll('.group-tag-checkbox:checked')).map(cb => cb.value);

            try {
                const toAdd = selectedTagNames.filter(name => !groupTagNames.has(name));
                const toRemove = [...groupTagNames].filter(name => !selectedTagNames.includes(name));

                for (const tagName of toAdd) {
                    await fetch(`/api/app-groups/${groupId}/tags`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tag_name: tagName })
                    });
                }

                for (const tagName of toRemove) {
                    const tagId = tagNameToId[tagName];
                    if (tagId) {
                        await fetch(`/api/app-groups/${groupId}/tags/${tagId}`, {
                            method: 'DELETE'
                        });
                    }
                }

                showNotification('Теги группы обновлены');
                closeModal();
                if (loadApplications) loadApplications();
            } catch (error) {
                console.error('Error updating group tags:', error);
                showError('Ошибка обновления тегов');
            }
        }
    };

    // Экспорт в глобальную область
    window.TagsModal = TagsModal;
})();

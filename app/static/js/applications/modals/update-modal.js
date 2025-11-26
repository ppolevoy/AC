/**
 * update-modal.js
 * Модуль для модальных окон обновления приложений
 *
 * ПРИМЕЧАНИЕ: Функции showSimpleUpdateModal и showTabsUpdateModal остаются в ModalManager
 * из-за сложных взаимосвязей. Этот модуль содержит вспомогательные функции.
 */
(function() {
    'use strict';

    const UpdateModal = {
        // Кэш для содержимого групп (используется в showTabsUpdateModal)
        groupContentCache: {},
        groupContentLoaded: {},

        /**
         * Функция для извлечения имени плейбука из пути
         */
        getPlaybookDisplayName(orchestrator) {
            const fileName = orchestrator.file_path.split('/').pop();
            return fileName.replace(/\.(yml|yaml)$/i, '');
        },

        /**
         * Создает HTML для выбора режима обновления
         */
        createModeRadioGroup(selectedMode = 'deliver') {
            return `
                <div class="form-group">
                    <label>Режим обновления:</label>
                    <div class="radio-group">
                        <label class="radio-label">
                            <input type="radio" name="mode" value="deliver" ${selectedMode === 'deliver' ? 'checked' : ''}> Доставить
                        </label>
                        <label class="radio-label">
                            <input type="radio" name="mode" value="immediate" ${selectedMode === 'immediate' ? 'checked' : ''}> Сейчас
                        </label>
                        <label class="radio-label">
                            <input type="radio" name="mode" value="night-restart" ${selectedMode === 'night-restart' ? 'checked' : ''}> В рестарт
                        </label>
                    </div>
                </div>
            `;
        },

        /**
         * Создает HTML для полей режима "Сейчас" (immediate)
         */
        createImmediateModeFields(orchestrators, state = {}) {
            const { orchestratorPlaybook = '', drainWaitTime = 5, restartMode = 'deliver' } = state;
            const display = restartMode === 'immediate' ? 'block' : 'none';

            return `
                <div id="immediate-mode-fields" style="display: ${display};" class="animated-fade-in">
                    <div class="form-group">
                        <label for="orchestrator-playbook">Orchestrator playbook:</label>
                        <select id="orchestrator-playbook" name="orchestrator_playbook" class="form-control">
                            <option value="none" ${orchestrators.length === 0 ? 'selected' : ''}>Без оркестрации</option>
                            ${orchestrators.map((orch, index) => {
                                const displayName = this.getPlaybookDisplayName(orch);
                                const selected = (orch.file_path === orchestratorPlaybook) ||
                                                (index === 0 && !orchestratorPlaybook) ? 'selected' : '';
                                return `<option value="${orch.file_path}" ${selected}>${displayName}</option>`;
                            }).join('')}
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="drain-wait-time">Время ожидания после drain:</label>
                        <div class="drain-wait-container">
                            <input type="number" id="drain-wait-time" name="drain_wait_time"
                                   class="form-control" min="0" max="60" value="${drainWaitTime}">
                            <span class="unit-label">минут</span>
                        </div>
                        <div class="quick-select-buttons">
                            <a href="#" class="quick-time-link" data-time="10">10</a>
                            <a href="#" class="quick-time-link" data-time="20">20</a>
                            <a href="#" class="quick-time-link" data-time="30">30</a>
                        </div>
                        <small class="form-help-text">Время ожидания после вывода инстанса из балансировки (0-60 минут)</small>
                    </div>
                </div>
            `;
        },

        /**
         * Привязывает обработчики для режима обновления
         */
        attachModeHandlers() {
            const modeRadios = document.querySelectorAll('input[name="mode"]');
            const immediateModeFields = document.getElementById('immediate-mode-fields');

            modeRadios.forEach(radio => {
                radio.addEventListener('change', function() {
                    if (this.value === 'immediate') {
                        immediateModeFields.style.display = 'block';
                        immediateModeFields.classList.add('animated-slide-down');
                    } else {
                        immediateModeFields.style.display = 'none';
                    }
                });
            });
        },

        /**
         * Привязывает обработчики для быстрого выбора времени
         */
        attachQuickTimeHandlers() {
            document.querySelectorAll('.quick-time-link').forEach(link => {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    const time = this.dataset.time;
                    const drainWaitInput = document.getElementById('drain-wait-time');
                    if (drainWaitInput) {
                        drainWaitInput.value = time;
                    }
                    document.querySelectorAll('.quick-time-link').forEach(l => l.classList.remove('active'));
                    this.classList.add('active');
                });
            });
        },

        /**
         * Очищает кэши при открытии нового модального окна
         */
        clearCaches() {
            this.groupContentCache = {};
            this.groupContentLoaded = {};
        }
    };

    // Экспорт в глобальную область
    window.UpdateModal = UpdateModal;
})();

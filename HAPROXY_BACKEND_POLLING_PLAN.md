# План реализации: Управление опросом HAProxy бэкендов

## Обзор функциональности

Добавление возможности выборочного опроса HAProxy бэкендов для снижения нагрузки и улучшения производительности системы мониторинга.

## Контекст

### Текущая ситуация
- HAProxy сервис опрашивает ВСЕ бэкенды для каждого активного инстанса
- Нет возможности отключить опрос ненужных бэкендов
- При большом количестве бэкендов создается излишняя нагрузка
- Данные всех бэкендов отображаются на странице HAProxy

### Требования
1. Добавить возможность включения/выключения опроса отдельных бэкендов
2. Интегрировать управление в существующее модальное окно "Настройка HAProxy"
3. Добавить предупреждение при отключении опроса
4. Скрывать данные отключенных бэкендов на странице HAProxy
5. Сохранять возможность восстановления опроса

## Детальный план реализации

### 1. Изменения в базе данных

#### Новое поле в таблице `haproxy_backends`
```sql
ALTER TABLE haproxy_backends
ADD COLUMN enable_polling BOOLEAN NOT NULL DEFAULT TRUE;

-- Индекс для быстрой фильтрации
CREATE INDEX idx_haproxy_backend_polling
ON haproxy_backends(enable_polling);
```

#### Миграция через Flask-Migrate
```bash
flask db migrate -m "Add enable_polling field to haproxy_backends"
flask db upgrade
```

### 2. Изменения в моделях

**Файл:** `app/models/haproxy.py`

#### Класс HAProxyBackend (после строки 92)
```python
# Backend polling configuration
enable_polling = db.Column(db.Boolean, default=True, nullable=False)
```

#### Обновление метода to_dict() (строка ~140)
```python
def to_dict(self):
    return {
        'id': self.id,
        'haproxy_instance_id': self.haproxy_instance_id,
        'backend_name': self.backend_name,
        'servers_count': self.servers_count,
        'status_stats': self.status_stats,
        'enable_polling': self.enable_polling,  # Новое поле
        'created_at': self.created_at.isoformat() if self.created_at else None,
        'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        'removed_at': self.removed_at.isoformat() if self.removed_at else None
    }
```

### 3. Изменения в API

**Файл:** `app/api/haproxy_routes.py`

#### Новый endpoint для управления опросом
```python
@bp.route('/haproxy/backends/<int:backend_id>/polling', methods=['PUT'])
def update_backend_polling(backend_id):
    """
    Включить или отключить опрос для конкретного бэкенда.

    Body:
    {
        "enable_polling": true/false
    }
    """
    try:
        data = request.json
        if 'enable_polling' not in data:
            return jsonify({'success': False, 'error': 'enable_polling field required'}), 400

        backend = HAProxyBackend.query.get(backend_id)
        if not backend:
            return jsonify({'success': False, 'error': 'Backend not found'}), 404

        old_state = backend.enable_polling
        backend.enable_polling = data['enable_polling']

        # При отключении опроса помечаем как удаленный
        if not backend.enable_polling:
            backend.soft_delete()
            logger.info(f"Backend {backend.backend_name} polling disabled and marked as removed")
        else:
            # При включении опроса восстанавливаем
            backend.restore()
            logger.info(f"Backend {backend.backend_name} polling enabled and restored")

        backend.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Polling {"enabled" if backend.enable_polling else "disabled"} for {backend.backend_name}',
            'backend': backend.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating backend polling: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
```

#### Модификация существующих endpoints
В endpoint `/haproxy/instances/<int:instance_id>/backends` добавить поддержку параметра `include_removed`:

```python
@bp.route('/haproxy/instances/<int:instance_id>/backends', methods=['GET'])
def get_instance_backends(instance_id):
    try:
        # Новый параметр для показа удаленных бэкендов
        include_removed = request.args.get('include_removed', 'false').lower() == 'true'

        query = HAProxyBackend.query.filter_by(haproxy_instance_id=instance_id)

        # Фильтрация удаленных только если не запрошено обратное
        if not include_removed:
            query = query.filter(HAProxyBackend.removed_at.is_(None))

        backends = query.order_by(HAProxyBackend.backend_name).all()

        return jsonify({
            'success': True,
            'instance_id': instance_id,
            'count': len(backends),
            'backends': [b.to_dict() for b in backends],
            'include_removed': include_removed
        }), 200
    except Exception as e:
        logger.error(f"Error getting backends: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
```

### 4. Изменения в сервисном слое

**Файл:** `app/services/haproxy_service.py`

#### Модификация метода sync_haproxy_instance() (строки 325-488)

После получения списка бэкендов от FAgent (строка ~356):

```python
# Получаем все бэкенды из БД для проверки настроек опроса
existing_backends = {
    b.backend_name: b
    for b in HAProxyBackend.query.filter_by(
        haproxy_instance_id=haproxy_instance.id
    ).all()
}

for backend_data in backends_data:
    backend_name = backend_data if isinstance(backend_data, str) else backend_data.get('name')

    # Проверяем, отключен ли опрос для этого бэкенда
    existing = existing_backends.get(backend_name)
    if existing and not existing.enable_polling:
        logger.debug(f"Skipping backend {backend_name} - polling disabled")
        continue

    # Продолжаем обработку только для бэкендов с включенным опросом
    logger.debug(f"Processing backend: {backend_name}")

    # Далее существующая логика синхронизации...
```

### 5. Изменения в Frontend

#### 5.1. Модальное окно настройки HAProxy

**Файл:** `app/static/js/servers/server-details.js`

##### Модификация функции loadHAProxyBackends() (строки 845-931)

Изменить HTML генерацию для добавления чекбокса (строки ~880-908):

```javascript
backendsHtml += `
    <div style="padding: 10px 12px; background: #252525; border: 1px solid #374151; border-radius: 4px; margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <!-- Новый чекбокс для управления опросом -->
                <label style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
                    <input type="checkbox"
                           id="polling-backend-${backend.id}"
                           ${backend.enable_polling !== false ? 'checked' : ''}
                           onchange="toggleBackendPolling(${backend.id}, '${backend.backend_name}', this.checked)"
                           style="width: 16px; height: 16px; cursor: pointer; accent-color: #2563eb;">
                    <span style="font-size: 12px; color: #888;">Опрос</span>
                </label>
                <!-- Имя бэкенда -->
                <div style="font-size: 14px; font-weight: 500; color: ${backend.removed_at ? '#888' : '#fff'};">
                    ${backend.backend_name}
                    ${backend.removed_at ? '<span style="color: #ef4444; font-size: 11px; margin-left: 8px;">(Отключен)</span>' : ''}
                </div>
            </div>
            <div style="display: flex; gap: 12px; font-size: 12px; align-items: center;">
                ${statusHtml}
                <span style="color: #6b7280;">Всего: ${backend.servers_count || 0}</span>
            </div>
        </div>
    </div>
`;
```

##### Добавление функции toggleBackendPolling()

```javascript
async function toggleBackendPolling(backendId, backendName, isEnabled) {
    try {
        // Показать предупреждение при отключении
        if (!isEnabled) {
            const confirmHtml = `
                <div style="padding: 20px;">
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                        <span style="font-size: 24px;">⚠️</span>
                        <h3 style="margin: 0; color: #fff;">Отключение опроса бэкенда</h3>
                    </div>

                    <p style="color: #d1d5db; margin-bottom: 16px;">
                        Вы собираетесь отключить опрос для бэкенда <strong style="color: #fff;">"${backendName}"</strong>.
                    </p>

                    <div style="background: #374151; border-radius: 8px; padding: 12px; margin-bottom: 16px;">
                        <p style="margin: 0 0 8px 0; color: #fbbf24; font-weight: 500;">
                            ⚠️ Это приведет к следующим последствиям:
                        </p>
                        <ul style="margin: 0; padding-left: 20px; color: #d1d5db;">
                            <li>Данные этого бэкенда перестанут обновляться</li>
                            <li>Бэкенд будет скрыт на странице HAProxy</li>
                            <li>Мониторинг серверов в этом бэкенде прекратится</li>
                        </ul>
                    </div>

                    <p style="color: #9ca3af; font-size: 14px; margin-bottom: 20px;">
                        <strong>Примечание:</strong> Существующие данные будут сохранены.
                        Вы сможете включить опрос снова в любое время.
                    </p>

                    <div style="text-align: center; color: #fff; font-weight: 500;">
                        Вы уверены, что хотите продолжить?
                    </div>
                </div>
            `;

            const modal = ModalManager.confirm(
                'Отключение опроса бэкенда',
                confirmHtml,
                async () => {
                    await performBackendPollingToggle(backendId, isEnabled);
                },
                () => {
                    // При отмене возвращаем чекбокс в исходное состояние
                    document.getElementById(`polling-backend-${backendId}`).checked = true;
                },
                {
                    confirmText: 'Отключить опрос',
                    cancelText: 'Отмена',
                    confirmClass: 'danger'
                }
            );
        } else {
            // Включение опроса без предупреждения
            await performBackendPollingToggle(backendId, isEnabled);
        }
    } catch (error) {
        console.error('Error toggling backend polling:', error);
        showError('Ошибка при изменении настроек опроса');
        // Возвращаем чекбокс в исходное состояние
        document.getElementById(`polling-backend-${backendId}`).checked = !isEnabled;
    }
}

async function performBackendPollingToggle(backendId, isEnabled) {
    try {
        const response = await fetch(`/api/haproxy/backends/${backendId}/polling`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ enable_polling: isEnabled })
        });

        const data = await response.json();

        if (data.success) {
            showNotification(
                isEnabled
                    ? '✓ Опрос бэкенда включен'
                    : '⚠️ Опрос бэкенда отключен',
                isEnabled ? 'success' : 'warning'
            );

            // Обновить отображение бэкенда
            const checkbox = document.getElementById(`polling-backend-${backendId}`);
            if (checkbox) {
                const backendElement = checkbox.closest('div[style*="padding: 10px 12px"]');
                if (backendElement && !isEnabled) {
                    // Визуально пометить как отключенный
                    backendElement.style.opacity = '0.7';
                    backendElement.style.borderColor = '#6b7280';
                } else if (backendElement && isEnabled) {
                    // Восстановить визуальное состояние
                    backendElement.style.opacity = '1';
                    backendElement.style.borderColor = '#374151';
                }
            }
        } else {
            throw new Error(data.error || 'Не удалось обновить настройки');
        }
    } catch (error) {
        showError(error.message || 'Ошибка соединения с сервером');
        // Возвращаем чекбокс в исходное состояние
        document.getElementById(`polling-backend-${backendId}`).checked = !isEnabled;
    }
}
```

#### 5.2. Страница HAProxy

**Файл:** `app/templates/haproxy.html`

##### Добавление фильтра для показа удаленных бэкендов

В секцию фильтров (после строки ~45):
```html
<div class="filter-group">
    <label class="checkbox-label">
        <input type="checkbox" id="show-removed-backends" class="filter-checkbox">
        <span>Показать отключенные бэкенды</span>
    </label>
</div>
```

**Файл:** `app/static/js/haproxy/manager.js`

##### Модификация loadData() для поддержки фильтра

```javascript
async loadData() {
    try {
        // Проверяем, нужно ли показывать удаленные бэкенды
        const showRemoved = document.getElementById('show-removed-backends')?.checked || false;

        // Загружаем бэкенды с учетом фильтра
        const backends = await HAProxyAPI.getInstanceBackends(
            instanceId,
            { include_removed: showRemoved }
        );

        // ... остальная логика
    } catch (error) {
        console.error('Error loading data:', error);
    }
}
```

**Файл:** `app/static/js/haproxy/ui.js`

##### Визуальное отличие для отключенных бэкендов

```javascript
renderBackend(backend) {
    const isRemoved = backend.removed_at != null;
    const isPollingDisabled = backend.enable_polling === false;

    let statusClass = '';
    let statusBadge = '';

    if (isRemoved || isPollingDisabled) {
        statusClass = 'removed-backend';
        statusBadge = `<span class="badge badge-danger">Отключен</span>`;
    }

    return `
        <div class="backend-item ${statusClass}">
            <div class="backend-header">
                <span class="backend-name">${backend.backend_name}</span>
                ${statusBadge}
                ${isRemoved ? `<span class="removed-date">Отключен: ${formatDate(backend.removed_at)}</span>` : ''}
            </div>
            <!-- остальной контент -->
        </div>
    `;
}
```

**Файл:** `app/static/css/haproxy.css`

##### Стили для отключенных бэкендов

```css
.removed-backend {
    opacity: 0.6;
    background-color: rgba(107, 114, 128, 0.1);
}

.removed-backend .backend-name {
    color: #6b7280;
    text-decoration: line-through;
}

.removed-backend .badge-danger {
    background-color: #ef4444;
    color: white;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    margin-left: 8px;
}

.removed-date {
    color: #6b7280;
    font-size: 12px;
    margin-left: auto;
}
```

### 6. Фоновая очистка старых данных

**Файл:** `app/tasks/monitoring.py`

#### Добавление задачи очистки (опционально)

```python
def cleanup_old_haproxy_backends():
    """
    Удаление бэкендов, которые были помечены как удаленные более 90 дней назад.
    Запускается раз в неделю.
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=90)

        # Находим старые удаленные бэкенды
        old_backends = HAProxyBackend.query.filter(
            HAProxyBackend.removed_at.isnot(None),
            HAProxyBackend.removed_at < cutoff_date
        ).all()

        deleted_count = 0
        for backend in old_backends:
            # Удаляем связанные серверы
            HAProxyServer.query.filter_by(backend_id=backend.id).delete()

            logger.info(f"Permanently deleting old backend {backend.backend_name} "
                       f"(removed on {backend.removed_at})")

            db.session.delete(backend)
            deleted_count += 1

        if deleted_count > 0:
            db.session.commit()
            logger.info(f"Cleaned up {deleted_count} old HAProxy backends")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cleaning up old HAProxy backends: {e}", exc_info=True)

# Добавить в scheduler (если используется)
scheduler.add_job(
    cleanup_old_haproxy_backends,
    'cron',
    day_of_week='sun',
    hour=3,
    minute=0,
    id='cleanup_old_haproxy_backends'
)
```

### 7. Конфигурация

**Файл:** `app/config.py`

```python
# HAProxy Backend Polling Configuration
HAPROXY_BACKEND_POLLING_ENABLED = os.environ.get('HAPROXY_BACKEND_POLLING_ENABLED', 'true').lower() == 'true'
HAPROXY_BACKEND_CLEANUP_DAYS = int(os.environ.get('HAPROXY_BACKEND_CLEANUP_DAYS', '90'))
```

## Порядок реализации

### Этап 1: База данных и модели (30 минут)
1. Создать и применить миграцию для поля `enable_polling`
2. Обновить модель `HAProxyBackend`
3. Обновить метод `to_dict()`

### Этап 2: Backend API (1 час)
1. Добавить новый endpoint для управления опросом
2. Модифицировать существующие endpoints для поддержки фильтра
3. Протестировать через Postman/curl

### Этап 3: Сервисный слой (1 час)
1. Модифицировать `sync_haproxy_instance()` для пропуска отключенных бэкендов
2. Добавить логирование
3. Протестировать синхронизацию

### Этап 4: Frontend - модальное окно (2 часа)
1. Добавить чекбоксы в карточки бэкендов
2. Реализовать функцию `toggleBackendPolling()`
3. Добавить диалог предупреждения
4. Протестировать взаимодействие

### Этап 5: Frontend - страница HAProxy (1 час)
1. Добавить фильтр "Показать отключенные"
2. Реализовать визуальное отличие для отключенных бэкендов
3. Добавить CSS стили
4. Протестировать отображение

### Этап 6: Фоновая очистка (30 минут)
1. Добавить задачу очистки старых данных
2. Настроить расписание запуска
3. Добавить конфигурационные параметры

### Этап 7: Тестирование (1 час)
1. Полное end-to-end тестирование
2. Проверка edge cases
3. Тестирование производительности

## Тестовые сценарии

### Сценарий 1: Отключение опроса бэкенда
1. Открыть страницу сервера `/server/{id}`
2. Нажать "Настройка HAProxy"
3. Развернуть инстанс HAProxy
4. Снять галочку "Опрос" у бэкенда
5. Подтвердить в диалоге предупреждения
6. Проверить, что бэкенд помечен как отключенный
7. Перейти на страницу HAProxy
8. Убедиться, что бэкенд не отображается

### Сценарий 2: Включение опроса бэкенда
1. В модальном окне поставить галочку "Опрос"
2. Проверить уведомление об успехе
3. Дождаться синхронизации
4. Проверить, что бэкенд появился на странице HAProxy

### Сценарий 3: Показ отключенных бэкендов
1. На странице HAProxy включить фильтр "Показать отключенные"
2. Проверить, что отключенные бэкенды отображаются с визуальным отличием
3. Проверить наличие badge "Отключен" и даты

## Риски и митигация

### Риск 1: Потеря данных при случайном отключении
**Митигация:**
- Диалог предупреждения с подтверждением
- Возможность восстановления через включение опроса
- Сохранение данных в БД при soft delete

### Риск 2: Накопление старых данных
**Митигация:**
- Автоматическая очистка через 90 дней
- Конфигурируемый период хранения

### Риск 3: Путаница с отключенными бэкендами
**Митигация:**
- Четкая визуальная индикация
- Фильтр для показа/скрытия
- Информативные уведомления

## Дополнительные улучшения (будущее)

1. **Массовое управление**: Возможность включить/выключить опрос для нескольких бэкендов
2. **Расписание опроса**: Возможность настроить расписание опроса (только в рабочие часы)
3. **Приоритеты опроса**: Разная частота опроса для разных бэкендов
4. **Уведомления**: Email/Slack уведомления при отключении критичных бэкендов
5. **Аудит**: Полный лог изменений настроек опроса

## Зависимости

- PostgreSQL с поддержкой индексов
- Flask-Migrate для миграций
- Существующая инфраструктура HAProxy мониторинга
- FAgent API для получения данных о бэкендах

## Совместимость

- Обратная совместимость: все существующие бэкенды будут иметь `enable_polling=true`
- Возможность отключения функции через конфигурацию
- Не влияет на существующие API endpoints (только расширяет)
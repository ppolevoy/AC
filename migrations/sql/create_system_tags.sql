-- Создание системных тегов
-- Безопасно запускать повторно: ON CONFLICT DO NOTHING

INSERT INTO tags (name, display_name, description, is_system, show_in_table, tag_type, border_color, text_color, icon, css_class)
VALUES
    ('haproxy', 'H', 'Приложение связано с HAProxy backend', TRUE, TRUE, 'system', '#28a745', '#28a745', '●', 'tag-system'),
    ('eureka', 'E', 'Приложение зарегистрировано в Eureka', TRUE, TRUE, 'system', '#007bff', '#007bff', '●', 'tag-system'),
    ('docker', 'docker', 'Docker-контейнер', TRUE, TRUE, 'system', '#2496ed', '#2496ed', '●', 'tag-system'),
    ('disable', 'disable', 'Отключенное приложение', TRUE, FALSE, 'system', '#6c757d', '#6c757d', '●', 'tag-system'),
    ('system', 'SYS', 'Системное приложение', TRUE, FALSE, 'system', '#6f42c1', '#6f42c1', '●', 'tag-system'),
    ('smf', 'smf', 'SMF сервис (Solaris)', TRUE, FALSE, 'system', '#fd7e14', '#fd7e14', '●', 'tag-system'),
    ('sysctl', 'sysctl', 'Systemctl сервис', TRUE, FALSE, 'system', '#20c997', '#20c997', '●', 'tag-system'),
    ('ver.lock', 'v.lock', 'Блокировка обновлений', TRUE, FALSE, 'system', '#dc3545', '#dc3545', '●', 'tag-system'),
    ('status.lock', 's.lock', 'Блокировка start/stop/restart', TRUE, FALSE, 'system', '#ffc107', '#856404', '●', 'tag-system'),
    ('pending_removal', 'DEL', 'Приложение будет удалено (offline > N дней)', TRUE, TRUE, 'system', '#dc3545', '#dc3545', '●', 'tag-system')
ON CONFLICT (name) DO NOTHING;

# app/services/orchestrator_parser.py
"""
Парсер метаданных для orchestrator playbooks.
Поддерживает два формата:
1. Структурированный (orchestrator_metadata:)
2. Простой формат в комментариях (Обязательные параметры:)
"""

import re
import os
import logging

logger = logging.getLogger(__name__)


def parse_orchestrator_metadata(file_content, filename):
    """
    Парсит метаданные из содержимого orchestrator playbook.

    Args:
        file_content: содержимое YAML файла (строка)
        filename: имя файла (для fallback и логирования)

    Returns:
        dict с метаданными или None, если парсинг не удался
    """
    try:
        # Извлечь блок комментариев из начала файла (первые 150 строк)
        lines = file_content.split('\n')[:150]
        comment_block = '\n'.join(lines)

        # Попытка парсинга структурированного формата
        metadata = parse_structured_metadata(comment_block)

        # Если не удалось, попробовать простой формат
        if not metadata or not metadata.get('name'):
            metadata = parse_simple_metadata(comment_block, filename)

        # Если ничего не найдено, генерируем fallback метаданные
        if not metadata or not metadata.get('name'):
            logger.warning(f"Metadata not found in {filename}, generating fallback")
            metadata = generate_fallback_metadata(filename)

        # Сохранить необработанный блок для отладки
        metadata['raw_metadata'] = {
            'comment_block': comment_block[:500]  # первые 500 символов
        }

        return metadata

    except Exception as e:
        logger.error(f"Error parsing metadata from {filename}: {e}")
        return generate_fallback_metadata(filename)


def parse_structured_metadata(comment_block):
    """
    Парсит структурированный формат метаданных:

    # orchestrator_metadata:
    #   name: "..."
    #   version: "..."
    #   description: "..."
    #
    # required_params:
    #   param_name:
    #     type: string
    #     description: "..."
    """
    metadata = {
        'name': None,
        'version': None,
        'description': None,
        'required_params': {},
        'optional_params': {}
    }

    # Поиск основных полей
    metadata['name'] = extract_field(comment_block, r'#\s*name:\s*["\']?(.+?)["\']?\s*$')
    metadata['version'] = extract_field(comment_block, r'#\s*version:\s*["\']?(.+?)["\']?\s*$')
    metadata['description'] = extract_field(comment_block, r'#\s*description:\s*["\']?(.+?)["\']?\s*$')

    # Если нашли хотя бы имя, пытаемся парсить параметры
    if metadata['name']:
        metadata['required_params'] = parse_structured_params_section(
            comment_block,
            section_name='required_params'
        )
        metadata['optional_params'] = parse_structured_params_section(
            comment_block,
            section_name='optional_params'
        )

    return metadata if metadata['name'] else None


def parse_simple_metadata(comment_block, filename=None):
    """
    Парсит простой формат из комментариев (как в orchestrator-50-50.v1.1.yml):

    # Playbook для автоматизированного обновления приложений
    # Поддерживает стратегию rolling update 50/50
    #
    # Обязательные параметры:
    #   app_name       - Список экземпляров приложения
    #   distr_url      - URL дистрибутива
    #
    # Опциональные параметры:
    #   wait_after_update - Время ожидания (по умолчанию 1800)
    """
    metadata = {
        'name': None,
        'version': None,
        'description': None,
        'required_params': {},
        'optional_params': {}
    }

    # Извлечь описание из первых строк комментариев
    description_lines = []
    for line in comment_block.split('\n'):
        line = line.strip()
        if line.startswith('#') and not any(keyword in line for keyword in
            ['параметры:', 'params:', 'Использование:', 'Usage:', '---', '===']):
            cleaned = line.lstrip('#').strip()
            if cleaned and not cleaned.startswith('orchestrator'):
                description_lines.append(cleaned)
        if len(description_lines) >= 3:
            break

    if description_lines:
        metadata['description'] = ' '.join(description_lines[:2])  # первые 2 строки
        metadata['name'] = description_lines[0][:128]  # первая строка как имя

    # Извлечь версию из имени файла если filename передан
    # Например: orchestrator-50-50.v1.1.yml -> 1.1
    if filename:
        version_match = re.search(r'\.v?(\d+\.?\d*\.?\d*)', filename)
        if version_match:
            metadata['version'] = version_match.group(1)

    # Парсинг параметров из простого формата
    metadata['required_params'] = parse_simple_params_format(
        comment_block,
        required=True
    )

    metadata['optional_params'] = parse_simple_params_format(
        comment_block,
        required=False
    )

    return metadata if metadata['name'] else None


def parse_structured_params_section(comment_block, section_name='required_params'):
    """
    Парсит секцию параметров в структурированном формате:

    # required_params:
    #   param_name:
    #     type: string
    #     description: "..."
    #     example: "..."
    """
    params = {}

    # Найти секцию
    pattern = rf'#\s*{section_name}:\s*$(.*?)(?=\n#\s*\w+:|$)'
    match = re.search(pattern, comment_block, re.MULTILINE | re.DOTALL)

    if not match:
        return params

    section_content = match.group(1)

    # Парсинг каждого параметра
    # Формат: #   param_name:\n#     type: ...\n#     description: ...
    param_pattern = r'#\s+(\w+):\s*$((?:\n#\s+\w+:.*$)*)'

    for param_match in re.finditer(param_pattern, section_content, re.MULTILINE):
        param_name = param_match.group(1)
        param_content = param_match.group(2)

        # Извлечь поля параметра
        param_type = extract_field(param_content, r'#\s+type:\s*(\w+)')
        param_desc = extract_field(param_content, r'#\s+description:\s*["\']?(.+?)["\']?\s*$')
        param_default = extract_field(param_content, r'#\s+default:\s*(.+?)\s*$')

        if param_desc:
            if param_default:
                params[param_name] = {
                    'description': param_desc,
                    'type': param_type or 'string',
                    'default': param_default
                }
            else:
                params[param_name] = param_desc

    return params


def parse_simple_params_format(comment_block, required=True):
    """
    Парсит упрощенный формат параметров:

    # Обязательные параметры:
    #   app_name       - Список экземпляров (например: bestapp_1,bestapp_3)
    #   distr_url      - URL дистрибутива

    # Опциональные параметры:
    #   wait_after_update - Время ожидания (по умолчанию 300 сек)
    """
    section_names = [
        'Обязательные параметры:' if required else 'Опциональные параметры:',
        'Required parameters:' if required else 'Optional parameters:',
        'required_params:' if required else 'optional_params:'
    ]

    params = {}

    for section_name in section_names:
        # Найти секцию (регистронезависимый поиск)
        # Ищем строку с section_name, затем захватываем все последующие строки с отступом
        # Останавливаемся когда встречаем:
        # - строку без отступа (другую секцию)
        # - пустую строку (только # без текста)
        # - начало YAML (---)
        # Паттерн: # section_name, затем строки вида #   param - description
        pattern = rf'#\s*{re.escape(section_name)}\s*$((?:\n#\s+.+)*)'
        match = re.search(pattern, comment_block, re.MULTILINE | re.IGNORECASE)

        if not match:
            continue

        section_content = match.group(1)
        logger.info(f"Found section '{section_name}', content length: {len(section_content)}")

        # Парсинг строк параметров
        for line in section_content.split('\n'):
            # Убираем # и заменяем табы на пробелы
            line = line.strip('#').replace('\t', '    ').strip()

            if not line:
                continue

            # Убрать маркеры списка (* - •) в начале (с любым количеством пробелов)
            line = re.sub(r'^\s*[\*\-\•]\s*', '', line).strip()

            if not line:
                continue

            # Формат с default: param_name - Description (по умолчанию VALUE)
            match_default = re.match(r'(\w+)\s+-\s+(.+?)\s+\(по умолчанию\s+(.+?)\)\s*$', line)
            if match_default:
                param_name = match_default.group(1)
                description = match_default.group(2).strip()
                default_value = match_default.group(3).strip()

                params[param_name] = {
                    'description': description,
                    'default': parse_value(default_value)
                }
                logger.info(f"Parsed param with default: {param_name}")
                continue

            # Формат без default: param_name - Description
            # Используем жадное совпадение (.+) вместо не жадного (.+?)
            match_simple = re.match(r'(\w+)\s+-\s+(.+)\s*$', line)
            if match_simple:
                param_name = match_simple.group(1)
                description = match_simple.group(2).strip()

                params[param_name] = description
                logger.info(f"Parsed param: {param_name} = '{description[:30]}...'")

        if not params:
            logger.warning(f"No params found in section ({'required' if required else 'optional'})")

    logger.info(f"Parsed {len(params)} params from section ({'required' if required else 'optional'})")
    return params


def extract_field(text, pattern):
    """Извлекает значение поля по регулярному выражению"""
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_value(value_str):
    """Пытается преобразовать строковое значение в правильный тип"""
    value_str = value_str.strip()

    # Попытка преобразовать в число
    if value_str.isdigit():
        return int(value_str)

    # Попытка преобразовать в float
    try:
        return float(value_str)
    except ValueError:
        pass

    # Булевы значения
    if value_str.lower() in ('true', 'yes', 'да'):
        return True
    if value_str.lower() in ('false', 'no', 'нет'):
        return False

    # Удалить кавычки
    if (value_str.startswith('"') and value_str.endswith('"')) or \
       (value_str.startswith("'") and value_str.endswith("'")):
        return value_str[1:-1]

    return value_str


def generate_fallback_metadata(filename):
    """
    Генерирует минимальные метаданные из имени файла.
    Используется когда парсинг метаданных не удался.

    Args:
        filename: имя файла (может быть с путем или без)
    """
    # Извлечь только имя файла если передан путь
    basename = os.path.basename(filename)
    name_without_ext = os.path.splitext(basename)[0]

    # Извлечь версию из имени файла
    version_match = re.search(r'v?(\d+\.?\d*\.?\d*)', name_without_ext)
    version = version_match.group(1) if version_match else '1.0'

    # Создать человекочитаемое имя из имени файла
    name = name_without_ext.replace('_', ' ').replace('-', ' ').title()

    logger.info(f"Generated fallback metadata for {filename}: name={name}, version={version}")

    return {
        'name': name,
        'version': version,
        'description': f'Orchestrator playbook (auto-generated from filename)',
        'required_params': {},
        'optional_params': {},
        'raw_metadata': {
            'fallback': True,
            'filename': basename
        }
    }


def validate_metadata(metadata):
    """
    Валидирует метаданные.
    Возвращает True если метаданные валидны, иначе False.
    """
    if not metadata:
        return False

    # Обязательные поля
    if not metadata.get('name'):
        return False

    # Проверка структуры
    if not isinstance(metadata.get('required_params', {}), dict):
        return False

    if not isinstance(metadata.get('optional_params', {}), dict):
        return False

    return True

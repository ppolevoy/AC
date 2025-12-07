# app/core/playbook_parameters.py
"""
Единая модель параметров для Ansible playbooks.

Этот модуль предоставляет единственную точку парсинга параметров в системе,
устраняя дублирование кода и обеспечивая консистентную обработку типов.

Поддерживаемые форматы параметров:
- Динамические: {param} - значение берётся из контекста выполнения
- Явные: {param=value} - значение задано в пути к playbook

Важно: Все значения для Ansible преобразуются в строки.
Boolean значения передаются как "true"/"false" (строки).
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)


@dataclass
class PlaybookParameter:
    """
    Единица параметра playbook.

    Attributes:
        name: Имя параметра (например: 'server', 'app', 'unpack')
        value: Значение параметра (None для динамических параметров)
        is_explicit: True если параметр задан явно как {param=value}
    """
    name: str
    value: Optional[str] = None
    is_explicit: bool = False

    def __post_init__(self):
        """Нормализация значения после создания."""
        if self.value is not None:
            # Нормализуем boolean значения к строкам
            if isinstance(self.value, bool):
                self.value = str(self.value).lower()
            elif isinstance(self.value, str):
                # Приводим строковые boolean к нижнему регистру
                if self.value.lower() in ('true', 'false'):
                    self.value = self.value.lower()
                else:
                    self.value = str(self.value)
            else:
                self.value = str(self.value)


@dataclass
class ParsedPlaybookConfig:
    """
    Результат парсинга пути к playbook с параметрами.

    Attributes:
        path: Чистый путь к playbook файлу (без параметров)
        parameters: Список распарсенных параметров
        raw_input: Исходная строка до парсинга (для отладки)
    """
    path: str
    parameters: List[PlaybookParameter] = field(default_factory=list)
    raw_input: str = ""

    def get_explicit_params(self) -> Dict[str, str]:
        """Возвращает словарь явно заданных параметров {name: value}."""
        return {
            p.name: p.value
            for p in self.parameters
            if p.is_explicit and p.value is not None
        }

    def get_dynamic_param_names(self) -> List[str]:
        """Возвращает список имён динамических параметров."""
        return [p.name for p in self.parameters if not p.is_explicit]

    def has_parameter(self, name: str) -> bool:
        """Проверяет наличие параметра по имени."""
        return any(p.name == name for p in self.parameters)


class PlaybookParameterParser:
    """
    Stateless парсер параметров playbook.

    Единственная точка парсинга параметров в системе.
    Обеспечивает консистентную обработку типов и форматов.

    Примеры использования:
        >>> config = PlaybookParameterParser.parse("playbook.yml {server} {app}")
        >>> config.path
        'playbook.yml'
        >>> len(config.parameters)
        2

        >>> config = PlaybookParameterParser.parse("playbook.yml {unpack=true}")
        >>> config.parameters[0].value
        'true'
        >>> config.parameters[0].is_explicit
        True
    """

    # Regex для поиска параметров в фигурных скобках
    PARAM_PATTERN = re.compile(r'\{([^}]+)\}')

    # Безопасные паттерны для валидации
    SAFE_PARAM_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    SAFE_PARAM_VALUE_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\./:\@\=\s]+$')

    # Доступные динамические переменные (для документации и валидации)
    AVAILABLE_VARIABLES = {
        'server': 'Имя сервера',
        'app': 'Имя приложения',
        'app_name': 'Имя приложения (алиас для app)',
        'action': 'Действие для управления приложением (start, stop, restart)',
        'image_url': 'URL до docker image',
        'distr_url': 'URL артефакта/дистрибутива',
        'mode': 'Режим обновления (deliver, immediate, night-restart)',
        'app_id': 'ID приложения в БД',
        'server_id': 'ID сервера в БД',
        'app_instances': 'Список составных имен server::app для orchestrator',
        'drain_delay': 'Время ожидания после drain в секундах',
        'update_playbook': 'Имя playbook для обновления',
        'wait_after_update': 'Время ожидания после обновления в секундах',
        'haproxy_api_url': 'URL HAProxy API для orchestrator',
        'haproxy_backend': 'Имя backend в HAProxy'
    }

    @classmethod
    def parse(cls, playbook_path_with_params: str) -> ParsedPlaybookConfig:
        """
        Парсит путь к playbook с параметрами.

        Args:
            playbook_path_with_params: Строка вида "/path/playbook.yml {param1} {param2=value}"

        Returns:
            ParsedPlaybookConfig с путём и списком параметров

        Examples:
            >>> config = PlaybookParameterParser.parse("/playbook.yml {server} {app}")
            >>> config.path
            '/playbook.yml'

            >>> config = PlaybookParameterParser.parse("/playbook.yml {unpack=true}")
            >>> config.parameters[0].is_explicit
            True
        """
        if not playbook_path_with_params:
            return ParsedPlaybookConfig(path="", raw_input="")

        raw_input = playbook_path_with_params
        parameters = []

        # Находим все параметры
        for match in cls.PARAM_PATTERN.findall(playbook_path_with_params):
            param = cls._parse_single_param(match)
            if param:
                parameters.append(param)

        # Извлекаем чистый путь (удаляем все параметры)
        path = cls.PARAM_PATTERN.sub('', playbook_path_with_params).strip()
        # Убираем лишние пробелы
        path = ' '.join(path.split())

        config = ParsedPlaybookConfig(
            path=path,
            parameters=parameters,
            raw_input=raw_input
        )

        logger.debug(
            f"Parsed playbook config: path='{path}', "
            f"params={[p.name for p in parameters]}"
        )

        return config

    @classmethod
    def _parse_single_param(cls, match: str) -> Optional[PlaybookParameter]:
        """
        Парсит одиночный параметр из match строки.

        Args:
            match: Содержимое внутри фигурных скобок (например: "server" или "unpack=true")

        Returns:
            PlaybookParameter или None если невалидный
        """
        match = match.strip()
        if not match:
            return None

        if '=' in match:
            # Явный параметр: {param=value}
            parts = match.split('=', 1)
            param_name = parts[0].strip()
            param_value = parts[1].strip() if len(parts) > 1 else ""

            # Нормализуем boolean
            if param_value.lower() in ('true', 'false'):
                param_value = param_value.lower()

            return PlaybookParameter(
                name=param_name,
                value=param_value,
                is_explicit=True
            )
        else:
            # Динамический параметр: {param}
            return PlaybookParameter(
                name=match,
                value=None,
                is_explicit=False
            )

    @classmethod
    def to_extra_vars(
        cls,
        config: ParsedPlaybookConfig,
        context: Dict[str, Any],
        skip_empty: bool = True
    ) -> Dict[str, str]:
        """
        Формирует extra_vars для ansible-playbook на основе конфигурации и контекста.

        Args:
            config: Распарсенная конфигурация playbook
            context: Словарь с контекстными значениями для динамических параметров
            skip_empty: Пропускать параметры с пустыми значениями

        Returns:
            Dict[str, str] - словарь параметров, готовый для передачи в ansible

        Note:
            Все значения преобразуются в строки для Ansible.
            Boolean значения становятся "true" или "false".
        """
        extra_vars = {}

        for param in config.parameters:
            if param.is_explicit:
                # Явный параметр - используем заданное значение
                if param.value is not None:
                    sanitized = cls._sanitize_value(param.value)
                    extra_vars[param.name] = sanitized
                elif not skip_empty:
                    extra_vars[param.name] = ""
            else:
                # Динамический параметр - берём из контекста
                if param.name in context:
                    value = context[param.name]
                    if value is not None:
                        # Преобразуем в строку
                        str_value = cls._to_string(value)
                        if str_value or not skip_empty:
                            extra_vars[param.name] = str_value
                    elif not skip_empty:
                        extra_vars[param.name] = ""

        logger.debug(f"Built extra_vars with {len(extra_vars)} parameters")
        return extra_vars

    @classmethod
    def validate_parameters(
        cls,
        config: ParsedPlaybookConfig,
        strict: bool = False
    ) -> tuple[bool, List[str]]:
        """
        Валидирует параметры playbook.

        Args:
            config: Распарсенная конфигурация
            strict: В строгом режиме неизвестные динамические параметры считаются ошибкой

        Returns:
            Tuple[bool, List[str]] - (все параметры валидны, список ошибок)
        """
        errors = []

        for param in config.parameters:
            # Проверка имени параметра
            if not cls.SAFE_PARAM_NAME_PATTERN.match(param.name):
                errors.append(f"Небезопасное имя параметра: '{param.name}'")
                continue

            if param.is_explicit:
                # Проверка значения явного параметра
                if param.value and not cls.SAFE_PARAM_VALUE_PATTERN.match(param.value):
                    errors.append(
                        f"Небезопасное значение параметра: '{param.name}={param.value}'"
                    )
            elif strict:
                # В строгом режиме проверяем известность динамического параметра
                if param.name not in cls.AVAILABLE_VARIABLES:
                    errors.append(f"Неизвестный динамический параметр: '{param.name}'")

        return len(errors) == 0, errors

    @classmethod
    def _sanitize_value(cls, value: str) -> str:
        """
        Санитизация значения для безопасной передачи в ansible.

        Args:
            value: Исходное значение

        Returns:
            Санитизированное значение
        """
        if not value:
            return value

        # Экранируем специальные символы для shell
        value = value.replace('\\', '\\\\')
        value = value.replace('"', '\\"')
        value = value.replace('$', '\\$')
        value = value.replace('`', '\\`')

        return value

    @classmethod
    def _to_string(cls, value: Any) -> str:
        """
        Преобразует значение в строку для Ansible.

        Args:
            value: Любое значение

        Returns:
            Строковое представление
        """
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()  # True -> "true", False -> "false"
        return str(value)

    @classmethod
    def build_playbook_path_with_params(
        cls,
        base_path: str,
        explicit_params: Dict[str, Any] = None,
        dynamic_params: List[str] = None
    ) -> str:
        """
        Строит путь к playbook с параметрами.

        Args:
            base_path: Базовый путь к playbook
            explicit_params: Словарь явных параметров {name: value}
            dynamic_params: Список имён динамических параметров

        Returns:
            Строка вида "/path/playbook.yml {param1=value1} {param2}"
        """
        parts = [base_path]

        if explicit_params:
            for name, value in explicit_params.items():
                str_value = cls._to_string(value)
                parts.append(f'{{{name}={str_value}}}')

        if dynamic_params:
            for name in dynamic_params:
                parts.append(f'{{{name}}}')

        return ' '.join(parts)

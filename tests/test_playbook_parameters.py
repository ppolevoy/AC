# tests/test_playbook_parameters.py
"""
Тесты для единой модели параметров playbook.

Покрывает:
- Парсинг динамических параметров {param}
- Парсинг явных параметров {param=value}
- Консистентность boolean значений (всегда строки для Ansible)
- Извлечение чистого пути из строки с параметрами
- Формирование extra_vars для Ansible
"""

import pytest
from app.core.playbook_parameters import (
    PlaybookParameter,
    ParsedPlaybookConfig,
    PlaybookParameterParser
)


class TestPlaybookParameter:
    """Тесты для dataclass PlaybookParameter."""

    def test_dynamic_parameter(self):
        """Динамический параметр без значения."""
        param = PlaybookParameter(name="server")
        assert param.name == "server"
        assert param.value is None
        assert param.is_explicit is False

    def test_explicit_parameter(self):
        """Явный параметр с значением."""
        param = PlaybookParameter(name="unpack", value="true", is_explicit=True)
        assert param.name == "unpack"
        assert param.value == "true"
        assert param.is_explicit is True

    def test_boolean_normalization_true(self):
        """Boolean True нормализуется в строку 'true'."""
        param = PlaybookParameter(name="flag", value=True)
        assert param.value == "true"

    def test_boolean_normalization_false(self):
        """Boolean False нормализуется в строку 'false'."""
        param = PlaybookParameter(name="flag", value=False)
        assert param.value == "false"

    def test_string_boolean_normalization(self):
        """Строковые 'True', 'FALSE' нормализуются к lowercase."""
        param1 = PlaybookParameter(name="flag1", value="True")
        param2 = PlaybookParameter(name="flag2", value="FALSE")
        assert param1.value == "true"
        assert param2.value == "false"


class TestParsedPlaybookConfig:
    """Тесты для dataclass ParsedPlaybookConfig."""

    def test_get_explicit_params(self):
        """Получение только явных параметров."""
        config = ParsedPlaybookConfig(
            path="/playbook.yml",
            parameters=[
                PlaybookParameter(name="server", is_explicit=False),
                PlaybookParameter(name="unpack", value="true", is_explicit=True),
                PlaybookParameter(name="mode", value="full", is_explicit=True),
            ]
        )
        explicit = config.get_explicit_params()
        assert explicit == {"unpack": "true", "mode": "full"}

    def test_get_dynamic_param_names(self):
        """Получение имён динамических параметров."""
        config = ParsedPlaybookConfig(
            path="/playbook.yml",
            parameters=[
                PlaybookParameter(name="server", is_explicit=False),
                PlaybookParameter(name="app", is_explicit=False),
                PlaybookParameter(name="unpack", value="true", is_explicit=True),
            ]
        )
        dynamic = config.get_dynamic_param_names()
        assert dynamic == ["server", "app"]

    def test_has_parameter(self):
        """Проверка наличия параметра по имени."""
        config = ParsedPlaybookConfig(
            path="/playbook.yml",
            parameters=[
                PlaybookParameter(name="server"),
                PlaybookParameter(name="app"),
            ]
        )
        assert config.has_parameter("server") is True
        assert config.has_parameter("app") is True
        assert config.has_parameter("nonexistent") is False


class TestPlaybookParameterParser:
    """Тесты для PlaybookParameterParser."""

    def test_parse_empty_string(self):
        """Пустая строка возвращает пустой конфиг."""
        config = PlaybookParameterParser.parse("")
        assert config.path == ""
        assert config.parameters == []

    def test_parse_path_only(self):
        """Путь без параметров."""
        config = PlaybookParameterParser.parse("/etc/ansible/playbook.yml")
        assert config.path == "/etc/ansible/playbook.yml"
        assert config.parameters == []

    def test_parse_single_dynamic_param(self):
        """Один динамический параметр."""
        config = PlaybookParameterParser.parse("playbook.yml {server}")
        assert config.path == "playbook.yml"
        assert len(config.parameters) == 1
        assert config.parameters[0].name == "server"
        assert config.parameters[0].is_explicit is False
        assert config.parameters[0].value is None

    def test_parse_multiple_dynamic_params(self):
        """Несколько динамических параметров."""
        config = PlaybookParameterParser.parse("playbook.yml {server} {app}")
        assert config.path == "playbook.yml"
        assert len(config.parameters) == 2
        assert config.parameters[0].name == "server"
        assert config.parameters[1].name == "app"

    def test_parse_explicit_param(self):
        """Явный параметр с значением."""
        config = PlaybookParameterParser.parse("playbook.yml {unpack=true}")
        assert config.path == "playbook.yml"
        assert len(config.parameters) == 1
        assert config.parameters[0].name == "unpack"
        assert config.parameters[0].value == "true"
        assert config.parameters[0].is_explicit is True

    def test_parse_mixed_params(self):
        """Смешанные параметры: динамические и явные."""
        config = PlaybookParameterParser.parse(
            "/etc/ansible/update.yml {server} {app} {unpack=true} {mode=full}"
        )
        assert config.path == "/etc/ansible/update.yml"
        assert len(config.parameters) == 4

        # Динамические
        assert config.parameters[0].name == "server"
        assert config.parameters[0].is_explicit is False

        assert config.parameters[1].name == "app"
        assert config.parameters[1].is_explicit is False

        # Явные
        assert config.parameters[2].name == "unpack"
        assert config.parameters[2].value == "true"
        assert config.parameters[2].is_explicit is True

        assert config.parameters[3].name == "mode"
        assert config.parameters[3].value == "full"
        assert config.parameters[3].is_explicit is True

    def test_parse_boolean_explicit_normalized(self):
        """Явные boolean параметры нормализуются в lowercase строки."""
        config = PlaybookParameterParser.parse("playbook.yml {flag=TRUE}")
        assert config.parameters[0].value == "true"

        config2 = PlaybookParameterParser.parse("playbook.yml {flag=False}")
        assert config2.parameters[0].value == "false"

    def test_path_extraction_with_extra_spaces(self):
        """Путь корректно извлекается при лишних пробелах."""
        config = PlaybookParameterParser.parse("  /path/playbook.yml   {server}  {app}  ")
        assert config.path == "/path/playbook.yml"

    def test_raw_input_preserved(self):
        """Оригинальная строка сохраняется."""
        raw = "playbook.yml {server} {app}"
        config = PlaybookParameterParser.parse(raw)
        assert config.raw_input == raw


class TestToExtraVars:
    """Тесты для метода to_extra_vars."""

    def test_explicit_params_only(self):
        """Явные параметры формируют extra_vars."""
        config = PlaybookParameterParser.parse("playbook.yml {unpack=true} {mode=full}")
        extra_vars = PlaybookParameterParser.to_extra_vars(config, {})
        assert extra_vars == {"unpack": "true", "mode": "full"}

    def test_dynamic_params_from_context(self):
        """Динамические параметры берутся из контекста."""
        config = PlaybookParameterParser.parse("playbook.yml {server} {app}")
        context = {"server": "prod01", "app": "myapp"}
        extra_vars = PlaybookParameterParser.to_extra_vars(config, context)
        assert extra_vars == {"server": "prod01", "app": "myapp"}

    def test_mixed_params(self):
        """Комбинация явных и динамических параметров."""
        config = PlaybookParameterParser.parse("playbook.yml {server} {unpack=true}")
        context = {"server": "prod01"}
        extra_vars = PlaybookParameterParser.to_extra_vars(config, context)
        assert extra_vars == {"server": "prod01", "unpack": "true"}

    def test_boolean_context_value(self):
        """Boolean значения из контекста конвертируются в строки."""
        config = PlaybookParameterParser.parse("playbook.yml {flag}")
        context = {"flag": True}
        extra_vars = PlaybookParameterParser.to_extra_vars(config, context)
        assert extra_vars["flag"] == "true"  # Строка, не bool!

    def test_skip_empty_default(self):
        """По умолчанию пустые значения пропускаются."""
        config = PlaybookParameterParser.parse("playbook.yml {server} {app}")
        context = {"server": "prod01"}  # app отсутствует
        extra_vars = PlaybookParameterParser.to_extra_vars(config, context)
        assert "server" in extra_vars
        assert "app" not in extra_vars

    def test_include_empty_when_skip_empty_false(self):
        """При skip_empty=False пустые значения включаются."""
        config = PlaybookParameterParser.parse("playbook.yml {server} {app}")
        # app присутствует в контексте но с пустым значением
        context = {"server": "prod01", "app": ""}
        extra_vars = PlaybookParameterParser.to_extra_vars(config, context, skip_empty=False)
        assert extra_vars["server"] == "prod01"
        assert extra_vars["app"] == ""


class TestValidateParameters:
    """Тесты для валидации параметров."""

    def test_valid_params(self):
        """Валидные параметры проходят проверку."""
        config = PlaybookParameterParser.parse("playbook.yml {server} {app_name}")
        is_valid, errors = PlaybookParameterParser.validate_parameters(config)
        assert is_valid is True
        assert errors == []

    def test_unsafe_param_name(self):
        """Небезопасные имена параметров отклоняются."""
        config = ParsedPlaybookConfig(
            path="playbook.yml",
            parameters=[PlaybookParameter(name="server;rm -rf /")]
        )
        is_valid, errors = PlaybookParameterParser.validate_parameters(config)
        assert is_valid is False
        assert len(errors) == 1
        assert "Небезопасное имя параметра" in errors[0]

    def test_strict_mode_unknown_param(self):
        """В строгом режиме неизвестные параметры - ошибка."""
        config = PlaybookParameterParser.parse("playbook.yml {unknown_param_xyz}")
        is_valid, errors = PlaybookParameterParser.validate_parameters(config, strict=True)
        assert is_valid is False
        assert "Неизвестный динамический параметр" in errors[0]

    def test_known_params_in_strict_mode(self):
        """Известные параметры проходят строгую проверку."""
        config = PlaybookParameterParser.parse("playbook.yml {server} {app}")
        is_valid, errors = PlaybookParameterParser.validate_parameters(config, strict=True)
        assert is_valid is True


class TestBuildPlaybookPath:
    """Тесты для построения пути с параметрами."""

    def test_build_with_explicit_params(self):
        """Построение пути с явными параметрами."""
        result = PlaybookParameterParser.build_playbook_path_with_params(
            "/etc/ansible/playbook.yml",
            explicit_params={"unpack": "true", "mode": "full"}
        )
        assert "{unpack=true}" in result
        assert "{mode=full}" in result
        assert result.startswith("/etc/ansible/playbook.yml")

    def test_build_with_dynamic_params(self):
        """Построение пути с динамическими параметрами."""
        result = PlaybookParameterParser.build_playbook_path_with_params(
            "/etc/ansible/playbook.yml",
            dynamic_params=["server", "app"]
        )
        assert "{server}" in result
        assert "{app}" in result

    def test_build_with_both(self):
        """Построение пути с обоими типами параметров."""
        result = PlaybookParameterParser.build_playbook_path_with_params(
            "/etc/ansible/playbook.yml",
            explicit_params={"unpack": True},  # boolean -> "true"
            dynamic_params=["server"]
        )
        assert "{unpack=true}" in result
        assert "{server}" in result


class TestSanitization:
    """Тесты для санитизации значений."""

    def test_sanitize_shell_special_chars(self):
        """Специальные символы shell экранируются."""
        config = ParsedPlaybookConfig(
            path="playbook.yml",
            parameters=[
                PlaybookParameter(name="cmd", value='echo $HOME', is_explicit=True)
            ]
        )
        extra_vars = PlaybookParameterParser.to_extra_vars(config, {})
        # $HOME должен быть экранирован
        assert "\\$" in extra_vars["cmd"]

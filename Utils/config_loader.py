"""
В данном модуле написаны функции для валидации конфигов.
"""
import configparser
from configparser import ConfigParser, SectionProxy
import codecs
import os

from Utils.exceptions import (ParamNotFoundError, EmptyValueError, ValueNotValidError, SectionNotFoundError,
                              ConfigParseError, ProductsFileNotFoundError, NoProductVarError,
                              SubCommandAlreadyExists, DuplicateSectionErrorWrapper)


def check_param(param_name: str, section: SectionProxy, valid_values: list[str | None] | None = None,
                raise_if_not_exists: bool = True) -> str | None:
    """
    Проверяет, существует ли в переданной секции указанный параметр и если да, валидно ли его значение.

    :param param_name: название параметра.
    :param section: объект секции.
    :param valid_values: валидные значения. Если None, любая строка - валидное значение.
    :param raise_if_not_exists: возбуждать ли исключение, если параметр не найден.

    :return: Значение ключа, если ключ найден и его значение валидно. Если ключ не найден и
    raise_ex_if_not_exists == False - возвращает None. В любом другом случае возбуждает исключения.
    """
    if param_name not in list(section.keys()):
        if raise_if_not_exists:
            raise ParamNotFoundError(param_name)
        return None

    value = section[param_name].strip()

    # Если значение пустое ("", оно не может быть None)
    if not value:
        if valid_values and None in valid_values:
            return value
        raise EmptyValueError(param_name)

    if valid_values and valid_values != [None] and value not in valid_values:
        raise ValueNotValidError(param_name, value, valid_values)
    return value


def create_config_obj(config_path: str) -> ConfigParser:
    """
    Создает объект конфига с нужными настройками.

    :param config_path: путь до файла конфига.

    :return: объект конфига.
    """
    config = ConfigParser(delimiters=(":", ), interpolation=None)
    config.optionxform = str
    config.read_file(codecs.open(config_path, "r", "utf8"))
    return config


def load_main_config(config_path: str):
    """
    Парсит и проверяет на правильность основной конфиг.

    :param config_path: путь до основного конфига.

    :return: спарсеный основной конфиг.
    """
    config = create_config_obj(config_path)
    values = {
        "FunPay": {
            "golden_key": "any",
            "user_agent": "any+empty",
            "autoRaise": ["0", "1"],
        },

        "Proxy": {
            "enable": ["0", "1"],
            "ip": "any+empty",
            "port": "any+empty",
            "login": "any+empty",
            "password": "any+empty",
            "check": ["0", "1"]
        },

        "Other": {
            "language": ["ru", "eng"]
        }
    }

    for section_name in values:
        if section_name not in config.sections():
            raise ConfigParseError(config_path, section_name, SectionNotFoundError())

        for param_name in values[section_name]:

            # UPDATE 009
            if section_name == "Other" and param_name == "language" and param_name not in config[section_name]:
                config.set("Other", "language", "ru")
                with open("configs/_main.cfg", "w", encoding="utf-8") as f:
                    config.write(f)
            # END OF UPDATE 009

            try:
                if values[section_name][param_name] == "any":
                    check_param(param_name, config[section_name])
                elif values[section_name][param_name] == "any+empty":
                    check_param(param_name, config[section_name], valid_values=[None])
                else:
                    check_param(param_name, config[section_name], valid_values=values[section_name][param_name])
            except (ParamNotFoundError, EmptyValueError, ValueNotValidError) as e:
                raise ConfigParseError(config_path, section_name, e)

    return config
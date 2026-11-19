"""Чтение и проверка XML-конфигурации."""

import os
import re
from xml.etree import ElementTree as etree

from errors import ConfigError

REAL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*$")
TEST_NAME_RE = re.compile(r"^[A-Z]+$")
URL_RE = re.compile(r"^https?://\S+$")
BOOL_VALUES = ("true", "false")


def _read_root(path):
    """Разбирает XML-файл и возвращает корневой элемент <config>."""
    try:
        root = etree.parse(path).getroot()
    except FileNotFoundError:
        raise ConfigError(f"файл конфигурации не найден: {path}")
    except etree.ParseError as err:
        raise ConfigError(f"некорректный XML в {path}: {err}")
    except OSError as err:
        raise ConfigError(f"не удалось прочитать {path}: {err.strerror}")
    if root.tag != "config":
        raise ConfigError(
            f"корневой элемент должен быть <config>, а не <{root.tag}>")
    return root


def _text(root, name, required=True):
    """Возвращает текст параметра <name> ('' для необязательного)."""
    element = root.find(name)
    if element is None:
        if required:
            raise ConfigError(f"отсутствует параметр <{name}>")
        return ""
    return (element.text or "").strip()


def _parse_bool(raw):
    """Преобразует 'true' / 'false' в bool (пустое значение = false)."""
    value = raw.lower() or "false"
    if value not in BOOL_VALUES:
        raise ConfigError(
            f"<test_mode>: ожидается true или false, получено '{value}'")
    return value == "true"


def _check_package(package, test_mode):
    """Проверяет имя пакета по правилам выбранного режима."""
    if not package:
        raise ConfigError("<package>: имя пакета не может быть пустым")
    pattern = TEST_NAME_RE if test_mode else REAL_NAME_RE
    if not pattern.match(package):
        hint = ("заглавные латинские буквы" if test_mode
                else "строчные буквы, цифры и + . -")
        raise ConfigError(
            f"<package>: недопустимое имя '{package}' (ожидается: {hint})")


def _check_repository(repository, test_mode):
    """Проверяет URL репозитория или путь к тестовому файлу."""
    if not repository:
        raise ConfigError("<repository>: значение не может быть пустым")
    if test_mode:
        if not os.path.isfile(repository):
            raise ConfigError("<repository>: файл тестового репозитория "
                              f"не найден: {repository}")
    elif not URL_RE.match(repository):
        raise ConfigError("<repository>: ожидается URL http(s)://..., "
                          f"получено '{repository}'")


def _parse_depth(raw):
    """Преобразует максимальную глубину в неотрицательное целое."""
    try:
        depth = int(raw)
    except ValueError:
        raise ConfigError(
            f"<max_depth>: ожидается целое число, получено '{raw}'")
    if depth < 0:
        raise ConfigError(
            f"<max_depth>: значение не может быть отрицательным ({depth})")
    return depth


def load_config(path):
    """Читает XML-конфиг, проверяет параметры и возвращает словарь."""
    root = _read_root(path)
    test_mode = _parse_bool(_text(root, "test_mode", required=False))
    package = _text(root, "package")
    _check_package(package, test_mode)
    repository = _text(root, "repository")
    _check_repository(repository, test_mode)
    return {
        "package": package,
        "repository": repository,
        "test_mode": test_mode,
        "max_depth": _parse_depth(_text(root, "max_depth")),
        "filter": _text(root, "filter", required=False),
    }


def format_config(cfg):
    """Возвращает строки 'ключ: значение' для вывода параметров."""
    lines = []
    for key, value in cfg.items():
        shown = str(value).lower() if isinstance(value, bool) else value
        lines.append(f"{key}: {shown}")
    return lines

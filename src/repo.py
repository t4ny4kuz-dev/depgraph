"""Загрузка и разбор репозиториев: apt (Packages) и тестового."""

import gzip
import lzma
import re
import urllib.error
import urllib.request

from config import TEST_NAME_RE
from errors import RepoError

FETCH_TIMEOUT = 120
CONTINUATION = (" ", "\t")
DEPENDS_FIELDS = ("Pre-Depends", "Depends")
VERSION_SPLIT_RE = re.compile(r"[\s(\[<]")
BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")


def _download(url):
    """Скачивает файл по URL и возвращает его байты."""
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        raise RepoError(f"сервер ответил HTTP {err.code} для {url}")
    except urllib.error.URLError as err:
        raise RepoError(f"не удалось подключиться к {url}: {err.reason}")
    except (OSError, ValueError) as err:
        raise RepoError(f"ошибка загрузки {url}: {err}")


def _decompress(url, data):
    """Распаковывает данные по расширению URL (.gz или .xz)."""
    try:
        if url.endswith(".gz"):
            return gzip.decompress(data)
        if url.endswith(".xz"):
            return lzma.decompress(data)
    except (OSError, EOFError, lzma.LZMAError) as err:
        raise RepoError(f"не удалось распаковать {url}: {err}")
    return data


def fetch_packages(url):
    """Скачивает индекс Packages(.gz/.xz) и возвращает его текст."""
    data = _decompress(url, _download(url))
    return data.decode("utf-8", errors="replace")


def parse_depends(value):
    """Разбирает поле Depends: 'a (>= 1), b | c, d:any' -> [a, b, d].

    Из альтернатив берётся первая, версии и архитектуры отбрасываются.
    """
    result = []
    for item in value.split(","):
        first = item.split("|")[0].strip()
        name = VERSION_SPLIT_RE.split(first)[0].split(":")[0]
        if name and name not in result:
            result.append(name)
    return result


def _parse_fields(block):
    """Разбирает один блок индекса Packages в словарь полей."""
    fields, key = {}, None
    for line in block.splitlines():
        if line[:1] in CONTINUATION:
            if key:
                fields[key] += "\n" + line.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    return fields


def _block_dependencies(fields):
    """Собирает зависимости из полей Pre-Depends и Depends."""
    deps = []
    for field in DEPENDS_FIELDS:
        for dep in parse_depends(fields.get(field, "")):
            if dep not in deps:
                deps.append(dep)
    return deps


def parse_packages(text):
    """Разбирает формат Debian control: {пакет: [прямые зависимости]}.

    При нескольких версиях пакета берётся первая.
    """
    db = {}
    for block in BLOCK_SPLIT_RE.split(text):
        fields = _parse_fields(block)
        name = fields.get("Package")
        if name and name not in db:
            db[name] = _block_dependencies(fields)
    return db


def _read_lines(path):
    """Читает файл построчно, ошибки чтения превращает в RepoError."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().splitlines()
    except OSError as err:
        raise RepoError(f"не удалось прочитать {path}: {err.strerror}")


def _parse_test_line(path, number, line):
    """Разбирает строку 'A: B C' тестового репозитория."""
    name, _, rest = line.partition(":")
    name, deps = name.strip(), rest.split()
    for pkg in [name] + deps:
        if not TEST_NAME_RE.match(pkg):
            raise RepoError(f"{path}:{number}: имя '{pkg}' должно "
                            "состоять из заглавных латинских букв")
    return name, list(dict.fromkeys(deps))


def load_test_repo(path):
    """Загружает тестовый граф: строка 'A: B C', комментарии после '#'."""
    db = {}
    for number, line in enumerate(_read_lines(path), 1):
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, deps = _parse_test_line(path, number, line)
        if name in db:
            raise RepoError(f"{path}:{number}: пакет {name} описан повторно")
        db[name] = deps
    return db


def load_repo(cfg):
    """Загружает репозиторий согласно конфигурации."""
    if cfg["test_mode"]:
        return load_test_repo(cfg["repository"])
    return parse_packages(fetch_packages(cfg["repository"]))


def known_packages(db):
    """Возвращает множество всех известных имён пакетов."""
    known = set(db)
    for deps in db.values():
        known.update(deps)
    return known

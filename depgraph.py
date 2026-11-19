#!/usr/bin/env python3
"""Инструмент визуализации графа зависимостей пакетов (формат apt / Ubuntu).

Вариант 15. Без менеджеров пакетов и сторонних библиотек: только стандартная
библиотека Python (xml, urllib, gzip, lzma, re).
"""

import argparse
import gzip
import lzma
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict


class ConfigError(Exception):
    """Ошибка конфигурационного файла."""


class RepoError(Exception):
    """Ошибка получения / разбора репозитория."""


# ---------------------------------------------------------------- Этап 1
REAL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*$")  # правила имён Debian
TEST_NAME_RE = re.compile(r"^[A-Z]+$")                  # тестовый репозиторий


def load_config(path):
    """Читает XML-конфиг и проверяет все параметры."""
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError:
        raise ConfigError(f"файл конфигурации не найден: {path}")
    except ET.ParseError as e:
        raise ConfigError(f"некорректный XML в {path}: {e}")
    except OSError as e:
        raise ConfigError(f"не удалось прочитать {path}: {e.strerror}")

    if root.tag != "config":
        raise ConfigError(f"корневой элемент должен быть <config>, а не <{root.tag}>")

    def text(name, required=True):
        el = root.find(name)
        if el is None:
            if required:
                raise ConfigError(f"отсутствует параметр <{name}>")
            return ""
        return (el.text or "").strip()

    # режим тестового репозитория
    tm = text("test_mode", required=False).lower() or "false"
    if tm not in ("true", "false"):
        raise ConfigError(f"<test_mode>: ожидается true или false, получено '{tm}'")
    test_mode = tm == "true"

    # имя пакета
    package = text("package")
    if not package:
        raise ConfigError("<package>: имя пакета не может быть пустым")
    name_re = TEST_NAME_RE if test_mode else REAL_NAME_RE
    if not name_re.match(package):
        hint = "заглавные латинские буквы" if test_mode else "строчные буквы, цифры и + . -"
        raise ConfigError(f"<package>: недопустимое имя '{package}' (ожидается: {hint})")

    # репозиторий
    repository = text("repository")
    if not repository:
        raise ConfigError("<repository>: значение не может быть пустым")
    if test_mode:
        if not os.path.isfile(repository):
            raise ConfigError(f"<repository>: файл тестового репозитория не найден: {repository}")
    elif not re.match(r"^https?://\S+$", repository):
        raise ConfigError(f"<repository>: ожидается URL http(s)://..., получено '{repository}'")

    # максимальная глубина
    raw_depth = text("max_depth")
    try:
        max_depth = int(raw_depth)
    except ValueError:
        raise ConfigError(f"<max_depth>: ожидается целое число, получено '{raw_depth}'")
    if max_depth < 0:
        raise ConfigError(f"<max_depth>: значение не может быть отрицательным ({max_depth})")

    # подстрока фильтра (может быть пустой = фильтр выключен)
    substring = text("filter", required=False)

    return {
        "package": package,
        "repository": repository,
        "test_mode": test_mode,
        "max_depth": max_depth,
        "filter": substring,
    }


def print_config(cfg):
    for key, value in cfg.items():
        shown = str(value).lower() if isinstance(value, bool) else value
        print(f"{key}: {shown}")


# ---------------------------------------------------------------- Этап 2
def fetch_packages(url):
    """Скачивает индекс Packages(.gz/.xz) и возвращает текст."""
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        raise RepoError(f"сервер ответил HTTP {e.code} для {url}")
    except urllib.error.URLError as e:
        raise RepoError(f"не удалось подключиться к {url}: {e.reason}")
    except (OSError, ValueError) as e:
        raise RepoError(f"ошибка загрузки {url}: {e}")

    try:
        if url.endswith(".gz"):
            data = gzip.decompress(data)
        elif url.endswith(".xz"):
            data = lzma.decompress(data)
    except (OSError, EOFError, lzma.LZMAError) as e:
        raise RepoError(f"не удалось распаковать {url}: {e}")
    return data.decode("utf-8", errors="replace")


def parse_depends(value):
    """'a (>= 1), b | c, d:any' -> ['a', 'b', 'd'] (из альтернатив берётся первая)."""
    result = []
    for item in value.split(","):
        first = item.split("|")[0].strip()
        name = re.split(r"[\s(\[<]", first)[0].split(":")[0]
        if name and name not in result:
            result.append(name)
    return result


def parse_packages(text):
    """Разбирает формат Debian control: {пакет: [прямые зависимости]}."""
    db = {}
    for block in re.split(r"\n\s*\n", text):
        fields, key = {}, None
        for line in block.splitlines():
            if line[:1] in (" ", "\t"):
                if key:
                    fields[key] += "\n" + line.strip()
            elif ":" in line:
                key, val = line.split(":", 1)
                fields[key] = val.strip()
        name = fields.get("Package")
        if not name or name in db:  # при нескольких версиях берём первую
            continue
        deps = []
        for field in ("Pre-Depends", "Depends"):
            for d in parse_depends(fields.get(field, "")):
                if d not in deps:
                    deps.append(d)
        db[name] = deps
    return db


def load_test_repo(path):
    """Файл вида 'A: B C' (по строке на пакет), имена - заглавные латинские буквы."""
    db = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise RepoError(f"не удалось прочитать {path}: {e.strerror}")
    for n, line in enumerate(lines, 1):
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, _, rest = line.partition(":")
        name, deps = name.strip(), rest.split()
        for p in [name] + deps:
            if not TEST_NAME_RE.match(p):
                raise RepoError(f"{path}:{n}: имя '{p}' должно состоять из заглавных латинских букв")
        if name in db:
            raise RepoError(f"{path}:{n}: пакет {name} описан повторно")
        db[name] = list(dict.fromkeys(deps))
    return db


def load_repo(cfg):
    if cfg["test_mode"]:
        return load_test_repo(cfg["repository"])
    return parse_packages(fetch_packages(cfg["repository"]))


def known_packages(db):
    known = set(db)
    for deps in db.values():
        known.update(deps)
    return known


# ---------------------------------------------------------------- Этап 3
def build_graph(get_deps, root, max_depth, substring=""):
    """BFS с рекурсией: каждый вызов level() обрабатывает один уровень графа.

    Глубина root = 0; рёбра раскрываются, пока depth < max_depth.
    Пакеты, в имени которых есть substring, пропускаются.
    Циклы обрываются множеством visited.
    """
    graph = OrderedDict()
    visited = {root}

    def level(frontier, depth):
        if not frontier:
            return
        if depth >= max_depth:          # граница глубины: узлы без раскрытия
            for pkg in frontier:
                graph.setdefault(pkg, [])
            return
        nxt = []
        for pkg in frontier:
            edges = []
            for dep in get_deps(pkg):
                if substring and substring in dep:
                    continue
                if dep not in edges:
                    edges.append(dep)
                if dep not in visited:
                    visited.add(dep)
                    nxt.append(dep)
            graph[pkg] = edges
        level(nxt, depth + 1)

    level([root], 0)
    return graph


def find_cycles(graph):
    """Возвращает список найденных циклов (по одному на обратное ребро DFS)."""
    cycles, state, stack = [], {}, []

    def dfs(node):
        state[node] = 1
        stack.append(node)
        for nb in graph.get(node, []):
            if state.get(nb) == 1:
                cycles.append(stack[stack.index(nb):] + [nb])
            elif nb not in state:
                dfs(nb)
        stack.pop()
        state[node] = 2

    for node in graph:
        if node not in state:
            dfs(node)
    return cycles


# ---------------------------------------------------------------- Этап 4
def reverse_index(db):
    rev = {}
    for pkg, deps in db.items():
        for d in deps:
            rev.setdefault(d, []).append(pkg)
    return {k: sorted(v) for k, v in rev.items()}


# ---------------------------------------------------------------- Этап 5
def to_dot(graph, root, reverse=False):
    """Граф на языке Graphviz. В режиме reverse стрелки: зависимый -> зависимость."""
    lines = ["digraph dependencies {", "  rankdir=LR;", "  node [shape=box];",
             f'  "{root}" [style=filled, fillcolor=lightblue];']
    for pkg, edges in graph.items():
        if not edges:
            lines.append(f'  "{pkg}";')
        for e in edges:
            a, b = (e, pkg) if reverse else (pkg, e)
            lines.append(f'  "{a}" -> "{b}";')
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI
def print_graph(graph, title):
    print(title)
    for pkg, edges in graph.items():
        print(f"  {pkg} -> {', '.join(edges) if edges else '(нет)'}")
    cycles = find_cycles(graph)
    if cycles:
        print("Обнаружены циклические зависимости:")
        for c in cycles:
            print("  " + " -> ".join(c))


def run(cfg, mode, out_file):
    db = load_repo(cfg)
    root = cfg["package"]
    if root not in known_packages(db):
        raise RepoError(f"пакет '{root}' не найден в репозитории")
    if cfg["filter"] and cfg["filter"] in root:
        raise ConfigError(f"<filter>: подстрока '{cfg['filter']}' содержится в имени анализируемого пакета")

    if mode == "direct":
        print(f"Прямые зависимости пакета {root}:")
        for d in db.get(root, []):
            print(f"  {d}")
        if not db.get(root):
            print("  (нет)")
        return

    if mode == "reverse":
        rev = reverse_index(db)
        graph = build_graph(lambda p: rev.get(p, []), root, cfg["max_depth"], cfg["filter"])
        print_graph(graph, f"Обратные зависимости {root} (кто зависит от пакета):")
        others = [p for p in graph if p != root]
        print(f"Всего пакетов, зависящих от {root}: {len(others)}")
        if out_file:
            save_dot(to_dot(graph, root, reverse=True), out_file)
        return

    graph = build_graph(lambda p: db.get(p, []), root, cfg["max_depth"], cfg["filter"])
    if mode == "graph":
        print_graph(graph, f"Граф зависимостей {root} (глубина <= {cfg['max_depth']}):")
    else:  # dot
        dot = to_dot(graph, root)
        print(dot)
        if out_file:
            save_dot(dot, out_file)


def save_dot(dot, path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(dot + "\n")
    except OSError as e:
        raise RepoError(f"не удалось записать {path}: {e.strerror}")
    print(f"Описание графа сохранено в {path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Визуализация графа зависимостей пакетов (apt)")
    ap.add_argument("config", nargs="?", default="config.xml", help="путь к XML-конфигу")
    ap.add_argument("--mode", choices=["direct", "graph", "reverse", "dot"], default="graph",
                    help="direct - прямые зависимости, graph - граф, reverse - обратные, dot - Graphviz")
    ap.add_argument("--show-config", action="store_true", help="вывести параметры (ключ: значение)")
    ap.add_argument("--out", help="сохранить описание Graphviz в файл (режимы dot/reverse)")
    args = ap.parse_args()

    try:
        cfg = load_config(args.config)
        if args.show_config:
            print_config(cfg)
        run(cfg, args.mode, args.out)
    except (ConfigError, RepoError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

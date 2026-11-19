"""Инструмент визуализации графа зависимостей пакетов (apt, вариант 15)."""

import argparse
import sys

from config import format_config, load_config
from errors import ConfigError, RepoError
from graph import build_graph, find_cycles, reverse_index
from render import save_dot, save_image, to_dot
from repo import known_packages, load_repo

EXIT_ERROR = 1
DEFAULT_IMAGE = "graph.svg"


def print_graph(graph, title):
    """Печатает граф списком рёбер и найденные циклы."""
    print(title)
    for pkg, edges in graph.items():
        print(f"  {pkg} -> {', '.join(edges) if edges else '(нет)'}")
    cycles = find_cycles(graph)
    if cycles:
        print("Обнаружены циклические зависимости:")
        for cycle in cycles:
            print("  " + " -> ".join(cycle))


def _check_root(cfg, db):
    """Проверяет, что анализируемый пакет есть и не отфильтрован."""
    root = cfg["package"]
    if root not in known_packages(db):
        raise RepoError(f"пакет '{root}' не найден в репозитории")
    if cfg["filter"] and cfg["filter"] in root:
        raise ConfigError(f"<filter>: подстрока '{cfg['filter']}' "
                          "содержится в имени анализируемого пакета")


def _export(graph, root, reverse, options):
    """Сохраняет dot-файл и/или картинку, если они запрошены."""
    if options.out:
        save_dot(to_dot(graph, root, reverse), options.out)
    if options.image:
        save_image(graph, root, reverse, options.image, options.show)


def _show_direct(cfg, db):
    """Режим direct: прямые зависимости пакета."""
    root = cfg["package"]
    print(f"Прямые зависимости пакета {root}:")
    for dep in db.get(root, []):
        print(f"  {dep}")
    if not db.get(root):
        print("  (нет)")


def _show_reverse(cfg, db, options):
    """Режим reverse: пакеты, зависящие от заданного (тот же BFS)."""
    root = cfg["package"]
    rev = reverse_index(db)
    graph = build_graph(lambda pkg: rev.get(pkg, []), root,
                        cfg["max_depth"], cfg["filter"])
    print_graph(graph, f"Обратные зависимости {root} "
                       "(кто зависит от пакета):")
    others = [pkg for pkg in graph if pkg != root]
    print(f"Всего пакетов, зависящих от {root}: {len(others)}")
    _export(graph, root, True, options)


def _show_graph(cfg, db, mode, options):
    """Режимы graph и dot: граф прямых зависимостей."""
    root = cfg["package"]
    graph = build_graph(lambda pkg: db.get(pkg, []), root,
                        cfg["max_depth"], cfg["filter"])
    if mode == "graph":
        print_graph(graph, f"Граф зависимостей {root} "
                           f"(глубина <= {cfg['max_depth']}):")
    else:
        print(to_dot(graph, root))
    _export(graph, root, False, options)


def run(cfg, mode, options):
    """Выполняет выбранный режим работы."""
    db = load_repo(cfg)
    _check_root(cfg, db)
    if mode == "direct":
        _show_direct(cfg, db)
    elif mode == "reverse":
        _show_reverse(cfg, db, options)
    else:
        _show_graph(cfg, db, mode, options)


def build_parser():
    """Создаёт разборщик аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Визуализация графа зависимостей пакетов (apt)")
    parser.add_argument("config", nargs="?", default="config.xml",
                        help="путь к XML-конфигу")
    parser.add_argument(
        "--mode", choices=["direct", "graph", "reverse", "dot"],
        default="graph",
        help="direct - прямые, graph - граф, reverse - обратные, "
             "dot - Graphviz")
    parser.add_argument("--show-config", action="store_true",
                        help="вывести параметры (ключ: значение)")
    parser.add_argument("--image",
                        help="сохранить картинку: .svg или .png/.pdf (dot)")
    parser.add_argument("--show", action="store_true",
                        help="нарисовать граф и открыть в браузере")
    parser.add_argument("--out", help="сохранить описание Graphviz в файл")
    return parser


def main():
    """Точка входа: читает конфиг и запускает выбранный режим."""
    args = build_parser().parse_args()
    if args.show and not args.image:
        args.image = DEFAULT_IMAGE
    try:
        cfg = load_config(args.config)
        if args.show_config:
            print("\n".join(format_config(cfg)))
        run(cfg, args.mode, args)
    except (ConfigError, RepoError) as err:
        print(f"Ошибка: {err}", file=sys.stderr)
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    main()

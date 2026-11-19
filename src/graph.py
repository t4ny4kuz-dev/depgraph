"""Построение графа зависимостей: BFS с рекурсией, циклы, обратный граф."""

from collections import OrderedDict

VISITING = 1
DONE = 2


def _expand_node(get_deps, pkg, substring, visited, nxt):
    """Возвращает рёбра пакета, добавляя новые узлы в очередь nxt."""
    edges = []
    for dep in get_deps(pkg):
        if substring and substring in dep:
            continue
        if dep not in edges:
            edges.append(dep)
        if dep not in visited:
            visited.add(dep)
            nxt.append(dep)
    return edges


def _level(graph, visited, frontier, depth, params):
    """Обрабатывает один уровень BFS и рекурсивно переходит к следующему."""
    get_deps, max_depth, substring = params
    if not frontier:
        return
    if depth >= max_depth:
        for pkg in frontier:
            graph.setdefault(pkg, [])
        return
    nxt = []
    for pkg in frontier:
        graph[pkg] = _expand_node(get_deps, pkg, substring, visited, nxt)
    _level(graph, visited, nxt, depth + 1, params)


def build_graph(get_deps, root, max_depth, substring=""):
    """Строит граф зависимостей обходом BFS с рекурсией.

    Корень имеет глубину 0, рёбра раскрываются пока глубина < max_depth.
    Пакеты, в имени которых есть substring, пропускаются. Циклы
    обрываются множеством посещённых узлов.
    """
    graph = OrderedDict()
    params = (get_deps, max_depth, substring)
    _level(graph, {root}, [root], 0, params)
    return graph


def _dfs(graph, node, state, stack, cycles):
    """Поиск в глубину; обратные рёбра записываются как циклы."""
    state[node] = VISITING
    stack.append(node)
    for neighbour in graph.get(node, []):
        if state.get(neighbour) == VISITING:
            cycles.append(stack[stack.index(neighbour):] + [neighbour])
        elif neighbour not in state:
            _dfs(graph, neighbour, state, stack, cycles)
    stack.pop()
    state[node] = DONE


def find_cycles(graph):
    """Возвращает список найденных циклов (каждый - список имён)."""
    cycles, state, stack = [], {}, []
    for node in graph:
        if node not in state:
            _dfs(graph, node, state, stack, cycles)
    return cycles


def reverse_index(db):
    """Строит обратный индекс: пакет -> отсортированные зависящие от него."""
    rev = {}
    for pkg, deps in db.items():
        for dep in deps:
            rev.setdefault(dep, []).append(pkg)
    return {key: sorted(value) for key, value in rev.items()}

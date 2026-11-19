"""Представления графа: Graphviz (dot), SVG и сохранение картинки."""

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from xml.sax.saxutils import escape

from errors import RepoError

NODE_W, NODE_H = 150, 36
GAP_X, GAP_Y, PAD = 90, 24, 20
CURVE = 60
MAX_LABEL = 20
ROOT_FILL = "#add8e6"
NODE_FILL = "#f4f4f4"
DOT_FORMATS = (".png", ".pdf")
SVG_MARKER = (
    '<defs><marker id="arr" markerWidth="10" markerHeight="8" '
    'refX="9" refY="4" orient="auto">'
    '<path d="M0,0 L10,4 L0,8 z" fill="#555"/></marker></defs>')


def _dot_edges(pkg, targets, reverse):
    """Возвращает строки dot для рёбер пакета (или одиночного узла)."""
    if not targets:
        return [f'  "{pkg}";']
    lines = []
    for target in targets:
        src, dst = (target, pkg) if reverse else (pkg, target)
        lines.append(f'  "{src}" -> "{dst}";')
    return lines


def to_dot(graph, root, reverse=False):
    """Формирует описание графа на языке Graphviz.

    В режиме reverse стрелки направлены от зависимого к зависимости.
    """
    lines = ["digraph dependencies {", "  rankdir=LR;",
             "  node [shape=box];",
             f'  "{root}" [style=filled, fillcolor=lightblue];']
    for pkg, targets in graph.items():
        lines.extend(_dot_edges(pkg, targets, reverse))
    lines.append("}")
    return "\n".join(lines)


def _graph_nodes(graph):
    """Возвращает все узлы графа в порядке появления."""
    nodes = list(graph)
    for targets in graph.values():
        for node in targets:
            if node not in nodes:
                nodes.append(node)
    return nodes


def _graph_edges(graph, reverse):
    """Возвращает рёбра (откуда, куда) с учётом направления."""
    edges = []
    for pkg, targets in graph.items():
        for target in targets:
            edges.append((target, pkg) if reverse else (pkg, target))
    return edges


def _bfs_levels(graph, root):
    """Считает уровень (расстояние от корня) каждого узла."""
    level, queue = {root: 0}, [root]
    while queue:
        current = queue.pop(0)
        for node in graph.get(current, []):
            if node not in level:
                level[node] = level[current] + 1
                queue.append(node)
    return level


def _layout(nodes, level):
    """Возвращает координаты узлов, ширину и высоту картинки."""
    layers = {}
    for node in nodes:
        layers.setdefault(level.get(node, 0), []).append(node)
    pos = {}
    for lvl, names in layers.items():
        for index, node in enumerate(names):
            pos[node] = (PAD + lvl * (NODE_W + GAP_X),
                         PAD + index * (NODE_H + GAP_Y))
    width = 2 * PAD + max(layers) * (NODE_W + GAP_X) + NODE_W
    tallest = max(len(names) for names in layers.values())
    height = 2 * PAD + tallest * (NODE_H + GAP_Y) - GAP_Y
    return pos, width, height


def _svg_edge(src_pos, dst_pos):
    """Рисует ребро кривой Безье со стрелкой."""
    start_x, start_y = src_pos[0] + NODE_W, src_pos[1] + NODE_H / 2
    end_x, end_y = dst_pos[0], dst_pos[1] + NODE_H / 2
    curve = (f"M{start_x},{start_y} "
             f"C{start_x + CURVE},{start_y} {end_x - CURVE},{end_y} "
             f"{end_x},{end_y}")
    return (f'<path d="{curve}" fill="none" stroke="#555" '
            'stroke-width="1.3" marker-end="url(#arr)"/>')


def _svg_node(name, position, root):
    """Рисует узел: прямоугольник и подпись."""
    pos_x, pos_y = position
    fill = ROOT_FILL if name == root else NODE_FILL
    label = name
    if len(name) > MAX_LABEL:
        label = name[:MAX_LABEL - 1] + "…"
    rect = (f'<rect x="{pos_x}" y="{pos_y}" width="{NODE_W}" '
            f'height="{NODE_H}" rx="4" fill="{fill}" stroke="#333"/>')
    text = (f'<text x="{pos_x + NODE_W / 2}" y="{pos_y + NODE_H / 2 + 5}" '
            f'text-anchor="middle">{escape(label)}</text>')
    return [rect, text]


def to_svg(graph, root, reverse=False):
    """Рисует граф в SVG без внешних библиотек (слои = уровни BFS)."""
    nodes = _graph_nodes(graph)
    pos, width, height = _layout(nodes, _bfs_levels(graph, root))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
           f'height="{height}" viewBox="0 0 {width} {height}" '
           'font-family="monospace" font-size="13">',
           SVG_MARKER,
           f'<rect width="{width}" height="{height}" fill="white"/>']
    for src, dst in _graph_edges(graph, reverse):
        if src != dst:
            out.append(_svg_edge(pos[src], pos[dst]))
    for node in nodes:
        out.extend(_svg_node(node, pos[node], root))
    out.append("</svg>")
    return "\n".join(out)


def _write_text(path, text):
    """Записывает текст в файл, ошибки превращает в RepoError."""
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    except OSError as err:
        raise RepoError(f"не удалось записать {path}: {err.strerror}")


def save_dot(dot, path):
    """Сохраняет описание Graphviz в файл."""
    _write_text(path, dot)
    print(f"Описание графа сохранено в {path}", file=sys.stderr)


def _render_with_dot(dot_text, path, fmt):
    """Строит PNG/PDF внешней программой Graphviz (команда dot)."""
    dot = shutil.which("dot")
    if not dot:
        raise RepoError("для PNG/PDF нужен Graphviz (команда dot). "
                        "Установите его или используйте --image graph.svg")
    try:
        subprocess.run([dot, "-T" + fmt, "-o", path],
                       input=dot_text.encode("utf-8"), check=True)
    except (OSError, subprocess.CalledProcessError):
        raise RepoError("Graphviz завершился с ошибкой")


def save_image(graph, root, reverse, path, show=False):
    """Сохраняет картинку графа (.svg встроенно, .png/.pdf через dot)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".svg":
        _write_text(path, to_svg(graph, root, reverse))
    elif ext in DOT_FORMATS:
        _render_with_dot(to_dot(graph, root, reverse), path, ext[1:])
    else:
        raise RepoError(
            f"неподдерживаемый формат изображения '{ext}' (svg, png, pdf)")
    print(f"Изображение сохранено в {path}", file=sys.stderr)
    if show:
        webbrowser.open(Path(path).resolve().as_uri())

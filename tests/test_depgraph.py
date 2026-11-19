"""Модульные тесты depgraph (запуск: python -m unittest discover tests)."""

import os
import tempfile
import unittest
from xml.etree import ElementTree as etree

import paths
from config import format_config, load_config
from errors import ConfigError, RepoError
from graph import build_graph, find_cycles, reverse_index
from render import to_dot, to_svg
from repo import (known_packages, load_test_repo, parse_depends,
                  parse_packages)

TEST_REPO = "A: B C\nB: D\nC: D E\nD: F\nE: A\nF:\nG: A\n"
PACKAGES = (
    "Package: curl\nDepends: libc6 (>= 2.34), zlib1g | zlib, foo:any\n"
    "Description: x\n more text\n\n"
    "Package: libc6\nPre-Depends: base\nDepends: libc6\n"
)
CONFIG = (
    "<config><package>{pkg}</package><repository>{repo}</repository>"
    "<test_mode>{mode}</test_mode><max_depth>{depth}</max_depth>"
    "<filter>x</filter></config>"
)


class TempFilesCase(unittest.TestCase):
    """Базовый класс с временным каталогом для файлов."""

    def setUp(self):
        """Создаёт временный каталог и тестовый репозиторий."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.repo_path = self.write("repo.txt", TEST_REPO)

    def write(self, name, text):
        """Записывает файл во временный каталог и возвращает путь."""
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def config(self, pkg="A", mode="true", depth="3", repo=None):
        """Создаёт XML-конфиг и возвращает путь к нему."""
        repo = repo or self.repo_path
        text = CONFIG.format(pkg=pkg, repo=repo, mode=mode, depth=depth)
        return self.write("config.xml", text)


class ParsingTests(unittest.TestCase):
    """Разбор формата apt."""

    def test_src_dir_exists(self):
        """Каталог с исходным кодом найден."""
        self.assertTrue(os.path.isdir(paths.SRC))

    def test_depends_strips_versions_and_alternatives(self):
        """Версии, архитектуры и альтернативы отбрасываются."""
        value = "a (>= 1), b | c, d:any, a"
        self.assertEqual(parse_depends(value), ["a", "b", "d"])

    def test_parse_packages(self):
        """Зависимости берутся из Depends и Pre-Depends."""
        db = parse_packages(PACKAGES)
        self.assertEqual(db["curl"], ["libc6", "zlib1g", "foo"])
        self.assertEqual(db["libc6"], ["base", "libc6"])


class TestRepoTests(TempFilesCase):
    """Тестовый репозиторий."""

    def test_load(self):
        """Файл разбирается в словарь зависимостей."""
        db = load_test_repo(self.repo_path)
        self.assertEqual(db["C"], ["D", "E"])
        self.assertEqual(db["F"], [])
        self.assertIn("F", known_packages(db))

    def test_bad_name(self):
        """Имя не из заглавных латинских букв - ошибка."""
        path = self.write("bad.txt", "a: B\n")
        with self.assertRaises(RepoError):
            load_test_repo(path)

    def test_duplicate(self):
        """Повторное описание пакета - ошибка."""
        path = self.write("dup.txt", "A: B\nA: C\n")
        with self.assertRaises(RepoError):
            load_test_repo(path)


class GraphTests(TempFilesCase):
    """Построение графа, циклы, обратные зависимости."""

    def graph(self, root="A", depth=3, substring=""):
        """Строит граф тестового репозитория."""
        db = load_test_repo(self.repo_path)
        return build_graph(lambda pkg: db.get(pkg, []), root, depth,
                           substring)

    def test_full_graph(self):
        """Граф полностью раскрывается при достаточной глубине."""
        graph = self.graph()
        self.assertEqual(graph["A"], ["B", "C"])
        self.assertEqual(graph["E"], ["A"])
        self.assertEqual(graph["F"], [])

    def test_depth_limit(self):
        """При глубине 1 раскрыт только корень."""
        graph = self.graph(depth=1)
        self.assertEqual(graph["A"], ["B", "C"])
        self.assertEqual(graph["B"], [])
        self.assertNotIn("D", graph)

    def test_depth_zero(self):
        """При глубине 0 в графе только корень."""
        self.assertEqual(dict(self.graph(depth=0)), {"A": []})

    def test_filter(self):
        """Пакеты с подстрокой в имени пропускаются."""
        graph = self.graph(substring="E")
        self.assertNotIn("E", graph)
        self.assertEqual(graph["C"], ["D"])

    def test_cycle(self):
        """Цикл A -> C -> E -> A обнаруживается и обход завершается."""
        cycles = find_cycles(self.graph())
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0][0], cycles[0][-1])
        self.assertEqual(set(cycles[0]), {"A", "C", "E"})

    def test_reverse(self):
        """Обратные зависимости D: B и C, затем A, затем E и G."""
        db = load_test_repo(self.repo_path)
        rev = reverse_index(db)
        graph = build_graph(lambda pkg: rev.get(pkg, []), "D", 3)
        self.assertEqual(graph["D"], ["B", "C"])
        self.assertEqual(graph["A"], ["E", "G"])


class RenderTests(TempFilesCase):
    """Представления графа."""

    def test_dot(self):
        """Graphviz-описание содержит рёбра и корень."""
        db = load_test_repo(self.repo_path)
        graph = build_graph(lambda pkg: db.get(pkg, []), "A", 3)
        dot = to_dot(graph, "A")
        self.assertIn('"A" -> "B";', dot)
        self.assertTrue(dot.startswith("digraph"))

    def test_dot_reverse_flips_arrows(self):
        """В режиме reverse стрелки идут от зависимого к зависимости."""
        graph = {"D": ["B"], "B": []}
        self.assertIn('"B" -> "D";', to_dot(graph, "D", reverse=True))

    def test_svg_is_valid_xml(self):
        """SVG - корректный XML с узлами графа."""
        db = load_test_repo(self.repo_path)
        graph = build_graph(lambda pkg: db.get(pkg, []), "A", 3)
        root = etree.fromstring(to_svg(graph, "A"))
        self.assertTrue(root.tag.endswith("svg"))


class ConfigTests(TempFilesCase):
    """Конфигурационный файл и обработка ошибок."""

    def test_valid(self):
        """Корректный конфиг читается и форматируется."""
        cfg = load_config(self.config())
        self.assertEqual(cfg["max_depth"], 3)
        self.assertIn("test_mode: true", format_config(cfg))

    def test_missing_file(self):
        """Отсутствующий файл конфигурации - ошибка."""
        with self.assertRaises(ConfigError):
            load_config(os.path.join(self.tmp, "none.xml"))

    def test_broken_xml(self):
        """Некорректный XML - ошибка."""
        path = self.write("broken.xml", "<config><package>")
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_bad_values(self):
        """Неверные значения параметров - ошибки."""
        bad = [self.config(depth="x"), self.config(depth="-1"),
               self.config(mode="maybe"), self.config(pkg="a"),
               self.config(repo=os.path.join(self.tmp, "no.txt"))]
        for path in bad:
            with self.subTest(path=path):
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_missing_param(self):
        """Отсутствие обязательного параметра - ошибка."""
        path = self.write("m.xml", "<config><package>A</package></config>")
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_real_mode_requires_url(self):
        """В обычном режиме репозиторий должен быть http(s) URL."""
        path = self.config(pkg="curl", mode="false", repo="ftp://x")
        with self.assertRaises(ConfigError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()

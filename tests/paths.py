"""Добавляет каталог src в sys.path для импорта модулей в тестах."""

import os
import sys

SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC)

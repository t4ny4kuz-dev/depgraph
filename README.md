# Визуализация графа зависимостей пакетов (вариант 15)

CLI-инструмент на Python 3.8+ (только стандартная библиотека). Формат пакетов — Ubuntu (apt).
Менеджеры пакетов (`apt`, `dpkg`) и сторонние библиотеки для получения зависимостей **не используются**:
индекс `Packages.gz` скачивается по URL и разбирается вручную.

## Структура репозитория
```
src/
  depgraph.py   - CLI (точка входа)
  config.py     - чтение и проверка XML-конфига
  repo.py       - загрузка и разбор apt-репозитория / тестового файла
  graph.py      - BFS с рекурсией, циклы, обратные зависимости
  render.py     - Graphviz (dot), SVG, сохранение картинки
  errors.py     - исключения
tests/          - модульные тесты (unittest)
config.xml          - конфиг для тестового репозитория
config_ubuntu.xml   - конфиг для реального репозитория Ubuntu
test_repo.txt       - тестовый граф (A, B, C... + цикл)
run.sh / run.bat / Makefile - скрипты запуска
.gitignore
```

## Запуск и тесты
```
./run.sh config.xml --show          # Linux / macOS
run.bat config.xml --show           # Windows
make run                            # через Makefile
python3 -m unittest discover -s tests -v   # тесты (или: make test)
```

## Конфигурационный файл (XML)

```
<config>
    <package>A</package>               <!-- имя пакета -->
    <repository>test_repo.txt</repository>  <!-- URL Packages.gz или путь к тестовому файлу -->
    <test_mode>true</test_mode>        <!-- режим тестового репозитория -->
    <max_depth>3</max_depth>           <!-- максимальная глубина -->
    <filter></filter>                  <!-- подстрока для фильтрации пакетов -->
</config>
```

## Параметры командной строки
```
python3 src/depgraph.py [config.xml] [--mode direct|graph|reverse|dot] [--show-config] [--out file.dot] [--image graph.svg|graph.png] [--show]
```

## Этап 1. Минимальный прототип с конфигурацией

Параметры читаются из XML; `--show-config` выводит их в формате ключ-значение.
```
$ python3 src/depgraph.py config.xml --show-config
package: A
repository: test_repo.txt
test_mode: true
max_depth: 3
filter:
```

Обработка ошибок для всех параметров:
```
Ошибка: файл конфигурации не найден: nope.xml
Ошибка: некорректный XML в /tmp/b.xml: no element found: line 2, column 0
Ошибка: <test_mode>: ожидается true или false, получено 'maybe'
Ошибка: <max_depth>: ожидается целое число, получено '-x'
Ошибка: <repository>: файл тестового репозитория не найден: nofile.txt
Ошибка: <package>: недопустимое имя 'curl' (ожидается: заглавные латинские буквы)
```
Также проверяются: отсутствие параметра, пустое имя, отрицательная глубина, URL без `http(s)://`.

Коммит: `feat(stage1): CLI prototype with XML configuration`

## Этап 2. Сбор данных

Скачивается `Packages.gz` (или `.xz`), разбирается формат Debian control (`Package`, `Depends`, `Pre-Depends`).
Из зависимости убираются версии `(>= 1.0)` и архитектура `:any`; из альтернатив `a | b` берётся первая.
```
python3 src/depgraph.py config_ubuntu.xml --mode direct
```
```
Прямые зависимости пакета curl:
  libc6
  libcurl4
  zlib1g
```
(Для демонстрации нужен доступ в интернет.)

Коммит: `feat(stage2): fetch direct dependencies from apt repository`

## Этап 3. Основные операции

Граф строится BFS с рекурсией: каждый вызов `level()` обрабатывает один уровень, затем рекурсивно вызывается для следующего.
Учитываются: `max_depth` (корень на глубине 0), фильтр по подстроке, циклы (множество `visited`, найденные циклы выводятся).
```
$ python3 src/depgraph.py config.xml
Граф зависимостей A (глубина <= 3):
  A -> B, C
  B -> D
  C -> D, E
  D -> F
  E -> A
  F -> (нет)
Обнаружены циклические зависимости:
  A -> C -> E -> A
```
Глубина 1 (`<max_depth>1</max_depth>`):
```
  A -> B, C
  B -> (нет)
  C -> (нет)
```
Фильтр `E` (`<filter>E</filter>`) — пакет E исключается, цикл исчезает:
```
  A -> B, C
  B -> D
  C -> D
  D -> F
  F -> (нет)
```

Коммит: `feat(stage3): BFS dependency graph with depth, filter and cycles`

## Этап 4. Обратные зависимости

Строится обратный индекс «пакет → кто от него зависит», далее используется тот же BFS.
```
$ python3 src/depgraph.py config.xml --mode reverse   # package = D
Обратные зависимости D (кто зависит от пакета):
  D -> B, C
  B -> A, H
  C -> A
  A -> E, G
  H -> (нет)
  E -> (нет)
  G -> (нет)
Всего пакетов, зависящих от D: 6
```

Коммит: `feat(stage4): reverse dependencies mode`

## Этап 5. Визуализация

```
$ python3 src/depgraph.py config.xml --mode dot --out graph.dot
digraph dependencies {
  rankdir=LR;
  node [shape=box];
  "A" [style=filled, fillcolor=lightblue];
  "A" -> "B";
  "A" -> "C";
  "B" -> "D";
  "C" -> "D";
  "C" -> "E";
  "D" -> "F";
  "E" -> "A";
  "F";
}
```
Картинка:
```
python3 src/depgraph.py config.xml --image graph.svg   # встроенный рендер, ничего ставить не надо (открыть в браузере)
python3 src/depgraph.py config.xml --image graph.png   # PNG через Graphviz (нужна команда dot)
```
Работает и с `--mode reverse`.

Для трёх реальных пакетов (например `curl`, `git`, `nginx`) нужно сделать скриншоты:

![curl](screenshots/curl.png)
![git](screenshots/git.png)
![nginx](screenshots/nginx.png)

### Сравнение со штатным инструментом
Штатная команда: `apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances <пакет>`.
Возможные расхождения:
- `apt-cache` показывает **все альтернативы** (`a | b`), а инструмент берёт только первую;
- `apt-cache` учитывает версии, установленные в системе и все подключённые репозитории (universe, updates), а инструмент — один индекс `Packages.gz`;
- виртуальные пакеты `apt-cache` показывает как `<имя>`, у инструмента они листья без зависимостей;
- у `apt-cache` нет ограничения глубины и фильтра по подстроке.

Коммит: `feat(stage5): Graphviz output`

## Коммиты
```
git init
git add -A
git commit -m "feat(stage1): CLI prototype with XML configuration"
```
(по одному коммиту на этап, сообщения указаны в каждом разделе)

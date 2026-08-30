"""
Проверить результат работы утилиты на синтетическом образце.

Смоук собранного исполняемого файла: сам exe запускает шаг CI, а этот
скрипт разбирает выходной .cdr и сверяет структуру.

Запуск: PYTHONPATH=src uv run python scripts/verify_output.py <результат.cdr>
"""

from __future__ import annotations

import sys
from pathlib import Path

from lbs_liner.cdr_read import CdrDocument

# argv: имя скрипта + путь к результату.
_EXPECTED_ARGC = 2
# В выходе ровно два объекта: красная линия и синяя.
_EXPECTED_OBJECTS = 2


def find_problems(doc: CdrDocument) -> list[str]:
    """Собрать список расхождений выходного файла с ожидаемой структурой."""
    problems = []
    objects = doc.curve_objects()
    if len(objects) != _EXPECTED_OBJECTS:
        return [f'ожидалось 2 объекта, найдено {len(objects)}']
    for obj in objects:
        if obj.fill_id is not None:
            problems.append('у объекта осталась заливка')
        if obj.outl_id is None:
            problems.append('у объекта нет обводки')
        open_subs = [sub for sub in obj.world_subpaths() if not sub.closed]
        if len(open_subs) != 1:
            problems.append(f'ожидалась одна открытая линия, найдено {len(open_subs)}')
    if len({obj.outl_id for obj in objects}) != _EXPECTED_OBJECTS:
        problems.append('обводки объектов совпадают — красная и синяя не различены')
    return problems


def main() -> int:
    """Разобрать выходной файл и сверить структуру двойной линии."""
    if len(sys.argv) != _EXPECTED_ARGC:
        sys.stdout.write('использование: verify_output.py <результат.cdr>\n')
        return 1
    problems = find_problems(CdrDocument.load(Path(sys.argv[1])))
    if problems:
        sys.stdout.write('\n'.join(problems) + '\n')
        return 1
    sys.stdout.write('смоук пройден: два объекта, открытая линия, разные обводки\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())

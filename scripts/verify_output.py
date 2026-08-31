"""
Проверить результат работы утилиты на синтетическом образце.

Смоук собранного исполняемого файла: сам exe запускает шаг CI, а этот
скрипт разбирает выходной .cdr и сверяет структуру: исходные объекты
целы, двойная линия добавлена отдельным новым слоем.

Запуск: PYTHONPATH=src uv run python scripts/verify_output.py <результат.cdr>
"""

from __future__ import annotations

import sys
from pathlib import Path

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.cdr_write import DEFAULT_LAYER_NAME

# argv: имя скрипта + путь к результату.
_EXPECTED_ARGC = 2
# В новом слое ровно два объекта: красная линия и синяя.
_EXPECTED_NEW = 2
# После преобразования из исходных кривых остаётся только чужой слой.
_EXPECTED_OLD = 1


def find_problems(doc: CdrDocument) -> list[str]:
    """Собрать список расхождений выходного файла с ожидаемой структурой."""
    problems = []
    objects = doc.curve_objects()
    new = [
        obj for obj in objects if doc.layer_name(obj.layer_chunk) == DEFAULT_LAYER_NAME
    ]
    old = [
        obj for obj in objects if doc.layer_name(obj.layer_chunk) != DEFAULT_LAYER_NAME
    ]
    if len(new) != _EXPECTED_NEW:
        problems.append(f'в слое «{DEFAULT_LAYER_NAME}» {len(new)} объектов, ждали 2')
    if len(old) != _EXPECTED_OLD:
        problems.append(f'посторонних кривых {len(old)}, ждали {_EXPECTED_OLD}')
    if any(obj.fill_id is None for obj in old):
        problems.append('у постороннего объекта пропала заливка')
    for obj in new:
        if obj.fill_id is None:
            problems.append('у нового объекта нет ссылки на «нет заливки»')
        if obj.outl_id is None:
            problems.append('у нового объекта нет обводки')
        open_subs = [sub for sub in obj.world_subpaths() if not sub.closed]
        if len(open_subs) != 1:
            problems.append(f'ждали одну открытую линию, нашли {len(open_subs)}')
    if len({obj.outl_id for obj in new}) != _EXPECTED_NEW:
        problems.append(
            'обводки новых объектов совпадают — красная и синяя не различены'
        )
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
    sys.stdout.write(
        'смоук пройден: исходные объекты целы, новый слой несёт две линии\n'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

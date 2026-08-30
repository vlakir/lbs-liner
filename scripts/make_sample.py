"""
Сгенерировать синтетический образец CDR (для смоука и examples/).

Запуск: PYTHONPATH=src uv run python scripts/make_sample.py <путь.cdr>
"""

from __future__ import annotations

import sys
from pathlib import Path

from lbs_liner.synthetic import build_sample_cdr

# argv: имя скрипта + путь к образцу.
_EXPECTED_ARGC = 2


def main() -> int:
    """Собрать образец по пути из argv."""
    if len(sys.argv) != _EXPECTED_ARGC:
        sys.stdout.write('использование: make_sample.py <путь.cdr>\n')
        return 1
    path = build_sample_cdr(Path(sys.argv[1]))
    sys.stdout.write(f'образец собран: {path}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())

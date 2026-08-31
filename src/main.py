"""Точка входа CLI: залитая область в CDR → двойная красно-синяя линия."""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

from lbs_liner.convert import (
    DEFAULT_BLUE_PT,
    DEFAULT_GAP_PT,
    DEFAULT_RED_PT,
    convert_file,
    lines_name,
    run_batch,
)
from lbs_liner.geometry import NoZoneError
from lbs_liner.riff import CdrFormatError

logger = logging.getLogger(__name__)


def _stdout_filter(record: logging.LogRecord) -> bool:
    """Пропускать в stdout только записи ниже WARNING (DEBUG/INFO)."""
    return record.levelno < logging.WARNING


def _configure_logging() -> None:
    """DEBUG/INFO — в stdout, WARNING и выше — в stderr."""
    # Консоль с узкой кодировкой (cp1252 и т.п.) не должна ронять вывод:
    # невлезающие символы заменяются, а не поднимают UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors='replace')
    fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s')

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(_stdout_filter)
    stdout_handler.setFormatter(fmt)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)


def build_parser() -> argparse.ArgumentParser:
    """Аргументы командной строки."""
    parser = argparse.ArgumentParser(
        prog='lbs-liner',
        description=(
            'Превращает залитую область в CDR-файле CorelDRAW в двойную '
            'контурную линию: красная — со стороны бывшей заливки, '
            'синяя — снаружи.'
        ),
    )
    parser.add_argument(
        'input',
        type=Path,
        nargs='?',
        default=None,
        help=(
            'входной .cdr (CorelDRAW X7+); без него обрабатываются все .cdr '
            'текущей папки, кроме уже готовых *-lines.cdr'
        ),
    )
    parser.add_argument(
        '-o',
        '--output',
        type=Path,
        default=None,
        help='выходной .cdr (по умолчанию: <вход>-lines.cdr)',
    )
    parser.add_argument(
        '--red-width',
        type=float,
        default=DEFAULT_RED_PT,
        help=f'толщина красной линии, пункты (по умолчанию {DEFAULT_RED_PT})',
    )
    parser.add_argument(
        '--blue-width',
        type=float,
        default=DEFAULT_BLUE_PT,
        help=f'толщина синей линии, пункты (по умолчанию {DEFAULT_BLUE_PT})',
    )
    parser.add_argument(
        '--gap',
        type=float,
        default=DEFAULT_GAP_PT,
        help=(
            'просвет между краями линий, пункты '
            f'(по умолчанию {DEFAULT_GAP_PT} — вплотную)'
        ),
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Выполнить преобразование; вернуть код возврата процесса."""
    if args.input is None:
        if args.output is not None:
            logger.error('-o работает только вместе с одним входным файлом')
            return 2
        return run_batch(Path.cwd(), args.red_width, args.blue_width, args.gap)
    output = args.output or lines_name(args.input)
    try:
        convert_file(args.input, output, args.red_width, args.blue_width, args.gap)
    except NoZoneError as exc:
        no_zone_reason = str(exc)
    except CdrFormatError, ValueError, OSError:
        logger.exception('не получилось')
        return 1
    else:
        logger.info('линии добавлены новым слоем, исходные слои не тронуты')
        return 0
    logger.error(no_zone_reason)
    return 1


def main() -> None:
    """Запуск приложения."""
    _configure_logging()
    sys.exit(run(build_parser().parse_args()))


if __name__ == '__main__':
    main()

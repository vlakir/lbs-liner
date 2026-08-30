"""Точка входа CLI: залитая область в CDR → двойная красно-синяя линия."""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.cdr_write import write_output
from lbs_liner.geometry import build_double_line, classify
from lbs_liner.riff import CdrFormatError

logger = logging.getLogger(__name__)

DEFAULT_WIDTH_MM = 0.2
DEFAULT_GAP_MM = 0.6


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
    parser.add_argument('input', type=Path, help='входной .cdr (CorelDRAW X7+)')
    parser.add_argument(
        '-o',
        '--output',
        type=Path,
        default=None,
        help='выходной .cdr (по умолчанию: <вход>-lines.cdr)',
    )
    parser.add_argument(
        '--width',
        type=float,
        default=DEFAULT_WIDTH_MM,
        help=f'толщина каждой линии, мм (по умолчанию {DEFAULT_WIDTH_MM})',
    )
    parser.add_argument(
        '--gap',
        type=float,
        default=DEFAULT_GAP_MM,
        help=f'расстояние между осями линий, мм (по умолчанию {DEFAULT_GAP_MM})',
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Выполнить преобразование; вернуть код возврата процесса."""
    output = args.output or args.input.with_name(f'{args.input.stem}-lines.cdr')
    try:
        doc = CdrDocument.load(args.input)
        objects = doc.curve_objects()
        logger.info('объектов-кривых в файле: %d', len(objects))
        contours = classify(objects)
        logger.info(
            'контуры: открытых %d, замкнутых %d, дублей отброшено %d',
            len(contours.open_lines),
            len(contours.closed_rings),
            contours.dropped_duplicates,
        )
        double = build_double_line(contours, gap_mm=args.gap)
        logger.info(
            'построено путей: красных %d, синих %d', len(double.red), len(double.blue)
        )
        write_output(
            doc,
            contours.zone_object,
            double.red,
            double.blue,
            width_mm=args.width,
            out_path=output,
        )
    except CdrFormatError, ValueError, OSError:
        logger.exception('не получилось')
        return 1
    logger.info('двойная линия добавлена новым слоем, исходное содержимое не менялось')
    logger.info('готово: %s', output)
    return 0


def main() -> None:
    """Запуск приложения."""
    _configure_logging()
    sys.exit(run(build_parser().parse_args()))


if __name__ == '__main__':
    main()

"""Точка входа CLI: залитая область в CDR → двойная красно-синяя линия."""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.cdr_write import write_output
from lbs_liner.geometry import NoZoneError, build_double_line, classify
from lbs_liner.riff import CdrFormatError

logger = logging.getLogger(__name__)

DEFAULT_RED_PT = 3.0
DEFAULT_BLUE_PT = 2.0
DEFAULT_GAP_PT = 0.0
PT_PER_INCH = 72.0


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


LINES_SUFFIX = '-lines'


def _convert_file(
    input_path: Path,
    output_path: Path,
    red_pt: float,
    blue_pt: float,
    gap_pt: float,
) -> None:
    """Преобразовать один файл (исключения пробрасываются наружу)."""
    doc = CdrDocument.load(input_path)
    objects = doc.curve_objects()
    logger.info('%s: объектов-кривых %d', input_path.name, len(objects))
    contours = classify(objects)
    logger.info(
        'контуры: открытых %d, замкнутых %d, дублей отброшено %d',
        len(contours.open_lines),
        len(contours.closed_rings),
        contours.dropped_duplicates,
    )
    # Оси смещены на полтолщины (+половина просвета) — края линий
    # смыкаются ровно на исходной трассе.
    double = build_double_line(
        contours,
        red_offset_in=(red_pt / 2 + gap_pt / 2) / PT_PER_INCH,
        blue_offset_in=(blue_pt / 2 + gap_pt / 2) / PT_PER_INCH,
    )
    logger.info(
        'построено путей: красных %d, синих %d', len(double.red), len(double.blue)
    )
    write_output(
        doc,
        contours.zone_object,
        double.red,
        double.blue,
        red_width_pt=red_pt,
        blue_width_pt=blue_pt,
        out_path=output_path,
    )
    logger.info('готово: %s', output_path)


def _lines_name(input_path: Path) -> Path:
    return input_path.with_name(f'{input_path.stem}{LINES_SUFFIX}.cdr')


def _run_batch(folder: Path, red_pt: float, blue_pt: float, gap_pt: float) -> int:
    """Обработать все .cdr папки, кроме уже готовых *-lines.cdr."""
    inputs = sorted(
        path
        for path in folder.glob('*.cdr', case_sensitive=False)
        if not path.stem.lower().endswith(LINES_SUFFIX)
    )
    if not inputs:
        logger.error('в папке %s нет файлов .cdr для обработки', folder)
        return 1
    failures = 0
    skipped = 0
    for path in inputs:
        try:
            _convert_file(path, _lines_name(path), red_pt, blue_pt, gap_pt)
        except NoZoneError:
            logger.info('%s: залитой зоны нет — пропущен', path.name)
            skipped += 1
        except CdrFormatError, ValueError, OSError:
            logger.exception('пропущен из-за ошибки: %s', path.name)
            failures += 1
    logger.info(
        'обработано: %d, без зоны: %d, с ошибками: %d',
        len(inputs) - failures - skipped,
        skipped,
        failures,
    )
    return 1 if failures else 0


def run(args: argparse.Namespace) -> int:
    """Выполнить преобразование; вернуть код возврата процесса."""
    if args.input is None:
        if args.output is not None:
            logger.error('-o работает только вместе с одним входным файлом')
            return 2
        return _run_batch(Path.cwd(), args.red_width, args.blue_width, args.gap)
    output = args.output or _lines_name(args.input)
    try:
        _convert_file(args.input, output, args.red_width, args.blue_width, args.gap)
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

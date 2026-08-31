"""Конвейер преобразования: общая логика для CLI и GUI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.cdr_write import write_output
from lbs_liner.geometry import NoZoneError, build_double_line, classify
from lbs_liner.riff import CdrFormatError

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RED_PT = 3.0
DEFAULT_BLUE_PT = 2.0
DEFAULT_GAP_PT = 0.0
PT_PER_INCH = 72.0
LINES_SUFFIX = '-lines'


def lines_name(input_path: Path) -> Path:
    """Имя результата рядом со входом: <имя>-lines.cdr."""
    return input_path.with_name(f'{input_path.stem}{LINES_SUFFIX}.cdr')


def convert_file(
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


def run_batch(folder: Path, red_pt: float, blue_pt: float, gap_pt: float) -> int:
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
            convert_file(path, lines_name(path), red_pt, blue_pt, gap_pt)
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

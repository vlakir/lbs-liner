"""
Классификация контуров залитой области и построение двойной линии.

Внутренние единицы — дюймы (родные для CDR после нормировки).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import unary_union

from lbs_liner.cdr_read import CurveObject, Subpath

logger = logging.getLogger(__name__)


class NoZoneError(ValueError):
    """В файле нет залитой зоны — преобразовывать нечего."""


MM_PER_INCH = 25.4

# Дегенеративные подпути (мусор на искусственных рёбрах) — меньше 1 мм².
_MIN_RING_AREA = (1.0 / MM_PER_INCH) ** 2
# Порог совпадения трасс: столько вершин кандидата должно лежать вплотную
# к трассе зоны, чтобы объект считался её дублем-черновиком.
_DUPLICATE_SHARE = 0.6
_DUPLICATE_DISTANCE = 0.1
# Слишком короткие объекты дублем зоны не считаются.
_MIN_DUPLICATE_POINTS = 10
# Большинство при голосовании сэмпл-точек за сторону.
_MAJORITY = 0.5
# Минимум точек: 2 — отрезок, 4 — замкнутое кольцо (с дублем вершины).
_MIN_LINE_POINTS = 2
_MIN_RING_POINTS = 4


@dataclass
class ClassifiedContours:
    """Результат разбора: что превращаем в двойную линию."""

    zone_object: CurveObject
    zone_polygon: Polygon
    open_lines: list[list[tuple[float, float]]] = field(default_factory=list)
    closed_rings: list[list[tuple[float, float]]] = field(default_factory=list)
    dropped_duplicates: int = 0


@dataclass
class DoubleLine:
    """Готовые осевые пути двойной линии."""

    red: list[Subpath] = field(default_factory=list)
    blue: list[Subpath] = field(default_factory=list)


def classify(objects: list[CurveObject]) -> ClassifiedContours:
    """
    Найти зону, снять искусственные рёбра, собрать контуры.

    Зона — объект с самой большой рамкой; объекты, чья трасса почти
    целиком совпадает с трассой зоны, считаются черновиками-дублями
    и отбрасываются; остальные замкнутые контуры идут в работу.
    """
    if not objects:
        msg = 'в файле не нашлось ни одного объекта-кривой'
        raise NoZoneError(msg)

    all_candidates = [(obj, obj.world_subpaths()) for obj in objects]
    # Зона — обязательно залитая кривая: без заливки «красноты» в файле нет,
    # и превращать в двойную линию просто самую большую кривую нельзя.
    filled = [pair for pair in all_candidates if pair[0].fill_id]
    if not filled:
        msg = 'в файле нет залитой зоны — преобразовывать нечего'
        raise NoZoneError(msg)
    zone_obj, zone_subpaths = max(filled, key=lambda pair: _bbox_area(pair[1]))
    # Чужие слои не трогаем: в работу идут только соседи зоны по слою.
    candidates = [
        pair for pair in all_candidates if pair[0].layer_chunk is zone_obj.layer_chunk
    ]
    skipped = len(all_candidates) - len(candidates)
    if skipped:
        logger.info('кривых на других слоях: %d — не участвуют', skipped)

    main_ring, islands = _zone_rings(zone_subpaths)
    zone_polygon = _build_zone_polygon(main_ring, islands)

    result = ClassifiedContours(zone_object=zone_obj, zone_polygon=zone_polygon)

    zone_track = LineString(main_ring)
    open_line = _strip_artificial_edges(main_ring)
    if open_line is None:
        result.closed_rings.append(main_ring)
        logger.info('искусственные рёбра не найдены — зона остаётся замкнутой')
    else:
        result.open_lines.append(open_line)
    result.closed_rings.extend(islands)

    for obj, subpaths in candidates:
        if obj is zone_obj:
            continue
        if _is_duplicate_of(subpaths, zone_track):
            result.dropped_duplicates += 1
            logger.info(
                'объект с %d подпутями лежит на трассе зоны — это черновик',
                len(subpaths),
            )
            continue
        for sub in subpaths:
            if not sub.closed:
                result.open_lines.append(sub.points)
            elif _ring_area(sub.points) >= _MIN_RING_AREA:
                result.closed_rings.append(sub.points)
    return result


def build_double_line(
    contours: ClassifiedContours, *, red_offset_in: float, blue_offset_in: float
) -> DoubleLine:
    """
    Сместить контуры: красная ось — к зоне, синяя — от неё (дюймы).

    При смещениях в полтолщины каждой линии их края смыкаются ровно
    на исходной трассе.
    """
    zone = contours.zone_polygon
    out = DoubleLine()

    for points in contours.open_lines:
        line = LineString(points)
        left_score = _side_score(
            line.offset_curve(red_offset_in, join_style='mitre', mitre_limit=5.0), zone
        )
        right_score = _side_score(
            line.offset_curve(-red_offset_in, join_style='mitre', mitre_limit=5.0), zone
        )
        red_sign = 1.0 if left_score >= right_score else -1.0
        red_geom = line.offset_curve(
            red_sign * red_offset_in, join_style='mitre', mitre_limit=5.0
        )
        blue_geom = line.offset_curve(
            -red_sign * blue_offset_in, join_style='mitre', mitre_limit=5.0
        )
        out.red.extend(_as_subpaths(red_geom, closed=False))
        out.blue.extend(_as_subpaths(blue_geom, closed=False))

    for ring in contours.closed_rings:
        polygon = Polygon(ring)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        red_inside = _red_is_inside(polygon, zone, red_offset_in)
        inner_offset = red_offset_in if red_inside else blue_offset_in
        outer_offset = blue_offset_in if red_inside else red_offset_in
        outer = polygon.buffer(outer_offset, join_style='mitre', mitre_limit=5.0)
        inner = polygon.buffer(-inner_offset, join_style='mitre', mitre_limit=5.0)
        outer_rings = _boundary_subpaths(outer)
        inner_rings = _boundary_subpaths(inner)
        if not inner_rings:
            logger.warning(
                'контур площадью %.2f мм² уже зазора — внутренняя линия схлопнулась, '
                'оставлена только внешняя',
                _ring_area(ring) * MM_PER_INCH**2,
            )
        if red_inside:
            out.red.extend(inner_rings)
            out.blue.extend(outer_rings)
        else:
            out.red.extend(outer_rings)
            out.blue.extend(inner_rings)
    return out


def _bbox_area(subpaths: list[Subpath]) -> float:
    xs = [x for sub in subpaths for x, _ in sub.points]
    ys = [y for sub in subpaths for _, y in sub.points]
    if not xs:
        return 0.0
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _ring_area(points: list[tuple[float, float]]) -> float:
    """Площадь кольца по формуле шнурков (по модулю)."""
    area = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1], strict=True):
        area += x0 * y1 - x1 * y0
    return abs(area) / 2.0


def _zone_rings(
    subpaths: list[Subpath],
) -> tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]:
    """Главное кольцо зоны и её островки (без дегенеративного мусора)."""
    ordered = sorted(subpaths, key=lambda sub: _ring_area(sub.points), reverse=True)
    main = ordered[0].points
    islands = [
        sub.points
        for sub in ordered[1:]
        if sub.closed and _ring_area(sub.points) >= _MIN_RING_AREA
    ]
    return main, islands


def _build_zone_polygon(
    main_ring: list[tuple[float, float]],
    islands: list[list[tuple[float, float]]],
) -> Polygon:
    shell = Polygon(main_ring)
    if not shell.is_valid:
        shell = shell.buffer(0)
    holes = []
    for ring in islands:
        hole = Polygon(ring)
        if not hole.is_valid:
            hole = hole.buffer(0)
        holes.append(hole)
    zone = shell.difference(unary_union(holes)) if holes else shell
    if zone.is_empty:
        msg = 'полигон зоны пуст — не из чего строить стороны'
        raise ValueError(msg)
    return zone


def _strip_artificial_edges(
    ring: list[tuple[float, float]],
) -> list[tuple[float, float]] | None:
    """
    Убрать из кольца цепочку длинных замыкающих рёбер.

    Рёбра настоящей границы на порядки короче искусственных; порог —
    адаптивный от медианы. Возвращает открытую линию или None,
    если длинных рёбер нет.
    """
    n = len(ring)
    lengths = []
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        lengths.append(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    median = sorted(lengths)[n // 2]
    threshold = max(1.0, 20.0 * median)
    long_edges = {i for i, length in enumerate(lengths) if length > threshold}
    if not long_edges:
        return None
    chain = _longest_run(long_edges, n)
    logger.info(
        'снята цепочка из %d искусственных рёбер (порог %.2f дюйма)',
        len(chain),
        threshold,
    )
    # Ребро i соединяет вершины i и i+1; цепочка рёбер [a..b] выбрасывает
    # внутренние вершины, открытая линия идёт от вершины (b+1) до вершины a.
    first = (max(chain) + 1) % n
    last = min(chain)
    if first <= last:
        return ring[first : last + 1]
    return ring[first:] + ring[: last + 1]


def _longest_run(edges: set[int], n: int) -> list[int]:
    """Самая длинная непрерывная (с учётом замыкания) цепочка индексов."""
    runs = []
    sorted_edges = sorted(edges)
    current = [sorted_edges[0]]
    for index in sorted_edges[1:]:
        if index == current[-1] + 1:
            current.append(index)
        else:
            runs.append(current)
            current = [index]
    runs.append(current)
    # Склейка через 0: последняя цепочка кончается на n-1, первая начинается с 0.
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == n - 1:
        runs[0] = runs[-1] + runs[0]
        runs.pop()
    return max(runs, key=len)


def _is_duplicate_of(subpaths: list[Subpath], zone_track: LineString) -> bool:
    """Лежит ли трасса объекта практически на трассе зоны."""
    points = [pt for sub in subpaths for pt in sub.points]
    if len(points) < _MIN_DUPLICATE_POINTS:
        return False
    sample = points[:: max(1, len(points) // 200)]
    close_count = sum(
        1 for pt in sample if zone_track.distance(Point(pt)) < _DUPLICATE_DISTANCE
    )
    return close_count / len(sample) >= _DUPLICATE_SHARE


def _side_score(geom: LineString | MultiLineString, zone: Polygon) -> float:
    """Доля сэмпл-точек линии, попавших внутрь зоны."""
    lines = list(geom.geoms) if isinstance(geom, MultiLineString) else [geom]
    inside = 0
    total = 0
    for line in lines:
        if line.is_empty:
            continue
        for i in range(21):
            pt = line.interpolate(i / 20.0, normalized=True)
            total += 1
            if zone.contains(pt):
                inside += 1
    return inside / total if total else 0.0


def _red_is_inside(polygon: Polygon, zone: Polygon, half_gap: float) -> bool:
    """
    Определить, лежит ли красная линия внутри замкнутого контура.

    Решает окружение: если сразу за контуром лежит красная сторона
    (дыра в зоне, «синий анклав») — красная линия идёт снаружи; если
    вокруг синяя земля (изолированное красное пятно) — внутри.
    """
    outer_offset = polygon.buffer(half_gap * 3).exterior
    outside_in_zone = _side_score(LineString(outer_offset.coords), zone) > _MAJORITY
    return not outside_in_zone


def _as_subpaths(geom: LineString | MultiLineString, *, closed: bool) -> list[Subpath]:
    lines = list(geom.geoms) if isinstance(geom, MultiLineString) else [geom]
    return [
        Subpath(points=list(line.coords), closed=closed)
        for line in lines
        if not line.is_empty and len(line.coords) >= _MIN_LINE_POINTS
    ]


def _boundary_subpaths(polygon: Polygon) -> list[Subpath]:
    """Все кольца полигона (или мультиполигона) как замкнутые подпути."""
    if polygon.is_empty:
        return []
    geoms = polygon.geoms if hasattr(polygon, 'geoms') else [polygon]
    out: list[Subpath] = []
    for geom in geoms:
        rings = [geom.exterior, *geom.interiors]
        out.extend(
            Subpath(points=list(ring.coords), closed=True)
            for ring in rings
            if len(ring.coords) >= _MIN_RING_POINTS
        )
    return out

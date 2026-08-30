"""Тесты классификации контуров и построения двойной линии."""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, Polygon

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.geometry import (
    NoZoneError,
    _side_score,
    _strip_artificial_edges,
    build_double_line,
    classify,
)


@pytest.fixture
def contours(sample_cdr: Path):  # noqa: ANN201
    doc = CdrDocument.load(sample_cdr)
    return classify(doc.curve_objects())


def test_classify_finds_zone_and_drops_draft(contours) -> None:  # noqa: ANN001
    """Зона — самый большой объект; черновик-дубль отброшен."""
    assert contours.dropped_duplicates == 1
    assert len(contours.open_lines) == 1
    # дыра-карман + пятно
    assert len(contours.closed_rings) == 2


def test_open_line_is_staircase_without_frame(contours) -> None:  # noqa: ANN001
    """Открытая линия — лесенка, без длинных замыкающих рёбер."""
    line = contours.open_lines[0]
    for (x0, y0), (x1, y1) in zip(line, line[1:], strict=False):
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        assert length < 1.0


def test_strip_returns_none_without_long_edges() -> None:
    """Кольцо из однородных рёбер остаётся замкнутым."""
    ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert _strip_artificial_edges(ring) is None


def test_double_line_sides(contours) -> None:  # noqa: ANN001
    """Красная линия — в бывшей розовой зоне, синяя — снаружи."""
    double = build_double_line(contours, gap_mm=2.0)
    zone = contours.zone_polygon
    red_main = max(double.red, key=lambda s: len(s.points))
    blue_main = max(double.blue, key=lambda s: len(s.points))
    assert _side_score(LineString(red_main.points), zone) > 0.8
    assert _side_score(LineString(blue_main.points), zone) < 0.2


def test_hole_ring_red_outside(contours) -> None:  # noqa: ANN001
    """У дыры-кармана красное кольцо снаружи, синее внутри."""
    double = build_double_line(contours, gap_mm=2.0)
    hole_center = Point(6.5, 0.25)  # (6, 0) + сдвиг (0.5, 0.25)
    red_rings = [s for s in double.red if s.closed]
    blue_rings = [s for s in double.blue if s.closed]
    red_around_hole = [
        s for s in red_rings if Polygon(s.points).contains(hole_center)
    ]
    blue_in_hole = [
        s for s in blue_rings if Polygon(s.points).contains(hole_center)
    ]
    assert red_around_hole
    assert blue_in_hole
    # красное кольцо дыры больше синего — оно снаружи
    assert Polygon(red_around_hole[0].points).area > Polygon(blue_in_hole[0].points).area


def test_isolated_blob_red_inside(contours) -> None:  # noqa: ANN001
    """У пятна вне зоны красное кольцо внутри, синее снаружи."""
    double = build_double_line(contours, gap_mm=2.0)
    blob_center = Point(-1.5, 1.25)  # (-2, 1) + сдвиг
    red = [s for s in double.red if s.closed and Polygon(s.points).contains(blob_center)]
    blue = [s for s in double.blue if s.closed and Polygon(s.points).contains(blob_center)]
    assert red
    assert blue
    assert Polygon(red[0].points).area < Polygon(blue[0].points).area


def test_foreign_layer_not_touched(contours) -> None:  # noqa: ANN001
    """Кривая с постороннего слоя не попадает в контуры."""
    for ring in contours.closed_rings:
        xs = [x for x, _ in ring]
        assert max(xs) < 15  # чужой квадрат живёт вокруг (20, 20)


def test_classify_rejects_empty() -> None:
    """Пустой список объектов — внятная ошибка."""
    with pytest.raises(NoZoneError, match='ни одного'):
        classify([])


def test_classify_requires_filled_zone() -> None:
    """Без залитой кривой зоны нет — самая большая кривая не подменяет её."""
    from lbs_liner.cdr_read import CurveObject
    from lbs_liner.riff import Chunk

    ring = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0), (0.0, 0.0)]
    unfilled = CurveObject(
        obj_chunk=Chunk(name='LIST', list_type='obj '),
        loda_raw=b'',
        points=ring,
        types=[0x0C, 0x44, 0x44, 0x44, 0x48],
        fill_id=None,
    )
    with pytest.raises(NoZoneError, match='залитой зоны'):
        classify([unfilled])

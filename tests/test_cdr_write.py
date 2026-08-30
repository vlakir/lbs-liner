"""Тесты записи: патч обводок, пересборка loda, сквозной прогон."""

from __future__ import annotations

import struct
from pathlib import Path

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.cdr_write import (
    BLUE_RGB,
    RED_RGB,
    _outl_block,
    _outl_width,
    _patch_outl,
    write_output,
)
from lbs_liner.geometry import build_double_line, classify
from lbs_liner.synthetic import OUTL_RECORD


def _color_at(record: bytes, offset: int) -> tuple[int, int, int]:
    model, palette, _, value = struct.unpack_from('<HHII', record, offset)
    return model, palette, value


def test_patch_outl_sets_width_and_color() -> None:
    """Патч меняет id, толщину и цвет в обоих местах записи."""
    patched = _patch_outl(OUTL_RECORD, new_id=7, width_units=5000, rgb=RED_RGB)
    assert len(patched) == len(OUTL_RECORD)
    assert struct.unpack_from('<I', patched, 0)[0] == 7
    assert _outl_width(patched) == 5000

    modern = _outl_block(patched, wanted_id=1)
    assert modern is not None
    model, _, value = _color_at(patched, modern + 18 + 46)
    assert model == 5
    assert value == 0xFF0000

    palette_block = _outl_block(patched, wanted_id=2)
    assert palette_block is not None
    model2, _, value2 = _color_at(patched, palette_block + 5)
    assert model2 == 5
    assert value2 == 0xFF0000
    # GUID палитры обнулён
    guid = patched[palette_block + 23 : palette_block + 39]
    assert guid == b'\x00' * 16


def test_full_pipeline_roundtrip(sample_cdr: Path, tmp_path: Path) -> None:
    """Вход → двойная линия → выход, который снова читается."""
    doc = CdrDocument.load(sample_cdr)
    contours = classify(doc.curve_objects())
    double = build_double_line(contours, gap_mm=2.0)
    out_path = tmp_path / 'out.cdr'
    write_output(
        doc, contours.zone_object, double.red, double.blue, width_mm=0.5, out_path=out_path
    )

    result = CdrDocument.load(out_path)
    objects = result.curve_objects()
    assert len(objects) == 2

    widths = set()
    colors = set()
    for obj in objects:
        assert obj.fill_id is None, 'заливка должна исчезнуть'
        assert obj.outl_id is not None
        record = _find_outl_record(result, obj.outl_id)
        widths.add(_outl_width(record))
        modern = _outl_block(record, wanted_id=1)
        assert modern is not None
        colors.add(_color_at(record, modern + 18 + 46)[2])
    expected_width = round(0.5 / 25.4 * 254000)
    assert widths == {expected_width}
    red_value = (RED_RGB[0] << 16) | (RED_RGB[1] << 8) | RED_RGB[2]
    blue_value = (BLUE_RGB[0] << 16) | (BLUE_RGB[1] << 8) | BLUE_RGB[2]
    assert colors == {red_value, blue_value}


def test_open_subpath_stays_open(sample_cdr: Path, tmp_path: Path) -> None:
    """У открытой линии нет бита замыкания ни на одной точке."""
    doc = CdrDocument.load(sample_cdr)
    contours = classify(doc.curve_objects())
    double = build_double_line(contours, gap_mm=2.0)
    out_path = tmp_path / 'out.cdr'
    write_output(
        doc, contours.zone_object, double.red, double.blue, width_mm=0.5, out_path=out_path
    )

    for obj in CdrDocument.load(out_path).curve_objects():
        subs = obj.world_subpaths()
        open_subs = [s for s in subs if not s.closed]
        assert len(open_subs) == 1
        # открытая линия в конце списка, замкнутые кольца перед ней
        assert not subs[-1].closed
        assert all(s.closed for s in subs[:-1])


def test_bbox_updated(sample_cdr: Path, tmp_path: Path) -> None:
    """bbox новых объектов отражает фактическую геометрию."""
    doc = CdrDocument.load(sample_cdr)
    contours = classify(doc.curve_objects())
    double = build_double_line(contours, gap_mm=2.0)
    out_path = tmp_path / 'out.cdr'
    write_output(
        doc, contours.zone_object, double.red, double.blue, width_mm=0.5, out_path=out_path
    )

    result = CdrDocument.load(out_path)
    all_points = [
        pt for sub in double.red + double.blue for pt in sub.points
    ]
    xs = [x for x, _ in all_points]
    for obj in result.curve_objects():
        bbox_chunks = obj.obj_chunk.find_all('bbox')
        assert bbox_chunks
        x0, _, x1, _ = struct.unpack('<4i', result.resolve(bbox_chunks[0]))
        assert x0 >= round((min(xs) - 0.01) * 254000)
        assert x1 <= round((max(xs) + 0.01) * 254000)


def _find_outl_record(doc: CdrDocument, outl_id: int) -> bytes:
    for chunk in doc.root.find_all('outl'):
        record = doc.resolve(chunk)
        if struct.unpack_from('<I', record, 0)[0] == outl_id:
            return record
    msg = f'нет записи обводки {outl_id}'
    raise AssertionError(msg)

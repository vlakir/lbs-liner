"""Тесты записи: патч обводок, аддитивный новый слой, сквозной прогон."""

from __future__ import annotations

import struct
from pathlib import Path

from lbs_liner.cdr_read import CdrDocument, CurveObject
from lbs_liner.cdr_write import (
    BLUE_RGB,
    DEFAULT_LAYER_NAME,
    RED_RGB,
    _outl_block,
    _outl_width,
    _patch_outl,
    write_output,
)
from lbs_liner.cdr_write import _rebuild_loda
from lbs_liner.geometry import build_double_line, classify
from lbs_liner.synthetic import OUTL_RECORD

# Реальная лода группы CorelDRAW 17–22 (нейтральная: пустой список
# растровых эффектов) — эталон родной раскладки: таблицы, сентинел,
# данные подряд без выравнивания.
GROUP_LODA = bytes.fromhex(
    '4f00000002000000140000002000000000000000280000002c0000004f000000'
    'c9000000e02e000000000000010000001b0000007b22537461636b6564426974'
    '6d617045666665637473223a7b7d7d'
)


def _color_at(record: bytes, offset: int) -> tuple[int, int, int]:
    model, palette, _, value = struct.unpack_from('<HHII', record, offset)
    return model, palette, value


def _convert(sample_cdr: Path, tmp_path: Path) -> tuple[CdrDocument, Path]:
    doc = CdrDocument.load(sample_cdr)
    contours = classify(doc.curve_objects())
    double = build_double_line(contours, gap_mm=2.0)
    out_path = tmp_path / 'out.cdr'
    write_output(
        doc,
        contours.zone_object,
        double.red,
        double.blue,
        width_mm=0.5,
        out_path=out_path,
    )
    return CdrDocument.load(out_path), out_path


def _new_objects(result: CdrDocument) -> list[CurveObject]:
    return [
        obj
        for obj in result.curve_objects()
        if result.layer_name(obj.layer_chunk) == DEFAULT_LAYER_NAME
    ]


def test_rebuild_loda_reproduces_corel_layout() -> None:
    """Пересборка без правок отдаёт кореловскую лоду байт-в-байт."""
    assert _rebuild_loda(GROUP_LODA, {}) == GROUP_LODA


def test_data_bodies_follow_tree_order(sample_cdr: Path, tmp_path: Path) -> None:
    """После записи тела чанков лежат в data-файлах в порядке дерева.

    Corel читает пулы потоком: смещение каждого следующего стаба обязано
    быть не меньше конца предыдущего в том же файле.
    """
    result, _ = _convert(sample_cdr, tmp_path)
    cursors: dict[int, int] = {}

    def walk(node) -> None:  # noqa: ANN001
        for child in node.children:
            if child.is_container:
                walk(child)
                continue
            try:
                file_index, size, offset = child.stub()
            except Exception:
                continue
            if file_index not in result.data:
                continue
            assert offset >= cursors.get(file_index, 0), (
                f'{child.name}: тело не по порядку ({offset})'
            )
            cursors[file_index] = offset + size

    walk(result.root)


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


def test_new_layer_holds_two_styled_objects(sample_cdr: Path, tmp_path: Path) -> None:
    """В новом слое два объекта: без заливки, красная и синяя обводки."""
    result, _ = _convert(sample_cdr, tmp_path)
    new_objects = _new_objects(result)
    assert len(new_objects) == 2

    widths = set()
    colors = set()
    for obj in new_objects:
        assert obj.fill_id is not None
        assert _is_nofill(result, obj.fill_id), 'заливка новых объектов не «нет»'
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


def test_original_objects_untouched(sample_cdr: Path, tmp_path: Path) -> None:
    """Все исходные объекты и слои остаются байт-в-байт."""
    original = CdrDocument.load(sample_cdr)
    original_lodas = sorted(obj.loda_raw for obj in original.curve_objects())
    result, _ = _convert(sample_cdr, tmp_path)

    by_layer: dict[str | None, list[CurveObject]] = {}
    for obj in result.curve_objects():
        by_layer.setdefault(result.layer_name(obj.layer_chunk), []).append(obj)
    old_objects = [
        obj
        for name, objs in by_layer.items()
        if name != DEFAULT_LAYER_NAME
        for obj in objs
    ]
    assert sorted(o.loda_raw for o in old_objects) == original_lodas
    assert all(o.fill_id == 1 for o in old_objects)
    assert {'Заливка', 'Топооснова'} <= set(by_layer)
    assert len(by_layer[DEFAULT_LAYER_NAME]) == 2


def test_new_ids_are_unique(sample_cdr: Path, tmp_path: Path) -> None:
    """spid новых объектов/группы/слоя не совпадают со старыми."""
    result, _ = _convert(sample_cdr, tmp_path)
    resolved = []
    for chunk in result.root.find_all('spid'):
        # В синтетике spid лежит прямо в payload, в реальных файлах — по стабу.
        body = chunk.payload
        if _looks_like_stub(result, chunk):
            body = result.resolve(chunk)
        resolved.append(body)
    assert len(resolved) == len(set(resolved)), 'дублирующиеся spid'


def _looks_like_stub(doc: CdrDocument, chunk) -> bool:  # noqa: ANN001
    file_index = struct.unpack_from('<I', chunk.payload, 0)[0]
    return file_index in doc.data


def test_open_subpath_stays_open(sample_cdr: Path, tmp_path: Path) -> None:
    """У новых объектов ровно одна открытая линия, кольца перед ней."""
    result, _ = _convert(sample_cdr, tmp_path)
    for obj in _new_objects(result):
        subs = obj.world_subpaths()
        open_subs = [s for s in subs if not s.closed]
        assert len(open_subs) == 1
        assert not subs[-1].closed
        assert all(s.closed for s in subs[:-1])


def test_bbox_updated(sample_cdr: Path, tmp_path: Path) -> None:
    """bbox новых объектов отражает фактическую геометрию."""
    doc = CdrDocument.load(sample_cdr)
    contours = classify(doc.curve_objects())
    double = build_double_line(contours, gap_mm=2.0)
    out_path = tmp_path / 'out.cdr'
    write_output(
        doc,
        contours.zone_object,
        double.red,
        double.blue,
        width_mm=0.5,
        out_path=out_path,
    )
    result = CdrDocument.load(out_path)
    all_points = [pt for sub in double.red + double.blue for pt in sub.points]
    xs = [x for x, _ in all_points]
    for obj in _new_objects(result):
        bbox_chunks = obj.obj_chunk.find_all('bbox')
        assert bbox_chunks
        x0, _, x1, _ = struct.unpack('<4i', result.resolve(bbox_chunks[0]))
        assert x0 >= round((min(xs) - 0.01) * 254000)
        assert x1 <= round((max(xs) + 0.01) * 254000)


def _is_nofill(doc: CdrDocument, fill_id: int) -> bool:
    """Ссылается ли объект на fild-запись типа 0 («нет заливки»)."""
    for chunk in doc.root.find_all('fild'):
        record = doc.resolve(chunk)
        if struct.unpack_from('<I', record, 0)[0] != fill_id:
            continue
        pos = 4
        while pos + 8 <= len(record):
            tag, length = struct.unpack_from('<II', record, pos)
            if tag == 0x514:
                return length >= 2 and struct.unpack_from('<H', record, pos + 8)[0] == 0
            pos += 8 + length
    return False


def _find_outl_record(doc: CdrDocument, outl_id: int) -> bytes:
    for chunk in doc.root.find_all('outl'):
        record = doc.resolve(chunk)
        if struct.unpack_from('<I', record, 0)[0] == outl_id:
            return record
    msg = f'нет записи обводки {outl_id}'
    raise AssertionError(msg)

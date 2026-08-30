"""
Сборка выходного CDR патчем входного контейнера.

Ничего не сдвигаем: новые тела чанков дописываются в хвост data-файлов,
старые байты остаются на местах. Переписываются только root.dat
(структура дерева) и сами data-файлы (append), плюс zip-контейнер.
"""

from __future__ import annotations

import struct
import zipfile
from typing import TYPE_CHECKING

from lbs_liner.cdr_read import (
    ARG_COORDS,
    ARG_FILL,
    ARG_OUTL,
    COORD_UNITS_PER_INCH,
    CdrDocument,
    CurveObject,
    Transform,
)
from lbs_liner.riff import CdrFormatError, Chunk, serialize

if TYPE_CHECKING:
    from pathlib import Path

    from lbs_liner.cdr_read import Point, Subpath

MM_PER_INCH = 25.4

RED_RGB = (0xFF, 0x00, 0x00)
BLUE_RGB = (0x00, 0x00, 0xFF)

_COLOR_MODEL_RGB = 5
_COLOR_PALETTE_PLAIN = 5
_GUID_TAG = 0x07

# Ниже этого определителя матрица объекта считается вырожденной.
_DEGENERATE_DET = 1e-12

# Биты типов точек: 0x40 — lineTo, 0x08 — замкнутый подпуть, 0x04 — острый узел.
PT_MOVE_OPEN = 0x04
PT_MOVE_CLOSED = 0x0C
PT_LINE = 0x44
PT_LINE_CLOSE = 0x48


def write_output(
    doc: CdrDocument,
    zone: CurveObject,
    red: list[Subpath],
    blue: list[Subpath],
    *,
    width_mm: float,
    out_path: Path,
) -> None:
    """Собрать выходной файл: два объекта-ломаные вместо старой группы."""
    donors = doc.curve_objects()
    others = [o for o in donors if o.obj_chunk is not zone.obj_chunk]
    other = others[0] if others else zone

    width_units = round(width_mm / MM_PER_INCH * COORD_UNITS_PER_INCH)
    red_outl_id, blue_outl_id = _append_outline_records(doc, width_units)

    grp = _group_of(zone.obj_chunk, doc.root)
    red_obj = _build_object(doc, zone, red, red_outl_id)
    blue_obj = _build_object(doc, other, blue, blue_outl_id, transform_from=zone)
    grp.children = [
        child
        for child in grp.children
        if not (child.is_container and child.list_type == 'obj ')
    ]
    grp.children.extend([red_obj, blue_obj])

    all_points = [pt for sub in red + blue for pt in sub.points]
    _update_bbox(doc, grp, all_points)

    _write_zip(doc, out_path)


def _group_of(obj_chunk: Chunk, root: Chunk) -> Chunk:
    """Родительская группа объекта (или его слой, если группы нет)."""
    parent = _find_parent(root, obj_chunk)
    if parent is None:
        msg = 'не нашёлся родитель объекта зоны'
        raise CdrFormatError(msg)
    return parent


def _find_parent(node: Chunk, target: Chunk) -> Chunk | None:
    for child in node.children:
        if child is target:
            return node
        if child.is_container:
            found = _find_parent(child, target)
            if found is not None:
                return found
    return None


# --- обводки ---------------------------------------------------------------


def _append_outline_records(doc: CdrDocument, width_units: int) -> tuple[int, int]:
    """Дописать в data1.dat красную и синюю обводки; вернуть их id."""
    otlt = _find_list(doc.root, 'otlt')
    outl_chunks = [ch for ch in otlt.children if ch.name == 'outl']
    if not outl_chunks:
        msg = 'в документе нет ни одной записи обводки (otlt пуст)'
        raise CdrFormatError(msg)
    records = [(ch, doc.resolve(ch)) for ch in outl_chunks]
    donor = max(records, key=lambda pair: _outl_width(pair[1]))[1]
    max_id = max(struct.unpack_from('<I', rec, 0)[0] for _, rec in records)

    red_id, blue_id = max_id + 1, max_id + 2
    red_record = _patch_outl(donor, red_id, width_units, RED_RGB)
    blue_record = _patch_outl(donor, blue_id, width_units, BLUE_RGB)

    donor_file = records[0][0].stub()[0]
    for record in (red_record, blue_record):
        stub_chunk = Chunk(name='outl')
        offset = len(doc.data[donor_file])
        doc.data[donor_file] += record
        stub_chunk.set_stub(donor_file, len(record), offset)
        otlt.children.append(stub_chunk)
    return red_id, blue_id


def _find_list(root: Chunk, list_type: str) -> Chunk:
    for chunk in _walk_containers(root):
        if chunk.list_type.strip() == list_type:
            return chunk
    msg = f'в дереве нет LIST:{list_type}'
    raise CdrFormatError(msg)


def _walk_containers(node: Chunk):  # noqa: ANN202
    for child in node.children:
        if child.is_container:
            yield child
            yield from _walk_containers(child)


def _outl_width(record: bytes) -> int:
    """Толщина из современного суб-блока (id=1) записи обводки."""
    block = _outl_block(record, wanted_id=1)
    if block is None:
        return 0
    return struct.unpack_from('<i', record, block + 6)[0]


def _outl_block(record: bytes, wanted_id: int) -> int | None:
    """Смещение начала тела суб-блока с данным id (или None)."""
    pos = 4
    while pos + 8 <= len(record):
        sub_id, sub_len = struct.unpack_from('<II', record, pos)
        if sub_id == wanted_id:
            return pos + 8
        pos += 8 + sub_len
    return None


def _patch_outl(
    donor: bytes, new_id: int, width_units: int, rgb: tuple[int, int, int]
) -> bytes:
    """
    Клон записи обводки с новым id, толщиной и сплошным RGB-цветом.

    Раскладка повторяет CDRParser::readOutl (версии ≥ 13): цвет лежит
    и в суб-блоке id=2 (палитровая форма с GUID), и в суб-блоке id=1
    (легаси-поля после толщины) — патчим оба.
    """
    record = bytearray(donor)
    struct.pack_into('<I', record, 0, new_id)

    modern = _outl_block(bytes(record), wanted_id=1)
    if modern is None:
        msg = 'запись обводки без суб-блока id=1 — незнакомая раскладка'
        raise CdrFormatError(msg)
    struct.pack_into('<i', record, modern + 6, width_units)
    # Цвет лежит после 18 байт полей линии и 46 байт масштабов.
    _patch_color(record, modern + 18 + 46, rgb)

    palette_block = _outl_block(bytes(record), wanted_id=2)
    if palette_block is not None and record[palette_block] == 0x01:
        # Тело: 0x01, u32 длина цвета (12), сам цвет, затем тег 0x07 с GUID.
        (block_len,) = struct.unpack_from('<I', donor, palette_block - 4)
        _patch_color(record, palette_block + 5, rgb)
        _zero_guid(record, palette_block + 17, palette_block + block_len)
    return bytes(record)


def _patch_color(record: bytearray, offset: int, rgb: tuple[int, int, int]) -> None:
    """Цвет по раскладке readColor: модель, палитра, 4 байта, значение."""
    r, g, b = rgb
    struct.pack_into(
        '<HHII',
        record,
        offset,
        _COLOR_MODEL_RGB,
        _COLOR_PALETTE_PLAIN,
        0,
        (r << 16) | (g << 8) | b,
    )


def _zero_guid(record: bytearray, start: int, end: int) -> None:
    """Обнулить GUID палитры (тег 0x07) после цвета, если он есть."""
    pos = start
    while pos + 5 <= min(end, len(record)):
        tag = record[pos]
        if tag == _GUID_TAG:
            (length,) = struct.unpack_from('<I', record, pos + 1)
            stop = min(pos + 5 + length, len(record))
            for i in range(pos + 5, stop):
                record[i] = 0
            return
        pos += 1


# --- объекты ---------------------------------------------------------------


def _build_object(
    doc: CdrDocument,
    donor: CurveObject,
    subpaths: list[Subpath],
    outl_id: int,
    transform_from: CurveObject | None = None,
) -> Chunk:
    """
    Новый LIST:obj: клоны служебных чанков донора + свежая геометрия.

    Точки пишутся в локальном фрейме объекта-образца (transform_from
    или сам донор), trfd клонируется от него же.
    """
    frame = transform_from or donor
    local = _to_local(subpaths, frame.transform)
    loda_payload = _rebuild_loda(frame.loda_raw, local, outl_id)

    page_file = _page_file_index(donor)
    loda_stub = Chunk(name='loda')
    offset = len(doc.data[page_file])
    doc.data[page_file] += loda_payload
    loda_stub.set_stub(page_file, len(loda_payload), offset)

    children: list[Chunk] = []
    for child in donor.obj_chunk.children:
        if child.is_container and child.list_type == 'lgob':
            lgob_children: list[Chunk] = [loda_stub]
            lgob_children.extend(
                Chunk(name=sub.name, payload=sub.payload)
                if not sub.is_container
                else _clone_container(sub, frame)
                for sub in child.children
                if sub.name != 'loda'
            )
            children.append(
                Chunk(name='LIST', list_type='lgob', children=lgob_children)
            )
        else:
            children.append(Chunk(name=child.name, payload=child.payload))
    obj = Chunk(name='LIST', list_type='obj ', children=children)

    world_points = [pt for sub in subpaths for pt in sub.points]
    _update_bbox(doc, obj, world_points)
    return obj


def _clone_container(container: Chunk, frame: CurveObject) -> Chunk:
    """Клон контейнера (trfl и т.п.): trfd берём от объекта-образца."""
    cloned = []
    for child in container.children:
        if child.name == 'trfd':
            source = frame.obj_chunk.find_all('trfd')
            payload = source[0].payload if source else child.payload
            cloned.append(Chunk(name='trfd', payload=payload))
        elif child.is_container:
            cloned.append(_clone_container(child, frame))
        else:
            cloned.append(Chunk(name=child.name, payload=child.payload))
    return Chunk(name=container.name, list_type=container.list_type, children=cloned)


def _page_file_index(donor: CurveObject) -> int:
    """Data-файл, где лежит loda донора, — туда же пишем новые лоды."""
    lodas = donor.obj_chunk.find_all('loda')
    return lodas[0].stub()[0]


def _to_local(
    subpaths: list[Subpath], transform: Transform
) -> list[tuple[list[Point], bool]]:
    """Мировые точки → локальный фрейм (обратная матрица trfd)."""
    v0, v1, x0, v3, v4, y0 = transform
    det = v0 * v4 - v1 * v3
    if abs(det) < _DEGENERATE_DET:
        msg = 'вырожденная матрица трансформации объекта-образца'
        raise CdrFormatError(msg)
    out = []
    for sub in subpaths:
        local = []
        for x, y in sub.points:
            dx, dy = x - x0, y - y0
            local.append(((v4 * dx - v1 * dy) / det, (-v3 * dx + v0 * dy) / det))
        out.append((local, sub.closed))
    return out


def _rebuild_loda(
    donor: bytes, subpaths: list[tuple[list[Point], bool]], outl_id: int
) -> bytes:
    """
    Пересобрать loda: новая геометрия, новая обводка, без заливки.

    Прочие аргументы донора переносятся байт-в-байт — Corel ждёт их
    состава, а нам их семантика не нужна.
    """
    _, num_args, start_args, start_types, chunk_type = struct.unpack_from(
        '<5I', donor, 0
    )
    offsets = struct.unpack_from(f'<{num_args}I', donor, start_args)
    types = list(reversed(struct.unpack_from(f'<{num_args}I', donor, start_types)))
    bounds = sorted([*offsets, start_args, start_types, len(donor)])

    args: list[tuple[int, bytes]] = []
    for offset, arg_type in sorted(zip(offsets, types, strict=True)):
        end = min(b for b in bounds if b > offset)
        args.append((arg_type, donor[offset:end]))

    rebuilt: list[tuple[int, bytes]] = []
    for arg_type, payload in args:
        if arg_type == ARG_FILL:
            continue
        if arg_type == ARG_COORDS:
            rebuilt.append((ARG_COORDS, _coords_blob(subpaths)))
        elif arg_type == ARG_OUTL:
            rebuilt.append((ARG_OUTL, struct.pack('<I', outl_id)))
        else:
            rebuilt.append((arg_type, payload))

    header_size = 20
    body = bytearray()
    new_offsets = []
    for _, payload in rebuilt:
        new_offsets.append(header_size + len(body))
        body += payload
        if len(body) & 3:
            body += b'\x00' * (4 - (len(body) & 3))
    args_at = header_size + len(body)
    types_at = args_at + 4 * len(rebuilt)
    total = types_at + 4 * len(rebuilt)
    out = bytearray(
        struct.pack('<5I', total, len(rebuilt), args_at, types_at, chunk_type)
    )
    out += body
    out += struct.pack(f'<{len(rebuilt)}I', *new_offsets)
    out += struct.pack(
        f'<{len(rebuilt)}I', *reversed([arg_type for arg_type, _ in rebuilt])
    )
    return bytes(out)


def _coords_blob(subpaths: list[tuple[list[Point], bool]]) -> bytes:
    """
    Аргумент координат: счётчик, точки int32, байты типов.

    Замкнутые подпути идут первыми, открытые — в конце: бит 0x08 на
    moveTo libcdr трактует как «закрыть предыдущий подпуть», Corel —
    как «этот подпуть замкнут»; такой порядок совместим с обеими
    трактовками.
    """
    ordered = sorted(subpaths, key=lambda pair: not pair[1])
    points: list[tuple[int, int]] = []
    types: list[int] = []
    for local, closed in ordered:
        pts = list(local)
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        for i, (x, y) in enumerate(pts):
            points.append(
                (round(x * COORD_UNITS_PER_INCH), round(y * COORD_UNITS_PER_INCH))
            )
            if i == 0:
                types.append(PT_MOVE_CLOSED if closed else PT_MOVE_OPEN)
            elif closed and i == len(pts) - 1:
                types.append(PT_LINE_CLOSE)
            else:
                types.append(PT_LINE)
    blob = bytearray(struct.pack('<I', len(points)))
    for x, y in points:
        blob += struct.pack('<ii', x, y)
    blob += bytes(types)
    return bytes(blob)


# --- рамки и контейнер -----------------------------------------------------


def _update_bbox(doc: CdrDocument, node: Chunk, world_points: list[Point]) -> None:
    """Пересчитать bbox/obbx узла по фактическим точкам (мировые дюймы)."""
    if not world_points:
        return
    xs = [x for x, _ in world_points]
    ys = [y for _, y in world_points]
    corners = (min(xs), max(ys), max(xs), min(ys))
    units = [round(v * COORD_UNITS_PER_INCH) for v in corners]
    for child in node.children:
        if child.name == 'bbox':
            _replace_body(doc, child, struct.pack('<4i', *units))
        elif child.name == 'obbx':
            _replace_body(doc, child, struct.pack('<8i', *units, *units))


def _replace_body(doc: CdrDocument, chunk: Chunk, body: bytes) -> None:
    file_index, _, _ = chunk.stub()
    if file_index not in doc.data:
        return
    offset = len(doc.data[file_index])
    doc.data[file_index] += body
    chunk.set_stub(file_index, len(body), offset)


def _write_zip(doc: CdrDocument, out_path: Path) -> None:
    """Записать контейнер: правленые части — заново, остальное как было."""
    replaced = {'content/root.dat': serialize(doc.root)}
    for index, name in enumerate(doc.data_names):
        replaced[f'content/data/{name}'] = bytes(doc.data[index])
    with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in doc.entries.items():
            if name == 'mimetype':
                zf.writestr(
                    zipfile.ZipInfo('mimetype'),
                    payload,
                    compress_type=zipfile.ZIP_STORED,
                )
            else:
                zf.writestr(name, replaced.get(name, payload))

"""
Сборка выходного CDR патчем входного контейнера.

Семантика аддитивная: исходное содержимое файла не меняется вовсе —
двойная линия добавляется отдельным новым слоем поверх существующих.
Новые тела чанков дописываются в хвост data-файлов (ничего не
сдвигается), переписывается только дерево root.dat и сам zip.
"""

from __future__ import annotations

import hashlib
import struct
import zipfile
from typing import TYPE_CHECKING

from lbs_liner.cdr_read import (
    ARG_COORDS,
    ARG_FILL,
    ARG_GUID,
    ARG_LAYER_NAME,
    ARG_OUTL,
    COORD_UNITS_PER_INCH,
    NO_DATA_FILE,
    CdrDocument,
    CurveObject,
    Transform,
    parse_loda_arg_list,
)
from lbs_liner.riff import CdrFormatError, Chunk, serialize

if TYPE_CHECKING:
    from pathlib import Path

    from lbs_liner.cdr_read import Point, Subpath

MM_PER_INCH = 25.4

RED_RGB = (0xFF, 0x00, 0x00)
BLUE_RGB = (0x00, 0x00, 0xFF)

DEFAULT_LAYER_NAME = 'Двойная линия'

_COLOR_MODEL_RGB = 5
_COLOR_PALETTE_PLAIN = 5
_GUID_TAG = 0x07
# Inline-стаб несёт 4-байтовое значение прямо в поле смещения.
_INLINE_SIZE = 4

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
    layer_name: str = DEFAULT_LAYER_NAME,
    remove_objects: list[CurveObject] | None = None,
) -> None:
    """
    Дописать новый слой с двумя ломаными; источники линий убрать.

    remove_objects — кривые, из которых построена двойная линия
    (залитая зона, дубли, пятна): их в выходе быть не должно. Прочее
    содержимое, включая чужие слои и не-кривые, не трогается.
    """
    width_units = round(width_mm / MM_PER_INCH * COORD_UNITS_PER_INCH)
    red_outl_id, blue_outl_id = _append_outline_records(doc, width_units)

    ids = _IdFactory(doc)
    nofill_id = _append_nofill_record(doc, ids)
    red_obj = _build_object(
        doc, zone, red, red_outl_id, ids=ids, tag='red', fill_id=nofill_id
    )
    blue_obj = _build_object(
        doc, zone, blue, blue_outl_id, ids=ids, tag='blue', fill_id=nofill_id
    )

    all_points = [pt for sub in red + blue for pt in sub.points]
    group = _build_group(doc, zone, [red_obj, blue_obj], all_points, ids)
    layer = _build_layer(doc, zone, group, layer_name, ids)

    zone_layer = zone.layer_chunk
    if zone_layer is None:
        msg = 'объект зоны не привязан к слою'
        raise CdrFormatError(msg)
    gobj = _find_parent(doc.root, zone_layer)
    if gobj is None:
        msg = 'не нашёлся родитель слоя зоны'
        raise CdrFormatError(msg)
    gobj.children.insert(gobj.children.index(zone_layer) + 1, layer)

    for consumed in remove_objects or []:
        _remove_object(doc.root, consumed.obj_chunk)
    _prune_empty_groups(zone_layer)

    _write_zip(doc, out_path)


def _remove_object(root: Chunk, obj_chunk: Chunk) -> None:
    """Убрать LIST:obj из его родителя (если он ещё в дереве)."""
    parent = _find_parent(root, obj_chunk)
    if parent is not None:
        parent.children.remove(obj_chunk)


def _prune_empty_groups(node: Chunk) -> None:
    """Удалить группы, в которых не осталось ни объектов, ни подгрупп."""
    for child in list(node.children):
        if child.is_container:
            _prune_empty_groups(child)
    node.children = [
        child
        for child in node.children
        if not (
            child.is_container
            and child.list_type.strip() == 'grp'
            and not any(
                sub.is_container and sub.list_type.strip() in ('obj', 'grp')
                for sub in child.children
            )
        )
    ]


class _IdFactory:
    """Новые уникальные идентификаторы: spid/GUID хешем, usdn — max+1."""

    def __init__(self, doc: CdrDocument) -> None:
        self._doc = doc
        self._counter = 0
        usdns = [
            value
            for chunk in doc.root.find_all('usdn')
            if (value := _inline_value(chunk)) is not None
        ]
        self._next_usdn = max(usdns, default=0) + 1

    def sixteen_bytes(self, tag: str) -> bytes:
        """Детерминированные 16 байт для spid или GUID слоя/группы."""
        self._counter += 1
        seed = f'lbs-liner:{tag}:{self._counter}'
        return hashlib.sha256(seed.encode()).digest()[:16]

    def usdn(self) -> int:
        """Очередной пользовательский номер объекта."""
        value = self._next_usdn
        self._next_usdn += 1
        return value


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
    """Дописать в data-файл красную и синюю обводки; вернуть их id."""
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


def _append_nofill_record(doc: CdrDocument, ids: _IdFactory) -> int:
    """
    Дописать fild-запись «нет заливки»; вернуть её id.

    Раскладка снята с файла, сохранённого самим CorelDRAW 26: GUID-блок
    (тег 0x960) и блок типа заливки (тег 0x514) длиной 2 с типом 0.
    Просто опустить аргумент заливки в лоде нельзя — Corel тогда берёт
    заливку из стиля и красит линию.
    """
    filt = _find_list(doc.root, 'filt')
    fild_chunks = filt.find_all('fild')
    if not fild_chunks:
        msg = 'в документе нет таблицы заливок (filt пуст)'
        raise CdrFormatError(msg)
    records = [(ch, doc.resolve(ch)) for ch in fild_chunks]
    new_id = max(struct.unpack_from('<I', rec, 0)[0] for _, rec in records) + 1

    record = bytearray()
    record += struct.pack('<I', new_id)
    record += struct.pack('<II', 0x960, 16) + ids.sixteen_bytes('fild-guid')
    record += struct.pack('<IIH', 0x514, 2, 0)
    record += b'\0' * 10

    donor_file = records[0][0].stub()[0]
    stub_chunk = Chunk(name='fild')
    stub_chunk.set_stub(donor_file, len(record), len(doc.data[donor_file]))
    doc.data[donor_file] += bytes(record)
    filt.children.append(Chunk(name='LIST', list_type='filc', children=[stub_chunk]))
    return new_id


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


# --- идентификаторы и клонирование чанков ----------------------------------


def _inline_value(chunk: Chunk) -> int | None:
    """Значение inline-стаба (файл 0xFFFFFFFF, тело упаковано в offset)."""
    try:
        file_index, size, offset = chunk.stub()
    except CdrFormatError:
        return None
    if file_index == NO_DATA_FILE and size == _INLINE_SIZE:
        return offset & 0xFFFFFFFF
    return None


def _make_inline(value: int) -> bytes:
    """Собрать inline-стаб с 4-байтовым значением."""
    return struct.pack('<IIQ', NO_DATA_FILE, 4, value)


def _clone_id_chunk(doc: CdrDocument, donor: Chunk, new_body: bytes) -> Chunk:
    """
    Клон 16-байтового id-чанка (spid) с новым содержимым.

    У реальных файлов тело вынесено по стабу — тогда новое тело
    дописывается в тот же data-файл; иначе кладём байты прямо в payload.
    """
    chunk = Chunk(name=donor.name)
    try:
        file_index, size, _ = donor.stub()
    except CdrFormatError:
        file_index, size = None, 0
    if file_index is not None and file_index in doc.data and size == len(new_body):
        offset = len(doc.data[file_index])
        doc.data[file_index] += new_body
        chunk.set_stub(file_index, len(new_body), offset)
    else:
        chunk.payload = new_body
    return chunk


def _append_loda(doc: CdrDocument, template: Chunk, payload: bytes) -> Chunk:
    """Новое тело loda в data-файл шаблонного стаба; вернуть новый стаб."""
    file_index = template.stub()[0]
    if file_index not in doc.data:
        msg = 'лода-шаблон указывает в несуществующий data-файл'
        raise CdrFormatError(msg)
    chunk = Chunk(name='loda')
    offset = len(doc.data[file_index])
    doc.data[file_index] += payload
    chunk.set_stub(file_index, len(payload), offset)
    return chunk


def _rebuild_loda(donor: bytes, overrides: dict[int, bytes | None]) -> bytes:
    """
    Пересобрать loda, заменив или убрав отдельные аргументы.

    Не перечисленные в overrides аргументы переносятся байт-в-байт —
    Corel ждёт их состава, а нам их семантика не нужна.
    """
    chunk_type = struct.unpack_from('<5I', donor, 0)[4]
    rebuilt: list[tuple[int, bytes]] = []
    for arg_type, payload in parse_loda_arg_list(donor):
        if arg_type in overrides:
            replacement = overrides[arg_type]
            if replacement is not None:
                rebuilt.append((arg_type, replacement))
        else:
            rebuilt.append((arg_type, payload))

    return _serialize_loda(rebuilt, chunk_type)


def _serialize_loda(args: list[tuple[int, bytes]], chunk_type: int) -> bytes:
    """
    Собрать loda в родной раскладке Corel.

    Заголовок, таблица смещений, сентинел (полная длина — по нему Corel
    считает длину последнего аргумента), таблица типов в обратном
    порядке, затем тела аргументов подряд без выравнивания.
    """
    num = len(args)
    args_at = 20
    types_at = args_at + 4 * num + 4  # +4 — сентинел после таблицы смещений
    data_at = types_at + 4 * num
    offsets = []
    cursor = data_at
    for _, payload in args:
        offsets.append(cursor)
        cursor += len(payload)
    total = cursor
    out = bytearray(struct.pack('<5I', total, num, args_at, types_at, chunk_type))
    out += struct.pack(f'<{num}I', *offsets)
    out += struct.pack('<I', total)
    out += struct.pack(f'<{num}I', *reversed([arg_type for arg_type, _ in args]))
    for _, payload in args:
        out += payload
    return bytes(out)


# --- объекты, группа, слой -------------------------------------------------


def _build_object(
    doc: CdrDocument,
    donor: CurveObject,
    subpaths: list[Subpath],
    outl_id: int,
    *,
    ids: _IdFactory,
    tag: str,
    fill_id: int,
) -> Chunk:
    """
    Новый LIST:obj по образцу объекта зоны.

    Служебные чанки клонируются от донора (spid/usdn получают новые
    значения), геометрия и обводка — свои, заливки нет. Точки пишутся
    в локальном фрейме донора, trfd делится с ним.
    """
    donor_lodas = donor.obj_chunk.find_all('loda')
    loda_payload = _rebuild_loda(
        donor.loda_raw,
        {
            ARG_COORDS: _coords_blob(_to_local(subpaths, donor.transform)),
            ARG_FILL: struct.pack('<I', fill_id),
            ARG_OUTL: struct.pack('<I', outl_id),
        },
    )
    loda_stub = _append_loda(doc, donor_lodas[0], loda_payload)

    children: list[Chunk] = []
    for child in donor.obj_chunk.children:
        if child.is_container and child.list_type == 'lgob':
            lgob_children: list[Chunk] = [loda_stub]
            lgob_children.extend(
                _clone_subtree(sub) for sub in child.children if sub.name != 'loda'
            )
            children.append(
                Chunk(name='LIST', list_type='lgob', children=lgob_children)
            )
        elif child.name == 'spid':
            children.append(
                _clone_id_chunk(doc, child, ids.sixteen_bytes(f'spid-{tag}'))
            )
        elif child.name == 'usdn':
            children.append(Chunk(name='usdn', payload=_make_inline(ids.usdn())))
        else:
            children.append(_clone_subtree(child))
    obj = Chunk(name='LIST', list_type='obj ', children=children)

    world_points = [pt for sub in subpaths for pt in sub.points]
    _update_bbox(doc, obj, world_points)
    return obj


def _build_group(
    doc: CdrDocument,
    zone: CurveObject,
    objects: list[Chunk],
    world_points: list[Point],
    ids: _IdFactory,
) -> Chunk:
    """Новая группа по образцу группы зоны, с новыми id и своими объектами."""
    donor_group = _find_parent(doc.root, zone.obj_chunk)
    if donor_group is None or donor_group.list_type.strip() != 'grp':
        # Зона лежит прямо в слое — обойдёмся без группы.
        return objects[0] if len(objects) == 1 else _plain_group(objects)
    children: list[Chunk] = []
    for child in donor_group.children:
        if child.is_container and child.list_type == 'obj ':
            continue
        if child.is_container and child.list_type == 'lgob':
            children.append(_rebuild_lgob(doc, child, ids, 'group'))
        elif child.name == 'spid':
            children.append(
                _clone_id_chunk(doc, child, ids.sixteen_bytes('spid-group'))
            )
        elif child.name == 'usdn':
            children.append(Chunk(name='usdn', payload=_make_inline(ids.usdn())))
        else:
            children.append(_clone_subtree(child))
    children.extend(objects)
    group = Chunk(name='LIST', list_type=donor_group.list_type, children=children)
    _update_bbox(doc, group, world_points)
    return group


def _plain_group(objects: list[Chunk]) -> Chunk:
    return Chunk(name='LIST', list_type='grp ', children=list(objects))


def _build_layer(
    doc: CdrDocument,
    zone: CurveObject,
    content: Chunk,
    layer_name: str,
    ids: _IdFactory,
) -> Chunk:
    """Новый слой по образцу слоя зоны: своё имя, свои id, наша группа."""
    donor_layer = zone.layer_chunk
    if donor_layer is None:
        msg = 'объект зоны не привязан к слою'
        raise CdrFormatError(msg)
    name_bytes = layer_name.encode('utf-16-le') + b'\x00\x00'
    children: list[Chunk] = []
    for child in donor_layer.children:
        if child.is_container and child.list_type == 'lgob':
            children.append(
                _rebuild_lgob(doc, child, ids, 'layer', {ARG_LAYER_NAME: name_bytes})
            )
        elif child.is_container:
            continue  # содержимое слоя-донора (группы, объекты) не тащим
        elif child.name == 'spid':
            children.append(
                _clone_id_chunk(doc, child, ids.sixteen_bytes('spid-layer'))
            )
        else:
            children.append(Chunk(name=child.name, payload=child.payload))
    children.append(content)
    return Chunk(name='LIST', list_type=donor_layer.list_type, children=children)


def _rebuild_lgob(
    doc: CdrDocument,
    donor_lgob: Chunk,
    ids: _IdFactory,
    tag: str,
    extra_overrides: dict[int, bytes | None] | None = None,
) -> Chunk:
    """Клон LIST:lgob с пересобранной loda (новый GUID + правки)."""
    children: list[Chunk] = []
    for child in donor_lgob.children:
        if child.name == 'loda':
            overrides: dict[int, bytes | None] = {
                ARG_GUID: ids.sixteen_bytes(f'guid-{tag}')
            }
            if extra_overrides:
                overrides.update(extra_overrides)
            donor_body = doc.resolve(child)
            args = dict(parse_loda_arg_list(donor_body))
            if ARG_GUID not in args:
                overrides.pop(ARG_GUID)
            payload = _rebuild_loda(donor_body, overrides)
            children.append(_append_loda(doc, child, payload))
        else:
            children.append(_clone_subtree(child))
    return Chunk(name='LIST', list_type='lgob', children=children)


def _clone_subtree(chunk: Chunk) -> Chunk:
    """Глубокая копия чанка; стабы остаются указывать на прежние тела."""
    if chunk.is_container:
        return Chunk(
            name=chunk.name,
            list_type=chunk.list_type,
            children=[_clone_subtree(child) for child in chunk.children],
        )
    return Chunk(name=chunk.name, payload=chunk.payload)


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


def _repack_data_files(doc: CdrDocument) -> None:
    """
    Пересобрать data-файлы: тела чанков строго в порядке обхода дерева.

    В родных файлах смещения тел монотонно растут в порядке дерева —
    Corel, судя по поведению, читает data-файлы потоком, а не по
    смещениям из стабов. Поэтому вклинивать новые тела в хвост нельзя:
    после правок дерева весь пул собирается заново, стабы обновляются.
    Тела, на которые ссылаются несколько стабов, дублируются — как в
    родных файлах.
    """
    new_data: dict[int, bytearray] = {index: bytearray() for index in doc.data}

    def walk(node: Chunk) -> None:
        for child in node.children:
            if child.is_container:
                walk(child)
                continue
            try:
                file_index, size, offset = child.stub()
            except CdrFormatError:
                continue
            if file_index == NO_DATA_FILE or file_index not in doc.data:
                continue
            body = bytes(doc.data[file_index][offset : offset + size])
            child.set_stub(file_index, size, len(new_data[file_index]))
            new_data[file_index] += body

    walk(doc.root)
    doc.data = new_data


def _write_zip(doc: CdrDocument, out_path: Path) -> None:
    """Записать контейнер: правленые части — заново, остальное как было."""
    _repack_data_files(doc)
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

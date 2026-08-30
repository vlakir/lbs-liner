"""
Чтение CDR-контейнера: объекты-кривые, их геометрия и стили.

Раскладка чанков восстановлена по исходникам libcdr (CDRParser.cpp,
CommonParser.cpp) и проверена на реальном файле CorelDRAW 17–22.
Координаты: 1 единица = 1/254000 дюйма; здесь всё приводится к дюймам.
"""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lbs_liner.riff import CdrFormatError, Chunk, parse

if TYPE_CHECKING:
    from pathlib import Path

COORD_UNITS_PER_INCH = 254000.0
NO_DATA_FILE = 0xFFFFFFFF

# Биты типа точки (CommonParser::processPath).
PT_CLOSED = 0x08
PT_MASK = 0xC0
PT_MOVE = 0x00
PT_LINE = 0x40
PT_CTRL = 0xC0
PT_CURVE_END = 0x80

CHUNK_TYPE_CURVE = 0x03
ARG_COORDS = 0x1E
ARG_FILL = 0x14
ARG_OUTL = 0x0A

# Заголовок loda: 5 полей u32.
_LODA_HEADER = 20
# Вид аргумента trfd, несущего матрицу.
_TRFD_MATRIX = 0x08
# Минимум точек: 2 — и для подпути, и для пары контрольных точек безье.
_PAIR = 2

Transform = tuple[float, float, float, float, float, float]
Point = tuple[float, float]


@dataclass
class Subpath:
    """Один подпуть кривой: уже сглаженная ломаная в мировых координатах."""

    points: list[Point]
    closed: bool


@dataclass
class CurveObject:
    """Объект-кривая на странице вместе со ссылками на его чанки."""

    obj_chunk: Chunk
    loda_raw: bytes
    points: list[Point] = field(default_factory=list)
    types: list[int] = field(default_factory=list)
    transform: Transform = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    fill_id: int | None = None
    outl_id: int | None = None

    def world_subpaths(self, tolerance: float = 0.002) -> list[Subpath]:
        """Подпути в мировых координатах, безье сглажены до ломаных."""
        v0, v1, x0, v3, v4, y0 = self.transform
        world = [(v0 * x + v1 * y + x0, v3 * x + v4 * y + y0) for x, y in self.points]
        return _split_subpaths(world, self.types, tolerance)


@dataclass
class CdrDocument:
    """Разобранный контейнер: дерево root.dat + пулы данных."""

    entries: dict[str, bytes]
    root: Chunk
    data_names: list[str]
    data: dict[int, bytearray]

    @classmethod
    def load(cls, path: Path) -> CdrDocument:
        """Открыть .cdr (zip) и разобрать структуру."""
        try:
            with zipfile.ZipFile(path) as zf:
                entries = {info.filename: zf.read(info) for info in zf.infolist()}
        except zipfile.BadZipFile as exc:
            msg = f'{path}: не zip-контейнер — старые (до X7) CDR не поддерживаются'
            raise CdrFormatError(msg) from exc
        required = ('content/root.dat', 'content/dataFileList.dat')
        if any(name not in entries for name in required):
            msg = f'{path}: нет content/root.dat — это не CDR X7+'
            raise CdrFormatError(msg)
        root = parse(entries['content/root.dat'])
        data_names = entries['content/dataFileList.dat'].decode('ascii').split()
        data = {
            index: bytearray(entries[f'content/data/{name}'])
            for index, name in enumerate(data_names)
        }
        return cls(entries=entries, root=root, data_names=data_names, data=data)

    def resolve(self, chunk: Chunk) -> bytes:
        """Тело листового чанка по его стабу."""
        file_index, size, offset = chunk.stub()
        if file_index == NO_DATA_FILE:
            return b''
        if file_index not in self.data:
            msg = f'чанк {chunk.name}: стаб глядит в несуществующий файл {file_index}'
            raise CdrFormatError(msg)
        return bytes(self.data[file_index][offset : offset + size])

    def curve_objects(self) -> list[CurveObject]:
        """Все объекты-кривые страниц в порядке рисования (низ → верх)."""
        return self._collect_objects(self.root)

    def _collect_objects(self, node: Chunk) -> list[CurveObject]:
        found: list[CurveObject] = []
        for child in node.children:
            if child.is_container and child.list_type == 'obj ':
                curve = self._parse_object(child)
                if curve is not None:
                    found.append(curve)
            elif child.is_container:
                found.extend(self._collect_objects(child))
        return found

    def _parse_object(self, obj_chunk: Chunk) -> CurveObject | None:
        lodas = obj_chunk.find_all('loda')
        if not lodas:
            return None
        loda_raw = self.resolve(lodas[0])
        curve = _parse_loda(loda_raw, obj_chunk)
        if curve is None:
            return None
        trfds = obj_chunk.find_all('trfd')
        if trfds:
            transform = _parse_trfd(self.resolve(trfds[0]))
            if transform is not None:
                curve.transform = transform
        return curve


def _parse_loda(body: bytes, obj_chunk: Chunk) -> CurveObject | None:
    """Разбор чанка loda: тип, аргументы, координаты (см. readLoda)."""
    if len(body) < _LODA_HEADER:
        return None
    _, num_args, start_args, start_types, chunk_type = struct.unpack_from(
        '<5I', body, 0
    )
    if chunk_type != CHUNK_TYPE_CURVE:
        return None
    arg_offsets = struct.unpack_from(f'<{num_args}I', body, start_args)
    arg_types = list(reversed(struct.unpack_from(f'<{num_args}I', body, start_types)))
    curve = CurveObject(obj_chunk=obj_chunk, loda_raw=body)
    for offset, arg_type in zip(arg_offsets, arg_types, strict=True):
        if arg_type == ARG_COORDS:
            (npts,) = struct.unpack_from('<H', body, offset)
            base = offset + 4
            for i in range(npts):
                x, y = struct.unpack_from('<ii', body, base + 8 * i)
                curve.points.append(
                    (x / COORD_UNITS_PER_INCH, y / COORD_UNITS_PER_INCH)
                )
            type_base = base + 8 * npts
            curve.types = list(body[type_base : type_base + npts])
        elif arg_type == ARG_FILL:
            (curve.fill_id,) = struct.unpack_from('<I', body, offset)
        elif arg_type == ARG_OUTL:
            (curve.outl_id,) = struct.unpack_from('<I', body, offset)
    if not curve.points:
        return None
    return curve


def _parse_trfd(body: bytes) -> Transform | None:
    """Матрица объекта из чанка trfd (см. readTrfd, версия ≥ 13)."""
    _, num_args, start_args, _ = struct.unpack_from('<4I', body, 0)
    arg_offsets = struct.unpack_from(f'<{num_args}I', body, start_args)
    for offset in arg_offsets:
        pos = offset + 8
        (kind,) = struct.unpack_from('<H', body, pos)
        if kind == _TRFD_MATRIX:
            v0, v1, x0, v3, v4, y0 = struct.unpack_from('<6d', body, pos + 8)
            scale = COORD_UNITS_PER_INCH
            return (v0, v1, x0 / scale, v3, v4, y0 / scale)
    return None


def _split_subpaths(
    points: list[Point], types: list[int], tolerance: float
) -> list[Subpath]:
    """Пройти точки по семантике processPath, разложив на ломаные подпути."""
    subpaths: list[Subpath] = []
    current: list[Point] = []
    ctrl: list[Point] = []
    closed = False

    def flush() -> None:
        nonlocal current, closed
        if len(current) >= _PAIR:
            subpaths.append(Subpath(points=current, closed=closed))
        current = []
        closed = False

    for point, ptype in zip(points, types, strict=True):
        kind = ptype & PT_MASK
        if kind == PT_MOVE:
            flush()
            current = [point]
            ctrl = []
        elif kind == PT_LINE:
            current.append(point)
            ctrl = []
        elif kind == PT_CTRL:
            ctrl.append(point)
        else:  # PT_CURVE_END
            if len(ctrl) >= _PAIR and current:
                current.extend(
                    _flatten_cubic(current[-1], ctrl[0], ctrl[1], point, tolerance)
                )
            current.append(point)
            ctrl = []
        if ptype & PT_CLOSED:
            closed = True
    flush()
    return subpaths


def _flatten_cubic(
    p0: Point, p1: Point, p2: Point, p3: Point, tolerance: float
) -> list[Point]:
    """
    Промежуточные точки кубической кривой Безье (без концов).

    Число шагов подбирается по грубой оценке отклонения контрольных
    точек от хорды — на картографических масштабах этого достаточно.
    """

    def chord_dev(axis: int, ctrl: Point, share: float) -> float:
        return abs((ctrl[axis] - p0[axis]) - share * (p3[axis] - p0[axis]))

    deviation = max(
        chord_dev(0, p1, 1 / 3) + chord_dev(1, p1, 1 / 3),
        chord_dev(0, p2, 2 / 3) + chord_dev(1, p2, 2 / 3),
    )
    steps = max(2, min(64, int((deviation / max(tolerance, 1e-6)) ** 0.5) + 2))

    def cubic(a: float, b: float, c: float, d: float, t: float) -> float:
        mt = 1 - t
        return mt**3 * a + 3 * mt**2 * t * b + 3 * mt * t**2 * c + t**3 * d

    return [
        (
            cubic(p0[0], p1[0], p2[0], p3[0], i / steps),
            cubic(p0[1], p1[1], p2[1], p3[1], i / steps),
        )
        for i in range(1, steps)
    ]

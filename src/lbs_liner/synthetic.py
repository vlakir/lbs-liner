"""
Генератор синтетического CDR, повторяющего структуру реального файла.

Геометрия придумана: «лесенка» границы, замкнутая длинными рёбрами прямого
угла, дыра-карман внутри зоны, отдельное пятно снаружи и черновик-дубль
трассы. Никаких реальных данных: из настоящего файла взяты
только байты записи стиля обводки (цвет и толщина, без геометрии).

Используется тестами и смоук-проверкой собранного исполняемого файла.
"""

from __future__ import annotations

import struct
import zipfile
from typing import TYPE_CHECKING

from lbs_liner.cdr_read import COORD_UNITS_PER_INCH
from lbs_liner.riff import Chunk, serialize

if TYPE_CHECKING:
    from pathlib import Path

# Реальная запись обводки CorelDRAW 17–22 (PANTONE-красный, 0.2 мм) —
# донор стиля для клонирования.
OUTL_RECORD = bytes.fromhex(
    '030000000b0000001000000003a9dcb0ea76fc4a86cdbbc9ee7b90b503000000'
    '04000000404b4c00020000002b000000010c000000030005000000000000ffff'
    '000710000000cb19cdcc75465e4a8bdad0bbbaab8af000000000000100000082'
    '000000020000000000d0070000640000000000000000000000f03f0000000000'
    '00000000000000000000000000000000000000000000000000f03f0000000000'
    '000000030005000000000000ffff000000243a0000000040a5ae023c00000000'
    '0000000000000000000000000000000000000000000000000000000000000000'
    '00000000000000000000000000'
)

Ring = list[tuple[float, float]]


def staircase() -> Ring:
    """«Лесенка» из коротких рёбер по 0.1 дюйма от (0,0) к (1.5,1.5)."""
    points = [(0.0, 0.0)]
    x = y = 0.0
    for _ in range(15):
        x += 0.1
        points.append((x, y))
        y += 0.1
        points.append((x, y))
    return points


def zone_ring() -> Ring:
    """Лесенка, замкнутая длинными рёбрами прямого угла справа."""
    ring = staircase()
    ring += [(10.0, 3.0), (10.0, -5.0), (0.0, -5.0)]
    ring.append(ring[0])
    return ring


def draft_ring() -> Ring:
    """Черновик: та же лесенка, замкнутая короче (меньшая рамка)."""
    ring = [(px + 0.01, py) for px, py in staircase()]
    ring += [(8.0, 3.0), (8.0, -4.0), (0.01, -4.0)]
    ring.append(ring[0])
    return ring


def square(cx: float, cy: float, half: float) -> Ring:
    """Квадратное колечко вокруг точки (замкнутое, с дублем вершины)."""
    ring = [
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    ]
    ring.append(ring[0])
    return ring


def coords_blob(rings: list[Ring]) -> bytes:
    """Аргумент координат в формате Corel: все кольца замкнуты."""
    points: list[tuple[int, int]] = []
    types: list[int] = []
    for ring in rings:
        for i, (x, y) in enumerate(ring):
            points.append(
                (round(x * COORD_UNITS_PER_INCH), round(y * COORD_UNITS_PER_INCH))
            )
            if i == 0:
                types.append(0x0C)
            elif i == len(ring) - 1:
                types.append(0x48)
            else:
                types.append(0x44)
    blob = bytearray(struct.pack('<I', len(points)))
    for x, y in points:
        blob += struct.pack('<ii', x, y)
    blob += bytes(types)
    return bytes(blob)


def build_loda(rings: list[Ring], outl_id: int, fill_id: int) -> bytes:
    """Чанк loda типа «кривая» с координатами, заливкой и обводкой."""
    args = [
        (0x1E, coords_blob(rings)),
        (0x14, struct.pack('<I', fill_id)),
        (0x0A, struct.pack('<I', outl_id)),
        (0x2EE0, b'\xaa\xbb\xcc\xdd'),
    ]
    return _serialize_loda_args(args, chunk_type=0x03)


def build_layer_loda(name: str) -> bytes:
    """Чанк loda слоя: GUID, служебные аргументы и имя (UTF-16LE)."""
    args = [
        (0x9C72, bytes(range(16))),
        (0x2EE0, b'\x00' * 4),
        (0x03E8, name.encode('utf-16-le') + b'\x00\x00'),
    ]
    return _serialize_loda_args(args, chunk_type=0x00)


def _serialize_loda_args(args: list[tuple[int, bytes]], chunk_type: int) -> bytes:
    body = bytearray()
    offsets = []
    for _, payload in args:
        offsets.append(20 + len(body))
        body += payload
        if len(body) & 3:
            body += b'\x00' * (4 - (len(body) & 3))
    args_at = 20 + len(body)
    types_at = args_at + 4 * len(args)
    total = types_at + 4 * len(args)
    out = bytearray(struct.pack('<5I', total, len(args), args_at, types_at, chunk_type))
    out += body
    out += struct.pack(f'<{len(args)}I', *offsets)
    out += struct.pack(f'<{len(args)}I', *reversed([t for t, _ in args]))
    return bytes(out)


def build_trfd(dx: float, dy: float) -> bytes:
    """Чанк trfd с матрицей сдвига."""
    arg = bytearray(b'\x00' * 8)
    arg += struct.pack('<H', 0x08)
    arg += b'\x00' * 6
    arg += struct.pack(
        '<6d', 1.0, 0.0, dx * COORD_UNITS_PER_INCH, 0.0, 1.0, dy * COORD_UNITS_PER_INCH
    )
    header = struct.pack('<4I', 16 + 4 + len(arg), 1, 16, 0)
    return header + struct.pack('<I', 20) + bytes(arg)


def build_sample_cdr(path: Path) -> Path:
    """Собрать синтетический .cdr на диске и вернуть путь."""
    page1 = bytearray()
    data1 = bytearray(OUTL_RECORD)

    def push(payload: bytes) -> tuple[int, int, int]:
        offset = len(page1)
        page1.extend(payload)
        return (1, len(payload), offset)

    def stub_chunk(name: str, ref: tuple[int, int, int]) -> Chunk:
        chunk = Chunk(name=name)
        chunk.set_stub(*ref)
        return chunk

    def build_obj(rings: list[Ring], spid: bytes) -> Chunk:
        loda_ref = push(build_loda(rings, outl_id=3, fill_id=1))
        trfd_ref = push(build_trfd(0.5, 0.25))
        bbox_ref = push(struct.pack('<4i', 0, 0, 0, 0))
        obbx_ref = push(struct.pack('<8i', *([0] * 8)))
        lgob = Chunk(
            name='LIST',
            list_type='lgob',
            children=[
                stub_chunk('loda', loda_ref),
                Chunk(
                    name='LIST',
                    list_type='trfl',
                    children=[stub_chunk('trfd', trfd_ref)],
                ),
            ],
        )
        return Chunk(
            name='LIST',
            list_type='obj ',
            children=[
                Chunk(name='spid', payload=spid),
                stub_chunk('bbox', bbox_ref),
                stub_chunk('obbx', obbx_ref),
                lgob,
            ],
        )

    def build_layr(name: str, spid: bytes, content: list[Chunk]) -> Chunk:
        loda_ref = push(build_layer_loda(name))
        flgs = Chunk(
            name='flgs', payload=struct.pack('<IIQ', 0xFFFFFFFF, 4, 0x98000000)
        )
        lgob = Chunk(
            name='LIST', list_type='lgob', children=[stub_chunk('loda', loda_ref)]
        )
        return Chunk(
            name='LIST',
            list_type='layr',
            children=[flgs, Chunk(name='spid', payload=spid), lgob, *content],
        )

    outl_stub = Chunk(name='outl')
    outl_stub.set_stub(0, len(OUTL_RECORD), 0)

    objects = [
        build_obj([square(-2.0, 1.0, 0.25)], b'\x01' * 16),  # пятно вне зоны
        build_obj([draft_ring()], b'\x02' * 16),  # черновик-дубль
        build_obj([zone_ring(), square(6.0, 0.0, 0.25)], b'\x03' * 16),  # зона с дырой
    ]
    grp = Chunk(
        name='LIST',
        list_type='grp ',
        children=[Chunk(name='spid', payload=b'\x04' * 16), *objects],
    )
    zone_layer = build_layr('Заливка', b'\x05' * 16, [grp])
    # Посторонний слой: одна чужая кривая, которую трогать нельзя.
    foreign_obj = build_obj([square(20.0, 20.0, 3.0)], b'\x06' * 16)
    foreign_layer = build_layr('Топооснова', b'\x07' * 16, [foreign_obj])
    root = Chunk(
        name='RIFF',
        list_type='CDRT',
        children=[
            Chunk(
                name='LIST',
                list_type='doc ',
                children=[Chunk(name='LIST', list_type='otlt', children=[outl_stub])],
            ),
            Chunk(
                name='LIST',
                list_type='page',
                children=[
                    Chunk(
                        name='LIST',
                        list_type='gobj',
                        children=[foreign_layer, zone_layer],
                    )
                ],
            ),
        ],
    )

    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            zipfile.ZipInfo('mimetype'),
            'application/x-vnd.corel.zcf.draw.document+zip',
            compress_type=zipfile.ZIP_STORED,
        )
        zf.writestr(zipfile.ZipInfo('content/root.dat'), serialize(root))
        zf.writestr(zipfile.ZipInfo('content/dataFileList.dat'), 'data1.dat\npage1.dat')
        zf.writestr(zipfile.ZipInfo('content/data/data1.dat'), bytes(data1))
        zf.writestr(zipfile.ZipInfo('content/data/page1.dat'), bytes(page1))
    return path

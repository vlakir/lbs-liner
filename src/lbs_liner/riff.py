"""
Дерево RIFF-чанков контейнера CDR (zip-формат CorelDRAW X7+).

В root.dat лежит дерево RIFF/LIST, все листовые чанки — 16-байтовые
ссылки («стабы») на тела, вынесенные в файлы content/data/*.dat:
``<индекс файла:u32> <размер:u32> <смещение:u64>``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

STUB_SIZE = 16
_HEADER = struct.Struct('<4sI')
_STUB = struct.Struct('<IIQ')


class CdrFormatError(ValueError):
    """Входной файл не похож на поддерживаемый CDR."""


@dataclass
class Chunk:
    """Узел дерева RIFF: либо контейнер (RIFF/LIST), либо лист со стабом."""

    name: str
    list_type: str = ''
    payload: bytes = b''
    children: list[Chunk] = field(default_factory=list)

    @property
    def is_container(self) -> bool:
        """Контейнерные чанки несут детей, листовые — payload."""
        return self.name in ('RIFF', 'LIST')

    def find_all(self, name: str) -> list[Chunk]:
        """Все потомки (в глубину) с данным именем."""
        found = []
        for child in self.children:
            if child.name == name:
                found.append(child)
            found.extend(child.find_all(name))
        return found

    def stub(self) -> tuple[int, int, int]:
        """Разобрать листовой payload как стаб: (файл, размер, смещение)."""
        if len(self.payload) != STUB_SIZE:
            msg = f'чанк {self.name}: ожидался стаб 16 байт, а тут {len(self.payload)}'
            raise CdrFormatError(msg)
        file_index, size, offset = _STUB.unpack(self.payload)
        return file_index, size, offset

    def set_stub(self, file_index: int, size: int, offset: int) -> None:
        """Записать в листовой payload ссылку на вынесенное тело."""
        self.payload = _STUB.pack(file_index, size, offset)


def parse(data: bytes) -> Chunk:
    """Разобрать root.dat в дерево; корень — RIFF:CDRT."""
    if data[:4] != b'RIFF':
        msg = 'root.dat не начинается с RIFF — это не CDR X7+'
        raise CdrFormatError(msg)
    root_children, _ = _parse_children(data, 12, len(data))
    return Chunk(
        name='RIFF', list_type=data[8:12].decode('ascii'), children=root_children
    )


def _parse_children(data: bytes, start: int, end: int) -> tuple[list[Chunk], int]:
    children = []
    pos = start
    while pos + 8 <= end:
        raw_name, size = _HEADER.unpack_from(data, pos)
        name = raw_name.decode('ascii', 'replace')
        body = pos + 8
        if name in ('RIFF', 'LIST'):
            list_type = data[body : body + 4].decode('ascii', 'replace')
            sub, _ = _parse_children(data, body + 4, min(body + size, end))
            children.append(Chunk(name=name, list_type=list_type, children=sub))
        else:
            children.append(Chunk(name=name, payload=data[body : body + size]))
        pos = body + size + (size & 1)
    return children, pos


def serialize(root: Chunk) -> bytes:
    """Собрать дерево обратно в байты с пересчётом размеров."""
    body = _serialize_children(root.children)
    payload = root.list_type.encode('ascii') + body
    return _HEADER.pack(b'RIFF', len(payload)) + payload


def _serialize_children(children: list[Chunk]) -> bytes:
    out = bytearray()
    for chunk in children:
        if chunk.is_container:
            body = chunk.list_type.encode('ascii') + _serialize_children(chunk.children)
        else:
            body = chunk.payload
        out += _HEADER.pack(chunk.name.encode('ascii'), len(body))
        out += body
        if len(body) & 1:
            out += b'\x00'
    return bytes(out)

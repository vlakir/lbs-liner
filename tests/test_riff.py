"""Тесты дерева RIFF: разбор, сериализация, стабы."""

from __future__ import annotations

import struct

import pytest

from lbs_liner.riff import Chunk, CdrFormatError, parse, serialize


def _leaf(name: str, payload: bytes) -> Chunk:
    return Chunk(name=name, payload=payload)


def test_roundtrip() -> None:
    """parse(serialize(дерево)) возвращает то же дерево."""
    tree = Chunk(
        name='RIFF',
        list_type='CDRT',
        children=[
            _leaf('fver', b'\x01' * 16),
            Chunk(
                name='LIST',
                list_type='doc ',
                children=[_leaf('mcfg', b'\x02' * 16), _leaf('odd ', b'\x03' * 7)],
            ),
        ],
    )
    data = serialize(tree)
    parsed = parse(data)
    assert parsed.list_type == 'CDRT'
    assert [ch.name for ch in parsed.children] == ['fver', 'LIST']
    doc = parsed.children[1]
    assert doc.list_type == 'doc '
    assert doc.children[0].payload == b'\x02' * 16
    # нечётный payload дополняется нулём в контейнере, но не в данных
    assert doc.children[1].payload == b'\x03' * 7


def test_serialize_pads_odd_sizes() -> None:
    """Нечётные чанки выравниваются, размеры родителей учитывают паддинг."""
    tree = Chunk(name='RIFF', list_type='CDRT', children=[_leaf('odd ', b'x' * 3)])
    data = serialize(tree)
    # 4 имени + 4 размера + 3 тела + 1 паддинг
    assert len(data) == 8 + 4 + 8 + 3 + 1
    assert parse(data).children[0].payload == b'x' * 3


def test_parse_rejects_non_riff() -> None:
    """Не-RIFF содержимое отклоняется с внятной ошибкой."""
    with pytest.raises(CdrFormatError, match='RIFF'):
        parse(b'PK\x03\x04....')


def test_stub_roundtrip() -> None:
    """Стаб пакуется и разбирается симметрично."""
    chunk = _leaf('loda', b'\x00' * 16)
    chunk.set_stub(2, 123, 456)
    assert chunk.stub() == (2, 123, 456)
    assert struct.unpack('<IIQ', chunk.payload) == (2, 123, 456)


def test_stub_rejects_wrong_size() -> None:
    """Стаб не 16 байт — ошибка формата."""
    with pytest.raises(CdrFormatError, match='16'):
        _leaf('loda', b'\x00' * 8).stub()


def test_find_all_recurses() -> None:
    """find_all находит чанки на любой глубине."""
    tree = Chunk(
        name='RIFF',
        list_type='CDRT',
        children=[
            Chunk(
                name='LIST',
                list_type='a',
                children=[Chunk(name='LIST', list_type='b', children=[_leaf('loda', b'')])],
            ),
            _leaf('loda', b''),
        ],
    )
    assert len(tree.find_all('loda')) == 2

"""Тесты чтения CDR: контейнер, loda, trfd, разбор подпутей."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from lbs_liner.cdr_read import CdrDocument, _split_subpaths
from lbs_liner.riff import CdrFormatError


def test_load_and_parse_objects(sample_cdr: Path) -> None:
    """Из контейнера достаются все четыре объекта-кривые."""
    doc = CdrDocument.load(sample_cdr)
    objects = doc.curve_objects()
    assert len(objects) == 4
    for obj in objects:
        assert obj.outl_id == 3
        assert obj.fill_id == 1
        assert obj.transform == (1.0, 0.0, 0.5, 0.0, 1.0, 0.25)


def test_objects_know_their_layers(sample_cdr: Path) -> None:
    """Каждый объект привязан к слою, имена слоёв читаются."""
    doc = CdrDocument.load(sample_cdr)
    names = {doc.layer_name(obj.layer_chunk) for obj in doc.curve_objects()}
    assert names == {'Заливка', 'Топооснова'}


def test_world_subpaths_applies_transform(sample_cdr: Path) -> None:
    """Мировые координаты сдвинуты матрицей trfd."""
    doc = CdrDocument.load(sample_cdr)
    # пятно вокруг (-2, 1) — единственная кривая с отрицательными x
    blob = next(o for o in doc.curve_objects() if o.points[0][0] < 0)
    subs = blob.world_subpaths()
    assert len(subs) == 1
    assert subs[0].closed
    xs = [x for x, _ in subs[0].points]
    assert min(xs) == pytest.approx(-2.25 + 0.5)


def test_zone_object_has_two_subpaths(sample_cdr: Path) -> None:
    """У зоны главное кольцо и дыра-карман."""
    doc = CdrDocument.load(sample_cdr)
    zone = max(doc.curve_objects(), key=lambda o: len(o.points))
    subs = zone.world_subpaths()
    assert len(subs) == 2
    assert all(sub.closed for sub in subs)


def test_load_rejects_plain_file(tmp_path: Path) -> None:
    """Не-zip файл отклоняется с понятным сообщением."""
    bad = tmp_path / 'bad.cdr'
    bad.write_bytes(b'RIFFxxxxCDRA' + b'\x00' * 100)
    with pytest.raises(CdrFormatError, match='до X7'):
        CdrDocument.load(bad)


def test_load_rejects_foreign_zip(tmp_path: Path) -> None:
    """Zip без content/root.dat — не CDR."""
    bad = tmp_path / 'bad.cdr'
    with zipfile.ZipFile(bad, 'w') as zf:
        zf.writestr('hello.txt', 'x')
    with pytest.raises(CdrFormatError, match='root.dat'):
        CdrDocument.load(bad)


def test_split_subpaths_open_and_closed() -> None:
    """Открытый и замкнутый подпути разделяются по битам типов."""
    points = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (5.0, 5.0), (6.0, 5.0), (5.0, 6.0)]
    types = [0x04, 0x44, 0x44, 0x0C, 0x44, 0x48]
    subs = _split_subpaths(points, types, tolerance=0.01)
    assert len(subs) == 2
    assert not subs[0].closed
    assert subs[1].closed


def test_split_subpaths_flattens_bezier() -> None:
    """Кубическая кривая превращается в ломаную с промежуточными точками."""
    points = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    types = [0x04, 0xC0, 0xC0, 0x84]
    subs = _split_subpaths(points, types, tolerance=0.01)
    assert len(subs) == 1
    pts = subs[0].points
    assert len(pts) > 4
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (1.0, 0.0)
    # кривая выгибается вверх между концами
    assert max(y for _, y in pts) > 0.5

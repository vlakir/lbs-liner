"""Тесты CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from main import build_parser, run

from lbs_liner.synthetic import build_sample_cdr


def test_happy_path(sample_cdr: Path, tmp_path: Path) -> None:
    """Штатный прогон: выход создан, код возврата 0."""
    out = tmp_path / 'result.cdr'
    args = build_parser().parse_args([str(sample_cdr), '-o', str(out)])
    assert run(args) == 0
    assert out.exists()


def test_default_output_name(sample_cdr: Path) -> None:
    """Без -o результат ложится рядом с входом с суффиксом -lines."""
    args = build_parser().parse_args([str(sample_cdr)])
    assert run(args) == 0
    assert sample_cdr.with_name('sample-lines.cdr').exists()


def test_missing_input_fails(tmp_path: Path) -> None:
    """Несуществующий вход — код 1, без трейсбека наружу."""
    args = build_parser().parse_args([str(tmp_path / 'нет.cdr')])
    assert run(args) == 1


def test_not_a_cdr_fails(tmp_path: Path) -> None:
    """Мусорный файл — код 1."""
    bad = tmp_path / 'bad.cdr'
    bad.write_bytes(b'\x00' * 64)
    args = build_parser().parse_args([str(bad)])
    assert run(args) == 1


def test_batch_mode(
    sample_cdr: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Без аргументов обрабатываются все .cdr папки, кроме *-lines."""
    ready = tmp_path / 'старый-lines.cdr'
    ready.write_bytes(sample_cdr.read_bytes())
    (tmp_path / 'заметки.txt').write_text('не кордел')
    monkeypatch.chdir(tmp_path)
    assert run(build_parser().parse_args(['--batch'])) == 0
    assert (tmp_path / 'sample-lines.cdr').exists()
    assert not (tmp_path / 'старый-lines-lines.cdr').exists()


def test_batch_continues_after_error(
    sample_cdr: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Битый файл пропускается с кодом 1, остальные обрабатываются."""
    (tmp_path / 'битый.cdr').write_bytes(b'\x00' * 32)
    monkeypatch.chdir(tmp_path)
    assert run(build_parser().parse_args(['--batch'])) == 1
    assert (tmp_path / 'sample-lines.cdr').exists()
    assert not (tmp_path / 'битый-lines.cdr').exists()


def test_batch_empty_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустая папка — код 1 и внятное сообщение."""
    monkeypatch.chdir(tmp_path)
    assert run(build_parser().parse_args(['--batch'])) == 1


def test_no_input_without_batch_fails() -> None:
    """Опции без файла и без --batch — ошибка использования."""
    assert run(build_parser().parse_args(['--red-width', '4'])) == 2


def test_batch_rejects_output_flag() -> None:
    """-o без входного файла — ошибка использования."""
    assert run(build_parser().parse_args(['-o', 'x.cdr'])) == 2


def test_batch_skips_zoneless(
    sample_cdr: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Файл без залитой зоны — не ошибка, просто пропуск."""
    build_sample_cdr(tmp_path / 'пустой.cdr', filled=False)
    monkeypatch.chdir(tmp_path)
    assert run(build_parser().parse_args(['--batch'])) == 0
    assert (tmp_path / 'sample-lines.cdr').exists()
    assert not (tmp_path / 'пустой-lines.cdr').exists()


def test_single_zoneless_fails_plainly(tmp_path: Path) -> None:
    """Одиночный режим на файле без зоны — код 1."""
    path = build_sample_cdr(tmp_path / 'пустой.cdr', filled=False)
    assert run(build_parser().parse_args([str(path)])) == 1


def test_defaults() -> None:
    """Дефолты: красная 3 pt, синяя 2 pt, просвет 0 — вплотную."""
    args = build_parser().parse_args(['x.cdr'])
    assert args.red_width == 3.0
    assert args.blue_width == 2.0
    assert args.gap == 0.0

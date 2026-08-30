"""Тесты CLI."""

from __future__ import annotations

from pathlib import Path

from main import build_parser, run


def test_happy_path(sample_cdr: Path, tmp_path: Path) -> None:
    """Штатный прогон: выход создан, код возврата 0."""
    out = tmp_path / 'result.cdr'
    args = build_parser().parse_args([str(sample_cdr), '-o', str(out), '--gap', '2.0'])
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


def test_defaults() -> None:
    """Дефолты параметров: 0.2 мм толщина, 0.6 мм зазор."""
    args = build_parser().parse_args(['x.cdr'])
    assert args.width == 0.2
    assert args.gap == 0.6

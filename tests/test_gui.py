"""Тесты окна: без mainloop, диалоги подменяются напрямую."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.cdr_write import DEFAULT_LAYER_NAME
from lbs_liner.gui import App, _parse_non_negative, _parse_number, _parse_positive

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def app() -> Iterator[App]:
    try:
        window = App()
    except tk.TclError:
        pytest.skip('нет дисплея для tkinter')
    yield window
    logging.getLogger().removeHandler(window._log_handler)  # noqa: SLF001
    window.destroy()


def _log_text(window: App) -> str:
    return window.log_widget.get('1.0', 'end')


def test_convert_via_gui(app: App, sample_cdr: Path) -> None:
    """Полный проход через окно: файл выбран, преобразован, выход читается."""
    out = sample_cdr.with_name('из-окна.cdr')
    app.input_var.set(str(sample_cdr))
    app.output_var.set(str(out))
    app.convert()
    assert out.exists()
    result = CdrDocument.load(out)
    new_objects = [
        obj
        for obj in result.curve_objects()
        if result.layer_name(obj.layer_chunk) == DEFAULT_LAYER_NAME
    ]
    assert len(new_objects) == 2
    assert 'готово' in _log_text(app)


def test_missing_input_reports(app: App, tmp_path: Path) -> None:
    """Пустой или несуществующий вход — сообщение, не падение."""
    app.input_var.set(str(tmp_path / 'нет.cdr'))
    app.convert()
    assert 'существующий' in _log_text(app)


def test_invalid_width_reports(app: App, sample_cdr: Path) -> None:
    """Не-числовая толщина ловится до конвертации."""
    app.input_var.set(str(sample_cdr))
    app.red_var.set('толсто')
    app.convert()
    assert 'не число' in _log_text(app)
    assert not sample_cdr.with_name('sample-lines.cdr').exists()


def test_choose_input_autofills_output(
    app: App, sample_cdr: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Выбор входа подставляет имя выхода с постфиксом -lines."""
    monkeypatch.setattr(
        'lbs_liner.gui.filedialog.askopenfilename', lambda **_: str(sample_cdr)
    )
    app.choose_input()
    assert app.output_var.get().endswith('sample-lines.cdr')


def test_batch_via_gui(
    app: App, sample_cdr: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Кнопка «Обработать папку» гонит пакетный режим по выбранной папке."""
    monkeypatch.setattr(
        'lbs_liner.gui.filedialog.askdirectory', lambda **_: str(tmp_path)
    )
    app.convert_folder()
    assert (tmp_path / 'sample-lines.cdr').exists()


def test_parsers() -> None:
    """Числа принимаются и с запятой; границы проверяются."""
    assert _parse_number(' 3,5 ') == 3.5
    assert _parse_positive('2') == 2.0
    assert _parse_non_negative('0') == 0.0
    with pytest.raises(ValueError, match='больше нуля'):
        _parse_positive('0')
    with pytest.raises(ValueError, match='отрицательным'):
        _parse_non_negative('-1')
    with pytest.raises(ValueError, match='не число'):
        _parse_number('пять')

"""Тесты окна: без mainloop, диалоги подменяются напрямую."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lbs_liner.cdr_read import CdrDocument
from lbs_liner.cdr_write import DEFAULT_LAYER_NAME
from lbs_liner.dialogs import _zenity
from lbs_liner.gui import App, _parse_non_negative, _parse_number, _parse_positive

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('APPDATA', str(tmp_path))


@pytest.fixture
def app() -> Iterator[App]:
    try:
        window = App()
    except tk.TclError:
        pytest.skip('нет дисплея для tkinter')
    yield window
    window.destroy()


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
    assert 'Готово' in app.status_var.get()


def test_button_follows_input(app: App, sample_cdr: Path) -> None:
    """Кнопка активируется только когда выбран существующий файл."""
    assert str(app.convert_button['state']) == 'disabled'
    app.input_var.set(str(sample_cdr))
    assert str(app.convert_button['state']) == 'normal'
    app.input_var.set(str(sample_cdr) + '.нет')
    assert str(app.convert_button['state']) == 'disabled'


def test_missing_input_reports(app: App, tmp_path: Path) -> None:
    """Несуществующий вход — сообщение в статусе, не падение."""
    app.input_var.set(str(tmp_path / 'нет.cdr'))
    app.convert()
    assert 'существующий' in app.status_var.get()


def test_invalid_width_reports(app: App, sample_cdr: Path) -> None:
    """Не-числовая толщина ловится до конвертации."""
    app.input_var.set(str(sample_cdr))
    app.red_var.set('толсто')
    app.convert()
    assert 'не число' in app.status_var.get()
    assert not sample_cdr.with_name('sample-lines.cdr').exists()


def test_choose_input_autofills_output(
    app: App, sample_cdr: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Выбор входа подставляет имя выхода с постфиксом -lines."""
    monkeypatch.setattr('lbs_liner.gui.pick_open_file', lambda: str(sample_cdr))
    app.choose_input()
    assert app.output_var.get().endswith('sample-lines.cdr')


def test_parameters_survive_restart(
    sample_cdr: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Параметры, выставленные в окне, доживают до следующего запуска."""
    try:
        first = App()
    except tk.TclError:
        pytest.skip('нет дисплея для tkinter')
    first.red_var.set('4,5')
    first.blue_var.set('1')
    first.gap_var.set('0.25')
    first.on_close()

    second = App()
    try:
        assert second.red_var.get() == '4.5'
        assert second.blue_var.get() == '1'
        assert second.gap_var.get() == '0.25'
    finally:
        second.destroy()


def test_zenity_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Хелпер zenity: нет бинаря — None, отмена — '', успех — вывод."""
    monkeypatch.setattr('lbs_liner.dialogs.shutil.which', lambda _name: None)
    assert _zenity(['--file-selection']) is None
    monkeypatch.setattr('lbs_liner.dialogs.shutil.which', lambda _name: '/bin/false')
    assert _zenity([]) == ''
    monkeypatch.setattr('lbs_liner.dialogs.shutil.which', lambda _name: '/bin/echo')
    assert _zenity(['выбранный.cdr']) == 'выбранный.cdr'


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

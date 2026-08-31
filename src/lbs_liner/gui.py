"""Простое окно поверх конвейера: файл, параметры, одна кнопка."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import font, ttk

from lbs_liner.convert import convert_file, lines_name
from lbs_liner.dialogs import pick_open_file, pick_save_file
from lbs_liner.geometry import NoZoneError
from lbs_liner.riff import CdrFormatError
from lbs_liner.settings import load_settings, save_settings

logger = logging.getLogger(__name__)

_PADDING = 6
# Ширина полей путей в символах — общая мера для любых шрифтов и DPI.
_PATH_CHARS = 60
_ERROR_COLOR = '#a00000'


class App(tk.Tk):
    """Главное (и единственное) окно утилиты."""

    def __init__(self) -> None:
        super().__init__()
        self.title('lbs-liner — двойная линия из заливки')
        self.resizable(width=True, height=False)
        # Размеры пляшут от шрифта платформы, а не от пикселей: поля путей
        # задаются числом символов, окно само подстраивается под шрифт.
        char_width = font.nametofont('TkDefaultFont').measure('0')

        saved = load_settings()
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.red_var = tk.StringVar(value=_pretty(saved['red_width']))
        self.blue_var = tk.StringVar(value=_pretty(saved['blue_width']))
        self.gap_var = tk.StringVar(value=_pretty(saved['gap']))
        self.status_var = tk.StringVar()

        body = ttk.Frame(self, padding=_PADDING * 2)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text='Входной .cdr:').grid(
            row=0, column=0, sticky='w', pady=_PADDING
        )
        ttk.Entry(body, textvariable=self.input_var, width=_PATH_CHARS).grid(
            row=0, column=1, sticky='ew', padx=_PADDING, pady=_PADDING
        )
        ttk.Button(body, text='Выбрать…', command=self.choose_input).grid(
            row=0, column=2, pady=_PADDING
        )

        ttk.Label(body, text='Сохранить в:').grid(
            row=1, column=0, sticky='w', pady=_PADDING
        )
        ttk.Entry(body, textvariable=self.output_var, width=_PATH_CHARS).grid(
            row=1, column=1, sticky='ew', padx=_PADDING, pady=_PADDING
        )
        ttk.Button(body, text='Обзор…', command=self.choose_output).grid(
            row=1, column=2, pady=_PADDING
        )

        params = ttk.Frame(body)
        params.grid(row=2, column=0, columnspan=3, sticky='w', pady=_PADDING * 2)
        for column, (label, var) in enumerate(
            [
                ('Красная, pt:', self.red_var),
                ('Синяя, pt:', self.blue_var),
                ('Просвет, pt:', self.gap_var),
            ]
        ):
            ttk.Label(params, text=label).grid(row=0, column=2 * column, sticky='w')
            ttk.Entry(params, textvariable=var, width=6).grid(
                row=0, column=2 * column + 1, padx=(2, _PADDING * 2)
            )

        self.convert_button = ttk.Button(
            body, text='Преобразовать', command=self.convert, state='disabled'
        )
        # Кнопка — по центру нижней зоны: воздух до неё равен воздуху
        # после (учитывая строку статуса и рамку окна).
        self.convert_button.grid(
            row=3, column=0, columnspan=3, pady=(_PADDING * 3, _PADDING)
        )

        self.status_label = ttk.Label(
            body,
            textvariable=self.status_var,
            wraplength=char_width * (_PATH_CHARS + 12),
        )
        self.status_label.grid(row=4, column=0, columnspan=3, sticky='w')

        self.input_var.trace_add('write', self._refresh_button)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    # --- обработчики -------------------------------------------------------

    def choose_input(self) -> None:
        """Выбрать входной файл; выход подставляется автоматически."""
        chosen = pick_open_file()
        if chosen:
            self.input_var.set(chosen)
            self.output_var.set(str(lines_name(Path(chosen))))

    def choose_output(self) -> None:
        """Выбрать имя выходного файла."""
        chosen = pick_save_file(self.output_var.get().strip())
        if chosen:
            self.output_var.set(chosen)

    def convert(self) -> None:
        """Преобразовать выбранный файл."""
        params = self._params()
        if params is None:
            return
        input_path = Path(self.input_var.get().strip())
        if not input_path.is_file():
            self._status('Выбери существующий входной .cdr', error=True)
            return
        output_path = (
            Path(self.output_var.get().strip())
            if self.output_var.get().strip()
            else lines_name(input_path)
        )
        self.convert_button.configure(state='disabled')
        self._status('Преобразую…')
        self.update_idletasks()
        problem: str | None = None
        try:
            convert_file(input_path, output_path, *params)
        except NoZoneError as exc:
            problem = str(exc)
        except (CdrFormatError, ValueError, OSError) as exc:
            logger.exception('не получилось')
            problem = f'Не получилось: {exc}'
        finally:
            self._refresh_button()
        if problem:
            self._status(problem, error=True)
        else:
            self._status(f'Готово: {output_path}')

    def on_close(self) -> None:
        """Запомнить параметры и закрыть окно."""
        params = self._params(quiet=True)
        if params is not None:
            save_settings(*params)
        self.destroy()

    def _params(self, *, quiet: bool = False) -> tuple[float, float, float] | None:
        try:
            red_pt = _parse_positive(self.red_var.get())
            blue_pt = _parse_positive(self.blue_var.get())
            gap_pt = _parse_non_negative(self.gap_var.get())
        except ValueError as exc:
            problem = str(exc)
        else:
            save_settings(red_pt, blue_pt, gap_pt)
            return red_pt, blue_pt, gap_pt
        if not quiet:
            self._status(problem, error=True)
        return None

    def _refresh_button(self, *_args: str) -> None:
        ready = Path(self.input_var.get().strip()).is_file()
        self.convert_button.configure(state='normal' if ready else 'disabled')

    def _status(self, text: str, *, error: bool = False) -> None:
        self.status_var.set(text)
        self.status_label.configure(foreground=_ERROR_COLOR if error else '')


def _pretty(value: float) -> str:
    """Число без лишнего хвоста: 3.0 → «3», 2.5 → «2.5»."""
    return str(int(value)) if value == int(value) else str(value)


def _parse_positive(text: str) -> float:
    value = _parse_number(text)
    if value <= 0:
        msg = f'толщина должна быть больше нуля, а не {text!r}'
        raise ValueError(msg)
    return value


def _parse_non_negative(text: str) -> float:
    value = _parse_number(text)
    if value < 0:
        msg = f'просвет не может быть отрицательным: {text!r}'
        raise ValueError(msg)
    return value


def _parse_number(text: str) -> float:
    try:
        return float(text.strip().replace(',', '.'))
    except ValueError:
        msg = f'не число: {text!r}'
        raise ValueError(msg) from None


def run_gui() -> None:
    """Запустить окно."""
    App().mainloop()

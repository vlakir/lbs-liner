"""Простое окно поверх конвейера: выбор файла, параметры, лог."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from lbs_liner.convert import (
    convert_file,
    lines_name,
    run_batch,
)
from lbs_liner.geometry import NoZoneError
from lbs_liner.riff import CdrFormatError
from lbs_liner.settings import load_settings, save_settings

logger = logging.getLogger(__name__)

_PADDING = 6


class TextLogHandler(logging.Handler):
    """Логи конвейера — прямо в текстовое поле окна."""

    def __init__(self, widget: tk.Text) -> None:
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        """Дописать строку в конец поля и прокрутить к ней."""
        message = self.format(record)
        self.widget.configure(state='normal')
        self.widget.insert('end', message + '\n')
        self.widget.configure(state='disabled')
        self.widget.see('end')
        self.widget.update_idletasks()


class App(tk.Tk):
    """Главное (и единственное) окно утилиты."""

    def __init__(self) -> None:
        super().__init__()
        self.title('lbs-liner — двойная линия из заливки')
        self.minsize(560, 420)

        saved = load_settings()
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.red_var = tk.StringVar(value=_pretty(saved['red_width']))
        self.blue_var = tk.StringVar(value=_pretty(saved['blue_width']))
        self.gap_var = tk.StringVar(value=_pretty(saved['gap']))

        body = ttk.Frame(self, padding=_PADDING)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text='Входной .cdr:').grid(row=0, column=0, sticky='w')
        ttk.Entry(body, textvariable=self.input_var).grid(
            row=0, column=1, sticky='ew', padx=_PADDING
        )
        ttk.Button(body, text='Выбрать…', command=self.choose_input).grid(
            row=0, column=2
        )

        ttk.Label(body, text='Сохранить в:').grid(row=1, column=0, sticky='w')
        ttk.Entry(body, textvariable=self.output_var).grid(
            row=1, column=1, sticky='ew', padx=_PADDING
        )
        ttk.Button(body, text='Обзор…', command=self.choose_output).grid(
            row=1, column=2
        )

        params = ttk.Frame(body)
        params.grid(row=2, column=0, columnspan=3, sticky='w', pady=_PADDING)
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

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=3, sticky='w')
        self.convert_button = ttk.Button(
            buttons, text='Преобразовать файл', command=self.convert
        )
        self.convert_button.grid(row=0, column=0, padx=(0, _PADDING))
        self.batch_button = ttk.Button(
            buttons, text='Обработать папку…', command=self.convert_folder
        )
        self.batch_button.grid(row=0, column=1)

        self.log_widget = tk.Text(body, height=12, state='disabled', wrap='word')
        self.log_widget.grid(
            row=4, column=0, columnspan=3, sticky='nsew', pady=_PADDING
        )
        body.rowconfigure(4, weight=1)

        handler = TextLogHandler(self.log_widget)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        self._log_handler = handler
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    # --- обработчики -------------------------------------------------------

    def choose_input(self) -> None:
        """Выбрать входной файл; выход подставляется автоматически."""
        chosen = filedialog.askopenfilename(
            title='Входной файл CorelDRAW',
            filetypes=[('CorelDRAW', '*.cdr'), ('Все файлы', '*.*')],
        )
        if chosen:
            self.input_var.set(chosen)
            self.output_var.set(str(lines_name(Path(chosen))))

    def choose_output(self) -> None:
        """Выбрать имя выходного файла."""
        chosen = filedialog.asksaveasfilename(
            title='Куда сохранить результат',
            defaultextension='.cdr',
            filetypes=[('CorelDRAW', '*.cdr')],
        )
        if chosen:
            self.output_var.set(chosen)

    def convert(self) -> None:
        """Преобразовать выбранный файл."""
        params = self._params()
        if params is None:
            return
        red_pt, blue_pt, gap_pt = params
        input_path = Path(self.input_var.get().strip())
        if not self.input_var.get().strip() or not input_path.is_file():
            logger.error('выбери существующий входной .cdr')
            return
        output_path = (
            Path(self.output_var.get().strip())
            if self.output_var.get().strip()
            else lines_name(input_path)
        )
        no_zone: str | None = None
        self._busy(active=True)
        try:
            convert_file(input_path, output_path, red_pt, blue_pt, gap_pt)
        except NoZoneError as exc:
            no_zone = str(exc)
        except CdrFormatError, ValueError, OSError:
            logger.exception('не получилось')
        finally:
            self._busy(active=False)
        if no_zone:
            logger.error(no_zone)

    def convert_folder(self) -> None:
        """Обработать все .cdr выбранной папки."""
        params = self._params()
        if params is None:
            return
        chosen = filedialog.askdirectory(title='Папка с .cdr')
        if not chosen:
            return
        self._busy(active=True)
        try:
            run_batch(Path(chosen), *params)
        finally:
            self._busy(active=False)

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
            logger.error(problem)
        return None

    def _busy(self, *, active: bool) -> None:
        state = 'disabled' if active else 'normal'
        self.convert_button.configure(state=state)
        self.batch_button.configure(state=state)
        self.update_idletasks()


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

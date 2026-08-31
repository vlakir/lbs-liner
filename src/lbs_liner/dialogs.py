"""Файловые диалоги: на Linux — нативный zenity, иначе (и фолбэком) tkinter."""

from __future__ import annotations

import shutil
import subprocess
import sys
from tkinter import filedialog

_ZENITY_TIMEOUT_S = 600


def _zenity(args: list[str]) -> str | None:
    """Запустить zenity; None — недоступен, '' — отмена, иначе выбранный путь."""
    exe = shutil.which('zenity')
    if exe is None:
        return None
    try:
        # Аргументы фиксированные, путь из shutil.which — недоверенного
        # ввода нет (подавление согласовано с Разработчиком 2026-08-31).
        result = subprocess.run(  # noqa: S603
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=_ZENITY_TIMEOUT_S,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return ''
    return result.stdout.strip()


def pick_open_file() -> str:
    """Диалог выбора входного .cdr; пустая строка — отмена."""
    if sys.platform != 'win32':
        chosen = _zenity(
            [
                '--file-selection',
                '--title=Входной файл CorelDRAW',
                '--file-filter=CorelDRAW | *.cdr *.CDR',
                '--file-filter=Все файлы | *',
            ]
        )
        if chosen is not None:
            return chosen
    return filedialog.askopenfilename(
        title='Входной файл CorelDRAW',
        filetypes=[('CorelDRAW', '*.cdr'), ('Все файлы', '*.*')],
    )


def pick_save_file(initial: str) -> str:
    """Диалог выбора выходного файла; пустая строка — отмена."""
    if sys.platform != 'win32':
        args = ['--file-selection', '--save', '--title=Куда сохранить результат']
        if initial:
            args.append(f'--filename={initial}')
        chosen = _zenity(args)
        if chosen is not None:
            return chosen
    return filedialog.asksaveasfilename(
        title='Куда сохранить результат',
        defaultextension='.cdr',
        filetypes=[('CorelDRAW', '*.cdr')],
    )

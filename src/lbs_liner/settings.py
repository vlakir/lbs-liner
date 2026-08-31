"""Память параметров между запусками: settings.json в профиле пользователя."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from lbs_liner.convert import DEFAULT_BLUE_PT, DEFAULT_GAP_PT, DEFAULT_RED_PT

logger = logging.getLogger(__name__)

_KEYS = ('red_width', 'blue_width', 'gap')


def settings_path() -> Path:
    """Файл настроек: %APPDATA%/lbs-liner на Windows, ~/.config/lbs-liner иначе."""
    appdata = os.environ.get('APPDATA')
    root = Path(appdata) if appdata else Path.home() / '.config'
    return root / 'lbs-liner' / 'settings.json'


def load_settings() -> dict[str, float]:
    """Прочитать сохранённые параметры; на любой беде — дефолты."""
    defaults = {
        'red_width': DEFAULT_RED_PT,
        'blue_width': DEFAULT_BLUE_PT,
        'gap': DEFAULT_GAP_PT,
    }
    try:
        raw = json.loads(settings_path().read_text(encoding='utf-8'))
        for key in _KEYS:
            defaults[key] = float(raw[key])
    except OSError, ValueError, KeyError, TypeError:
        pass
    return defaults


def save_settings(red_width: float, blue_width: float, gap: float) -> None:
    """Сохранить параметры; сбой записи не роняет работу."""
    payload = {'red_width': red_width, 'blue_width': blue_width, 'gap': gap}
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    except OSError:
        logger.warning('не удалось сохранить настройки в %s', path)

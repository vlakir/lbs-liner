"""Тесты памяти параметров."""

from __future__ import annotations

from pathlib import Path

import pytest

from lbs_liner.settings import load_settings, save_settings, settings_path


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('APPDATA', str(tmp_path))


def test_roundtrip() -> None:
    """Сохранённое читается обратно."""
    save_settings(4.5, 1.5, 0.7)
    assert load_settings() == {'red_width': 4.5, 'blue_width': 1.5, 'gap': 0.7}


def test_defaults_when_missing() -> None:
    """Нет файла — дефолты 3/2/0."""
    assert load_settings() == {'red_width': 3.0, 'blue_width': 2.0, 'gap': 0.0}


def test_defaults_when_corrupted() -> None:
    """Битый файл не роняет запуск."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('не json', encoding='utf-8')
    assert load_settings() == {'red_width': 3.0, 'blue_width': 2.0, 'gap': 0.0}


def test_partial_file_falls_back() -> None:
    """Файл без нужных ключей — дефолты."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"red_width": "жирная"}', encoding='utf-8')
    assert load_settings() == {'red_width': 3.0, 'blue_width': 2.0, 'gap': 0.0}

"""Общие фикстуры: синтетический CDR из lbs_liner.synthetic."""

from __future__ import annotations

from pathlib import Path

import pytest

from lbs_liner.synthetic import build_sample_cdr


@pytest.fixture
def sample_cdr(tmp_path: Path) -> Path:
    """Синтетический .cdr на диске."""
    return build_sample_cdr(tmp_path / 'sample.cdr')

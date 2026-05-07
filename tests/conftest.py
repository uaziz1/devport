import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Copy sample registry to a tmp path and point devport at it."""
    src = FIXTURES / "sample.toml"
    dst = tmp_path / "dev-ports.toml"
    shutil.copy(src, dst)
    monkeypatch.setenv("DEVPORTS_FILE", str(dst))
    return dst


@pytest.fixture
def clean_registry(tmp_path, monkeypatch):
    """A registry with no collisions, for free/check tests."""
    p = tmp_path / "dev-ports.toml"
    p.write_text(
        "[alpha]\nweb = 3010\napi = 3011\n\n[beta]\nweb = 3020\n"
    )
    monkeypatch.setenv("DEVPORTS_FILE", str(p))
    return p

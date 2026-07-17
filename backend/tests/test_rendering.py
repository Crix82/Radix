from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.rendering import (
    PageOutOfRange,
    page_count,
    pagecache_dir,
    render_page,
)
from tests.conftest import FIXTURES_DIR

RS30 = FIXTURES_DIR / "RS-30_instruction_manual.pdf"


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_page_count() -> None:
    assert page_count(RS30) == 2


def test_render_creates_cached_png(data_dir: Path) -> None:
    out = render_page(42, RS30, 1)
    assert out == pagecache_dir() / "42" / "1.png"
    assert out.is_file()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_is_cached_not_regenerated(data_dir: Path) -> None:
    first = render_page(7, RS30, 2)
    mtime = first.stat().st_mtime_ns
    second = render_page(7, RS30, 2)
    assert second == first
    assert second.stat().st_mtime_ns == mtime  # served from cache, not re-rendered


def test_render_out_of_range_raises(data_dir: Path) -> None:
    with pytest.raises(PageOutOfRange):
        render_page(1, RS30, 99)
    with pytest.raises(PageOutOfRange):
        render_page(1, RS30, 0)

"""services/logo_service.py 테스트 (CP14 TDD).

두 축:
A. render_wordmark — logo_gen_exp 의 pil_renderer 에서 이식. 순수 함수.
B. LogoAutoGenerator — render_wordmark 호출 + 파일 저장까지 담당.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from services.logo_service import LogoAutoGenerator, render_wordmark

# 이식 대상 폰트 — assets/fonts/ 로 배치된다.
_ASSETS_FONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "LXGWWenKaiKR-Medium.ttf"


class TestRenderWordmark:
    def test_returns_png_magic_bytes(self):
        out = render_wordmark(
            name="goorm", color_hex="#5562EA", font_path=_ASSETS_FONT
        )
        assert out.startswith(b"\x89PNG")

    def test_non_trivial_bytes(self):
        out = render_wordmark(
            name="goorm", color_hex="#000000", font_path=_ASSETS_FONT
        )
        assert len(out) > 500

    def test_white_corner_background(self):
        out = render_wordmark(
            name="x", color_hex="#FF0000", font_path=_ASSETS_FONT
        )
        img = Image.open(io.BytesIO(out)).convert("RGB")
        assert img.getpixel((2, 2)) == (255, 255, 255)

    def test_korean_name(self):
        out = render_wordmark(
            name="구름 베이커리", color_hex="#000000", font_path=_ASSETS_FONT
        )
        assert out.startswith(b"\x89PNG")
        assert len(out) > 500

    def test_missing_font_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            render_wordmark(
                name="x", color_hex="#000000", font_path=tmp_path / "nope.ttf"
            )


class TestLogoAutoGenerator:
    """파일 저장까지 책임지는 래퍼 — save_dir 을 주입받아 격리 가능."""

    def test_generate_and_save_returns_existing_png_file(self, tmp_path):
        save_dir = tmp_path / "brand_assets"
        gen = LogoAutoGenerator(font_path=_ASSETS_FONT, save_dir=save_dir)
        path = gen.generate_and_save(name="goorm", color_hex="#5562EA")
        assert path.exists()
        assert path.suffix == ".png"
        assert path.parent == save_dir
        assert path.read_bytes().startswith(b"\x89PNG")

    def test_each_call_creates_new_file(self, tmp_path):
        save_dir = tmp_path / "brand_assets"
        gen = LogoAutoGenerator(font_path=_ASSETS_FONT, save_dir=save_dir)
        p1 = gen.generate_and_save(name="a", color_hex="#000000")
        p2 = gen.generate_and_save(name="b", color_hex="#111111")
        assert p1 != p2
        assert p1.exists() and p2.exists()

    def test_save_dir_is_created_if_missing(self, tmp_path):
        save_dir = tmp_path / "new_dir_that_does_not_exist"
        gen = LogoAutoGenerator(font_path=_ASSETS_FONT, save_dir=save_dir)
        gen.generate_and_save(name="x", color_hex="#000000")
        assert save_dir.exists()
        assert save_dir.is_dir()

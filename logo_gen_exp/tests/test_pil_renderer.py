"""PIL 기반 워드마크 렌더러 테스트 (TDD 사이클 4).

실제 TTF 폰트 파일(LXGWWenKaiKR-Medium.ttf) 을 사용하므로 파일 존재 전제.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from logo_gen_exp.pil_renderer import render_wordmark
from logo_gen_exp.tests.conftest import FONT_PATH_KR_MEDIUM


class TestBytesOutput:
    def test_returns_png_magic_bytes(self):
        out = render_wordmark(
            name="goorm", color_hex="#5562EA", font_path=FONT_PATH_KR_MEDIUM
        )
        assert out.startswith(b"\x89PNG"), "PNG magic bytes 로 시작해야 함"

    def test_bytes_is_non_trivial(self):
        """텍스트가 실제로 그려졌다면 일정 크기 이상의 바이트가 나와야 함."""
        out = render_wordmark(
            name="goorm", color_hex="#000000", font_path=FONT_PATH_KR_MEDIUM
        )
        assert len(out) > 500


class TestImageProperties:
    def _load(self, png_bytes: bytes) -> Image.Image:
        return Image.open(io.BytesIO(png_bytes)).convert("RGB")

    def test_default_canvas_is_square(self):
        out = render_wordmark(
            name="goorm", color_hex="#000000", font_path=FONT_PATH_KR_MEDIUM
        )
        img = self._load(out)
        assert img.width == img.height

    def test_white_background_at_corner(self):
        out = render_wordmark(
            name="x", color_hex="#FF0000", font_path=FONT_PATH_KR_MEDIUM
        )
        img = self._load(out)
        # 좌상단 모서리는 흰색이어야 함
        assert img.getpixel((2, 2)) == (255, 255, 255)

    def test_color_hex_pixel_present(self):
        """지정 색의 픽셀이 이미지 어딘가에 반드시 존재해야 함.
        anti-aliasing 때문에 완벽히 동일한 RGB 픽셀 수가 많진 않아도 몇 개는 있어야 함.
        """
        target_rgb = (0xAA, 0x11, 0x88)  # #AA1188
        out = render_wordmark(
            name="X", color_hex="#AA1188", font_path=FONT_PATH_KR_MEDIUM
        )
        img = self._load(out)
        pixels = img.getdata()
        # AA 근처의 R 값만 체크해도 글자가 그려진 흔적을 포착 가능 (anti-aliasing 대비)
        matched = sum(
            1
            for (r, g, b) in pixels
            if abs(r - target_rgb[0]) < 20
            and abs(g - target_rgb[1]) < 20
            and abs(b - target_rgb[2]) < 20
        )
        assert matched > 0, "브랜드 색상이 반영된 픽셀이 하나도 없음"


class TestLanguageSupport:
    def test_english_name_renders(self):
        out = render_wordmark(
            name="goorm bakery", color_hex="#000000", font_path=FONT_PATH_KR_MEDIUM
        )
        assert out.startswith(b"\x89PNG")
        assert len(out) > 500

    def test_korean_name_renders(self):
        out = render_wordmark(
            name="구름 베이커리", color_hex="#000000", font_path=FONT_PATH_KR_MEDIUM
        )
        assert out.startswith(b"\x89PNG")
        assert len(out) > 500

    def test_mixed_name_renders(self):
        out = render_wordmark(
            name="GOORM 구름", color_hex="#000000", font_path=FONT_PATH_KR_MEDIUM
        )
        assert out.startswith(b"\x89PNG")
        assert len(out) > 500


class TestErrorCases:
    def test_missing_font_file_raises(self, tmp_path):
        missing = tmp_path / "nope.ttf"
        with pytest.raises(FileNotFoundError):
            render_wordmark(
                name="x", color_hex="#000000", font_path=missing
            )

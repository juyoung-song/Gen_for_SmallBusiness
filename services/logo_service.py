"""로고 자동 생성 서비스 (CP14).

온보딩 시 사용자가 로고 파일을 업로드하지 않은 경우, 브랜드 이름 + 색상만으로
PIL 로컬 렌더링을 통해 간단한 타이포그래피 워드마크 로고 PNG 를 생성/저장한다.

두 공개 API:
- render_wordmark(name, color_hex, font_path, ...) -> bytes
  순수 함수. 주입받은 TTF 로 워드마크 PNG 바이트 반환.
- LogoAutoGenerator(font_path, save_dir).generate_and_save(name, color_hex) -> Path
  render_wordmark 호출 후 지정 디렉토리에 파일 저장, 경로 반환.

실험 (logo_gen_exp/pil_renderer.py) 에서 채택된 경로를 그대로 이식.
"""

from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

DEFAULT_SIZE: tuple[int, int] = (1024, 1024)
DEFAULT_FONT_POINT = 320
DEFAULT_PADDING = 80
_MIN_FONT_POINT = 40


def _hex_to_rgb(color_hex: str) -> tuple[int, int, int]:
    """'#RRGGBB' → (R, G, B). 앞 '#' 없어도 허용."""
    h = color_hex.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"color_hex 는 '#RRGGBB' 형식이어야 합니다: {color_hex}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def render_wordmark(
    *,
    name: str,
    color_hex: str,
    font_path: Path,
    size: tuple[int, int] = DEFAULT_SIZE,
    padding: int = DEFAULT_PADDING,
    initial_font_point: int = DEFAULT_FONT_POINT,
) -> bytes:
    """TTF 로 워드마크 PNG bytes 렌더링.

    - 흰 배경 정사각 캔버스 중앙에 텍스트 배치
    - 색상 = `color_hex`
    - 폰트 크기는 initial_font_point 에서 시작, padding 넘어가면 20pt 씩 축소
      (최소 _MIN_FONT_POINT 까지). 그래도 안 맞으면 그대로 그림 (잘림 허용).
    """
    if not font_path.exists():
        raise FileNotFoundError(f"폰트 파일 없음: {font_path}")

    rgb = _hex_to_rgb(color_hex)
    canvas_w, canvas_h = size
    max_text_w = canvas_w - 2 * padding
    max_text_h = canvas_h - 2 * padding

    point = initial_font_point
    font: ImageFont.FreeTypeFont
    text_bbox: tuple[int, int, int, int]
    while point >= _MIN_FONT_POINT:
        font = ImageFont.truetype(str(font_path), point)
        text_bbox = font.getbbox(name)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        if text_w <= max_text_w and text_h <= max_text_h:
            break
        point -= 20
    else:
        font = ImageFont.truetype(str(font_path), _MIN_FONT_POINT)
        text_bbox = font.getbbox(name)

    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)

    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = (canvas_w - text_w) // 2 - text_bbox[0]
    y = (canvas_h - text_h) // 2 - text_bbox[1]
    draw.text((x, y), name, fill=rgb, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class LogoAutoGenerator:
    """TTF 폰트 경로와 저장 디렉토리를 주입받아 로고를 생성·저장한다.

    OnboardingService.finalize() 에서 `draft.logo_path is None` 일 때 사용.
    """

    def __init__(self, *, font_path: Path, save_dir: Path) -> None:
        self.font_path = font_path
        self.save_dir = save_dir

    def generate_and_save(self, *, name: str, color_hex: str) -> Path:
        """로고 PNG 를 생성해 save_dir 아래 <uuid>.png 로 저장. 경로 반환."""
        self.save_dir.mkdir(parents=True, exist_ok=True)
        png_bytes = render_wordmark(
            name=name, color_hex=color_hex, font_path=self.font_path
        )
        out_path = self.save_dir / f"{uuid4().hex}.png"
        out_path.write_bytes(png_bytes)
        return out_path

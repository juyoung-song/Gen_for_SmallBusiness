"""PIL 기반 워드마크 로고 렌더러 — 외부 모델 없이 로컬에서 그림.

특징:
- 결정적 출력 (같은 입력 → 같은 바이트)
- 한글/영문 모두 정확 (TTF 폰트의 글리프 그대로)
- 색상 `color_hex` 정확 반영
- 비용 0, 지연 ~ms 단위

LogoGenerator 의 ImageClientProtocol 과는 별개의 경로. Streamlit 에서 모드 분기로 호출.
"""

from __future__ import annotations

import io
from pathlib import Path

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

    기본 동작:
    - 흰 배경 캔버스(`size`)에 중앙 정렬된 텍스트
    - 텍스트 색 = `color_hex`
    - 폰트 크기는 `initial_font_point` 로 시도 후, padding 을 넘어가면 축소
      (최소 _MIN_FONT_POINT 까지)
    - 반환: PNG 바이트
    """
    if not font_path.exists():
        raise FileNotFoundError(f"폰트 파일 없음: {font_path}")

    rgb = _hex_to_rgb(color_hex)
    canvas_w, canvas_h = size
    max_text_w = canvas_w - 2 * padding
    max_text_h = canvas_h - 2 * padding

    # 폰트 크기 동적 조정 — 텍스트가 캔버스 안에 들어갈 때까지 축소
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
        # 최소 크기에서도 안 맞으면 그대로 진행 (잘림 허용 — 실험용)
        font = ImageFont.truetype(str(font_path), _MIN_FONT_POINT)
        text_bbox = font.getbbox(name)

    # 캔버스 준비 (흰 배경)
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 중앙 정렬 — getbbox 의 오프셋(left/top) 을 고려해 정확히 가운데
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = (canvas_w - text_w) // 2 - text_bbox[0]
    y = (canvas_h - text_h) // 2 - text_bbox[1]
    draw.text((x, y), name, fill=rgb, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

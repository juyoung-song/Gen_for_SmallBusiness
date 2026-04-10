"""Mock 이미지 백엔드 — Pillow 그라데이션 응답.

USE_MOCK 모드에서 외부 API 호출 없이 빠르게 동작 검증을 가능케 한다.
스타일별로 미리 정의된 색상으로 그라데이션 PNG 를 생성한다.

backends.image_base.ImageBackend 프로토콜 구현.

기존 services/image_service.py 의 _mock_response() 와 _create_gradient_image() 를
이 모듈로 이동.
"""

import io

from PIL import Image, ImageDraw

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

# 스타일별 그라데이션 색상 (top, bottom)
_STYLE_GRADIENTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "기본": ((41, 128, 185), (52, 152, 219)),
    "감성": ((192, 108, 132), (241, 148, 138)),
    "고급": ((44, 62, 80), (127, 140, 141)),
    "유머": ((243, 156, 18), (247, 220, 111)),
    "심플": ((149, 165, 166), (236, 240, 241)),
}


class MockImageBackend:
    """Pillow 기반 Mock 이미지 백엔드."""

    name = "mock_image"

    def __init__(self, settings=None) -> None:
        self.settings = settings  # 인터페이스 통일을 위해 받지만 사용 안 함

    def is_available(self) -> bool:
        """Pillow 만 있으면 항상 사용 가능."""
        return True

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        img = self._create_gradient_image(request.style)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return ImageGenerationResponse(
            image_data=buffer.getvalue(),
            revised_prompt=(
                f"[Mock 이미지] {request.style} 스타일 · 프롬프트: {request.prompt}"
            ),
        )

    @staticmethod
    def _create_gradient_image(style: str) -> Image.Image:
        """스타일에 맞는 그라데이션 이미지를 생성 (512x512)."""
        width, height = 512, 512
        color_top, color_bottom = _STYLE_GRADIENTS.get(style, _STYLE_GRADIENTS["기본"])

        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            ratio = y / height
            r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
            g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
            b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 장식 — 반투명 원형 포인트들
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        circles = [
            (100, 120, 80, 30),
            (350, 200, 60, 20),
            (200, 380, 100, 15),
            (420, 420, 50, 25),
            (80, 350, 40, 20),
        ]
        for cx, cy, radius, alpha in circles:
            overlay_draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=(255, 255, 255, alpha),
            )

        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")

        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [width // 4, height // 2 - 1, 3 * width // 4, height // 2 + 1],
            fill=(255, 255, 255),
        )
        return img

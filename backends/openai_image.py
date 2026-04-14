"""OpenAI gpt-image-1-mini 이미지 백엔드 (CP15).

이전 백엔드들(HF SD/FLUX/IP-Adapter, Mock)과 달리 **상품 사진 + 로고 두 장을 함께**
입력으로 넘겨 소품(컵·접시·포장)에 브랜드 로고가 자연스럽게 각인된 광고 이미지를
한 번의 호출로 생성한다.

핵심 함수:
- build_multi_input_prompt(translated_prompt) -> str
  번역된 영문 프롬프트 앞에 "첫 번째 이미지=상품, 두 번째 이미지=로고" 안내와
  로고 보존·각인 지시를 prepend 한 최종 프롬프트.
- OpenAIImageBackend — ImageBackend 프로토콜 구현체.
  ImageClient (실제는 `langfuse.openai.OpenAI`) 를 주입받아 Fake 로 테스트 가능.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any, Protocol

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-image-1-mini"
DEFAULT_SIZE = "1024x1024"


# ─────────────────────────────────────────────────────────────
# multi-input 프롬프트 빌더
# ─────────────────────────────────────────────────────────────
_MULTI_INPUT_GUIDANCE = (
    "You are given TWO images:\n"
    "  1) The FIRST image is the PRODUCT photograph (a café / bakery item).\n"
    "  2) The SECOND image is the brand WORDMARK logo — simple text on a plain\n"
    "     white background. It is NOT a style reference, NOT a color palette,\n"
    "     and NOT a mood board. Treat it purely as letter shapes to be copied.\n"
    "\n"
    "Task: Produce a single commercial advertisement / product photography image\n"
    "based on the product photo. The wordmark from the second image MUST appear\n"
    "engraved, printed, or lettered on exactly ONE plausible surface visible in\n"
    "the scene — choose ONLY ONE of: a MUG, CUP, PLATE, paper bag, NAPKIN, or\n"
    "PACKAGING. Do NOT repeat the wordmark on multiple props; pick the single\n"
    "most natural surface. Respect the perspective, curvature, and lighting of\n"
    "that surface so the wordmark looks physically part of the object.\n"
    "\n"
    "STRICT rules about the wordmark:\n"
    "- Preserve the EXACT letter shapes, spelling, and color of the wordmark.\n"
    "- Do not add or remove any letters. Do not change its text.\n"
    "- Do not distort the wordmark beyond the natural curvature of the surface.\n"
)

_TAIL_REMINDER = (
    "\n\n"
    "FINAL REMINDER (MANDATORY): The SECOND input image is a wordmark logo on\n"
    "white — copy its letters EXACTLY onto exactly ONE prop (a mug, cup, plate,\n"
    "paper bag, napkin, or packaging) in the output scene. Pick the single most\n"
    "natural prop and place the wordmark there.\n"
    "\n"
    "All OTHER props in the scene MUST be COMPLETELY BLANK — no text, no logo,\n"
    "no print, no lettering of any kind. Leave napkins plain, leave packaging\n"
    "plain, leave plates plain. Only the chosen single prop bears the wordmark."
)


def build_multi_input_prompt(*, translated_prompt: str) -> str:
    """번역된 영문 프롬프트 앞뒤로 multi-input 지시를 샌드위치.

    긴 brand_prompt 꼬리에 묻혀 multi-input 지시가 희석되는 문제를 완화하기
    위해 guidance 를 앞에 두고, 본문 뒤에도 짧은 재지시(reminder) 를 붙인다.
    """
    cleaned = translated_prompt.strip() if translated_prompt else ""
    if not cleaned:
        raise ValueError("translated_prompt 가 비어 있습니다")

    return (
        f"{_MULTI_INPUT_GUIDANCE}\n"
        "Creative direction for the product photograph (already translated to English):\n"
        f"{cleaned}"
        f"{_TAIL_REMINDER}"
    )


# ─────────────────────────────────────────────────────────────
# ImageClient Protocol (의존 주입 — 테스트에서 Fake 주입)
# ─────────────────────────────────────────────────────────────
class ImageClient(Protocol):
    def edit_images(
        self,
        *,
        model: str,
        images: list[tuple[str, bytes]],
        prompt: str,
        size: str,
    ) -> bytes:
        """모델 + 입력 이미지 리스트 + 프롬프트 → 결과 PNG bytes."""


# ─────────────────────────────────────────────────────────────
# OpenAIImageBackend 본체
# ─────────────────────────────────────────────────────────────
class OpenAIImageBackend:
    """ImageBackend 프로토콜 충족 — services/image_service.py 에서 호출됨.

    현재 ImageBackend 프로토콜에는 generate(request) -> response 가 있다.
    """

    name = "openai_image"

    def __init__(
        self,
        settings: Any,
        *,
        client: ImageClient | None = None,
        model: str = DEFAULT_MODEL,
        size: str = DEFAULT_SIZE,
    ) -> None:
        self.settings = settings
        self.model = model
        self.size = size
        self._client: ImageClient = client or _RealOpenAIImageClient(settings)

    def is_available(self) -> bool:
        return bool(getattr(self.settings, "OPENAI_API_KEY", ""))

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        if request.image_data is None:
            raise RuntimeError(
                "OpenAIImageBackend 는 상품 사진(image_data) 이 필수입니다."
            )
        logo_path = getattr(request, "logo_path", None)
        if not logo_path:
            raise RuntimeError(
                "OpenAIImageBackend 는 brand.logo_path 를 필요로 합니다. "
                "CP14 온보딩이 로고를 자동 생성하므로 이 경로가 항상 존재해야 정상."
            )
        logo_bytes = Path(logo_path).read_bytes()
        final_prompt = build_multi_input_prompt(translated_prompt=request.prompt)

        png_bytes = self._client.edit_images(
            model=self.model,
            images=[
                ("product.png", request.image_data),
                ("logo.png", logo_bytes),
            ],
            prompt=final_prompt,
            size=self.size,
        )

        return ImageGenerationResponse(
            image_data=png_bytes,
            revised_prompt=final_prompt,
        )


# ─────────────────────────────────────────────────────────────
# 실제 OpenAI 클라이언트 어댑터 (Langfuse span 포함)
# ─────────────────────────────────────────────────────────────
class _RealOpenAIImageClient:
    """langfuse.openai.OpenAI.images.edit 를 ImageClient 프로토콜로 감싼 구현체."""

    def __init__(self, settings: Any) -> None:
        from langfuse.openai import OpenAI

        self._openai = OpenAI(api_key=settings.OPENAI_API_KEY)

    def edit_images(
        self,
        *,
        model: str,
        images: list[tuple[str, bytes]],
        prompt: str,
        size: str,
    ) -> bytes:
        files = []
        for name, data in images:
            buf = io.BytesIO(data)
            buf.name = name
            files.append(buf)

        resp = self._openai.images.edit(
            model=model,
            image=files,
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            n=1,
        )
        b64 = resp.data[0].b64_json
        if not b64:
            raise RuntimeError("gpt-image-1 응답에 b64_json 데이터가 없습니다")
        return base64.b64decode(b64)

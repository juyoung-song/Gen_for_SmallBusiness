"""OpenAI gpt-image-1-mini 이미지 백엔드 (CP15).

이전 백엔드들(HF SD/FLUX/IP-Adapter, Mock)과 달리 **상품 사진 + 로고 + 참조이미지 세 장을 함께**
입력으로 넘겨 소품(컵·접시·포장)에 브랜드 로고가 자연스럽게 각인되고 참조 이미지의 구도를 따르는
광고 이미지를 한 번의 호출로 생성한다.

핵심 함수:
- build_multi_input_prompt(translated_prompt) -> str
  최적화된 영문 프롬프트 앞뒤로 multi-input 지시를 prepend/append 한 최종 프롬프트.
- OpenAIImageBackend — ImageBackend 프로토콜 구현체.
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
    "You are given UP TO THREE images:\n"
    "  1) The FIRST image is the PRODUCT (café/bakery item) to be transformed.\n"
    "  2) The SECOND image is the brand LOGO wordmark on white. Copy its exact letter shapes and color.\n"
    "  3) (Optional) The THIRD image is a REFERENCE for composition/layout.\n"
    "\n"
    "Task: Generate a single commercial photography image. \n"
    "- If the THIRD image is provided, strictly follow its camera angle, lens distance, and subject placement (ignore its subject and colors).\n"
    "- The LOGO from the SECOND image MUST be naturally engraved or printed on exactly ONE prop surface (MUG, CUP, PLATE, PACKAGING, or TRAY). \n"
    "- Match the perspective and lighting so the logo looks physically real.\n"
    "\n"
    "STRICT rules:\n"
    "- Brand logo MUST only appear on prop surfaces, NEVER floating in the air.\n"
    "- Preserve the EXACT spelling and typography of the logo.\n"
)

_TAIL_REMINDER = (
    "\n\n"
    "FINAL REMINDER: Branding logo ONLY on props (mug, plate, tray, etc.). "
    "Use correct perspective. All other props must be blank. "
    "Follow the third image's composition exactly."
)


def build_multi_input_prompt(*, translated_prompt: str) -> str:
    """최적화된 영문 프롬프트 앞뒤로 multi-input 지시를 샌드위치."""
    cleaned = translated_prompt.strip() if translated_prompt else ""
    if not cleaned:
        raise ValueError("translated_prompt 가 비어 있습니다")

    return (
        f"{_MULTI_INPUT_GUIDANCE}\n"
        "Creative direction (optimized for gpt-image-1):\n"
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
    """ImageBackend 프로토콜 충족 — services/image_service.py 에서 호출됨."""

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
            )
        logo_bytes = Path(logo_path).read_bytes()
        
        final_prompt = build_multi_input_prompt(translated_prompt=request.prompt)

        # Multi-input 구성 (1:상품, 2:로고, 3:참조-선택사항)
        input_images = [
            ("product.png", request.image_data),
            ("logo.png", logo_bytes),
        ]
        
        # 만약 reference_image_paths가 있고, services/image_service가 
        # analyze_reference_composition을 위해 request.image_data를 참조 이미지로 
        # 이미 덮어썼다면, 실제로는 services/image_service에서 
        # 원본 상품 이미지를 잃어버릴 위험이 있음.
        # (현 시점 image_service.py 로직 상 resolve_reference_image_data가 
        #  image_data를 참조 이미지로 교체함)
        
        # [수정] 참조 이미지도 함께 전달 (3번째 인풋)
        if request.reference_image_paths:
            ref_path = Path(request.reference_image_paths[0])
            if ref_path.exists():
                input_images.append(("reference.png", ref_path.read_bytes()))

        png_bytes = self._client.edit_images(
            model=self.model,
            images=input_images,
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

"""Hugging Face Serverless Inference API 백엔드.

router.huggingface.co/hf-inference 라우터를 통해 원격으로 이미지를 생성한다.
설치된 로컬 diffusers 백엔드(hf_sd15 등)와 달리 모델 다운로드 없이 동작한다.

backends.image_base.ImageBackend 프로토콜 구현.

기존 services/image_service.py 의 _api_response() 를 이 모듈로 이동.
프롬프트 한국어→영문 번역은 ImageService 의 책임이며,
본 백엔드는 영문 프롬프트(request.prompt)를 그대로 HF API 에 전달한다.
"""

import logging

import httpx

from config.settings import Settings
from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)


class HFInferenceAPIBackend:
    """Hugging Face Serverless Inference API 백엔드."""

    name = "hf_inference_api"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_available(self) -> bool:
        """HF API 키가 설정되어 있는지 확인."""
        return self.settings.is_huggingface_ready

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """HF Inference API 호출 → 이미지 응답.

        request.prompt 는 영문으로 번역된 상태로 도착한다고 가정한다.
        예외는 백엔드에서 그대로 발생시키고, ImageService 가 사용자 친화적
        메시지로 래핑한다.
        """
        if not self.is_available():
            raise RuntimeError(
                "Hugging Face API 키가 설정되지 않았습니다. .env 의 HUGGINGFACE_API_KEY 를 확인하세요."
            )

        api_url = (
            f"https://router.huggingface.co/hf-inference/models/{self.settings.IMAGE_MODEL}"
        )
        headers = {"Authorization": f"Bearer {self.settings.HUGGINGFACE_API_KEY}"}
        payload = {"inputs": request.prompt}

        logger.info("HF 추론 API 호출 (url=%s)", api_url)
        response = httpx.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=self.settings.IMAGE_TIMEOUT,
        )
        response.raise_for_status()

        image_bytes = response.content
        if not image_bytes:
            raise RuntimeError("Hugging Face API 가 비어있는 이미지를 반환했습니다.")

        logger.info("HF 이미지 생성 완료 (size=%d bytes)", len(image_bytes))

        return ImageGenerationResponse(
            image_data=image_bytes,
            revised_prompt=request.prompt,
        )

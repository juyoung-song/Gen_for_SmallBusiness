"""원격 이미지 워커 백엔드.

자체 운영 워커(worker_api.py)를 호출해 이미지를 생성한다.
GCP VM 등에서 실행되는 별도의 FastAPI 워커가 ImageService 에 위임된 작업을 수행.

backends.image_base.ImageBackend 프로토콜 구현.

기존 services/image_service.py 의 _remote_response() 를 이 모듈로 이동.
프롬프트 번역은 ImageService 의 책임이며, 본 백엔드는 영문 프롬프트를
워커 페이로드에 그대로 담아 전달한다.
"""

import base64
import logging

import httpx

from config.settings import Settings
from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse

logger = logging.getLogger(__name__)


class RemoteWorkerBackend:
    """원격 이미지 워커 호출 백엔드."""

    name = "remote_worker"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_available(self) -> bool:
        """워커 URL 및 인증 토큰이 설정되어 있는지 확인."""
        return self.settings.is_image_worker_ready

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """원격 워커에 페이로드 전송 → base64 응답 디코딩."""
        if not self.is_available():
            raise RuntimeError(
                "원격 이미지 워커 설정이 비어 있습니다. "
                ".env 의 IMAGE_WORKER_URL, IMAGE_WORKER_TOKEN 을 확인하세요."
            )

        api_url = f"{self.settings.IMAGE_WORKER_URL.rstrip('/')}/generate-image"
        headers = {"Authorization": f"Bearer {self.settings.IMAGE_WORKER_TOKEN}"}
        payload = {
            "prompt": request.prompt,
            "product_name": request.product_name,
            "description": request.description,
            "goal": request.goal,
            "style": request.style,
            "image_data_b64": (
                base64.b64encode(request.image_data).decode("utf-8")
                if request.image_data
                else None
            ),
        }

        logger.info("원격 워커 호출 (url=%s)", api_url)
        response = httpx.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=self.settings.IMAGE_WORKER_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        image_data_b64 = data.get("image_data_b64", "")
        if not image_data_b64:
            raise RuntimeError("원격 이미지 워커가 이미지를 반환하지 않았습니다.")

        logger.info("원격 워커 응답 수신")

        return ImageGenerationResponse(
            image_data=base64.b64decode(image_data_b64),
            revised_prompt=data.get("revised_prompt", ""),
        )

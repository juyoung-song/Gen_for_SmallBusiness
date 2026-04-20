"""이미지 생성 백엔드 프로토콜.

새 이미지 생성 백엔드는 이 프로토콜을 구현하면 된다.
ImageService는 백엔드를 직접 알지 않고, 본 프로토콜만 호출한다.

설계 원칙 (compass/context.md §4):
- 1 모듈 = 1 파일
- 백엔드는 자기 책임으로 모델 호출만 수행
- 프롬프트 번역 등 사전 처리는 ImageService가 담당
"""

from typing import Protocol, runtime_checkable

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse


@runtime_checkable
class ImageBackend(Protocol):
    """이미지 생성 백엔드 인터페이스.

    구현체는 다음 위치에 1파일 1모듈로 둔다:
        backends/hf_sd15.py        — Hugging Face Stable Diffusion 1.5
        backends/hf_flux.py        — Hugging Face FLUX
        backends/hf_ip_adapter.py  — SD 1.5 + IP-Adapter
        backends/nano_banana.py    — nano banana (외부 VM)
        backends/remote_worker.py  — 자체 원격 워커
        backends/mock_image.py     — Mock (Pillow 그라데이션)
    """

    name: str
    """백엔드 식별자. 로깅/디버깅용. (예: "hf_sd15", "mock_image")"""

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """광고 이미지를 생성하여 반환.

        구현 시 주의:
        - request.prompt 는 이미 영문으로 번역된 상태로 도착한다고 가정한다
          (한글→영문 번역은 ImageService가 사전에 수행).
        - request.image_data 는 참조 이미지 (옵션). 지원 안 하면 무시 가능.
        - 실패 시 예외 발생 가능. ImageService가 ImageServiceError로 래핑한다.
        """
        ...

    def is_available(self) -> bool:
        """백엔드 실행에 필요한 의존성/리소스가 모두 충족되는지 확인.

        - 의존 패키지가 import 가능한가
        - 모델 파일이 캐시에 있는가 (선택)
        - 외부 서비스 인증이 가능한가 (선택)
        """
        ...

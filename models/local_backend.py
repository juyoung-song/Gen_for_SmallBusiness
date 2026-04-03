"""로컬 이미지 생성 백엔드 프로토콜.

새 로컬 모델 추가 시 이 프로토콜을 구현하면 ImageService가 자동으로 인식합니다.
"""

from typing import Protocol, runtime_checkable

from schemas.image_schema import ImageGenerationRequest, ImageGenerationResponse


@runtime_checkable
class LocalImageBackend(Protocol):
    """로컬 diffusers 기반 이미지 생성 백엔드 인터페이스."""

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """프롬프트(+ 선택적 참조 이미지)로 광고 이미지를 생성."""
        ...

    def is_available(self) -> bool:
        """필수 패키지 및 모델 파일이 사용 가능한지 확인."""
        ...

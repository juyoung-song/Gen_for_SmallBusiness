"""텍스트 생성 백엔드 프로토콜.

새 텍스트 생성 백엔드는 이 프로토콜을 구현하면 된다.
TextService는 백엔드를 직접 알지 않고, 본 프로토콜만 호출한다.

설계 원칙: backends/image_base.py 와 동일.
메서드명을 generate 로 통일하여 두 프로토콜의 일관성을 유지한다.
"""

from typing import Protocol, runtime_checkable

from schemas.text_schema import TextGenerationRequest, TextGenerationResponse


@runtime_checkable
class TextBackend(Protocol):
    """텍스트(광고 카피) 생성 백엔드 인터페이스.

    구현체는 다음 위치에 1파일 1모듈로 둔다:
        backends/openai_gpt.py     — OpenAI GPT
        backends/mock_text.py      — Mock 응답
    """

    name: str
    """백엔드 식별자. 로깅/디버깅용. (예: "openai_gpt", "mock_text")"""

    def generate(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """광고 카피 + 홍보 문장 + 스토리 카피를 생성하여 반환.

        구현 시 주의:
        - 응답은 ad_copies/promo_sentences/story_copies 모두 채워서 반환.
        - 실패 시 예외 발생 가능. TextService가 TextServiceError로 래핑한다.
        """
        ...

    def is_available(self) -> bool:
        """백엔드 실행에 필요한 의존성/리소스가 모두 충족되는지 확인."""
        ...

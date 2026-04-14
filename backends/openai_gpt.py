"""OpenAI GPT 텍스트 생성 백엔드.

광고 카피 + 홍보 문장 + 스토리 카피를 생성한다.
backends.text_base.TextBackend 프로토콜 구현.

기존 services/text_service.py 의 _api_response() 와 _parse_response() 를
이 모듈로 이동·정리한 것. 서비스 레이어는 이 백엔드를 호출만 한다.
"""

import logging
import re

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from langfuse.openai import OpenAI  # Langfuse auto-trace wrapper

from config.settings import Settings
from schemas.text_schema import TextGenerationRequest, TextGenerationResponse
from utils.prompt_builder import build_text_prompt

logger = logging.getLogger(__name__)


class OpenAIGPTBackend:
    """OpenAI GPT 기반 텍스트 생성 백엔드."""

    name = "openai_gpt"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """OpenAI 클라이언트 (lazy 초기화, 재사용)."""
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    def is_available(self) -> bool:
        """OpenAI API 키가 설정되어 있는지 확인."""
        return self.settings.is_api_ready

    def generate(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """OpenAI GPT 호출 → 광고 카피 응답.

        실패 시 백엔드에서는 예외를 그대로 발생시키고,
        TextService 가 사용자 친화적 메시지로 래핑한다.
        """
        if not self.is_available():
            raise RuntimeError(
                "OpenAI API 키가 설정되지 않았습니다. .env 의 OPENAI_API_KEY 를 확인하세요."
            )

        image_hint = (
            "상점에 상품 이미지가 업로드되었습니다. 그 분위기를 참고하세요."
            if request.image_data
            else None
        )

        system_prompt, user_prompt = build_text_prompt(
            product_name=request.product_name,
            description=request.description,
            style=request.style,
            goal=request.goal,
            image_hint=image_hint,
            brand_prompt=request.brand_prompt,
            is_new_product=request.is_new_product,
            reference_analysis=request.reference_analysis,
        )

        response = self.client.chat.completions.create(
            model=self.settings.TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=self.settings.TEXT_TIMEOUT,
        )

        raw_text = response.choices[0].message.content or ""
        logger.info(
            "OpenAI 응답 수신 (model=%s, length=%d, usage=%s)",
            response.model,
            len(raw_text),
            response.usage,
        )

        return self._parse_response(raw_text)

    @staticmethod
    def _parse_response(raw_text: str) -> TextGenerationResponse:
        """GPT 원시 응답을 TextGenerationResponse 로 파싱.

        섹션 헤더("광고 문구", "홍보 문장", "스토리 카피")를 기준으로 항목을 분류한다.
        파싱이 실패하면 폴백 메시지로 채운다.
        """
        logger.debug("Raw GPT output:\n%s", raw_text)

        ad_copies: list[str] = []
        promo_sentences: list[str] = []
        story_copies: list[str] = []
        current_section: str | None = None

        for line in raw_text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("```"):
                continue

            clean_line = re.sub(r"[*#]", "", line).strip()

            if "광고 문구" in clean_line:
                current_section = "ad_copies"
                continue
            if "홍보 문장" in clean_line:
                current_section = "promo_sentences"
                continue
            if "스토리 카피" in clean_line:
                current_section = "story_copies"
                continue

            parsed_text = re.sub(r"^(\d+[\.\)]\s*|-\s*)", "", clean_line).strip()
            if not parsed_text:
                continue

            if current_section == "ad_copies":
                ad_copies.append(parsed_text)
            elif current_section == "promo_sentences":
                promo_sentences.append(parsed_text)
            elif current_section == "story_copies":
                story_copies.append(parsed_text)

        if not ad_copies:
            ad_copies = [raw_text] if raw_text else ["생성 결과를 파싱할 수 없습니다."]
        if not promo_sentences:
            promo_sentences = ["(마크다운 구조 변경으로 홍보 문장 분리 실패)"]
        if not story_copies:
            story_copies = ["(스토리 카피 분리 실패)"]

        return TextGenerationResponse(
            ad_copies=ad_copies[:3],
            promo_sentences=promo_sentences[:2],
            story_copies=story_copies[:3],
        )

"""인스타그램용 캡션 및 해시태그 생성 서비스.

Stage 2 결정: 텍스트 백엔드는 무조건 OpenAI. Mock 분기는 폐지.
"""

import logging

from openai import OpenAI

from config.settings import Settings
from schemas.instagram_schema import CaptionGenerationRequest, CaptionGenerationResponse

logger = logging.getLogger(__name__)


class CaptionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    def generate_caption(
        self, request: CaptionGenerationRequest
    ) -> CaptionGenerationResponse:
        """인스타그램 본문 + 해시태그 생성 (OpenAI chat completions)."""
        logger.info("GPT를 이용해 인스타그램 캡션과 해시태그 생성 중...")

        system_prompt = (
            "당신은 인스타그램 전문 SNS 마케터입니다. 생성된 광고 문구들을 활용하여 1개의 매력적인 인스타그램 본문(캡션)과 "
            "해당 상품에 어울리는 최적의 해시태그 5~10개를 생성해주세요. "
            "응답은 반드시 아래 형식을 지켜주세요.\n\n"
            "[본문]\n(여기에 줄바꿈과 이모지를 듬뿍 활용한 SNS 감성 본문 작성)\n\n"
            "[해시태그]\n#해시태그1 #해시태그2"
        )
        user_prompt = (
            f"상품명: {request.product_name}\n"
            f"광고 스타일: {request.style}\n"
            f"참고용 광고 문구들: {', '.join(request.ad_copies)}"
        )

        response = self.client.chat.completions.create(
            model=self.settings.TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=self.settings.TEXT_TIMEOUT,
        )

        result_text = response.choices[0].message.content.strip()

        # 텍스트 파싱
        parts = result_text.split("[해시태그]")
        caption = parts[0].replace("[본문]", "").strip()
        hashtags = parts[1].strip() if len(parts) > 1 else "#추천 #인스타그램"

        return CaptionGenerationResponse(caption=caption, hashtags=hashtags)

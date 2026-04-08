"""인스타그램용 캡션 및 해시태그 생성 서비스."""

import logging

from openai import OpenAI

from config.settings import Settings
from schemas.instagram_schema import CaptionGenerationRequest, CaptionGenerationResponse

logger = logging.getLogger(__name__)


# 스타일별 Mock 캡션 템플릿 (USE_MOCK=True 일 때 사용)
_MOCK_CAPTIONS: dict[str, str] = {
    "기본": (
        "{name} ✨\n\n"
        "오늘도 당신에게 특별한 하루를 선물합니다.\n"
        "지금 만나보세요 💫"
    ),
    "감성": (
        "{name} 🌸\n\n"
        "일상에 스며드는 작은 행복.\n"
        "따뜻한 순간을 {name} 과 함께 해보세요 ☕"
    ),
    "고급": (
        "{name} 👑\n\n"
        "품격이 다른 선택.\n"
        "진정한 프리미엄을 경험해보세요 ✦"
    ),
    "유머": (
        "{name} 😄\n\n"
        "한번 맛보면 빠져나올 수 없어요!\n"
        "이 기회 놓치지 마세요 🔥"
    ),
    "심플": (
        "{name}.\n\n"
        "군더더기 없이, 핵심만.\n"
        "지금 확인하세요."
    ),
}


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
        """인스타그램 본문 + 해시태그 생성.

        USE_MOCK=True → 스타일별 하드코딩 응답 (I-2 수정).
        USE_MOCK=False → OpenAI chat completions 호출.
        """
        if self.settings.USE_MOCK:
            return self._mock_response(request)
        return self._api_response(request)

    # ──────────────────────────────────────────
    # Mock 응답 (I-2)
    # ──────────────────────────────────────────
    def _mock_response(
        self, request: CaptionGenerationRequest
    ) -> CaptionGenerationResponse:
        """Mock 모드에서 외부 호출 없이 하드코딩 캡션 반환."""
        template = _MOCK_CAPTIONS.get(request.style, _MOCK_CAPTIONS["기본"])
        caption = template.format(name=request.product_name)
        hashtags = f"#{request.product_name.replace(' ', '')} #추천 #오늘의한끼 #감성스타그램 #맛스타그램"
        return CaptionGenerationResponse(caption=caption, hashtags=hashtags)

    # ──────────────────────────────────────────
    # OpenAI 호출
    # ──────────────────────────────────────────
    def _api_response(
        self, request: CaptionGenerationRequest
    ) -> CaptionGenerationResponse:
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

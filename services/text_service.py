"""광고 문구 생성 서비스.

architecture.md 4.2 기준:
- 광고 문구 생성 비즈니스 로직
- Mock 모드 / API 모드 분기
- PromptBuilder로 프롬프트 생성 → OpenAI API 호출

architecture.md 6장 전환 전략:
- USE_MOCK=true → _mock_response() (하드코딩)
- USE_MOCK=false → _api_response() (OpenAI GPT 호출)
"""

import logging

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

from config.settings import Settings
from schemas.text_schema import TextGenerationRequest, TextGenerationResponse
from utils.prompt_builder import build_text_prompt

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 커스텀 예외
# ──────────────────────────────────────────────
class TextServiceError(Exception):
    """텍스트 서비스 에러. UI에 전달할 사용자 친화적 메시지를 담는다."""


# ──────────────────────────────────────────────
# 스타일별 Mock 응답 데이터
# ──────────────────────────────────────────────
_MOCK_DATA: dict[str, dict[str, list[str]]] = {
    "기본": {
        "ad_copies": [
            "✨ {name}, 당신의 일상에 특별함을 더하다",
            "🎯 {name}, 믿을 수 있는 품질의 시작",
            "💡 오늘부터 {name}과 함께하세요",
        ],
        "promo_sentences": [
            "{name} — {desc}. 합리적인 가격으로 최고의 품질을 경험하세요. "
            "지금 바로 만나보세요!",
            "매일 쓰는 것이니까, 좋은 것으로. {name}이 당신의 선택을 도와드립니다. "
        ],
        "story_copies": [
            "오늘의 선택, {name} ✨",
            "지금 만나러 갑니다 🎯",
            "일상의 완성을 위해 💡"
        ]
    },
    "감성": {
        "ad_copies": [
            "🌸 {name}, 작은 행복이 피어나는 순간",
            "☕ 당신만을 위한 따뜻한 선물, {name}",
            "🌿 일상에 스며드는 {name}의 감동",
        ],
        "promo_sentences": [
            "바쁜 하루 끝, {name}이 전하는 작은 위로. {desc}. "
            "당신의 소중한 시간을 더 특별하게 만들어 드립니다.",
            "좋아하는 것들로 채워가는 나만의 시간. "
            "{name}과 함께라면 평범한 오늘도 특별해집니다. 💕",
        ],
        "story_copies": [
            "당신의 오늘을 응원해요 🌸",
            "따뜻한 {name} 한 잔 ☕",
            "감성을 채우는 시간 🌿"
        ]
    },
    "고급": {
        "ad_copies": [
            "👑 {name}, 프리미엄의 새로운 기준",
            "✦ 품격이 다른 선택, {name}",
            "💎 {name}, 당신의 격을 높이다",
        ],
        "promo_sentences": [
            "{name} — {desc}. 진정한 프리미엄이란 디테일에서 완성됩니다. "
            "특별한 당신을 위한 최상의 선택.",
            "타협 없는 품질, 흔들리지 않는 가치. "
            "{name}이 선사하는 프리미엄 경험을 지금 만나보세요.",
        ],
        "story_copies": [
            "품격의 차이, {name} 👑",
            "당신을 위한 프레스티지 ✦",
            "오직 단 하나, 프리미엄 💎"
        ]
    },
    "유머": {
        "ad_copies": [
            "😄 {name} 없이 어떻게 살았지?!",
            "🤩 이건 사는 게 아니라 '득템'이에요, {name}!",
            "🔥 {name}, 한번 쓰면 못 끊는 그 맛!",
        ],
        "promo_sentences": [
            "친구한테 자랑하고 싶은 {name}! {desc}. "
            "이 가격에 이 퀄리티? 의심하지 마세요, 진짜입니다! 😲",
            "장바구니에 넣어만 둔 당신, 이제 결제 버튼을 누를 때입니다! "
            "{name}, 후회는 안 산 사람만 합니다! 🛒",
        ],
        "story_copies": [
            "일단 한 번 잡솨봐 😄",
            "지갑 조심하세요! 🤩",
            "오늘만 이 가격 🔥"
        ]
    },
    "심플": {
        "ad_copies": [
            "{name}. 깔끔하게, 확실하게.",
            "{name}. 딱 이거면 충분합니다.",
            "{name}. 본질에 집중합니다.",
        ],
        "promo_sentences": [
            "{name}. {desc}. 군더더기 없이, 핵심만 담았습니다.",
            "필요한 건 {name} 하나면 됩니다. 지금 확인하세요.",
        ],
        "story_copies": [
            "심플함의 끝, {name}",
            "이거면 충분합니다",
            "확실한 선택, {name}"
        ]
    },
}


class TextService:
    """광고 문구 생성 서비스.

    settings.USE_MOCK 값에 따라 Mock/API를 자동 전환합니다.
    OpenAI 클라이언트는 API 모드에서 1회만 생성하여 재사용합니다.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """OpenAI 클라이언트 (lazy 초기화, 재사용)."""
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    async def generate_ad_copy(
        self, request: TextGenerationRequest
    ) -> TextGenerationResponse:
        """광고 문구를 생성하여 반환."""
        if self.settings.USE_MOCK:
            logger.info("Mock 모드: 하드코딩 응답 반환 (product=%s)", request.product_name)
            return self._mock_response(request)

        logger.info("API 모드: OpenAI GPT 호출 (product=%s, model=%s)",
                     request.product_name, self.settings.TEXT_MODEL)
        return await self._api_response(request)

    # ──────────────────────────────────────────
    # Mock 응답
    # ──────────────────────────────────────────
    def _mock_response(
        self, request: TextGenerationRequest
    ) -> TextGenerationResponse:
        """스타일별 하드코딩 Mock 응답을 반환."""
        style = request.style if request.style in _MOCK_DATA else "기본"
        template = _MOCK_DATA[style]

        desc = request.description if request.description else "특별한 경험을 선사합니다"

        return TextGenerationResponse(
            ad_copies=[
                copy.format(name=request.product_name, desc=desc)
                for copy in template["ad_copies"]
            ],
            promo_sentences=[
                sentence.format(name=request.product_name, desc=desc)
                for sentence in template["promo_sentences"]
            ],
            story_copies=[
                story.format(name=request.product_name, desc=desc)
                for story in template["story_copies"]
            ],
        )

    # ──────────────────────────────────────────
    # OpenAI API 호출
    # ──────────────────────────────────────────
    async def _api_response(
        self, request: TextGenerationRequest
    ) -> TextGenerationResponse:
        """OpenAI GPT API를 호출하여 광고 문구를 생성."""
        if not self.settings.is_api_ready:
            raise TextServiceError(
                "OpenAI API 키가 설정되지 않았습니다. "
                ".env 파일에서 OPENAI_API_KEY를 설정해주세요."
            )

        # 파일 힌트 생성
        image_hint = "상점에 상품 이미지가 업로드되었습니다. 그 분위기를 참고하세요." if request.image_data else None

        # 브랜드 설정 로드
        from services.brand_service import BrandService
        brand_service = BrandService()
        brand_config = await brand_service.get_brand_config()
        brand_context = brand_config.model_dump() if brand_config else None

        system_prompt, user_prompt = build_text_prompt(
            product_name=request.product_name,
            description=request.description,
            style=request.style,
            goal=request.goal,
            image_hint=image_hint,
            brand_context=brand_context
        )

        try:
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

        except AuthenticationError:
            logger.error("OpenAI 인증 실패 — API 키를 확인하세요")
            raise TextServiceError(
                "OpenAI API 키가 유효하지 않습니다. "
                ".env 파일의 OPENAI_API_KEY를 확인해주세요."
            )
        except RateLimitError:
            logger.error("OpenAI API 요청 한도 초과")
            raise TextServiceError(
                "API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요. "
                "(과금 한도 또는 분당 요청 수 초과)"
            )
        except APITimeoutError:
            logger.error("OpenAI API 타임아웃 (%.0f초)", self.settings.TEXT_TIMEOUT)
            raise TextServiceError(
                f"API 응답 시간이 초과되었습니다 ({self.settings.TEXT_TIMEOUT:.0f}초). "
                "잠시 후 다시 시도해주세요."
            )
        except BadRequestError as e:
            logger.error("OpenAI 잘못된 요청: %s", e)
            raise TextServiceError(
                f"요청이 거부되었습니다: {e.message}"
            )
        except APIConnectionError:
            logger.error("OpenAI API 연결 실패")
            raise TextServiceError(
                "OpenAI 서버에 연결할 수 없습니다. 네트워크를 확인해주세요."
            )
        except Exception as e:
            logger.error("텍스트 생성 예외: %s", e)
            raise TextServiceError(f"문구 생성 중 오류가 발생했습니다: {e}")

    # ──────────────────────────────────────────
    # 응답 파싱
    # ──────────────────────────────────────────
    @staticmethod
    def _parse_response(raw_text: str) -> TextGenerationResponse:
        """GPT 원시 응답을 TextGenerationResponse로 파싱."""
        import re
        import logging
        logging.getLogger(__name__).debug("Raw GPT output:\n%s", raw_text)

        ad_copies: list[str] = []
        promo_sentences: list[str] = []
        story_copies: list[str] = []
        current_section: str | None = None

        for line in raw_text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("```"):
                continue

            clean_line = re.sub(r'[*#]', '', line).strip()

            if "광고 문구" in clean_line:
                current_section = "ad_copies"
                continue
            if "홍보 문장" in clean_line:
                current_section = "promo_sentences"
                continue
            if "스토리 카피" in clean_line:
                current_section = "story_copies"
                continue

            parsed_text = re.sub(r'^(\d+[\.\)]\s*|-\s*)', '', clean_line).strip()
            
            if not parsed_text:
                continue

            if current_section == "ad_copies":
                ad_copies.append(parsed_text)
            elif current_section == "promo_sentences":
                promo_sentences.append(parsed_text)
            elif current_section == "story_copies":
                story_copies.append(parsed_text)

        # 파싱 실패 시 폴백
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

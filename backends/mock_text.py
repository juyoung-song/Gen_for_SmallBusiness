"""Mock 텍스트 백엔드 — 스타일별 하드코딩 응답.

USE_MOCK 모드에서 OpenAI 호출 없이 빠르게 동작 검증을 가능케 한다.
스타일별로 미리 정의된 광고 카피/홍보 문장/스토리 카피를 반환한다.

backends.text_base.TextBackend 프로토콜 구현.

기존 services/text_service.py 의 _mock_response() 와 _MOCK_DATA 를
이 모듈로 이동.
"""

from schemas.text_schema import TextGenerationRequest, TextGenerationResponse

# 스타일별 Mock 응답 데이터
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
            "일상의 완성을 위해 💡",
        ],
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
            "감성을 채우는 시간 🌿",
        ],
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
            "오직 단 하나, 프리미엄 💎",
        ],
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
            "오늘만 이 가격 🔥",
        ],
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
            "확실한 선택, {name}",
        ],
    },
}


class MockTextBackend:
    """스타일별 하드코딩 텍스트 백엔드."""

    name = "mock_text"

    def __init__(self, settings=None) -> None:
        self.settings = settings  # 인터페이스 통일을 위해 받지만 사용 안 함

    def is_available(self) -> bool:
        return True

    def generate(self, request: TextGenerationRequest) -> TextGenerationResponse:
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

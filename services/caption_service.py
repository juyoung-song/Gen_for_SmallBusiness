"""인스타그램용 캡션 및 해시태그 생성 서비스."""
import logging

from openai import OpenAI

from config.settings import Settings
from schemas.instagram_schema import CaptionGenerationRequest, CaptionGenerationResponse

logger = logging.getLogger(__name__)


def _product_status_label(is_new_product: bool, is_renewal_product: bool) -> str:
    if is_new_product:
        return "신상품"
    if is_renewal_product:
        return "리뉴얼 상품"
    return "기존 상품"

class CaptionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    def generate_caption(self, request: CaptionGenerationRequest) -> CaptionGenerationResponse:
        logger.info("GPT를 이용해 인스타그램 캡션과 해시태그 생성 중...")

        product_status = _product_status_label(
            request.is_new_product,
            request.is_renewal_product,
        )
        philosophy_line = (
            f"브랜드 철학: {request.brand_philosophy}\n"
            if request.brand_philosophy
            else ""
        )
        description_line = (
            f"상품 설명: {request.description}\n"
            if request.description
            else ""
        )
        reference_line = (
            f"참고 이미지 분석 요약: {request.reference_analysis}\n"
            if request.reference_analysis
            else ""
        )

        system_prompt = (
            "당신은 인스타그램 전문 SNS 마케터입니다. 생성된 광고 문구들을 활용하여 1개의 매력적인 인스타그램 본문(캡션)과 "
            "해당 상품에 어울리는 최적의 해시태그 5~10개를 생성해주세요. "
            "브랜드 철학과 상품 상태가 주어지면 본문의 어조와 메시지에 자연스럽게 반영하세요. "
            "참고 이미지 분석 요약은 문체, 분위기, 단어 선택을 다듬는 참고 정보로만 사용하고, 새로운 사실 정보처럼 쓰지 마세요. "
            "본문의 내용은 반드시 상품명, 상품 설명, 상품 상태, 브랜드 철학, 참고용 광고 문구 등 명시적으로 주어진 사실에만 근거해 작성하세요. "
            "실제로 확인되지 않은 배경, 소품, 접시, 테이블, 조명, 공간, 사람의 행동, 맛의 세부 묘사, 장면 연출을 지어내지 마세요. "
            "본문은 제품 묘사만 나열하지 말고, 고객이 자기 일상에 대입해 상상할 수 있는 현실적인 예시 문장을 반드시 1개 포함하세요. "
            "그 예시 문장은 짧고 구체적이어야 하며, 과장 없이 여유로운 일상 톤을 유지해야 합니다. "
            "브랜드 철학이 있다면 그 철학이 고객 경험 장면에도 자연스럽게 드러나야 합니다. "
            "예시 문장은 정확히 1개만 넣고, 전체 본문과 자연스럽게 이어지게 작성하세요. "
            "본문은 3~4개의 짧은 문단으로 구성하고, 문맥이 달라질 때마다 한 줄씩 띄워 가독성을 확보하세요. "
            "각 문단은 1~2문장 정도로 간결하게 유지하세요. "
            "응답은 반드시 아래 형식을 지켜주세요.\n\n"
            "[본문]\n(여기에 문단 사이를 한 줄씩 띄운, 사실 기반의 SNS 본문 작성)\n\n"
            "[해시태그]\n#해시태그1 #해시태그2"
        )
        user_prompt = (
            f"상품명: {request.product_name}\n"
            f"{description_line}"
            f"상품 상태: {product_status}\n"
            f"{philosophy_line}"
            f"{reference_line}"
            f"광고 스타일: {request.style}\n"
            f"참고용 광고 문구들: {', '.join(request.ad_copies)}\n"
            "추가 요청: 고객이 '내 이야기 같다'고 느낄 수 있도록, 실제로 있을 법한 짧은 일상 장면 예시를 본문 안에 한 문장만 넣어주세요. "
            "그 예시도 반드시 주어진 사실 범위 안에서만 작성하고, 확인되지 않은 시각적 배경이나 소품을 붙이지 마세요."
        )

        response = self.client.chat.completions.create(
            model=self.settings.TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            timeout=self.settings.TEXT_TIMEOUT,
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # 텍스트 파싱
        parts = result_text.split("[해시태그]")
        caption = parts[0].replace("[본문]", "").strip()
        hashtags = parts[1].strip() if len(parts) > 1 else "#추천 #인스타그램"

        return CaptionGenerationResponse(caption=caption, hashtags=hashtags)

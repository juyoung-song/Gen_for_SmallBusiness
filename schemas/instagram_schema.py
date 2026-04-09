"""인스타그램 캡션 및 업로드 관련 스키마.

Loah 프롬프트 이식 — CaptionGenerationRequest 에 brand_prompt, description,
is_new_product, reference_analysis 필드 추가.
"""

from pydantic import BaseModel


class CaptionGenerationRequest(BaseModel):
    product_name: str
    description: str = ""
    ad_copies: list[str]
    style: str
    brand_prompt: str = ""           # 온보딩에서 생성한 브랜드 가이드라인
    is_new_product: bool = False     # 신상품 토글 상태
    reference_analysis: str = ""     # 참조 이미지 분석 텍스트 (DB 에서 가져옴)


class CaptionGenerationResponse(BaseModel):
    caption: str
    hashtags: str

"""인스타그램 캡션 및 업로드 관련 스키마.

Loah 프롬프트 이식 — CaptionGenerationRequest 에 brand_prompt, description,
is_new_product, reference_analysis 필드 추가.

OAuth 이식 — InstagramConnectionResponse / InstagramAccountInfo 신규 추가.
(song/main-fix-insta 에서 append; won 의 Loah 필드는 그대로 보존)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

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


# ── Instagram OAuth 연결 스키마 (신규) ──


class InstagramConnectionResponse(BaseModel):
    """인스타그램 연결 상태 응답 스키마."""

    id: UUID
    brand_id: UUID
    facebook_page_name: Optional[str] = None
    is_active: bool
    token_expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class InstagramAccountInfo(BaseModel):
    """Meta API에서 조회한 인스타그램 계정 정보."""

    instagram_account_id: str
    instagram_username: str = ""
    facebook_page_id: str = ""
    facebook_page_name: str = ""

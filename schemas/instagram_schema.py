"""인스타그램 캡션 및 업로드 관련 스키마."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CaptionGenerationRequest(BaseModel):
    product_name: str
    ad_copies: list[str]
    style: str

class CaptionGenerationResponse(BaseModel):
    caption: str
    hashtags: str


# ── Instagram OAuth 연결 스키마 (신규) ──

class InstagramConnectionResponse(BaseModel):
    """인스타그램 연결 상태 응답 스키마."""

    id: UUID
    brand_config_id: UUID
    instagram_account_id: str
    instagram_username: Optional[str] = None
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

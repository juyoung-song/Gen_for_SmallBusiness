"""브랜드 온보딩 설정을 위한 Pydantic 스키마 정의."""

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class BrandConfigBase(BaseModel):
    """공통 브랜드 베이스."""
    brand_name: str
    brand_color: Optional[str] = None
    brand_logo_path: Optional[str] = None
    atmosphere: Optional[str] = None
    global_style_prompt: Optional[str] = None
    reference_context: Optional[str] = None


class BrandConfigCreate(BrandConfigBase):
    """온보딩 시 생성을 위한 요청 스키마."""
    pass


class BrandConfigUpdate(BaseModel):
    """설정 수정을 위한 데이터 정의."""
    brand_name: Optional[str] = None
    brand_color: Optional[str] = None
    brand_logo_path: Optional[str] = None
    atmosphere: Optional[str] = None
    global_style_prompt: Optional[str] = None
    reference_context: Optional[str] = None


class BrandConfigResponse(BrandConfigBase):
    """클라이언트에 반환할 응답 스키마."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

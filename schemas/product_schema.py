"""상품 자산 관리를 위한 Pydantic 스키마 정의."""

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ProductBase(BaseModel):
    """공통 상품 정보."""
    name: str
    description: Optional[str] = None
    representative_image_path: str


class ProductCreate(ProductBase):
    """신상품 등록을 위한 요청 스키마."""
    pass


class ProductUpdate(BaseModel):
    """상품 정보 수정을 위한 데이터 정의."""
    name: Optional[str] = None
    description: Optional[str] = None
    representative_image_path: Optional[str] = None


class ProductResponse(ProductBase):
    """클라이언트에 반환할 응답 스키마."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

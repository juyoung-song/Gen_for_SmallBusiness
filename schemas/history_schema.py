"""히스토리 생성 및 조회를 위한 검증 스키마."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from models.history import GenerationType


class HistoryCreate(BaseModel):
    """새로운 히스토리 레코드를 생성할 때 필요한 스키마."""
    generation_type: GenerationType
    product_name: str
    description: str | None = None
    style: str
    result_data: dict[str, Any]


class HistoryResponse(BaseModel):
    """조회 시 반환되는 히스토리 스키마."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    generation_type: GenerationType
    product_name: str
    description: str | None
    style: str
    result_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime

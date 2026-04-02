"""광고 콘텐츠 생성 히스토리 저장을 위한 ORM 모델 정의.
- PK는 규칙에 따라 Uuid 사용.
"""

import enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class GenerationType(str, enum.Enum):
    """생성 콘텐츠 타입 Enum."""
    TEXT = "text"
    IMAGE = "image"
    COMBINED = "combined"


class History(Base, TimestampMixin):
    """광고 생성 이력 모델."""
    __tablename__ = "histories"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    generation_type: Mapped[GenerationType] = mapped_column(
        Enum(GenerationType, native_enum=False), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    style: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # 텍스트 결과(사전) 또는 이미지 URL 경로 등의 결과물을 모두 수용
    result_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

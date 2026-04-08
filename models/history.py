"""광고 콘텐츠 생성 히스토리 저장을 위한 ORM 모델 정의 (LEGACY).

⚠️ LEGACY — Phase 2 종료 시 제거 예정.

본 모델은 Step 1.2 에서 brand_image / product / generated_upload 3종으로 대체되었다.
신규 코드는 본 모델을 사용해서는 안 되며, 기존 사용처(services/history_service.py,
schemas/history_schema.py, app.py)는 Phase 1.3 / Phase 2 에서 점진적으로 마이그레이션된다.

새로운 코드는 다음을 사용한다:
- `models.brand_image.BrandImage` — 브랜드 정체성 (불변)
- `models.product.Product` — 상품 raw 이미지
- `models.generated_upload.GeneratedUpload` — 생성 결과 + 인스타 메타
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

"""Generation ORM 모델.

docs/schema.md §3.3 기준:
- 상품 1건 → 게시글 1건(이미지 1장 + 텍스트 세트) 단위의 생성 이벤트.
- Langfuse trace 연결 키(langfuse_trace_id)로 프롬프트·모델·토큰 추적.
- brand/reference 스냅샷은 저장하지 않음 (brand 불변 + reference 재분석 드묾).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_image_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("reference_images.id", ondelete="SET NULL"), nullable=True, default=None
    )

    # 상품 입력
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    product_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    goal: Mapped[str] = mapped_column(String(64), nullable=False)
    tone: Mapped[str] = mapped_column(String(64), nullable=False)
    is_new_product: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # 추적 & 에러
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    brand: Mapped["Brand"] = relationship(back_populates="generations")  # noqa: F821
    reference_image: Mapped["ReferenceImage | None"] = relationship(  # noqa: F821
        back_populates="generations"
    )
    outputs: Mapped[list["GenerationOutput"]] = relationship(  # noqa: F821
        back_populates="generation", cascade="all, delete-orphan"
    )

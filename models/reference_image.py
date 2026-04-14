"""ReferenceImage ORM 모델.

docs/schema.md §3.2 기준:
- 구도 전용 참조 이미지. 브랜드 톤 주입 금지.
- color/mood/tone 컬럼은 의도적으로 누락 (원칙 #3 방어선).
- 현재 MVP 는 '기존 게시물만 참조' 정책이므로 source_output_id (GenerationOutput FK) 를
  UNIQUE 로 걸어 같은 게시물 이미지는 하나의 reference_images 레코드로 재사용.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class ReferenceImage(Base):
    __tablename__ = "reference_images"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 참조 원천 — 기존 게시물의 GenerationOutput(kind=image). UNIQUE 로 재사용 보장.
    source_output_id: Mapped[UUID] = mapped_column(
        ForeignKey("generation_outputs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    path: Mapped[str] = mapped_column(String(512), nullable=False)
    composition_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brand: Mapped["Brand"] = relationship(back_populates="reference_images")  # noqa: F821
    generations: Mapped[list["Generation"]] = relationship(  # noqa: F821
        back_populates="reference_image"
    )

"""GenerationOutput ORM 모델.

docs/schema.md §3.4 기준:
- 한 Generation 의 산출물 (이미지 1장 + 광고문구 3 + 홍보문장 2 + 스토리 카피 3 등).
- kind: image / ad_copy / promo_sentence / story_copy / caption / hashtags
- 이미지면 content_path, 텍스트면 content_text.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class GenerationOutput(Base):
    __tablename__ = "generation_outputs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    generation_id: Mapped[UUID] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    content_path: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    generation: Mapped["Generation"] = relationship(back_populates="outputs")  # noqa: F821
    uploads: Mapped[list["GeneratedUpload"]] = relationship(  # noqa: F821
        back_populates="generation_output", cascade="all, delete-orphan"
    )

"""GeneratedUpload ORM 모델.

design.md §2.2 / §5 기준:
- 시스템이 생성해서 인스타에 게시한 결과물 ("화장 후")
- product 에 belongsTo (FK)
- 인스타 게시 후에만 instagram_post_id / posted_at 이 채워진다 (nullable)
- goal_category 는 칩 6종 중 하나, goal_freeform 은 자유 텍스트 보강
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class GeneratedUpload(Base, TimestampMixin):
    """생성 결과 + 인스타 게시 메타데이터."""

    __tablename__ = "generated_uploads"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    goal_category: Mapped[str] = mapped_column(String(64), nullable=False)
    goal_freeform: Mapped[str] = mapped_column(Text, nullable=False, default="")
    instagram_post_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    product: Mapped["Product"] = relationship(  # noqa: F821
        back_populates="uploads"
    )

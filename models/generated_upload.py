"""GeneratedUpload ORM 모델.

docs/schema.md §3.5 기준:
- 인스타 게시 이력. GenerationOutput(kind=image) 에 걸림.
- 한 이미지가 feed + story 로 각각 업로드될 수 있으므로 1:N.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class GeneratedUpload(Base):
    __tablename__ = "generated_uploads"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    generation_output_id: Mapped[UUID] = mapped_column(
        ForeignKey("generation_outputs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "feed" | "story"
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    instagram_post_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    generation_output: Mapped["GenerationOutput"] = relationship(  # noqa: F821
        back_populates="uploads"
    )

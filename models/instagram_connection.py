"""InstagramConnection ORM 모델.

docs/schema.md §3.5 기준:
- Meta OAuth 토큰 전용 테이블. brands 는 불변(원칙 #4)이라 가변 데이터를 분리.
- 1 Brand : 1 Connection (UNIQUE(brand_id)).
- access_token 은 Fernet 암호화 저장.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class InstagramConnection(Base, TimestampMixin):
    __tablename__ = "instagram_connections"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    brand_id: Mapped[UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    access_token: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet 암호문
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, default="long_lived")
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    facebook_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    facebook_page_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    brand: Mapped["Brand"] = relationship()  # noqa: F821

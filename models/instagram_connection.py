"""사용자별 인스타그램 OAuth 연결 정보 모델."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class InstagramConnection(Base, TimestampMixin):
    """브랜드별 인스타그램 OAuth 연결 정보.

    현재 모바일 앱은 브랜드 온보딩 결과물(BrandImage)을 사실상 사용자 식별자로 사용한다.
    """

    __tablename__ = "instagram_connections"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    brand_image_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, unique=True, index=True
    )

    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(20), default="long_lived")
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    instagram_account_id: Mapped[str] = mapped_column(String(50), nullable=False)
    instagram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    facebook_page_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    facebook_page_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

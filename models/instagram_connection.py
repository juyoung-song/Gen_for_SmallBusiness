"""사용자별 인스타그램 OAuth 연결 정보 모델 정의."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class InstagramConnection(Base, TimestampMixin):
    """사용자별 인스타그램 OAuth 연결 정보.

    온보딩 완료된 brand_config와 1:1 매핑되며,
    Meta OAuth를 통해 발급받은 토큰과 계정 정보를 저장합니다.
    """

    __tablename__ = "instagram_connections"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    # brand_config와 1:1 매핑 (현재 사용자 식별자)
    brand_config_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, unique=True
    )

    # ── Meta OAuth 토큰 (암호화 저장) ──
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(
        String(20), default="long_lived"
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Instagram 계정 정보 ──
    instagram_account_id: Mapped[str] = mapped_column(String(50), nullable=False)
    instagram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    facebook_page_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    facebook_page_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # ── 연결 상태 ──
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

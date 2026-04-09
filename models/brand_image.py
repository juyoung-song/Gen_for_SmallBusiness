"""BrandImage ORM 모델.

design.md §2.3 기준:
- 온보딩 1회 생성되는 불변 레코드
- content 는 GPT 가 정제한 시스템 프롬프트 역할 텍스트
- source_* 필드는 생성 근거 (사용자 원본 입력 + 레퍼런스 링크 + 캡처 경로)
- 단일 사용자 MVP 이지만 향후 멀티테넌트 확장을 막지 않도록 user_id 를 둔다
"""

from uuid import UUID, uuid4

from sqlalchemy import JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class BrandImage(Base, TimestampMixin):
    """브랜드 정체성 (system prompt 역할, 불변)."""

    __tablename__ = "brand_images"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_freetext: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_screenshots: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, default=list
    )

    # Song 이식 — 구조화된 브랜드 기본 정보 (nullable, 기존 레코드 호환)
    brand_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    brand_color: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    # M3 fix — 이전엔 온보딩 입력의 brand_atmosphere 가 Vision freetext 로만
    # 머지되고 독립 컬럼으로는 저장되지 않아 재진입 시 사라졌다.
    brand_atmosphere: Mapped[str | None] = mapped_column(
        String(200), nullable=True, default=None
    )
    brand_logo_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None
    )

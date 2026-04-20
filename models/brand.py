"""Brand ORM 모델.

docs/schema.md §3.1 기준:
- 온보딩 산출물. 이름/로고/컬러 + 스타일 입력·분석 결과를 1:1 로 흡수.
- 불변: updated_at 컬럼 없음. 서비스 레이어도 update() 미제공.
- instagram_account_id 는 온보딩 시 NULL, 인스타 연결 후 채워짐.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    # 인스타 연결 (온보딩 시엔 NULL)
    instagram_account_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, default=None
    )
    instagram_username: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )

    # 브랜드 아이덴티티
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    logo_path: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)

    # 스타일 입력 (온보딩 재분석 시 갱신 가능)
    input_instagram_url: Mapped[str] = mapped_column(Text, nullable=False)
    input_description: Mapped[str] = mapped_column(Text, nullable=False)
    input_mood: Mapped[str] = mapped_column(Text, nullable=False)

    # 스타일 분석 결과 (온보딩 재분석 시 갱신 가능)
    style_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    reference_images: Mapped[list["ReferenceImage"]] = relationship(  # noqa: F821
        back_populates="brand", cascade="all, delete-orphan"
    )
    generations: Mapped[list["Generation"]] = relationship(  # noqa: F821
        back_populates="brand", cascade="all, delete-orphan"
    )

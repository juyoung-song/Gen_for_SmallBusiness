"""브랜드 온보딩 설정 정보 모델 정의."""

from uuid import UUID, uuid4
from sqlalchemy import String, Uuid, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class BrandConfig(Base, TimestampMixin):
    """브랜드 온보딩 설정 정보 모델.
    
    최초 1회 온보딩 시 생성되며, 모든 광고 콘텐츠 생성의 
    '고정 스타일(Global Style Prompt)'의 기초가 됩니다.
    """
    __tablename__ = "brand_configs"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    # 브랜드 기본 정보
    brand_name: Mapped[str] = mapped_column(String(100), nullable=False)
    brand_color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    brand_logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    atmosphere: Mapped[str | None] = mapped_column(String(200), nullable=True)
    
    # [핵심] 온보딩 시 분석된 브랜드 고정 스타일 프롬프트 (피드 일관성 제어용)
    global_style_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # 분석에 사용된 레퍼런스 정보 (이미지 경로 또는 인스타 링크)
    reference_context: Mapped[str | None] = mapped_column(Text, nullable=True)

"""SQLAlchemy 공통 Base 모델 데이터 정의.
- 모든 모델은 TimestampMixin을 상속받도록 규칙(user_global) 준수.
"""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 선언적 매핑 베이스 클래스."""
    pass


class TimestampMixin:
    """공통 타임스탬프 속성 (생성일, 수정일)."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False
    )

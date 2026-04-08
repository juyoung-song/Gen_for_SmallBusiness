"""Product ORM 모델.

design.md §2.2 / §5 기준:
- 상품(raw 이미지 = "화장 전")
- name 은 인덱스만 두고 unique 강제하지 않는다 (소상공인이 동일 명칭으로
  여러 변형을 등록할 수 있어 자유도 우선)
- description 은 텍스트 생성 단계의 컨텍스트에 함께 들어가는 필수 필드
- raw_image_path 는 staging/permanent 경로 모두 수용
"""

from uuid import UUID, uuid4

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    """상품 (화장 전 raw 이미지)."""

    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_image_path: Mapped[str] = mapped_column(String(512), nullable=False)

    uploads: Mapped[list["GeneratedUpload"]] = relationship(  # noqa: F821
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

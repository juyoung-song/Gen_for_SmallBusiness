"""상품별 대표 이미지와 정보를 관리하는 모델 정의."""

from uuid import UUID, uuid4
from sqlalchemy import String, Uuid, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    """상품별 대표 이미지 관리 모델.
    
    신상품 등록 시 대표 이미지로 지정된 파일은 DB에 영구 저장되어
    이후 기존 상품 모드에서 해당 상품의 광고 생성 시 
    이미지 베이스로 사용됩니다.
    """
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    # 상품 기본 정보 (이름은 고유해야 함)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    
    # 해당 상품의 원본(Raw) 대표 이미지 로컬 파일 경로
    representative_image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # 추후 확장용: 브랜드와의 결합 정보 (선택)
    brand_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

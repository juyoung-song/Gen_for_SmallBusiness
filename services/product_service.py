"""Product CRUD 서비스.

design.md §4.1 의 입력 폼이 사용한다:
- 신상품 토글 ON 시 → create()
- 기존 상품 드롭다운 → list_all() / get(id)
- 이름 매칭 → find_by_name()
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.product import Product


class ProductService:
    """Product CRUD 서비스."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        name: str,
        description: str,
        raw_image_path: str,
    ) -> Product:
        """신상품 등록."""
        product = Product(
            name=name,
            description=description,
            raw_image_path=raw_image_path,
        )
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def get(self, product_id: UUID) -> Product | None:
        """ID 단일 조회. 없으면 None."""
        return await self.session.get(Product, product_id)

    async def list_all(self) -> list[Product]:
        """전체 상품 조회 (드롭다운/갤러리용)."""
        result = await self.session.execute(select(Product).order_by(Product.created_at))
        return list(result.scalars().all())

    async def find_by_name(self, name: str) -> list[Product]:
        """이름 정확 매칭. Product.name 은 unique 가 아니므로 리스트 반환."""
        result = await self.session.execute(
            select(Product).where(Product.name == name).order_by(Product.created_at)
        )
        return list(result.scalars().all())

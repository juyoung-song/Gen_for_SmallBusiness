"""상품 및 대표 이미지를 관리하는 서비스 레이어."""

import os
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.product import Product
from schemas.product_schema import ProductCreate, ProductResponse, ProductUpdate


class ProductService:
    """상품 자산(대표 이미지)을 관리하는 서비스 클래스."""

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        self.db = db

    async def register_product(self, create_data: ProductCreate) -> ProductResponse:
        """새 상품을 등록하고 대표 이미지를 저장."""
        if self.db:
            return await self._register_impl(self.db, create_data)
        
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._register_impl(session, create_data)

    async def _register_impl(self, session: AsyncSession, create_data: ProductCreate) -> ProductResponse:
        """상품 등록 트랜잭션."""
        try:
            # 기존 동일 이름 상품 체크 (업데이트로 처리 가능하지만 여기선 신규 등록 기준)
            query = select(Product).where(Product.name == create_data.name)
            result = await session.execute(query)
            existing = result.scalar_one_or_none()
            
            if existing:
                # 수정 로직으로 위임하거나 에러
                for field, value in create_data.model_dump().items():
                    setattr(existing, field, value)
                product = existing
            else:
                product = Product(
                    name=create_data.name,
                    description=create_data.description,
                    representative_image_path=create_data.representative_image_path,
                )
                session.add(product)
            
            await session.commit()
            await session.refresh(product)
            return ProductResponse.model_validate(product)
        except Exception:
            await session.rollback()
            raise

    async def get_product_by_name(self, name: str) -> Optional[ProductResponse]:
        """상품명으로 상품 정보를 조회하여 대표 이미지를 로드."""
        if self.db:
            return await self._get_by_name_impl(self.db, name)
        
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._get_by_name_impl(session, name)

    async def _get_by_name_impl(self, session: AsyncSession, name: str) -> Optional[ProductResponse]:
        """조회 쿼리 수행."""
        query = select(Product).where(Product.name == name)
        result = await session.execute(query)
        product = result.scalar_one_or_none()
        if product:
            return ProductResponse.model_validate(product)
        return None

    async def get_all_products(self) -> List[ProductResponse]:
        """등록된 모든 상품 목록을 조회 (드롭다운 용)."""
        if self.db:
            return await self._get_all_impl(self.db)
        
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._get_all_impl(session)

    async def _get_all_impl(self, session: AsyncSession) -> List[ProductResponse]:
        """목록 조회 쿼리 수행."""
        query = select(Product).order_by(Product.name.asc())
        result = await session.execute(query)
        products = result.scalars().all()
        return [ProductResponse.model_validate(p) for p in products]

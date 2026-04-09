"""브랜드 설정을 관리하는 서비스 레이어."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.brand import BrandConfig
from schemas.brand_schema import BrandConfigCreate, BrandConfigResponse, BrandConfigUpdate


class BrandService:
    """브랜드 온보딩 설정을 CRUD하는 서비스 클래스."""

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        self.db = db

    async def get_brand_config(self) -> Optional[BrandConfigResponse]:
        """현재 저장된 브랜드 설정을 상세 조회하며 없으면 None 반환."""
        if self.db:
            return await self._get_impl(self.db)
        
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._get_impl(session)

    async def _get_impl(self, session: AsyncSession) -> Optional[BrandConfigResponse]:
        """브랜드 설정 레코드를 조회 (최초 1개 가정)."""
        query = select(BrandConfig).limit(1)
        result = await session.execute(query)
        brand = result.scalar_one_or_none()
        if brand:
            return BrandConfigResponse.model_validate(brand)
        return None

    async def save_brand_config(self, create_data: BrandConfigCreate) -> BrandConfigResponse:
        """새 브랜드 설정을 DB에 저장."""
        if self.db:
            return await self._save_impl(self.db, create_data)
        
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._save_impl(session, create_data)

    async def _save_impl(self, session: AsyncSession, create_data: BrandConfigCreate) -> BrandConfigResponse:
        """실제 저장 트랜잭션 관리."""
        try:
            brand = BrandConfig(
                brand_name=create_data.brand_name,
                brand_color=create_data.brand_color,
                brand_logo_path=create_data.brand_logo_path,
                atmosphere=create_data.atmosphere,
                global_style_prompt=create_data.global_style_prompt,
                reference_context=create_data.reference_context,
            )
            session.add(brand)
            await session.commit()
            await session.refresh(brand)
            return BrandConfigResponse.model_validate(brand)
        except Exception:
            await session.rollback()
            raise

    async def update_brand_config(self, update_data: BrandConfigUpdate) -> Optional[BrandConfigResponse]:
        """기존 브랜드 설정을 업데이트."""
        if self.db:
            return await self._update_impl(self.db, update_data)
        
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._update_impl(session, update_data)

    async def _update_impl(self, session: AsyncSession, update_data: BrandConfigUpdate) -> Optional[BrandConfigResponse]:
        """업데이트 트랜잭션."""
        try:
            query = select(BrandConfig).limit(1)
            result = await session.execute(query)
            brand = result.scalar_one_or_none()
            if not brand:
                return None
            
            for field, value in update_data.model_dump(exclude_unset=True).items():
                setattr(brand, field, value)
            
            await session.commit()
            await session.refresh(brand)
            return BrandConfigResponse.model_validate(brand)
        except Exception:
            await session.rollback()
            raise

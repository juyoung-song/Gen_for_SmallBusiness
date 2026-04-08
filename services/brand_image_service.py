"""BrandImage CRUD 서비스.

design.md §2.3 / §3 기준:
- 사용자당 brand_image 는 1개 (불변)
- 온보딩 1회만 create() 호출, 이후 get_for_user() / exists_for_user() 만 사용
- 두 번째 create() 시도는 BrandImageAlreadyExistsError 발생
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.brand_image import BrandImage


class BrandImageAlreadyExistsError(Exception):
    """동일 사용자의 brand_image 가 이미 존재할 때 발생."""


class BrandImageService:
    """BrandImage CRUD 서비스."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_for_user(self, user_id: str) -> bool:
        """사용자에게 brand_image 가 등록되어 있는지 여부."""
        stmt = select(BrandImage.id).where(BrandImage.user_id == user_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_for_user(self, user_id: str) -> BrandImage | None:
        """사용자의 brand_image 단일 조회. 없으면 None."""
        stmt = select(BrandImage).where(BrandImage.user_id == user_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: str,
        content: str,
        source_freetext: str,
        source_reference_url: str,
        source_screenshots: list[str] | None = None,
    ) -> BrandImage:
        """새 brand_image 생성. 이미 존재하면 BrandImageAlreadyExistsError."""
        if await self.exists_for_user(user_id):
            raise BrandImageAlreadyExistsError(
                f"사용자 '{user_id}' 의 brand_image 가 이미 존재합니다. "
                "brand_image 는 불변 정책으로 한 번만 생성 가능합니다."
            )

        brand = BrandImage(
            user_id=user_id,
            content=content,
            source_freetext=source_freetext,
            source_reference_url=source_reference_url,
            source_screenshots=source_screenshots or [],
        )
        self.session.add(brand)
        await self.session.commit()
        await self.session.refresh(brand)
        return brand

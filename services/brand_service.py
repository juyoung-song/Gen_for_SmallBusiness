"""Brand CRUD 서비스.

docs/schema.md §3.1 기준:
- 브랜드는 불변. create() 1회, 이후 get() 만. update() 미제공.
- 인스타 연결 단계에서만 instagram_account_id/username 을 한 번 채우는 허용
  (link_instagram) — 이는 "수정" 이 아니라 "최초 연결" 로 본다.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.brand import Brand


class BrandAlreadyExistsError(Exception):
    """동일 instagram_account_id 의 brand 가 이미 존재."""


class BrandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, brand_id: UUID) -> Brand | None:
        stmt = select(Brand).where(Brand.id == brand_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_instagram_account(self, instagram_account_id: str) -> Brand | None:
        stmt = (
            select(Brand)
            .where(Brand.instagram_account_id == instagram_account_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_first(self) -> Brand | None:
        """회원가입 미지원 MVP — 단일 브랜드 조회용 편의 메서드."""
        stmt = select(Brand).order_by(Brand.created_at).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        name: str,
        color_hex: str,
        logo_path: str | None,
        input_instagram_url: str,
        input_description: str,
        input_mood: str,
        style_prompt: str,
    ) -> Brand:
        brand = Brand(
            name=name,
            color_hex=color_hex,
            logo_path=logo_path,
            input_instagram_url=input_instagram_url,
            input_description=input_description,
            input_mood=input_mood,
            style_prompt=style_prompt,
        )
        self.session.add(brand)
        await self.session.commit()
        await self.session.refresh(brand)
        return brand

    async def link_instagram(
        self,
        brand_id: UUID,
        *,
        instagram_account_id: str,
        instagram_username: str | None,
    ) -> Brand:
        """인스타 연결 시점에 account_id/username 을 1회 채운다.

        이미 다른 brand 가 해당 account_id 를 소유 중이면 예외.
        """
        existing = await self.get_by_instagram_account(instagram_account_id)
        if existing and existing.id != brand_id:
            raise BrandAlreadyExistsError(
                f"instagram_account_id={instagram_account_id} 가 이미 다른 brand 에 연결됨"
            )

        brand = await self.get(brand_id)
        if brand is None:
            raise ValueError(f"brand_id={brand_id} 를 찾을 수 없음")

        brand.instagram_account_id = instagram_account_id
        brand.instagram_username = instagram_username
        await self.session.commit()
        await self.session.refresh(brand)
        return brand

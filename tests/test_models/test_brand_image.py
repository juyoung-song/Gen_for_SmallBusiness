"""BrandImage 모델 테스트.

design.md §2.3 및 §5 기준:
- brand_image 는 온보딩 1회 생성되는 불변 레코드
- content = GPT 가 정제한 system prompt 역할 텍스트
- source_freetext / source_reference_url / source_screenshots 는 생성 근거
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from models.brand_image import BrandImage


class TestBrandImageModel:
    async def test_can_persist_and_reload_with_minimal_fields(self, db_session):
        """필수 필드만으로 저장·재조회가 된다."""
        brand = BrandImage(
            user_id="default",
            content="따뜻하고 미니멀한 베이커리. 베이지 톤, 여백 중시.",
            source_freetext="그냥 따뜻한 느낌으로요",
            source_reference_url="https://www.instagram.com/some_bakery/",
        )
        db_session.add(brand)
        await db_session.commit()

        stmt = select(BrandImage).where(BrandImage.user_id == "default")
        result = await db_session.execute(stmt)
        loaded = result.scalar_one()

        assert isinstance(loaded.id, UUID)
        assert loaded.user_id == "default"
        assert loaded.content == "따뜻하고 미니멀한 베이커리. 베이지 톤, 여백 중시."
        assert loaded.source_freetext == "그냥 따뜻한 느낌으로요"
        assert loaded.source_reference_url == "https://www.instagram.com/some_bakery/"
        assert loaded.created_at is not None

    async def test_source_screenshots_can_store_list_of_paths(self, db_session):
        """source_screenshots 는 캡처 파일 경로 리스트를 JSON 으로 저장한다."""
        brand = BrandImage(
            user_id="default",
            content="...",
            source_freetext="...",
            source_reference_url="https://example.com/",
            source_screenshots=[
                "data/onboarding/shot_1.png",
                "data/onboarding/shot_2.png",
            ],
        )
        db_session.add(brand)
        await db_session.commit()
        await db_session.refresh(brand)

        assert isinstance(brand.source_screenshots, list)
        assert len(brand.source_screenshots) == 2
        assert brand.source_screenshots[0] == "data/onboarding/shot_1.png"

    async def test_user_id_defaults_to_default_when_omitted(self, db_session):
        """단일 사용자 가정: user_id 생략 시 'default' 로 자동 설정."""
        brand = BrandImage(
            content="...",
            source_freetext="...",
            source_reference_url="https://example.com/",
        )
        db_session.add(brand)
        await db_session.commit()
        await db_session.refresh(brand)

        assert brand.user_id == "default"

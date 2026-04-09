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

    async def test_brand_name_and_color_fields_optional(self, db_session):
        """Song 이식: brand_name, brand_color 필드는 선택 (nullable)."""
        brand = BrandImage(
            user_id="default",
            content="...",
            source_freetext="...",
            source_reference_url="https://example.com/",
            brand_name="구름 베이커리",
            brand_color="#5562EA",
        )
        db_session.add(brand)
        await db_session.commit()
        await db_session.refresh(brand)

        assert brand.brand_name == "구름 베이커리"
        assert brand.brand_color == "#5562EA"

    async def test_brand_name_and_color_default_to_none(self, db_session):
        """신규 필드 미지정 시 None (기존 레코드 호환)."""
        brand = BrandImage(
            content="...",
            source_freetext="...",
            source_reference_url="https://example.com/",
        )
        db_session.add(brand)
        await db_session.commit()
        await db_session.refresh(brand)

        assert brand.brand_name is None
        assert brand.brand_color is None

    async def test_logo_path_field_optional(self, db_session):
        """Song 이식: brand_logo_path 필드도 nullable."""
        brand = BrandImage(
            content="...",
            source_freetext="...",
            source_reference_url="https://example.com/",
            brand_logo_path="data/brand/logo_abc.png",
        )
        db_session.add(brand)
        await db_session.commit()
        await db_session.refresh(brand)

        assert brand.brand_logo_path == "data/brand/logo_abc.png"

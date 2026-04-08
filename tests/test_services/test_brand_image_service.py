"""BrandImageService 테스트.

design.md §2.3 기준:
- brand_image 는 사용자당 1개, 온보딩 1회 생성 후 불변
- 서비스는 다음을 제공:
  - create(...): 새 brand_image 생성 (이미 있으면 BrandImageAlreadyExistsError)
  - get_for_user(user_id): 단일 brand_image 조회
  - exists_for_user(user_id): 존재 여부 (라우팅용)
"""

import pytest

from services.brand_image_service import (
    BrandImageAlreadyExistsError,
    BrandImageService,
)


class TestBrandImageService:
    async def test_exists_returns_false_when_no_brand_image(self, db_session):
        service = BrandImageService(db_session)
        assert await service.exists_for_user("default") is False

    async def test_create_then_exists_returns_true(self, db_session):
        service = BrandImageService(db_session)
        await service.create(
            user_id="default",
            content="따뜻하고 미니멀한 톤",
            source_freetext="따뜻한 느낌",
            source_reference_url="https://www.instagram.com/some/",
            source_screenshots=["data/onboarding/shot_1.png"],
        )
        assert await service.exists_for_user("default") is True

    async def test_get_for_user_returns_brand_image(self, db_session):
        service = BrandImageService(db_session)
        await service.create(
            user_id="default",
            content="고급스러운 다크 톤",
            source_freetext="고급스럽게",
            source_reference_url="https://example.com/",
        )

        loaded = await service.get_for_user("default")
        assert loaded is not None
        assert loaded.content == "고급스러운 다크 톤"
        assert loaded.user_id == "default"

    async def test_get_for_user_returns_none_when_missing(self, db_session):
        service = BrandImageService(db_session)
        assert await service.get_for_user("default") is None

    async def test_create_twice_for_same_user_raises(self, db_session):
        """불변 정책: 동일 사용자에 대해 두 번째 create 는 에러."""
        service = BrandImageService(db_session)
        await service.create(
            user_id="default",
            content="첫 번째",
            source_freetext="...",
            source_reference_url="https://example.com/",
        )

        with pytest.raises(BrandImageAlreadyExistsError):
            await service.create(
                user_id="default",
                content="두 번째 시도",
                source_freetext="...",
                source_reference_url="https://example.com/",
            )

    async def test_different_users_can_each_have_brand_image(self, db_session):
        """멀티테넌트 확장 대비: user_id 가 다르면 각자 1개씩 가능."""
        service = BrandImageService(db_session)
        await service.create(
            user_id="user_a",
            content="A의 톤",
            source_freetext="...",
            source_reference_url="https://example.com/a",
        )
        await service.create(
            user_id="user_b",
            content="B의 톤",
            source_freetext="...",
            source_reference_url="https://example.com/b",
        )

        a = await service.get_for_user("user_a")
        b = await service.get_for_user("user_b")
        assert a is not None and a.content == "A의 톤"
        assert b is not None and b.content == "B의 톤"

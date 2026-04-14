"""BrandService 테스트.

docs/schema.md §3.1 원칙 확인:
- 불변 엔티티 (update API 제공 안 함)
- instagram_account_id UNIQUE
- link_instagram 은 1회성 연결 허용
"""

import pytest

from services.brand_service import BrandAlreadyExistsError, BrandService


class TestBrandServiceCreate:
    async def test_create_returns_persisted_brand(self, db_session):
        svc = BrandService(db_session)
        brand = await svc.create(
            name="구름 베이커리",
            color_hex="#5562EA",
            logo_path=None,
            input_instagram_url="https://instagram.com/x",
            input_description="동네 베이커리",
            input_mood="따뜻한",
            style_prompt="이 브랜드는 베이커리입니다.",
        )
        assert brand.id is not None
        assert brand.name == "구름 베이커리"
        assert brand.instagram_account_id is None  # 연결 전
        assert brand.created_at is not None


class TestBrandServiceGet:
    async def test_get_returns_none_if_missing(self, db_session):
        import uuid
        svc = BrandService(db_session)
        result = await svc.get(uuid.uuid4())
        assert result is None

    async def test_get_first_returns_earliest(self, db_session, brand_factory):
        b1 = await brand_factory(name="A")
        b2 = await brand_factory(name="B")
        svc = BrandService(db_session)
        first = await svc.get_first()
        assert first is not None
        assert first.id == b1.id  # created_at 오름차순 중 첫 번째

    async def test_get_by_instagram_account(self, db_session, brand_factory):
        b = await brand_factory(instagram_account_id="17841000000000001")
        svc = BrandService(db_session)
        found = await svc.get_by_instagram_account("17841000000000001")
        assert found is not None and found.id == b.id

        missing = await svc.get_by_instagram_account("nope")
        assert missing is None


class TestBrandServiceLinkInstagram:
    async def test_link_fills_account_fields(self, db_session, brand_factory):
        brand = await brand_factory()
        svc = BrandService(db_session)
        updated = await svc.link_instagram(
            brand.id,
            instagram_account_id="17841000000000001",
            instagram_username="my_cafe",
        )
        assert updated.instagram_account_id == "17841000000000001"
        assert updated.instagram_username == "my_cafe"

    async def test_link_raises_when_account_taken_by_other(
        self, db_session, brand_factory
    ):
        await brand_factory(instagram_account_id="17841000000000001")
        brand2 = await brand_factory(name="B", instagram_account_id=None)
        svc = BrandService(db_session)
        with pytest.raises(BrandAlreadyExistsError):
            await svc.link_instagram(
                brand2.id,
                instagram_account_id="17841000000000001",
                instagram_username="x",
            )

    async def test_link_is_idempotent_for_same_brand(self, db_session, brand_factory):
        brand = await brand_factory(instagram_account_id="17841000000000001")
        svc = BrandService(db_session)
        # 같은 brand 에 같은 account_id 재적용은 허용 (연결 유지)
        updated = await svc.link_instagram(
            brand.id,
            instagram_account_id="17841000000000001",
            instagram_username="renamed",
        )
        assert updated.instagram_username == "renamed"

    async def test_link_raises_when_brand_missing(self, db_session):
        import uuid
        svc = BrandService(db_session)
        with pytest.raises(ValueError):
            await svc.link_instagram(
                uuid.uuid4(),
                instagram_account_id="x",
                instagram_username=None,
            )

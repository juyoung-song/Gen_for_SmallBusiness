"""ProductService 테스트.

design.md §4.1 기준:
- 신상품 토글 ON 시 → service.create()
- 기존 상품 드롭다운 → service.list_all() / service.get(id)
- (선택) 이름 매칭 → service.find_by_name(name)
"""

from uuid import UUID, uuid4

import pytest

from services.product_service import ProductService


class TestProductService:
    async def test_create_returns_persisted_product(self, db_session):
        service = ProductService(db_session)
        product = await service.create(
            name="블루베리 치즈케이크",
            description="프랑스산 크림치즈",
            raw_image_path="data/products/cake.jpg",
        )
        assert isinstance(product.id, UUID)
        assert product.name == "블루베리 치즈케이크"
        assert product.description == "프랑스산 크림치즈"
        assert product.raw_image_path == "data/products/cake.jpg"

    async def test_get_returns_product_by_id(self, db_session):
        service = ProductService(db_session)
        created = await service.create(
            name="마들렌",
            description="버터 향",
            raw_image_path="data/products/madeleine.jpg",
        )
        loaded = await service.get(created.id)
        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.name == "마들렌"

    async def test_get_returns_none_for_unknown_id(self, db_session):
        service = ProductService(db_session)
        assert await service.get(uuid4()) is None

    async def test_list_all_returns_all_products_ordered_by_creation(
        self, db_session
    ):
        service = ProductService(db_session)
        await service.create(
            name="크루아상", description="버터 결", raw_image_path="data/c.jpg"
        )
        await service.create(
            name="에그타르트", description="포르투갈식", raw_image_path="data/e.jpg"
        )
        await service.create(
            name="스콘", description="잉글랜드식", raw_image_path="data/s.jpg"
        )

        products = await service.list_all()
        assert len(products) == 3
        names = [p.name for p in products]
        assert "크루아상" in names
        assert "에그타르트" in names
        assert "스콘" in names

    async def test_find_by_name_exact_match(self, db_session):
        service = ProductService(db_session)
        await service.create(
            name="블루베리 치즈케이크",
            description="버전 A",
            raw_image_path="data/a.jpg",
        )
        await service.create(
            name="블루베리 치즈케이크",
            description="버전 B (시즌 한정)",
            raw_image_path="data/b.jpg",
        )
        await service.create(
            name="딸기 치즈케이크",
            description="...",
            raw_image_path="data/strawberry.jpg",
        )

        # 같은 이름이 여러 개일 수 있음 (Product 모델은 unique 강제 X)
        matches = await service.find_by_name("블루베리 치즈케이크")
        assert len(matches) == 2
        assert {m.description for m in matches} == {"버전 A", "버전 B (시즌 한정)"}

    async def test_find_by_name_returns_empty_when_no_match(self, db_session):
        service = ProductService(db_session)
        await service.create(
            name="크루아상", description="...", raw_image_path="data/c.jpg"
        )
        assert await service.find_by_name("없는 상품") == []

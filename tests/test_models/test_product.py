"""Product 모델 테스트.

design.md §2.2 / §5 기준:
- 상품(raw 이미지 = "화장 전")의 최소 단위
- name 은 검색 대상이므로 인덱스 + 자유 텍스트 (소상공인 특성상 unique 강제는 위험)
- raw_image_path 는 staging/permanent 어디든 파일 시스템 경로
"""

from uuid import UUID

import pytest
from sqlalchemy import select

from models.product import Product


class TestProductModel:
    async def test_can_persist_with_required_fields(self, db_session):
        """필수 필드(name, description, raw_image_path) 만으로 저장된다."""
        product = Product(
            name="블루베리 치즈케이크",
            description="프랑스산 크림치즈 사용. 단맛 절제.",
            raw_image_path="data/products/cake_raw.jpg",
        )
        db_session.add(product)
        await db_session.commit()

        result = await db_session.execute(select(Product))
        loaded = result.scalar_one()

        assert isinstance(loaded.id, UUID)
        assert loaded.name == "블루베리 치즈케이크"
        assert loaded.description == "프랑스산 크림치즈 사용. 단맛 절제."
        assert loaded.raw_image_path == "data/products/cake_raw.jpg"
        assert loaded.created_at is not None

    async def test_multiple_products_can_share_no_uniqueness_constraint(
        self, db_session
    ):
        """name 은 unique 가 아니다 — 같은 이름의 상품이 두 개 등록되어도 거부되지 않는다."""
        a = Product(
            name="마들렌",
            description="버터 향",
            raw_image_path="data/products/madeleine_a.jpg",
        )
        b = Product(
            name="마들렌",
            description="레몬 글레이즈",
            raw_image_path="data/products/madeleine_b.jpg",
        )
        db_session.add_all([a, b])
        await db_session.commit()

        result = await db_session.execute(select(Product))
        all_products = result.scalars().all()
        assert len(all_products) == 2

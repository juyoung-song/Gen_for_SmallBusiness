"""GeneratedUpload 모델 테스트.

design.md §2.2 / §5 / §4.4 기준:
- 시스템이 생성해서 인스타에 게시한 결과물 ("화장 후")
- product 와 부모-자식 관계 (FK)
- instagram_post_id / posted_at 은 게시 성공 후에만 채워진다 (nullable)
- goal_category / goal_freeform 은 카테고리 + 자유 텍스트 양쪽 보존
"""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.generated_upload import GeneratedUpload
from models.product import Product


class TestGeneratedUploadModel:
    async def test_can_persist_with_required_fields_only(self, db_session):
        """게시 직전 상태(인스타 메타 없음)도 저장 가능."""
        product = Product(
            name="블루베리 치즈케이크",
            description="...",
            raw_image_path="data/products/cake.jpg",
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        upload = GeneratedUpload(
            product_id=product.id,
            image_path="data/uploads/result.png",
            caption="✨ 오늘의 블루베리 치즈케이크",
            goal_category="신메뉴 출시",
            goal_freeform="여름 한정으로 출시",
        )
        db_session.add(upload)
        await db_session.commit()
        await db_session.refresh(upload)

        assert isinstance(upload.id, UUID)
        assert upload.product_id == product.id
        assert upload.image_path == "data/uploads/result.png"
        assert upload.caption == "✨ 오늘의 블루베리 치즈케이크"
        assert upload.goal_category == "신메뉴 출시"
        assert upload.goal_freeform == "여름 한정으로 출시"
        assert upload.instagram_post_id is None
        assert upload.posted_at is None
        assert upload.created_at is not None

    async def test_can_set_instagram_metadata_after_posting(self, db_session):
        """게시 성공 시 instagram_post_id 와 posted_at 을 채울 수 있다.

        SQLite 는 timezone-aware datetime 저장 시 tzinfo 를 떼버리는 알려진
        동작이 있어, 본 테스트는 시각 동일성만 검증한다.
        """
        product = Product(
            name="마들렌",
            description="버터 향",
            raw_image_path="data/products/madeleine.jpg",
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        posted = datetime(2026, 4, 8, 15, 30, tzinfo=timezone.utc)
        upload = GeneratedUpload(
            product_id=product.id,
            image_path="data/uploads/madeleine_result.png",
            caption="...",
            goal_category="할인·이벤트",
            goal_freeform="10% 할인",
            instagram_post_id="17841234567890",
            posted_at=posted,
        )
        db_session.add(upload)
        await db_session.commit()
        await db_session.refresh(upload)

        assert upload.instagram_post_id == "17841234567890"
        # SQLite 는 tzinfo 를 저장하지 않음 — naive 로 비교
        assert upload.posted_at.replace(tzinfo=None) == posted.replace(tzinfo=None)

    async def test_product_to_uploads_relationship_loads(self, db_session):
        """product.uploads 로 자식 GeneratedUpload 들을 조회할 수 있다."""
        product = Product(
            name="크루아상",
            description="버터 결",
            raw_image_path="data/products/croissant.jpg",
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        for i in range(3):
            db_session.add(
                GeneratedUpload(
                    product_id=product.id,
                    image_path=f"data/uploads/croissant_{i}.png",
                    caption=f"caption {i}",
                    goal_category="일상·감성",
                    goal_freeform="",
                )
            )
        await db_session.commit()

        # selectinload 로 자식 미리 가져옴 (lazy 회피)
        stmt = (
            select(Product)
            .where(Product.id == product.id)
            .options(selectinload(Product.uploads))
        )
        loaded = (await db_session.execute(stmt)).scalar_one()

        assert len(loaded.uploads) == 3
        assert {u.caption for u in loaded.uploads} == {"caption 0", "caption 1", "caption 2"}

    async def test_deleting_product_cascades_uploads(self, db_session):
        """Product 삭제 시 자식 GeneratedUpload 도 함께 삭제된다 (orphan 방지)."""
        product = Product(
            name="에그타르트",
            description="포르투갈식",
            raw_image_path="data/products/egg_tart.jpg",
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        db_session.add(
            GeneratedUpload(
                product_id=product.id,
                image_path="data/uploads/eggtart.png",
                caption="...",
                goal_category="신메뉴 출시",
                goal_freeform="",
            )
        )
        await db_session.commit()

        # 삭제
        await db_session.delete(product)
        await db_session.commit()

        result = await db_session.execute(select(GeneratedUpload))
        remaining = result.scalars().all()
        assert remaining == []

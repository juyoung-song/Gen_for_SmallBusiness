"""GeneratedUploadService 테스트.

design.md §4.4 / §4.5 / §6 기준:
- create(): 생성 결과를 staging 상태로 저장 (instagram_post_id=None)
- mark_posted(): 게시 성공 시 인스타 메타 갱신
- list_published(): 인스타 게시 완료된 것만 (참조 이미지 풀)
- list_for_product(): 특정 상품의 모든 결과물 (옵션)
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from services.product_service import ProductService
from services.upload_service import UploadService


class TestUploadService:
    async def test_create_persists_with_no_instagram_metadata(self, db_session):
        product_service = ProductService(db_session)
        upload_service = UploadService(db_session)

        product = await product_service.create(
            name="블루베리 치즈케이크",
            description="...",
            raw_image_path="data/products/cake.jpg",
        )

        upload = await upload_service.create(
            product_id=product.id,
            image_path="data/uploads/result.png",
            caption="✨ 오늘의 디저트",
            goal_category="신메뉴 출시",
            goal_freeform="여름 한정",
        )

        assert upload.product_id == product.id
        assert upload.image_path == "data/uploads/result.png"
        assert upload.caption == "✨ 오늘의 디저트"
        assert upload.goal_category == "신메뉴 출시"
        assert upload.goal_freeform == "여름 한정"
        assert upload.instagram_post_id is None
        assert upload.posted_at is None

    async def test_mark_posted_updates_instagram_metadata(self, db_session):
        product_service = ProductService(db_session)
        upload_service = UploadService(db_session)

        product = await product_service.create(
            name="마들렌", description="...", raw_image_path="data/m.jpg"
        )
        upload = await upload_service.create(
            product_id=product.id,
            image_path="data/uploads/m.png",
            caption="...",
            goal_category="일상·감성",
            goal_freeform="",
        )

        posted = datetime(2026, 4, 8, 15, 30, tzinfo=timezone.utc)
        updated = await upload_service.mark_posted(
            upload_id=upload.id,
            instagram_post_id="17841234567890",
            posted_at=posted,
        )

        assert updated.instagram_post_id == "17841234567890"
        assert updated.posted_at is not None
        # SQLite 는 tzinfo 를 떼버리므로 naive 비교
        assert updated.posted_at.replace(tzinfo=None) == posted.replace(tzinfo=None)

    async def test_list_published_excludes_unposted(self, db_session):
        """참조 이미지 풀에는 인스타 게시 완료된 것만 포함된다."""
        product_service = ProductService(db_session)
        upload_service = UploadService(db_session)

        product = await product_service.create(
            name="크루아상", description="...", raw_image_path="data/c.jpg"
        )
        # 3개 생성, 그 중 2개만 mark_posted
        u1 = await upload_service.create(
            product_id=product.id,
            image_path="data/u1.png",
            caption="1",
            goal_category="신메뉴 출시",
            goal_freeform="",
        )
        u2 = await upload_service.create(
            product_id=product.id,
            image_path="data/u2.png",
            caption="2",
            goal_category="신메뉴 출시",
            goal_freeform="",
        )
        u3 = await upload_service.create(  # 게시 안 함
            product_id=product.id,
            image_path="data/u3.png",
            caption="3",
            goal_category="신메뉴 출시",
            goal_freeform="",
        )

        await upload_service.mark_posted(
            upload_id=u1.id,
            instagram_post_id="post1",
            posted_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        await upload_service.mark_posted(
            upload_id=u2.id,
            instagram_post_id="post2",
            posted_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )

        published = await upload_service.list_published()
        assert len(published) == 2
        captions = {p.caption for p in published}
        assert captions == {"1", "2"}
        assert "3" not in captions

    async def test_list_for_product_returns_only_that_product_uploads(
        self, db_session
    ):
        product_service = ProductService(db_session)
        upload_service = UploadService(db_session)

        product_a = await product_service.create(
            name="A", description="...", raw_image_path="data/a.jpg"
        )
        product_b = await product_service.create(
            name="B", description="...", raw_image_path="data/b.jpg"
        )

        await upload_service.create(
            product_id=product_a.id,
            image_path="data/a1.png",
            caption="a1",
            goal_category="...",
            goal_freeform="",
        )
        await upload_service.create(
            product_id=product_a.id,
            image_path="data/a2.png",
            caption="a2",
            goal_category="...",
            goal_freeform="",
        )
        await upload_service.create(
            product_id=product_b.id,
            image_path="data/b1.png",
            caption="b1",
            goal_category="...",
            goal_freeform="",
        )

        a_uploads = await upload_service.list_for_product(product_a.id)
        assert {u.caption for u in a_uploads} == {"a1", "a2"}

    async def test_mark_posted_for_unknown_id_raises(self, db_session):
        upload_service = UploadService(db_session)
        with pytest.raises(ValueError):
            await upload_service.mark_posted(
                upload_id=uuid4(),
                instagram_post_id="post",
                posted_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            )

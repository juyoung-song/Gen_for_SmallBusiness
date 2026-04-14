"""UploadService 테스트.

docs/schema.md §3.6 원칙:
- generation_output_id 기반
- kind: feed / story 만 허용
- list_published 는 (upload, output) 튜플
"""

from datetime import datetime, timezone

import pytest

from services.generation_service import GenerationService, OutputSpec
from services.upload_service import UploadService


@pytest.fixture
async def image_output(db_session, brand_factory):
    """테스트용 GenerationOutput(kind=image) 하나를 만들어 반환."""
    brand = await brand_factory()
    gen = await GenerationService(db_session).create_with_outputs(
        brand_id=brand.id, reference_image_id=None,
        product_name="p", product_description="d", product_image_path=None,
        goal="g", tone="기본", is_new_product=False,
        outputs=[OutputSpec(kind="image", content_path="/tmp/img.png")],
    )
    image_out = next(o for o in gen.outputs if o.kind == "image")
    return brand, gen, image_out


class TestCreate:
    async def test_create_feed_with_caption(self, db_session, image_output):
        _, _, output = image_output
        svc = UploadService(db_session)
        upload = await svc.create(
            generation_output_id=output.id,
            kind="feed",
            caption="본문\n#해시",
        )
        assert upload.id is not None
        assert upload.kind == "feed"
        assert upload.caption == "본문\n#해시"
        assert upload.instagram_post_id is None

    async def test_create_story_empty_caption(self, db_session, image_output):
        _, _, output = image_output
        svc = UploadService(db_session)
        upload = await svc.create(generation_output_id=output.id, kind="story")
        assert upload.kind == "story"
        assert upload.caption == ""

    async def test_invalid_kind_raises(self, db_session, image_output):
        _, _, output = image_output
        svc = UploadService(db_session)
        with pytest.raises(ValueError):
            await svc.create(generation_output_id=output.id, kind="reel")


class TestMarkPosted:
    async def test_sets_post_id_and_posted_at(self, db_session, image_output):
        _, _, output = image_output
        svc = UploadService(db_session)
        upload = await svc.create(generation_output_id=output.id, kind="feed")
        now = datetime.now(timezone.utc)
        marked = await svc.mark_posted(
            upload_id=upload.id,
            instagram_post_id="IG_POST_123",
            posted_at=now,
        )
        assert marked.instagram_post_id == "IG_POST_123"
        assert marked.posted_at is not None

    async def test_raises_when_upload_missing(self, db_session):
        import uuid
        svc = UploadService(db_session)
        with pytest.raises(ValueError):
            await svc.mark_posted(
                upload_id=uuid.uuid4(),
                instagram_post_id="x",
                posted_at=datetime.now(timezone.utc),
            )


class TestListPublished:
    async def test_only_published(self, db_session, image_output):
        _, _, output = image_output
        svc = UploadService(db_session)
        u1 = await svc.create(generation_output_id=output.id, kind="feed")
        u2 = await svc.create(generation_output_id=output.id, kind="story")
        # u1 만 게시
        await svc.mark_posted(
            upload_id=u1.id,
            instagram_post_id="X",
            posted_at=datetime.now(timezone.utc),
        )
        pairs = await svc.list_published()
        assert len(pairs) == 1
        upload, out = pairs[0]
        assert upload.id == u1.id
        assert out.id == output.id

    async def test_filters_by_brand(self, db_session, brand_factory):
        svc_gen_factory = lambda s: GenerationService(s)  # noqa: E731
        brand_a = await brand_factory(name="A")
        brand_b = await brand_factory(name="B")
        # 각 brand 에 generation 1개씩
        gen_a = await svc_gen_factory(db_session).create_with_outputs(
            brand_id=brand_a.id, reference_image_id=None,
            product_name="pa", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="image", content_path="/tmp/a.png")],
        )
        gen_b = await svc_gen_factory(db_session).create_with_outputs(
            brand_id=brand_b.id, reference_image_id=None,
            product_name="pb", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="image", content_path="/tmp/b.png")],
        )
        out_a = next(o for o in gen_a.outputs if o.kind == "image")
        out_b = next(o for o in gen_b.outputs if o.kind == "image")

        usvc = UploadService(db_session)
        ua = await usvc.create(generation_output_id=out_a.id, kind="feed")
        ub = await usvc.create(generation_output_id=out_b.id, kind="feed")
        await usvc.mark_posted(upload_id=ua.id, instagram_post_id="A", posted_at=datetime.now(timezone.utc))
        await usvc.mark_posted(upload_id=ub.id, instagram_post_id="B", posted_at=datetime.now(timezone.utc))

        a_pairs = await usvc.list_published(brand_id=brand_a.id)
        assert len(a_pairs) == 1 and a_pairs[0][0].id == ua.id


class TestListForGeneration:
    async def test_returns_uploads_for_generation(self, db_session, image_output):
        _, gen, output = image_output
        svc = UploadService(db_session)
        u1 = await svc.create(generation_output_id=output.id, kind="feed")
        u2 = await svc.create(generation_output_id=output.id, kind="story")
        uploads = await svc.list_for_generation(gen.id)
        ids = {u.id for u in uploads}
        assert ids == {u1.id, u2.id}

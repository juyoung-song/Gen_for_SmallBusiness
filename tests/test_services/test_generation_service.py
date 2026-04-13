"""GenerationService 테스트.

docs/schema.md §3.3 / §3.4 원칙:
- Generation + Output append-only 작성
- list_products: product_name 그룹핑 + 카운트 + 최신 대표
- mark_failed: error_message 기록
"""

from datetime import datetime, timedelta, timezone

import pytest

from services.generation_service import GenerationService, OutputSpec


async def _set_created_at(session, gen, ts: datetime) -> None:
    """SQLite CURRENT_TIMESTAMP 가 초 단위라 연속 insert 정렬이 꼬이는 걸 회피.

    테스트에서 명시적으로 created_at 을 덮어써서 정렬 검증을 안정화한다.
    """
    gen.created_at = ts
    await session.commit()
    await session.refresh(gen)


@pytest.fixture
def outputs_full():
    return [
        OutputSpec(kind="image", content_path="/tmp/img.png"),
        OutputSpec(kind="ad_copy", content_text="첫 광고 카피"),
        OutputSpec(kind="ad_copy", content_text="두번째 카피"),
        OutputSpec(kind="promo_sentence", content_text="홍보 문장"),
        OutputSpec(kind="story_copy", content_text="스토리 카피"),
    ]


class TestCreateWithOutputs:
    async def test_persists_generation_and_outputs(
        self, db_session, brand_factory, outputs_full
    ):
        brand = await brand_factory()
        svc = GenerationService(db_session)
        gen = await svc.create_with_outputs(
            brand_id=brand.id,
            reference_image_id=None,
            product_name="크루아상",
            product_description="막 구운",
            product_image_path=None,
            goal="신메뉴 출시",
            tone="감성",
            is_new_product=True,
            outputs=outputs_full,
        )
        assert gen.id is not None
        assert gen.product_name == "크루아상"
        loaded = await svc.get_with_outputs(gen.id)
        assert loaded is not None
        assert len(loaded.outputs) == 5
        kinds = sorted([o.kind for o in loaded.outputs])
        assert kinds == ["ad_copy", "ad_copy", "image", "promo_sentence", "story_copy"]

    async def test_strips_whitespace_in_product_name(
        self, db_session, brand_factory
    ):
        brand = await brand_factory()
        svc = GenerationService(db_session)
        gen = await svc.create_with_outputs(
            brand_id=brand.id,
            reference_image_id=None,
            product_name="  크루아상  ",
            product_description="d",
            product_image_path=None,
            goal="g",
            tone="기본",
            is_new_product=False,
            outputs=[OutputSpec(kind="image", content_path="/tmp/x.png")],
        )
        assert gen.product_name == "크루아상"

    async def test_stores_langfuse_trace_id(self, db_session, brand_factory):
        brand = await brand_factory()
        svc = GenerationService(db_session)
        gen = await svc.create_with_outputs(
            brand_id=brand.id,
            reference_image_id=None,
            product_name="p",
            product_description="d",
            product_image_path=None,
            goal="g",
            tone="기본",
            is_new_product=False,
            outputs=[OutputSpec(kind="ad_copy", content_text="x")],
            langfuse_trace_id="trace-abc-123",
        )
        assert gen.langfuse_trace_id == "trace-abc-123"


class TestMarkFailed:
    async def test_sets_error_message(self, db_session, brand_factory):
        brand = await brand_factory()
        svc = GenerationService(db_session)
        gen = await svc.create_with_outputs(
            brand_id=brand.id,
            reference_image_id=None,
            product_name="p", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="ad_copy", content_text="x")],
        )
        await svc.mark_failed(gen.id, "timeout")
        reloaded = await svc.get_with_outputs(gen.id)
        assert reloaded.error_message == "timeout"

    async def test_silent_when_generation_missing(self, db_session):
        import uuid
        svc = GenerationService(db_session)
        # 예외를 터뜨리지 않고 조용히 지나감
        await svc.mark_failed(uuid.uuid4(), "x")


class TestListForBrand:
    async def test_returns_recent_first(self, db_session, brand_factory):
        brand = await brand_factory()
        svc = GenerationService(db_session)
        base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        for i in range(3):
            gen = await svc.create_with_outputs(
                brand_id=brand.id, reference_image_id=None,
                product_name=f"P{i}", product_description="d", product_image_path=None,
                goal="g", tone="기본", is_new_product=False,
                outputs=[OutputSpec(kind="ad_copy", content_text=str(i))],
            )
            await _set_created_at(db_session, gen, base + timedelta(seconds=i))
        gens = await svc.list_for_brand(brand.id)
        assert len(gens) == 3
        assert [g.product_name for g in gens] == ["P2", "P1", "P0"]

    async def test_filters_by_brand(self, db_session, brand_factory):
        a = await brand_factory(name="A")
        b = await brand_factory(name="B")
        svc = GenerationService(db_session)
        await svc.create_with_outputs(
            brand_id=a.id, reference_image_id=None,
            product_name="pa", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="ad_copy", content_text="a")],
        )
        await svc.create_with_outputs(
            brand_id=b.id, reference_image_id=None,
            product_name="pb", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="ad_copy", content_text="b")],
        )
        assert [g.product_name for g in await svc.list_for_brand(a.id)] == ["pa"]
        assert [g.product_name for g in await svc.list_for_brand(b.id)] == ["pb"]


class TestListProducts:
    async def test_groups_by_product_name(self, db_session, brand_factory):
        brand = await brand_factory()
        svc = GenerationService(db_session)
        base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        for i in range(3):
            gen = await svc.create_with_outputs(
                brand_id=brand.id, reference_image_id=None,
                product_name="크루아상", product_description=f"v{i}",
                product_image_path=f"/tmp/c{i}.png",
                goal="g", tone="기본", is_new_product=(i == 0),
                outputs=[OutputSpec(kind="image", content_path=f"/tmp/c{i}.png")],
            )
            await _set_created_at(db_session, gen, base + timedelta(seconds=i))

        bag = await svc.create_with_outputs(
            brand_id=brand.id, reference_image_id=None,
            product_name="바게트", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="image", content_path="/tmp/b.png")],
        )
        # 바게트가 가장 최근이 되도록 timestamp 보정
        await _set_created_at(db_session, bag, base + timedelta(seconds=10))

        products = await svc.list_products(brand.id)
        names = [p.product_name for p in products]
        assert names == ["바게트", "크루아상"]
        croissant = next(p for p in products if p.product_name == "크루아상")
        assert croissant.generation_count == 3
        assert croissant.product_description == "v2"

    async def test_empty_for_brand_without_generation(self, db_session, brand_factory):
        brand = await brand_factory()
        svc = GenerationService(db_session)
        assert await svc.list_products(brand.id) == []

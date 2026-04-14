"""ReferenceImageService 테스트.

docs/schema.md §3.2 원칙:
- source_output_id UNIQUE → 재사용
- composition_prompt 는 ReferenceAnalyzer 가 생성 (테스트는 Fake 주입)
- 이미지가 아닌 output 참조 시 ValueError
"""

from pathlib import Path

import pytest

from services.generation_service import GenerationService, OutputSpec
from services.reference_service import ReferenceImageService


class _FakeAnalyzer:
    """실 OpenAI 호출 없이 composition_prompt 를 돌려주는 Fake."""

    def __init__(self, prompt: str = "overhead flat-lay, central subject"):
        self.prompt = prompt
        self.calls = 0

    def analyze(self, image_path: Path) -> str:
        self.calls += 1
        return self.prompt


@pytest.fixture
async def image_output_with_file(db_session, brand_factory, tmp_path):
    """실제 파일까지 존재하는 GenerationOutput(kind=image)."""
    img_path = tmp_path / "ref.png"
    img_path.write_bytes(b"fake png bytes")
    brand = await brand_factory()
    gen = await GenerationService(db_session).create_with_outputs(
        brand_id=brand.id, reference_image_id=None,
        product_name="p", product_description="d", product_image_path=None,
        goal="g", tone="기본", is_new_product=False,
        outputs=[OutputSpec(kind="image", content_path=str(img_path))],
    )
    out = next(o for o in gen.outputs if o.kind == "image")
    return brand, out


class TestUpsertBySourceOutput:
    async def test_creates_when_missing(self, db_session, image_output_with_file):
        brand, output = image_output_with_file
        analyzer = _FakeAnalyzer(prompt="low-angle, off-center")
        svc = ReferenceImageService(db_session)

        ref = await svc.upsert_by_source_output(
            source_output_id=output.id, analyzer=analyzer,
        )
        assert ref.id is not None
        assert ref.source_output_id == output.id
        assert ref.brand_id == brand.id
        assert ref.composition_prompt == "low-angle, off-center"
        assert ref.path == output.content_path
        assert analyzer.calls == 1

    async def test_reuses_existing(self, db_session, image_output_with_file):
        _, output = image_output_with_file
        analyzer = _FakeAnalyzer()
        svc = ReferenceImageService(db_session)

        ref1 = await svc.upsert_by_source_output(
            source_output_id=output.id, analyzer=analyzer,
        )
        ref2 = await svc.upsert_by_source_output(
            source_output_id=output.id, analyzer=analyzer,
        )
        assert ref1.id == ref2.id
        assert analyzer.calls == 1  # 두 번째는 재분석 없이 재사용

    async def test_rejects_non_image_output(self, db_session, brand_factory):
        brand = await brand_factory()
        gen = await GenerationService(db_session).create_with_outputs(
            brand_id=brand.id, reference_image_id=None,
            product_name="p", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="ad_copy", content_text="not an image")],
        )
        text_out = next(o for o in gen.outputs if o.kind == "ad_copy")
        svc = ReferenceImageService(db_session)
        with pytest.raises(ValueError):
            await svc.upsert_by_source_output(
                source_output_id=text_out.id, analyzer=_FakeAnalyzer(),
            )

    async def test_rejects_missing_output(self, db_session):
        import uuid
        svc = ReferenceImageService(db_session)
        with pytest.raises(ValueError):
            await svc.upsert_by_source_output(
                source_output_id=uuid.uuid4(), analyzer=_FakeAnalyzer(),
            )


class TestGetBySourceOutput:
    async def test_returns_none_when_absent(self, db_session, image_output_with_file):
        _, output = image_output_with_file
        svc = ReferenceImageService(db_session)
        assert await svc.get_by_source_output(output.id) is None

    async def test_returns_existing_after_upsert(
        self, db_session, image_output_with_file
    ):
        _, output = image_output_with_file
        svc = ReferenceImageService(db_session)
        created = await svc.upsert_by_source_output(
            source_output_id=output.id, analyzer=_FakeAnalyzer(),
        )
        found = await svc.get_by_source_output(output.id)
        assert found is not None and found.id == created.id
